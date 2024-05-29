import logging

from gitfourchette import colors
from gitfourchette import settings
from gitfourchette.application import GFApplication
from gitfourchette.graph import Graph, BatchRow
from gitfourchette.diffview.diffdocument import DiffDocument
from gitfourchette.diffview.specialdiff import (ShouldDisplayPatchAsImageDiff, SpecialDiffError, DiffImagePair,
                                                DiffConflict)
from gitfourchette.graphview.commitlogmodel import SpecialRow
from gitfourchette.nav import NavLocator, NavFlags, NavContext
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskEffects
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables

logger = logging.getLogger(__name__)

RENAME_COUNT_THRESHOLD = 100
""" Don't find_similar beyond this number of files in the main diff """

def contextLines():
    return settings.prefs.contextLines


class PrimeRepo(RepoTask):
    progressRange = Signal(int, int)
    progressValue = Signal(int)
    progressMessage = Signal(str)
    progressAbortable = Signal(bool)

    abortFlag: bool

    def onAbortButtonClicked(self):
        self.abortFlag = True

    def flow(self, path: str, maxCommits: int = -1):
        from gitfourchette.graph import KF_INTERVAL
        from gitfourchette.repowidget import RepoWidget
        from gitfourchette.repostate import RepoState, UC_FAKEID
        from gitfourchette.tasks.jumptasks import Jump

        assert path

        rw = self.rw
        assert isinstance(rw, RepoWidget)

        progressWidget = rw.setPlaceholderWidgetOpenRepoProgress()

        self.abortFlag = False
        self.progressRange.connect(progressWidget.ui.progressBar.setRange)
        self.progressValue.connect(progressWidget.ui.progressBar.setValue)
        self.progressMessage.connect(progressWidget.ui.label.setText)
        self.progressAbortable.connect(progressWidget.ui.abortButton.setEnabled)
        progressWidget.ui.abortButton.clicked.connect(self.onAbortButtonClicked)

        # Create the repo
        repo = Repo(path, RepositoryOpenFlag.NO_SEARCH)
        self.setRepo(repo)  # required to execute subtasks later

        if repo.is_bare:
            raise NotImplementedError(self.tr("Sorry, {app} doesn’t support bare repositories.").format(app=qAppName()))

        # Bind to sessionwide git config file
        sessionwideConfigPath = GFApplication.instance().sessionwideGitConfigPath
        # Level -1 was chosen because it's the only level for which changing branch settings
        # in a repo won't leak into this file (e.g. change branch upstream).
        # TODO: `level=4, force=True` would make sense here but this leaks branch settings. Is this a bug in pygit2?
        #       git_config_add_file_ondisk has an optional 'repo' argument "to allow parsing of conditional includes",
        #       but pygit2 doesn't make it possible to pass anything but NULL.
        #       See also https://github.com/libgit2/libgit2/blob/main/include/git2/config.h#L42
        repo.config.add_file(sessionwideConfigPath, level=-1)

        # Create repo state
        state = RepoState(rw, repo)

        # ---------------------------------------------------------------------
        # EXIT UI THREAD
        # ---------------------------------------------------------------------
        yield from self.flowEnterWorkerThread()

        locale = QLocale()

        # Prime the walker (this might take a while)
        walker = state.initializeWalker(state.refCache.values())

        state.updateActiveCommitId()

        commitSequence: list[Commit | None] = []

        # Retrieve the number of commits that we loaded last time we opened this repo
        # so we can estimate how long it'll take to load it again
        numCommitsBallpark = settings.history.getRepoNumCommits(repo.workdir)
        if numCommitsBallpark != 0:
            # Reserve second half of progress bar for graph progress
            self.progressRange.emit(0, 2*numCommitsBallpark)

        # ---------------------------------------------------------------------
        # Build commit sequence

        self.progressAbortable.emit(True)

        truncatedHistory = False
        if maxCommits < 0:  # -1 means take maxCommits from prefs. Warning, pref value can be 0, meaning infinity!
            maxCommits = settings.prefs.maxCommits
        if maxCommits == 0:  # 0 means infinity
            maxCommits = 2**63  # ought to be enough
        progressInterval = 5000 if maxCommits >= 10000 else 1000

        for i, commit in enumerate(walker):
            commitSequence.append(commit)

            if i+1 >= maxCommits or (self.abortFlag and i+1 >= progressInterval):
                truncatedHistory = True
                break

            # Report progress, not too often
            if i != 0 and i % progressInterval == 0:
                message = self.tr("{0} commits...").format(locale.toString(i))
                self.progressMessage.emit(message)
                if numCommitsBallpark > 0 and i <= numCommitsBallpark:
                    self.progressValue.emit(i)

        # Can't abort anymore
        self.progressAbortable.emit(False)

        numCommits = len(commitSequence)
        logger.info(f"{state.shortName}: loaded {numCommits} commits")
        if truncatedHistory:
            message = self.tr("{0} commits (truncated log).").format(locale.toString(numCommits))
        else:
            message = self.tr("{0} commits total.").format(locale.toString(numCommits))
        self.progressMessage.emit(message)

        if numCommitsBallpark != 0:
            # First half of progress bar was for commit log
            self.progressRange.emit(-numCommits, numCommits)
        else:
            self.progressRange.emit(0, numCommits)
        self.progressValue.emit(0)

        # ---------------------------------------------------------------------
        # Build graph

        graph = Graph()
        graphGenerator = graph.startGenerator()

        # Generate fake "Uncommitted Changes" with HEAD as parent
        commitSequence.insert(0, None)  # Uncommitted Changes

        state.hiddenCommits = set()
        state.foreignCommits = set()
        hiddenCommitSolver = state.newHiddenCommitSolver()
        foreignCommitSolver = state.newForeignCommitSolver()

        for commit in commitSequence:
            if not commit:
                oid = UC_FAKEID
                parents = state._uncommittedChangesFakeCommitParents()
            else:
                oid = commit.id
                parents = commit.parent_ids

            graphGenerator.newCommit(oid, parents)

            foreignCommitSolver.newCommit(oid, parents, state.foreignCommits)
            hiddenCommitSolver.newCommit(oid, parents, state.hiddenCommits)

            row = graphGenerator.row
            rowInt = int(row)

            assert type(row) == BatchRow
            assert rowInt >= 0
            graph.commitRows[oid] = row

            # Save keyframes at regular intervals for faster random access.
            if rowInt % KF_INTERVAL == 0:
                graph.saveKeyframe(graphGenerator)
                self.progressValue.emit(rowInt)

        self.progressValue.emit(numCommits)

        logger.debug(f"Peak arc count: {graphGenerator.peakArcCount}")

        state.commitSequence = commitSequence
        state.truncatedHistory = truncatedHistory
        state.graph = graph

        # ---------------------------------------------------------------------
        # RETURN TO UI THREAD
        # ---------------------------------------------------------------------
        yield from self.flowEnterUiThread()

        # Assign state to RepoWidget
        rw.state = state

        # Save commit count (if not truncated)
        if not truncatedHistory:
            settings.history.setRepoNumCommits(repo.workdir, numCommits)

        # Bump repo in history
        settings.history.addRepo(repo.workdir)
        settings.history.setRepoSuperproject(repo.workdir, state.superproject)
        settings.history.write()
        rw.window().fillRecentMenu()  # TODO: emit signal instead?

        # Finally, prime the UI.

        # Prime GraphView
        with QSignalBlockerContext(rw.graphView):
            if state.truncatedHistory:
                extraRow = SpecialRow.TruncatedHistory
            elif repo.is_shallow:
                extraRow = SpecialRow.EndOfShallowHistory
            else:
                extraRow = SpecialRow.Invalid

            rw.graphView.clModel._extraRow = extraRow
            rw.graphView.setHiddenCommits(state.hiddenCommits)
            rw.graphView.setCommitSequence(commitSequence)
            rw.graphView.selectRowForLocator(NavLocator.inWorkdir(), force=True)

        # Prime Sidebar
        with QSignalBlockerContext(rw.sidebar):
            collapseCache = state.uiPrefs.collapseCache
            if collapseCache:
                rw.sidebar.collapseCache = set(collapseCache)
                rw.sidebar.collapseCacheValid = True
            rw.sidebar.refresh(state)

        # Restore main UI
        rw.removePlaceholderWidget()

        # Refresh tab text
        rw.nameChange.emit()

        # Splitters may have moved around while loading, restore them
        rw.restoreSplitterStates()

        # Scrolling HEAD into view isn't super intuitive if we boot to Uncommitted Changes
        # if newState.activeCommitId:
        #     rw.graphView.scrollToCommit(newState.activeCommitId, QAbstractItemView.ScrollHint.PositionAtCenter)

        # Focus on some interesting widget within the RepoWidget after loading the repo.
        # (delay to next event loop so Qt has time to show the widget first)
        QTimer.singleShot(0, rw.setInitialFocus)

        # Jump to workdir (or pending locator, if any)
        if not rw.pendingLocator:
            initialLocator = NavLocator(NavContext.WORKDIR)
        else:
            # Consume pending locator
            initialLocator = rw.pendingLocator
            rw.pendingLocator = NavLocator()
        yield from self.flowSubtask(Jump, initialLocator)
        rw.graphView.scrollToRowForLocator(initialLocator, QAbstractItemView.ScrollHint.PositionAtCenter)

    def onError(self, exc: Exception):
        self.rw.cleanup(str(exc), allowAutoReload=False)
        super().onError(exc)


class LoadWorkdir(RepoTask):
    def canKill(self, task: RepoTask):
        if type(task) is LoadWorkdir:
            logger.warning("LoadWorkdir is killing another LoadWorkdir. This is inefficient!")
            return True
        return type(task) in [LoadCommit, LoadPatch]

    def flow(self, allowWriteIndex: bool):
        yield from self.flowEnterWorkerThread()

        with Benchmark("LoadWorkdir/Index"):
            self.repo.refresh_index()

        with Benchmark("LoadWorkdir/Staged"):
            self.stageDiff = self.repo.get_staged_changes(context_lines=contextLines())

        yield from self.flowEnterWorkerThread()  # let task thread be interrupted here
        with Benchmark("LoadWorkdir/Unstaged"):
            self.dirtyDiff = self.repo.get_unstaged_changes(allowWriteIndex, context_lines=contextLines())


class LoadCommit(RepoTask):
    def canKill(self, task: RepoTask):
        return type(task) in [LoadWorkdir, LoadCommit, LoadPatch]

    def flow(self, locator: NavLocator):
        yield from self.flowEnterWorkerThread()

        oid = locator.commit
        largeCommitThreshold = -1 if locator.hasFlags(NavFlags.AllowLargeCommits) else RENAME_COUNT_THRESHOLD

        self.diffs, self.skippedRenameDetection = self.repo.commit_diffs(
            oid, find_similar_threshold=largeCommitThreshold, context_lines=contextLines())
        self.message = self.repo.get_commit_message(oid)


class LoadPatch(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Nothing  # let custom callback in RepoWidget do it

    def canKill(self, task: RepoTask):
        return type(task) in [LoadPatch]

    def _processPatch(self, patch: Patch, locator: NavLocator
                      ) -> DiffDocument | SpecialDiffError | DiffConflict | DiffImagePair:
        if not patch:
            locator = locator.withExtraFlags(NavFlags.Force)
            longformItems = [locator.toHtml(self.tr("Try to reload the file."))]

            if locator.context.isWorkdir() and not settings.prefs.autoRefresh:
                prefKey = "autoRefresh"
                tip = self.tr("Consider re-enabling [{0}] to prevent this issue."
                              ).format(hquo(TrTables.prefKey(prefKey)))
                tip = linkify(tip, makeInternalLink("prefs", prefKey))
                longformItems.append(tip)

            return SpecialDiffError(self.tr("Outdated diff."),
                                    self.tr("The file appears to have changed on disk."),
                                    icon="SP_MessageBoxWarning",
                                    longform=toRoomyUL(longformItems))

        if not patch.delta:
            # Rare libgit2 bug, should be fixed in 1.6.0
            return SpecialDiffError(self.tr("Patch has no delta!"), icon="SP_MessageBoxWarning")

        if patch.delta.status == DeltaStatus.CONFLICTED:
            path = patch.delta.new_file.path
            return self.repo.wrap_conflict(path)

        if FileMode.COMMIT in (patch.delta.new_file.mode, patch.delta.old_file.mode):
            return SpecialDiffError.submoduleDiff(self.repo, patch, locator)

        try:
            diffModel = DiffDocument.fromPatch(patch, locator)
            diffModel.document.moveToThread(QApplication.instance().thread())
            return diffModel
        except SpecialDiffError as dme:
            return dme
        except ShouldDisplayPatchAsImageDiff:
            return DiffImagePair(self.repo, patch.delta, locator)
        except BaseException as exc:
            summary, details = excStrings(exc)
            return SpecialDiffError(summary, icon="SP_MessageBoxCritical", preformatted=details)

    def _makeHeader(self, result, locator):
        header = "<html>" + escape(locator.path)

        if isinstance(result, DiffDocument):
            if settings.prefs.colorblind:
                addColor = colors.teal
                delColor = colors.orange
            else:
                addColor = colors.olive
                delColor = colors.red
            if result.pluses:
                header += f" <span style='color: {addColor.name()};'>+{result.pluses}</span>"
            if result.minuses:
                header += f" <span style='color: {delColor.name()};'>-{result.minuses}</span>"

        locationText = ""
        if locator.context == NavContext.COMMITTED:
            locationText = self.tr("at {0}", "at <specific commit>").format(shortHash(locator.commit))
        elif locator.context.isWorkdir():
            locationText = locator.context.translateName().lower()
        if locationText:
            header += f" <span style='color: gray;'>({locationText})</span>"

        return header

    def flow(self, patch: Patch, locator: NavLocator):
        # yield from self.flowEnterWorkerThread()
        yield from self.flowEnterUiThread()
        # QThread.msleep(500)
        self.result = self._processPatch(patch, locator)
        self.header = self._makeHeader(self.result, locator)
