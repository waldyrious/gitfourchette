from gitfourchette import log
from gitfourchette import porcelain
from gitfourchette import util
from gitfourchette.benchmark import Benchmark
from gitfourchette.nav import NavLocator, NavFlags
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskEffects
from gitfourchette.widgets.diffmodel import DiffModelError, DiffConflict, DiffModel, ShouldDisplayPatchAsImageDiff, \
    DiffImagePair
import pygit2

TAG = "LoadTasks"


class LoadWorkdir(RepoTask):
    def name(self):
        return translate("Operation", "Refresh working directory")

    def canKill(self, task: RepoTask):
        if type(task) is LoadWorkdir:
            log.warning(TAG, "LoadWorkdir is killing another LoadWorkdir. This is inefficient!")
            return True
        return type(task) in [LoadCommit, LoadPatch]

    def flow(self, allowWriteIndex: bool):
        yield from self._flowBeginWorkerThread()

        with Benchmark("LoadWorkdir/Index"):
            porcelain.refreshIndex(self.repo)

        yield from self._flowBeginWorkerThread()  # let task thread be interrupted here
        with Benchmark("LoadWorkdir/Staged"):
            self.stageDiff = porcelain.getStagedChanges(self.repo)

        yield from self._flowBeginWorkerThread()  # let task thread be interrupted here
        with Benchmark("LoadWorkdir/Unstaged"):
            self.dirtyDiff = porcelain.getUnstagedChanges(self.repo, allowWriteIndex)


class LoadCommit(RepoTask):
    def name(self):
        return translate("Operation", "Load commit")

    def canKill(self, task: RepoTask):
        return type(task) in [LoadWorkdir, LoadCommit, LoadPatch]

    def flow(self, oid: pygit2.Oid):
        yield from self._flowBeginWorkerThread()
        # import time; time.sleep(1) #----------to debug out-of-order events
        self.diffs = porcelain.loadCommitDiffs(self.repo, oid)
        self.message = porcelain.getCommitMessage(self.repo, oid)


class LoadPatch(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Nothing  # let custom callback in RepoWidget do it

    def name(self):
        return translate("Operation", "Load diff")

    def canKill(self, task: RepoTask):
        return type(task) in [LoadPatch]

    def _processPatch(self, patch: pygit2.Patch, locator: NavLocator
                      ) -> DiffModel | DiffModelError | DiffConflict | DiffImagePair:
        if not patch:
            locator = locator.withExtraFlags(NavFlags.ForceRefreshWorkdir)
            message = locator.toHtml(self.tr("The file appears to have changed on disk since we cached it. "
                                             "[Try to refresh it.]"))
            return DiffModelError(self.tr("Outdated diff."), message,
                                  icon=QStyle.StandardPixmap.SP_MessageBoxWarning)

        if not patch.delta:
            # Rare libgit2 bug, should be fixed in 1.6.0
            return DiffModelError(self.tr("Patch has no delta!"), icon=QStyle.StandardPixmap.SP_MessageBoxWarning)

        if patch.delta.status == pygit2.GIT_DELTA_CONFLICTED:
            ancestor, ours, theirs = self.repo.index.conflicts[patch.delta.new_file.path]
            return DiffConflict(ancestor, ours, theirs)

        try:
            diffModel = DiffModel.fromPatch(patch, locator)
            diffModel.document.moveToThread(QApplication.instance().thread())
            return diffModel
        except DiffModelError as dme:
            return dme
        except ShouldDisplayPatchAsImageDiff:
            return DiffImagePair(self.repo, patch.delta, locator)
        except BaseException as exc:
            summary, details = util.excStrings(exc)
            return DiffModelError(summary, icon=QStyle.StandardPixmap.SP_MessageBoxCritical, preformatted=details)

    def flow(self, patch: pygit2.Patch, locator: NavLocator):
        yield from self._flowBeginWorkerThread()
        # import time; time.sleep(1) #----------to debug out-of-order events
        self.result = self._processPatch(patch, locator)
