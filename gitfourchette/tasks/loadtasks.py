from gitfourchette import porcelain
from gitfourchette import util
from gitfourchette.qt import *
from gitfourchette.stagingstate import StagingState
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat
from gitfourchette.widgets.diffmodel import DiffModelError, DiffConflict, DiffModel, ShouldDisplayPatchAsImageDiff, \
    DiffImagePair
import pygit2


class LoadWorkdirDiffs(RepoTask):
    def name(self):
        return translate("Operation", "Refresh working directory")

    def flow(self, allowUpdateIndex: bool):
        yield from self._flowBeginWorkerThread()
        porcelain.refreshIndex(self.repo)
        self.dirtyDiff = porcelain.diffWorkdirToIndex(self.repo, allowUpdateIndex)
        self.stageDiff = porcelain.diffIndexToHead(self.repo)


class LoadCommit(RepoTask):
    def name(self):
        return translate("Operation", "Load commit")

    def flow(self, oid: pygit2.Oid):
        yield from self._flowBeginWorkerThread()
        # import time; time.sleep(1) #----------to debug out-of-order events
        self.diffs = porcelain.loadCommitDiffs(self.repo, oid)


class LoadPatch(RepoTask):
    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.NOTHING  # let custom callback in RepoWidget do it

    def name(self):
        return translate("Operation", "Load diff")

    def _processPatch(self, patch: pygit2.Patch, stagingState: StagingState
                      ) -> DiffModel | DiffModelError | DiffConflict | DiffImagePair:
        if not patch:
            return DiffModelError(
                self.tr("Patch is invalid."),
                self.tr("The patched file may have changed on disk since we last read it. Try refreshing the window."),
                icon=QStyle.StandardPixmap.SP_MessageBoxWarning)

        if patch.delta.status == pygit2.GIT_DELTA_CONFLICTED:
            ancestor, ours, theirs = self.repo.index.conflicts[patch.delta.new_file.path]
            return DiffConflict(self.repo, ancestor, ours, theirs)

        try:
            diffModel = DiffModel.fromPatch(patch)
            diffModel.document.moveToThread(QApplication.instance().thread())
            return diffModel
        except DiffModelError as dme:
            return dme
        except ShouldDisplayPatchAsImageDiff:
            return DiffImagePair(self.repo, patch.delta, stagingState)
        except BaseException as exc:
            summary, details = util.excStrings(exc)
            return DiffModelError(summary, icon=QStyle.StandardPixmap.SP_MessageBoxCritical, preformatted=details)

    def flow(self, patch: pygit2.Patch, stagingState: StagingState):
        yield from self._flowBeginWorkerThread()
        self.result = self._processPatch(patch, stagingState)
