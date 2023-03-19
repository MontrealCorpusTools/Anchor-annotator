# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'error_dialog.ui'
##
## Created by: Qt User Interface Compiler version 6.3.1
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
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import anchor.resources_rc
from anchor.widgets import ErrorButtonBox


class Ui_ErrorDialog(object):
    def setupUi(self, ErrorDialog):
        if not ErrorDialog.objectName():
            ErrorDialog.setObjectName("ErrorDialog")
        ErrorDialog.resize(400, 300)
        icon = QIcon()
        icon.addFile(
            ":/disabled/exclamation-triangle.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off
        )
        ErrorDialog.setWindowIcon(icon)
        ErrorDialog.setModal(True)
        self.verticalLayout = QVBoxLayout(ErrorDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.verticalLayout_2 = QVBoxLayout()
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.label = QLabel(ErrorDialog)
        self.label.setObjectName("label")
        self.label.setMaximumSize(QSize(75, 75))
        self.label.setPixmap(QPixmap(":/checked/bug.svg"))
        self.label.setScaledContents(True)
        self.label.setMargin(15)

        self.horizontalLayout_2.addWidget(self.label)

        self.line = QFrame(ErrorDialog)
        self.line.setObjectName("line")
        self.line.setFrameShape(QFrame.VLine)
        self.line.setFrameShadow(QFrame.Sunken)

        self.horizontalLayout_2.addWidget(self.line)

        self.label_2 = QLabel(ErrorDialog)
        self.label_2.setObjectName("label_2")
        self.label_2.setWordWrap(True)

        self.horizontalLayout_2.addWidget(self.label_2)

        self.verticalLayout_2.addLayout(self.horizontalLayout_2)

        self.detailed_message = QTextEdit(ErrorDialog)
        self.detailed_message.setObjectName("detailed_message")

        self.verticalLayout_2.addWidget(self.detailed_message)

        self.verticalLayout.addLayout(self.verticalLayout_2)

        self.buttonBox = ErrorButtonBox(ErrorDialog)
        self.buttonBox.setObjectName("buttonBox")
        self.buttonBox.setStyleSheet("")
        self.buttonBox.setStandardButtons(QDialogButtonBox.Close)

        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(ErrorDialog)

        QMetaObject.connectSlotsByName(ErrorDialog)

    # setupUi

    def retranslateUi(self, ErrorDialog):
        ErrorDialog.setWindowTitle(
            QCoreApplication.translate("ErrorDialog", "Error encountered", None)
        )
        self.label.setText("")
        self.label_2.setText(
            QCoreApplication.translate(
                "ErrorDialog",
                "Something went wrong! To report this bug, please copy and paste the text below along with what you were trying to do.  Thanks!",
                None,
            )
        )

    # retranslateUi
