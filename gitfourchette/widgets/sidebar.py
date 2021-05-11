from allqt import *
from dialogs.trackedbranchdialog import TrackedBranchDialog
from widgets.sidebardelegate import SidebarDelegate
from widgets.sidebarentry import SidebarEntry
from util import labelQuote, textInputDialog, shortHash
import git


# TODO: we should just use a custom model
def SidebarItem(name: str, data=None) -> QStandardItem:
    item = QStandardItem(name)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    if data:
        item.setData(data, Qt.UserRole)
    item.setSizeHint(QSize(-1, 16))
    return item


def SidebarSeparator() -> QStandardItem:
    sep = SidebarItem(None)
    sep.setSelectable(False)
    sep.setEnabled(False)
    sep.setSizeHint(QSize(-1, 8))
    return sep


class Sidebar(QTreeView):
    uncommittedChangesClicked = Signal()
    refClicked = Signal(str)
    tagClicked = Signal(str)
    newBranch = Signal(str)
    switchToBranch = Signal(str)
    renameBranch = Signal(str, str)
    editTrackingBranch = Signal(str, str)
    mergeBranchIntoActive = Signal(str)
    rebaseActiveOntoBranch = Signal(str)
    deleteBranch = Signal(str)
    pushBranch = Signal(str)
    newTrackingBranch = Signal(str, str)
    editRemoteURL = Signal(str, str)

    currentGitRepo: git.Repo

    def __init__(self, parent):
        super().__init__(parent)

        self.setMinimumWidth(128)

        self.currentGitRepo = None

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        #self.setUniformRowHeights(True)
        self.setHeaderHidden(True)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.onCustomContextMenuRequested)

        self.setObjectName("sidebar")  # for styling

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRootIsDecorated(False)
        self.setIndentation(0)
        self.setItemDelegate(SidebarDelegate(self))

    def onCustomContextMenuRequested(self, localPoint: QPoint):
        globalPoint = self.mapToGlobal(localPoint)
        index = self.indexAt(localPoint)
        data: SidebarEntry = index.data(Qt.UserRole)

        if not data:
            return

        menu = QMenu(self)

        if data.type == SidebarEntry.Type.LOCAL_BRANCHES_HEADER:
            menu.addAction(F"&New Branch...", self._newBranchFlow)

        elif data.type == SidebarEntry.Type.LOCAL_REF:
            if data.name != self.activeBranchName:
                menu.addAction(
                    F"&Switch to {labelQuote(data.name)}",
                    lambda: self.switchToBranch.emit(data.name))
                if self.activeBranchName:
                    menu.addSeparator()
                    menu.addAction(
                        F"&Merge {labelQuote(data.name)} into {labelQuote(self.activeBranchName)}...",
                        lambda: self.mergeBranchIntoActive.emit(data.name))
                    menu.addAction(
                        F"&Rebase {labelQuote(self.activeBranchName)} onto {labelQuote(data.name)}...",
                        lambda: self.rebaseActiveOntoBranch.emit(data.name))

            menu.addSeparator()

            if data.trackingBranch:
                menu.addAction(F"&Push to {labelQuote(data.trackingBranch)}...", lambda: self.pushBranch.emit(data.name))
            else:
                a = menu.addAction("&Push: no tracked branch")
                a.setEnabled(False)

            menu.addAction("Set &Tracked Branch...", lambda: self._editTrackingBranchFlow(data.name))

            menu.addSeparator()

            menu.addAction("Re&name...", lambda: self._renameBranchFlow(data.name))
            menu.addAction("&Delete...", lambda: self._deleteBranchFlow(data.name))

            menu.addSeparator()

            a = menu.addAction(F"Show In Graph")
            a.setCheckable(True)
            a.setChecked(True)

        elif data.type == SidebarEntry.Type.REMOTE_REF:
            menu.addAction(F"New local branch tracking {labelQuote(data.name)}...", lambda: self._newTrackingBranchFlow(data.name))

        elif data.type == SidebarEntry.Type.REMOTE:
            menu.addAction(F"Edit URL...", lambda: self._editRemoteURLFlow(data.name))

        menu.exec_(globalPoint)

    def _newBranchFlow(self):
        newBranchName, ok = textInputDialog(self, "New Branch", "Enter name for new branch:", None)
        if ok:
            self.newBranch.emit(newBranchName)

    def _editTrackingBranchFlow(self, localBranchName):
        dlg = TrackedBranchDialog(self.currentGitRepo, localBranchName, self)
        rc = dlg.exec_()
        newTrackingBranchName = dlg.newTrackingBranchName
        dlg.deleteLater()  # avoid leaking dialog (can't use WA_DeleteOnClose because we needed to retrieve the message)
        if rc != QDialog.DialogCode.Accepted:
            return
        self.editTrackingBranch.emit(localBranchName, newTrackingBranchName)

    def _renameBranchFlow(self, oldName):
        newName, ok = textInputDialog(
            self,
            "Rename Branch",
            F"Enter new name for branch <b>{labelQuote(oldName)}</b>:",
            oldName,
            okButtonText="Rename")
        if ok:
            self.renameBranch.emit(oldName, newName)

    def _deleteBranchFlow(self, localBranchName):
        rc = QMessageBox.warning(self, "Delete Branch",
                                 F"Really delete local branch <b>{labelQuote(localBranchName)}</b>?"
                                 F"<br>This cannot be undone!",
                                 QMessageBox.Discard | QMessageBox.Cancel)
        if rc == QMessageBox.Discard:
            self.deleteBranch.emit(localBranchName)

    def _newTrackingBranchFlow(self, remoteBranchName):
        localBranchName, ok = textInputDialog(
            self,
            "New Tracking Branch",
            F"Enter name for a new local branch that will track remote branch {labelQuote(remoteBranchName)}:",
            remoteBranchName[remoteBranchName.find('/') + 1:],
            okButtonText="Create")
        if ok:
            self.newTrackingBranch.emit(localBranchName, remoteBranchName)

    def _editRemoteURLFlow(self, remoteName):
        newURL, ok = textInputDialog(
            self,
            "Edit Remote URL",
            F"Enter new URL for remote <b>{labelQuote(remoteName)}</b>:",
            self.currentGitRepo.remote(remoteName).url)
        if ok:
            self.editRemoteURL.emit(remoteName, newURL)

    def fill(self, repo: git.Repo):
        model = QStandardItemModel()

        if repo.head.is_detached:
            self.activeBranchName = None
        else:
            self.activeBranchName = repo.active_branch.name

        uncommittedChangesEntry = SidebarEntry(SidebarEntry.Type.UNCOMMITTED_CHANGES, None)
        uncommittedChanges = SidebarItem("Changes", uncommittedChangesEntry)
        model.appendRow(uncommittedChanges)

        model.appendRow(SidebarSeparator())

        branchesParentEntry = SidebarEntry(SidebarEntry.Type.LOCAL_BRANCHES_HEADER, None)
        branchesParent = SidebarItem("Local Branches", branchesParentEntry)
        branchesParent.setSelectable(False)

        if repo.head.is_detached:
            caption = F"★ detached HEAD @ {shortHash(repo.head.commit.hexsha)}"
            branchEntry = SidebarEntry(SidebarEntry.Type.DETACHED_HEAD, None)
            item = SidebarItem(caption, branchEntry)
            item.setToolTip(F"detached HEAD @{shortHash(repo.head.commit.hexsha)}")
            branchesParent.appendRow(item)

        for branch in repo.branches:
            caption = branch.name
            tooltip = branch.name
            if not repo.head.is_detached and repo.active_branch == branch:
                caption = F"★ {caption}"
                tooltip += " (★ active branch)"
            branchEntry = SidebarEntry(SidebarEntry.Type.LOCAL_REF, branch.name)
            if branch.tracking_branch():
                branchEntry.trackingBranch = branch.tracking_branch().name
                tooltip += F"\ntracking {branchEntry.trackingBranch}"
            item = SidebarItem(caption, branchEntry)
            item.setToolTip(tooltip)
            branchesParent.appendRow(item)
        model.appendRow(branchesParent)

        model.appendRow(SidebarSeparator())

        remote: git.Remote
        for remote in repo.remotes:
            remoteEntry = SidebarEntry(SidebarEntry.Type.REMOTE, remote.name)
            remoteParent = SidebarItem(F"Remote “{remote.name}”", remoteEntry)
            remoteParent.setSelectable(False)
            remotePrefix = remote.name + '/'
            for remoteRef in remote.refs:
                remoteRefShortName = remoteRef.name
                if remoteRefShortName.startswith(remotePrefix):
                    remoteRefShortName = remoteRefShortName[len(remotePrefix):]
                remoteRefEntry = SidebarEntry(SidebarEntry.Type.REMOTE_REF, remoteRef.name)
                remoteRefItem = SidebarItem(remoteRefShortName, remoteRefEntry)
                remoteParent.appendRow(remoteRefItem)
            model.appendRow(remoteParent)
            model.appendRow(SidebarSeparator())

        tagsParent = QStandardItem("Tags")
        tagsParent.setSelectable(False)
        tag: git.Tag
        for tag in repo.tags:
            tagEntry = SidebarEntry(SidebarEntry.Type.TAG, tag.name)
            tagItem = SidebarItem(tag.name, tagEntry)
            tagsParent.appendRow(tagItem)
        model.appendRow(tagsParent)

        self.currentGitRepo = repo
        self._replaceModel(model)

        # expand branch container
        self.setExpanded(model.indexFromItem(branchesParent), True)

    def _replaceModel(self, model):
        if self.model():
            self.model().deleteLater()  # avoid memory leak
        self.setModel(model)

    def currentChanged(self, current: QModelIndex, previous: QModelIndex):
        super().currentChanged(current, previous)
        if not current.isValid():
            return
        data: SidebarEntry = current.data(Qt.UserRole)
        if not data:
            return
        if data.type == SidebarEntry.Type.UNCOMMITTED_CHANGES:
            self.uncommittedChangesClicked.emit()
        elif data.type in [SidebarEntry.Type.LOCAL_REF, SidebarEntry.Type.REMOTE_REF]:
            self.refClicked.emit(data.name)
        elif data.type == SidebarEntry.Type.TAG:
            self.tagClicked.emit(data.name)

    def mousePressEvent(self, event: QMouseEvent):
        index: QModelIndex = self.indexAt(event.pos())
        lastState = self.isExpanded(index)
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton and index.isValid() and lastState == self.isExpanded(index):
            self.setExpanded(index, not lastState)

    def mouseDoubleClickEvent(self, event):
        index: QModelIndex = self.indexAt(event.pos())
        if event.button() == Qt.LeftButton and index.isValid():
            data: SidebarEntry = index.data(Qt.UserRole)
            if data.type == SidebarEntry.Type.LOCAL_REF:
                self.switchToBranch.emit(data.name)
                return
        super().mouseDoubleClickEvent(event)

