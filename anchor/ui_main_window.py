# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_window.ui'
##
## Created by: Qt User Interface Compiler version 6.2.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QDockWidget, QMainWindow, QMenu,
    QMenuBar, QSizePolicy, QStatusBar, QToolBar,
    QVBoxLayout, QWidget)

from anchor.widgets import (AcousticModelWidget, AlignmentWidget, DiarizationWidget, DictionaryWidget,
    LanguageModelWidget, LoadingScreen, OovWidget, SpeakerWidget,
    TitleScreen, TranscriberWidget, UtteranceDetailWidget, UtteranceListWidget)
import resources_rc

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1448, 974)
        icon = QIcon()
        icon.addFile(u":/anchor-yellow.svg", QSize(), QIcon.Normal, QIcon.Off)
        MainWindow.setWindowIcon(icon)
        MainWindow.setStyleSheet(u"QMainWindow, QDialog{\n"
"            background-color: rgb(0, 53, 102);\n"
"        }\n"
"        QMenuBar {\n"
"            background-color: rgb(255, 195, 0);\n"
"            spacing: 2px;\n"
"        }\n"
"        QMenuBar::item {\n"
"            padding: 4px 4px;\n"
"                        color: rgb(0, 8, 20);\n"
"                        background-color: rgb(255, 195, 0);\n"
"        }\n"
"        QMenuBar::item:selected {\n"
"                        color: rgb(255, 214, 10);\n"
"                        background-color: rgb(14, 99, 179);\n"
"        }\n"
"        QMenuBar::item:disabled {\n"
"                        color: rgb(198, 54, 35);\n"
"                        background-color: rgb(255, 195, 0);\n"
"                        }\n"
"        ButtonWidget {\n"
"            background-color: rgb(14, 99, 179);\n"
"        }\n"
"        QDockWidget {\n"
"            background-color: rgb(0, 29, 61);\n"
"            color: rgb(255, 214, 10);\n"
"            \n"
"            titlebar-close-icon: url(:che"
                        "cked/times.svg);\n"
"            titlebar-normal-icon: url(:checked/external-link.svg);\n"
"        }\n"
"        QDockWidget::title {\n"
"            text-align: center;\n"
"        }\n"
"        \n"
"        QMainWindow::separator {\n"
"    background: rgb(0, 53, 102);\n"
"    width: 10px; /* when vertical */\n"
"    height: 10px; /* when horizontal */\n"
"}\n"
"\n"
"QMainWindow::separator:hover {\n"
"    background: rgb(255, 195, 0);\n"
"}\n"
"        #utteranceListWidget, #dictionaryWidget, #speakerWidget {\n"
"            background-color: rgb(0, 8, 20);\n"
"        \n"
"            border: 2px solid rgb(14, 99, 179);\n"
"            color: rgb(14, 99, 179);\n"
"            padding: 0px;\n"
"            padding-top: 20px;\n"
"            margin-top: 0ex; /* leave space at the top for the title */\n"
"            }\n"
"            \n"
"        #utteranceDetailWidget {\n"
"            background-color: rgb(0, 53, 102);\n"
"            padding: 0px;\n"
"            border: none;\n"
"            margin: 0;\n"
""
                        "        }\n"
"        InformationWidget {\n"
"            background-color: rgb(0, 8, 20);\n"
"            border: 2px solid rgb(14, 99, 179);\n"
"            border-top-right-radius: 5px;\n"
"            border-bottom-right-radius: 5px;\n"
"                    \n"
"        }\n"
"        \n"
"        QGroupBox::title {\n"
"            color: rgb(237, 221, 212);\n"
"            background-color: transparent;\n"
"            subcontrol-origin: margin;\n"
"            subcontrol-position: top center; /* position at the top center */\n"
"            padding-top: 5px;\n"
"        }\n"
"        QLabel {\n"
"                        color: rgb(237, 221, 212);\n"
"            }\n"
"        QStatusBar {\n"
"            background-color: rgb(0, 8, 20);\n"
"                        color: rgb(237, 221, 212);\n"
"            }\n"
"        WarningLabel {\n"
"                        color: rgb(198, 54, 35);\n"
"            }\n"
"        QCheckBox {\n"
"            color: rgb(237, 221, 212);\n"
"        }\n"
"        QTabWidge"
                        "t::pane, SearchWidget, DictionaryWidget, SpeakerWidget { /* The tab widget frame */\n"
"            background-color: rgb(0, 8, 20);\n"
"        \n"
"        }\n"
"        QTabWidget::pane  { /* The tab widget frame */\n"
"            border: 2px solid rgb(14, 99, 179);\n"
"            border-top-color: rgb(0, 8, 20);\n"
"            background-color: rgb(0, 8, 20);\n"
"        \n"
"        }\n"
"            \n"
"            \n"
"        QTabBar::tab {\n"
"            color: rgb(0, 8, 20);\n"
"            background-color: rgb(255, 195, 0);\n"
"            border-color: rgb(0, 8, 20);\n"
"            border: 1px solid rgb(0, 8, 20);\n"
"            border-top-color: rgb(14, 99, 179);\n"
"            border-bottom: none;\n"
"            \n"
"            min-width: 8ex;\n"
"            padding: 5px;\n"
"            margin: 0px;\n"
"        }\n"
"            \n"
"        QTabBar::scroller{\n"
"            width: 50px;\n"
"        }\n"
"        QTabBar QToolButton  {\n"
"            border-radius: 0px;\n"
"       "
                        " }\n"
"        \n"
"        QTabBar QToolButton::right-arrow  {\n"
"            image: url(:caret-right.svg);\n"
"            height: 25px;\n"
"            width: 25px;\n"
"        }\n"
"        QTabBar QToolButton::right-arrow :pressed {\n"
"            image: url(:checked/caret-right.svg);\n"
"        }\n"
"        QTabBar QToolButton::right-arrow :disabled {\n"
"            image: url(:disabled/caret-right.svg);\n"
"        }\n"
"        \n"
"        QTabBar QToolButton::left-arrow  {\n"
"            image: url(:caret-left.svg);\n"
"            height: 25px;\n"
"            width: 25px;\n"
"        }\n"
"        QTabBar QToolButton::left-arrow:pressed {\n"
"            image: url(:checked/caret-left.svg);\n"
"        }\n"
"        QTabBar QToolButton::left-arrow:disabled {\n"
"            image: url(:disabled/caret-left.svg);\n"
"        }\n"
"        \n"
"        QTabBar::tab-bar {\n"
"            color: rgb(0, 8, 20);\n"
"            background-color: rgb(255, 195, 0);\n"
"            border: 2px solid rg"
                        "b(14, 99, 179);\n"
"        }\n"
"            \n"
"        QTabBar::tab:hover {\n"
"            color: rgb(255, 214, 10);\n"
"            background-color: rgb(14, 99, 179);\n"
"            border-bottom-color:  rgb(14, 99, 179);\n"
"        }\n"
"        QTabBar::tab:selected {\n"
"            color: rgb(255, 214, 10);\n"
"            background-color: rgb(0, 29, 61);\n"
"            margin-left: -2px;\n"
"            margin-right: -2px;\n"
"            border-color: rgb(14, 99, 179);\n"
"            border-bottom-color:  rgb(14, 99, 179);\n"
"        }\n"
"        QTabBar::tab:first {\n"
"            border-left-width: 2px;\n"
"            margin-left: 0px;\n"
"        }\n"
"        QTabBar::tab:last {\n"
"            border-right-width: 2px;\n"
"            margin-right: 0px;\n"
"        }\n"
"        QToolBar {\n"
"            spacing: 3px; \n"
"			border: none;s\n"
"        }\n"
"        #toolBar {\n"
"            background: rgb(0, 8, 20);\n"
"        }\n"
"            \n"
"        QToolBar::separator {\n"
""
                        "            margin-left: 5px;\n"
"            margin-right: 5px;\n"
"            width: 3px;\n"
"            height: 3px;\n"
"            background: rgb(14, 99, 179);\n"
"        }\n"
"            \n"
"        \n"
"            \n"
"        QPushButton, QToolButton {\n"
"            background-color: rgb(255, 195, 0);\n"
"            color: rgb(0, 8, 20);\n"
"            padding: 2px;\n"
"            border-width: 2px; \n"
"            border-style: solid; \n"
"            border-color: rgb(0, 8, 20);\n"
"            border-radius: 5px;\n"
"        }\n"
"        QToolButton[popupMode=\"1\"] { /* only for MenuButtonPopup */\n"
"            padding-right: 20px; /* make way for the popup button */\n"
"        }\n"
"        QToolButton::menu-button {\n"
"            border: 2px solid rgb(0, 8, 20);\n"
"            border-top-right-radius: 5px;\n"
"            border-bottom-right-radius: 5px;\n"
"            \n"
"            width: 16px;\n"
"        }\n"
"        QMenuBar QToolButton{\n"
"            padding: 0px;\n"
""
                        "        }\n"
"        QLineEdit QToolButton {\n"
"                        background-color: rgb(255, 195, 0);\n"
"                        color: rgb(237, 221, 212);\n"
"                        border: none;\n"
"        }\n"
"        QToolButton#clear_search_field, QToolButton#clear_new_speaker_field, \n"
"        QToolButton#regex_search_field, QToolButton#word_search_field {\n"
"                        background-color: none;\n"
"                        border: none;\n"
"                        padding: 2px;\n"
"        }\n"
"        QMenu {\n"
"                margin: 2px;\n"
"                background-color: rgb(255, 195, 0);\n"
"                color: rgb(0, 8, 20);\n"
"        }\n"
"        QMenu::item {\n"
"                padding: 2px 25px 2px 20px;\n"
"                border: 1px solid transparent;\n"
"                background-color: rgb(255, 195, 0);\n"
"                color: rgb(0, 8, 20);\n"
"        }\n"
"        QMenu::item:disabled {\n"
"                border: none;\n"
"                backg"
                        "round-color: rgb(0, 29, 61);\n"
"                color: rgb(198, 54, 35);\n"
"        }\n"
"        QMenu::item:!disabled:selected {\n"
"            border-color: rgb(0, 8, 20);\n"
"            background-color: rgb(14, 99, 179);\n"
"        }\n"
"        QComboBox {\n"
"            color: rgb(0, 8, 20);\n"
"            background-color: rgb(255, 195, 0);\n"
"            selection-background-color: none;\n"
"        }\n"
"        QComboBox QAbstractItemView {\n"
"            color: rgb(0, 8, 20);\n"
"            background-color: rgb(255, 195, 0);\n"
"            selection-background-color: rgb(14, 99, 179);\n"
"        }\n"
"        QToolButton:checked  {\n"
"            color: rgb(255, 214, 10);\n"
"            background-color: rgb(0, 29, 61);\n"
"            border-color: rgb(14, 99, 179);\n"
"        }\n"
"        QPushButton:disabled, QToolButton:disabled {\n"
"            color: rgb(198, 54, 35);\n"
"            background-color: rgb(160, 122, 0);\n"
"        }\n"
"        \n"
"        QToolButton#cance"
                        "l_load:disabled {\n"
"            color: rgb(198, 54, 35);\n"
"            background-color: rgb(0, 29, 61);\n"
"        }\n"
"        QPushButton:hover, QToolButton:hover, QToolButton:focus, QToolButton:pressed, ToolButton:hover {\n"
"            color: rgb(255, 214, 10);\n"
"            background-color: rgb(14, 99, 179);\n"
"        }\n"
"        \n"
"        QToolButton#cancel_load:focus:hover {\n"
"            color: rgb(255, 214, 10);\n"
"            background-color: rgb(14, 99, 179);\n"
"        }\n"
"        QPlainTextEdit {\n"
"            color: rgb(237, 221, 212);\n"
"            background-color: rgb(0, 8, 20);\n"
"            border: 2px solid rgb(14, 99, 179);\n"
"            selection-background-color: rgb(14, 99, 179);\n"
"        }\n"
"        QGraphicsView {\n"
"            border: 2px solid rgb(14, 99, 179);\n"
"        }\n"
"         QLineEdit {\n"
"            color: rgb(0, 8, 20);\n"
"            background-color: rgb(237, 221, 212);\n"
"            selection-background-color: rgb(14, 99"
                        ", 179);\n"
"        }\n"
"        QSlider::handle:horizontal {\n"
"            height: 10px;\n"
"            background: rgb(255, 195, 0);\n"
"            border: 1px solid rgb(0, 8, 20);\n"
"            margin: 0 -2px; /* expand outside the groove */\n"
"        }\n"
"        QSlider::handle:horizontal:hover {\n"
"            height: 10px;\n"
"            background: rgb(14, 99, 179);\n"
"            margin: 0 -2px; /* expand outside the groove */\n"
"        }\n"
"        QTableWidget, QTableView {\n"
"            alternate-background-color: rgb(242, 205, 73); \n"
"            selection-background-color: rgb(14, 99, 179);\n"
"            selection-color: rgb(237, 221, 212);\n"
"            background-color: rgb(122, 181, 230);\n"
"            color: rgb(0, 8, 20);\n"
"            border: 4px solid rgb(0, 8, 20);\n"
"        }\n"
"        QScrollArea {\n"
"            border: 4px solid rgb(0, 8, 20);\n"
"		background-color: rgb(0, 29, 61);\n"
"        }\n"
"        QHeaderView::up-arrow {\n"
"            subc"
                        "ontrol-origin: padding; \n"
"            subcontrol-position: center right;\n"
"            image: url(:hover/sort-up.svg);\n"
"            height: 20px;\n"
"            width: 20px;\n"
"        }\n"
"        QHeaderView::down-arrow {\n"
"            image: url(:hover/sort-down.svg);\n"
"            subcontrol-origin: padding; \n"
"            subcontrol-position: center right;\n"
"            height: 20px;\n"
"            width: 20px;\n"
"        }\n"
"        QTableView QTableCornerButton::section {\n"
"            background-color: rgb(255, 195, 0);\n"
"        }\n"
"        QHeaderView {\n"
"            background-color: rgb(122, 181, 230);\n"
"        }\n"
"        QHeaderView::section {\n"
"            color: rgb(237, 221, 212);\n"
"            background-color: rgb(14, 99, 179);\n"
"            padding-left: 5px;\n"
"        }\n"
"        QHeaderView::section:horizontal {\n"
"            padding-right: 15px;\n"
"        }\n"
"\n"
"        QScrollBar {\n"
"            color: rgb(255, 214, 10);\n"
"      "
                        "      background: rgb(0, 29, 61);\n"
"            border: 2px solid rgb(0, 8, 20);\n"
"        }\n"
"        QScrollBar#time_scroll_bar {\n"
"            color: rgb(255, 214, 10);\n"
"            background: rgb(0, 29, 61);\n"
"            border: 2px solid rgb(0, 8, 20);\n"
"            margin-left: 0px;\n"
"            margin-right: 0px;\n"
"        }\n"
"        QScrollBar:horizontal {\n"
"            height: 25px;\n"
"            border: 2px solid rgb(0, 8, 20);\n"
"            border-radius: 12px;\n"
"            margin-left: 25px;\n"
"            margin-right: 25px;\n"
"        }\n"
"        QScrollBar:vertical {\n"
"            width: 25px;\n"
"            border: 2px solid rgb(0, 8, 20);\n"
"            border-radius: 12px;\n"
"            margin-top: 25px;\n"
"            margin-bottom: 25px;\n"
"        }\n"
"        \n"
"        QScrollBar:left-arrow:horizontal {\n"
"            image: url(:caret-left.svg);\n"
"            height: 25px;\n"
"            width: 25px;\n"
"        }\n"
"\n"
"        QSc"
                        "rollBar:left-arrow:horizontal:pressed {\n"
"            image: url(:checked/caret-left.svg);\n"
"        }\n"
"        \n"
"        QScrollBar:right-arrow:horizontal {\n"
"            image: url(:caret-right.svg);\n"
"            height: 25px;\n"
"            width: 25px;\n"
"        }\n"
"\n"
"        QScrollBar:right-arrow:horizontal:pressed {\n"
"            image: url(:checked/caret-right.svg);\n"
"        }\n"
"        \n"
"        QScrollBar:up-arrow:vertical {\n"
"            image: url(:caret-up.svg);\n"
"            height: 25px;\n"
"            width: 25px;\n"
"        }\n"
"\n"
"        QScrollBar:up-arrow:vertical:pressed {\n"
"            image: url(:checked/caret-up.svg);\n"
"        }\n"
"        \n"
"        QScrollBar:down-arrow:vertical {\n"
"            image: url(:caret-down.svg);\n"
"            height: 25px;\n"
"            width: 25px;\n"
"        }\n"
"        QScrollBar:down-arrow:vertical:pressed {\n"
"            image: url(:checked/caret-down.svg);\n"
"        }\n"
"        \n"
"   "
                        "     QScrollBar::handle:horizontal {\n"
"            background: rgb(255, 214, 10);\n"
"            min-width: 25px;\n"
"            border: 2px solid rgb(0, 8, 20);\n"
"            border-radius: 10px;\n"
"        }\n"
"        \n"
"        QScrollBar::handle:vertical {\n"
"            background: rgb(255, 214, 10);\n"
"            min-height: 25px;\n"
"            border: 2px solid rgb(0, 8, 20);\n"
"            border-radius: 10px;\n"
"        }\n"
"        \n"
"        QToolButton#pan_left_button, QToolButton#pan_right_button {\n"
"            \n"
"            color: none;\n"
"            background-color: none;\n"
"            border: none;\n"
"            margin: 0px;\n"
"            padding: 0px;\n"
"        }\n"
"\n"
"        QScrollBar::add-page, QScrollBar::sub-page {\n"
"            background: none;\n"
"            height: 25px;\n"
"            width: 25px;\n"
"            padding: 0px;\n"
"            margin: 0px;\n"
"        }\n"
"        \n"
"        QScrollBar::add-line:horizontal {\n"
"       "
                        "     background: none;\n"
"            subcontrol-position: right;\n"
"            subcontrol-origin: margin;\n"
"            width: 25px;\n"
"        }\n"
"        \n"
"        QScrollBar::sub-line:horizontal {\n"
"            background: none;\n"
"            subcontrol-position: left;\n"
"            subcontrol-origin: margin;\n"
"            width: 25px;\n"
"        }\n"
"        \n"
"        QScrollBar::add-line:vertical {\n"
"            background: none;\n"
"            subcontrol-position: bottom;\n"
"            subcontrol-origin: margin;\n"
"            height: 25px;\n"
"        }\n"
"        \n"
"        QScrollBar::sub-line:vertical {\n"
"            background: none;\n"
"            subcontrol-position: top;\n"
"            subcontrol-origin: margin;\n"
"            height: 25px;\n"
"        }\n"
"        \n"
"        QScrollBar#time_scroll_bar::add-line:horizontal {\n"
"            background: none;\n"
"            subcontrol-position: none;\n"
"            subcontrol-origin: none;\n"
"          "
                        "  width: 0px;\n"
"        }\n"
"        \n"
"        QScrollBar#time_scroll_bar::sub-line:horizontal {\n"
"            background: none;\n"
"            subcontrol-position: none;\n"
"            subcontrol-origin: none;\n"
"            width: 0px;\n"
"        }")
        MainWindow.setAnimated(True)
        MainWindow.setDocumentMode(False)
        MainWindow.setDockOptions(QMainWindow.AllowTabbedDocks|QMainWindow.AnimatedDocks|QMainWindow.ForceTabbedDocks|QMainWindow.VerticalTabs)
        self.loadCorpusAct = QAction(MainWindow)
        self.loadCorpusAct.setObjectName(u"loadCorpusAct")
        self.closeCurrentCorpusAct = QAction(MainWindow)
        self.closeCurrentCorpusAct.setObjectName(u"closeCurrentCorpusAct")
        self.closeCurrentCorpusAct.setEnabled(False)
        self.changeTemporaryDirectoryAct = QAction(MainWindow)
        self.changeTemporaryDirectoryAct.setObjectName(u"changeTemporaryDirectoryAct")
        self.openPreferencesAct = QAction(MainWindow)
        self.openPreferencesAct.setObjectName(u"openPreferencesAct")
        self.loadDictionaryAct = QAction(MainWindow)
        self.loadDictionaryAct.setObjectName(u"loadDictionaryAct")
        self.loadAcousticModelAct = QAction(MainWindow)
        self.loadAcousticModelAct.setObjectName(u"loadAcousticModelAct")
        self.loadG2PModelAct = QAction(MainWindow)
        self.loadG2PModelAct.setObjectName(u"loadG2PModelAct")
        self.playAct = QAction(MainWindow)
        self.playAct.setObjectName(u"playAct")
        self.playAct.setCheckable(True)
        self.playAct.setEnabled(False)
        icon1 = QIcon()
        icon1.addFile(u":/play.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon1.addFile(u":/checked/pause.svg", QSize(), QIcon.Normal, QIcon.On)
        icon1.addFile(u":/play.svg", QSize(), QIcon.Disabled, QIcon.Off)
        icon1.addFile(u":/checked/play.svg", QSize(), QIcon.Active, QIcon.Off)
        icon1.addFile(u":/checked/pause.svg", QSize(), QIcon.Active, QIcon.On)
        icon1.addFile(u":/checked/play.svg", QSize(), QIcon.Selected, QIcon.Off)
        icon1.addFile(u":/checked/pause.svg", QSize(), QIcon.Selected, QIcon.On)
        self.playAct.setIcon(icon1)
        self.playAct.setAutoRepeat(False)
        self.muteAct = QAction(MainWindow)
        self.muteAct.setObjectName(u"muteAct")
        self.muteAct.setCheckable(True)
        self.muteAct.setEnabled(False)
        icon2 = QIcon()
        icon2.addFile(u":/volume-mute.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon2.addFile(u":/volume-mute.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.muteAct.setIcon(icon2)
        self.zoomInAct = QAction(MainWindow)
        self.zoomInAct.setObjectName(u"zoomInAct")
        self.zoomInAct.setEnabled(False)
        icon3 = QIcon()
        icon3.addFile(u":/magnifying-glass-plus.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon3.addFile(u":/magnifying-glass-plus.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.zoomInAct.setIcon(icon3)
        self.zoomOutAct = QAction(MainWindow)
        self.zoomOutAct.setObjectName(u"zoomOutAct")
        self.zoomOutAct.setEnabled(False)
        icon4 = QIcon()
        icon4.addFile(u":/magnifying-glass-minus.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon4.addFile(u":/magnifying-glass-minus.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.zoomOutAct.setIcon(icon4)
        self.mergeUtterancesAct = QAction(MainWindow)
        self.mergeUtterancesAct.setObjectName(u"mergeUtterancesAct")
        self.mergeUtterancesAct.setEnabled(False)
        icon5 = QIcon()
        icon5.addFile(u":/compress.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon5.addFile(u":/compress.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.mergeUtterancesAct.setIcon(icon5)
        self.splitUtterancesAct = QAction(MainWindow)
        self.splitUtterancesAct.setObjectName(u"splitUtterancesAct")
        self.splitUtterancesAct.setEnabled(False)
        icon6 = QIcon()
        icon6.addFile(u":/expand.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon6.addFile(u":/expand.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.splitUtterancesAct.setIcon(icon6)
        self.deleteUtterancesAct = QAction(MainWindow)
        self.deleteUtterancesAct.setObjectName(u"deleteUtterancesAct")
        self.deleteUtterancesAct.setEnabled(False)
        icon7 = QIcon()
        icon7.addFile(u":/disabled/trash.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon7.addFile(u":/trash.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.deleteUtterancesAct.setIcon(icon7)
        self.showAllSpeakersAct = QAction(MainWindow)
        self.showAllSpeakersAct.setObjectName(u"showAllSpeakersAct")
        self.showAllSpeakersAct.setCheckable(True)
        self.showAllSpeakersAct.setEnabled(False)
        icon8 = QIcon()
        icon8.addFile(u":/users.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon8.addFile(u":/users.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.showAllSpeakersAct.setIcon(icon8)
        self.revertDictionaryAct = QAction(MainWindow)
        self.revertDictionaryAct.setObjectName(u"revertDictionaryAct")
        self.revertDictionaryAct.setEnabled(False)
        icon9 = QIcon()
        icon9.addFile(u":/disabled/book-undo.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon9.addFile(u":/book-undo.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.revertDictionaryAct.setIcon(icon9)
        self.addSpeakerAct = QAction(MainWindow)
        self.addSpeakerAct.setObjectName(u"addSpeakerAct")
        self.addSpeakerAct.setEnabled(False)
        icon10 = QIcon()
        icon10.addFile(u":/user-plus.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon10.addFile(u":/user-plus.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.addSpeakerAct.setIcon(icon10)
        self.saveChangesAct = QAction(MainWindow)
        self.saveChangesAct.setObjectName(u"saveChangesAct")
        self.saveChangesAct.setEnabled(False)
        icon11 = QIcon()
        icon11.addFile(u":/sync.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon11.addFile(u":/sync.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.saveChangesAct.setIcon(icon11)
        self.getHelpAct = QAction(MainWindow)
        self.getHelpAct.setObjectName(u"getHelpAct")
        icon12 = QIcon()
        icon12.addFile(u":/help.svg", QSize(), QIcon.Normal, QIcon.Off)
        self.getHelpAct.setIcon(icon12)
        self.reportBugAct = QAction(MainWindow)
        self.reportBugAct.setObjectName(u"reportBugAct")
        icon13 = QIcon()
        icon13.addFile(u":/bug.svg", QSize(), QIcon.Normal, QIcon.Off)
        self.reportBugAct.setIcon(icon13)
        self.exitAct = QAction(MainWindow)
        self.exitAct.setObjectName(u"exitAct")
        icon14 = QIcon()
        icon14.addFile(u":/times.svg", QSize(), QIcon.Normal, QIcon.Off)
        self.exitAct.setIcon(icon14)
        self.cancelCorpusLoadAct = QAction(MainWindow)
        self.cancelCorpusLoadAct.setObjectName(u"cancelCorpusLoadAct")
        self.cancelCorpusLoadAct.setIcon(icon14)
        self.loadIvectorExtractorAct = QAction(MainWindow)
        self.loadIvectorExtractorAct.setObjectName(u"loadIvectorExtractorAct")
        self.loadLanguageModelAct = QAction(MainWindow)
        self.loadLanguageModelAct.setObjectName(u"loadLanguageModelAct")
        self.panLeftAct = QAction(MainWindow)
        self.panLeftAct.setObjectName(u"panLeftAct")
        self.panLeftAct.setEnabled(False)
        icon15 = QIcon()
        icon15.addFile(u":/caret-left.svg", QSize(), QIcon.Normal, QIcon.Off)
        self.panLeftAct.setIcon(icon15)
        self.panRightAct = QAction(MainWindow)
        self.panRightAct.setObjectName(u"panRightAct")
        self.panRightAct.setEnabled(False)
        icon16 = QIcon()
        icon16.addFile(u":/caret-right.svg", QSize(), QIcon.Normal, QIcon.Off)
        self.panRightAct.setIcon(icon16)
        self.searchAct = QAction(MainWindow)
        self.searchAct.setObjectName(u"searchAct")
        self.searchAct.setEnabled(False)
        icon17 = QIcon()
        icon17.addFile(u":/magnifying-glass.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon17.addFile(u":/magnifying-glass.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.searchAct.setIcon(icon17)
        self.changeVolumeAct = QAction(MainWindow)
        self.changeVolumeAct.setObjectName(u"changeVolumeAct")
        icon18 = QIcon()
        icon18.addFile(u":/volume-up.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon18.addFile(u":/volume-up.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.changeVolumeAct.setIcon(icon18)
        self.changeSpeakerAct = QAction(MainWindow)
        self.changeSpeakerAct.setObjectName(u"changeSpeakerAct")
        self.changeSpeakerAct.setEnabled(False)
        icon19 = QIcon()
        icon19.addFile(u":/speaker.svg", QSize(), QIcon.Normal, QIcon.Off)
        self.changeSpeakerAct.setIcon(icon19)
        self.saveDictionaryAct = QAction(MainWindow)
        self.saveDictionaryAct.setObjectName(u"saveDictionaryAct")
        self.saveDictionaryAct.setEnabled(False)
        icon20 = QIcon()
        icon20.addFile(u":/book-save.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon20.addFile(u":/book-save.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.saveDictionaryAct.setIcon(icon20)
        self.closeDictionaryAct = QAction(MainWindow)
        self.closeDictionaryAct.setObjectName(u"closeDictionaryAct")
        self.closeDictionaryAct.setEnabled(False)
        self.closeAcousticModelAct = QAction(MainWindow)
        self.closeAcousticModelAct.setObjectName(u"closeAcousticModelAct")
        self.closeAcousticModelAct.setEnabled(False)
        self.closeG2PAct = QAction(MainWindow)
        self.closeG2PAct.setObjectName(u"closeG2PAct")
        self.closeG2PAct.setEnabled(False)
        self.closeIvectorExtractorAct = QAction(MainWindow)
        self.closeIvectorExtractorAct.setObjectName(u"closeIvectorExtractorAct")
        self.closeIvectorExtractorAct.setEnabled(False)
        self.closeLanguageModelAct = QAction(MainWindow)
        self.closeLanguageModelAct.setObjectName(u"closeLanguageModelAct")
        self.closeLanguageModelAct.setEnabled(False)
        self.transcribeCorpusAct = QAction(MainWindow)
        self.transcribeCorpusAct.setObjectName(u"transcribeCorpusAct")
        self.transcribeCorpusAct.setEnabled(False)
        self.alignCorpusAct = QAction(MainWindow)
        self.alignCorpusAct.setObjectName(u"alignCorpusAct")
        self.loadReferenceAlignmentsAct = QAction(MainWindow)
        self.loadReferenceAlignmentsAct.setObjectName(u"loadReferenceAlignmentsAct")
        self.selectMappingFileAct = QAction(MainWindow)
        self.selectMappingFileAct.setObjectName(u"selectMappingFileAct")
        self.evaluateAlignmentsAct = QAction(MainWindow)
        self.evaluateAlignmentsAct.setObjectName(u"evaluateAlignmentsAct")
        self.revertChangesAct = QAction(MainWindow)
        self.revertChangesAct.setObjectName(u"revertChangesAct")
        self.revertChangesAct.setEnabled(False)
        icon21 = QIcon()
        icon21.addFile(u":/history.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon21.addFile(u":/history.svg", QSize(), QIcon.Disabled, QIcon.Off)
        icon21.addFile(u":/history.svg", QSize(), QIcon.Disabled, QIcon.On)
        self.revertChangesAct.setIcon(icon21)
        self.exportFilesAct = QAction(MainWindow)
        self.exportFilesAct.setObjectName(u"exportFilesAct")
        self.exportFilesAct.setEnabled(False)
        icon22 = QIcon()
        icon22.addFile(u":/file-export.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon22.addFile(u":/file-export.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.exportFilesAct.setIcon(icon22)
        self.lockEditAct = QAction(MainWindow)
        self.lockEditAct.setObjectName(u"lockEditAct")
        self.lockEditAct.setCheckable(True)
        self.lockEditAct.setEnabled(False)
        icon23 = QIcon()
        icon23.addFile(u":/lock-open.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon23.addFile(u":/checked/lock.svg", QSize(), QIcon.Normal, QIcon.On)
        icon23.addFile(u":/lock-open.svg", QSize(), QIcon.Disabled, QIcon.Off)
        icon23.addFile(u":/lock.svg", QSize(), QIcon.Disabled, QIcon.On)
        icon23.addFile(u":/checked/lock-open.svg", QSize(), QIcon.Active, QIcon.Off)
        icon23.addFile(u":/checked/lock.svg", QSize(), QIcon.Active, QIcon.On)
        icon23.addFile(u":/checked/lock-open.svg", QSize(), QIcon.Selected, QIcon.Off)
        icon23.addFile(u":/checked/lock.svg", QSize(), QIcon.Selected, QIcon.On)
        self.lockEditAct.setIcon(icon23)
        self.alignUtteranceAct = QAction(MainWindow)
        self.alignUtteranceAct.setObjectName(u"alignUtteranceAct")
        self.alignUtteranceAct.setEnabled(False)
        icon24 = QIcon()
        icon24.addFile(u":/magic.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon24.addFile(u":/magic.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.alignUtteranceAct.setIcon(icon24)
        self.reloadCorpusAct = QAction(MainWindow)
        self.reloadCorpusAct.setObjectName(u"reloadCorpusAct")
        self.zoomToSelectionAct = QAction(MainWindow)
        self.zoomToSelectionAct.setObjectName(u"zoomToSelectionAct")
        self.zoomToSelectionAct.setEnabled(False)
        icon25 = QIcon()
        icon25.addFile(u":/magnifying-glass-location.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon25.addFile(u":/magnifying-glass-location.svg", QSize(), QIcon.Disabled, QIcon.Off)
        self.zoomToSelectionAct.setIcon(icon25)
        self.oovsOnlyAct = QAction(MainWindow)
        self.oovsOnlyAct.setObjectName(u"oovsOnlyAct")
        self.oovsOnlyAct.setCheckable(True)
        icon26 = QIcon()
        icon26.addFile(u":/oov-check.svg", QSize(), QIcon.Normal, QIcon.Off)
        icon26.addFile(u":/oov-check.svg", QSize(), QIcon.Disabled, QIcon.Off)
        icon26.addFile(u":/checked/oov-check.svg", QSize(), QIcon.Disabled, QIcon.On)
        icon26.addFile(u":/checked/oov-check.svg", QSize(), QIcon.Active, QIcon.On)
        icon26.addFile(u":/oov-check.svg", QSize(), QIcon.Selected, QIcon.Off)
        self.oovsOnlyAct.setIcon(icon26)
        self.diarizeSpeakersAct = QAction(MainWindow)
        self.diarizeSpeakersAct.setObjectName(u"diarizeSpeakersAct")
        self.find_duplicates_action = QAction(MainWindow)
        self.find_duplicates_action.setObjectName(u"find_duplicates_action")
        self.cluster_utterances_action = QAction(MainWindow)
        self.cluster_utterances_action.setObjectName(u"cluster_utterances_action")
        self.classify_speakers_action = QAction(MainWindow)
        self.classify_speakers_action.setObjectName(u"classify_speakers_action")
        self.segmentUtteranceAct = QAction(MainWindow)
        self.segmentUtteranceAct.setObjectName(u"segmentUtteranceAct")
        icon27 = QIcon()
        icon27.addFile(u":/expand.svg", QSize(), QIcon.Normal, QIcon.Off)
        self.segmentUtteranceAct.setIcon(icon27)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout_4 = QVBoxLayout(self.centralwidget)
        self.verticalLayout_4.setSpacing(0)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.verticalLayout_4.setContentsMargins(0, 0, 0, 0)
        self.utteranceDetailWidget = UtteranceDetailWidget(self.centralwidget)
        self.utteranceDetailWidget.setObjectName(u"utteranceDetailWidget")

        self.verticalLayout_4.addWidget(self.utteranceDetailWidget)

        self.titleScreen = TitleScreen(self.centralwidget)
        self.titleScreen.setObjectName(u"titleScreen")

        self.verticalLayout_4.addWidget(self.titleScreen)

        self.loadingScreen = LoadingScreen(self.centralwidget)
        self.loadingScreen.setObjectName(u"loadingScreen")

        self.verticalLayout_4.addWidget(self.loadingScreen)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1448, 24))
        self.menuCorpus = QMenu(self.menubar)
        self.menuCorpus.setObjectName(u"menuCorpus")
        self.loadRecentCorpusMenu = QMenu(self.menuCorpus)
        self.loadRecentCorpusMenu.setObjectName(u"loadRecentCorpusMenu")
        self.loadRecentCorpusMenu.setMaximumSize(QSize(200, 400))
        self.menuEdit = QMenu(self.menubar)
        self.menuEdit.setObjectName(u"menuEdit")
        self.menuDictionary = QMenu(self.menubar)
        self.menuDictionary.setObjectName(u"menuDictionary")
        self.mfaDictionaryMenu = QMenu(self.menuDictionary)
        self.mfaDictionaryMenu.setObjectName(u"mfaDictionaryMenu")
        self.menuDownload_dictionary = QMenu(self.menuDictionary)
        self.menuDownload_dictionary.setObjectName(u"menuDownload_dictionary")
        self.menuDownload_dictionary.setMaximumSize(QSize(200, 400))
        self.menuWindow = QMenu(self.menubar)
        self.menuWindow.setObjectName(u"menuWindow")
        self.menuModels = QMenu(self.menubar)
        self.menuModels.setObjectName(u"menuModels")
        self.acousticModelMenu = QMenu(self.menuModels)
        self.acousticModelMenu.setObjectName(u"acousticModelMenu")
        self.g2pMenu = QMenu(self.menuModels)
        self.g2pMenu.setObjectName(u"g2pMenu")
        self.ivectorExtractorMenu = QMenu(self.menuModels)
        self.ivectorExtractorMenu.setObjectName(u"ivectorExtractorMenu")
        self.languageModelMenu = QMenu(self.menuModels)
        self.languageModelMenu.setObjectName(u"languageModelMenu")
        self.menuDownload_acoustic_model = QMenu(self.menuModels)
        self.menuDownload_acoustic_model.setObjectName(u"menuDownload_acoustic_model")
        self.menuDownload_acoustic_model.setMaximumSize(QSize(200, 400))
        self.menuDownload_ivector_extractor = QMenu(self.menuModels)
        self.menuDownload_ivector_extractor.setObjectName(u"menuDownload_ivector_extractor")
        self.menuDownload_ivector_extractor.setMaximumSize(QSize(200, 400))
        self.menuDownload_language_model = QMenu(self.menuModels)
        self.menuDownload_language_model.setObjectName(u"menuDownload_language_model")
        self.menuDownload_language_model.setMaximumSize(QSize(200, 400))
        self.menuDownload_G2P_model = QMenu(self.menuModels)
        self.menuDownload_G2P_model.setObjectName(u"menuDownload_G2P_model")
        self.menuDownload_G2P_model.setMaximumSize(QSize(200, 400))
        self.menuAlignment = QMenu(self.menubar)
        self.menuAlignment.setObjectName(u"menuAlignment")
        self.menuTranscription = QMenu(self.menubar)
        self.menuTranscription.setObjectName(u"menuTranscription")
        self.menuExperimental = QMenu(self.menubar)
        self.menuExperimental.setObjectName(u"menuExperimental")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)
        self.utteranceDockWidget = QDockWidget(MainWindow)
        self.utteranceDockWidget.setObjectName(u"utteranceDockWidget")
        self.utteranceDockWidget.setFeatures(QDockWidget.DockWidgetClosable|QDockWidget.DockWidgetFloatable|QDockWidget.DockWidgetMovable)
        self.utteranceListWidget = UtteranceListWidget()
        self.utteranceListWidget.setObjectName(u"utteranceListWidget")
        self.utteranceDockWidget.setWidget(self.utteranceListWidget)
        MainWindow.addDockWidget(Qt.LeftDockWidgetArea, self.utteranceDockWidget)
        self.dictionaryDockWidget = QDockWidget(MainWindow)
        self.dictionaryDockWidget.setObjectName(u"dictionaryDockWidget")
        self.dictionaryWidget = DictionaryWidget()
        self.dictionaryWidget.setObjectName(u"dictionaryWidget")
        self.dictionaryDockWidget.setWidget(self.dictionaryWidget)
        MainWindow.addDockWidget(Qt.LeftDockWidgetArea, self.dictionaryDockWidget)
        self.speakerDockWidget = QDockWidget(MainWindow)
        self.speakerDockWidget.setObjectName(u"speakerDockWidget")
        self.speakerWidget = SpeakerWidget()
        self.speakerWidget.setObjectName(u"speakerWidget")
        self.speakerDockWidget.setWidget(self.speakerWidget)
        MainWindow.addDockWidget(Qt.LeftDockWidgetArea, self.speakerDockWidget)
        self.toolBar = QToolBar(MainWindow)
        self.toolBar.setObjectName(u"toolBar")
        self.toolBar.setEnabled(True)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.toolBar.sizePolicy().hasHeightForWidth())
        self.toolBar.setSizePolicy(sizePolicy)
        self.toolBar.setAcceptDrops(False)
        self.toolBar.setMovable(False)
        self.toolBar.setAllowedAreas(Qt.BottomToolBarArea)
        self.toolBar.setIconSize(QSize(25, 25))
        self.toolBar.setFloatable(False)
        MainWindow.addToolBar(Qt.BottomToolBarArea, self.toolBar)
        self.acousticModelDockWidget = QDockWidget(MainWindow)
        self.acousticModelDockWidget.setObjectName(u"acousticModelDockWidget")
        self.acousticModelWidget = AcousticModelWidget()
        self.acousticModelWidget.setObjectName(u"acousticModelWidget")
        self.acousticModelDockWidget.setWidget(self.acousticModelWidget)
        MainWindow.addDockWidget(Qt.LeftDockWidgetArea, self.acousticModelDockWidget)
        self.languageModelDockWidget = QDockWidget(MainWindow)
        self.languageModelDockWidget.setObjectName(u"languageModelDockWidget")
        self.languageModelWidget = LanguageModelWidget()
        self.languageModelWidget.setObjectName(u"languageModelWidget")
        self.languageModelDockWidget.setWidget(self.languageModelWidget)
        MainWindow.addDockWidget(Qt.LeftDockWidgetArea, self.languageModelDockWidget)
        self.transcriptionDockWidget = QDockWidget(MainWindow)
        self.transcriptionDockWidget.setObjectName(u"transcriptionDockWidget")
        self.transcriptionWidget = TranscriberWidget()
        self.transcriptionWidget.setObjectName(u"transcriptionWidget")
        self.transcriptionDockWidget.setWidget(self.transcriptionWidget)
        MainWindow.addDockWidget(Qt.LeftDockWidgetArea, self.transcriptionDockWidget)
        self.alignmentDockWidget = QDockWidget(MainWindow)
        self.alignmentDockWidget.setObjectName(u"alignmentDockWidget")
        self.alignmentDockWidget.setEnabled(True)
        self.alignmentDockWidget.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.alignmentWidget = AlignmentWidget()
        self.alignmentWidget.setObjectName(u"alignmentWidget")
        self.alignmentDockWidget.setWidget(self.alignmentWidget)
        MainWindow.addDockWidget(Qt.LeftDockWidgetArea, self.alignmentDockWidget)
        self.oovDockWidget = QDockWidget(MainWindow)
        self.oovDockWidget.setObjectName(u"oovDockWidget")
        self.oovWidget = OovWidget()
        self.oovWidget.setObjectName(u"oovWidget")
        self.oovDockWidget.setWidget(self.oovWidget)
        MainWindow.addDockWidget(Qt.RightDockWidgetArea, self.oovDockWidget)
        self.diarizationDockWidget = QDockWidget(MainWindow)
        self.diarizationDockWidget.setObjectName(u"diarizationDockWidget")
        self.diarizationWidget = DiarizationWidget()
        self.diarizationWidget.setObjectName(u"diarizationWidget")
        self.diarizationDockWidget.setWidget(self.diarizationWidget)
        MainWindow.addDockWidget(Qt.LeftDockWidgetArea, self.diarizationDockWidget)

        self.menubar.addAction(self.menuCorpus.menuAction())
        self.menubar.addAction(self.menuEdit.menuAction())
        self.menubar.addAction(self.menuDictionary.menuAction())
        self.menubar.addAction(self.menuModels.menuAction())
        self.menubar.addAction(self.menuAlignment.menuAction())
        self.menubar.addAction(self.menuTranscription.menuAction())
        self.menubar.addAction(self.menuExperimental.menuAction())
        self.menubar.addAction(self.menuWindow.menuAction())
        self.menuCorpus.addAction(self.loadCorpusAct)
        self.menuCorpus.addAction(self.loadRecentCorpusMenu.menuAction())
        self.menuCorpus.addSeparator()
        self.menuCorpus.addAction(self.reloadCorpusAct)
        self.menuCorpus.addAction(self.saveChangesAct)
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
        self.menuEdit.addAction(self.revertChangesAct)
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
        self.menuAlignment.addAction(self.loadReferenceAlignmentsAct)
        self.menuAlignment.addAction(self.selectMappingFileAct)
        self.menuAlignment.addAction(self.evaluateAlignmentsAct)
        self.menuTranscription.addAction(self.transcribeCorpusAct)
        self.menuExperimental.addAction(self.find_duplicates_action)
        self.menuExperimental.addAction(self.cluster_utterances_action)
        self.menuExperimental.addAction(self.classify_speakers_action)
        self.toolBar.addAction(self.playAct)
        self.toolBar.addAction(self.showAllSpeakersAct)
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
        self.toolBar.addAction(self.segmentUtteranceAct)
        self.toolBar.addAction(self.lockEditAct)
        self.toolBar.addAction(self.saveChangesAct)
        self.toolBar.addAction(self.revertChangesAct)
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
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MFA Anchor", None))
        self.loadCorpusAct.setText(QCoreApplication.translate("MainWindow", u"Load a corpus", None))
        self.closeCurrentCorpusAct.setText(QCoreApplication.translate("MainWindow", u"Close current corpus", None))
        self.changeTemporaryDirectoryAct.setText(QCoreApplication.translate("MainWindow", u"Change temporary directory", None))
        self.openPreferencesAct.setText(QCoreApplication.translate("MainWindow", u"Preferences...", None))
        self.loadDictionaryAct.setText(QCoreApplication.translate("MainWindow", u"Choose a dictionary...", None))
        self.loadAcousticModelAct.setText(QCoreApplication.translate("MainWindow", u"Choose a model...", None))
        self.loadG2PModelAct.setText(QCoreApplication.translate("MainWindow", u"Choose a model...", None))
        self.playAct.setText(QCoreApplication.translate("MainWindow", u"Play", None))
        self.muteAct.setText(QCoreApplication.translate("MainWindow", u"Mute", None))
        self.zoomInAct.setText(QCoreApplication.translate("MainWindow", u"Zoom in", None))
#if QT_CONFIG(shortcut)
        self.zoomInAct.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+I", None))
#endif // QT_CONFIG(shortcut)
        self.zoomOutAct.setText(QCoreApplication.translate("MainWindow", u"Zoom out", None))
#if QT_CONFIG(shortcut)
        self.zoomOutAct.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+O", None))
#endif // QT_CONFIG(shortcut)
        self.mergeUtterancesAct.setText(QCoreApplication.translate("MainWindow", u"Merge utterances", None))
#if QT_CONFIG(shortcut)
        self.mergeUtterancesAct.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+M", None))
#endif // QT_CONFIG(shortcut)
        self.splitUtterancesAct.setText(QCoreApplication.translate("MainWindow", u"Split utterances", None))
        self.deleteUtterancesAct.setText(QCoreApplication.translate("MainWindow", u"Delete utterance", None))
#if QT_CONFIG(shortcut)
        self.deleteUtterancesAct.setShortcut(QCoreApplication.translate("MainWindow", u"Del", None))
#endif // QT_CONFIG(shortcut)
        self.showAllSpeakersAct.setText(QCoreApplication.translate("MainWindow", u"Show all speakers", None))
        self.revertDictionaryAct.setText(QCoreApplication.translate("MainWindow", u"Revert dictionary changes", None))
        self.addSpeakerAct.setText(QCoreApplication.translate("MainWindow", u"Add new speaker", None))
        self.saveChangesAct.setText(QCoreApplication.translate("MainWindow", u"Sync changes", None))
#if QT_CONFIG(tooltip)
        self.saveChangesAct.setToolTip(QCoreApplication.translate("MainWindow", u"Sync changes to the database", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(shortcut)
        self.saveChangesAct.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+S", None))
#endif // QT_CONFIG(shortcut)
        self.getHelpAct.setText(QCoreApplication.translate("MainWindow", u"Help", None))
        self.reportBugAct.setText(QCoreApplication.translate("MainWindow", u"Report bug", None))
        self.exitAct.setText(QCoreApplication.translate("MainWindow", u"Exit", None))
        self.cancelCorpusLoadAct.setText(QCoreApplication.translate("MainWindow", u"Cancel loading corpus", None))
        self.loadIvectorExtractorAct.setText(QCoreApplication.translate("MainWindow", u"Choose a model...", None))
        self.loadLanguageModelAct.setText(QCoreApplication.translate("MainWindow", u"Choose a model...", None))
        self.panLeftAct.setText(QCoreApplication.translate("MainWindow", u"Pan left", None))
        self.panRightAct.setText(QCoreApplication.translate("MainWindow", u"Pan right", None))
        self.searchAct.setText(QCoreApplication.translate("MainWindow", u"Search corpus", None))
        self.changeVolumeAct.setText(QCoreApplication.translate("MainWindow", u"Change volume", None))
        self.changeSpeakerAct.setText(QCoreApplication.translate("MainWindow", u"Change speaker", None))
        self.saveDictionaryAct.setText(QCoreApplication.translate("MainWindow", u"Save dictionary", None))
        self.closeDictionaryAct.setText(QCoreApplication.translate("MainWindow", u"Close dictionary", None))
        self.closeAcousticModelAct.setText(QCoreApplication.translate("MainWindow", u"Close acoustic model", None))
        self.closeG2PAct.setText(QCoreApplication.translate("MainWindow", u"Close G2P model", None))
        self.closeIvectorExtractorAct.setText(QCoreApplication.translate("MainWindow", u"Close ivector extractor", None))
        self.closeLanguageModelAct.setText(QCoreApplication.translate("MainWindow", u"Close language model", None))
        self.transcribeCorpusAct.setText(QCoreApplication.translate("MainWindow", u"Transcribe corpus", None))
        self.alignCorpusAct.setText(QCoreApplication.translate("MainWindow", u"Align corpus", None))
        self.loadReferenceAlignmentsAct.setText(QCoreApplication.translate("MainWindow", u"Load reference alignments", None))
        self.selectMappingFileAct.setText(QCoreApplication.translate("MainWindow", u"Select custom mapping file", None))
        self.evaluateAlignmentsAct.setText(QCoreApplication.translate("MainWindow", u"Evaluate alignments", None))
        self.revertChangesAct.setText(QCoreApplication.translate("MainWindow", u"Revert changes", None))
#if QT_CONFIG(tooltip)
        self.revertChangesAct.setToolTip(QCoreApplication.translate("MainWindow", u"Revert current changes to last sync", None))
#endif // QT_CONFIG(tooltip)
        self.exportFilesAct.setText(QCoreApplication.translate("MainWindow", u"Export changes", None))
#if QT_CONFIG(tooltip)
        self.exportFilesAct.setToolTip(QCoreApplication.translate("MainWindow", u"Export changes to original files", None))
#endif // QT_CONFIG(tooltip)
        self.lockEditAct.setText(QCoreApplication.translate("MainWindow", u"Lock editing", None))
        self.alignUtteranceAct.setText(QCoreApplication.translate("MainWindow", u"Align utterance", None))
#if QT_CONFIG(tooltip)
        self.alignUtteranceAct.setToolTip(QCoreApplication.translate("MainWindow", u"Align the current utterance", None))
#endif // QT_CONFIG(tooltip)
        self.reloadCorpusAct.setText(QCoreApplication.translate("MainWindow", u"Reload corpus text from disk", None))
        self.zoomToSelectionAct.setText(QCoreApplication.translate("MainWindow", u"Zoom to selection", None))
        self.oovsOnlyAct.setText(QCoreApplication.translate("MainWindow", u"OOVs Only", None))
        self.diarizeSpeakersAct.setText(QCoreApplication.translate("MainWindow", u"Calculate ivectors", None))
        self.find_duplicates_action.setText(QCoreApplication.translate("MainWindow", u"Find duplicate utterances", None))
        self.cluster_utterances_action.setText(QCoreApplication.translate("MainWindow", u"Cluster utterances", None))
        self.classify_speakers_action.setText(QCoreApplication.translate("MainWindow", u"Classify speakers", None))
        self.segmentUtteranceAct.setText(QCoreApplication.translate("MainWindow", u"Segment utterance", None))
#if QT_CONFIG(tooltip)
        self.segmentUtteranceAct.setToolTip(QCoreApplication.translate("MainWindow", u"Split an utterance into VAD-based segments", None))
#endif // QT_CONFIG(tooltip)
        self.menuCorpus.setTitle(QCoreApplication.translate("MainWindow", u"Corpus", None))
        self.loadRecentCorpusMenu.setTitle(QCoreApplication.translate("MainWindow", u"Load a recent corpus", None))
        self.menuEdit.setTitle(QCoreApplication.translate("MainWindow", u"Edit", None))
        self.menuDictionary.setTitle(QCoreApplication.translate("MainWindow", u"Dictionary", None))
        self.mfaDictionaryMenu.setTitle(QCoreApplication.translate("MainWindow", u"Load a saved dictionary", None))
        self.menuDownload_dictionary.setTitle(QCoreApplication.translate("MainWindow", u"Download dictionary", None))
        self.menuWindow.setTitle(QCoreApplication.translate("MainWindow", u"Window", None))
        self.menuModels.setTitle(QCoreApplication.translate("MainWindow", u"Models", None))
        self.acousticModelMenu.setTitle(QCoreApplication.translate("MainWindow", u"Load acoustic model", None))
        self.g2pMenu.setTitle(QCoreApplication.translate("MainWindow", u"Load G2P model", None))
        self.ivectorExtractorMenu.setTitle(QCoreApplication.translate("MainWindow", u"Load ivector extractor", None))
        self.languageModelMenu.setTitle(QCoreApplication.translate("MainWindow", u"Load language model", None))
        self.menuDownload_acoustic_model.setTitle(QCoreApplication.translate("MainWindow", u"Download acoustic model", None))
        self.menuDownload_ivector_extractor.setTitle(QCoreApplication.translate("MainWindow", u"Download ivector extractor", None))
        self.menuDownload_language_model.setTitle(QCoreApplication.translate("MainWindow", u"Download language model", None))
        self.menuDownload_G2P_model.setTitle(QCoreApplication.translate("MainWindow", u"Download G2P model", None))
        self.menuAlignment.setTitle(QCoreApplication.translate("MainWindow", u"Alignment", None))
        self.menuTranscription.setTitle(QCoreApplication.translate("MainWindow", u"Transcription", None))
        self.menuExperimental.setTitle(QCoreApplication.translate("MainWindow", u"Experimental", None))
        self.utteranceDockWidget.setWindowTitle(QCoreApplication.translate("MainWindow", u"Utterances", None))
        self.dictionaryDockWidget.setWindowTitle(QCoreApplication.translate("MainWindow", u"Dictionary", None))
        self.speakerDockWidget.setWindowTitle(QCoreApplication.translate("MainWindow", u"Speakers", None))
        self.toolBar.setWindowTitle(QCoreApplication.translate("MainWindow", u"toolBar", None))
        self.acousticModelDockWidget.setWindowTitle(QCoreApplication.translate("MainWindow", u"Acoustic model", None))
        self.languageModelDockWidget.setWindowTitle(QCoreApplication.translate("MainWindow", u"Language model", None))
        self.transcriptionDockWidget.setWindowTitle(QCoreApplication.translate("MainWindow", u"Transcription", None))
        self.alignmentDockWidget.setWindowTitle(QCoreApplication.translate("MainWindow", u"Alignment", None))
        self.oovDockWidget.setWindowTitle(QCoreApplication.translate("MainWindow", u"OOVs", None))
        self.diarizationDockWidget.setWindowTitle(QCoreApplication.translate("MainWindow", u"Diarization", None))
    # retranslateUi

