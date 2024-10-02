# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'preferences.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (
    QCoreApplication,
    QDate,
    QDateTime,
    QLocale,
    QMetaObject,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTime,
    QUrl,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QFontDatabase,
    QGradient,
    QIcon,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPalette,
    QPixmap,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from anchor.widgets import ColorEdit, FontEdit


class Ui_PreferencesDialog(object):
    def setupUi(self, PreferencesDialog):
        if not PreferencesDialog.objectName():
            PreferencesDialog.setObjectName("PreferencesDialog")
        PreferencesDialog.resize(724, 451)
        self.verticalLayout = QVBoxLayout(PreferencesDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.tabWidget = QTabWidget(PreferencesDialog)
        self.tabWidget.setObjectName("tabWidget")
        self.generalTab = QWidget()
        self.generalTab.setObjectName("generalTab")
        self.verticalLayout_8 = QVBoxLayout(self.generalTab)
        self.verticalLayout_8.setObjectName("verticalLayout_8")
        self.scrollArea_3 = QScrollArea(self.generalTab)
        self.scrollArea_3.setObjectName("scrollArea_3")
        self.scrollArea_3.setWidgetResizable(True)
        self.scrollAreaWidgetContents_3 = QWidget()
        self.scrollAreaWidgetContents_3.setObjectName("scrollAreaWidgetContents_3")
        self.scrollAreaWidgetContents_3.setGeometry(QRect(0, 0, 682, 353))
        self.formLayout = QFormLayout(self.scrollAreaWidgetContents_3)
        self.formLayout.setObjectName("formLayout")
        self.autosaveLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.autosaveLabel.setObjectName("autosaveLabel")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.autosaveLabel)

        self.autosaveOnExitCheckBox = QCheckBox(self.scrollAreaWidgetContents_3)
        self.autosaveOnExitCheckBox.setObjectName("autosaveOnExitCheckBox")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.autosaveOnExitCheckBox)

        self.autoloadLastUsedCorpusLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.autoloadLastUsedCorpusLabel.setObjectName("autoloadLastUsedCorpusLabel")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.autoloadLastUsedCorpusLabel)

        self.autoloadLastUsedCorpusCheckBox = QCheckBox(self.scrollAreaWidgetContents_3)
        self.autoloadLastUsedCorpusCheckBox.setObjectName("autoloadLastUsedCorpusCheckBox")

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.autoloadLastUsedCorpusCheckBox)

        self.audioDeviceLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.audioDeviceLabel.setObjectName("audioDeviceLabel")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.audioDeviceLabel)

        self.audioDeviceEdit = QComboBox(self.scrollAreaWidgetContents_3)
        self.audioDeviceEdit.setObjectName("audioDeviceEdit")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.audioDeviceEdit)

        self.fadeInLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.fadeInLabel.setObjectName("fadeInLabel")

        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.fadeInLabel)

        self.enableFadeCheckBox = QCheckBox(self.scrollAreaWidgetContents_3)
        self.enableFadeCheckBox.setObjectName("enableFadeCheckBox")

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.enableFadeCheckBox)

        self.useCudaLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.useCudaLabel.setObjectName("useCudaLabel")

        self.formLayout.setWidget(5, QFormLayout.LabelRole, self.useCudaLabel)

        self.numJobsLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.numJobsLabel.setObjectName("numJobsLabel")

        self.formLayout.setWidget(7, QFormLayout.LabelRole, self.numJobsLabel)

        self.numJobsEdit = QSpinBox(self.scrollAreaWidgetContents_3)
        self.numJobsEdit.setObjectName("numJobsEdit")

        self.formLayout.setWidget(7, QFormLayout.FieldRole, self.numJobsEdit)

        self.githubTokenLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.githubTokenLabel.setObjectName("githubTokenLabel")

        self.formLayout.setWidget(9, QFormLayout.LabelRole, self.githubTokenLabel)

        self.githubTokenEdit = QLineEdit(self.scrollAreaWidgetContents_3)
        self.githubTokenEdit.setObjectName("githubTokenEdit")

        self.formLayout.setWidget(9, QFormLayout.FieldRole, self.githubTokenEdit)

        self.resultsPerPageLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.resultsPerPageLabel.setObjectName("resultsPerPageLabel")

        self.formLayout.setWidget(11, QFormLayout.LabelRole, self.resultsPerPageLabel)

        self.resultsPerPageEdit = QSpinBox(self.scrollAreaWidgetContents_3)
        self.resultsPerPageEdit.setObjectName("resultsPerPageEdit")
        self.resultsPerPageEdit.setMaximum(1000)

        self.formLayout.setWidget(11, QFormLayout.FieldRole, self.resultsPerPageEdit)

        self.timeDirectionLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.timeDirectionLabel.setObjectName("timeDirectionLabel")

        self.formLayout.setWidget(13, QFormLayout.LabelRole, self.timeDirectionLabel)

        self.timeDirectionComboBox = QComboBox(self.scrollAreaWidgetContents_3)
        self.timeDirectionComboBox.addItem("")
        self.timeDirectionComboBox.addItem("")
        self.timeDirectionComboBox.setObjectName("timeDirectionComboBox")

        self.formLayout.setWidget(13, QFormLayout.FieldRole, self.timeDirectionComboBox)

        self.visibleSpeakerLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.visibleSpeakerLabel.setObjectName("visibleSpeakerLabel")

        self.formLayout.setWidget(14, QFormLayout.LabelRole, self.visibleSpeakerLabel)

        self.visibleSpeakerComboBox = QComboBox(self.scrollAreaWidgetContents_3)
        self.visibleSpeakerComboBox.addItem("")
        self.visibleSpeakerComboBox.addItem("")
        self.visibleSpeakerComboBox.addItem("")
        self.visibleSpeakerComboBox.addItem("")
        self.visibleSpeakerComboBox.addItem("")
        self.visibleSpeakerComboBox.setObjectName("visibleSpeakerComboBox")

        self.formLayout.setWidget(14, QFormLayout.FieldRole, self.visibleSpeakerComboBox)

        self.cudaCheckBox = QCheckBox(self.scrollAreaWidgetContents_3)
        self.cudaCheckBox.setObjectName("cudaCheckBox")

        self.formLayout.setWidget(5, QFormLayout.FieldRole, self.cudaCheckBox)

        self.useMpCheckBox = QCheckBox(self.scrollAreaWidgetContents_3)
        self.useMpCheckBox.setObjectName("useMpCheckBox")

        self.formLayout.setWidget(6, QFormLayout.FieldRole, self.useMpCheckBox)

        self.useMpLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.useMpLabel.setObjectName("useMpLabel")

        self.formLayout.setWidget(6, QFormLayout.LabelRole, self.useMpLabel)

        self.hfTokenEdit = QLineEdit(self.scrollAreaWidgetContents_3)
        self.hfTokenEdit.setObjectName("hfTokenEdit")

        self.formLayout.setWidget(10, QFormLayout.FieldRole, self.hfTokenEdit)

        self.hfTokenLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.hfTokenLabel.setObjectName("hfTokenLabel")

        self.formLayout.setWidget(10, QFormLayout.LabelRole, self.hfTokenLabel)

        self.scrollArea_3.setWidget(self.scrollAreaWidgetContents_3)

        self.verticalLayout_8.addWidget(self.scrollArea_3)

        self.tabWidget.addTab(self.generalTab, "")
        self.appearenceTab = QWidget()
        self.appearenceTab.setObjectName("appearenceTab")
        self.verticalLayout_3 = QVBoxLayout(self.appearenceTab)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.widget = QWidget(self.appearenceTab)
        self.widget.setObjectName("widget")
        self.horizontalLayout_2 = QHBoxLayout(self.widget)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label_11 = QLabel(self.widget)
        self.label_11.setObjectName("label_11")

        self.horizontalLayout_2.addWidget(self.label_11)

        self.presetThemeEdit = QComboBox(self.widget)
        self.presetThemeEdit.addItem("")
        self.presetThemeEdit.addItem("")
        self.presetThemeEdit.addItem("")
        self.presetThemeEdit.setObjectName("presetThemeEdit")

        self.horizontalLayout_2.addWidget(self.presetThemeEdit)

        self.label_12 = QLabel(self.widget)
        self.label_12.setObjectName("label_12")

        self.horizontalLayout_2.addWidget(self.label_12)

        self.fontEdit = FontEdit(self.widget)
        self.fontEdit.setObjectName("fontEdit")

        self.horizontalLayout_2.addWidget(self.fontEdit)

        self.verticalLayout_3.addWidget(self.widget)

        self.scrollArea = QScrollArea(self.appearenceTab)
        self.scrollArea.setObjectName("scrollArea")
        self.scrollArea.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName("scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 682, 305))
        self.horizontalLayout = QHBoxLayout(self.scrollAreaWidgetContents)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.primaryHueBox = QGroupBox(self.scrollAreaWidgetContents)
        self.primaryHueBox.setObjectName("primaryHueBox")
        self.verticalLayout_6 = QVBoxLayout(self.primaryHueBox)
        self.verticalLayout_6.setObjectName("verticalLayout_6")
        self.formLayout_5 = QFormLayout()
        self.formLayout_5.setObjectName("formLayout_5")
        self.label_15 = QLabel(self.primaryHueBox)
        self.label_15.setObjectName("label_15")

        self.formLayout_5.setWidget(0, QFormLayout.LabelRole, self.label_15)

        self.primaryBaseEdit = ColorEdit(self.primaryHueBox)
        self.primaryBaseEdit.setObjectName("primaryBaseEdit")

        self.formLayout_5.setWidget(0, QFormLayout.FieldRole, self.primaryBaseEdit)

        self.label_16 = QLabel(self.primaryHueBox)
        self.label_16.setObjectName("label_16")

        self.formLayout_5.setWidget(1, QFormLayout.LabelRole, self.label_16)

        self.primaryLightEdit = ColorEdit(self.primaryHueBox)
        self.primaryLightEdit.setObjectName("primaryLightEdit")

        self.formLayout_5.setWidget(1, QFormLayout.FieldRole, self.primaryLightEdit)

        self.label_19 = QLabel(self.primaryHueBox)
        self.label_19.setObjectName("label_19")

        self.formLayout_5.setWidget(2, QFormLayout.LabelRole, self.label_19)

        self.primaryDarkEdit = ColorEdit(self.primaryHueBox)
        self.primaryDarkEdit.setObjectName("primaryDarkEdit")

        self.formLayout_5.setWidget(2, QFormLayout.FieldRole, self.primaryDarkEdit)

        self.label_28 = QLabel(self.primaryHueBox)
        self.label_28.setObjectName("label_28")

        self.formLayout_5.setWidget(3, QFormLayout.LabelRole, self.label_28)

        self.primaryVeryLightEdit = ColorEdit(self.primaryHueBox)
        self.primaryVeryLightEdit.setObjectName("primaryVeryLightEdit")

        self.formLayout_5.setWidget(3, QFormLayout.FieldRole, self.primaryVeryLightEdit)

        self.label_27 = QLabel(self.primaryHueBox)
        self.label_27.setObjectName("label_27")

        self.formLayout_5.setWidget(4, QFormLayout.LabelRole, self.label_27)

        self.primaryVeryDarkEdit = ColorEdit(self.primaryHueBox)
        self.primaryVeryDarkEdit.setObjectName("primaryVeryDarkEdit")

        self.formLayout_5.setWidget(4, QFormLayout.FieldRole, self.primaryVeryDarkEdit)

        self.verticalLayout_6.addLayout(self.formLayout_5)

        self.horizontalLayout.addWidget(self.primaryHueBox)

        self.accentHueBox = QGroupBox(self.scrollAreaWidgetContents)
        self.accentHueBox.setObjectName("accentHueBox")
        self.verticalLayout_5 = QVBoxLayout(self.accentHueBox)
        self.verticalLayout_5.setObjectName("verticalLayout_5")
        self.formLayout_4 = QFormLayout()
        self.formLayout_4.setObjectName("formLayout_4")
        self.label_20 = QLabel(self.accentHueBox)
        self.label_20.setObjectName("label_20")

        self.formLayout_4.setWidget(0, QFormLayout.LabelRole, self.label_20)

        self.accentBaseEdit = ColorEdit(self.accentHueBox)
        self.accentBaseEdit.setObjectName("accentBaseEdit")

        self.formLayout_4.setWidget(0, QFormLayout.FieldRole, self.accentBaseEdit)

        self.label_30 = QLabel(self.accentHueBox)
        self.label_30.setObjectName("label_30")

        self.formLayout_4.setWidget(1, QFormLayout.LabelRole, self.label_30)

        self.accentLightEdit = ColorEdit(self.accentHueBox)
        self.accentLightEdit.setObjectName("accentLightEdit")

        self.formLayout_4.setWidget(1, QFormLayout.FieldRole, self.accentLightEdit)

        self.label_21 = QLabel(self.accentHueBox)
        self.label_21.setObjectName("label_21")

        self.formLayout_4.setWidget(2, QFormLayout.LabelRole, self.label_21)

        self.accentDarkEdit = ColorEdit(self.accentHueBox)
        self.accentDarkEdit.setObjectName("accentDarkEdit")

        self.formLayout_4.setWidget(2, QFormLayout.FieldRole, self.accentDarkEdit)

        self.label_35 = QLabel(self.accentHueBox)
        self.label_35.setObjectName("label_35")

        self.formLayout_4.setWidget(3, QFormLayout.LabelRole, self.label_35)

        self.accentVeryLightEdit = ColorEdit(self.accentHueBox)
        self.accentVeryLightEdit.setObjectName("accentVeryLightEdit")

        self.formLayout_4.setWidget(3, QFormLayout.FieldRole, self.accentVeryLightEdit)

        self.label_29 = QLabel(self.accentHueBox)
        self.label_29.setObjectName("label_29")

        self.formLayout_4.setWidget(4, QFormLayout.LabelRole, self.label_29)

        self.accentVeryDarkEdit = ColorEdit(self.accentHueBox)
        self.accentVeryDarkEdit.setObjectName("accentVeryDarkEdit")

        self.formLayout_4.setWidget(4, QFormLayout.FieldRole, self.accentVeryDarkEdit)

        self.verticalLayout_5.addLayout(self.formLayout_4)

        self.horizontalLayout.addWidget(self.accentHueBox)

        self.otherBox = QGroupBox(self.scrollAreaWidgetContents)
        self.otherBox.setObjectName("otherBox")
        self.verticalLayout_4 = QVBoxLayout(self.otherBox)
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.formLayout_3 = QFormLayout()
        self.formLayout_3.setObjectName("formLayout_3")
        self.label_14 = QLabel(self.otherBox)
        self.label_14.setObjectName("label_14")

        self.formLayout_3.setWidget(0, QFormLayout.LabelRole, self.label_14)

        self.mainTextColorEdit = ColorEdit(self.otherBox)
        self.mainTextColorEdit.setObjectName("mainTextColorEdit")

        self.formLayout_3.setWidget(0, QFormLayout.FieldRole, self.mainTextColorEdit)

        self.label_17 = QLabel(self.otherBox)
        self.label_17.setObjectName("label_17")

        self.formLayout_3.setWidget(1, QFormLayout.LabelRole, self.label_17)

        self.selectedTextColorEdit = ColorEdit(self.otherBox)
        self.selectedTextColorEdit.setObjectName("selectedTextColorEdit")

        self.formLayout_3.setWidget(1, QFormLayout.FieldRole, self.selectedTextColorEdit)

        self.label_18 = QLabel(self.otherBox)
        self.label_18.setObjectName("label_18")

        self.formLayout_3.setWidget(2, QFormLayout.LabelRole, self.label_18)

        self.errorColorEdit = ColorEdit(self.otherBox)
        self.errorColorEdit.setObjectName("errorColorEdit")

        self.formLayout_3.setWidget(2, QFormLayout.FieldRole, self.errorColorEdit)

        self.label_13 = QLabel(self.otherBox)
        self.label_13.setObjectName("label_13")

        self.formLayout_3.setWidget(3, QFormLayout.LabelRole, self.label_13)

        self.plotTextWidth = QSpinBox(self.otherBox)
        self.plotTextWidth.setObjectName("plotTextWidth")
        self.plotTextWidth.setMinimum(100)
        self.plotTextWidth.setMaximum(1000)
        self.plotTextWidth.setValue(400)

        self.formLayout_3.setWidget(3, QFormLayout.FieldRole, self.plotTextWidth)

        self.verticalLayout_4.addLayout(self.formLayout_3)

        self.horizontalLayout.addWidget(self.otherBox)

        self.scrollArea.setWidget(self.scrollAreaWidgetContents)

        self.verticalLayout_3.addWidget(self.scrollArea)

        self.tabWidget.addTab(self.appearenceTab, "")
        self.keybindTab = QWidget()
        self.keybindTab.setObjectName("keybindTab")
        self.verticalLayout_2 = QVBoxLayout(self.keybindTab)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.scrollArea_2 = QScrollArea(self.keybindTab)
        self.scrollArea_2.setObjectName("scrollArea_2")
        self.scrollArea_2.setWidgetResizable(True)
        self.scrollAreaWidgetContents_2 = QWidget()
        self.scrollAreaWidgetContents_2.setObjectName("scrollAreaWidgetContents_2")
        self.scrollAreaWidgetContents_2.setGeometry(QRect(0, 0, 668, 410))
        self.verticalLayout_7 = QVBoxLayout(self.scrollAreaWidgetContents_2)
        self.verticalLayout_7.setObjectName("verticalLayout_7")
        self.formLayout_2 = QFormLayout()
        self.formLayout_2.setObjectName("formLayout_2")
        self.label = QLabel(self.scrollAreaWidgetContents_2)
        self.label.setObjectName("label")

        self.formLayout_2.setWidget(1, QFormLayout.LabelRole, self.label)

        self.playAudioShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.playAudioShortcutEdit.setObjectName("playAudioShortcutEdit")

        self.formLayout_2.setWidget(1, QFormLayout.FieldRole, self.playAudioShortcutEdit)

        self.label_2 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_2.setObjectName("label_2")

        self.formLayout_2.setWidget(2, QFormLayout.LabelRole, self.label_2)

        self.zoomInShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.zoomInShortcutEdit.setObjectName("zoomInShortcutEdit")

        self.formLayout_2.setWidget(2, QFormLayout.FieldRole, self.zoomInShortcutEdit)

        self.label_3 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_3.setObjectName("label_3")

        self.formLayout_2.setWidget(3, QFormLayout.LabelRole, self.label_3)

        self.zoomOutShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.zoomOutShortcutEdit.setObjectName("zoomOutShortcutEdit")

        self.formLayout_2.setWidget(3, QFormLayout.FieldRole, self.zoomOutShortcutEdit)

        self.label_4 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_4.setObjectName("label_4")

        self.formLayout_2.setWidget(5, QFormLayout.LabelRole, self.label_4)

        self.panLeftShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.panLeftShortcutEdit.setObjectName("panLeftShortcutEdit")

        self.formLayout_2.setWidget(5, QFormLayout.FieldRole, self.panLeftShortcutEdit)

        self.label_5 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_5.setObjectName("label_5")

        self.formLayout_2.setWidget(6, QFormLayout.LabelRole, self.label_5)

        self.panRightShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.panRightShortcutEdit.setObjectName("panRightShortcutEdit")

        self.formLayout_2.setWidget(6, QFormLayout.FieldRole, self.panRightShortcutEdit)

        self.label_6 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_6.setObjectName("label_6")

        self.formLayout_2.setWidget(7, QFormLayout.LabelRole, self.label_6)

        self.mergeShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.mergeShortcutEdit.setObjectName("mergeShortcutEdit")

        self.formLayout_2.setWidget(7, QFormLayout.FieldRole, self.mergeShortcutEdit)

        self.label_7 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_7.setObjectName("label_7")

        self.formLayout_2.setWidget(8, QFormLayout.LabelRole, self.label_7)

        self.splitShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.splitShortcutEdit.setObjectName("splitShortcutEdit")

        self.formLayout_2.setWidget(8, QFormLayout.FieldRole, self.splitShortcutEdit)

        self.label_8 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_8.setObjectName("label_8")

        self.formLayout_2.setWidget(9, QFormLayout.LabelRole, self.label_8)

        self.deleteShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.deleteShortcutEdit.setObjectName("deleteShortcutEdit")

        self.formLayout_2.setWidget(9, QFormLayout.FieldRole, self.deleteShortcutEdit)

        self.label_9 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_9.setObjectName("label_9")

        self.formLayout_2.setWidget(10, QFormLayout.LabelRole, self.label_9)

        self.saveShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.saveShortcutEdit.setObjectName("saveShortcutEdit")

        self.formLayout_2.setWidget(10, QFormLayout.FieldRole, self.saveShortcutEdit)

        self.label_10 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_10.setObjectName("label_10")

        self.formLayout_2.setWidget(11, QFormLayout.LabelRole, self.label_10)

        self.searchShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.searchShortcutEdit.setObjectName("searchShortcutEdit")

        self.formLayout_2.setWidget(11, QFormLayout.FieldRole, self.searchShortcutEdit)

        self.label_23 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_23.setObjectName("label_23")

        self.formLayout_2.setWidget(12, QFormLayout.LabelRole, self.label_23)

        self.undoShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.undoShortcutEdit.setObjectName("undoShortcutEdit")

        self.formLayout_2.setWidget(12, QFormLayout.FieldRole, self.undoShortcutEdit)

        self.label_22 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_22.setObjectName("label_22")

        self.formLayout_2.setWidget(13, QFormLayout.LabelRole, self.label_22)

        self.redoShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.redoShortcutEdit.setObjectName("redoShortcutEdit")

        self.formLayout_2.setWidget(13, QFormLayout.FieldRole, self.redoShortcutEdit)

        self.zoomToSelectionShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.zoomToSelectionShortcutEdit.setObjectName("zoomToSelectionShortcutEdit")

        self.formLayout_2.setWidget(4, QFormLayout.FieldRole, self.zoomToSelectionShortcutEdit)

        self.label_31 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_31.setObjectName("label_31")

        self.formLayout_2.setWidget(4, QFormLayout.LabelRole, self.label_31)

        self.verticalLayout_7.addLayout(self.formLayout_2)

        self.scrollArea_2.setWidget(self.scrollAreaWidgetContents_2)

        self.verticalLayout_2.addWidget(self.scrollArea_2)

        self.tabWidget.addTab(self.keybindTab, "")
        self.spectrogramTab = QWidget()
        self.spectrogramTab.setObjectName("spectrogramTab")
        self.verticalLayout_10 = QVBoxLayout(self.spectrogramTab)
        self.verticalLayout_10.setObjectName("verticalLayout_10")
        self.scrollArea_4 = QScrollArea(self.spectrogramTab)
        self.scrollArea_4.setObjectName("scrollArea_4")
        self.scrollArea_4.setWidgetResizable(True)
        self.scrollAreaWidgetContents_4 = QWidget()
        self.scrollAreaWidgetContents_4.setObjectName("scrollAreaWidgetContents_4")
        self.scrollAreaWidgetContents_4.setGeometry(QRect(0, 0, 682, 353))
        self.verticalLayout_11 = QVBoxLayout(self.scrollAreaWidgetContents_4)
        self.verticalLayout_11.setObjectName("verticalLayout_11")
        self.formLayout_6 = QFormLayout()
        self.formLayout_6.setObjectName("formLayout_6")
        self.label_42 = QLabel(self.scrollAreaWidgetContents_4)
        self.label_42.setObjectName("label_42")

        self.formLayout_6.setWidget(0, QFormLayout.LabelRole, self.label_42)

        self.dynamicRangeEdit = QSpinBox(self.scrollAreaWidgetContents_4)
        self.dynamicRangeEdit.setObjectName("dynamicRangeEdit")
        self.dynamicRangeEdit.setMaximum(10000)

        self.formLayout_6.setWidget(0, QFormLayout.FieldRole, self.dynamicRangeEdit)

        self.fftSizeEdit = QSpinBox(self.scrollAreaWidgetContents_4)
        self.fftSizeEdit.setObjectName("fftSizeEdit")
        self.fftSizeEdit.setMaximum(1000000)

        self.formLayout_6.setWidget(1, QFormLayout.FieldRole, self.fftSizeEdit)

        self.numTimeStepsEdit = QSpinBox(self.scrollAreaWidgetContents_4)
        self.numTimeStepsEdit.setObjectName("numTimeStepsEdit")
        self.numTimeStepsEdit.setMaximum(100000)
        self.numTimeStepsEdit.setSingleStep(10)

        self.formLayout_6.setWidget(2, QFormLayout.FieldRole, self.numTimeStepsEdit)

        self.maxFrequencyEdit = QSpinBox(self.scrollAreaWidgetContents_4)
        self.maxFrequencyEdit.setObjectName("maxFrequencyEdit")
        self.maxFrequencyEdit.setMaximum(1000000)
        self.maxFrequencyEdit.setSingleStep(1000)

        self.formLayout_6.setWidget(3, QFormLayout.FieldRole, self.maxFrequencyEdit)

        self.windowSizeEdit = QLineEdit(self.scrollAreaWidgetContents_4)
        self.windowSizeEdit.setObjectName("windowSizeEdit")

        self.formLayout_6.setWidget(4, QFormLayout.FieldRole, self.windowSizeEdit)

        self.preemphasisEdit = QLineEdit(self.scrollAreaWidgetContents_4)
        self.preemphasisEdit.setObjectName("preemphasisEdit")

        self.formLayout_6.setWidget(5, QFormLayout.FieldRole, self.preemphasisEdit)

        self.label_43 = QLabel(self.scrollAreaWidgetContents_4)
        self.label_43.setObjectName("label_43")

        self.formLayout_6.setWidget(1, QFormLayout.LabelRole, self.label_43)

        self.label_44 = QLabel(self.scrollAreaWidgetContents_4)
        self.label_44.setObjectName("label_44")

        self.formLayout_6.setWidget(2, QFormLayout.LabelRole, self.label_44)

        self.label_45 = QLabel(self.scrollAreaWidgetContents_4)
        self.label_45.setObjectName("label_45")

        self.formLayout_6.setWidget(3, QFormLayout.LabelRole, self.label_45)

        self.label_46 = QLabel(self.scrollAreaWidgetContents_4)
        self.label_46.setObjectName("label_46")

        self.formLayout_6.setWidget(4, QFormLayout.LabelRole, self.label_46)

        self.label_47 = QLabel(self.scrollAreaWidgetContents_4)
        self.label_47.setObjectName("label_47")

        self.formLayout_6.setWidget(5, QFormLayout.LabelRole, self.label_47)

        self.specMaxTimeEdit = QLineEdit(self.scrollAreaWidgetContents_4)
        self.specMaxTimeEdit.setObjectName("specMaxTimeEdit")

        self.formLayout_6.setWidget(6, QFormLayout.FieldRole, self.specMaxTimeEdit)

        self.label_24 = QLabel(self.scrollAreaWidgetContents_4)
        self.label_24.setObjectName("label_24")

        self.formLayout_6.setWidget(6, QFormLayout.LabelRole, self.label_24)

        self.verticalLayout_11.addLayout(self.formLayout_6)

        self.scrollArea_4.setWidget(self.scrollAreaWidgetContents_4)

        self.verticalLayout_10.addWidget(self.scrollArea_4)

        self.tabWidget.addTab(self.spectrogramTab, "")
        self.pitchTab = QWidget()
        self.pitchTab.setObjectName("pitchTab")
        self.verticalLayout_12 = QVBoxLayout(self.pitchTab)
        self.verticalLayout_12.setObjectName("verticalLayout_12")
        self.scrollArea_5 = QScrollArea(self.pitchTab)
        self.scrollArea_5.setObjectName("scrollArea_5")
        self.scrollArea_5.setWidgetResizable(True)
        self.scrollAreaWidgetContents_5 = QWidget()
        self.scrollAreaWidgetContents_5.setObjectName("scrollAreaWidgetContents_5")
        self.scrollAreaWidgetContents_5.setGeometry(QRect(0, 0, 682, 353))
        self.verticalLayout_13 = QVBoxLayout(self.scrollAreaWidgetContents_5)
        self.verticalLayout_13.setObjectName("verticalLayout_13")
        self.formLayout_7 = QFormLayout()
        self.formLayout_7.setObjectName("formLayout_7")
        self.label_34 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_34.setObjectName("label_34")

        self.formLayout_7.setWidget(0, QFormLayout.LabelRole, self.label_34)

        self.showPitchCheck = QCheckBox(self.scrollAreaWidgetContents_5)
        self.showPitchCheck.setObjectName("showPitchCheck")

        self.formLayout_7.setWidget(0, QFormLayout.FieldRole, self.showPitchCheck)

        self.label_36 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_36.setObjectName("label_36")

        self.formLayout_7.setWidget(1, QFormLayout.LabelRole, self.label_36)

        self.minPitchEdit = QSpinBox(self.scrollAreaWidgetContents_5)
        self.minPitchEdit.setObjectName("minPitchEdit")
        self.minPitchEdit.setMaximum(2000)
        self.minPitchEdit.setSingleStep(10)

        self.formLayout_7.setWidget(1, QFormLayout.FieldRole, self.minPitchEdit)

        self.label_37 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_37.setObjectName("label_37")

        self.formLayout_7.setWidget(2, QFormLayout.LabelRole, self.label_37)

        self.maxPitchEdit = QSpinBox(self.scrollAreaWidgetContents_5)
        self.maxPitchEdit.setObjectName("maxPitchEdit")
        self.maxPitchEdit.setMaximum(5000)
        self.maxPitchEdit.setSingleStep(10)

        self.formLayout_7.setWidget(2, QFormLayout.FieldRole, self.maxPitchEdit)

        self.label_38 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_38.setObjectName("label_38")

        self.formLayout_7.setWidget(3, QFormLayout.LabelRole, self.label_38)

        self.timeStepEdit = QSpinBox(self.scrollAreaWidgetContents_5)
        self.timeStepEdit.setObjectName("timeStepEdit")
        self.timeStepEdit.setMaximum(100000)
        self.timeStepEdit.setSingleStep(100)

        self.formLayout_7.setWidget(3, QFormLayout.FieldRole, self.timeStepEdit)

        self.label_39 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_39.setObjectName("label_39")

        self.formLayout_7.setWidget(4, QFormLayout.LabelRole, self.label_39)

        self.frameLengthEdit = QSpinBox(self.scrollAreaWidgetContents_5)
        self.frameLengthEdit.setObjectName("frameLengthEdit")

        self.formLayout_7.setWidget(4, QFormLayout.FieldRole, self.frameLengthEdit)

        self.penaltyEdit = QLineEdit(self.scrollAreaWidgetContents_5)
        self.penaltyEdit.setObjectName("penaltyEdit")

        self.formLayout_7.setWidget(5, QFormLayout.FieldRole, self.penaltyEdit)

        self.pitchDeltaEdit = QLineEdit(self.scrollAreaWidgetContents_5)
        self.pitchDeltaEdit.setObjectName("pitchDeltaEdit")

        self.formLayout_7.setWidget(6, QFormLayout.FieldRole, self.pitchDeltaEdit)

        self.label_40 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_40.setObjectName("label_40")

        self.formLayout_7.setWidget(5, QFormLayout.LabelRole, self.label_40)

        self.label_41 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_41.setObjectName("label_41")

        self.formLayout_7.setWidget(6, QFormLayout.LabelRole, self.label_41)

        self.pitchMaxTimeEdit = QLineEdit(self.scrollAreaWidgetContents_5)
        self.pitchMaxTimeEdit.setObjectName("pitchMaxTimeEdit")

        self.formLayout_7.setWidget(7, QFormLayout.FieldRole, self.pitchMaxTimeEdit)

        self.label_26 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_26.setObjectName("label_26")

        self.formLayout_7.setWidget(7, QFormLayout.LabelRole, self.label_26)

        self.verticalLayout_13.addLayout(self.formLayout_7)

        self.scrollArea_5.setWidget(self.scrollAreaWidgetContents_5)

        self.verticalLayout_12.addWidget(self.scrollArea_5)

        self.tabWidget.addTab(self.pitchTab, "")

        self.verticalLayout.addWidget(self.tabWidget)

        self.buttonBox = QDialogButtonBox(PreferencesDialog)
        self.buttonBox.setObjectName("buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)

        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(PreferencesDialog)
        self.buttonBox.accepted.connect(PreferencesDialog.accept)
        self.buttonBox.rejected.connect(PreferencesDialog.reject)

        self.tabWidget.setCurrentIndex(3)
        self.visibleSpeakerComboBox.setCurrentIndex(1)

        QMetaObject.connectSlotsByName(PreferencesDialog)

    # setupUi

    def retranslateUi(self, PreferencesDialog):
        PreferencesDialog.setWindowTitle(
            QCoreApplication.translate("PreferencesDialog", "Dialog", None)
        )
        self.autosaveLabel.setText(
            QCoreApplication.translate("PreferencesDialog", "Autosave on exit", None)
        )
        self.autoloadLastUsedCorpusLabel.setText(
            QCoreApplication.translate("PreferencesDialog", "Autoload last used corpus", None)
        )
        self.audioDeviceLabel.setText(
            QCoreApplication.translate("PreferencesDialog", "Audio device", None)
        )
        self.fadeInLabel.setText(
            QCoreApplication.translate("PreferencesDialog", "Fade in audio on play", None)
        )
        self.enableFadeCheckBox.setText("")
        self.useCudaLabel.setText(
            QCoreApplication.translate("PreferencesDialog", "Use CUDA", None)
        )
        self.numJobsLabel.setText(
            QCoreApplication.translate("PreferencesDialog", "Number of MFA jobs", None)
        )
        self.githubTokenLabel.setText(
            QCoreApplication.translate("PreferencesDialog", "Github request token", None)
        )
        self.resultsPerPageLabel.setText(
            QCoreApplication.translate("PreferencesDialog", "Results per page", None)
        )
        self.timeDirectionLabel.setText(
            QCoreApplication.translate("PreferencesDialog", "Time direction", None)
        )
        self.timeDirectionComboBox.setItemText(
            0, QCoreApplication.translate("PreferencesDialog", "Left-to-right", None)
        )
        self.timeDirectionComboBox.setItemText(
            1, QCoreApplication.translate("PreferencesDialog", "Right-to-left", None)
        )

        self.visibleSpeakerLabel.setText(
            QCoreApplication.translate("PreferencesDialog", "Maximum visible speakers", None)
        )
        self.visibleSpeakerComboBox.setItemText(
            0, QCoreApplication.translate("PreferencesDialog", "1", None)
        )
        self.visibleSpeakerComboBox.setItemText(
            1, QCoreApplication.translate("PreferencesDialog", "2", None)
        )
        self.visibleSpeakerComboBox.setItemText(
            2, QCoreApplication.translate("PreferencesDialog", "3", None)
        )
        self.visibleSpeakerComboBox.setItemText(
            3, QCoreApplication.translate("PreferencesDialog", "4", None)
        )
        self.visibleSpeakerComboBox.setItemText(
            4, QCoreApplication.translate("PreferencesDialog", "5", None)
        )

        self.cudaCheckBox.setText("")
        self.useMpCheckBox.setText("")
        self.useMpLabel.setText(
            QCoreApplication.translate("PreferencesDialog", "Use multiprocessing?", None)
        )
        self.hfTokenLabel.setText(
            QCoreApplication.translate("PreferencesDialog", "HuggingFace request token", None)
        )
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.generalTab),
            QCoreApplication.translate("PreferencesDialog", "General", None),
        )
        self.label_11.setText(QCoreApplication.translate("PreferencesDialog", "Theme", None))
        self.presetThemeEdit.setItemText(
            0, QCoreApplication.translate("PreferencesDialog", "MFA", None)
        )
        self.presetThemeEdit.setItemText(
            1, QCoreApplication.translate("PreferencesDialog", "Native", None)
        )
        self.presetThemeEdit.setItemText(
            2, QCoreApplication.translate("PreferencesDialog", "Custom", None)
        )

        self.label_12.setText(QCoreApplication.translate("PreferencesDialog", "Font", None))
        self.fontEdit.setText(QCoreApplication.translate("PreferencesDialog", "PushButton", None))
        self.primaryHueBox.setTitle(
            QCoreApplication.translate("PreferencesDialog", "Primary hues", None)
        )
        self.label_15.setText(QCoreApplication.translate("PreferencesDialog", "Base hue", None))
        self.primaryBaseEdit.setText("")
        self.label_16.setText(QCoreApplication.translate("PreferencesDialog", "Light", None))
        self.primaryLightEdit.setText("")
        self.label_19.setText(QCoreApplication.translate("PreferencesDialog", "Dark", None))
        self.primaryDarkEdit.setText("")
        self.label_28.setText(QCoreApplication.translate("PreferencesDialog", "Very light", None))
        self.primaryVeryLightEdit.setText("")
        self.label_27.setText(QCoreApplication.translate("PreferencesDialog", "Very dark", None))
        self.primaryVeryDarkEdit.setText("")
        self.accentHueBox.setTitle(
            QCoreApplication.translate("PreferencesDialog", "Accent hues", None)
        )
        self.label_20.setText(QCoreApplication.translate("PreferencesDialog", "Base hue", None))
        self.accentBaseEdit.setText("")
        self.label_30.setText(QCoreApplication.translate("PreferencesDialog", "Light", None))
        self.accentLightEdit.setText("")
        self.label_21.setText(QCoreApplication.translate("PreferencesDialog", "Dark", None))
        self.accentDarkEdit.setText("")
        self.label_35.setText(QCoreApplication.translate("PreferencesDialog", "Very light", None))
        self.accentVeryLightEdit.setText("")
        self.label_29.setText(QCoreApplication.translate("PreferencesDialog", "Very dark", None))
        self.accentVeryDarkEdit.setText("")
        self.otherBox.setTitle(QCoreApplication.translate("PreferencesDialog", "Other", None))
        self.label_14.setText(
            QCoreApplication.translate("PreferencesDialog", "Main text hue", None)
        )
        self.mainTextColorEdit.setText("")
        self.label_17.setText(
            QCoreApplication.translate("PreferencesDialog", "Selected text hue", None)
        )
        self.selectedTextColorEdit.setText("")
        self.label_18.setText(QCoreApplication.translate("PreferencesDialog", "Error hue", None))
        self.errorColorEdit.setText("")
        self.label_13.setText(
            QCoreApplication.translate("PreferencesDialog", "Plot text width", None)
        )
        self.plotTextWidth.setSuffix(QCoreApplication.translate("PreferencesDialog", "px", None))
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.appearenceTab),
            QCoreApplication.translate("PreferencesDialog", "Appearance", None),
        )
        self.label.setText(QCoreApplication.translate("PreferencesDialog", "Play audio", None))
        self.playAudioShortcutEdit.setKeySequence("")
        self.label_2.setText(QCoreApplication.translate("PreferencesDialog", "Zoom in", None))
        self.label_3.setText(QCoreApplication.translate("PreferencesDialog", "Zoom out", None))
        self.label_4.setText(QCoreApplication.translate("PreferencesDialog", "Pan left", None))
        self.label_5.setText(QCoreApplication.translate("PreferencesDialog", "Pan right", None))
        self.label_6.setText(
            QCoreApplication.translate("PreferencesDialog", "Merge utterances", None)
        )
        self.label_7.setText(
            QCoreApplication.translate("PreferencesDialog", "Split utterances", None)
        )
        self.label_8.setText(
            QCoreApplication.translate("PreferencesDialog", "Delete utterances", None)
        )
        self.label_9.setText(
            QCoreApplication.translate("PreferencesDialog", "Save current file", None)
        )
        self.label_10.setText(
            QCoreApplication.translate("PreferencesDialog", "Search within corpus", None)
        )
        self.label_23.setText(QCoreApplication.translate("PreferencesDialog", "Undo", None))
        self.label_22.setText(QCoreApplication.translate("PreferencesDialog", "Redo", None))
        self.label_31.setText(
            QCoreApplication.translate("PreferencesDialog", "Zoom to selection", None)
        )
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.keybindTab),
            QCoreApplication.translate("PreferencesDialog", "Key shortcuts", None),
        )
        self.label_42.setText(
            QCoreApplication.translate("PreferencesDialog", "Dynamic range (dB)", None)
        )
        self.label_43.setText(QCoreApplication.translate("PreferencesDialog", "FFT size", None))
        self.label_44.setText(
            QCoreApplication.translate("PreferencesDialog", "Number of time steps", None)
        )
        self.label_45.setText(
            QCoreApplication.translate("PreferencesDialog", "Maximum frequency (Hz)", None)
        )
        self.label_46.setText(
            QCoreApplication.translate("PreferencesDialog", "Window size (s)", None)
        )
        self.label_47.setText(
            QCoreApplication.translate("PreferencesDialog", "Pre-emphasis factor", None)
        )
        self.label_24.setText(
            QCoreApplication.translate("PreferencesDialog", "Maximum visible time (s)", None)
        )
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.spectrogramTab),
            QCoreApplication.translate("PreferencesDialog", "Spectrogram", None),
        )
        self.label_34.setText(QCoreApplication.translate("PreferencesDialog", "Show pitch", None))
        self.showPitchCheck.setText("")
        self.label_36.setText(
            QCoreApplication.translate("PreferencesDialog", "Minimum pitch (Hz)", None)
        )
        self.label_37.setText(
            QCoreApplication.translate("PreferencesDialog", "Maximum pitch (Hz)", None)
        )
        self.label_38.setText(
            QCoreApplication.translate("PreferencesDialog", "Time step (ms)", None)
        )
        self.label_39.setText(
            QCoreApplication.translate("PreferencesDialog", "Frame length (ms)", None)
        )
        self.label_40.setText(
            QCoreApplication.translate("PreferencesDialog", "Pentalty factor", None)
        )
        self.label_41.setText(
            QCoreApplication.translate("PreferencesDialog", "Pitch delta factor", None)
        )
        self.label_26.setText(
            QCoreApplication.translate("PreferencesDialog", "Maximum visible time (s)", None)
        )
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.pitchTab),
            QCoreApplication.translate("PreferencesDialog", "Pitch", None),
        )

    # retranslateUi
