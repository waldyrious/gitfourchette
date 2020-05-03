from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

import git

import MainWindow
import globals


class TreeView(QListView):
    rowstuff = []

    def __init__(self, parent: MainWindow.MainWindow):
        super(__class__, self).__init__(parent)
        self.uindo = parent
        self.setModel(QStandardItemModel())
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setIconSize(QSize(16, 16))
        self.setEditTriggers(QAbstractItemView.NoEditTriggers) # prevent editing text after double-clicking

    def clear(self):
        with self.uindo.unready():
            self.model().clear()
            self.rowstuff = []

    def fillDiff(self, diff: git.DiffIndex):
        model: QStandardItemModel = self.model()
        for f in diff:
            self.rowstuff.append(f)
            item = QStandardItem(f.a_path)
            item.setIcon(globals.statusIcons[f.change_type])
            model.appendRow(item)

    def fillUntracked(self, untracked_files):
        model: QStandardItemModel = self.model()
        for f in untracked_files:
            self.rowstuff.append(f)
            item = QStandardItem(f + " (untracked)")
            item.setIcon(globals.statusIcons['A'])
            model.appendRow(item)

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        super().selectionChanged(selected, deselected)

        if not self.uindo.isReady(): return

        current = selected.indexes()[0]

        if not current.isValid():
            self.uindo.diffView.clear()
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            change = self.rowstuff[current.row()]
            self.uindo.diffView.setDiffContents(self.uindo.state.repo, change)
        except BaseException as ex:
            import traceback
            traceback.print_exc()
            self.uindo.diffView.setFailureContents(F"Error displaying diff: {repr(ex)}")
        QApplication.restoreOverrideCursor()


class UnstagedView(TreeView):
    def __init__(self, parent: MainWindow.MainWindow):
        super(__class__, self).__init__(parent)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

        stageAction = QAction("Stage", self)
        stageAction.triggered.connect(self.stage)
        self.addAction(stageAction)

        restoreAction = QAction("Discard changes", self)
        restoreAction.triggered.connect(self.restore)
        self.addAction(restoreAction)

    def stage(self):
        git = self.uindo.state.repo.git
        for si in self.selectedIndexes():
            change = self.rowstuff[si.row()]
            print(F"Staging: {change.a_path}")
            git.add(change.a_path)
            #self.uindo.state.index.add(change.a_path) # <- also works at first... but might add too many things after repeated staging/unstaging??
        self.uindo.fillStageView()

    def restore(self):
        qmb = QMessageBox(
            QMessageBox.Question,
            "Discard changes",
            MainWindow.fplural(F"Really discard changes to # file^s?\nThis cannot be undone!", len(self.selectedIndexes())),
            QMessageBox.Yes | QMessageBox.Cancel)
        yes = qmb.button(QMessageBox.Yes)
        yes.setText("Discard changes")
        qmb.exec_()
        if qmb.clickedButton() != yes:
            return
        git = self.uindo.state.repo.git
        for si in self.selectedIndexes():
            change = self.rowstuff[si.row()]
            print(F"Discarding: {change.a_path}")
            git.restore(change.a_path)


class StagedView(TreeView):
    def __init__(self, parent: MainWindow.MainWindow):
        super(__class__, self).__init__(parent)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

        action = QAction("UnStage", self)
        action.triggered.connect(self.unstage)
        self.addAction(action)

    def unstage(self):
        git = self.uindo.state.repo.git
        for si in self.selectedIndexes():
            change = self.rowstuff[si.row()]
            print(F"UnStaging: {change.a_path}")
            git.restore(change.a_path, staged=True)
        self.uindo.fillStageView()
