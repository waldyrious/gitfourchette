import porcelain
from allqt import *
from util import labelQuote, shortHash
from widgets.brandeddialog import showTextInputDialog
from widgets.remotedialog import RemoteDialog
from widgets.trackedbranchdialog import TrackedBranchDialog
from widgets.sidebardelegate import SidebarDelegate
from widgets.sidebarentry import SidebarEntry
import pygit2


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
    commitClicked = Signal(pygit2.Oid)
    newBranch = Signal(str)
    switchToBranch = Signal(str)
    renameBranch = Signal(str, str)
    editTrackingBranch = Signal(str, str)
    mergeBranchIntoActive = Signal(str)
    rebaseActiveOntoBranch = Signal(str)
    deleteBranch = Signal(str)
    pushBranch = Signal(str)
    newTrackingBranch = Signal(str, str)
    editRemote = Signal(str, str, str)

    repo: pygit2.Repository

    def __init__(self, parent):
        super().__init__(parent)

        self.setMinimumWidth(128)

        self.repo = None

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
        menu.setObjectName("SidebarContextMenu")

        if data.type == SidebarEntry.Type.LOCAL_BRANCHES_HEADER:
            menu.addAction(F"&New Branch...", self._newBranchFlow)

        elif data.type == SidebarEntry.Type.LOCAL_REF:
            strippedName = data.name.removeprefix("refs/heads/")
            branch: pygit2.Branch = self.repo.lookup_branch(strippedName)

            activeBranchName = porcelain.getActiveBranchShorthand(self.repo)

            switchAction: QAction = menu.addAction(F"&Switch to {labelQuote(strippedName)}")
            menu.addSeparator()
            mergeAction: QAction = menu.addAction(F"&Merge {labelQuote(strippedName)} into {labelQuote(activeBranchName)}...")
            rebaseAction: QAction = menu.addAction(F"&Rebase {labelQuote(activeBranchName)} onto {labelQuote(strippedName)}...")

            switchAction.setIcon(QIcon.fromTheme("document-swap"))

            for action in switchAction, mergeAction, rebaseAction:
                action.setEnabled(False)

            if branch and not branch.is_checked_out():
                switchAction.triggered.connect(lambda: self.switchToBranch.emit(data.name))
                switchAction.setEnabled(True)

                if activeBranchName:
                    mergeAction.triggered.connect(lambda: self.mergeBranchIntoActive.emit(data.name))
                    rebaseAction.triggered.connect(lambda: self.rebaseActiveOntoBranch.emit(data.name))

                    mergeAction.setEnabled(True)
                    rebaseAction.setEnabled(True)

            menu.addSeparator()

            if data.trackingBranch:
                a = menu.addAction(F"&Push to {labelQuote(data.trackingBranch)}...", lambda: self.pushBranch.emit(data.name))
                a.setIcon(QIcon.fromTheme("vcs-push"))
            else:
                a = menu.addAction("&Push: no tracked branch")
                a.setEnabled(False)
                a.setIcon(QIcon.fromTheme("vcs-push"))

            menu.addAction("Set &Tracked Branch...", lambda: self._editTrackingBranchFlow(data.name))

            menu.addSeparator()

            menu.addAction("Re&name...", lambda: self._renameBranchFlow(data.name))
            a = menu.addAction("&Delete...", lambda: self._deleteBranchFlow(data.name))
            a.setIcon(QIcon.fromTheme("vcs-branch-delete"))

            """
            menu.addSeparator()
            a = menu.addAction(F"Show In Graph")
            a.setCheckable(True)
            a.setChecked(True)
            """

        elif data.type == SidebarEntry.Type.REMOTE_REF:
            shortRef = data.name.removeprefix("refs/remotes/")
            menu.addAction(F"New local branch tracking {labelQuote(shortRef)}...",
                           lambda: self._newTrackingBranchFlow(data.name))

        elif data.type == SidebarEntry.Type.REMOTE:
            a: QAction = menu.addAction(F"Edit remote...", lambda: self._editRemoteFlow(data.name))
            a.setIcon(QIcon.fromTheme("document-edit"))

        menu.exec_(globalPoint)

    def _newBranchFlow(self):
        def onAccept(newBranchName):
            self.newBranch.emit(newBranchName)
        showTextInputDialog(
            self,
            "New branch",
            "Enter name for new branch:",
            None,
            onAccept)

    def _editTrackingBranchFlow(self, localBranchName):
        dlg = TrackedBranchDialog(self.repo, localBranchName, self)

        def onAccept():
            newTrackingBranchName = dlg.newTrackingBranchName
            self.editTrackingBranch.emit(localBranchName, newTrackingBranchName)

        dlg.accepted.connect(onAccept)
        dlg.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
        dlg.show()

    def _renameBranchFlow(self, oldName):
        def onAccept(newName):
            self.renameBranch.emit(oldName, newName)

        strippedName = oldName.removeprefix('refs/heads/')

        showTextInputDialog(
            self,
            F"Rename branch {labelQuote(strippedName)}",
            "Enter new name:",
            strippedName,
            onAccept,
            okButtonText="Rename")

    def _deleteBranchFlow(self, localBranchName):
        rc = QMessageBox.warning(self, "Delete Branch",
                                 F"Really delete local branch <b>{labelQuote(localBranchName)}</b>?"
                                 F"<br>This cannot be undone!",
                                 QMessageBox.Discard | QMessageBox.Cancel)
        if rc == QMessageBox.Discard:
            self.deleteBranch.emit(localBranchName)

    def _newTrackingBranchFlow(self, name):
        def onAccept(localBranchName):
            self.newTrackingBranch.emit(localBranchName, name)

        strippedName = name.removeprefix("refs/remotes/")

        showTextInputDialog(
            self,
            f"New branch tracking {labelQuote(strippedName)}",
            F"Enter name for a new local branch that will\ntrack remote branch {labelQuote(strippedName)}:",
            name[name.rfind('/') + 1:],
            onAccept,
            okButtonText="Create")

    def _editRemoteFlow(self, remoteName) -> RemoteDialog:
        def onAccept(newName, newURL):
            self.editRemote.emit(remoteName, newName, newURL)

        dlg = RemoteDialog(remoteName, self.repo.remotes[remoteName].url, self)
        dlg.accepted.connect(lambda: onAccept(dlg.ui.nameEdit.text(), dlg.ui.urlEdit.text()))
        dlg.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
        dlg.show()
        return dlg

    def fill(self, repo: pygit2.Repository):
        model = QStandardItemModel()

        uncommittedChangesEntry = SidebarEntry(SidebarEntry.Type.UNCOMMITTED_CHANGES)
        uncommittedChanges = SidebarItem("Changes", uncommittedChangesEntry)
        model.appendRow(uncommittedChanges)

        model.appendRow(SidebarSeparator())

        branchesParentEntry = SidebarEntry(SidebarEntry.Type.LOCAL_BRANCHES_HEADER)
        branchesParent = SidebarItem("Local Branches", branchesParentEntry)
        branchesParent.setSelectable(False)

        if repo.head_is_unborn:
            target: str = repo.lookup_reference("HEAD").target
            target = target.removeprefix("refs/heads/")
            caption = F"★ {target} (unborn)"
            branchEntry = SidebarEntry(SidebarEntry.Type.UNBORN_HEAD)
            item = SidebarItem(caption, branchEntry)
            item.setToolTip(F"Unborn HEAD (does not point to a commit yet)")
            branchesParent.appendRow(item)

        elif repo.head_is_detached:
            caption = F"★ detached HEAD @ {shortHash(repo.head.target)}"
            branchEntry = SidebarEntry(SidebarEntry.Type.DETACHED_HEAD, oid=repo.head.target)
            item = SidebarItem(caption, branchEntry)
            item.setToolTip(F"detached HEAD @{shortHash(repo.head.target)}")
            branchesParent.appendRow(item)

        for localBranchRawName in repo.raw_listall_branches(pygit2.GIT_BRANCH_LOCAL):
            branch: pygit2.Branch = repo.lookup_branch(localBranchRawName)
            caption = branch.branch_name
            tooltip = branch.branch_name
            if not repo.head_is_detached and branch.is_checked_out():
                caption = F"★ {caption}"
                tooltip += " (★ active branch)"
            branchEntry = SidebarEntry(SidebarEntry.Type.LOCAL_REF, branch.name)
            if branch.upstream:
                branchEntry.trackingBranch = branch.upstream.branch_name
                tooltip += F"\ntracking {branchEntry.trackingBranch}"
            item = SidebarItem(caption, branchEntry)
            item.setToolTip(tooltip)
            branchesParent.appendRow(item)

        model.appendRow(branchesParent)

        model.appendRow(SidebarSeparator())

        allRefs = repo.listall_references()

        remote: pygit2.Remote
        for remote in repo.remotes:
            remoteEntry = SidebarEntry(SidebarEntry.Type.REMOTE, remote.name)
            remoteParent = SidebarItem(F"Remote “{remote.name}”", remoteEntry)
            remoteParent.setSelectable(False)

            remotePrefix = F"refs/remotes/{remote.name}/"
            remoteRefNames = (refName for refName in allRefs if refName.startswith(remotePrefix))

            for remoteRefLongName in remoteRefNames:
                print(remoteRefLongName)
                remoteRefShortName = remoteRefLongName[len(remotePrefix):]
                remoteRefEntry = SidebarEntry(SidebarEntry.Type.REMOTE_REF, remoteRefLongName)
                remoteRefItem = SidebarItem(remoteRefShortName, remoteRefEntry)
                remoteParent.appendRow(remoteRefItem)

            model.appendRow(remoteParent)
            model.appendRow(SidebarSeparator())

        tagsParent = QStandardItem("Tags")
        tagsParent.setSelectable(False)
        for tagLongName in (refName for refName in allRefs if refName.startswith("refs/tags/")):
            tagShortName = tagLongName[len("refs/tags/"):]
            tagEntry = SidebarEntry(SidebarEntry.Type.TAG, tagShortName)
            tagItem = SidebarItem(tagShortName, tagEntry)
            tagsParent.appendRow(tagItem)
        model.appendRow(tagsParent)

        self.repo = repo
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
        elif data.type == SidebarEntry.Type.DETACHED_HEAD:
            self.commitClicked.emit(data.oid)
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

