from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.util import labelQuote, shortHash, stockIcon
from html import escape
from typing import Any
import enum
import pygit2


ROLE_USERDATA = Qt.UserRole + 0
ROLE_EITEM = Qt.UserRole + 1
ACTIVE_BULLET = "★ "


class EItem(enum.Enum):
    UncommittedChanges = enum.auto()
    LocalBranchesHeader = enum.auto()
    StashesHeader = enum.auto()
    RemotesHeader = enum.auto()
    TagsHeader = enum.auto()
    SubmodulesHeader = enum.auto()
    LocalBranch = enum.auto()
    DetachedHead = enum.auto()
    UnbornHead = enum.auto()
    Stash = enum.auto()
    Remote = enum.auto()
    RemoteBranch = enum.auto()
    Tag = enum.auto()
    Submodule = enum.auto()
    Spacer = enum.auto()


ITEM_NAMES = {
    EItem.UncommittedChanges: "Changes",
    EItem.LocalBranchesHeader: "Branches",
    EItem.StashesHeader: "Stashes",
    EItem.RemotesHeader: "Remotes",
    EItem.TagsHeader: "Tags",
    EItem.SubmodulesHeader: "Submodules",
    EItem.LocalBranch: "Local branch",
    EItem.DetachedHead: "Detached HEAD",
    EItem.UnbornHead: "Unborn HEAD",
    EItem.RemoteBranch: "Remote branch",
    EItem.Stash: "Stash",
    EItem.Remote: "Remote",
    EItem.Tag: "Tag",
    EItem.Submodule: "Submodules",
    EItem.Spacer: "---",
}

HEADER_ITEMS = [
    EItem.UncommittedChanges,
    EItem.Spacer,
    EItem.StashesHeader,
    EItem.Spacer,
    EItem.LocalBranchesHeader,
    EItem.Spacer,
    EItem.RemotesHeader,
    EItem.Spacer,
    EItem.TagsHeader,
    EItem.Spacer,
    EItem.SubmodulesHeader,
]

LEAF_ITEMS = [
    EItem.Spacer,
    EItem.LocalBranch,
    EItem.Stash,
    EItem.RemoteBranch,
    EItem.Tag,
    EItem.UnbornHead,
    EItem.DetachedHead,
    EItem.UncommittedChanges,
    EItem.Submodule,
]

UNINDENT_ITEMS = [
    EItem.LocalBranch,
    EItem.UnbornHead,
    EItem.DetachedHead,
    EItem.Stash,
    EItem.Tag,
    EItem.Submodule,
]


class SidebarModel(QAbstractItemModel):
    repo: pygit2.Repository | None
    _localBranches: list[str]
    _tracking: list[str]
    _unbornHead: str
    _detachedHead: str
    _checkedOut: str
    _stashes: list[pygit2.Stash]
    _remotes: list[str]
    _remoteURLs: list[str]
    _remoteBranchesDict: dict[str, list[str]]
    _tags: list[str]
    _submodules: list[str]

    @staticmethod
    def packId(eid: EItem, offset: int = 0) -> int:
        return eid.value | (offset << 8)

    @staticmethod
    def unpackItem(index: QModelIndex) -> EItem:
        return EItem(index.internalId() & 0xFF)

    @staticmethod
    def unpackOffset(index: QModelIndex) -> int:
        return index.internalId() >> 8

    @staticmethod
    def unpackItemAndData(index: QModelIndex):
        return SidebarModel.unpackItem(index), index.data(Qt.UserRole)

    @property
    def _parentWidget(self) -> QWidget:
        return QObject.parent(self)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.repo = None

    def refreshCache(self, repo: pygit2.Repository):
        self.beginResetModel()

        self.repo = repo

        self._localBranches = [b for b in repo.branches.local]

        self._tracking = []
        for branchName in self._localBranches:
            upstream = self.repo.branches.local[branchName].upstream
            if not upstream:
                self._tracking.append("")
            else:
                self._tracking.append(upstream.shorthand)

        self._unbornHead = ""
        self._detachedHead = ""
        self._checkedOut = ""
        if repo.head_is_unborn:
            target: str = repo.lookup_reference("HEAD").target
            target = target.removeprefix("refs/heads/")
            self._unbornHead = target
        elif repo.head_is_detached:
            self._detachedHead = repo.head.target.hex
        else:
            self._checkedOut = repo.head.shorthand

        self._stashes = repo.listall_stashes()

        self._remotes = [r.name for r in repo.remotes]
        self._remoteURLs = [repo.remotes[r].url for r in self._remotes]
        self._remoteBranchesDict = porcelain.getRemoteBranchNames(repo)

        self._tags = sorted(porcelain.getTagNames(repo))

        self._submodules = repo.listall_submodules()

        self.endResetModel()

    def columnCount(self, parent: QModelIndex) -> int:
        return 1

    def index(self, row, column, parent: QModelIndex = None) -> QModelIndex:
        if not self.repo or column != 0 or row < 0:
            return QModelIndex()

        if not parent or not parent.isValid():  # root
            return self.createIndex(row, 0, HEADER_ITEMS[row].value)

        item = self.unpackItem(parent)

        if item == EItem.LocalBranchesHeader:
            y = 0

            if self._unbornHead:
                if y == row:
                    return self.createIndex(row, 0, self.packId(EItem.UnbornHead))
                y += 1

            if self._detachedHead:
                if y == row:
                    return self.createIndex(row, 0, self.packId(EItem.DetachedHead))
                y += 1

            return self.createIndex(row, 0, self.packId(EItem.LocalBranch, row - y))

        elif item == EItem.RemotesHeader:
            return self.createIndex(row, 0, self.packId(EItem.Remote))

        elif item == EItem.Remote:
            return self.createIndex(row, 0, self.packId(EItem.RemoteBranch, parent.row()))

        elif item == EItem.TagsHeader:
            return self.createIndex(row, 0, self.packId(EItem.Tag))

        elif item == EItem.StashesHeader:
            return self.createIndex(row, 0, self.packId(EItem.Stash))

        elif item == EItem.SubmodulesHeader:
            return self.createIndex(row, 0, self.packId(EItem.Submodule))

        return QModelIndex()

    def parent(self, index: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.repo or not index.isValid():
            return QModelIndex()

        item = self.unpackItem(index)

        def makeParentIndex(parentHeader: EItem):
            return self.createIndex(HEADER_ITEMS.index(parentHeader), 0, self.packId(parentHeader))

        if item in HEADER_ITEMS:
            # it's a root node -- return invalid index because no parent
            return QModelIndex()

        elif item in [EItem.LocalBranch, EItem.DetachedHead, EItem.UnbornHead]:
            return makeParentIndex(EItem.LocalBranchesHeader)

        elif item == EItem.Remote:
            return makeParentIndex(EItem.RemotesHeader)

        elif item == EItem.RemoteBranch:
            remoteNo = self.unpackOffset(index)
            return self.createIndex(remoteNo, 0, self.packId(EItem.Remote))

        elif item == EItem.Tag:
            return makeParentIndex(EItem.TagsHeader)

        elif item == EItem.Stash:
            return makeParentIndex(EItem.StashesHeader)

        elif item == EItem.Submodule:
            return makeParentIndex(EItem.SubmodulesHeader)

        else:
            return QModelIndex()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not self.repo:
            return 0

        if not parent.isValid():
            return len(HEADER_ITEMS)

        item = self.unpackItem(parent)

        if item == EItem.LocalBranchesHeader:
            n = len(self._localBranches)
            if self._unbornHead:
                n += 1
            if self._detachedHead:
                n += 1
            return n

        elif item == EItem.RemotesHeader:
            return len(self._remotes)

        elif item == EItem.Remote:
            remoteName = self._remotes[parent.row()]
            return len(self._remoteBranchesDict[remoteName])

        elif item == EItem.TagsHeader:
            return len(self._tags)

        elif item == EItem.StashesHeader:
            return len(self._stashes)

        elif item == EItem.SubmodulesHeader:
            return len(self._submodules)

        else:
            return 0

    def data(self, index: QModelIndex, role: Qt.ItemDataRole = Qt.DisplayRole) -> Any:
        if not self.repo:
            return None

        row = index.row()
        item = self.unpackItem(index)

        if role == ROLE_EITEM:  # for testing (match by EItem type)
            return item

        display = role == Qt.DisplayRole
        user = role == ROLE_USERDATA
        tooltip = role == Qt.ToolTipRole
        sizeHint = role == Qt.SizeHintRole

        if item == EItem.Spacer:
            if sizeHint:
                parentWidget: QWidget = QObject.parent(self)
                return QSize(-1, int(0.5 * parentWidget.fontMetrics().height()))
            else:
                return None

        elif item == EItem.LocalBranch:
            branchNo = self.unpackOffset(index)
            branchName = self._localBranches[branchNo]
            if display:
                if branchName == self._checkedOut:
                    return F"{ACTIVE_BULLET}{branchName}"
                else:
                    return branchName
            elif user:
                return branchName
            elif tooltip:
                text = F"Local branch “{branchName}”"
                if branchName == self._checkedOut:
                    text += F"\n{ACTIVE_BULLET}Active branch"
                if self._tracking[branchNo]:
                    text += F"\nTracking remote “{self._tracking[branchNo]}”"
                return text

        elif item == EItem.UnbornHead:
            if display:
                return F"{ACTIVE_BULLET}{self._unbornHead} [unborn]"
            elif user:
                return self._unbornHead
            elif tooltip:
                return "Unborn HEAD: does not point to a commit yet."

        elif item == EItem.DetachedHead:
            if display:
                return F"{ACTIVE_BULLET}[detached head]"
            elif user:
                return self._detachedHead
            elif tooltip:
                return F"Detached HEAD @ {self._detachedHead}"

        elif item == EItem.Remote:
            if display or user:
                return self._remotes[row]
            elif tooltip:
                return self._remoteURLs[row]

        elif item == EItem.RemoteBranch:
            remoteNo = self.unpackOffset(index)
            remoteName = self._remotes[remoteNo]
            branchName = self._remoteBranchesDict[remoteName][row]
            if display:
                return branchName
            elif user:
                return F"{remoteName}/{branchName}"
            elif tooltip:
                return F"{remoteName}/{branchName}"

        elif item == EItem.Tag:
            if display or user:
                return self._tags[row]

        elif item == EItem.Stash:
            stash = self._stashes[row]
            if display:
                return stash.message
            elif tooltip:
                return F"<b>stash@{{{row}}}</b>:<br/>{escape(stash.message)}"
            elif user:
                return stash.commit_id.hex

        elif item == EItem.Submodule:
            if display:
                return self._submodules[row].rsplit("/", 1)[-1]
            elif tooltip:
                return self._submodules[row]
            elif user:
                return self._submodules[row]

        else:
            if display:
                return ITEM_NAMES[item]
            elif role == Qt.FontRole:
                font = self._parentWidget.font()
                font.setBold(True)
                return font

        # fallback
        if sizeHint:
            return QSize(-1, self._parentWidget.fontMetrics().height())

        return None

    def flags(self, index: QModelIndex) -> int:
        item = self.unpackItem(index)

        if item == EItem.Spacer:
            return Qt.NoItemFlags

        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


class SidebarDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget):
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        view: QTreeView = option.widget
        item = SidebarModel.unpackItem(index)

        opt = QStyleOptionViewItem(option)

        if item in UNINDENT_ITEMS:
            opt.rect.adjust(-view.indentation(), 0, 0, 0)

        # Draw custom branch indicator. The standard one is too cluttered in some themes, e.g. Breeze.
        if item not in LEAF_ITEMS:
            opt2 = QStyleOptionViewItem(option)

            r: QRect = opt2.rect
            r.adjust(-view.indentation(), 0, 0, 0)
            r.setWidth(view.indentation())

            # See QTreeView::drawBranches() in qtreeview.cpp for other interesting states
            opt2.state &= ~QStyle.State_MouseOver

            style: QStyle = view.style()
            arrowPrimitive = QStyle.PE_IndicatorArrowDown if view.isExpanded(index) else QStyle.PE_IndicatorArrowRight
            style.drawPrimitive(arrowPrimitive, opt2, painter, view)

        super().paint(painter, opt, index)


class Sidebar(QTreeView):
    uncommittedChangesClicked = Signal()
    refClicked = Signal(str)
    commitClicked = Signal(pygit2.Oid)
    commit = Signal()

    newBranch = Signal()
    renameBranch = Signal(str)
    deleteBranch = Signal(str)
    switchToBranch = Signal(str)
    mergeBranchIntoActive = Signal(str)
    rebaseActiveOntoBranch = Signal(str)
    pushBranch = Signal(str)
    newTrackingBranch = Signal(str)
    fetchRemoteBranch = Signal(str)
    editTrackingBranch = Signal(str)

    newRemote = Signal()
    fetchRemote = Signal(str)
    editRemote = Signal(str)
    deleteRemote = Signal(str)

    newStash = Signal()
    popStash = Signal(pygit2.Oid)
    applyStash = Signal(pygit2.Oid)
    dropStash = Signal(pygit2.Oid)

    openSubmoduleRepo = Signal(str)
    openSubmoduleFolder = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)

        self.setObjectName("sidebar")  # for styling
        self.setMinimumWidth(128)
        self.setIndentation(16)
        self.setHeaderHidden(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.customContextMenuRequested.connect(self.onCustomContextMenuRequested)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

        self.setItemDelegate(SidebarDelegate(self))

        self.setModel(SidebarModel(self))

    def generateMenuForEntry(self, item: EItem, data: str = "", menu: QMenu = None):
        if menu is None:
            menu = QMenu(self)
            menu.setObjectName("SidebarContextMenu")

        if item == EItem.LocalBranchesHeader:
            menu.addAction(F"&New Branch...", lambda: self.newBranch.emit())

        elif item == EItem.LocalBranch:
            model: SidebarModel = self.model()
            repo = model.repo
            branch = repo.branches.local[data]
            activeBranchName = porcelain.getActiveBranchShorthand(repo)

            switchAction: QAction = menu.addAction(F"&Switch to {labelQuote(data)}")
            menu.addSeparator()
            mergeAction: QAction = menu.addAction(F"&Merge {labelQuote(data)} into {labelQuote(activeBranchName)}...")
            rebaseAction: QAction = menu.addAction(F"&Rebase {labelQuote(activeBranchName)} onto {labelQuote(data)}...")

            switchAction.setIcon(QIcon.fromTheme("document-swap"))

            for action in switchAction, mergeAction, rebaseAction:
                action.setEnabled(False)

            if branch and not branch.is_checked_out():
                switchAction.triggered.connect(lambda: self.switchToBranch.emit(data))
                switchAction.setEnabled(True)

                if activeBranchName:
                    mergeAction.triggered.connect(lambda: self.mergeBranchIntoActive.emit(data))
                    rebaseAction.triggered.connect(lambda: self.rebaseActiveOntoBranch.emit(data))

                    mergeAction.setEnabled(True)
                    rebaseAction.setEnabled(True)

            menu.addSeparator()
            menu.addAction(stockIcon("vcs-push"), "&Push...", lambda: self.pushBranch.emit(data))
            menu.addAction("Set &Tracked Branch...", lambda: self.editTrackingBranch.emit(data))

            menu.addSeparator()
            menu.addAction("Re&name...", lambda: self.renameBranch.emit(data))
            a = menu.addAction("&Delete...", lambda: self.deleteBranch.emit(data))
            a.setIcon(QIcon.fromTheme("vcs-branch-delete"))

        elif item == EItem.RemoteBranch:
            menu.addAction(F"New local branch tracking {labelQuote(data)}...",
                           lambda: self.newTrackingBranch.emit(data))

            a = menu.addAction(F"Fetch this remote branch...", lambda: self.fetchRemoteBranch.emit(data))
            a.setIcon(self.parentWidget().style().standardIcon(QStyle.SP_BrowserReload))

        elif item == EItem.Remote:
            a = menu.addAction("&Edit Remote...", lambda: self.editRemote.emit(data))
            a.setIcon(QIcon.fromTheme("document-edit"))

            a = menu.addAction("&Fetch all branches on this remote...", lambda: self.fetchRemote.emit(data))
            a.setIcon(self.parentWidget().style().standardIcon(QStyle.SP_BrowserReload))

            menu.addSeparator()

            a = menu.addAction("&Delete Remote", lambda: self.deleteRemote.emit(data))
            a.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))

        elif item == EItem.RemotesHeader:
            menu.addAction("&New Remote...", lambda: self.newRemote.emit())

        elif item == EItem.StashesHeader:
            menu.addAction("&New stash", lambda: self.newStash.emit())

        elif item == EItem.Stash:
            oid = pygit2.Oid(hex=data)
            menu.addAction("&Pop (apply and delete)", lambda: self.popStash.emit(oid))
            menu.addAction("&Apply", lambda: self.applyStash.emit(oid))
            menu.addSeparator()
            menu.addAction(stockIcon(QStyle.SP_TrashIcon), "&Delete", lambda: self.dropStash.emit(oid))

        elif item == EItem.Submodule:
            menu.addAction(f"&Open submodule in {QApplication.applicationDisplayName()}", lambda: self.openSubmoduleRepo.emit(data))
            menu.addAction(f"Open submodule &folder", lambda: self.openSubmoduleFolder.emit(data))

        return menu

    def onCustomContextMenuRequested(self, localPoint: QPoint):
        globalPoint = self.mapToGlobal(localPoint)
        index: QModelIndex = self.indexAt(localPoint)
        if index.isValid():
            menu = self.generateMenuForEntry(*SidebarModel.unpackItemAndData(index))
            menu.exec_(globalPoint)

    def refresh(self, repo: pygit2.Repository):
        sidebarModel: SidebarModel = self.model()
        sidebarModel.refreshCache(repo)
        self.expandAll()

    def onEntryClicked(self, item: EItem, data: str):
        if item == EItem.UncommittedChanges:
            self.uncommittedChangesClicked.emit()
        elif item == EItem.UnbornHead:
            pass
        elif item == EItem.DetachedHead:
            self.refClicked.emit("HEAD")
        elif item == EItem.LocalBranch:
            self.refClicked.emit(F"refs/heads/{data}")
        elif item == EItem.RemoteBranch:
            self.refClicked.emit(F"refs/remotes/{data}")
        elif item == EItem.Tag:
            self.refClicked.emit(F"refs/tags/{data}")
        elif item == EItem.Stash:
            self.commitClicked.emit(pygit2.Oid(hex=data))
        else:
            pass

    def onEntryDoubleClicked(self, item: EItem, data: str):
        if item == EItem.LocalBranch:
            self.switchToBranch.emit(data)
        elif item == EItem.Remote:
            self.editRemote.emit(data)
        elif item == EItem.RemotesHeader:
            self.newRemote.emit()
        elif item == EItem.LocalBranchesHeader:
            self.newBranch.emit()
        elif item == EItem.UncommittedChanges:
            self.commit.emit()
        elif item == EItem.Submodule:
            self.openSubmoduleRepo.emit(data)

    def currentChanged(self, current: QModelIndex, previous: QModelIndex):
        super().currentChanged(current, previous)
        if current.isValid():
            self.onEntryClicked(*SidebarModel.unpackItemAndData(current))

    def mouseDoubleClickEvent(self, event):
        # NOT calling "super().mouseDoubleClickEvent(event)" on purpose.
        index: QModelIndex = self.indexAt(event.pos())
        if event.button() == Qt.LeftButton and index.isValid():
            self.onEntryDoubleClicked(*SidebarModel.unpackItemAndData(index))
