# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'corpus_manager.ui'
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
    QHBoxLayout,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from anchor.widgets import (
    AcousticModelDetailWidget,
    AcousticModelListWidget,
    CorpusDetailWidget,
    CorpusListWidget,
    DictionaryModelDetailWidget,
    DictionaryModelListWidget,
    G2PModelDetailWidget,
    G2PModelListWidget,
    IvectorExtractorDetailWidget,
    IvectorExtractorListWidget,
    LanguageModelDetailWidget,
    LanguageModelListWidget,
)


class Ui_CorpusManagerDialog(object):
    def setupUi(self, CorpusManagerDialog):
        if not CorpusManagerDialog.objectName():
            CorpusManagerDialog.setObjectName("CorpusManagerDialog")
        CorpusManagerDialog.resize(1560, 973)
        self.verticalLayout = QVBoxLayout(CorpusManagerDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.tabWidget = QTabWidget(CorpusManagerDialog)
        self.tabWidget.setObjectName("tabWidget")
        self.corpusTab = QWidget()
        self.corpusTab.setObjectName("corpusTab")
        self.horizontalLayout_2 = QHBoxLayout(self.corpusTab)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.corpusListWidget = CorpusListWidget(self.corpusTab)
        self.corpusListWidget.setObjectName("corpusListWidget")

        self.horizontalLayout_2.addWidget(self.corpusListWidget)

        self.corpusDetailWidget = CorpusDetailWidget(self.corpusTab)
        self.corpusDetailWidget.setObjectName("corpusDetailWidget")

        self.horizontalLayout_2.addWidget(self.corpusDetailWidget)

        self.tabWidget.addTab(self.corpusTab, "")
        self.dictionaryTab = QWidget()
        self.dictionaryTab.setObjectName("dictionaryTab")
        self.horizontalLayout_3 = QHBoxLayout(self.dictionaryTab)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.dictionaryListWidget = DictionaryModelListWidget(self.dictionaryTab)
        self.dictionaryListWidget.setObjectName("dictionaryListWidget")

        self.horizontalLayout_3.addWidget(self.dictionaryListWidget)

        self.dictionaryDetailWidget = DictionaryModelDetailWidget(self.dictionaryTab)
        self.dictionaryDetailWidget.setObjectName("dictionaryDetailWidget")

        self.horizontalLayout_3.addWidget(self.dictionaryDetailWidget)

        self.tabWidget.addTab(self.dictionaryTab, "")
        self.acousticModelTab = QWidget()
        self.acousticModelTab.setObjectName("acousticModelTab")
        self.horizontalLayout_7 = QHBoxLayout(self.acousticModelTab)
        self.horizontalLayout_7.setObjectName("horizontalLayout_7")
        self.acousticModelListWidget = AcousticModelListWidget(self.acousticModelTab)
        self.acousticModelListWidget.setObjectName("acousticModelListWidget")

        self.horizontalLayout_7.addWidget(self.acousticModelListWidget)

        self.acousticModelDetailWidget = AcousticModelDetailWidget(self.acousticModelTab)
        self.acousticModelDetailWidget.setObjectName("acousticModelDetailWidget")

        self.horizontalLayout_7.addWidget(self.acousticModelDetailWidget)

        self.tabWidget.addTab(self.acousticModelTab, "")
        self.g2pModelTab = QWidget()
        self.g2pModelTab.setObjectName("g2pModelTab")
        self.horizontalLayout_4 = QHBoxLayout(self.g2pModelTab)
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        self.g2pModelListWidget = G2PModelListWidget(self.g2pModelTab)
        self.g2pModelListWidget.setObjectName("g2pModelListWidget")

        self.horizontalLayout_4.addWidget(self.g2pModelListWidget)

        self.g2pModelDetailWidget = G2PModelDetailWidget(self.g2pModelTab)
        self.g2pModelDetailWidget.setObjectName("g2pModelDetailWidget")

        self.horizontalLayout_4.addWidget(self.g2pModelDetailWidget)

        self.tabWidget.addTab(self.g2pModelTab, "")
        self.languageModelTab = QWidget()
        self.languageModelTab.setObjectName("languageModelTab")
        self.horizontalLayout_5 = QHBoxLayout(self.languageModelTab)
        self.horizontalLayout_5.setObjectName("horizontalLayout_5")
        self.languageModelListWidget = LanguageModelListWidget(self.languageModelTab)
        self.languageModelListWidget.setObjectName("languageModelListWidget")

        self.horizontalLayout_5.addWidget(self.languageModelListWidget)

        self.languageModelDetailWidget = LanguageModelDetailWidget(self.languageModelTab)
        self.languageModelDetailWidget.setObjectName("languageModelDetailWidget")

        self.horizontalLayout_5.addWidget(self.languageModelDetailWidget)

        self.tabWidget.addTab(self.languageModelTab, "")
        self.ivectorExtractorTab = QWidget()
        self.ivectorExtractorTab.setObjectName("ivectorExtractorTab")
        self.horizontalLayout_6 = QHBoxLayout(self.ivectorExtractorTab)
        self.horizontalLayout_6.setObjectName("horizontalLayout_6")
        self.ivectorExtractorListWidget = IvectorExtractorListWidget(self.ivectorExtractorTab)
        self.ivectorExtractorListWidget.setObjectName("ivectorExtractorListWidget")

        self.horizontalLayout_6.addWidget(self.ivectorExtractorListWidget)

        self.ivectorExtractorDetailWidget = IvectorExtractorDetailWidget(self.ivectorExtractorTab)
        self.ivectorExtractorDetailWidget.setObjectName("ivectorExtractorDetailWidget")

        self.horizontalLayout_6.addWidget(self.ivectorExtractorDetailWidget)

        self.tabWidget.addTab(self.ivectorExtractorTab, "")

        self.horizontalLayout.addWidget(self.tabWidget)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.buttonBox = QDialogButtonBox(CorpusManagerDialog)
        self.buttonBox.setObjectName("buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Ok)

        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(CorpusManagerDialog)
        self.buttonBox.accepted.connect(CorpusManagerDialog.accept)
        self.buttonBox.rejected.connect(CorpusManagerDialog.reject)

        self.tabWidget.setCurrentIndex(0)

        QMetaObject.connectSlotsByName(CorpusManagerDialog)

    # setupUi

    def retranslateUi(self, CorpusManagerDialog):
        CorpusManagerDialog.setWindowTitle(
            QCoreApplication.translate("CorpusManagerDialog", "Dialog", None)
        )
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.corpusTab),
            QCoreApplication.translate("CorpusManagerDialog", "Corpora", None),
        )
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.dictionaryTab),
            QCoreApplication.translate("CorpusManagerDialog", "Dictionaries", None),
        )
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.acousticModelTab),
            QCoreApplication.translate("CorpusManagerDialog", "Acoustic models", None),
        )
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.g2pModelTab),
            QCoreApplication.translate("CorpusManagerDialog", "G2P models", None),
        )
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.languageModelTab),
            QCoreApplication.translate("CorpusManagerDialog", "Language models", None),
        )
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.ivectorExtractorTab),
            QCoreApplication.translate("CorpusManagerDialog", "Ivector extractors", None),
        )

    # retranslateUi
