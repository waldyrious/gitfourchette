from collections import defaultdict
from dataclasses import dataclass, field
from gitfourchette import log
from gitfourchette import porcelain, tempdir
from gitfourchette import settings
from gitfourchette.hiddencommitsolver import HiddenCommitSolver
from gitfourchette.graph import Graph, GraphMarker, GraphSplicer, KF_INTERVAL, BatchRow
from gitfourchette.qt import *
from gitfourchette.settings import BasePrefs
from gitfourchette.toolbox import *
from typing import Iterable
import os
import pygit2


UC_FAKEID = "UC_FAKEID"
PROGRESS_INTERVAL = 5000


def progressTick(progress, i, numCommitsBallpark=0):
    if i != 0 and i % PROGRESS_INTERVAL == 0:
        if numCommitsBallpark > 0 and i <= numCommitsBallpark:
            # Updating the text too often prevents progress bar from updating on macOS theme,
            # so don't use setLabelText if we're changing the progress value
            progress.setValue(i)
        else:
            progress.setLabelText(tr("{0} commits processed.").format(progress.locale().toString(i)))
        QCoreApplication.processEvents()
        if progress.wasCanceled():
            raise StopIteration()


@dataclass
class RepoPrefs(BasePrefs):
    filename = "prefs.json"
    _parentDir = ""

    draftCommitMessage: str = ""
    draftAmendMessage: str = ""
    hiddenBranches: list[str] = field(default_factory=list)

    def getParentDir(self):
        return self._parentDir


class RepoState:
    repo: pygit2.Repository

    # May be None; call initializeWalker before use.
    # Keep it around to speed up refreshing.
    walker: pygit2.Walker | None

    # ordered list of commits
    commitSequence: list[pygit2.Commit]
    # TODO PYGIT2 ^^^ do we want to store the actual commits? wouldn't the oids be enough? not for search though i guess...

    graph: Graph | None

    refCache: dict[str, pygit2.Oid]
    "Maps reference names to commit oids"

    reverseRefCache: dict[pygit2.Oid, list[str]]
    "Maps commit oids to reference names pointing to this commit"

    # path of superproject if this is a submodule
    superproject: str

    # oid of the active commit (to make it bold)
    activeCommitOid: pygit2.Oid | None

    localCommits: GraphMarker | None
    """Use this to look up which commits are part of local branches,
    and which commits are 'foreign'."""

    hiddenCommits: set[pygit2.Oid]

    workdirStale: bool

    uiPrefs: RepoPrefs

    def __init__(self, repo: pygit2.Repository):
        self.repo = repo

        uiConfigPath = os.path.join(self.repo.path, settings.REPO_SETTINGS_DIR)
        self.uiPrefs = RepoPrefs()
        self.uiPrefs._parentDir = uiConfigPath

        # On Windows, core.autocrlf is usually set to true in the system config.
        # However, libgit2 cannot find the system config if git wasn't installed
        # with the official installer, e.g. via scoop. If a repo was cloned with
        # autocrlf=true, GF's staging area would be unusable on Windows without
        # setting autocrlf=true in the config.
        if WINDOWS and "core.autocrlf" not in self.repo.config:
            tempConfigPath = os.path.join(tempdir.getSessionTemporaryDirectory(), "gitconfig")
            log.info("RepoState", "Forcing core.autocrlf=true in: " + tempConfigPath)
            tempConfig = pygit2.Config(tempConfigPath)
            tempConfig["core.autocrlf"] = "true"
            self.repo.config.add_file(tempConfigPath, level=1)

        self.walker = None

        self.commitSequence = []
        self.hiddenCommits = set()

        self.graph = None
        self.localCommits = None

        self.headIsDetached = False
        self.refCache = {}
        self.reverseRefCache = {}
        self.refreshRefCache()

        self.superproject = porcelain.getSuperproject(self.repo)

        self.activeCommitOid = None

        self.workdirStale = True

        self.uiPrefs.load()

        self.resolveHiddenCommits()

    @property
    def hiddenBranches(self):
        return self.uiPrefs.hiddenBranches

    def getDraftCommitMessage(self, forAmending = False) -> str:
        if forAmending:
            return self.uiPrefs.draftAmendMessage
        else:
            return self.uiPrefs.draftCommitMessage

    def setDraftCommitMessage(self, newMessage: str | None, forAmending: bool = False):
        if not newMessage:
            newMessage = ""
        if forAmending:
            self.uiPrefs.draftAmendMessage = newMessage
        else:
            self.uiPrefs.draftCommitMessage = newMessage
        self.uiPrefs.write()

    @benchmark
    def refreshRefCache(self):
        """ Refresh refCache and reverseRefCache.

        Return True if there were any changes in the refs since the last
        refresh, or False if nothing changed.
        """
        self.headIsDetached = self.repo.head_is_detached

        refCache = porcelain.mapRefsToOids(self.repo)

        if refCache == self.refCache:
            # Nothing to do!
            return False

        reverseRefCache = defaultdict(list)
        for k, v in refCache.items():
            reverseRefCache[v].append(k)

        self.refCache = refCache
        self.reverseRefCache = reverseRefCache
        return True

    @property
    def shortName(self) -> str:
        prefix = ""
        if self.superproject:
            superprojectNickname = settings.history.getRepoNickname(self.superproject)
            prefix = superprojectNickname + ": "

        return prefix + settings.history.getRepoNickname(self.repo.workdir)

    @benchmark
    def initializeWalker(self, tipOids: Iterable[pygit2.Oid]) -> pygit2.Walker:
        sorting = pygit2.GIT_SORT_TOPOLOGICAL

        if settings.prefs.graph_chronologicalOrder:
            # In strictly chronological ordering, a commit may appear before its
            # children if it was "created" later than its children. The graph
            # generator produces garbage in this case. So, for chronological
            # ordering, keep GIT_SORT_TOPOLOGICAL in addition to GIT_SORT_TIME.
            sorting |= pygit2.GIT_SORT_TIME

        if self.walker is None:
            self.walker = self.repo.walk(None, sorting)
        else:
            self.walker.sort(sorting)  # this resets the walker

        for tip in tipOids:
            self.walker.push(tip)

        return self.walker

    def updateActiveCommitOid(self):
        try:
            self.activeCommitOid = self.repo.head.target
        except pygit2.GitError:
            self.activeCommitOid = None

    def _uncommittedChangesFakeCommitParents(self):
        try:
            return [self.refCache["HEAD"]]
        except KeyError:  # Unborn HEAD
            return []

    def loadCommitSequence(self, progress: QProgressDialog):
        progress.setLabelText(tr("Processing commit log..."))
        QCoreApplication.processEvents()

        walker = self.initializeWalker(self.refCache.values())

        self.updateActiveCommitOid()

        bench = Benchmark("GRAND TOTAL"); bench.__enter__()

        commitSequence: list[pygit2.Commit | None] = []
        graph = Graph()

        # Retrieve the number of commits that we loaded last time we opened this repo
        # so we can estimate how long it'll take to load it again
        numCommitsBallpark = settings.history.getRepoNumCommits(self.repo.workdir)
        if numCommitsBallpark != 0:
            progress.setMinimum(0)
            progress.setMaximum(2 * numCommitsBallpark)  # reserve second half of progress bar for graph progress

        hiddenCommitSolver = self.newHiddenCommitSolver()
        try:
            for offsetFromTop, commit in enumerate(walker):
                progressTick(progress, offsetFromTop, numCommitsBallpark)
                commitSequence.append(commit)
                hiddenCommitSolver.feed(commit)
        except StopIteration:
            pass

        log.info("loadCommitSequence", F"{self.shortName}: loaded {len(commitSequence):,} commits")
        progress.setLabelText(tr("Preparing graph..."))

        if numCommitsBallpark != 0:
            progress.setMinimum(-len(commitSequence))  # first half of progress bar was for commit log
        progress.setMaximum(len(commitSequence))

        graphGenerator = graph.startGenerator()

        # Generate fake "Uncommitted Changes" with HEAD as parent
        commitSequence.insert(0, None)

        for commit in commitSequence:
            if not commit:
                oid = UC_FAKEID
                parents = self._uncommittedChangesFakeCommitParents()
            else:
                oid = commit.oid
                parents = commit.parent_ids

            graphGenerator.newCommit(oid, parents)

            row = graphGenerator.row
            rowInt = int(row)

            assert type(row) == BatchRow
            assert rowInt >= 0
            graph.commitRows[oid] = row

            # Save keyframes at regular intervals for faster random access,
            # and also at commitless parents to help out GraphMarker
            if rowInt % KF_INTERVAL == 0 or not parents:
                graph.saveKeyframe(graphGenerator)

            if rowInt % KF_INTERVAL == 0:
                progress.setValue(rowInt)
                QCoreApplication.processEvents()

        log.info("loadCommitSequence", "Peak arc count:", graphGenerator.peakArcCount)

        self.commitSequence = commitSequence
        self.hiddenCommits = hiddenCommitSolver.hiddenCommits
        self.graph = graph

        self.refreshLocalCommits()

        bench.__exit__(None, None, None)

        return commitSequence

    @benchmark
    def loadChangedRefs(self, oldRefCache: dict[str, pygit2.Oid]):
        # DO NOT call processEvents() here. While splicing a large amount of
        # commits, GraphView may try to repaint an incomplete graph.
        # GraphView somehow ignores setUpdatesEnabled(False) here!

        newCommitSequence = []

        oldHeads = oldRefCache.values()
        newHeads = self.refCache.values()

        walker = self.initializeWalker(newHeads)

        graphSplicer = GraphSplicer(self.graph, oldHeads, newHeads)
        newHiddenCommitSolver: HiddenCommitSolver = self.newHiddenCommitSolver()

        # Generate fake "Uncommitted Changes" with HEAD as parent
        newCommitSequence.insert(0, None)
        graphSplicer.spliceNewCommit(UC_FAKEID, self._uncommittedChangesFakeCommitParents())

        if graphSplicer.keepGoing:
            with Benchmark("Walk graph until equilibrium"):
                for commit in walker:
                    newCommitSequence.append(commit)
                    graphSplicer.spliceNewCommit(commit.oid, commit.parent_ids)
                    newHiddenCommitSolver.feed(commit)
                    if not graphSplicer.keepGoing:
                        break

        graphSplicer.finish()

        if graphSplicer.foundEquilibrium:
            nRemoved = graphSplicer.equilibriumOldRow
            nAdded = graphSplicer.equilibriumNewRow
        else:
            nRemoved = -1  # We could use len(self.commitSequence), but -1 will force refreshRepo to replace the model wholesale
            nAdded = len(newCommitSequence)

        # Piece correct commit sequence back together
        with Benchmark("Reassemble commit sequence"):
            if not graphSplicer.foundEquilibrium:
                self.commitSequence = newCommitSequence
            elif nAdded == 0 and nRemoved == 0:
                pass
            elif nRemoved == 0:
                self.commitSequence = newCommitSequence[:nAdded] + self.commitSequence
            else:
                self.commitSequence = newCommitSequence[:nAdded] + self.commitSequence[nRemoved:]

        self.refreshLocalCommits()

        # Update hidden commits
        self.hiddenCommits.update(newHiddenCommitSolver.hiddenCommits)

        self.updateActiveCommitOid()

        return nRemoved, nAdded

    @benchmark
    def refreshLocalCommits(self):
        localCommits = GraphMarker(self.graph)
        for refName, commitOid in self.refCache.items():
            if refName == 'HEAD' or refName.startswith("refs/heads/"):
                localCommits.mark(commitOid)
        self.localCommits = localCommits

    @benchmark
    def toggleHideBranch(self, branchName: str):
        if branchName not in self.hiddenBranches:
            self.hideBranch(branchName)
        else:
            self.unhideBranch(branchName)

    def hideBranch(self, branchName: str):
        if branchName in self.hiddenBranches:
            return
        self.uiPrefs.hiddenBranches.append(branchName)
        self.uiPrefs.write()
        self.resolveHiddenCommits()

    def unhideBranch(self, branchName: str):
        if branchName not in self.hiddenBranches:
            return
        self.uiPrefs.hiddenBranches.remove(branchName)
        self.uiPrefs.write()
        self.resolveHiddenCommits()

    def getHiddenBranchOids(self):
        seeds = set()

        def isSharedByVisibleBranch(oid):
            return any(
                refName for refName in self.reverseRefCache[oid]
                if refName not in self.hiddenBranches
                and not refName.startswith(porcelain.TAGS_PREFIX))

        hiddenBranches = self.hiddenBranches[:]
        for hiddenBranch in hiddenBranches:
            try:
                oid = self.refCache[hiddenBranch]
                if not isSharedByVisibleBranch(oid):
                    seeds.add(oid)
            except (KeyError, pygit2.InvalidSpecError):
                log.info("RepoState", "Skipping missing hidden branch: " + hiddenBranch)
                self.uiPrefs.hiddenBranches.remove(hiddenBranch)  # Remove it from prefs

        return seeds

    def newHiddenCommitSolver(self) -> HiddenCommitSolver:
        solver = HiddenCommitSolver()

        for hiddenBranchTip in self.getHiddenBranchOids():
            solver.hideCommit(hiddenBranchTip)

        if settings.prefs.debug_hideStashJunkParents:
            for stash in self.repo.listall_stashes():
                stashCommit: pygit2.Commit = self.repo[stash.commit_id].peel(pygit2.Commit)
                if len(stashCommit.parents) >= 2 and stashCommit.parents[1].raw_message.startswith(b"index on "):
                    solver.hideCommit(stashCommit.parents[1].id, force=True)
                if len(stashCommit.parents) >= 3 and stashCommit.parents[2].raw_message.startswith(b"untracked files on "):
                    solver.hideCommit(stashCommit.parents[2].id, force=True)

        return solver

    def resolveHiddenCommits(self):
        solver = self.newHiddenCommitSolver()
        for commit in self.commitSequence:
            if not commit:  # May be a fake commit such as Uncommitted Changes
                continue
            solver.feed(commit)
            if solver.done:
                break
        self.hiddenCommits = solver.hiddenCommits
