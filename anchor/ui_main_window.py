# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_window.ui'
##
## Created by: Qt User Interface Compiler version 6.7.1
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
    QAction,
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
    QApplication,
    QDockWidget,
    QMainWindow,
    QMenu,
    QMenuBar,
    QSizePolicy,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

import anchor.resources_rc
from anchor.widgets import (
    AcousticModelWidget,
    AlignmentAnalysisWidget,
    AlignmentWidget,
    DiarizationWidget,
    DictionaryWidget,
    LanguageModelWidget,
    LoadingScreen,
    OovWidget,
    SpeakerWidget,
    TitleScreen,
    TranscriberWidget,
    UtteranceDetailWidget,
    UtteranceListWidget,
)


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1448, 974)
        icon = QIcon()
        icon.addFile(":/anchor-yellow.svg", QSize(), QIcon.Normal, QIcon.Off)
        MainWindow.setWindowIcon(icon)
        MainWindow.setStyleSheet("")
        MainWindow.setAnimated(True)
        MainWindow.setDocumentMode(False)
        MainWindow.setDockOptions(
            QMainWindow.AllowTabbedDocks
            | QMainWindow.AnimatedDocks
            | QMainWindow.ForceTabbedDocks
            | QMainWindow.VerticalTabs
        )
        self.loadCorpusAct = QAction(MainWindow)
        self.loadCorpusAct.setObjectName("loadCorpusAct")
        self.closeCurrentCorpusAct = QAction(MainWindow)
        self.closeCurrentCorpusAct.setObjectName("closeCurrentCorpusAct")
        self.closeCurrentCorpusAct.setEnabled(False)
        self.changeTemporaryDirectoryAct = QAction(MainWindow)
        self.changeTemporaryDirectoryAct.setObjectName("changeTemporaryDirectoryAct")
        self.openPreferencesAct = QAction(MainWindow)
        self.openPreferencesAct.setObjectName("openPreferencesAct")
        self.loadDictionaryAct = QAction(MainWindow)
        self.loadDictionaryAct.setObjectName("loadDictionaryAct")
        self.loadAcousticModelAct = QAction(MainWindow)
        self.loadAcousticModelAct.setObjectName("loadAcousticModelAct")
        self.loadG2PModelAct = QAction(MainWindow)
        self.loadG2PModelAct.setObjectName("loadG2PModelAct")
        self.playAct = QAction(MainWindow)
        self.playAct.setObjectName("playAct")
        self.playAct.setCheckable(True)
        self.playAct.setEnabled(False)
        icon1 = QIcon(QIcon.fromTheme("media-playback-start"))
        self.playAct.setIcon(icon1)
        self.playAct.setAutoRepeat(False)
        self.muteAct = QAction(MainWindow)
        self.muteAct.setObjectName("muteAct")
        self.muteAct.setCheckable(True)
        self.muteAct.setEnabled(False)
        icon2 = QIcon(QIcon.fromTheme("audio-volume-muted"))
        self.muteAct.setIcon(icon2)
        self.zoomInAct = QAction(MainWindow)
        self.zoomInAct.setObjectName("zoomInAct")
        self.zoomInAct.setEnabled(False)
        icon3 = QIcon(QIcon.fromTheme("zoom-in"))
        self.zoomInAct.setIcon(icon3)
        self.zoomOutAct = QAction(MainWindow)
        self.zoomOutAct.setObjectName("zoomOutAct")
        self.zoomOutAct.setEnabled(False)
        icon4 = QIcon(QIcon.fromTheme("zoom-out"))
        self.zoomOutAct.setIcon(icon4)
        self.mergeUtterancesAct = QAction(MainWindow)
        self.mergeUtterancesAct.setObjectName("mergeUtterancesAct")
        self.mergeUtterancesAct.setEnabled(False)
        icon5 = QIcon(QIcon.fromTheme("format-justify-center"))
        self.mergeUtterancesAct.setIcon(icon5)
        self.splitUtterancesAct = QAction(MainWindow)
        self.splitUtterancesAct.setObjectName("splitUtterancesAct")
        self.splitUtterancesAct.setEnabled(False)
        icon6 = QIcon(QIcon.fromTheme("format-justify-fill"))
        self.splitUtterancesAct.setIcon(icon6)
        self.deleteUtterancesAct = QAction(MainWindow)
        self.deleteUtterancesAct.setObjectName("deleteUtterancesAct")
        self.deleteUtterancesAct.setEnabled(False)
        icon7 = QIcon(QIcon.fromTheme("edit-delete"))
        self.deleteUtterancesAct.setIcon(icon7)
        self.revertDictionaryAct = QAction(MainWindow)
        self.revertDictionaryAct.setObjectName("revertDictionaryAct")
        self.revertDictionaryAct.setEnabled(False)
        icon8 = QIcon(QIcon.fromTheme("edit-book-undo"))
        self.revertDictionaryAct.setIcon(icon8)
        self.addSpeakerAct = QAction(MainWindow)
        self.addSpeakerAct.setObjectName("addSpeakerAct")
        self.addSpeakerAct.setEnabled(False)
        icon9 = QIcon(QIcon.fromTheme("contact-new"))
        self.addSpeakerAct.setIcon(icon9)
        self.getHelpAct = QAction(MainWindow)
        self.getHelpAct.setObjectName("getHelpAct")
        icon10 = QIcon(QIcon.fromTheme("help-about"))
        self.getHelpAct.setIcon(icon10)
        self.reportBugAct = QAction(MainWindow)
        self.reportBugAct.setObjectName("reportBugAct")
        icon11 = QIcon(QIcon.fromTheme("mail-forward"))
        self.reportBugAct.setIcon(icon11)
        self.exitAct = QAction(MainWindow)
        self.exitAct.setObjectName("exitAct")
        icon12 = QIcon(QIcon.fromTheme("process-stop"))
        self.exitAct.setIcon(icon12)
        self.cancelCorpusLoadAct = QAction(MainWindow)
        self.cancelCorpusLoadAct.setObjectName("cancelCorpusLoadAct")
        self.cancelCorpusLoadAct.setIcon(icon12)
        self.loadIvectorExtractorAct = QAction(MainWindow)
        self.loadIvectorExtractorAct.setObjectName("loadIvectorExtractorAct")
        self.loadLanguageModelAct = QAction(MainWindow)
        self.loadLanguageModelAct.setObjectName("loadLanguageModelAct")
        self.panLeftAct = QAction(MainWindow)
        self.panLeftAct.setObjectName("panLeftAct")
        self.panLeftAct.setEnabled(False)
        icon13 = QIcon(QIcon.fromTheme("media-seek-backward"))
        self.panLeftAct.setIcon(icon13)
        self.panRightAct = QAction(MainWindow)
        self.panRightAct.setObjectName("panRightAct")
        self.panRightAct.setEnabled(False)
        icon14 = QIcon(QIcon.fromTheme("media-seek-forward"))
        self.panRightAct.setIcon(icon14)
        self.searchAct = QAction(MainWindow)
        self.searchAct.setObjectName("searchAct")
        self.searchAct.setEnabled(False)
        icon15 = QIcon(QIcon.fromTheme("edit-find"))
        self.searchAct.setIcon(icon15)
        self.changeVolumeAct = QAction(MainWindow)
        self.changeVolumeAct.setObjectName("changeVolumeAct")
        self.changeSpeakerAct = QAction(MainWindow)
        self.changeSpeakerAct.setObjectName("changeSpeakerAct")
        self.changeSpeakerAct.setEnabled(False)
        self.saveDictionaryAct = QAction(MainWindow)
        self.saveDictionaryAct.setObjectName("saveDictionaryAct")
        self.saveDictionaryAct.setEnabled(False)
        icon16 = QIcon(QIcon.fromTheme("edit-book-save"))
        self.saveDictionaryAct.setIcon(icon16)
        self.closeDictionaryAct = QAction(MainWindow)
        self.closeDictionaryAct.setObjectName("closeDictionaryAct")
        self.closeDictionaryAct.setEnabled(False)
        self.closeAcousticModelAct = QAction(MainWindow)
        self.closeAcousticModelAct.setObjectName("closeAcousticModelAct")
        self.closeAcousticModelAct.setEnabled(False)
        self.closeG2PAct = QAction(MainWindow)
        self.closeG2PAct.setObjectName("closeG2PAct")
        self.closeG2PAct.setEnabled(False)
        self.closeIvectorExtractorAct = QAction(MainWindow)
        self.closeIvectorExtractorAct.setObjectName("closeIvectorExtractorAct")
        self.closeIvectorExtractorAct.setEnabled(False)
        self.closeLanguageModelAct = QAction(MainWindow)
        self.closeLanguageModelAct.setObjectName("closeLanguageModelAct")
        self.closeLanguageModelAct.setEnabled(False)
        self.transcribeCorpusAct = QAction(MainWindow)
        self.transcribeCorpusAct.setObjectName("transcribeCorpusAct")
        self.transcribeCorpusAct.setEnabled(False)
        self.alignCorpusAct = QAction(MainWindow)
        self.alignCorpusAct.setObjectName("alignCorpusAct")
        self.loadReferenceAlignmentsAct = QAction(MainWindow)
        self.loadReferenceAlignmentsAct.setObjectName("loadReferenceAlignmentsAct")
        self.selectMappingFileAct = QAction(MainWindow)
        self.selectMappingFileAct.setObjectName("selectMappingFileAct")
        self.evaluateAlignmentsAct = QAction(MainWindow)
        self.evaluateAlignmentsAct.setObjectName("evaluateAlignmentsAct")
        self.exportFilesAct = QAction(MainWindow)
        self.exportFilesAct.setObjectName("exportFilesAct")
        self.exportFilesAct.setEnabled(False)
        icon17 = QIcon(QIcon.fromTheme("document-save"))
        self.exportFilesAct.setIcon(icon17)
        self.lockEditAct = QAction(MainWindow)
        self.lockEditAct.setObjectName("lockEditAct")
        self.lockEditAct.setCheckable(True)
        self.lockEditAct.setEnabled(False)
        icon18 = QIcon(QIcon.fromTheme("edit-lock"))
        self.lockEditAct.setIcon(icon18)
        self.alignUtteranceAct = QAction(MainWindow)
        self.alignUtteranceAct.setObjectName("alignUtteranceAct")
        self.alignUtteranceAct.setEnabled(False)
        icon19 = QIcon(QIcon.fromTheme("edit-magic"))
        self.alignUtteranceAct.setIcon(icon19)
        self.trimUtteranceAct = QAction(MainWindow)
        self.trimUtteranceAct.setObjectName("trimUtteranceAct")
        self.trimUtteranceAct.setEnabled(False)
        icon20 = QIcon(QIcon.fromTheme("edit-scissors"))
        self.trimUtteranceAct.setIcon(icon20)
        self.reloadCorpusAct = QAction(MainWindow)
        self.reloadCorpusAct.setObjectName("reloadCorpusAct")
        self.zoomToSelectionAct = QAction(MainWindow)
        self.zoomToSelectionAct.setObjectName("zoomToSelectionAct")
        self.zoomToSelectionAct.setEnabled(False)
        icon21 = QIcon(QIcon.fromTheme("zoom-fit-best"))
        self.zoomToSelectionAct.setIcon(icon21)
        self.oovsOnlyAct = QAction(MainWindow)
        self.oovsOnlyAct.setObjectName("oovsOnlyAct")
        self.oovsOnlyAct.setCheckable(True)
        icon22 = QIcon(QIcon.fromTheme("tools-check-spelling"))
        self.oovsOnlyAct.setIcon(icon22)
        self.diarizeSpeakersAct = QAction(MainWindow)
        self.diarizeSpeakersAct.setObjectName("diarizeSpeakersAct")
        self.find_duplicates_action = QAction(MainWindow)
        self.find_duplicates_action.setObjectName("find_duplicates_action")
        self.cluster_utterances_action = QAction(MainWindow)
        self.cluster_utterances_action.setObjectName("cluster_utterances_action")
        self.classify_speakers_action = QAction(MainWindow)
        self.classify_speakers_action.setObjectName("classify_speakers_action")
        self.segmentUtteranceAct = QAction(MainWindow)
        self.segmentUtteranceAct.setObjectName("segmentUtteranceAct")
        self.segmentUtteranceAct.setIcon(icon6)
        self.openCorpusManagerAct = QAction(MainWindow)
        self.openCorpusManagerAct.setObjectName("openCorpusManagerAct")
        self.verifyTranscriptsAct = QAction(MainWindow)
        self.verifyTranscriptsAct.setObjectName("verifyTranscriptsAct")
        self.transcribeUtteranceAct = QAction(MainWindow)
        self.transcribeUtteranceAct.setObjectName("transcribeUtteranceAct")
        self.transcribeUtteranceAct.setEnabled(False)
        icon23 = QIcon(QIcon.fromTheme("edit-pen"))
        self.transcribeUtteranceAct.setIcon(icon23)
        self.actionLoad_VAD_model = QAction(MainWindow)
        self.actionLoad_VAD_model.setObjectName("actionLoad_VAD_model")
        self.speechbrainVadAct = QAction(MainWindow)
        self.speechbrainVadAct.setObjectName("speechbrainVadAct")
        self.speechbrainVadAct.setCheckable(True)
        self.speechbrainVadAct.setEnabled(False)
        self.kaldiVadAct = QAction(MainWindow)
        self.kaldiVadAct.setObjectName("kaldiVadAct")
        self.kaldiVadAct.setCheckable(True)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.verticalLayout_4 = QVBoxLayout(self.centralwidget)
        self.verticalLayout_4.setSpacing(0)
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.verticalLayout_4.setContentsMargins(0, 0, 0, 0)
        self.utteranceDetailWidget = UtteranceDetailWidget(self.centralwidget)
        self.utteranceDetailWidget.setObjectName("utteranceDetailWidget")

        self.verticalLayout_4.addWidget(self.utteranceDetailWidget)

        self.titleScreen = TitleScreen(self.centralwidget)
        self.titleScreen.setObjectName("titleScreen")

        self.verticalLayout_4.addWidget(self.titleScreen)

        self.loadingScreen = LoadingScreen(self.centralwidget)
        self.loadingScreen.setObjectName("loadingScreen")

        self.verticalLayout_4.addWidget(self.loadingScreen)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName("menubar")
        self.menubar.setGeometry(QRect(0, 0, 1448, 21))
        self.menuCorpus = QMenu(self.menubar)
        self.menuCorpus.setObjectName("menuCorpus")
        self.loadRecentCorpusMenu = QMenu(self.menuCorpus)
        self.loadRecentCorpusMenu.setObjectName("loadRecentCorpusMenu")
        self.menuEdit = QMenu(self.menubar)
        self.menuEdit.setObjectName("menuEdit")
        self.menuDictionary = QMenu(self.menubar)
        self.menuDictionary.setObjectName("menuDictionary")
        self.mfaDictionaryMenu = QMenu(self.menuDictionary)
        self.mfaDictionaryMenu.setObjectName("mfaDictionaryMenu")
        self.menuDownload_dictionary = QMenu(self.menuDictionary)
        self.menuDownload_dictionary.setObjectName("menuDownload_dictionary")
        self.menuWindow = QMenu(self.menubar)
        self.menuWindow.setObjectName("menuWindow")
        self.menuModels = QMenu(self.menubar)
        self.menuModels.setObjectName("menuModels")
        self.acousticModelMenu = QMenu(self.menuModels)
        self.acousticModelMenu.setObjectName("acousticModelMenu")
        self.g2pMenu = QMenu(self.menuModels)
        self.g2pMenu.setObjectName("g2pMenu")
        self.ivectorExtractorMenu = QMenu(self.menuModels)
        self.ivectorExtractorMenu.setObjectName("ivectorExtractorMenu")
        self.languageModelMenu = QMenu(self.menuModels)
        self.languageModelMenu.setObjectName("languageModelMenu")
        self.menuDownload_acoustic_model = QMenu(self.menuModels)
        self.menuDownload_acoustic_model.setObjectName("menuDownload_acoustic_model")
        self.menuDownload_ivector_extractor = QMenu(self.menuModels)
        self.menuDownload_ivector_extractor.setObjectName("menuDownload_ivector_extractor")
        self.menuDownload_language_model = QMenu(self.menuModels)
        self.menuDownload_language_model.setObjectName("menuDownload_language_model")
        self.menuDownload_G2P_model = QMenu(self.menuModels)
        self.menuDownload_G2P_model.setObjectName("menuDownload_G2P_model")
        self.vadModelMenu = QMenu(self.menuModels)
        self.vadModelMenu.setObjectName("vadModelMenu")
        self.menuAlignment = QMenu(self.menubar)
        self.menuAlignment.setObjectName("menuAlignment")
        self.menuTranscription = QMenu(self.menubar)
        self.menuTranscription.setObjectName("menuTranscription")
        self.menuExperimental = QMenu(self.menubar)
        self.menuExperimental.setObjectName("menuExperimental")
        self.menuLanguage = QMenu(self.menubar)
        self.menuLanguage.setObjectName("menuLanguage")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)
        self.utteranceDockWidget = QDockWidget(MainWindow)
        self.utteranceDockWidget.setObjectName("utteranceDockWidget")
        self.utteranceDockWidget.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetMovable
        )
        self.utteranceListWidget = UtteranceListWidget()
        self.utteranceListWidget.setObjectName("utteranceListWidget")
        self.utteranceDockWidget.setWidget(self.utteranceListWidget)
        MainWindow.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.utteranceDockWidget)
        self.dictionaryDockWidget = QDockWidget(MainWindow)
        self.dictionaryDockWidget.setObjectName("dictionaryDockWidget")
        self.dictionaryWidget = DictionaryWidget()
        self.dictionaryWidget.setObjectName("dictionaryWidget")
        self.dictionaryDockWidget.setWidget(self.dictionaryWidget)
        MainWindow.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dictionaryDockWidget)
        self.speakerDockWidget = QDockWidget(MainWindow)
        self.speakerDockWidget.setObjectName("speakerDockWidget")
        self.speakerWidget = SpeakerWidget()
        self.speakerWidget.setObjectName("speakerWidget")
        self.speakerDockWidget.setWidget(self.speakerWidget)
        MainWindow.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.speakerDockWidget)
        self.toolBar = QToolBar(MainWindow)
        self.toolBar.setObjectName("toolBar")
        self.toolBar.setEnabled(True)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.toolBar.sizePolicy().hasHeightForWidth())
        self.toolBar.setSizePolicy(sizePolicy)
        self.toolBar.setAcceptDrops(False)
        self.toolBar.setMovable(False)
        self.toolBar.setAllowedAreas(Qt.BottomToolBarArea)
        self.toolBar.setIconSize(QSize(25, 25))
        self.toolBar.setFloatable(False)
        MainWindow.addToolBar(Qt.ToolBarArea.BottomToolBarArea, self.toolBar)
        self.acousticModelDockWidget = QDockWidget(MainWindow)
        self.acousticModelDockWidget.setObjectName("acousticModelDockWidget")
        self.acousticModelWidget = AcousticModelWidget()
        self.acousticModelWidget.setObjectName("acousticModelWidget")
        self.acousticModelDockWidget.setWidget(self.acousticModelWidget)
        MainWindow.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea, self.acousticModelDockWidget
        )
        self.languageModelDockWidget = QDockWidget(MainWindow)
        self.languageModelDockWidget.setObjectName("languageModelDockWidget")
        self.languageModelWidget = LanguageModelWidget()
        self.languageModelWidget.setObjectName("languageModelWidget")
        self.languageModelDockWidget.setWidget(self.languageModelWidget)
        MainWindow.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea, self.languageModelDockWidget
        )
        self.transcriptionDockWidget = QDockWidget(MainWindow)
        self.transcriptionDockWidget.setObjectName("transcriptionDockWidget")
        self.transcriptionWidget = TranscriberWidget()
        self.transcriptionWidget.setObjectName("transcriptionWidget")
        self.transcriptionDockWidget.setWidget(self.transcriptionWidget)
        MainWindow.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea, self.transcriptionDockWidget
        )
        self.alignmentDockWidget = QDockWidget(MainWindow)
        self.alignmentDockWidget.setObjectName("alignmentDockWidget")
        self.alignmentDockWidget.setEnabled(True)
        self.alignmentDockWidget.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.alignmentWidget = AlignmentWidget()
        self.alignmentWidget.setObjectName("alignmentWidget")
        self.alignmentDockWidget.setWidget(self.alignmentWidget)
        MainWindow.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.alignmentDockWidget)
        self.oovDockWidget = QDockWidget(MainWindow)
        self.oovDockWidget.setObjectName("oovDockWidget")
        self.oovWidget = OovWidget()
        self.oovWidget.setObjectName("oovWidget")
        self.oovDockWidget.setWidget(self.oovWidget)
        MainWindow.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.oovDockWidget)
        self.diarizationDockWidget = QDockWidget(MainWindow)
        self.diarizationDockWidget.setObjectName("diarizationDockWidget")
        self.diarizationWidget = DiarizationWidget()
        self.diarizationWidget.setObjectName("diarizationWidget")
        self.diarizationDockWidget.setWidget(self.diarizationWidget)
        MainWindow.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.diarizationDockWidget)
        self.alignmentAnalysisDockWidget = QDockWidget(MainWindow)
        self.alignmentAnalysisDockWidget.setObjectName("alignmentAnalysisDockWidget")
        self.alignmentAnalysisWidget = AlignmentAnalysisWidget()
        self.alignmentAnalysisWidget.setObjectName("alignmentAnalysisWidget")
        self.alignmentAnalysisDockWidget.setWidget(self.alignmentAnalysisWidget)
        MainWindow.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea, self.alignmentAnalysisDockWidget
        )

        self.menubar.addAction(self.menuCorpus.menuAction())
        self.menubar.addAction(self.menuEdit.menuAction())
        self.menubar.addAction(self.menuDictionary.menuAction())
        self.menubar.addAction(self.menuModels.menuAction())
        self.menubar.addAction(self.menuAlignment.menuAction())
        self.menubar.addAction(self.menuTranscription.menuAction())
        self.menubar.addAction(self.menuExperimental.menuAction())
        self.menubar.addAction(self.menuWindow.menuAction())
        self.menubar.addAction(self.menuLanguage.menuAction())
        self.menuCorpus.addAction(self.loadCorpusAct)
        self.menuCorpus.addAction(self.loadRecentCorpusMenu.menuAction())
        self.menuCorpus.addAction(self.openCorpusManagerAct)
        self.menuCorpus.addSeparator()
        self.menuCorpus.addAction(self.reloadCorpusAct)
        self.menuCorpus.addAction(self.exportFilesAct)
        self.menuCorpus.addSeparator()
        self.menuCorpus.addAction(self.closeCurrentCorpusAct)
        self.menuCorpus.addSeparator()
        self.menuCorpus.addSeparator()
        self.menuCorpus.addAction(self.exitAct)
        self.menuCorpus.addSeparator()
        self.loadRecentCorpusMenu.addSeparator()
        self.menuEdit.addAction(self.changeTemporaryDirectoryAct)
        self.menuEdit.addAction(self.openPreferencesAct)
        self.menuEdit.addSeparator()
        self.menuEdit.addAction(self.lockEditAct)
        self.menuDictionary.addAction(self.loadDictionaryAct)
        self.menuDictionary.addAction(self.mfaDictionaryMenu.menuAction())
        self.menuDictionary.addAction(self.menuDownload_dictionary.menuAction())
        self.menuDictionary.addSeparator()
        self.menuDictionary.addAction(self.saveDictionaryAct)
        self.menuDictionary.addAction(self.revertDictionaryAct)
        self.menuDictionary.addAction(self.closeDictionaryAct)
        self.mfaDictionaryMenu.addSeparator()
        self.menuDownload_dictionary.addSeparator()
        self.menuModels.addAction(self.acousticModelMenu.menuAction())
        self.menuModels.addAction(self.menuDownload_acoustic_model.menuAction())
        self.menuModels.addAction(self.closeAcousticModelAct)
        self.menuModels.addSeparator()
        self.menuModels.addAction(self.g2pMenu.menuAction())
        self.menuModels.addAction(self.menuDownload_G2P_model.menuAction())
        self.menuModels.addAction(self.closeG2PAct)
        self.menuModels.addSeparator()
        self.menuModels.addAction(self.languageModelMenu.menuAction())
        self.menuModels.addAction(self.menuDownload_language_model.menuAction())
        self.menuModels.addAction(self.closeLanguageModelAct)
        self.menuModels.addSeparator()
        self.menuModels.addAction(self.ivectorExtractorMenu.menuAction())
        self.menuModels.addAction(self.menuDownload_ivector_extractor.menuAction())
        self.menuModels.addAction(self.closeIvectorExtractorAct)
        self.menuModels.addSeparator()
        self.menuModels.addAction(self.vadModelMenu.menuAction())
        self.acousticModelMenu.addAction(self.loadAcousticModelAct)
        self.acousticModelMenu.addSeparator()
        self.g2pMenu.addAction(self.loadG2PModelAct)
        self.g2pMenu.addSeparator()
        self.ivectorExtractorMenu.addAction(self.loadIvectorExtractorAct)
        self.ivectorExtractorMenu.addSeparator()
        self.languageModelMenu.addAction(self.loadLanguageModelAct)
        self.languageModelMenu.addSeparator()
        self.menuDownload_acoustic_model.addSeparator()
        self.menuDownload_ivector_extractor.addSeparator()
        self.menuDownload_language_model.addSeparator()
        self.menuDownload_G2P_model.addSeparator()
        self.vadModelMenu.addAction(self.speechbrainVadAct)
        self.vadModelMenu.addAction(self.kaldiVadAct)
        self.menuAlignment.addAction(self.loadReferenceAlignmentsAct)
        self.menuAlignment.addAction(self.selectMappingFileAct)
        self.menuAlignment.addAction(self.evaluateAlignmentsAct)
        self.menuTranscription.addAction(self.transcribeCorpusAct)
        self.menuExperimental.addAction(self.find_duplicates_action)
        self.menuExperimental.addAction(self.cluster_utterances_action)
        self.menuExperimental.addAction(self.classify_speakers_action)
        self.toolBar.addAction(self.playAct)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.zoomInAct)
        self.toolBar.addAction(self.zoomOutAct)
        self.toolBar.addAction(self.zoomToSelectionAct)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.mergeUtterancesAct)
        self.toolBar.addAction(self.splitUtterancesAct)
        self.toolBar.addAction(self.deleteUtterancesAct)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.alignUtteranceAct)
        self.toolBar.addAction(self.transcribeUtteranceAct)
        self.toolBar.addAction(self.trimUtteranceAct)
        self.toolBar.addAction(self.segmentUtteranceAct)
        self.toolBar.addAction(self.lockEditAct)
        self.toolBar.addAction(self.exportFilesAct)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.getHelpAct)
        self.toolBar.addAction(self.reportBugAct)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.muteAct)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)

    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", "MFA Anchor", None))
        self.loadCorpusAct.setText(QCoreApplication.translate("MainWindow", "Load a corpus", None))
        self.closeCurrentCorpusAct.setText(
            QCoreApplication.translate("MainWindow", "Close current corpus", None)
        )
        self.changeTemporaryDirectoryAct.setText(
            QCoreApplication.translate("MainWindow", "Change temporary directory", None)
        )
        self.openPreferencesAct.setText(
            QCoreApplication.translate("MainWindow", "Preferences...", None)
        )
        self.loadDictionaryAct.setText(
            QCoreApplication.translate("MainWindow", "Choose a dictionary...", None)
        )
        self.loadAcousticModelAct.setText(
            QCoreApplication.translate("MainWindow", "Choose a model...", None)
        )
        self.loadG2PModelAct.setText(
            QCoreApplication.translate("MainWindow", "Choose a model...", None)
        )
        self.playAct.setText(QCoreApplication.translate("MainWindow", "Play", None))
        self.muteAct.setText(QCoreApplication.translate("MainWindow", "Mute", None))
        self.zoomInAct.setText(QCoreApplication.translate("MainWindow", "Zoom in", None))
        # if QT_CONFIG(shortcut)
        self.zoomInAct.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+I", None))
        # endif // QT_CONFIG(shortcut)
        self.zoomOutAct.setText(QCoreApplication.translate("MainWindow", "Zoom out", None))
        # if QT_CONFIG(shortcut)
        self.zoomOutAct.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+O", None))
        # endif // QT_CONFIG(shortcut)
        self.mergeUtterancesAct.setText(
            QCoreApplication.translate("MainWindow", "Merge utterances", None)
        )
        # if QT_CONFIG(shortcut)
        self.mergeUtterancesAct.setShortcut(
            QCoreApplication.translate("MainWindow", "Ctrl+M", None)
        )
        # endif // QT_CONFIG(shortcut)
        self.splitUtterancesAct.setText(
            QCoreApplication.translate("MainWindow", "Split utterances", None)
        )
        self.deleteUtterancesAct.setText(
            QCoreApplication.translate("MainWindow", "Delete utterance", None)
        )
        # if QT_CONFIG(shortcut)
        self.deleteUtterancesAct.setShortcut(QCoreApplication.translate("MainWindow", "Del", None))
        # endif // QT_CONFIG(shortcut)
        self.revertDictionaryAct.setText(
            QCoreApplication.translate("MainWindow", "Revert dictionary changes", None)
        )
        self.addSpeakerAct.setText(
            QCoreApplication.translate("MainWindow", "Add new speaker", None)
        )
        self.getHelpAct.setText(QCoreApplication.translate("MainWindow", "Help", None))
        self.reportBugAct.setText(QCoreApplication.translate("MainWindow", "Report bug", None))
        self.exitAct.setText(QCoreApplication.translate("MainWindow", "Exit", None))
        self.cancelCorpusLoadAct.setText(
            QCoreApplication.translate("MainWindow", "Cancel loading corpus", None)
        )
        self.loadIvectorExtractorAct.setText(
            QCoreApplication.translate("MainWindow", "Choose a model...", None)
        )
        self.loadLanguageModelAct.setText(
            QCoreApplication.translate("MainWindow", "Choose a model...", None)
        )
        self.panLeftAct.setText(QCoreApplication.translate("MainWindow", "Pan left", None))
        self.panRightAct.setText(QCoreApplication.translate("MainWindow", "Pan right", None))
        self.searchAct.setText(QCoreApplication.translate("MainWindow", "Search corpus", None))
        self.changeVolumeAct.setText(
            QCoreApplication.translate("MainWindow", "Change volume", None)
        )
        self.changeSpeakerAct.setText(
            QCoreApplication.translate("MainWindow", "Change speaker", None)
        )
        self.saveDictionaryAct.setText(
            QCoreApplication.translate("MainWindow", "Save dictionary", None)
        )
        self.closeDictionaryAct.setText(
            QCoreApplication.translate("MainWindow", "Close dictionary", None)
        )
        self.closeAcousticModelAct.setText(
            QCoreApplication.translate("MainWindow", "Close acoustic model", None)
        )
        self.closeG2PAct.setText(QCoreApplication.translate("MainWindow", "Close G2P model", None))
        self.closeIvectorExtractorAct.setText(
            QCoreApplication.translate("MainWindow", "Close ivector extractor", None)
        )
        self.closeLanguageModelAct.setText(
            QCoreApplication.translate("MainWindow", "Close language model", None)
        )
        self.transcribeCorpusAct.setText(
            QCoreApplication.translate("MainWindow", "Transcribe corpus", None)
        )
        self.alignCorpusAct.setText(QCoreApplication.translate("MainWindow", "Align corpus", None))
        self.loadReferenceAlignmentsAct.setText(
            QCoreApplication.translate("MainWindow", "Load reference alignments", None)
        )
        self.selectMappingFileAct.setText(
            QCoreApplication.translate("MainWindow", "Select custom mapping file", None)
        )
        self.evaluateAlignmentsAct.setText(
            QCoreApplication.translate("MainWindow", "Evaluate alignments", None)
        )
        self.exportFilesAct.setText(
            QCoreApplication.translate("MainWindow", "Export changes", None)
        )
        # if QT_CONFIG(tooltip)
        self.exportFilesAct.setToolTip(
            QCoreApplication.translate("MainWindow", "Export changes to original files", None)
        )
        # endif // QT_CONFIG(tooltip)
        self.lockEditAct.setText(QCoreApplication.translate("MainWindow", "Lock editing", None))
        self.alignUtteranceAct.setText(
            QCoreApplication.translate("MainWindow", "Align utterance", None)
        )
        # if QT_CONFIG(tooltip)
        self.alignUtteranceAct.setToolTip(
            QCoreApplication.translate("MainWindow", "Align the current utterance", None)
        )
        # endif // QT_CONFIG(tooltip)
        self.trimUtteranceAct.setText(
            QCoreApplication.translate("MainWindow", "Trim utterance", None)
        )
        # if QT_CONFIG(tooltip)
        self.trimUtteranceAct.setToolTip(
            QCoreApplication.translate("MainWindow", "Trim the current utterance", None)
        )
        # endif // QT_CONFIG(tooltip)
        self.reloadCorpusAct.setText(
            QCoreApplication.translate("MainWindow", "Reload corpus text from disk", None)
        )
        self.zoomToSelectionAct.setText(
            QCoreApplication.translate("MainWindow", "Zoom to selection", None)
        )
        self.oovsOnlyAct.setText(QCoreApplication.translate("MainWindow", "OOVs Only", None))
        self.diarizeSpeakersAct.setText(
            QCoreApplication.translate("MainWindow", "Calculate ivectors", None)
        )
        self.find_duplicates_action.setText(
            QCoreApplication.translate("MainWindow", "Find duplicate utterances", None)
        )
        self.cluster_utterances_action.setText(
            QCoreApplication.translate("MainWindow", "Cluster utterances", None)
        )
        self.classify_speakers_action.setText(
            QCoreApplication.translate("MainWindow", "Classify speakers", None)
        )
        self.segmentUtteranceAct.setText(
            QCoreApplication.translate("MainWindow", "Segment utterance", None)
        )
        # if QT_CONFIG(tooltip)
        self.segmentUtteranceAct.setToolTip(
            QCoreApplication.translate(
                "MainWindow", "Split an utterance into VAD-based segments", None
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.openCorpusManagerAct.setText(
            QCoreApplication.translate("MainWindow", "Manage corpora...", None)
        )
        # if QT_CONFIG(tooltip)
        self.openCorpusManagerAct.setToolTip(
            QCoreApplication.translate("MainWindow", "Manage corpora and models", None)
        )
        # endif // QT_CONFIG(tooltip)
        self.verifyTranscriptsAct.setText(
            QCoreApplication.translate("MainWindow", "Verify transcripts", None)
        )
        # if QT_CONFIG(tooltip)
        self.verifyTranscriptsAct.setToolTip(
            QCoreApplication.translate("MainWindow", "Verify transcripts", None)
        )
        # endif // QT_CONFIG(tooltip)
        self.transcribeUtteranceAct.setText(
            QCoreApplication.translate("MainWindow", "Transcribe utterance", None)
        )
        # if QT_CONFIG(tooltip)
        self.transcribeUtteranceAct.setToolTip(
            QCoreApplication.translate("MainWindow", "Transcribe the current utterance", None)
        )
        # endif // QT_CONFIG(tooltip)
        self.actionLoad_VAD_model.setText(
            QCoreApplication.translate("MainWindow", "Load VAD model", None)
        )
        self.speechbrainVadAct.setText(
            QCoreApplication.translate("MainWindow", "speechbrain", None)
        )
        self.kaldiVadAct.setText(QCoreApplication.translate("MainWindow", "kaldi", None))
        self.menuCorpus.setTitle(QCoreApplication.translate("MainWindow", "Corpus", None))
        self.loadRecentCorpusMenu.setTitle(
            QCoreApplication.translate("MainWindow", "Load a recent corpus", None)
        )
        self.menuEdit.setTitle(QCoreApplication.translate("MainWindow", "Edit", None))
        self.menuDictionary.setTitle(QCoreApplication.translate("MainWindow", "Dictionary", None))
        self.mfaDictionaryMenu.setTitle(
            QCoreApplication.translate("MainWindow", "Load a saved dictionary", None)
        )
        self.menuDownload_dictionary.setTitle(
            QCoreApplication.translate("MainWindow", "Download dictionary", None)
        )
        self.menuWindow.setTitle(QCoreApplication.translate("MainWindow", "Window", None))
        self.menuModels.setTitle(QCoreApplication.translate("MainWindow", "Models", None))
        self.acousticModelMenu.setTitle(
            QCoreApplication.translate("MainWindow", "Load acoustic model", None)
        )
        self.g2pMenu.setTitle(QCoreApplication.translate("MainWindow", "Load G2P model", None))
        self.ivectorExtractorMenu.setTitle(
            QCoreApplication.translate("MainWindow", "Load ivector extractor", None)
        )
        self.languageModelMenu.setTitle(
            QCoreApplication.translate("MainWindow", "Load language model", None)
        )
        self.menuDownload_acoustic_model.setTitle(
            QCoreApplication.translate("MainWindow", "Download acoustic model", None)
        )
        self.menuDownload_ivector_extractor.setTitle(
            QCoreApplication.translate("MainWindow", "Download ivector extractor", None)
        )
        self.menuDownload_language_model.setTitle(
            QCoreApplication.translate("MainWindow", "Download language model", None)
        )
        self.menuDownload_G2P_model.setTitle(
            QCoreApplication.translate("MainWindow", "Download G2P model", None)
        )
        self.vadModelMenu.setTitle(
            QCoreApplication.translate("MainWindow", "Load VAD model", None)
        )
        self.menuAlignment.setTitle(QCoreApplication.translate("MainWindow", "Alignment", None))
        self.menuTranscription.setTitle(
            QCoreApplication.translate("MainWindow", "Transcription", None)
        )
        self.menuExperimental.setTitle(
            QCoreApplication.translate("MainWindow", "Experimental", None)
        )
        self.menuLanguage.setTitle(QCoreApplication.translate("MainWindow", "Language", None))
        self.utteranceDockWidget.setWindowTitle(
            QCoreApplication.translate("MainWindow", "Utterances", None)
        )
        self.dictionaryDockWidget.setWindowTitle(
            QCoreApplication.translate("MainWindow", "Dictionary", None)
        )
        self.speakerDockWidget.setWindowTitle(
            QCoreApplication.translate("MainWindow", "Speakers", None)
        )
        self.toolBar.setWindowTitle(QCoreApplication.translate("MainWindow", "toolBar", None))
        self.acousticModelDockWidget.setWindowTitle(
            QCoreApplication.translate("MainWindow", "Acoustic model", None)
        )
        self.languageModelDockWidget.setWindowTitle(
            QCoreApplication.translate("MainWindow", "Language model", None)
        )
        self.transcriptionDockWidget.setWindowTitle(
            QCoreApplication.translate("MainWindow", "Transcription", None)
        )
        self.alignmentDockWidget.setWindowTitle(
            QCoreApplication.translate("MainWindow", "Alignment", None)
        )
        self.oovDockWidget.setWindowTitle(QCoreApplication.translate("MainWindow", "OOVs", None))
        self.diarizationDockWidget.setWindowTitle(
            QCoreApplication.translate("MainWindow", "Diarization", None)
        )
        self.alignmentAnalysisDockWidget.setWindowTitle(
            QCoreApplication.translate("MainWindow", "Alignment analysis", None)
        )

    # retranslateUi
