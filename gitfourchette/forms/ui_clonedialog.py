# Form implementation generated from reading ui file 'clonedialog.ui'
#
# Created by: PyQt6 UI code generator 6.7.0
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from gitfourchette.qt import *


class Ui_CloneDialog(object):
    def setupUi(self, CloneDialog):
        CloneDialog.setObjectName("CloneDialog")
        CloneDialog.setWindowModality(Qt.WindowModality.NonModal)
        CloneDialog.setEnabled(True)
        CloneDialog.resize(635, 225)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(CloneDialog.sizePolicy().hasHeightForWidth())
        CloneDialog.setSizePolicy(sizePolicy)
        CloneDialog.setSizeGripEnabled(False)
        CloneDialog.setModal(True)
        self.formLayout = QFormLayout(CloneDialog)
        self.formLayout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.formLayout.setObjectName("formLayout")
        self.urlLabel = QLabel(parent=CloneDialog)
        self.urlLabel.setObjectName("urlLabel")
        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.urlLabel)
        self.urlEdit = QComboBox(parent=CloneDialog)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.urlEdit.sizePolicy().hasHeightForWidth())
        self.urlEdit.setSizePolicy(sizePolicy)
        self.urlEdit.setEditable(True)
        self.urlEdit.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.urlEdit.setObjectName("urlEdit")
        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.urlEdit)
        self.pathLabel = QLabel(parent=CloneDialog)
        self.pathLabel.setObjectName("pathLabel")
        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.pathLabel)
        self.pathLayout = QHBoxLayout()
        self.pathLayout.setObjectName("pathLayout")
        self.pathEdit = QLineEdit(parent=CloneDialog)
        self.pathEdit.setObjectName("pathEdit")
        self.pathLayout.addWidget(self.pathEdit)
        self.browseButton = QPushButton(parent=CloneDialog)
        self.browseButton.setObjectName("browseButton")
        self.pathLayout.addWidget(self.browseButton)
        self.formLayout.setLayout(1, QFormLayout.ItemRole.FieldRole, self.pathLayout)
        self.optionsLabel = QLabel(parent=CloneDialog)
        self.optionsLabel.setObjectName("optionsLabel")
        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.optionsLabel)
        self.shallowCloneLayout = QHBoxLayout()
        self.shallowCloneLayout.setObjectName("shallowCloneLayout")
        self.shallowCloneCheckBox = QCheckBox(parent=CloneDialog)
        self.shallowCloneCheckBox.setText("(SHALLOW CLONE)")
        self.shallowCloneCheckBox.setObjectName("shallowCloneCheckBox")
        self.shallowCloneLayout.addWidget(self.shallowCloneCheckBox)
        self.shallowCloneDepthSpinBox = QSpinBox(parent=CloneDialog)
        self.shallowCloneDepthSpinBox.setProperty("showGroupSeparator", True)
        self.shallowCloneDepthSpinBox.setPrefix("")
        self.shallowCloneDepthSpinBox.setMinimum(1)
        self.shallowCloneDepthSpinBox.setMaximum(999999)
        self.shallowCloneDepthSpinBox.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        self.shallowCloneDepthSpinBox.setObjectName("shallowCloneDepthSpinBox")
        self.shallowCloneLayout.addWidget(self.shallowCloneDepthSpinBox)
        self.shallowCloneSuffix = QLabel(parent=CloneDialog)
        self.shallowCloneSuffix.setText("(SUFFIX)")
        self.shallowCloneSuffix.setObjectName("shallowCloneSuffix")
        self.shallowCloneLayout.addWidget(self.shallowCloneSuffix)
        self.formLayout.setLayout(2, QFormLayout.ItemRole.FieldRole, self.shallowCloneLayout)
        self.keyFileLayout = QGridLayout()
        self.keyFileLayout.setObjectName("keyFileLayout")
        self.keyFileCheckBox = QCheckBox(parent=CloneDialog)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.keyFileCheckBox.sizePolicy().hasHeightForWidth())
        self.keyFileCheckBox.setSizePolicy(sizePolicy)
        self.keyFileCheckBox.setObjectName("keyFileCheckBox")
        self.keyFileLayout.addWidget(self.keyFileCheckBox, 0, 0, 1, 2)
        self.keyFileBrowseButton = QToolButton(parent=CloneDialog)
        self.keyFileBrowseButton.setMaximumSize(QSize(16777215, 20))
        self.keyFileBrowseButton.setObjectName("keyFileBrowseButton")
        self.keyFileLayout.addWidget(self.keyFileBrowseButton, 1, 0, 1, 1)
        self.keyFilePath = QLabel(parent=CloneDialog)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.keyFilePath.sizePolicy().hasHeightForWidth())
        self.keyFilePath.setSizePolicy(sizePolicy)
        self.keyFilePath.setText("(KEY FILE PATH)")
        self.keyFilePath.setObjectName("keyFilePath")
        self.keyFileLayout.addWidget(self.keyFilePath, 1, 1, 1, 1)
        self.formLayout.setLayout(3, QFormLayout.ItemRole.FieldRole, self.keyFileLayout)
        self.statusLabel = QLabel(parent=CloneDialog)
        self.statusLabel.setObjectName("statusLabel")
        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.statusLabel)
        self.statusGroupBox = QGroupBox(parent=CloneDialog)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.statusGroupBox.sizePolicy().hasHeightForWidth())
        self.statusGroupBox.setSizePolicy(sizePolicy)
        self.statusGroupBox.setTitle("")
        self.statusGroupBox.setObjectName("statusGroupBox")
        self.verticalLayout = QVBoxLayout(self.statusGroupBox)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.statusForm = StatusForm(parent=self.statusGroupBox)
        self.statusForm.setObjectName("statusForm")
        self.verticalLayout.addWidget(self.statusForm)
        self.formLayout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.statusGroupBox)
        self.buttonBox = QDialogButtonBox(parent=CloneDialog)
        self.buttonBox.setOrientation(Qt.Orientation.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Ok)
        self.buttonBox.setCenterButtons(False)
        self.buttonBox.setObjectName("buttonBox")
        self.formLayout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.buttonBox)
        self.urlLabel.setBuddy(self.urlEdit)
        self.pathLabel.setBuddy(self.pathEdit)
        self.optionsLabel.setBuddy(self.shallowCloneCheckBox)
        self.shallowCloneSuffix.setBuddy(self.shallowCloneDepthSpinBox)

        self.retranslateUi(CloneDialog)
        self.buttonBox.rejected.connect(CloneDialog.reject) # type: ignore
        QMetaObject.connectSlotsByName(CloneDialog)
        CloneDialog.setTabOrder(self.urlEdit, self.pathEdit)
        CloneDialog.setTabOrder(self.pathEdit, self.browseButton)

    def retranslateUi(self, CloneDialog):
        _translate = QCoreApplication.translate
        CloneDialog.setWindowTitle(_translate("CloneDialog", "Clone repository"))
        self.urlLabel.setText(_translate("CloneDialog", "Remote &URL:"))
        self.pathLabel.setText(_translate("CloneDialog", "Clone in&to:"))
        self.browseButton.setText(_translate("CloneDialog", "&Browse..."))
        self.optionsLabel.setText(_translate("CloneDialog", "Options:"))
        self.shallowCloneCheckBox.setToolTip(_translate("CloneDialog", "<p>Tick this to download just the latest commits, not the entire history of the repository."))
        self.keyFileCheckBox.setText(_translate("CloneDialog", "Log in with custom &key file"))
        self.keyFileBrowseButton.setText(_translate("CloneDialog", "Select..."))
        self.statusLabel.setText(_translate("CloneDialog", "Status:"))
from gitfourchette.forms.statusform import StatusForm
