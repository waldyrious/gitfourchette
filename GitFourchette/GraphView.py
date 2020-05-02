from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import git

import GraphDelegate
import MainWindow


class GraphView(QListView):
    def __init__(self, parent:MainWindow.MainWindow=None):
        super(__class__, self).__init__(parent)
        self.uindo = parent
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        #self.setModel(QStandardItemModel())
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)  # sinon on peut double-cliquer pour éditer les lignes...
        self.setItemDelegate(GraphDelegate.GraphDelegate())

    def fill(self, progress: QProgressDialog):
        repo = self.uindo.state.repo

        #model: QAbstractItemModel = self.model() ; model.clear()
        # Recreating a model on the fly is faster than clearing an existing one?
        model = QStandardItemModel()

        model.appendRow(QStandardItem("◆ Uncommitted Changes"))

        i = 0
        for commit in repo.iter_commits(repo.active_branch):#, max_count=999000):
            if i != 0 and i % 1000 == 0:
                progress.setLabelText(F"{i:,} commits loaded.")
                QCoreApplication.processEvents()
            if progress.wasCanceled():
                raise Exception("Canceled!")
            i += 1
            item = QStandardItem()
            item.setData(self.uindo.state.getOrCreateMetadata(commit), Qt.DisplayRole)
            model.appendRow(item)
        progress.setLabelText(F"{i:,} commits total.")
        #progress.setCancelButton(None)
        #progress.setWindowFlags(progress.windowFlags() & ~Qt.WindowCloseButtonHint)
        #progress.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint)
        QCoreApplication.processEvents()
        self.setModel(model)
        self.repaint()
        QCoreApplication.processEvents()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if not self.currentIndex().isValid():
            return
        commit: git.Commit = self.currentIndex().data().commit
        QMessageBox.about(None, F"Commit info {commit.hexsha[:7]}", F"""\
SHA: {commit.hexsha}
AUTHOR: {commit.author} <{commit.author.email}> {commit.authored_date}
COMMITTER: {commit.committer} <{commit.committer.email}> {commit.committed_date}

{commit.message}""")

    def currentChanged(self, current: QModelIndex, previous: QModelIndex):
        if not self.uindo.isReady(): return

        # do standard callback, such as scrolling the viewport if reaching the edges, etc.
        super(__class__, self).currentChanged(current, previous)

        if not current.isValid(): return

        if current.row() == 0:
            self.uindo.fillStageView()
            return

        commit: git.Commit = current.data().commit
        self.uindo.changedFilesView.clear()
        for parent in commit.parents:
            self.uindo.changedFilesView.fillDiff(parent.diff(commit))
        self.uindo.filesStack.setCurrentIndex(0)