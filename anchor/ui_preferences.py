# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'preferences.ui'
##
## Created by: Qt User Interface Compiler version 6.4.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit,
    QScrollArea, QSizePolicy, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget)

from anchor.widgets import (ColorEdit, FontEdit)

class Ui_PreferencesDialog(object):
    def setupUi(self, PreferencesDialog):
        if not PreferencesDialog.objectName():
            PreferencesDialog.setObjectName(u"PreferencesDialog")
        PreferencesDialog.resize(724, 451)
        self.verticalLayout = QVBoxLayout(PreferencesDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.tabWidget = QTabWidget(PreferencesDialog)
        self.tabWidget.setObjectName(u"tabWidget")
        self.appearenceTab = QWidget()
        self.appearenceTab.setObjectName(u"appearenceTab")
        self.verticalLayout_3 = QVBoxLayout(self.appearenceTab)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.widget = QWidget(self.appearenceTab)
        self.widget.setObjectName(u"widget")
        self.horizontalLayout_2 = QHBoxLayout(self.widget)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.label_11 = QLabel(self.widget)
        self.label_11.setObjectName(u"label_11")

        self.horizontalLayout_2.addWidget(self.label_11)

        self.presetThemeEdit = QComboBox(self.widget)
        self.presetThemeEdit.addItem("")
        self.presetThemeEdit.addItem("")
        self.presetThemeEdit.addItem("")
        self.presetThemeEdit.setObjectName(u"presetThemeEdit")

        self.horizontalLayout_2.addWidget(self.presetThemeEdit)

        self.label_12 = QLabel(self.widget)
        self.label_12.setObjectName(u"label_12")

        self.horizontalLayout_2.addWidget(self.label_12)

        self.fontEdit = FontEdit(self.widget)
        self.fontEdit.setObjectName(u"fontEdit")

        self.horizontalLayout_2.addWidget(self.fontEdit)


        self.verticalLayout_3.addWidget(self.widget)

        self.scrollArea = QScrollArea(self.appearenceTab)
        self.scrollArea.setObjectName(u"scrollArea")
        self.scrollArea.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 682, 305))
        self.horizontalLayout = QHBoxLayout(self.scrollAreaWidgetContents)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.primaryHueBox = QGroupBox(self.scrollAreaWidgetContents)
        self.primaryHueBox.setObjectName(u"primaryHueBox")
        self.verticalLayout_6 = QVBoxLayout(self.primaryHueBox)
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.formLayout_5 = QFormLayout()
        self.formLayout_5.setObjectName(u"formLayout_5")
        self.label_15 = QLabel(self.primaryHueBox)
        self.label_15.setObjectName(u"label_15")

        self.formLayout_5.setWidget(0, QFormLayout.LabelRole, self.label_15)

        self.primaryBaseEdit = ColorEdit(self.primaryHueBox)
        self.primaryBaseEdit.setObjectName(u"primaryBaseEdit")

        self.formLayout_5.setWidget(0, QFormLayout.FieldRole, self.primaryBaseEdit)

        self.label_16 = QLabel(self.primaryHueBox)
        self.label_16.setObjectName(u"label_16")

        self.formLayout_5.setWidget(1, QFormLayout.LabelRole, self.label_16)

        self.primaryLightEdit = ColorEdit(self.primaryHueBox)
        self.primaryLightEdit.setObjectName(u"primaryLightEdit")

        self.formLayout_5.setWidget(1, QFormLayout.FieldRole, self.primaryLightEdit)

        self.label_19 = QLabel(self.primaryHueBox)
        self.label_19.setObjectName(u"label_19")

        self.formLayout_5.setWidget(2, QFormLayout.LabelRole, self.label_19)

        self.primaryDarkEdit = ColorEdit(self.primaryHueBox)
        self.primaryDarkEdit.setObjectName(u"primaryDarkEdit")

        self.formLayout_5.setWidget(2, QFormLayout.FieldRole, self.primaryDarkEdit)

        self.label_28 = QLabel(self.primaryHueBox)
        self.label_28.setObjectName(u"label_28")

        self.formLayout_5.setWidget(3, QFormLayout.LabelRole, self.label_28)

        self.primaryVeryLightEdit = ColorEdit(self.primaryHueBox)
        self.primaryVeryLightEdit.setObjectName(u"primaryVeryLightEdit")

        self.formLayout_5.setWidget(3, QFormLayout.FieldRole, self.primaryVeryLightEdit)

        self.label_27 = QLabel(self.primaryHueBox)
        self.label_27.setObjectName(u"label_27")

        self.formLayout_5.setWidget(4, QFormLayout.LabelRole, self.label_27)

        self.primaryVeryDarkEdit = ColorEdit(self.primaryHueBox)
        self.primaryVeryDarkEdit.setObjectName(u"primaryVeryDarkEdit")

        self.formLayout_5.setWidget(4, QFormLayout.FieldRole, self.primaryVeryDarkEdit)


        self.verticalLayout_6.addLayout(self.formLayout_5)


        self.horizontalLayout.addWidget(self.primaryHueBox)

        self.accentHueBox = QGroupBox(self.scrollAreaWidgetContents)
        self.accentHueBox.setObjectName(u"accentHueBox")
        self.verticalLayout_5 = QVBoxLayout(self.accentHueBox)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.formLayout_4 = QFormLayout()
        self.formLayout_4.setObjectName(u"formLayout_4")
        self.label_20 = QLabel(self.accentHueBox)
        self.label_20.setObjectName(u"label_20")

        self.formLayout_4.setWidget(0, QFormLayout.LabelRole, self.label_20)

        self.accentBaseEdit = ColorEdit(self.accentHueBox)
        self.accentBaseEdit.setObjectName(u"accentBaseEdit")

        self.formLayout_4.setWidget(0, QFormLayout.FieldRole, self.accentBaseEdit)

        self.label_30 = QLabel(self.accentHueBox)
        self.label_30.setObjectName(u"label_30")

        self.formLayout_4.setWidget(1, QFormLayout.LabelRole, self.label_30)

        self.accentLightEdit = ColorEdit(self.accentHueBox)
        self.accentLightEdit.setObjectName(u"accentLightEdit")

        self.formLayout_4.setWidget(1, QFormLayout.FieldRole, self.accentLightEdit)

        self.label_21 = QLabel(self.accentHueBox)
        self.label_21.setObjectName(u"label_21")

        self.formLayout_4.setWidget(2, QFormLayout.LabelRole, self.label_21)

        self.accentDarkEdit = ColorEdit(self.accentHueBox)
        self.accentDarkEdit.setObjectName(u"accentDarkEdit")

        self.formLayout_4.setWidget(2, QFormLayout.FieldRole, self.accentDarkEdit)

        self.label_35 = QLabel(self.accentHueBox)
        self.label_35.setObjectName(u"label_35")

        self.formLayout_4.setWidget(3, QFormLayout.LabelRole, self.label_35)

        self.accentVeryLightEdit = ColorEdit(self.accentHueBox)
        self.accentVeryLightEdit.setObjectName(u"accentVeryLightEdit")

        self.formLayout_4.setWidget(3, QFormLayout.FieldRole, self.accentVeryLightEdit)

        self.label_29 = QLabel(self.accentHueBox)
        self.label_29.setObjectName(u"label_29")

        self.formLayout_4.setWidget(4, QFormLayout.LabelRole, self.label_29)

        self.accentVeryDarkEdit = ColorEdit(self.accentHueBox)
        self.accentVeryDarkEdit.setObjectName(u"accentVeryDarkEdit")

        self.formLayout_4.setWidget(4, QFormLayout.FieldRole, self.accentVeryDarkEdit)


        self.verticalLayout_5.addLayout(self.formLayout_4)


        self.horizontalLayout.addWidget(self.accentHueBox)

        self.otherBox = QGroupBox(self.scrollAreaWidgetContents)
        self.otherBox.setObjectName(u"otherBox")
        self.verticalLayout_4 = QVBoxLayout(self.otherBox)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.formLayout_3 = QFormLayout()
        self.formLayout_3.setObjectName(u"formLayout_3")
        self.label_14 = QLabel(self.otherBox)
        self.label_14.setObjectName(u"label_14")

        self.formLayout_3.setWidget(0, QFormLayout.LabelRole, self.label_14)

        self.mainTextColorEdit = ColorEdit(self.otherBox)
        self.mainTextColorEdit.setObjectName(u"mainTextColorEdit")

        self.formLayout_3.setWidget(0, QFormLayout.FieldRole, self.mainTextColorEdit)

        self.label_17 = QLabel(self.otherBox)
        self.label_17.setObjectName(u"label_17")

        self.formLayout_3.setWidget(1, QFormLayout.LabelRole, self.label_17)

        self.selectedTextColorEdit = ColorEdit(self.otherBox)
        self.selectedTextColorEdit.setObjectName(u"selectedTextColorEdit")

        self.formLayout_3.setWidget(1, QFormLayout.FieldRole, self.selectedTextColorEdit)

        self.label_18 = QLabel(self.otherBox)
        self.label_18.setObjectName(u"label_18")

        self.formLayout_3.setWidget(2, QFormLayout.LabelRole, self.label_18)

        self.errorColorEdit = ColorEdit(self.otherBox)
        self.errorColorEdit.setObjectName(u"errorColorEdit")

        self.formLayout_3.setWidget(2, QFormLayout.FieldRole, self.errorColorEdit)

        self.label_13 = QLabel(self.otherBox)
        self.label_13.setObjectName(u"label_13")

        self.formLayout_3.setWidget(3, QFormLayout.LabelRole, self.label_13)

        self.plotTextWidth = QSpinBox(self.otherBox)
        self.plotTextWidth.setObjectName(u"plotTextWidth")
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
        self.keybindTab.setObjectName(u"keybindTab")
        self.verticalLayout_2 = QVBoxLayout(self.keybindTab)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.scrollArea_2 = QScrollArea(self.keybindTab)
        self.scrollArea_2.setObjectName(u"scrollArea_2")
        self.scrollArea_2.setWidgetResizable(True)
        self.scrollAreaWidgetContents_2 = QWidget()
        self.scrollAreaWidgetContents_2.setObjectName(u"scrollAreaWidgetContents_2")
        self.scrollAreaWidgetContents_2.setGeometry(QRect(0, 0, 668, 410))
        self.verticalLayout_7 = QVBoxLayout(self.scrollAreaWidgetContents_2)
        self.verticalLayout_7.setObjectName(u"verticalLayout_7")
        self.formLayout_2 = QFormLayout()
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.label = QLabel(self.scrollAreaWidgetContents_2)
        self.label.setObjectName(u"label")

        self.formLayout_2.setWidget(1, QFormLayout.LabelRole, self.label)

        self.playAudioShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.playAudioShortcutEdit.setObjectName(u"playAudioShortcutEdit")

        self.formLayout_2.setWidget(1, QFormLayout.FieldRole, self.playAudioShortcutEdit)

        self.label_2 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_2.setObjectName(u"label_2")

        self.formLayout_2.setWidget(2, QFormLayout.LabelRole, self.label_2)

        self.zoomInShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.zoomInShortcutEdit.setObjectName(u"zoomInShortcutEdit")

        self.formLayout_2.setWidget(2, QFormLayout.FieldRole, self.zoomInShortcutEdit)

        self.label_3 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_3.setObjectName(u"label_3")

        self.formLayout_2.setWidget(3, QFormLayout.LabelRole, self.label_3)

        self.zoomOutShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.zoomOutShortcutEdit.setObjectName(u"zoomOutShortcutEdit")

        self.formLayout_2.setWidget(3, QFormLayout.FieldRole, self.zoomOutShortcutEdit)

        self.label_4 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_4.setObjectName(u"label_4")

        self.formLayout_2.setWidget(5, QFormLayout.LabelRole, self.label_4)

        self.panLeftShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.panLeftShortcutEdit.setObjectName(u"panLeftShortcutEdit")

        self.formLayout_2.setWidget(5, QFormLayout.FieldRole, self.panLeftShortcutEdit)

        self.label_5 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_5.setObjectName(u"label_5")

        self.formLayout_2.setWidget(6, QFormLayout.LabelRole, self.label_5)

        self.panRightShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.panRightShortcutEdit.setObjectName(u"panRightShortcutEdit")

        self.formLayout_2.setWidget(6, QFormLayout.FieldRole, self.panRightShortcutEdit)

        self.label_6 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_6.setObjectName(u"label_6")

        self.formLayout_2.setWidget(7, QFormLayout.LabelRole, self.label_6)

        self.mergeShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.mergeShortcutEdit.setObjectName(u"mergeShortcutEdit")

        self.formLayout_2.setWidget(7, QFormLayout.FieldRole, self.mergeShortcutEdit)

        self.label_7 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_7.setObjectName(u"label_7")

        self.formLayout_2.setWidget(8, QFormLayout.LabelRole, self.label_7)

        self.splitShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.splitShortcutEdit.setObjectName(u"splitShortcutEdit")

        self.formLayout_2.setWidget(8, QFormLayout.FieldRole, self.splitShortcutEdit)

        self.label_8 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_8.setObjectName(u"label_8")

        self.formLayout_2.setWidget(9, QFormLayout.LabelRole, self.label_8)

        self.deleteShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.deleteShortcutEdit.setObjectName(u"deleteShortcutEdit")

        self.formLayout_2.setWidget(9, QFormLayout.FieldRole, self.deleteShortcutEdit)

        self.label_9 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_9.setObjectName(u"label_9")

        self.formLayout_2.setWidget(10, QFormLayout.LabelRole, self.label_9)

        self.saveShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.saveShortcutEdit.setObjectName(u"saveShortcutEdit")

        self.formLayout_2.setWidget(10, QFormLayout.FieldRole, self.saveShortcutEdit)

        self.label_10 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_10.setObjectName(u"label_10")

        self.formLayout_2.setWidget(11, QFormLayout.LabelRole, self.label_10)

        self.searchShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.searchShortcutEdit.setObjectName(u"searchShortcutEdit")

        self.formLayout_2.setWidget(11, QFormLayout.FieldRole, self.searchShortcutEdit)

        self.label_23 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_23.setObjectName(u"label_23")

        self.formLayout_2.setWidget(12, QFormLayout.LabelRole, self.label_23)

        self.undoShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.undoShortcutEdit.setObjectName(u"undoShortcutEdit")

        self.formLayout_2.setWidget(12, QFormLayout.FieldRole, self.undoShortcutEdit)

        self.label_22 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_22.setObjectName(u"label_22")

        self.formLayout_2.setWidget(13, QFormLayout.LabelRole, self.label_22)

        self.redoShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.redoShortcutEdit.setObjectName(u"redoShortcutEdit")

        self.formLayout_2.setWidget(13, QFormLayout.FieldRole, self.redoShortcutEdit)

        self.zoomToSelectionShortcutEdit = QKeySequenceEdit(self.scrollAreaWidgetContents_2)
        self.zoomToSelectionShortcutEdit.setObjectName(u"zoomToSelectionShortcutEdit")

        self.formLayout_2.setWidget(4, QFormLayout.FieldRole, self.zoomToSelectionShortcutEdit)

        self.label_31 = QLabel(self.scrollAreaWidgetContents_2)
        self.label_31.setObjectName(u"label_31")

        self.formLayout_2.setWidget(4, QFormLayout.LabelRole, self.label_31)


        self.verticalLayout_7.addLayout(self.formLayout_2)

        self.scrollArea_2.setWidget(self.scrollAreaWidgetContents_2)

        self.verticalLayout_2.addWidget(self.scrollArea_2)

        self.tabWidget.addTab(self.keybindTab, "")
        self.spectrogramTab = QWidget()
        self.spectrogramTab.setObjectName(u"spectrogramTab")
        self.verticalLayout_10 = QVBoxLayout(self.spectrogramTab)
        self.verticalLayout_10.setObjectName(u"verticalLayout_10")
        self.scrollArea_4 = QScrollArea(self.spectrogramTab)
        self.scrollArea_4.setObjectName(u"scrollArea_4")
        self.scrollArea_4.setWidgetResizable(True)
        self.scrollAreaWidgetContents_4 = QWidget()
        self.scrollAreaWidgetContents_4.setObjectName(u"scrollAreaWidgetContents_4")
        self.scrollAreaWidgetContents_4.setGeometry(QRect(0, 0, 682, 353))
        self.verticalLayout_11 = QVBoxLayout(self.scrollAreaWidgetContents_4)
        self.verticalLayout_11.setObjectName(u"verticalLayout_11")
        self.formLayout_6 = QFormLayout()
        self.formLayout_6.setObjectName(u"formLayout_6")
        self.label_42 = QLabel(self.scrollAreaWidgetContents_4)
        self.label_42.setObjectName(u"label_42")

        self.formLayout_6.setWidget(0, QFormLayout.LabelRole, self.label_42)

        self.spinBox_5 = QSpinBox(self.scrollAreaWidgetContents_4)
        self.spinBox_5.setObjectName(u"spinBox_5")

        self.formLayout_6.setWidget(0, QFormLayout.FieldRole, self.spinBox_5)

        self.spinBox_6 = QSpinBox(self.scrollAreaWidgetContents_4)
        self.spinBox_6.setObjectName(u"spinBox_6")

        self.formLayout_6.setWidget(1, QFormLayout.FieldRole, self.spinBox_6)

        self.spinBox_7 = QSpinBox(self.scrollAreaWidgetContents_4)
        self.spinBox_7.setObjectName(u"spinBox_7")

        self.formLayout_6.setWidget(2, QFormLayout.FieldRole, self.spinBox_7)

        self.spinBox_8 = QSpinBox(self.scrollAreaWidgetContents_4)
        self.spinBox_8.setObjectName(u"spinBox_8")

        self.formLayout_6.setWidget(3, QFormLayout.FieldRole, self.spinBox_8)

        self.lineEdit_3 = QLineEdit(self.scrollAreaWidgetContents_4)
        self.lineEdit_3.setObjectName(u"lineEdit_3")

        self.formLayout_6.setWidget(4, QFormLayout.FieldRole, self.lineEdit_3)

        self.lineEdit_4 = QLineEdit(self.scrollAreaWidgetContents_4)
        self.lineEdit_4.setObjectName(u"lineEdit_4")

        self.formLayout_6.setWidget(5, QFormLayout.FieldRole, self.lineEdit_4)

        self.label_43 = QLabel(self.scrollAreaWidgetContents_4)
        self.label_43.setObjectName(u"label_43")

        self.formLayout_6.setWidget(1, QFormLayout.LabelRole, self.label_43)

        self.label_44 = QLabel(self.scrollAreaWidgetContents_4)
        self.label_44.setObjectName(u"label_44")

        self.formLayout_6.setWidget(2, QFormLayout.LabelRole, self.label_44)

        self.label_45 = QLabel(self.scrollAreaWidgetContents_4)
        self.label_45.setObjectName(u"label_45")

        self.formLayout_6.setWidget(3, QFormLayout.LabelRole, self.label_45)

        self.label_46 = QLabel(self.scrollAreaWidgetContents_4)
        self.label_46.setObjectName(u"label_46")

        self.formLayout_6.setWidget(4, QFormLayout.LabelRole, self.label_46)

        self.label_47 = QLabel(self.scrollAreaWidgetContents_4)
        self.label_47.setObjectName(u"label_47")

        self.formLayout_6.setWidget(5, QFormLayout.LabelRole, self.label_47)


        self.verticalLayout_11.addLayout(self.formLayout_6)

        self.scrollArea_4.setWidget(self.scrollAreaWidgetContents_4)

        self.verticalLayout_10.addWidget(self.scrollArea_4)

        self.tabWidget.addTab(self.spectrogramTab, "")
        self.pitchTab = QWidget()
        self.pitchTab.setObjectName(u"pitchTab")
        self.verticalLayout_12 = QVBoxLayout(self.pitchTab)
        self.verticalLayout_12.setObjectName(u"verticalLayout_12")
        self.scrollArea_5 = QScrollArea(self.pitchTab)
        self.scrollArea_5.setObjectName(u"scrollArea_5")
        self.scrollArea_5.setWidgetResizable(True)
        self.scrollAreaWidgetContents_5 = QWidget()
        self.scrollAreaWidgetContents_5.setObjectName(u"scrollAreaWidgetContents_5")
        self.scrollAreaWidgetContents_5.setGeometry(QRect(0, 0, 682, 353))
        self.verticalLayout_13 = QVBoxLayout(self.scrollAreaWidgetContents_5)
        self.verticalLayout_13.setObjectName(u"verticalLayout_13")
        self.formLayout_7 = QFormLayout()
        self.formLayout_7.setObjectName(u"formLayout_7")
        self.label_34 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_34.setObjectName(u"label_34")

        self.formLayout_7.setWidget(0, QFormLayout.LabelRole, self.label_34)

        self.checkBox = QCheckBox(self.scrollAreaWidgetContents_5)
        self.checkBox.setObjectName(u"checkBox")

        self.formLayout_7.setWidget(0, QFormLayout.FieldRole, self.checkBox)

        self.label_36 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_36.setObjectName(u"label_36")

        self.formLayout_7.setWidget(1, QFormLayout.LabelRole, self.label_36)

        self.spinBox = QSpinBox(self.scrollAreaWidgetContents_5)
        self.spinBox.setObjectName(u"spinBox")

        self.formLayout_7.setWidget(1, QFormLayout.FieldRole, self.spinBox)

        self.label_37 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_37.setObjectName(u"label_37")

        self.formLayout_7.setWidget(2, QFormLayout.LabelRole, self.label_37)

        self.spinBox_2 = QSpinBox(self.scrollAreaWidgetContents_5)
        self.spinBox_2.setObjectName(u"spinBox_2")

        self.formLayout_7.setWidget(2, QFormLayout.FieldRole, self.spinBox_2)

        self.label_38 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_38.setObjectName(u"label_38")

        self.formLayout_7.setWidget(3, QFormLayout.LabelRole, self.label_38)

        self.spinBox_3 = QSpinBox(self.scrollAreaWidgetContents_5)
        self.spinBox_3.setObjectName(u"spinBox_3")

        self.formLayout_7.setWidget(3, QFormLayout.FieldRole, self.spinBox_3)

        self.label_39 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_39.setObjectName(u"label_39")

        self.formLayout_7.setWidget(4, QFormLayout.LabelRole, self.label_39)

        self.spinBox_4 = QSpinBox(self.scrollAreaWidgetContents_5)
        self.spinBox_4.setObjectName(u"spinBox_4")

        self.formLayout_7.setWidget(4, QFormLayout.FieldRole, self.spinBox_4)

        self.lineEdit = QLineEdit(self.scrollAreaWidgetContents_5)
        self.lineEdit.setObjectName(u"lineEdit")

        self.formLayout_7.setWidget(5, QFormLayout.FieldRole, self.lineEdit)

        self.lineEdit_2 = QLineEdit(self.scrollAreaWidgetContents_5)
        self.lineEdit_2.setObjectName(u"lineEdit_2")

        self.formLayout_7.setWidget(6, QFormLayout.FieldRole, self.lineEdit_2)

        self.label_40 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_40.setObjectName(u"label_40")

        self.formLayout_7.setWidget(5, QFormLayout.LabelRole, self.label_40)

        self.label_41 = QLabel(self.scrollAreaWidgetContents_5)
        self.label_41.setObjectName(u"label_41")

        self.formLayout_7.setWidget(6, QFormLayout.LabelRole, self.label_41)


        self.verticalLayout_13.addLayout(self.formLayout_7)

        self.scrollArea_5.setWidget(self.scrollAreaWidgetContents_5)

        self.verticalLayout_12.addWidget(self.scrollArea_5)

        self.tabWidget.addTab(self.pitchTab, "")
        self.generalTab = QWidget()
        self.generalTab.setObjectName(u"generalTab")
        self.verticalLayout_8 = QVBoxLayout(self.generalTab)
        self.verticalLayout_8.setObjectName(u"verticalLayout_8")
        self.scrollArea_3 = QScrollArea(self.generalTab)
        self.scrollArea_3.setObjectName(u"scrollArea_3")
        self.scrollArea_3.setWidgetResizable(True)
        self.scrollAreaWidgetContents_3 = QWidget()
        self.scrollAreaWidgetContents_3.setObjectName(u"scrollAreaWidgetContents_3")
        self.scrollAreaWidgetContents_3.setGeometry(QRect(0, 0, 682, 353))
        self.verticalLayout_9 = QVBoxLayout(self.scrollAreaWidgetContents_3)
        self.verticalLayout_9.setObjectName(u"verticalLayout_9")
        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.label_24 = QLabel(self.scrollAreaWidgetContents_3)
        self.label_24.setObjectName(u"label_24")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.label_24)

        self.audioDeviceEdit = QComboBox(self.scrollAreaWidgetContents_3)
        self.audioDeviceEdit.setObjectName(u"audioDeviceEdit")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.audioDeviceEdit)

        self.numJobsEdit = QSpinBox(self.scrollAreaWidgetContents_3)
        self.numJobsEdit.setObjectName(u"numJobsEdit")

        self.formLayout.setWidget(5, QFormLayout.FieldRole, self.numJobsEdit)

        self.label_25 = QLabel(self.scrollAreaWidgetContents_3)
        self.label_25.setObjectName(u"label_25")

        self.formLayout.setWidget(5, QFormLayout.LabelRole, self.label_25)

        self.useMpCheckBox = QCheckBox(self.scrollAreaWidgetContents_3)
        self.useMpCheckBox.setObjectName(u"useMpCheckBox")

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.useMpCheckBox)

        self.label_26 = QLabel(self.scrollAreaWidgetContents_3)
        self.label_26.setObjectName(u"label_26")

        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.label_26)

        self.autosaveLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.autosaveLabel.setObjectName(u"autosaveLabel")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.autosaveLabel)

        self.autosaveOnExitCheckBox = QCheckBox(self.scrollAreaWidgetContents_3)
        self.autosaveOnExitCheckBox.setObjectName(u"autosaveOnExitCheckBox")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.autosaveOnExitCheckBox)

        self.autoloadLastUsedCorpusLabel = QLabel(self.scrollAreaWidgetContents_3)
        self.autoloadLastUsedCorpusLabel.setObjectName(u"autoloadLastUsedCorpusLabel")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.autoloadLastUsedCorpusLabel)

        self.autoloadLastUsedCorpusCheckBox = QCheckBox(self.scrollAreaWidgetContents_3)
        self.autoloadLastUsedCorpusCheckBox.setObjectName(u"autoloadLastUsedCorpusCheckBox")

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.autoloadLastUsedCorpusCheckBox)

        self.githubTokenEdit = QLineEdit(self.scrollAreaWidgetContents_3)
        self.githubTokenEdit.setObjectName(u"githubTokenEdit")

        self.formLayout.setWidget(6, QFormLayout.FieldRole, self.githubTokenEdit)

        self.label_32 = QLabel(self.scrollAreaWidgetContents_3)
        self.label_32.setObjectName(u"label_32")

        self.formLayout.setWidget(6, QFormLayout.LabelRole, self.label_32)

        self.resultsPerPageEdit = QSpinBox(self.scrollAreaWidgetContents_3)
        self.resultsPerPageEdit.setObjectName(u"resultsPerPageEdit")

        self.formLayout.setWidget(7, QFormLayout.FieldRole, self.resultsPerPageEdit)

        self.label_33 = QLabel(self.scrollAreaWidgetContents_3)
        self.label_33.setObjectName(u"label_33")

        self.formLayout.setWidget(7, QFormLayout.LabelRole, self.label_33)

        self.cudaCheckBox = QCheckBox(self.scrollAreaWidgetContents_3)
        self.cudaCheckBox.setObjectName(u"cudaCheckBox")

        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.cudaCheckBox)

        self.label_48 = QLabel(self.scrollAreaWidgetContents_3)
        self.label_48.setObjectName(u"label_48")

        self.formLayout.setWidget(4, QFormLayout.LabelRole, self.label_48)


        self.verticalLayout_9.addLayout(self.formLayout)

        self.scrollArea_3.setWidget(self.scrollAreaWidgetContents_3)

        self.verticalLayout_8.addWidget(self.scrollArea_3)

        self.tabWidget.addTab(self.generalTab, "")

        self.verticalLayout.addWidget(self.tabWidget)

        self.buttonBox = QDialogButtonBox(PreferencesDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.verticalLayout.addWidget(self.buttonBox)


        self.retranslateUi(PreferencesDialog)
        self.buttonBox.accepted.connect(PreferencesDialog.accept)
        self.buttonBox.rejected.connect(PreferencesDialog.reject)

        self.tabWidget.setCurrentIndex(4)


        QMetaObject.connectSlotsByName(PreferencesDialog)
    # setupUi

    def retranslateUi(self, PreferencesDialog):
        PreferencesDialog.setWindowTitle(QCoreApplication.translate("PreferencesDialog", u"Dialog", None))
        self.label_11.setText(QCoreApplication.translate("PreferencesDialog", u"Theme", None))
        self.presetThemeEdit.setItemText(0, QCoreApplication.translate("PreferencesDialog", u"MFA", None))
        self.presetThemeEdit.setItemText(1, QCoreApplication.translate("PreferencesDialog", u"Praat-like", None))
        self.presetThemeEdit.setItemText(2, QCoreApplication.translate("PreferencesDialog", u"Custom", None))

        self.label_12.setText(QCoreApplication.translate("PreferencesDialog", u"Font", None))
        self.fontEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.primaryHueBox.setTitle(QCoreApplication.translate("PreferencesDialog", u"Primary hues", None))
        self.label_15.setText(QCoreApplication.translate("PreferencesDialog", u"Base hue", None))
        self.primaryBaseEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.label_16.setText(QCoreApplication.translate("PreferencesDialog", u"Light", None))
        self.primaryLightEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.label_19.setText(QCoreApplication.translate("PreferencesDialog", u"Dark", None))
        self.primaryDarkEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.label_28.setText(QCoreApplication.translate("PreferencesDialog", u"Very light", None))
        self.primaryVeryLightEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.label_27.setText(QCoreApplication.translate("PreferencesDialog", u"Very dark", None))
        self.primaryVeryDarkEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.accentHueBox.setTitle(QCoreApplication.translate("PreferencesDialog", u"Accent hues", None))
        self.label_20.setText(QCoreApplication.translate("PreferencesDialog", u"Base hue", None))
        self.accentBaseEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.label_30.setText(QCoreApplication.translate("PreferencesDialog", u"Light", None))
        self.accentLightEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.label_21.setText(QCoreApplication.translate("PreferencesDialog", u"Dark", None))
        self.accentDarkEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.label_35.setText(QCoreApplication.translate("PreferencesDialog", u"Very light", None))
        self.accentVeryLightEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.label_29.setText(QCoreApplication.translate("PreferencesDialog", u"Very dark", None))
        self.accentVeryDarkEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.otherBox.setTitle(QCoreApplication.translate("PreferencesDialog", u"Other", None))
        self.label_14.setText(QCoreApplication.translate("PreferencesDialog", u"Main text hue", None))
        self.mainTextColorEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.label_17.setText(QCoreApplication.translate("PreferencesDialog", u"Selected text hue", None))
        self.selectedTextColorEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.label_18.setText(QCoreApplication.translate("PreferencesDialog", u"Error hue", None))
        self.errorColorEdit.setText(QCoreApplication.translate("PreferencesDialog", u"PushButton", None))
        self.label_13.setText(QCoreApplication.translate("PreferencesDialog", u"Plot text width", None))
        self.plotTextWidth.setSuffix(QCoreApplication.translate("PreferencesDialog", u"px", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.appearenceTab), QCoreApplication.translate("PreferencesDialog", u"Appearance", None))
        self.label.setText(QCoreApplication.translate("PreferencesDialog", u"Play audio", None))
        self.playAudioShortcutEdit.setKeySequence("")
        self.label_2.setText(QCoreApplication.translate("PreferencesDialog", u"Zoom in", None))
        self.label_3.setText(QCoreApplication.translate("PreferencesDialog", u"Zoom out", None))
        self.label_4.setText(QCoreApplication.translate("PreferencesDialog", u"Pan left", None))
        self.label_5.setText(QCoreApplication.translate("PreferencesDialog", u"Pan right", None))
        self.label_6.setText(QCoreApplication.translate("PreferencesDialog", u"Merge utterances", None))
        self.label_7.setText(QCoreApplication.translate("PreferencesDialog", u"Split utterances", None))
        self.label_8.setText(QCoreApplication.translate("PreferencesDialog", u"Delete utterances", None))
        self.label_9.setText(QCoreApplication.translate("PreferencesDialog", u"Save current file", None))
        self.label_10.setText(QCoreApplication.translate("PreferencesDialog", u"Search within corpus", None))
        self.label_23.setText(QCoreApplication.translate("PreferencesDialog", u"Undo", None))
        self.label_22.setText(QCoreApplication.translate("PreferencesDialog", u"Redo", None))
        self.label_31.setText(QCoreApplication.translate("PreferencesDialog", u"Zoom to selection", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.keybindTab), QCoreApplication.translate("PreferencesDialog", u"Key shortcuts", None))
        self.label_42.setText(QCoreApplication.translate("PreferencesDialog", u"Dynamic range (dB)", None))
        self.label_43.setText(QCoreApplication.translate("PreferencesDialog", u"FFT size", None))
        self.label_44.setText(QCoreApplication.translate("PreferencesDialog", u"Number of time steps", None))
        self.label_45.setText(QCoreApplication.translate("PreferencesDialog", u"Maximum frequency (Hz)", None))
        self.label_46.setText(QCoreApplication.translate("PreferencesDialog", u"Window size (s)", None))
        self.label_47.setText(QCoreApplication.translate("PreferencesDialog", u"Pre-emphasis factor", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.spectrogramTab), QCoreApplication.translate("PreferencesDialog", u"Spectrogram", None))
        self.label_34.setText(QCoreApplication.translate("PreferencesDialog", u"Show pitch", None))
        self.checkBox.setText("")
        self.label_36.setText(QCoreApplication.translate("PreferencesDialog", u"Minimum pitch (Hz)", None))
        self.label_37.setText(QCoreApplication.translate("PreferencesDialog", u"Maximum pitch (Hz)", None))
        self.label_38.setText(QCoreApplication.translate("PreferencesDialog", u"Time step (ms)", None))
        self.label_39.setText(QCoreApplication.translate("PreferencesDialog", u"Frame length (ms)", None))
        self.label_40.setText(QCoreApplication.translate("PreferencesDialog", u"Pentalty factor", None))
        self.label_41.setText(QCoreApplication.translate("PreferencesDialog", u"Pitch delta factor", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.pitchTab), QCoreApplication.translate("PreferencesDialog", u"Pitch", None))
        self.label_24.setText(QCoreApplication.translate("PreferencesDialog", u"Audio device", None))
        self.label_25.setText(QCoreApplication.translate("PreferencesDialog", u"Number of processors to use", None))
        self.useMpCheckBox.setText("")
        self.label_26.setText(QCoreApplication.translate("PreferencesDialog", u"Use multiprocessing?", None))
        self.autosaveLabel.setText(QCoreApplication.translate("PreferencesDialog", u"Autosave on exit", None))
        self.autoloadLastUsedCorpusLabel.setText(QCoreApplication.translate("PreferencesDialog", u"Autoload last used corpus", None))
        self.label_32.setText(QCoreApplication.translate("PreferencesDialog", u"Github request token", None))
        self.label_33.setText(QCoreApplication.translate("PreferencesDialog", u"Results per page", None))
        self.cudaCheckBox.setText("")
        self.label_48.setText(QCoreApplication.translate("PreferencesDialog", u"Use CUDA", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.generalTab), QCoreApplication.translate("PreferencesDialog", u"General", None))
    # retranslateUi

