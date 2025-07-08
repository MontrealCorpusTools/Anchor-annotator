from __future__ import annotations

import logging
import os
import re
import time
import typing
from typing import TYPE_CHECKING, Optional

import numpy as np
from _kalpy.ivector import ivector_normalize_length
from _kalpy.matrix import DoubleVector
from montreal_forced_aligner.data import (  # noqa
    ClusterType,
    DistanceMetric,
    Language,
    ManifoldAlgorithm,
    PhoneSetType,
    PhoneType,
    WordType,
)
from montreal_forced_aligner.db import Corpus, Phone, Speaker, Utterance  # noqa
from montreal_forced_aligner.models import AcousticModel, Archive
from montreal_forced_aligner.utils import DatasetType, inspect_database, mfa_open  # noqa
from PySide6 import QtCore, QtGui, QtMultimedia, QtSvgWidgets, QtWidgets

import anchor.resources_rc  # noqa
from anchor.models import (
    AcousticModelTableModel,
    AlignmentAnalysisModel,
    CorpusModel,
    CorpusSelectionModel,
    CorpusTableModel,
    DiarizationModel,
    DictionaryModelTableModel,
    DictionaryTableModel,
    FileSelectionModel,
    FileUtterancesModel,
    G2PModelTableModel,
    IvectorExtractorTableModel,
    LanguageModelTableModel,
    MfaModelTableModel,
    OovModel,
    SpeakerModel,
    TextFilterQuery,
)
from anchor.plot import UtteranceClusterView, UtteranceView
from anchor.settings import AnchorSettings
from anchor.workers import Worker

if TYPE_CHECKING:
    import anchor.db
    from anchor.main import MainWindow

outside_column_ratio = 0.2
outside_column_minimum = 250

logger = logging.getLogger("anchor")


class ScrollableMenuStyle(QtWidgets.QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QtWidgets.QStyle.StyleHint.SH_Menu_Scrollable:
            return 0
        return super().styleHint(hint, option, widget, returnData)


class ErrorButtonBox(QtWidgets.QDialogButtonBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Close)
        self.report_bug_button = QtWidgets.QPushButton("Report bug")
        self.report_bug_button.setIcon(QtGui.QIcon.fromTheme("folder-open"))
        self.addButton(self.report_bug_button, QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)


class MediaPlayer(QtMultimedia.QMediaPlayer):  # pragma: no cover
    timeChanged = QtCore.Signal(object)
    audioReady = QtCore.Signal(object)

    def __init__(self, *args):
        super(MediaPlayer, self).__init__(*args)
        self.settings = AnchorSettings()
        self.devices = QtMultimedia.QMediaDevices()
        self.devices.audioOutputsChanged.connect(self.update_audio_device)
        self.max_time = None
        self.start_load_time = None
        self.min_time = None
        self.selection_model = None
        self.positionChanged.connect(self.checkStop)
        # self.positionChanged.connect(self.positionDebug)
        self.errorOccurred.connect(self.handle_error)
        o = None

        for o in QtMultimedia.QMediaDevices.audioOutputs():
            if o.id() == self.settings.value(self.settings.AUDIO_DEVICE):
                break
        self._audio_output = QtMultimedia.QAudioOutput(o)
        self._audio_output.setDevice(self.devices.defaultAudioOutput())
        self.setAudioOutput(self._audio_output)
        self.playbackStateChanged.connect(self.reset_position)
        self.fade_in_anim = QtCore.QPropertyAnimation(self._audio_output, b"volume")
        self.fade_in_anim.setDuration(10)
        self.fade_in_anim.setStartValue(0.1)
        self.fade_in_anim.setEndValue(self._audio_output.volume())
        self.fade_in_anim.setEasingCurve(QtCore.QEasingCurve.Type.Linear)
        self.fade_in_anim.setKeyValueAt(0.1, 0.1)

        self.file_path = None
        self.set_volume(self.settings.value(self.settings.VOLUME))

    def setMuted(self, muted: bool):
        self.audioOutput().setMuted(muted)

    def handle_error(self, *args):
        logger.info("ERROR")
        logger.info(args)

    def play(self) -> None:
        if self.startTime() is None:
            return
        if self.mediaStatus() not in {
            QtMultimedia.QMediaPlayer.MediaStatus.BufferedMedia,
            QtMultimedia.QMediaPlayer.MediaStatus.LoadedMedia,
            QtMultimedia.QMediaPlayer.MediaStatus.EndOfMedia,
        }:
            return
        fade_in = self.settings.value(self.settings.ENABLE_FADE)
        if fade_in:
            self._audio_output.setVolume(0.1)
        if (
            self.playbackState() == QtMultimedia.QMediaPlayer.PlaybackState.StoppedState
            or self.currentTime() < self.startTime()
            or self.currentTime() >= self.maxTime()
        ):
            self.setCurrentTime(self.startTime())
        super(MediaPlayer, self).play()
        if fade_in:
            self.fade_in_anim.start()

    def startTime(self):
        if (
            self.selection_model.selected_min_time is not None
            and self.selection_model.min_time
            <= self.selection_model.selected_min_time
            <= self.selection_model.max_time
        ):
            return self.selection_model.selected_min_time
        return self.selection_model.min_time

    def maxTime(self):
        if (
            self.selection_model.selected_max_time is not None
            and self.selection_model.min_time
            <= self.selection_model.selected_max_time
            <= self.selection_model.max_time
        ):
            return self.selection_model.selected_max_time
        return self.selection_model.max_time

    def reset_position(self):
        state = self.playbackState()
        if state == QtMultimedia.QMediaPlayer.PlaybackState.StoppedState:
            self.setCurrentTime(self.startTime())

    def update_audio_device(self):
        self._audio_output.setDevice(self.devices.defaultAudioOutput())
        self.setAudioOutput(self._audio_output)

    def refresh_settings(self):
        self.settings.sync()
        o = None
        for o in QtMultimedia.QMediaDevices.audioOutputs():
            if o.id() == self.settings.value(self.settings.AUDIO_DEVICE):
                break
        self._audio_output.setDevice(o)

    def set_models(self, selection_model: Optional[FileSelectionModel]):
        if selection_model is None:
            return
        self.selection_model = selection_model
        self.selection_model.fileChanged.connect(self.load_new_file)
        self.selection_model.viewChanged.connect(self.update_times)
        self.selection_model.selectionAudioChanged.connect(self.update_selection_times)

    def set_volume(self, volume: int):
        self.settings.setValue(self.settings.VOLUME, volume)
        if self.audioOutput() is None:
            return
        linearVolume = QtMultimedia.QAudio.convertVolume(
            volume / 100.0,
            QtMultimedia.QAudio.VolumeScale.LogarithmicVolumeScale,
            QtMultimedia.QAudio.VolumeScale.LinearVolumeScale,
        )
        self.audioOutput().setVolume(linearVolume)
        self.fade_in_anim.setEndValue(linearVolume)

    def volume(self) -> int:
        if self.audioOutput() is None:
            return 100
        volume = self.audioOutput().volume()
        volume = int(
            QtMultimedia.QAudio.convertVolume(
                volume,
                QtMultimedia.QAudio.VolumeScale.LinearVolumeScale,
                QtMultimedia.QAudio.VolumeScale.LogarithmicVolumeScale,
            )
            * 100
        )
        return volume

    def update_selection_times(self, update=False):
        if update or self.playbackState() != QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
            self.setCurrentTime(self.startTime())

    def update_times(self):
        if self.playbackState() == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
            return
        if self.currentTime() < self.startTime() or self.currentTime() > self.maxTime():
            self.stop()
        if self.playbackState() != QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
            self.stop()
            self.setCurrentTime(self.startTime())

    def load_new_file(self, *args):
        if self.playbackState() in {
            QtMultimedia.QMediaPlayer.PlaybackState.PlayingState,
            QtMultimedia.QMediaPlayer.PlaybackState.PausedState,
        }:
            self.stop()
            time.sleep(0.1)
        try:
            new_file = self.selection_model.model().file.sound_file.sound_file_path
        except Exception:
            self.setSource(QtCore.QUrl())
            return
        if (
            self.selection_model.max_time is None
            or self.selection_model.model().file is None
            or self.selection_model.model().file.duration is None
        ):
            self.setSource(QtCore.QUrl())
            return
        self.setSource(f"file:///{new_file}")

    def currentTime(self):
        pos = self.position()
        return pos / 1000

    def setCurrentTime(self, time):
        if time is None:
            time = 0
        pos = int(time * 1000)
        self.setPosition(pos)

    def checkStop(self):
        self.timeChanged.emit(self.currentTime())
        if self.playbackState() == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
            if self.maxTime() is None or self.currentTime() > self.maxTime():
                self.stop()


class NewSpeakerField(QtWidgets.QLineEdit):
    enableAddSpeaker = QtCore.Signal(object)

    @property
    def _internal_layout(self):
        if not hasattr(self, "_internal_layout_"):
            self._internal_layout_ = QtWidgets.QHBoxLayout(self)
            self._internal_layout_.addStretch()
        self._internal_layout_.setContentsMargins(1, 1, 1, 1)
        self._internal_layout_.setSpacing(0)
        return self._internal_layout_

    def add_button(self, button):
        self._internal_layout.insertWidget(self._internal_layout.count(), button)
        button.setFocusProxy(self)

    def _fix_cursor_position(self, button):
        self.setTextMargins(button.geometry().right(), 0, 0, 0)

    def __init__(self, *args):
        super(NewSpeakerField, self).__init__(*args)
        self.setObjectName("new_speaker_field")
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred
        )
        clear_icon = QtGui.QIcon.fromTheme("edit-clear")

        self.clear_action = QtGui.QAction(icon=clear_icon, parent=self)
        self.clear_action.triggered.connect(self.clear)
        self.clear_action.setVisible(False)

        self.textChanged.connect(self.check_contents)

        self.tool_bar = QtWidgets.QToolBar()
        self.tool_bar.addAction(self.clear_action)
        w = self.tool_bar.widgetForAction(self.clear_action)
        w.setObjectName("clear_new_speaker_field")
        w.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        self.add_button(self.tool_bar)
        self.save_action = None

    def check_contents(self):
        if self.text():
            self.clear_action.setVisible(True)
            self.enableAddSpeaker.emit(True)
        else:
            self.clear_action.setVisible(False)
            self.enableAddSpeaker.emit(False)


class HelpDropDown(QtWidgets.QToolButton):
    def __init__(self, *args):
        super(HelpDropDown, self).__init__(*args)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.menu = QtWidgets.QMenu(self)
        self.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.setMenu(self.menu)
        self.clicked.connect(self.showMenu)

    def addAction(self, action: "QtGui.QAction") -> None:
        self.menu.addAction(action)


class SpeakerDropDown(QtWidgets.QToolButton):
    def __init__(self, *args):
        super(SpeakerDropDown, self).__init__(*args)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.current_speaker = ""
        self.menu = QtWidgets.QMenu(self)
        # self.menu.setStyleSheet(self.parent().settings.menu_style_sheet)
        self.speakers = []
        self.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.setMenu(self.menu)
        self.menu.triggered.connect(self.select_speaker)
        self.clicked.connect(self.showMenu)

    def select_speaker(self, action):
        s = action.text()
        self.setCurrentSpeaker(s)
        self.defaultAction().trigger()

    def refresh_speaker_dropdown(self, speakers):
        self.speakers = speakers
        self.menu.clear()
        if self.speakers:
            for s in self.speakers:
                self.menu.addAction(s.name)

        if self.current_speaker not in speakers:
            self.setCurrentSpeaker(Speaker(""))

    def setCurrentSpeaker(self, speaker: Speaker):
        self.current_speaker = speaker
        self.setText(speaker.name)


class BaseTableView(QtWidgets.QTableView):
    def __init__(self, *args):
        self.settings = AnchorSettings()
        super().__init__(*args)
        self.setCornerButtonEnabled(False)
        # self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setHighlightSections(False)
        self.verticalHeader().setSectionsClickable(False)

        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setDragEnabled(False)
        self.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSelectionBehavior(QtWidgets.QTableView.SelectionBehavior.SelectRows)
        self.header = HeaderView(QtCore.Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(self.header)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        copy_combo = QtCore.QKeyCombination(QtCore.Qt.Modifier.CTRL, QtCore.Qt.Key.Key_C)
        if event.keyCombination() == copy_combo:
            clipboard = QtGui.QGuiApplication.clipboard()
            current = self.selectionModel().currentIndex()
            text = self.selectionModel().model().data(current, QtCore.Qt.ItemDataRole.DisplayRole)
            clipboard.setText(str(text))
        elif QtGui.QKeySequence(event.keyCombination()) not in self.settings.all_keybinds:
            super().keyPressEvent(event)

    def setModel(self, model: QtCore.QAbstractItemModel) -> None:
        super().setModel(model)
        self.refresh_settings()

    def refresh_settings(self):
        self.settings.sync()
        # self.horizontalHeader().setFont(self.settings.big_font)
        # self.setFont(self.settings.font)


class AnchorTableView(BaseTableView):
    def setModel(self, model: QtCore.QAbstractItemModel) -> None:
        super().setModel(model)
        # self.model().newResults.connect(self.scrollToTop)
        self.selectionModel().clear()
        self.horizontalHeader().sortIndicatorChanged.connect(self.model().update_sort)

    def refresh_settings(self):
        super().refresh_settings()
        fm = QtGui.QFontMetrics(self.settings.big_font)
        minimum = 100
        for i in range(self.horizontalHeader().count()):
            text = self.model().headerData(
                i, QtCore.Qt.Orientation.Horizontal, QtCore.Qt.ItemDataRole.DisplayRole
            )

            width = fm.boundingRect(text).width() + (3 * self.settings.sort_indicator_padding)
            if width < minimum:
                minimum = width
            self.setColumnWidth(i, width)
        self.horizontalHeader().setMinimumSectionSize(minimum)


class UtteranceListTable(AnchorTableView):
    def __init__(self, *args):
        super().__init__(*args)

    def set_models(self, model: CorpusModel, selection_model: CorpusSelectionModel):
        self.setModel(model)
        self.setSelectionModel(selection_model)
        self.doubleClicked.connect(self.selectionModel().focus_utterance)
        self.model().utteranceTextUpdated.connect(self.repaint)
        self.refresh_settings()
        model.corpusLoaded.connect(self.update_header)

    def update_header(self):
        m: CorpusModel = self.model()
        for i in m.alignment_header_indices:
            self.horizontalHeader().setSectionHidden(i, True)
        for i in m.alignment_evaluation_header_indices:
            self.horizontalHeader().setSectionHidden(i, True)
        for i in m.transcription_header_indices:
            self.horizontalHeader().setSectionHidden(i, True)
        for i in m.diarization_header_indices:
            self.horizontalHeader().setSectionHidden(i, True)
        if m.corpus.alignment_evaluation_done:
            for i in m.alignment_evaluation_header_indices:
                self.horizontalHeader().setSectionHidden(i, False)
        if m.corpus.has_alignments():
            for i in m.alignment_header_indices:
                self.horizontalHeader().setSectionHidden(i, False)
        if m.corpus.has_any_ivectors():
            for i in m.diarization_header_indices:
                self.horizontalHeader().setSectionHidden(i, False)
        if m.corpus.transcription_done:
            for i in m.transcription_header_indices:
                self.horizontalHeader().setSectionHidden(i, False)


# noinspection PyUnresolvedReferences
class CompleterLineEdit(QtWidgets.QWidget):
    def __init__(self, *args, corpus_model: CorpusModel = None):
        super().__init__(*args)
        self.settings = AnchorSettings()
        self.corpus_model = corpus_model
        layout = QtWidgets.QHBoxLayout()
        self.line_edit = QtWidgets.QLineEdit(self)
        # self.model = QtCore.QStringListModel(self)
        # self.completer.setModel(self.model)
        layout.addWidget(self.line_edit)
        clear_icon = QtGui.QIcon.fromTheme("edit-clear")
        self.button = QtWidgets.QToolButton(self)
        self.button.clicked.connect(self.clear_text)
        self.line_edit.textChanged.connect(self.check_actions)
        self.button.setIcon(clear_icon)
        self.button.setDisabled(True)
        # self.clear_action = QtGui.QAction(icon=clear_icon, parent=self)
        # self.clear_action.triggered.connect(self.clear_index)
        # self.clear_action.setVisible(False)
        layout.addWidget(self.button)
        self.setLayout(layout)
        # self.setStyleSheet(self.settings.style_sheet)
        self.completions = {}

    def validate(self) -> bool:
        if not self.line_edit.text():
            return False
        return self.line_edit.text() in self.completions

    def current_text(self):
        if self.line_edit.text():
            if self.corpus_model is not None:
                return self.corpus_model.get_speaker_id(self.line_edit.text())
            if self.line_edit.text() in self.completions:
                return self.completions[self.line_edit.text()]
            return self.line_edit.text()
        return None

    def clear_text(self):
        self.line_edit.clear()
        self.line_edit.returnPressed.emit()

    def check_actions(self):
        if self.line_edit.text():
            self.button.setDisabled(False)
        else:
            self.button.setDisabled(True)

    def update_completions(self, completions: dict[str, int]) -> None:
        self.completions = completions
        model = QtCore.QStringListModel(sorted(self.completions.keys()))
        completer = QtWidgets.QCompleter(self)
        completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseSensitive)
        completer.setModelSorting(QtWidgets.QCompleter.ModelSorting.CaseSensitivelySortedModel)
        completer.setCompletionMode(QtWidgets.QCompleter.CompletionMode.PopupCompletion)
        completer.popup().setUniformItemSizes(True)
        completer.popup().setLayoutMode(QtWidgets.QListView.LayoutMode.Batched)
        completer.setModel(model)
        completer.popup().setStyleSheet(self.settings.completer_style_sheet)
        self.line_edit.setCompleter(completer)
        # self.line_edit.textChanged.connect(completer.setCompletionPrefix)


class WordCompleterLineEdit(CompleterLineEdit):
    def current_text(self):
        if self.line_edit.text():
            if self.line_edit.text() in self.completions:
                return self.completions[self.line_edit.text()]
            return self.line_edit.text()
        return None


class ClearableDropDown(QtWidgets.QWidget):
    def __init__(self, *args):
        super(ClearableDropDown, self).__init__(*args)
        self.combo_box = QtWidgets.QComboBox(self)
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.combo_box)
        clear_icon = QtGui.QIcon.fromTheme("edit-clear")
        self.combo_box.currentIndexChanged.connect(self.check_actions)
        self.button = QtWidgets.QToolButton(self)
        self.button.clicked.connect(self.clear_index)
        self.button.setIcon(clear_icon)
        self.button.setDisabled(True)
        # self.clear_action = QtGui.QAction(icon=clear_icon, parent=self)
        # self.clear_action.triggered.connect(self.clear_index)
        # self.clear_action.setVisible(False)
        self.combo_box.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        # self.tool_bar.addAction(self.clear_action)
        # w = self.tool_bar.widgetForAction(self.clear_action)

        layout.addWidget(self.button)
        self.setLayout(layout)

    def check_actions(self):
        if self.combo_box.currentIndex() == -1:
            self.button.setDisabled(True)
        else:
            self.button.setEnabled(True)

    def clear_index(self):
        self.combo_box.setCurrentIndex(-1)

    def clear(self):
        self.combo_box.clear()

    def addItem(self, *args):
        self.combo_box.addItem(*args)


class PaginationWidget(QtWidgets.QToolBar):
    offsetRequested = QtCore.Signal(int)
    pageRequested = QtCore.Signal()

    def __init__(self, *args):
        super(PaginationWidget, self).__init__(*args)
        w = QtWidgets.QWidget(self)
        w.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding
        )
        w2 = QtWidgets.QWidget(self)
        w2.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding
        )
        self.current_page = 0
        self.limit = 1
        self.num_pages = 1
        self.result_count = 0
        self.next_page_action = QtGui.QAction(
            icon=QtGui.QIcon.fromTheme("media-seek-forward"), text="Next page"
        )
        self.previous_page_action = QtGui.QAction(
            icon=QtGui.QIcon.fromTheme("media-seek-backward"), text="Previous page"
        )
        self.addWidget(w)
        self.page_label = QtWidgets.QLabel("Page 1 of 1")
        self.addAction(self.previous_page_action)
        self.addWidget(self.page_label)
        self.addAction(self.next_page_action)
        self.addWidget(w2)
        self.next_page_action.triggered.connect(self.next_page)
        self.previous_page_action.triggered.connect(self.previous_page)

    def reset(self):
        self.current_page = 0
        self.num_pages = 0

    def first_page(self):
        self.current_page = 0
        self.offsetRequested.emit(self.current_page * self.limit)

    def next_page(self):
        if self.current_page != self.num_pages - 1:
            self.current_page += 1
            self.offsetRequested.emit(self.current_page * self.limit)
            self.refresh_pages()

    def previous_page(self):
        if self.current_page != 0:
            self.current_page -= 1
            self.offsetRequested.emit(self.current_page * self.limit)
            self.refresh_pages()

    def set_limit(self, limit: int):
        self.limit = limit
        self._recalculate_num_pages()

    def _recalculate_num_pages(self):
        if self.result_count == 0:
            return
        self.num_pages = int(self.result_count / self.limit)
        if self.result_count % self.limit != 0:
            self.num_pages += 1
        self.refresh_pages()

    def update_result_count(self, result_count: int):
        self.result_count = result_count
        self._recalculate_num_pages()
        self.current_page = min(self.current_page, self.num_pages)

    def refresh_pages(self):
        self.previous_page_action.setEnabled(True)
        self.next_page_action.setEnabled(True)
        if self.current_page == 0:
            self.previous_page_action.setEnabled(False)
        if self.current_page == self.num_pages - 1 and self.num_pages > 0:
            self.next_page_action.setEnabled(False)
        self.page_label.setText(f"Page {self.current_page + 1} of {self.num_pages}")
        self.pageRequested.emit()


class UtteranceListWidget(QtWidgets.QWidget):  # pragma: no cover
    fileChanged = QtCore.Signal(object)

    def __init__(self, *args):
        super(UtteranceListWidget, self).__init__(*args)
        self.settings = AnchorSettings()
        self.setMinimumWidth(100)
        self.corpus_model: Optional[CorpusModel] = None
        self.selection_model: Optional[CorpusSelectionModel] = None
        layout = QtWidgets.QVBoxLayout()

        self.status_indicator = LoadingScreen(self, logo=False)
        self.status_indicator.setVisible(False)
        layout.addWidget(self.status_indicator)
        self.file_dropdown = CompleterLineEdit(self)
        self.file_dropdown.line_edit.setPlaceholderText("Filter by file")
        self.file_dropdown.line_edit.returnPressed.connect(self.search)

        self.speaker_dropdown = CompleterLineEdit(self)
        self.speaker_dropdown.line_edit.setPlaceholderText("Filter by speaker")
        self.speaker_dropdown.line_edit.returnPressed.connect(self.search)

        layout.addWidget(self.file_dropdown)
        layout.addWidget(self.speaker_dropdown)
        self.search_box = SearchBox(self)
        search_layout = QtWidgets.QHBoxLayout()
        self.replace_box = ReplaceBox(self)
        self.oov_button = QtWidgets.QToolButton()
        self.search_widget = QtWidgets.QWidget()
        search_layout.addWidget(self.search_box)
        search_layout.addWidget(self.oov_button)
        search_layout.addWidget(self.replace_box)
        self.search_widget.setLayout(search_layout)
        layout.addWidget(self.search_widget)
        self.replace_box.replaceAllActivated.connect(self.replace)
        self.search_box.searchActivated.connect(self.search)
        self.cached_query = None

        self.table_widget = UtteranceListTable(self)
        self.highlight_delegate = HighlightDelegate(self.table_widget)
        self.nowrap_delegate = NoWrapDelegate(self.table_widget)

        self.icon_delegate = IconDelegate(self.table_widget)
        self.table_widget.setItemDelegateForColumn(0, self.icon_delegate)

        layout.addWidget(self.table_widget)
        self.pagination_toolbar = PaginationWidget()
        self.pagination_toolbar.pageRequested.connect(self.table_widget.scrollToTop)
        layout.addWidget(self.pagination_toolbar)
        self.setLayout(layout)
        self.dictionary = None
        self.refresh_settings()
        self.requested_utterance_id = None

    def query_started(self):
        self.table_widget.setVisible(False)
        self.pagination_toolbar.setVisible(False)
        self.search_widget.setVisible(False)
        self.speaker_dropdown.setVisible(False)
        self.file_dropdown.setVisible(False)
        self.status_indicator.setVisible(True)

    def query_finished(self):
        self.table_widget.setVisible(True)
        self.pagination_toolbar.setVisible(True)
        self.search_widget.setVisible(True)
        self.speaker_dropdown.setVisible(True)
        self.file_dropdown.setVisible(True)
        self.status_indicator.setVisible(False)
        if self.requested_utterance_id is not None:
            self.selection_model.update_select(self.requested_utterance_id, reset=True)
        else:
            self.selection_model.clearSelection()

    def set_models(
        self,
        corpus_model: CorpusModel,
        selection_model: CorpusSelectionModel,
        speaker_model: SpeakerModel,
    ):
        self.corpus_model: CorpusModel = corpus_model
        self.selection_model: CorpusSelectionModel = selection_model
        self.table_widget.set_models(self.corpus_model, selection_model)
        self.search_box.validationError.connect(self.corpus_model.statusUpdate.emit)
        self.corpus_model.resultCountChanged.connect(self.pagination_toolbar.update_result_count)
        self.pagination_toolbar.offsetRequested.connect(self.corpus_model.set_offset)
        self.search_box.searchActivated.connect(self.query_started)
        self.corpus_model.newResults.connect(self.query_finished)
        self.corpus_model.speakersRefreshed.connect(self.speaker_dropdown.update_completions)
        self.corpus_model.filesRefreshed.connect(self.file_dropdown.update_completions)

    def refresh_settings(self):
        self.settings.sync()
        self.icon_delegate.refresh_settings()
        self.highlight_delegate.refresh_settings()
        self.nowrap_delegate.refresh_settings()
        # self.search_box.setStyleSheet(self.settings.search_box_style_sheet)
        # self.replace_box.setStyleSheet(self.settings.search_box_style_sheet)
        self.table_widget.refresh_settings()
        self.pagination_toolbar.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))

    def search(self):
        self.selection_model.clearSelection()
        query = self.search_box.query()
        query.graphemes = self.corpus_model.dictionary_model.graphemes
        self.pagination_toolbar.reset()
        self.corpus_model.current_offset = 0
        self.corpus_model.search(
            query,
            self.file_dropdown.current_text(),
            self.speaker_dropdown.current_text(),
            oovs=self.oov_button.isChecked(),
        )

    def replace(self):
        search_query = self.search_box.query()
        search_query.graphemes = self.corpus_model.dictionary_model.graphemes
        if not search_query.text:
            return
        replacement = self.replace_box.text()
        try:
            _ = re.sub(search_query.generate_expression(), replacement, "")
        except Exception as e:
            self.replace_box.setProperty("error", True)
            self.replace_box.style().unpolish(self.replace_box)
            self.replace_box.style().polish(self.replace_box)
            self.replace_box.update()
            self.corpus_model.statusUpdate.emit(f"Regex error: {e}")
            return
        self.corpus_model.replace_all(search_query, replacement)


class UtteranceDetailWidget(QtWidgets.QWidget):  # pragma: no cover
    lookUpWord = QtCore.Signal(object)
    createWord = QtCore.Signal(object)
    saveUtterance = QtCore.Signal(object, object)
    selectUtterance = QtCore.Signal(object, object)
    createUtterance = QtCore.Signal(object, object, object, object)
    refreshCorpus = QtCore.Signal(object)
    audioPlaying = QtCore.Signal(object)

    def __init__(self, parent: MainWindow):
        super(UtteranceDetailWidget, self).__init__(parent=parent)
        from anchor.main import AnchorSettings

        self.settings = AnchorSettings()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.corpus_model = None
        self.file_model = None
        self.selection_model = None
        self.dictionary_model = None
        self.plot_widget = UtteranceView(self)

        layout = QtWidgets.QVBoxLayout()
        self.scroll_bar_wrapper = QtWidgets.QHBoxLayout()
        self.pan_left_button = QtWidgets.QToolButton(self)
        self.pan_left_button.setObjectName("pan_left_button")
        self.scroll_bar_wrapper.addWidget(self.pan_left_button)
        self.pan_right_button = QtWidgets.QToolButton(self)
        self.pan_right_button.setObjectName("pan_right_button")
        self.pan_left_button.setIconSize(QtCore.QSize(25, 25))
        self.pan_right_button.setIconSize(QtCore.QSize(25, 25))

        self.scroll_bar = QtWidgets.QScrollBar(QtCore.Qt.Orientation.Horizontal, self)
        self.scroll_bar.setObjectName("time_scroll_bar")

        # self.scroll_bar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.scroll_bar.valueChanged.connect(self.update_from_slider)
        scroll_bar_layout = QtWidgets.QVBoxLayout()
        scroll_bar_layout.addWidget(self.scroll_bar, 1)
        self.scroll_bar_wrapper.addLayout(scroll_bar_layout)
        self.scroll_bar_wrapper.addWidget(self.pan_right_button)

        text_layout = QtWidgets.QHBoxLayout()

        layout.addWidget(self.plot_widget)
        layout.addLayout(self.scroll_bar_wrapper)
        layout.addLayout(text_layout)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        self.show_all_speakers = False

    def set_models(
        self,
        corpus_model: CorpusModel,
        file_model: FileUtterancesModel,
        selection_model: FileSelectionModel,
        dictionary_model: DictionaryTableModel,
    ):
        self.corpus_model = corpus_model
        self.file_model = file_model
        self.selection_model = selection_model
        self.dictionary_model = dictionary_model
        self.corpus_model.textFilterChanged.connect(self.plot_widget.set_search_term)
        self.selection_model.viewChanged.connect(self.update_to_slider)
        self.selection_model.fileChanged.connect(self.update_to_slider)
        self.plot_widget.set_models(
            corpus_model, file_model, selection_model, self.dictionary_model
        )

    def update_to_slider(self):
        with QtCore.QSignalBlocker(self.scroll_bar):
            if self.selection_model.model().file is None or self.selection_model.min_time is None:
                return
            if (
                self.selection_model.min_time == 0
                and self.selection_model.max_time == self.selection_model.model().file.duration
            ):
                self.scroll_bar.setPageStep(10)
                self.scroll_bar.setEnabled(False)
                self.pan_left_button.setEnabled(False)
                self.pan_right_button.setEnabled(False)
                self.scroll_bar.setMaximum(0)
                return
            duration_ms = int(self.selection_model.model().file.duration * 1000)
            begin = self.selection_model.min_time * 1000
            end = self.selection_model.max_time * 1000
            window_size_ms = int(end - begin)
            self.scroll_bar.setEnabled(True)
            self.pan_left_button.setEnabled(True)
            self.pan_right_button.setEnabled(True)
            self.scroll_bar.setPageStep(int(window_size_ms))
            self.scroll_bar.setSingleStep(int(window_size_ms * 0.5))
            self.scroll_bar.setMaximum(duration_ms - window_size_ms)
            self.scroll_bar.setValue(begin)

    def update_from_slider(self, value: int):
        self.selection_model.update_from_slider(value / 1000)

    def pan_left(self):
        self.scroll_bar.triggerAction(self.scroll_bar.SliderAction.SliderSingleStepSub)

    def pan_right(self):
        self.scroll_bar.triggerAction(self.scroll_bar.SliderAction.SliderSingleStepAdd)


class LoadingScreen(QtWidgets.QWidget):
    def __init__(self, *args, logo=True):
        super(LoadingScreen, self).__init__(*args)
        self.has_logo = logo
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.settings = AnchorSettings()
        layout = QtWidgets.QVBoxLayout()
        self.loading_movie = QtGui.QMovie(":loading_screen.gif")
        self.movie_label = QtWidgets.QLabel()
        if logo:
            self.movie_label.setMinimumSize(720, 576)

        self.movie_label.setMovie(self.loading_movie)

        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.movie_label)
        if logo:
            self.logo_icon = QtGui.QIcon(":logo_text.svg")

            self.logo_label = QtWidgets.QLabel()
            self.logo_label.setPixmap(self.logo_icon.pixmap(QtCore.QSize(720, 144)))

            self.logo_label.setFixedSize(720, 144)

            self.text_label = QtWidgets.QLabel()
            self.text_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.exit_label = QtWidgets.QLabel(
                "Wrapping things up before exit, please wait a moment..."
            )
            self.exit_label.setVisible(False)
            tool_bar_wrapper = QtWidgets.QVBoxLayout()
            self.tool_bar = QtWidgets.QToolBar()
            self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.tool_bar.addWidget(self.text_label)

            tool_bar_wrapper.addWidget(
                self.tool_bar, alignment=QtCore.Qt.AlignmentFlag.AlignCenter
            )

            self.setVisible(False)
            layout.addWidget(self.logo_label)
            layout.addWidget(self.text_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
            layout.addLayout(tool_bar_wrapper)
            layout.addWidget(self.exit_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setVisible(False)
        self.setLayout(layout)
        self.worker = None
        self.progress_bar = None

    def set_worker(self, worker):
        self.worker = worker

        if self.worker is None:
            return
        self.progress_bar = StoppableProgressBar(worker, 0)
        self.layout().addWidget(self.progress_bar)
        self.progress_bar.finished.connect(self.update_finished)

    def update_finished(self):
        self.worker = None
        if self.progress_bar is not None:
            self.layout().removeWidget(self.progress_bar)
            self.progress_bar.deleteLater()
            self.progress_bar = None

    def setExiting(self):
        self.tool_bar.setVisible(False)
        self.exit_label.setVisible(True)
        self.repaint()

    def setVisible(self, visible: bool) -> None:
        if visible:
            self.loading_movie.start()
        else:
            if self.has_logo:
                self.text_label.setText("")
            self.loading_movie.stop()
        super(LoadingScreen, self).setVisible(visible)

    def setCorpusName(self, corpus_name):
        self.text_label.setText(corpus_name)
        self.text_label.setVisible(True)


class TitleScreen(QtWidgets.QWidget):
    def __init__(self, *args):
        super(TitleScreen, self).__init__(*args)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QtWidgets.QVBoxLayout()
        self.logo_widget = QtSvgWidgets.QSvgWidget(":splash_screen.svg")
        self.logo_widget.setFixedSize(720, 720)
        # self.setMaximumSize(720, 720)

        # self.loading_label.setWindowFlag()
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.logo_widget)

        self.setLayout(layout)


class InternalToolButtonEdit(QtWidgets.QLineEdit):
    def __init__(self, *args):
        super().__init__(*args)

        self.tool_bar = QtWidgets.QToolBar(self)
        self._internal_layout.insertWidget(self._internal_layout.count(), self.tool_bar)
        self.tool_bar.setFocusProxy(self)

    @property
    def _internal_layout(self):
        if not hasattr(self, "_internal_layout_"):
            self._internal_layout_ = QtWidgets.QHBoxLayout(self)
            self._internal_layout_.addStretch()
        self._internal_layout_.setContentsMargins(1, 1, 1, 1)
        self._internal_layout_.setSpacing(0)
        return self._internal_layout_

    def setError(self):
        if not self.property("error"):
            self.setProperty("error", True)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

    def resetError(self):
        if self.property("error"):
            self.setProperty("error", False)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

    def _fix_cursor_position(self):
        self.setTextMargins(0, 0, self.tool_bar.geometry().width(), 0)

    def add_internal_action(self, action, name=None):
        self.tool_bar.addAction(action)
        w = self.tool_bar.widgetForAction(action)
        if name is not None:
            w.setObjectName(name)
        w.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        w.setFocusProxy(self)
        self._fix_cursor_position()


class ClearableField(InternalToolButtonEdit):
    def __init__(self, *args):
        super().__init__(*args)

        clear_icon = QtGui.QIcon.fromTheme("edit-clear")
        self.clear_action = QtGui.QAction(icon=clear_icon, parent=self)
        self.clear_action.triggered.connect(self.clear)
        self.clear_action.setVisible(False)
        self.textChanged.connect(self.check_contents)
        self.add_internal_action(self.clear_action, "clear_field")

    def clear(self) -> None:
        super().clear()
        self.returnPressed.emit()

    def add_button(self, button):
        self._internal_layout.insertWidget(self._internal_layout.count(), button)
        button.setFocusProxy(self)

    def check_contents(self):
        self.resetError()
        if super().text():
            self.clear_action.setVisible(True)
        else:
            self.clear_action.setVisible(False)


class ReplaceBox(ClearableField):
    replaceAllActivated = QtCore.Signal(object)

    def __init__(self, *args):
        super().__init__(*args)
        self.returnPressed.connect(self.activate)
        self.setObjectName("replace_box")

    def lock(self):
        self.setDisabled(True)

    def unlock(self):
        self.setEnabled(True)

    def activate(self):
        if not self.isEnabled():
            return
        self.replaceAllActivated.emit(self.text())


class SearchBox(ClearableField):
    searchActivated = QtCore.Signal(object)
    validationError = QtCore.Signal(object)

    def __init__(self, *args):
        super().__init__(*args)
        settings = AnchorSettings()
        self.returnPressed.connect(self.activate)
        self.setObjectName("search_box")

        self.clear_action.triggered.connect(self.returnPressed.emit)

        regex_icon = QtGui.QIcon()
        word_icon = QtGui.QIcon()
        case_icon = QtGui.QIcon()
        if (
            settings.theme_preset == "Native"
            and QtGui.QGuiApplication.styleHints().colorScheme() == QtCore.Qt.ColorScheme.Dark
        ):
            regex_icon.addFile(
                ":icons/anchor_dark/actions/edit-regex.svg",
                mode=QtGui.QIcon.Mode.Normal,
                state=QtGui.QIcon.State.Off,
            )
            word_icon.addFile(
                ":icons/anchor_dark/actions/edit-word.svg",
                mode=QtGui.QIcon.Mode.Normal,
                state=QtGui.QIcon.State.Off,
            )
            case_icon.addFile(
                ":icons/anchor_dark/actions/edit-case.svg",
                mode=QtGui.QIcon.Mode.Normal,
                state=QtGui.QIcon.State.Off,
            )
        else:
            regex_icon.addFile(
                ":icons/anchor_light/actions/edit-regex.svg",
                mode=QtGui.QIcon.Mode.Normal,
                state=QtGui.QIcon.State.Off,
            )
            word_icon.addFile(
                ":icons/anchor_light/actions/edit-word.svg",
                mode=QtGui.QIcon.Mode.Normal,
                state=QtGui.QIcon.State.Off,
            )
            case_icon.addFile(
                ":icons/anchor_light/actions/edit-case.svg",
                mode=QtGui.QIcon.Mode.Normal,
                state=QtGui.QIcon.State.Off,
            )
        regex_icon.addFile(
            ":icons/edit-regex-checked.svg",
            mode=QtGui.QIcon.Mode.Normal,
            state=QtGui.QIcon.State.On,
        )
        word_icon.addFile(
            ":icons/edit-word-checked.svg",
            mode=QtGui.QIcon.Mode.Normal,
            state=QtGui.QIcon.State.On,
        )
        case_icon.addFile(
            ":icons/edit-case-checked.svg",
            mode=QtGui.QIcon.Mode.Normal,
            state=QtGui.QIcon.State.On,
        )

        self.regex_action = QtGui.QAction(icon=regex_icon, parent=self)
        self.regex_action.setCheckable(True)

        self.word_action = QtGui.QAction(icon=word_icon, parent=self)
        self.word_action.setCheckable(True)

        self.case_action = QtGui.QAction(icon=case_icon, parent=self)
        self.case_action.setCheckable(True)

        self.add_internal_action(self.regex_action, "regex_search_field")
        self.add_internal_action(self.word_action, "word_search_field")
        self.add_internal_action(self.case_action, "case_search_field")

    def activate(self):
        if self.regex_action.isChecked():
            try:
                _ = re.compile(self.text())
            except Exception:
                self.setError()
                self.validationError.emit("Search regex not valid")
                return
        self.searchActivated.emit(self.query())

    def setQuery(self, query: TextFilterQuery):
        self.setText(query.text)
        with QtCore.QSignalBlocker(self.regex_action) as _, QtCore.QSignalBlocker(
            self.word_action
        ) as _:
            self.regex_action.setChecked(query.regex)
            self.word_action.setChecked(query.word)
            self.case_action.setChecked(query.case_sensitive)
            self.activate()

    def query(self) -> TextFilterQuery:
        filter = TextFilterQuery(
            super().text(),
            self.regex_action.isChecked(),
            self.word_action.isChecked(),
            self.case_action.isChecked(),
        )
        return filter


class HorizontalSpacer(QtWidgets.QWidget):
    def __init__(self, *args):
        super(HorizontalSpacer, self).__init__(*args)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred
        )


class NoWrapDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super(NoWrapDelegate, self).__init__(parent)
        self.doc = QtGui.QTextDocument(self)
        self.settings = AnchorSettings()

    def refresh_settings(self):
        self.settings.sync()
        # self.doc.setDefaultFont(self.settings.font)

    def sizeHint(
        self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex
    ) -> QtCore.QSize:
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        self.doc.setPlainText(options.text)
        style = (
            QtWidgets.QApplication.style() if options.widget is None else options.widget.style()
        )
        textRect = style.subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemText, options)

        if index.column() != 0:
            textRect.adjust(5, 0, 0, 0)

        the_constant = 4
        margin = (option.rect.height() - options.fontMetrics.height()) // 2
        margin = margin - the_constant
        textRect.setTop(textRect.top() + margin)
        return textRect.size()

    def paint(self, painter, option, index):
        selection_color = self.settings.PRIMARY_LIGHT_COLOR
        option.palette.setColor(
            QtGui.QPalette.ColorGroup.Active,
            QtGui.QPalette.ColorRole.Window,
            QtGui.QColor(selection_color),
        )
        painter.save()
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        self.doc.setPlainText(options.text)
        options.text = ""
        style = (
            QtWidgets.QApplication.style() if options.widget is None else options.widget.style()
        )
        style.drawControl(QtWidgets.QStyle.ControlElement.CE_ItemViewItem, options, painter)

        ctx = QtGui.QAbstractTextDocumentLayout.PaintContext()
        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QtGui.QColor(selection_color))
            ctx.palette.setColor(
                QtGui.QPalette.ColorRole.Text,
                option.palette.color(
                    QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorRole.HighlightedText
                ),
            )
        else:
            ctx.palette.setColor(
                QtGui.QPalette.ColorRole.Text,
                option.palette.color(
                    QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorRole.Text
                ),
            )

        textRect = style.subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemText, options)

        if index.column() != 0:
            textRect.adjust(5, 0, 0, 0)

        the_constant = 4
        margin = (option.rect.height() - options.fontMetrics.height()) // 2
        margin = margin - the_constant
        textRect.setTop(textRect.top() + margin)

        painter.translate(textRect.topLeft())
        painter.setClipRect(textRect.translated(-textRect.topLeft()))
        self.doc.documentLayout().draw(painter, ctx)

        painter.restore()


class HighlightDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super(HighlightDelegate, self).__init__(parent)
        self.doc = QtGui.QTextDocument(self)
        self.settings = AnchorSettings()
        self._filters = []
        self.current_doc_width = 100
        self.minimum_doc_size = 100
        self.margin = 5
        self.doc.setDocumentMargin(self.margin)

    def refresh_settings(self):
        self.settings.sync()
        # self.doc.setDefaultFont(self.settings.font)

    def sizeHint(
        self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex
    ) -> QtCore.QSize:
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        self.doc.setPlainText(options.text)
        self.apply_highlight()
        options.text = ""
        style = (
            QtWidgets.QApplication.style() if options.widget is None else options.widget.style()
        )
        textRect = style.subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemText, options)
        textRect.setWidth(self.current_doc_width)

        if textRect.width() < self.minimum_doc_size:
            textRect.setWidth(self.minimum_doc_size)

        self.doc.setTextWidth(textRect.width())
        doc_height = self.doc.documentLayout().documentSize().height()
        textRect.setHeight(doc_height)
        return textRect.size()

    def paint(self, painter, option, index):
        selection_color = self.settings.primary_very_light_color
        option.palette.setColor(
            QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorRole.Window, selection_color
        )
        painter.save()
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        self.doc.setPlainText(options.text)
        self.apply_highlight()
        options.text = ""
        style = (
            QtWidgets.QApplication.style() if options.widget is None else options.widget.style()
        )
        style.drawControl(QtWidgets.QStyle.ControlElement.CE_ItemViewItem, options, painter)

        ctx = QtGui.QAbstractTextDocumentLayout.PaintContext()
        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QtGui.QColor(selection_color))
            ctx.palette.setColor(
                QtGui.QPalette.ColorRole.Text,
                option.palette.color(
                    QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorRole.HighlightedText
                ),
            )
        else:
            ctx.palette.setColor(
                QtGui.QPalette.ColorRole.Text,
                option.palette.color(
                    QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorRole.Text
                ),
            )

        textRect = style.subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemText, options)

        textRect.setWidth(self.current_doc_width)
        if textRect.width() < self.minimum_doc_size:
            textRect.setWidth(self.minimum_doc_size)

        self.doc.setTextWidth(textRect.width())
        doc_height = self.doc.documentLayout().documentSize().height()
        textRect.setHeight(doc_height)

        painter.translate(textRect.topLeft())
        self.doc.documentLayout().draw(painter, ctx)

        painter.restore()

    def apply_highlight(self):
        cursor = QtGui.QTextCursor(self.doc)
        cursor.beginEditBlock()
        fmt = QtGui.QTextCharFormat()
        fmt.setBackground(self.settings.accent_light_color)
        fmt.setForeground(self.settings.primary_very_dark_color)
        for f in self.filters():
            f = QtCore.QRegExp(f)
            highlightCursor = QtGui.QTextCursor(self.doc)
            while not highlightCursor.isNull() and not highlightCursor.atEnd():
                highlightCursor = self.doc.find(f, highlightCursor)
                if not highlightCursor.isNull():
                    highlightCursor.mergeCharFormat(fmt)
        cursor.endEditBlock()

    @QtCore.Slot(list)
    def setFilters(self, filters):
        if self._filters == filters:
            return
        self._filters = filters

    def filters(self):
        return self._filters


class HeaderView(QtWidgets.QHeaderView):
    def __init__(self, *args):
        super(HeaderView, self).__init__(*args)
        self.settings = AnchorSettings()
        self.setHighlightSections(False)
        self.setStretchLastSection(True)
        self.setSortIndicatorShown(True)
        self.setSectionsClickable(True)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.generate_context_menu)

    def sectionSizeFromContents(self, logicalIndex: int) -> QtCore.QSize:
        size = super().sectionSizeFromContents(logicalIndex)
        size.setWidth(
            size.width() + self.settings.text_padding + 3 + self.settings.sort_indicator_padding
        )
        return size

    def showHideColumn(self):
        index = self.model()._header_data.index(self.sender().text())
        self.setSectionHidden(index, not self.isSectionHidden(index))

    def generate_context_menu(self, location):
        menu = QtWidgets.QMenu()
        menu.addSeparator()
        m: CorpusModel = self.model()
        section_index = self.logicalIndexAt(location)
        a = QtGui.QAction("Filter Nulls", self)
        a.setCheckable(True)
        a.setChecked(m.filter_nulls[section_index])
        a.toggled.connect(lambda x, y=section_index: m.update_filter_nulls(x, y))
        menu.addAction(a)
        for i in range(m.columnCount()):
            column_name = m.headerData(
                i,
                orientation=QtCore.Qt.Orientation.Horizontal,
                role=QtCore.Qt.ItemDataRole.DisplayRole,
            )
            a = QtGui.QAction(column_name, self)

            a.setCheckable(True)
            if not self.isSectionHidden(i):
                a.setChecked(True)
            a.triggered.connect(self.showHideColumn)
            menu.addAction(a)
        # menu.setStyleSheet(self.settings.menu_style_sheet)
        menu.exec_(self.mapToGlobal(location))


class IconDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        from anchor.main import AnchorSettings

        self.settings = AnchorSettings()

    def refresh_settings(self):
        self.settings.sync()

    def sizeHint(
        self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex
    ) -> QtCore.QSize:
        if index.column() != 0:
            return super().sizeHint(option, index)
        size = int(self.settings.icon_size / 2)
        return QtCore.QSize(size, size)

    def paint(self, painter: QtGui.QPainter, option, index) -> None:
        if index.column() != 0:
            return super().paint(painter, option, index)
        painter.save()
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        if options.checkState == QtCore.Qt.CheckState.Checked:
            icon = QtGui.QIcon(":oov-check.svg")
            icon.paint(painter, options.rect, QtCore.Qt.AlignmentFlag.AlignCenter)

        painter.restore()


class ModelIconDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        from anchor.main import AnchorSettings

        self.settings = AnchorSettings()
        self.icon_mapping = {
            "available": QtGui.QIcon.fromTheme("emblem-default"),
            "unavailable": QtGui.QIcon.fromTheme("emblem-important"),
            "remote": QtGui.QIcon.fromTheme("sync-synchronizing"),
            "unknown": QtGui.QIcon.fromTheme("emblem-unknown"),
        }

    def refresh_settings(self):
        self.settings.sync()

    def sizeHint(
        self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex
    ) -> QtCore.QSize:
        if index.column() != 0:
            return super().sizeHint(option, index)
        size = int(self.settings.icon_size / 2)
        return QtCore.QSize(size, size)

    def paint(self, painter: QtGui.QPainter, option, index) -> None:
        if index.column() != 0:
            return super().paint(painter, option, index)
        painter.save()
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        icon = self.icon_mapping[options.text]
        r = option.rect
        half_size = int(self.settings.icon_size / 2)
        x = r.left() + (r.width() / 2) - half_size
        y = r.top() + (r.height() / 2) - half_size
        options.rect = QtCore.QRect(x, y, self.settings.icon_size, self.settings.icon_size)
        icon.paint(
            painter,
            options.rect,
            QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.AlignmentFlag.AlignVCenter,
        )

        painter.restore()


class StoppableProgressBar(QtWidgets.QWidget):
    finished = QtCore.Signal(object)

    def __init__(self, worker: Worker, id, *args):
        super().__init__(*args)
        self.worker = worker
        self.id = id
        self.worker.signals.progress.connect(self.update_progress)
        self.worker.signals.total.connect(self.update_total)
        self.worker.signals.finished.connect(self.update_finished)
        layout = QtWidgets.QHBoxLayout()
        self.label = QtWidgets.QLabel(self.worker.name)
        layout.addWidget(self.label)
        self.progress_bar = QtWidgets.QProgressBar()
        layout.addWidget(self.progress_bar)
        self.cancel_button = QtWidgets.QToolButton()
        self.cancel_action = QtGui.QAction("select", self)
        self.cancel_action.setIcon(QtGui.QIcon.fromTheme("edit-clear"))
        self.cancel_action.triggered.connect(worker.cancel)
        self.cancel_button.setDefaultAction(self.cancel_action)
        layout.addWidget(self.cancel_button)
        self.setLayout(layout)

    def cancel(self):
        self.progress_bar.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.worker.stopped.stop()

    def update_finished(self):
        self.finished.emit(self.id)

    def update_total(self, total):
        self.progress_bar.setMaximum(total)

    def update_progress(self, progress, time_remaining):
        self.progress_bar.setFormat(f"%v of %m - %p% ({time_remaining} remaining)")
        self.progress_bar.setValue(progress)


class ProgressMenu(QtWidgets.QMenu):
    allDone = QtCore.Signal()

    def __init__(self, *args):
        super(ProgressMenu, self).__init__(*args)
        self.settings = AnchorSettings()
        layout = QtWidgets.QVBoxLayout()
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_layout = QtWidgets.QVBoxLayout()
        self.scroll_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setLayout(self.scroll_layout)
        layout.addWidget(self.scroll_area)
        self.scroll_area.setFixedWidth(
            500 + self.scroll_area.verticalScrollBar().sizeHint().width()
        )
        self.scroll_area.setFixedHeight(300)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.progress_bars: typing.Dict[int, StoppableProgressBar] = {}
        self.setLayout(layout)
        self.current_id = 0

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        p = self.pos()
        geo = self.parent().geometry()
        self.move(
            p.x() + geo.width() - self.geometry().width(),
            p.y() - geo.height() - self.geometry().height(),
        )

    def track_worker(self, worker: Worker):
        self.progress_bars[self.current_id] = StoppableProgressBar(worker, self.current_id)
        self.scroll_area.layout().addWidget(self.progress_bars[self.current_id])
        self.progress_bars[self.current_id].finished.connect(self.update_finished)
        self.current_id += 1

    def update_finished(self, id):
        self.scroll_layout.removeWidget(self.progress_bars[id])
        self.progress_bars[id].deleteLater()
        del self.progress_bars[id]
        if len(self.progress_bars) == 0:
            self.allDone.emit()


class ProgressWidget(QtWidgets.QPushButton):
    def __init__(self, *args):
        super().__init__(*args)
        self.done_icon = QtGui.QIcon.fromTheme("emblem-default")
        self.animated = QtGui.QMovie(":spinning_blue.svg")
        self.animated.frameChanged.connect(self.update_animation)
        self.setIcon(self.done_icon)
        self.menu = ProgressMenu(self)
        self.setMenu(self.menu)
        self.menu.allDone.connect(self.all_done)

    def add_worker(self, worker):
        self.menu.track_worker(worker)
        if self.animated.state() == QtGui.QMovie.MovieState.NotRunning:
            self.animated.start()

    def update_animation(self):
        self.setIcon(QtGui.QIcon(self.animated.currentPixmap()))

    def all_done(self):
        self.setIcon(self.done_icon)
        if self.animated.state() == QtGui.QMovie.MovieState.Running:
            self.animated.stop()


class SpeakerClusterSettingsMenu(QtWidgets.QMenu):
    def __init__(self, *args):
        super().__init__(*args)
        self.settings = AnchorSettings()
        self.settings.sync()
        layout = QtWidgets.QVBoxLayout()
        self.scroll_area = QtWidgets.QScrollArea()
        self.form_layout = QtWidgets.QFormLayout()
        self.form_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        self.metric_dropdown = QtWidgets.QComboBox()
        for m in DistanceMetric:
            if m is DistanceMetric.euclidean:
                continue
            self.metric_dropdown.addItem(m.name)

        self.row_indices = {}

        self.visualization_size_edit = QtWidgets.QSpinBox(self)
        self.visualization_size_edit.setMinimum(100)
        self.visualization_size_edit.setMaximum(5000)
        self.visualization_size_edit.setValue(500)
        self.form_layout.addRow("Visualization limit", self.visualization_size_edit)
        self.perplexity_edit = ThresholdWidget(self)
        self.form_layout.addRow("Perplexity", self.perplexity_edit)
        self.metric_dropdown.setCurrentIndex(
            self.metric_dropdown.findText(self.settings.value(self.settings.CLUSTERING_METRIC))
        )
        self.form_layout.addRow("Distance metric", self.metric_dropdown)
        self.distance_threshold_edit = ThresholdWidget(self)
        self.row_indices["distance_threshold"] = self.form_layout.rowCount()
        self.form_layout.addRow("Distance threshold", self.distance_threshold_edit)

        self.recluster_button = QtWidgets.QPushButton("Recluster")
        self.recluster_button.setEnabled(False)
        self.form_layout.addWidget(self.recluster_button)

        self.perplexity_edit.setValue(self.settings.value(self.settings.CLUSTERING_PERPLEXITY))
        self.distance_threshold_edit.setValue(
            self.settings.value(self.settings.CLUSTERING_DISTANCE_THRESHOLD)
        )
        self.scroll_area.setLayout(self.form_layout)
        layout.addWidget(self.scroll_area)
        self.scroll_area.setFixedWidth(
            500 + self.scroll_area.verticalScrollBar().sizeHint().width()
        )
        self.scroll_area.setFixedHeight(300)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLayout(layout)
        self.metric_dropdown.currentIndexChanged.connect(self.update_current_metric)

    def update_current_metric(self):
        metric = self.metric_dropdown.currentText()
        self.settings.setValue(self.settings.CLUSTERING_METRIC, metric)

    @property
    def cluster_kwargs(self):
        self.settings.sync()
        metric = DistanceMetric[self.settings.value(self.settings.CLUSTERING_METRIC)]
        kwargs = {
            "metric_type": metric,
            "limit": int(self.visualization_size_edit.value()),
        }

        val = self.distance_threshold_edit.value()
        self.settings.setValue(self.settings.CLUSTERING_DISTANCE_THRESHOLD, val)
        kwargs["distance_threshold"] = val

        return kwargs

    @property
    def manifold_kwargs(self):
        kwargs = {
            "metric_type": DistanceMetric[self.metric_dropdown.currentText()],
            "limit": int(self.visualization_size_edit.value()),
            "perplexity": float(self.perplexity_edit.value()),
        }

        val = self.distance_threshold_edit.value()
        self.settings.setValue(self.settings.CLUSTERING_DISTANCE_THRESHOLD, val)
        kwargs["distance_threshold"] = val

        return kwargs

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        p = self.pos()
        geo = self.parent().geometry()
        self.move(
            p.x() + geo.width() - self.geometry().width(),
            p.y() - geo.height() - self.geometry().height(),
        )


class SpeakerClusterSettingsWidget(QtWidgets.QPushButton):
    reclusterRequested = QtCore.Signal()

    def __init__(self, *args):
        super().__init__("Cluster settings", *args)
        self.menu = SpeakerClusterSettingsMenu(self)
        self.setMenu(self.menu)
        self.menu.recluster_button.clicked.connect(self.recluster)

    def recluster_available(self):
        self.menu.recluster_button.setEnabled(True)

    def recluster(self):
        self.menu.recluster_button.setEnabled(False)
        self.reclusterRequested.emit()


class IpaKeyboard(QtWidgets.QMenu):
    inputPhone = QtCore.Signal(object, object)

    def __init__(self, phones, parent=None):
        super().__init__(parent)
        self.settings = AnchorSettings()
        layout = QtWidgets.QHBoxLayout()
        self.scroll_area = QtWidgets.QScrollArea(self)
        self.scroll_area.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        widget = QtWidgets.QWidget(self)
        scroll_layout = QtWidgets.QGridLayout()
        self.scroll_area.setFixedHeight(300)
        column_count = 10
        self.buttons = [QtWidgets.QPushButton(p) for p in sorted(phones)]
        col_index = 0
        row_index = 0
        for b in self.buttons:
            b.clicked.connect(self.press)
            b.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            b.installEventFilter(self)

            scroll_layout.addWidget(b, row_index, col_index)
            col_index += 1
            if col_index >= column_count:
                col_index = 0
                row_index += 1
        layout.addWidget(self.scroll_area)
        scroll_layout.setContentsMargins(0,0,0,0)
        widget.setLayout(scroll_layout)
        self.scroll_area.setWidget(widget)
        self.setLayout(layout)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.scroll_area.setMinimumWidth(
            widget.sizeHint().width() + self.scroll_area.verticalScrollBar().sizeHint().width() + 1
        )
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(self.settings.keyboard_style_sheet)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.KeyPress:
            return True
        return super(IpaKeyboard, self).eventFilter(watched, event)

    def press(self):
        b: QtWidgets.QPushButton = self.sender()
        self.inputPhone.emit(b.text(), True)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        pos = self.parent().geometry().bottomLeft()
        p = self.parent().mapToGlobal(pos)

        geo = self.geometry()
        new_pos = int(p.x() - (geo.width() / 2))
        self.move(new_pos, p.y())


class PronunciationErrorHighlighter(QtGui.QSyntaxHighlighter):
    PHONES = r"\S+"

    def __init__(self, phones, *args):
        super().__init__(*args)
        self.phones = set(phones)
        self.settings = AnchorSettings()
        self.keyword_color = self.settings.error_color
        self.keyword_text_color = self.settings.primary_very_dark_color
        self.highlight_format = QtGui.QTextCharFormat()
        self.highlight_format.setBackground(self.keyword_color)
        self.highlight_format.setForeground(self.keyword_text_color)

    def highlightBlock(self, text):
        for phone_object in re.finditer(self.PHONES, text):
            if phone_object.group() not in self.phones:
                self.setFormat(
                    phone_object.start(),
                    phone_object.end() - phone_object.start(),
                    self.highlight_format,
                )


class PronunciationField(QtWidgets.QTextEdit):
    def __init__(self, parent, phones):
        super().__init__(parent)
        self.phones = phones
        self.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
        self.setWordWrapMode(QtGui.QTextOption.WrapMode.NoWrap)
        self.setObjectName("pronunciation_field")
        self.highlighter = PronunciationErrorHighlighter(self.phones, self.document())
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


class KeyboardWidget(QtWidgets.QPushButton):
    def __init__(self, phones, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        keyboard_icon = QtGui.QIcon.fromTheme("input-keyboard")
        self.setIcon(keyboard_icon)
        self.keyboard = IpaKeyboard(phones, self)
        self.setMenu(self.keyboard)

        self.clicked.connect(self.showMenu)
        
    def showMenu(self):
        self.menu().show()


class PronunciationInput(QtWidgets.QToolBar):
    validationError = QtCore.Signal(object)
    returnPressed = QtCore.Signal()

    PHONES = r"\S+"

    def __init__(self, phones, *args, icon_size=25):
        super().__init__(*args)
        self.phones = phones
        self.input = PronunciationField(self, phones)
        self.input.installEventFilter(self)
        self.input.textChanged.connect(self.check_accept)
        phone_set = "|".join(phones + [" "])
        self.validation_pattern = re.compile(rf"^({phone_set})+$")
        self.icon_size = icon_size
        self.original_text = None
        self.setContentsMargins(0, 0, 0, 0)
        self.setFocusProxy(self.input)

        accept_icon = QtGui.QIcon.fromTheme("emblem-default")

        self.accept_action = QtGui.QAction(icon=accept_icon, parent=self)
        self.accept_action.triggered.connect(self.returnPressed.emit)

        cancel_icon = QtGui.QIcon.fromTheme("edit-undo")

        self.cancel_action = QtGui.QAction(icon=cancel_icon, parent=self)
        self.cancel_action.triggered.connect(self.cancel)

        self.keyboard_widget = KeyboardWidget(phones, self)
        self.keyboard_widget.keyboard.installEventFilter(self)
        self.keyboard_widget.keyboard.inputPhone.connect(self.add_phone)

        self.addWidget(self.input)
        self.addWidget(self.keyboard_widget)
        self.addAction(self.accept_action)
        self.addAction(self.cancel_action)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if (
            isinstance(watched, (PronunciationField, IpaKeyboard))
            and event.type() == QtCore.QEvent.Type.KeyPress
            and event.key()
            in {QtGui.Qt.Key.Key_Enter, QtGui.Qt.Key.Key_Return, QtGui.Qt.Key.Key_Tab}
        ):
            if self.accept_action.isEnabled():
                self.returnPressed.emit()
            return True
        elif (
            isinstance(watched, IpaKeyboard)
            and event.type() == QtCore.QEvent.Type.KeyPress
            and event.key() not in {QtGui.Qt.Key.Key_Escape}
        ):
            self.input.keyPressEvent(event)
            return True
        return super(PronunciationInput, self).eventFilter(watched, event)

    def check_accept(self):
        self.accept_action.setEnabled(self.validate())
        self.cancel_action.setEnabled(self.original_text != self.text())

    def sanitize(self, text):
        return text.replace()

    def add_phone(self, phone, full_phone):
        if full_phone:
            cursor = self.input.textCursor()
            current_pos = cursor.position()
            cursor.movePosition(
                QtGui.QTextCursor.MoveOperation.Right, QtGui.QTextCursor.MoveMode.KeepAnchor
            )
            if cursor.selectedText() != " ":
                phone = phone + " "

            cursor.setPosition(current_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
            cursor.movePosition(
                QtGui.QTextCursor.MoveOperation.Left, QtGui.QTextCursor.MoveMode.KeepAnchor
            )
            if cursor.selectedText() != " ":
                phone = " " + phone
            cursor.setPosition(current_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
        self.input.insertPlainText(phone)

    def sizeHint(self) -> QtCore.QSize:
        size = super().sizeHint()
        size.setHeight(self.icon_size)
        return size

    def setText(self, text: str):
        if self.original_text is None:
            self.original_text = text
        self.input.setPlainText(text)

    def text(self) -> str:
        return self.input.toPlainText()

    def validate(self) -> bool:
        for phone_object in re.finditer(self.PHONES, self.text()):
            if phone_object.group() not in self.phones:
                return False
        return True

    def cancel(self):
        self.setText(self.original_text)


class WordInput(QtWidgets.QLineEdit):
    def __init__(self, *args):
        super().__init__(*args)
        self.original_text = None
        self.setFrame(False)

    def setText(self, text: str):
        if self.original_text is None:
            self.original_text = text
        super().setText(text)

    def cancel(self):
        self.setText(self.original_text)


class CountDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        from anchor.main import AnchorSettings

        self.settings = AnchorSettings()

    def refresh_settings(self):
        self.settings.sync()

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> None:
        super().paint(painter, option, index)
        painter.save()
        r = option.rect
        half_size = int(self.settings.icon_size / 2)
        x = r.left() + r.width() - self.settings.icon_size
        y = r.top() + (r.height() / 2) - half_size
        options = QtWidgets.QStyleOptionViewItem(option)
        options.rect = QtCore.QRect(x, y, self.settings.icon_size, self.settings.icon_size)
        self.initStyleOption(options, index)
        icon = QtGui.QIcon.fromTheme("folder-open")
        icon.paint(
            painter,
            options.rect,
            QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.AlignmentFlag.AlignVCenter,
        )

        painter.restore()


class WordTypeDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        from anchor.main import AnchorSettings

        self.settings = AnchorSettings()

    def refresh_settings(self):
        self.settings.sync()

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> None:
        super().paint(painter, option, index)
        painter.save()
        r = option.rect
        half_size = int(self.settings.icon_size / 2)
        x = r.left() + r.width() - self.settings.icon_size
        y = r.top() + (r.height() / 2) - half_size
        options = QtWidgets.QStyleOptionViewItem(option)
        options.rect = QtCore.QRect(x, y, self.settings.icon_size, self.settings.icon_size)
        self.initStyleOption(options, index)
        icon = QtGui.QIcon.fromTheme("sync-synchronizing")
        icon.paint(
            painter,
            options.rect,
            QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.AlignmentFlag.AlignVCenter,
        )

        painter.restore()


class EditableDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        from anchor.main import AnchorSettings

        self.settings = AnchorSettings()

    def refresh_settings(self):
        self.settings.sync()

    def createEditor(
        self,
        parent: DictionaryTableView,
        option: QtWidgets.QStyleOptionViewItem,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> QtWidgets.QWidget:
        editor = WordInput(parent)
        # editor.setStyleSheet(self.settings.search_box_style_sheet)
        # editor.setFont(self.settings.font)
        return editor

    def setEditorData(
        self,
        editor: WordInput,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> None:
        editor.setText(index.model().data(index, QtCore.Qt.ItemDataRole.EditRole))

    def setModelData(
        self,
        editor: WordInput,
        model: DictionaryTableModel,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> None:
        value = editor.text().strip()
        if editor.original_text != value:
            model.setData(index, value, QtCore.Qt.ItemDataRole.EditRole)
            model.submit()

    def updateEditorGeometry(
        self,
        editor: WordInput,
        option: QtWidgets.QStyleOptionViewItem,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> None:
        editor.setGeometry(option.rect)


class PronunciationDelegate(EditableDelegate):
    def eventFilter(self, object: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.KeyPress:
            if isinstance(object, PronunciationInput) or isinstance(
                object.parent(), PronunciationInput
            ):
                if isinstance(object.parent(), PronunciationInput):
                    object = object.parent()
                if event.key() in {
                    QtGui.Qt.Key.Key_Enter,
                    QtGui.Qt.Key.Key_Return,
                    QtGui.Qt.Key.Key_Tab,
                }:
                    self.commitData.emit(object)
                    return True
        return super().eventFilter(object, event)

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> QtCore.QSize:
        size = super().sizeHint(option, index)
        size.setHeight(self.settings.icon_size)
        return size

    def createEditor(
        self,
        parent: DictionaryTableView,
        option: QtWidgets.QStyleOptionViewItem,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> QtWidgets.QWidget:
        m: DictionaryTableModel = index.model()
        self.view = parent.parent()
        editor = PronunciationInput(m.phones, parent)
        # editor.setStyleSheet(self.settings.search_box_style_sheet)
        # editor.setFont(self.settings.font)
        editor.installEventFilter(self)
        editor.returnPressed.connect(self.accept)
        editor.input.setFocus()
        return editor

    def accept(self):
        editor = self.sender()
        if editor.validate():
            self.commitData.emit(editor)
            self.closeEditor.emit(editor)

    def setModelData(
        self,
        editor: PronunciationInput,
        model: DictionaryTableModel,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> None:
        if editor.validate():
            value = editor.text().strip()
            if editor.original_text != value:
                model.setData(index, value, QtCore.Qt.ItemDataRole.EditRole)
                model.submit()


class OovTableView(AnchorTableView):
    searchRequested = QtCore.Signal(object)
    g2pRequested = QtCore.Signal(object, object)

    def __init__(self, *args):
        super().__init__(*args)
        self.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
            | QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked
        )
        self.doubleClicked.connect(self.search_word)
        self.count_delegate = CountDelegate(self)
        self.setItemDelegateForColumn(1, self.count_delegate)
        self.add_pronunciation_action = QtGui.QAction("Add pronunciation", self)
        self.add_pronunciation_action.triggered.connect(self.add_pronunciation)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.generate_context_menu)
        self.oov_model: typing.Optional[OovModel] = None

    def generate_context_menu(self, location):
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(self.settings.menu_style_sheet)
        menu.addAction(self.add_pronunciation_action)
        menu.exec_(self.mapToGlobal(location))

    def add_pronunciation(self):
        rows = self.selectionModel().selectedRows()
        if not rows:
            return
        word = self.oov_model.data(
            self.oov_model.createIndex(rows[0].row(), 0), QtCore.Qt.ItemDataRole.DisplayRole
        )
        word_id = self.oov_model.indices[rows[0].row()]
        self.g2pRequested.emit(word, word_id)
        self.oov_model.refresh()

    def set_models(self, oov_model: OovModel):
        self.oov_model = oov_model
        self.setModel(self.oov_model)
        self.refresh_settings()
        self.horizontalHeader().sortIndicatorChanged.connect(self.model().update_sort)

    def search_word(self, index: QtCore.QModelIndex):
        if not index.isValid() or index.column() != 1:
            return
        word_index = self.oov_model.index(index.row(), 0)
        word = self.oov_model.data(word_index, QtCore.Qt.ItemDataRole.DisplayRole)
        query = TextFilterQuery(word, False, True, False)
        self.searchRequested.emit(query)


class DictionaryTableView(AnchorTableView):
    searchRequested = QtCore.Signal(object)

    def __init__(self, *args):
        super().__init__(*args)
        self.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
            | QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked
        )
        self.doubleClicked.connect(self.search_word)
        self.edit_delegate = EditableDelegate(self)
        self.word_type_delegate = WordTypeDelegate(self)
        self.count_delegate = CountDelegate(self)
        self.pronunciation_delegate = PronunciationDelegate(self)
        self.setItemDelegateForColumn(0, self.edit_delegate)
        self.setItemDelegateForColumn(1, self.word_type_delegate)
        self.setItemDelegateForColumn(2, self.count_delegate)
        self.setItemDelegateForColumn(3, self.pronunciation_delegate)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.delete_words_action = QtGui.QAction("Delete words", self)
        self.delete_pronunciations_action = QtGui.QAction("Delete pronunciations", self)
        self.add_pronunciation_action = QtGui.QAction("Add pronunciation", self)
        self.add_pronunciation_action.triggered.connect(self.add_pronunciation)
        self.delete_pronunciations_action.triggered.connect(self.delete_pronunciations)
        self.delete_words_action.triggered.connect(self.delete_words)
        self.customContextMenuRequested.connect(self.generate_context_menu)

    def generate_context_menu(self, location):
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(self.settings.menu_style_sheet)
        menu.addAction(self.add_pronunciation_action)
        menu.addSeparator()
        menu.addAction(self.delete_words_action)
        menu.addAction(self.delete_pronunciations_action)
        menu.exec_(self.mapToGlobal(location))

    def delete_pronunciations(self):
        rows = self.selectionModel().selectedRows(2)
        if not rows:
            return
        pronunciation_ids = [self.dictionary_model.pron_indices[x.row()] for x in rows]
        self.dictionary_model.delete_pronunciations(pronunciation_ids)

    def delete_words(self):
        rows = self.selectionModel().selectedRows(0)
        if not rows:
            return
        word_ids = [self.dictionary_model.word_indices[x.row()] for x in rows]
        self.dictionary_model.delete_words(word_ids)

    def add_pronunciation(self):
        rows = self.selectionModel().selectedRows()
        if not rows:
            return
        word_id = self.dictionary_model.word_indices[rows[0].row()]
        word = self.dictionary_model.data(
            self.dictionary_model.createIndex(rows[0].row(), 0), QtCore.Qt.ItemDataRole.DisplayRole
        )
        self.dictionary_model.add_pronunciation(word, word_id)

    def set_models(self, dictionary_model: DictionaryTableModel):
        self.dictionary_model = dictionary_model
        self.setModel(self.dictionary_model)
        self.refresh_settings()
        self.horizontalHeader().sortIndicatorChanged.connect(self.model().update_sort)
        self.dictionary_model.newResults.connect(self.calculate_spans)

    def calculate_spans(self):
        for i in range(self.dictionary_model.rowCount()):
            if self.rowSpan(i, 0) != 1:
                self.setSpan(i, 0, 1, 1)
                self.setSpan(i, 1, 1, 1)
            if (
                i > 0
                and self.dictionary_model.word_indices[i - 1]
                == self.dictionary_model.word_indices[i]
            ):
                prev_span = self.rowSpan(i - 1, 0)
                self.setSpan(i - prev_span, 0, prev_span + 1, 1)
                self.setSpan(i - prev_span, 1, prev_span + 1, 1)

    def search_word(self, index: QtCore.QModelIndex):
        if not index.isValid():
            return
        if index.column() == 1:
            rows = self.selectionModel().selectedRows()
            if not rows:
                return
            word_id = self.dictionary_model.word_indices[rows[0].row()]
            current_word_type = self.dictionary_model.data(
                self.dictionary_model.createIndex(rows[0].row(), 1),
                QtCore.Qt.ItemDataRole.DisplayRole,
            )
            self.dictionary_model.change_word_type(word_id, WordType[current_word_type])

        elif index.column() == 2:
            word_index = self.dictionary_model.index(index.row(), 0)
            word = self.dictionary_model.data(word_index, QtCore.Qt.ItemDataRole.DisplayRole)
            query = TextFilterQuery(word, False, True, False)
            self.searchRequested.emit(query)


class SpeakerTableView(AnchorTableView):
    searchRequested = QtCore.Signal(object)

    def __init__(self, *args):
        super().__init__(*args)
        self.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
            | QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked
        )
        self.speaker_model: SpeakerModel = None
        self.view_delegate = ButtonDelegate("edit-find", self)
        self.edit_delegate = EditableDelegate(self)
        self.speaker_delegate = UtteranceCountDelegate(self)
        self.setItemDelegateForColumn(1, self.speaker_delegate)
        self.setItemDelegateForColumn(0, self.edit_delegate)
        self.setItemDelegateForColumn(4, self.view_delegate)
        # self.setItemDelegateForColumn(5, self.delete_delegate)
        self.clicked.connect(self.cluster_utterances)
        self.doubleClicked.connect(self.search_speaker)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)

        self.customContextMenuRequested.connect(self.generate_context_menu)
        self.add_speaker_action = QtGui.QAction("Compare speakers", self)
        self.add_speaker_action.triggered.connect(self.add_speakers)
        self.break_up_speaker_action = QtGui.QAction("Break up speaker", self)
        self.break_up_speaker_action.triggered.connect(self.break_up_speaker)

    def add_speakers(self):
        selected_rows = self.selectionModel().selectedRows(0)
        if not selected_rows:
            return
        speakers = [self.speaker_model.speakerAt(index.row()) for index in selected_rows]
        self.speaker_model.change_current_speaker(speakers)

    def break_up_speaker(self):
        index = self.selectionModel().currentIndex()
        if not index or not index.isValid():
            return
        speaker_id = self.speaker_model.speakerAt(index.row())
        speaker_name = self.speaker_model.data(index, QtCore.Qt.ItemDataRole.DisplayRole)
        dialog = ConfirmationDialog(
            "Break up speaker confirmation",
            f"Are you sure you want to break up {speaker_name}?",
            self,
        )
        if dialog.exec_():
            self.speaker_model.break_up_speaker(speaker_id)

    def generate_context_menu(self, location):
        menu = QtWidgets.QMenu(self)
        # menu.setStyleSheet(self.settings.menu_style_sheet)
        menu.addAction(self.add_speaker_action)
        menu.addSeparator()
        menu.addAction(self.break_up_speaker_action)
        menu.exec_(self.mapToGlobal(location))

    def set_models(self, model: SpeakerModel):
        self.speaker_model = model
        self.setModel(model)
        self.refresh_settings()

    def cluster_utterances(self, index: QtCore.QModelIndex):
        if not index.isValid() or index.column() < 4:
            return
        if index.column() == 4:
            self.speaker_model.change_current_speaker(self.speaker_model.speakerAt(index.row()))

    def search_speaker(self, index: QtCore.QModelIndex):
        if index.isValid() and index.column() == 1:
            speaker = self.model().data(
                self.model().index(index.row(), 0), QtCore.Qt.ItemDataRole.DisplayRole
            )
            self.searchRequested.emit(speaker)


class ModelInfoWidget(QtWidgets.QWidget):
    def __init__(self, model_type, *args):
        super().__init__(*args)
        self.model_type = model_type
        self.settings = AnchorSettings()
        self.label = QtWidgets.QLineEdit(f"No {model_type} loaded")
        self.path_label = QtWidgets.QLineEdit("")
        self.label.setReadOnly(True)
        self.path_label.setReadOnly(True)
        self.tree = QtWidgets.QTreeWidget()
        self.header = HeaderView(QtCore.Qt.Orientation.Horizontal, self)
        self.header.setSectionsClickable(False)
        self.header.setSortIndicatorShown(False)
        self.tree.setHeader(self.header)
        self.tree.setAlternatingRowColors(True)
        self.setLayout(QtWidgets.QVBoxLayout())
        info_layout = QtWidgets.QFormLayout()
        name_label = QtWidgets.QLabel(model_type.title())
        # name_label.setFont(self.settings.font)
        info_layout.addRow(name_label, self.label)
        path_label = QtWidgets.QLabel("Path")
        # path_label.setFont(self.settings.font)
        info_layout.addRow(path_label, self.path_label)
        self.layout().setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.layout().addLayout(info_layout)
        self.layout().addWidget(self.tree)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Property", "Value"])
        self.tree.setIndentation(25)
        self.header.setDefaultSectionSize(200)
        self.corpus_model = None
        self.model = None
        # self.label.setFont(self.settings.font)
        # self.path_label.setFont(self.settings.font)
        # self.path_label.setWordWrap(True)

    def refresh(self):
        self.tree.clear()
        if self.model is not None and isinstance(self.model, Archive):
            self.label.setText(self.model.name)
            self.path_label.setText(str(self.model.source))
            meta = self.model.meta
            for k, v in meta.items():
                node = QtWidgets.QTreeWidgetItem(self.tree)

                label = QtWidgets.QLabel(str(k))
                # label.setFont(self.settings.font)
                self.tree.setItemWidget(node, 0, label)
                if isinstance(v, dict):
                    for k2, v2 in v.items():
                        child_node = QtWidgets.QTreeWidgetItem(node)

                        label = QtWidgets.QLabel(str(k2))
                        # label.setFont(self.settings.font)
                        self.tree.setItemWidget(child_node, 0, label)

                        label = QtWidgets.QLabel(str(v2))
                        label.setWordWrap(True)
                        # label.setFont(self.settings.font)
                        self.tree.setItemWidget(child_node, 1, label)
                else:
                    label = QtWidgets.QLabel(str(v))
                    label.setWordWrap(True)
                    # label.setFont(self.settings.font)
                    self.tree.setItemWidget(node, 1, label)
        else:
            self.label.setText(f"No {self.model_type} loaded")
            self.path_label.setText("")


class AcousticModelWidget(ModelInfoWidget):
    def __init__(self, *args):
        super().__init__("acoustic model", *args)

    def change_model(self):
        self.model = None
        if self.corpus_model is not None:
            self.model = self.corpus_model.acoustic_model
        self.refresh()

    def set_models(self, corpus_model: CorpusModel):
        self.corpus_model = corpus_model
        self.corpus_model.acousticModelChanged.connect(self.change_model)


class LanguageModelWidget(ModelInfoWidget):
    def __init__(self, *args):
        super().__init__("language model", *args)

    def change_model(self):
        self.model = None
        if self.corpus_model is not None:
            self.model = self.corpus_model.language_model
        self.refresh()

    def set_models(self, corpus_model: CorpusModel):
        self.corpus_model = corpus_model
        self.corpus_model.languageModelChanged.connect(self.change_model)


class G2PModelWidget(ModelInfoWidget):
    def __init__(self, *args):
        super().__init__("G2P model", *args)

    def change_model(self):
        self.model = None
        if self.corpus_model is not None:
            self.model = self.corpus_model.g2p_model
        self.refresh()

    def set_models(self, corpus_model: CorpusModel):
        self.corpus_model = corpus_model
        self.corpus_model.g2pModelChanged.connect(self.change_model)


class TranscriberWidget(QtWidgets.QWidget):
    def __init__(self, *args):
        super().__init__(*args)
        self.button = QtWidgets.QToolButton()
        layout = QtWidgets.QFormLayout()
        self.acoustic_model_label = QtWidgets.QLabel("Not loaded")
        self.dictionary_label = QtWidgets.QLabel("Not loaded")
        self.language_model_label = QtWidgets.QLabel("Not loaded")
        self.frequent_words_edit = QtWidgets.QSpinBox()
        self.frequent_words_edit.setMinimum(10)
        self.frequent_words_edit.setMaximum(1000)
        self.frequent_words_edit.setValue(100)
        self.frequent_words_edit.setEnabled(False)
        layout.addRow(QtWidgets.QLabel("Acoustic model"), self.acoustic_model_label)
        layout.addRow(QtWidgets.QLabel("Dictionary"), self.dictionary_label)
        layout.addRow(QtWidgets.QLabel("Language model"), self.language_model_label)
        layout.addRow(QtWidgets.QLabel("Target number of ngrams"), self.frequent_words_edit)
        layout.addWidget(self.button)
        self.text = QtWidgets.QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        self.setLayout(layout)
        self.corpus_model: Optional[CorpusModel] = None

    def refresh(self):
        validate_enabled = True
        if self.corpus_model.corpus is None:
            return
        dataset_type = inspect_database(self.corpus_model.corpus.identifier)
        if dataset_type in {
            DatasetType.ACOUSTIC_CORPUS_WITH_DICTIONARY,
            DatasetType.TEXT_CORPUS_WITH_DICTIONARY,
        }:
            self.dictionary_label.setText(self.corpus_model.corpus.dictionary_model.name)
        else:
            validate_enabled = False
            self.dictionary_label.setText("Not loaded")
        if isinstance(self.corpus_model.acoustic_model, AcousticModel):
            self.acoustic_model_label.setText(self.corpus_model.acoustic_model.name)
        else:
            validate_enabled = False
            self.acoustic_model_label.setText("Not loaded")
        if self.corpus_model.language_model is not None:
            self.language_model_label.setText(self.corpus_model.language_model.name)
        else:
            self.language_model_label.setText("Not loaded")
        self.frequent_words_edit.setEnabled(validate_enabled)
        self.button.defaultAction().setEnabled(validate_enabled)

    def set_models(self, corpus_model: CorpusModel, dictionary_model: DictionaryTableModel):
        self.corpus_model = corpus_model
        self.dictionary_model = dictionary_model
        self.corpus_model.dictionaryChanged.connect(self.refresh)
        self.corpus_model.acousticModelChanged.connect(self.refresh)
        self.corpus_model.languageModelChanged.connect(self.refresh)


class UtteranceCountDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        from anchor.main import AnchorSettings

        self.settings = AnchorSettings()

    def refresh_settings(self):
        self.settings.sync()

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> None:
        super().paint(painter, option, index)
        m = index.model()
        if not m.data(index, QtCore.Qt.ItemDataRole.DisplayRole):
            return
        painter.save()

        r = option.rect
        size = int(self.settings.icon_size / 2)
        half_size = int(size / 2)
        x = r.left() + r.width() - size
        y = r.top() + (r.height() / 2) - half_size
        options = QtWidgets.QStyleOptionViewItem(option)
        options.rect = QtCore.QRect(x, y, size, size)
        self.initStyleOption(options, index)
        icon = QtGui.QIcon.fromTheme("folder-open")
        icon.paint(painter, options.rect, QtCore.Qt.AlignmentFlag.AlignCenter)

        painter.restore()


class SpeakerCycleDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        from anchor.main import AnchorSettings

        self.settings = AnchorSettings()

    def refresh_settings(self):
        self.settings.sync()

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> None:
        super().paint(painter, option, index)

        m: DiarizationModel = index.model()
        if hasattr(m, "can_cycle") and not m.can_cycle(index):
            return
        painter.save()
        r = option.rect
        size = int(self.settings.icon_size / 2)
        half_size = int(size / 2)
        x = r.left() + r.width() - size
        y = r.top() + (r.height() / 2) - half_size
        options = QtWidgets.QStyleOptionViewItem(option)
        options.rect = QtCore.QRect(x, y, size, size)
        self.initStyleOption(options, index)
        icon = QtGui.QIcon.fromTheme("sync-synchronizing")
        icon.paint(painter, options.rect, QtCore.Qt.AlignmentFlag.AlignCenter)

        painter.restore()


class ButtonDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, icon_path, parent=None):
        super().__init__(parent)
        from anchor.main import AnchorSettings

        self.settings = AnchorSettings()
        self.icon_path = icon_path

    def refresh_settings(self):
        self.settings.sync()

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> None:
        painter.save()
        r = option.rect
        half_size = int(self.settings.icon_size / 2)
        x = r.left() + r.width() - self.settings.icon_size
        y = r.top() + (r.height() / 2) - half_size
        options = QtWidgets.QStyleOptionViewItem(option)
        options.rect = QtCore.QRect(x, y, self.settings.icon_size, self.settings.icon_size)
        self.initStyleOption(options, index)
        icon = QtGui.QIcon.fromTheme(self.icon_path)
        icon.paint(painter, options.rect, QtCore.Qt.AlignmentFlag.AlignCenter)

        painter.restore()


class SpeakerClustersWidget(QtWidgets.QWidget):
    search_requested = QtCore.Signal(object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.speaker_model = None
        self.settings = AnchorSettings()
        self.settings.sync()
        form_layout = QtWidgets.QHBoxLayout()
        self.cluster_settings_widget = SpeakerClusterSettingsWidget(self)

        self.search_button = QtWidgets.QPushButton("Search on selection")
        self.button = QtWidgets.QPushButton("Change speaker")
        form_layout.addWidget(self.search_button)
        form_layout.addWidget(self.button)
        self.search_button.clicked.connect(self.search_speaker)
        self.button.clicked.connect(self.change_speaker)
        self.plot_widget = UtteranceClusterView(self)
        self.cluster_settings_widget.reclusterRequested.connect(self.recluster)
        self.plot_widget.plotAvailable.connect(self.cluster_settings_widget.recluster_available)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.cluster_settings_widget)
        layout.addWidget(self.plot_widget)
        layout.addLayout(form_layout)
        self.setLayout(layout)

    def recluster(self):
        self.speaker_model.update_manifold_kwargs(
            self.cluster_settings_widget.menu.manifold_kwargs
        )
        self.speaker_model.update_cluster_kwargs(self.cluster_settings_widget.menu.cluster_kwargs)

    def search_speaker(self):
        if not self.plot_widget.selected_indices:
            return
        indices = np.array(list(self.plot_widget.selected_indices))
        mean_ivector = np.mean(self.speaker_model.ivectors[indices, :], axis=0)
        kaldi_ivector = DoubleVector()
        kaldi_ivector.from_numpy(mean_ivector)
        ivector_normalize_length(kaldi_ivector)
        self.search_requested.emit(kaldi_ivector.numpy())

    def change_speaker(self):
        if not self.plot_widget.updated_indices:
            return
        data = []
        for index in self.plot_widget.updated_indices:
            u_id = int(self.speaker_model.utterance_ids[index])
            data.append(
                [
                    u_id,
                    self.speaker_model.utt2spk[u_id],
                    int(self.speaker_model.cluster_labels[index]),
                ]
            )
        self.speaker_model.change_speakers(data, self.speaker_model.current_speakers[0])
        self.plot_widget.updated_indices = set()
        self.plot_widget.selected_indices = set()

    def set_models(
        self,
        corpus_model: CorpusModel,
        selection_model: CorpusSelectionModel,
        speaker_model: SpeakerModel,
    ):
        self.speaker_model = speaker_model
        self.speaker_model.update_manifold_kwargs(
            self.cluster_settings_widget.menu.manifold_kwargs
        )
        self.speaker_model.update_cluster_kwargs(self.cluster_settings_widget.menu.cluster_kwargs)
        self.plot_widget.set_models(corpus_model, selection_model, speaker_model)


class DiarizationTable(AnchorTableView):
    utteranceSearchRequested = QtCore.Signal(object, object)
    speakerSearchRequested = QtCore.Signal(object)
    referenceUtteranceSelected = QtCore.Signal(object)

    def __init__(self, *args):
        super().__init__(*args)
        self.setSortingEnabled(False)
        self.count_delegate = UtteranceCountDelegate(self)
        self.speaker_delegate = SpeakerCycleDelegate(self)
        self.button_delegate = ButtonDelegate("format-justify-center", self)
        self.setItemDelegateForColumn(0, self.count_delegate)
        self.setItemDelegateForColumn(1, self.speaker_delegate)
        self.setItemDelegateForColumn(2, self.count_delegate)
        self.setItemDelegateForColumn(4, self.count_delegate)
        self.setItemDelegateForColumn(6, self.button_delegate)
        self.setItemDelegateForColumn(7, self.button_delegate)
        self.doubleClicked.connect(self.search_utterance)
        self.clicked.connect(self.reassign_utterance)
        self.diarization_model: Optional[DiarizationModel] = None
        self.selection_model: Optional[FileSelectionModel] = None
        self.set_reference_utterance_action = QtGui.QAction("Use utterance as reference", self)
        self.set_reference_utterance_action.triggered.connect(self.set_reference_utterance)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.generate_context_menu)

    def generate_context_menu(self, location):
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(self.settings.menu_style_sheet)
        menu.addAction(self.set_reference_utterance_action)
        menu.exec_(self.mapToGlobal(location))

    def set_reference_utterance(self):
        rows = self.selectionModel().selectedRows()
        if not rows:
            return
        utterance_id = self.diarization_model.utterance_ids[rows[0].row()]
        self.diarization_model.set_utterance_filter(utterance_id)
        self.referenceUtteranceSelected.emit(
            self.diarization_model.data(
                self.diarization_model.createIndex(rows[0].row(), 0),
                QtCore.Qt.ItemDataRole.DisplayRole,
            )
        )

    def set_models(self, model: DiarizationModel, selection_model: FileSelectionModel):
        self.diarization_model = model
        self.selection_model = selection_model
        self.setModel(model)
        self.refresh_settings()

    def reassign_utterance(self, index: QtCore.QModelIndex):
        if not index.isValid() or index.column() < 6:
            return
        if index.column() == 6:
            self.diarization_model.reassign_utterance(index.row())
        elif index.column() == 7:
            self.diarization_model.merge_speakers(index.row())

    def search_utterance(self, index: QtCore.QModelIndex):
        if not index.isValid() or index.column() not in {0, 1, 2, 3, 4}:
            return
        if index.column() == 1:
            row = index.row()
            self.diarization_model.change_suggested_speaker(row)
        if index.column() == 0:
            row = index.row()
            utterance_id = self.diarization_model.utterance_ids[row]
            if utterance_id is None:
                return
            with self.diarization_model.corpus_model.corpus.session() as session:
                try:
                    file_id, begin, end, speaker_id = (
                        session.query(
                            Utterance.file_id, Utterance.begin, Utterance.end, Utterance.speaker_id
                        )
                        .filter(Utterance.id == utterance_id)
                        .first()
                    )
                except TypeError:
                    self.selection_model.clearSelection()
                    return
        else:
            if index.column() in {1, 2}:
                speaker_id = self.diarization_model.suggested_indices[index.row()]
                if isinstance(speaker_id, list):
                    speaker_id = speaker_id[
                        self.diarization_model.selected_speaker_indices.get(index.row(), 0)
                    ]
            else:
                speaker_id = self.diarization_model.speaker_indices[index.row()]
            with self.diarization_model.corpus_model.corpus.session() as session:
                c = session.query(Corpus).first()
                try:
                    utterance_id, file_id, begin, end = (
                        session.query(
                            Utterance.id,
                            Utterance.file_id,
                            Utterance.begin,
                            Utterance.end,
                        )
                        .join(Utterance.speaker)
                        .filter(Utterance.speaker_id == speaker_id)
                        .order_by(
                            c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column)
                        )
                        .first()
                    )
                except TypeError:
                    self.selection_model.clearSelection()
                    return
        self.selection_model.set_current_file(
            file_id,
            begin,
            end,
            utterance_id,
            speaker_id,
            force_update=True,
            single_utterance=False,
        )


class ThresholdWidget(QtWidgets.QLineEdit):
    def __init__(self, *args):
        super().__init__(*args)
        self.settings = AnchorSettings()
        self.minimum = None
        self.maximum = None

    def set_min_max(self, minimum, maximum):
        self.minimum = minimum
        self.maximum = maximum

    def validate(self, required=False):
        if self.text() == "":
            if required:
                return False
            return True
        try:
            v = float(self.text())
            if self.minimum is not None and v <= self.minimum:
                return False
            if self.maximum is not None and v >= self.maximum:
                return False
        except ValueError:
            self.setProperty("error", True)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

            return False
        return True

    def value(self):
        if self.text() and self.validate():
            return float(self.text())
        return None

    def setValue(self, val):
        self.setText(f"{val:.4f}")


class AlignmentAnalysisTable(AnchorTableView):
    def __init__(self, *args):
        super().__init__(*args)
        self.alignment_analysis_model: typing.Optional[AlignmentAnalysisModel] = None
        self.selection_model: typing.Optional[FileSelectionModel] = None
        self.clicked.connect(self.search_utterance)

    def set_models(self, model: AlignmentAnalysisModel, selection_model: FileSelectionModel):
        self.alignment_analysis_model = model
        self.selection_model = selection_model
        self.setModel(model)
        self.refresh_settings()

    def search_utterance(self, index: QtCore.QModelIndex):
        if not index.isValid():
            return
        row = index.row()
        utterance_id = self.alignment_analysis_model.utterance_ids[row]
        if utterance_id is None:
            return
        with self.alignment_analysis_model.corpus_model.corpus.session() as session:
            try:
                file_id, begin, end, speaker_id = (
                    session.query(
                        Utterance.file_id, Utterance.begin, Utterance.end, Utterance.speaker_id
                    )
                    .filter(Utterance.id == utterance_id)
                    .first()
                )
            except TypeError:
                self.selection_model.clearSelection()
                return
        word_index = self.alignment_analysis_model.createIndex(row, 5)
        word = self.alignment_analysis_model.data(word_index)
        self.selection_model.set_search_term(word)
        self.selection_model.set_current_file(
            file_id,
            begin,
            end,
            utterance_id,
            speaker_id,
            force_update=True,
            single_utterance=False,
        )


class AlignmentAnalysisWidget(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = AnchorSettings()
        form_layout = QtWidgets.QFormLayout()
        form_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        self.greater_than_edit = ThresholdWidget(self)
        self.greater_than_edit.returnPressed.connect(self.search)
        self.less_than_edit = ThresholdWidget(self)
        self.less_than_edit.returnPressed.connect(self.search)
        self.word_check = QtWidgets.QCheckBox()
        self.search_box = SearchBox(self)
        self.word_check.toggled.connect(self.switch_word_phone_mode)
        form_layout.addRow(QtWidgets.QLabel("Search based on words"), self.word_check)
        self.search_box_label = QtWidgets.QLabel("Search")
        form_layout.addRow(self.search_box_label, self.search_box)
        self.search_box.searchActivated.connect(self.search)
        self.phone_dropdown = QtWidgets.QComboBox()
        self.measure_dropdown = QtWidgets.QComboBox()
        for m in ["Duration", "Log-likelihood"]:
            self.measure_dropdown.addItem(m)
        self.phone_dropdown_label = QtWidgets.QLabel("Phone")
        form_layout.addRow(self.phone_dropdown_label, self.phone_dropdown)
        form_layout.addRow(QtWidgets.QLabel("Measure"), self.measure_dropdown)
        form_layout.addRow(QtWidgets.QLabel("Less than"), self.less_than_edit)
        form_layout.addRow(QtWidgets.QLabel("Greater than"), self.greater_than_edit)
        self.exclude_manual_check = QtWidgets.QCheckBox()
        self.relative_duration_check = QtWidgets.QCheckBox()
        form_layout.addRow(
            QtWidgets.QLabel("Exclude manually aligned utterances"), self.exclude_manual_check
        )
        form_layout.addRow(QtWidgets.QLabel("Relative duration"), self.relative_duration_check)

        self.clear_action = QtGui.QAction("Reset")
        self.search_action = QtGui.QAction("Search")
        self.search_action.triggered.connect(self.search)
        self.clear_action.triggered.connect(self.clear_fields)
        self.toolbar = QtWidgets.QToolBar()
        self.toolbar.addAction(self.search_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.clear_action)
        self.speaker_dropdown = CompleterLineEdit(self)
        self.speaker_dropdown.line_edit.setPlaceholderText("Filter by speaker")
        self.speaker_dropdown.line_edit.returnPressed.connect(self.search)

        form_layout.addRow("Speaker", self.speaker_dropdown)
        form_widget.setLayout(form_layout)
        layout.addWidget(form_widget)
        layout.addWidget(self.toolbar)
        self.table = AlignmentAnalysisTable(self)
        layout.addWidget(self.table)
        self.alignment_analysis_model: Optional[AlignmentAnalysisModel] = None
        self.current_page = 0
        self.num_pages = 0
        self.pagination_toolbar = PaginationWidget()
        self.pagination_toolbar.pageRequested.connect(self.table.scrollToTop)
        layout.addWidget(self.pagination_toolbar)
        self.setLayout(layout)

    def switch_word_phone_mode(self, word_mode):
        if word_mode:
            self.phone_dropdown_label.setVisible(False)
            self.phone_dropdown.setVisible(False)
        else:
            self.phone_dropdown_label.setVisible(True)
            self.phone_dropdown.setVisible(True)

    def set_models(self, model: AlignmentAnalysisModel, selection_model: FileSelectionModel):
        self.alignment_analysis_model = model
        self.alignment_analysis_model.corpus_model.corpusLoaded.connect(self.refresh)
        self.table.set_models(model, selection_model)
        self.alignment_analysis_model.resultCountChanged.connect(
            self.pagination_toolbar.update_result_count
        )
        self.pagination_toolbar.offsetRequested.connect(self.alignment_analysis_model.set_offset)
        self.pagination_toolbar.set_limit(self.alignment_analysis_model.limit)
        self.alignment_analysis_model.corpus_model.speakersRefreshed.connect(
            self.speaker_dropdown.update_completions
        )

    def refresh(self):
        if self.alignment_analysis_model.corpus_model.corpus is not None:
            validate_enabled = self.alignment_analysis_model.corpus_model.has_alignments
            self.phone_dropdown.clear()
            self.phone_dropdown.addItem("")
            for p in self.alignment_analysis_model.corpus_model.phones.keys():
                self.phone_dropdown.addItem(p)
        else:
            validate_enabled = False
        self.search_action.setEnabled(validate_enabled)
        self.clear_action.setEnabled(validate_enabled)
        self.exclude_manual_check.setEnabled(validate_enabled)
        self.phone_dropdown.setEnabled(validate_enabled)
        self.measure_dropdown.setEnabled(validate_enabled)
        self.less_than_edit.setEnabled(validate_enabled)
        self.greater_than_edit.setEnabled(validate_enabled)
        self.speaker_dropdown.setEnabled(validate_enabled)

    def search(self):
        self.table.selectionModel().clearSelection()
        self.alignment_analysis_model.set_speaker_filter(self.speaker_dropdown.current_text())
        self.alignment_analysis_model.set_word_mode(self.word_check.isChecked())
        self.alignment_analysis_model.set_relative_duration(
            self.relative_duration_check.isChecked()
        )
        if self.word_check.isChecked():
            self.alignment_analysis_model.set_phone_filter(None)
        else:
            self.alignment_analysis_model.set_phone_filter(self.phone_dropdown.currentText())
        self.alignment_analysis_model.set_word_filter(self.search_box.query())
        self.alignment_analysis_model.set_less_than(self.less_than_edit.value())
        self.alignment_analysis_model.set_greater_than(self.greater_than_edit.value())
        self.alignment_analysis_model.set_measure(self.measure_dropdown.currentText())
        self.alignment_analysis_model.set_exclude_manual(self.exclude_manual_check.isChecked())
        self.pagination_toolbar.first_page()

    def clear_fields(self):
        self.speaker_dropdown.line_edit.clear()
        self.phone_dropdown.setCurrentIndex(0)
        self.measure_dropdown.setCurrentIndex(0)
        self.less_than_edit.clear()
        self.greater_than_edit.clear()
        self.exclude_manual_check.setChecked(False)


class DiarizationWidget(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = AnchorSettings()
        form_layout = QtWidgets.QFormLayout()
        form_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        self.ivector_extractor_label = QtWidgets.QLabel("Not loaded")
        self.threshold_edit = ThresholdWidget(self)
        self.threshold_edit.returnPressed.connect(self.search)
        self.inverted_check = QtWidgets.QCheckBox()
        self.speaker_check = QtWidgets.QCheckBox()
        form_layout.addRow(QtWidgets.QLabel("Search based on speakers"), self.speaker_check)
        self.metric_dropdown = QtWidgets.QComboBox()
        for m in DistanceMetric:
            if m is DistanceMetric.euclidean:
                continue
            self.metric_dropdown.addItem(m.value)
        self.metric_dropdown.currentIndexChanged.connect(self.update_metric_language)
        self.threshold_label = QtWidgets.QLabel("Distance threshold")
        form_layout.addRow(QtWidgets.QLabel("Ivector extractor"), self.ivector_extractor_label)
        form_layout.addRow(self.threshold_label, self.threshold_edit)
        form_layout.addRow(QtWidgets.QLabel("Distance metric"), self.metric_dropdown)
        form_layout.addRow(QtWidgets.QLabel("Search in speaker"), self.inverted_check)
        self.reference_utterance_label = QtWidgets.QLabel("No reference utterance")
        self.clear_reference_utterance_button = QtWidgets.QPushButton("Clear reference utterance")
        self.clear_reference_utterance_button.clicked.connect(self.clear_reference_utterance)
        form_layout.addRow(self.reference_utterance_label, self.clear_reference_utterance_button)

        self.refresh_ivectors_action = QtGui.QAction("Refresh ivectors")
        self.reassign_all_action = QtGui.QAction("Reassign all with threshold")
        self.calculate_plda_action = QtGui.QAction("Calculate PLDA")
        self.reset_ivectors_action = QtGui.QAction("Reset ivectors")
        self.search_action = QtGui.QAction("Search")
        self.search_action.triggered.connect(self.search)
        self.reassign_all_action.triggered.connect(self.reassign_all)
        self.toolbar = QtWidgets.QToolBar()
        self.toolbar.addAction(self.search_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.reassign_all_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.refresh_ivectors_action)
        self.toolbar.addAction(self.calculate_plda_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.reset_ivectors_action)
        self.speaker_dropdown = CompleterLineEdit(self)
        self.speaker_dropdown.line_edit.setPlaceholderText("Filter by speaker")
        self.speaker_dropdown.line_edit.returnPressed.connect(self.search)
        self.alternate_speaker_dropdown = CompleterLineEdit(self)
        self.alternate_speaker_dropdown.line_edit.setPlaceholderText("Filter by speaker")
        self.alternate_speaker_dropdown.line_edit.returnPressed.connect(self.search)

        form_layout.addRow("Target speaker", self.speaker_dropdown)
        form_layout.addRow("Alternate speaker", self.alternate_speaker_dropdown)
        self.search_box = SearchBox(self)
        self.search_box.searchActivated.connect(self.search)
        form_layout.addRow("Text", self.search_box)
        form_widget.setLayout(form_layout)
        layout.addWidget(form_widget)
        layout.addWidget(self.toolbar)
        self.table = DiarizationTable(self)
        layout.addWidget(self.table)
        self.diarization_model: Optional[DiarizationModel] = None
        self.current_page = 0
        self.num_pages = 0
        self.pagination_toolbar = PaginationWidget()
        self.pagination_toolbar.pageRequested.connect(self.table.scrollToTop)
        layout.addWidget(self.pagination_toolbar)
        self.setLayout(layout)
        self.table.referenceUtteranceSelected.connect(self.update_reference_utterance)

    def update_reference_utterance(self, utterance_name):
        self.reference_utterance_label.setText(utterance_name)
        self.search_action.trigger()

    def clear_reference_utterance(self):
        self.reference_utterance_label.setText("No reference utterance")
        self.diarization_model.set_utterance_filter(None)

    def update_metric_language(self):
        current_metric = self.metric_dropdown.currentText()
        if current_metric == "plda":
            self.threshold_label.setText("Log-likelihood threshold")
            self.threshold_edit.set_min_max(None, None)
        else:
            self.threshold_label.setText("Distance threshold")
            self.threshold_edit.set_min_max(0, 1)

    def search(self):
        self.table.selectionModel().clearSelection()
        try:
            self.diarization_model.set_speaker_filter(self.speaker_dropdown.current_text())
        except Exception:
            return
        try:
            self.diarization_model.set_alternate_speaker_filter(
                self.alternate_speaker_dropdown.current_text()
            )
        except Exception:
            return
        self.diarization_model.set_threshold(self.threshold_edit.value())
        self.diarization_model.set_metric(self.metric_dropdown.currentText())
        self.diarization_model.set_inverted(self.inverted_check.isChecked())
        self.diarization_model.set_speaker_lookup(self.speaker_check.isChecked())
        self.diarization_model.set_text_filter(self.search_box.query())
        self.diarization_model.update_data()
        self.diarization_model.update_result_count()

    def reassign_all(self):
        if not self.threshold_edit.validate(required=True) or not self.speaker_dropdown.validate():
            return
        self.diarization_model.set_speaker_filter(self.speaker_dropdown.current_text())
        self.diarization_model.set_threshold(self.threshold_edit.value())
        self.diarization_model.set_metric(self.metric_dropdown.currentText())
        self.diarization_model.reassign_utterances()

    def refresh(self):
        validate_enabled = True
        if (
            self.diarization_model.corpus_model.ivector_extractor is not None
            and self.diarization_model.corpus_model.corpus is not None
        ):
            if isinstance(self.diarization_model.corpus_model.ivector_extractor, str):
                name = self.diarization_model.corpus_model.ivector_extractor
            else:
                name = self.diarization_model.corpus_model.ivector_extractor.name
            self.ivector_extractor_label.setText(name)
            self.search_action.setEnabled(
                self.diarization_model.corpus_model.corpus.has_any_ivectors()
            )
            self.threshold_edit.setEnabled(
                self.diarization_model.corpus_model.corpus.has_any_ivectors()
            )
        else:
            validate_enabled = False
            self.ivector_extractor_label.setText("Not loaded")
            self.search_action.setEnabled(False)
            self.threshold_edit.setEnabled(False)
        self.refresh_ivectors_action.setEnabled(validate_enabled)

    def set_models(self, model: DiarizationModel, selection_model: FileSelectionModel):
        self.diarization_model = model
        self.diarization_model.corpus_model.corpusLoaded.connect(self.refresh)
        self.table.set_models(model, selection_model)
        self.diarization_model.corpus_model.ivectorExtractorChanged.connect(self.refresh)
        self.diarization_model.resultCountChanged.connect(
            self.pagination_toolbar.update_result_count
        )
        self.pagination_toolbar.offsetRequested.connect(self.diarization_model.set_offset)
        self.pagination_toolbar.set_limit(self.diarization_model.limit)
        self.diarization_model.corpus_model.speakersRefreshed.connect(
            self.speaker_dropdown.update_completions
        )


class AlignmentWidget(QtWidgets.QWidget):
    def __init__(self, *args):
        super().__init__(*args)
        self.button = QtWidgets.QToolButton()
        self.verify_button = QtWidgets.QToolButton()
        form_layout = QtWidgets.QFormLayout()
        button_layout = QtWidgets.QHBoxLayout()
        layout = QtWidgets.QVBoxLayout()
        self.acoustic_model_label = QtWidgets.QLabel("Not loaded")
        self.dictionary_label = QtWidgets.QLabel("Not loaded")
        self.interjection_word_label = QtWidgets.QLabel("Not loaded")
        self.fine_tune_check = QtWidgets.QCheckBox()
        self.beam = QtWidgets.QSpinBox()
        self.beam.setMinimum(6)
        self.beam.setValue(10)
        self.beam.setMaximum(1000)
        self.retry_beam = QtWidgets.QSpinBox()
        self.retry_beam.setMinimum(24)
        self.retry_beam.setMaximum(4000)
        self.retry_beam.setValue(40)
        self.silence_boost = ThresholdWidget()
        self.silence_boost.setText("1.0")
        self.cutoff_check = QtWidgets.QCheckBox()
        form_layout.addRow(QtWidgets.QLabel("Acoustic model"), self.acoustic_model_label)
        form_layout.addRow(QtWidgets.QLabel("Dictionary"), self.dictionary_label)
        form_layout.addRow(QtWidgets.QLabel("Beam"), self.beam)
        form_layout.addRow(QtWidgets.QLabel("Retry beam"), self.retry_beam)
        form_layout.addRow(QtWidgets.QLabel("Silence boost factor"), self.silence_boost)
        form_layout.addRow(QtWidgets.QLabel("Fine tune"), self.fine_tune_check)
        form_layout.addRow(QtWidgets.QLabel("Cutoff modeling"), self.cutoff_check)
        form_layout.addRow(QtWidgets.QLabel("Interjection words"), self.interjection_word_label)
        layout.addLayout(form_layout)
        button_layout.addWidget(self.button)
        button_layout.addWidget(self.verify_button)
        layout.addLayout(button_layout)
        self.text = QtWidgets.QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        self.setLayout(layout)
        self.corpus_model: Optional[CorpusModel] = None

    def refresh(self):
        validate_enabled = True
        num_interjection_words = self.corpus_model.get_interjection_count()
        self.interjection_word_label.setText(str(num_interjection_words))
        if self.verify_button.defaultAction() is not None:
            self.verify_button.defaultAction().setEnabled(num_interjection_words > 0)
        if self.corpus_model.has_dictionary:
            self.dictionary_label.setText(self.corpus_model.corpus.dictionary_model.name)
        else:
            validate_enabled = False
            self.dictionary_label.setText("Not loaded")
        if isinstance(self.corpus_model.acoustic_model, AcousticModel):
            self.acoustic_model_label.setText(self.corpus_model.acoustic_model.name)
        else:
            validate_enabled = False
            self.acoustic_model_label.setText("Not loaded")
        if self.button.defaultAction() is not None:
            self.button.defaultAction().setEnabled(validate_enabled)

    def set_models(self, corpus_model: CorpusModel):
        self.corpus_model = corpus_model
        self.refresh()
        self.corpus_model.dictionaryChanged.connect(self.refresh)
        self.corpus_model.acousticModelChanged.connect(self.refresh)
        self.corpus_model.corpusLoaded.connect(self.refresh)

    def parameters(self):
        return {
            "beam": int(self.beam.text()),
            "retry_beam": int(self.retry_beam.text()),
            "boost_silence": self.silence_boost.value(),
            "fine_tune": self.fine_tune_check.isChecked(),
            "use_cutoff_model": self.cutoff_check.isChecked(),
        }


class WordDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, *args):
        super(WordDelegate, self).__init__(*args)


class OovWidget(QtWidgets.QWidget):
    dictionaryError = QtCore.Signal(object)

    def __init__(self, *args):
        super().__init__(*args)
        self.settings = AnchorSettings()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.oov_model: Optional[OovModel] = None
        dict_layout = QtWidgets.QVBoxLayout()
        self.table = OovTableView(self)
        # self.table.cellChanged.connect(self.dictionary_edited)
        self.toolbar = QtWidgets.QToolBar()
        self.search_box = SearchBox(self)
        self.toolbar.addWidget(self.search_box)
        self.search_box.searchActivated.connect(self.search)
        self.current_search_query = None
        self.current_search_text = ""
        dict_layout.addWidget(self.toolbar)
        dict_layout.addWidget(self.table)
        self.pagination_toolbar = PaginationWidget()
        self.pagination_toolbar.pageRequested.connect(self.table.scrollToTop)
        dict_layout.addWidget(self.pagination_toolbar)

        self.setLayout(dict_layout)
        self.refresh_settings()

    def refresh_settings(self):
        self.settings.sync()
        self.table.refresh_settings()
        self.pagination_toolbar.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))
        # self.search_box.setFont(font)
        # self.search_box.setStyleSheet(self.settings.search_box_style_sheet)

    def search(self):
        if self.oov_model.text_filter != self.search_box.query():
            self.pagination_toolbar.current_page = 0
            self.oov_model.current_offset = 0
        self.oov_model.set_text_filter(self.search_box.query())

    def set_models(self, oov_model: OovModel):
        self.oov_model = oov_model
        self.table.set_models(oov_model)
        self.oov_model.resultCountChanged.connect(self.pagination_toolbar.update_result_count)
        self.pagination_toolbar.offsetRequested.connect(self.oov_model.set_offset)
        self.oov_model.refresh()


class DictionaryWidget(QtWidgets.QWidget):
    dictionaryError = QtCore.Signal(object)

    def __init__(self, *args):
        super().__init__(*args)
        self.settings = AnchorSettings()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.dictionary_model: Optional[DictionaryTableModel] = None
        dict_layout = QtWidgets.QVBoxLayout()
        self.table = DictionaryTableView(self)
        self.ignore_errors = False
        self.toolbar = QtWidgets.QToolBar()
        self.search_box = SearchBox(self)
        self.status_indicator = LoadingScreen(self, logo=False)
        self.status_indicator.setVisible(False)
        dict_layout.addWidget(self.status_indicator)
        self.dictionary_dropdown = QtWidgets.QComboBox()
        self.toolbar.addWidget(self.dictionary_dropdown)
        self.toolbar.addWidget(self.search_box)
        self.search_box.searchActivated.connect(self.search)
        self.current_search_query = None
        self.current_search_text = ""
        self.refresh_word_counts_action = QtGui.QAction(self)
        self.refresh_word_counts_action.setIcon(QtGui.QIcon.fromTheme("tools-check-spelling"))
        self.refresh_word_counts_action.setEnabled(True)
        self.toolbar.addAction(self.refresh_word_counts_action)
        self.rebuild_lexicon_action = QtGui.QAction(self)
        self.rebuild_lexicon_action.setIcon(QtGui.QIcon.fromTheme("sync-synchronizing"))
        self.rebuild_lexicon_action.setEnabled(True)
        self.toolbar.addAction(self.rebuild_lexicon_action)
        dict_layout.addWidget(self.toolbar)
        dict_layout.addWidget(self.table)
        self.pagination_toolbar = PaginationWidget()
        self.pagination_toolbar.pageRequested.connect(self.table.scrollToTop)
        dict_layout.addWidget(self.pagination_toolbar)

        self.setLayout(dict_layout)
        self.refresh_settings()

    def dictionaries_refreshed(self, dictionaries):
        self.dictionary_dropdown.clear()
        if not dictionaries:
            return
        for d_id, d_name in dictionaries:
            self.dictionary_dropdown.addItem(d_name, userData=d_id)
        self.dictionary_dropdown.setCurrentIndex(0)

    def refresh_settings(self):
        self.settings.sync()
        self.table.refresh_settings()
        self.pagination_toolbar.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))
        # self.search_box.setFont(font)
        # self.search_box.setStyleSheet(self.settings.search_box_style_sheet)

    def search(self):
        if self.dictionary_model.text_filter != self.search_box.query():
            self.pagination_toolbar.current_page = 0
            self.dictionary_model.current_offset = 0
        self.dictionary_model.set_text_filter(self.search_box.query())

    def update_g2p(self, g2p_model):
        self.g2p_model = g2p_model

    def corpus_data_changed(self):
        self.refresh_word_counts_action.setEnabled(True)

    def updating_counts(self):
        self.table.setVisible(False)
        self.pagination_toolbar.setVisible(False)
        self.toolbar.setVisible(False)
        self.status_indicator.setVisible(True)
        self.refresh_word_counts_action.setEnabled(False)

    def counts_updated(self):
        self.table.setVisible(True)
        self.pagination_toolbar.setVisible(True)
        self.toolbar.setVisible(True)
        self.status_indicator.setVisible(False)
        self.refresh_word_counts_action.setEnabled(True)

    def set_models(self, dictionary_model: DictionaryTableModel):
        self.dictionary_model = dictionary_model
        self.dictionary_model.requestLookup.connect(self.look_up_word)
        self.dictionary_model.dictionariesRefreshed.connect(self.dictionaries_refreshed)
        self.dictionary_dropdown.currentIndexChanged.connect(self.update_current_dictionary)
        self.refresh_word_counts_action.triggered.connect(self.dictionary_model.update_word_counts)
        self.rebuild_lexicon_action.triggered.connect(self.dictionary_model.rebuild_lexicons)
        self.dictionary_model.wordCountsRefreshed.connect(self.counts_updated)
        self.refresh_word_counts_action.triggered.connect(self.updating_counts)
        self.dictionary_model.corpus_model.databaseSynced.connect(self.corpus_data_changed)
        self.table.set_models(dictionary_model)
        self.dictionary_model.resultCountChanged.connect(
            self.pagination_toolbar.update_result_count
        )
        self.pagination_toolbar.offsetRequested.connect(self.dictionary_model.set_offset)

    def update_current_dictionary(self):
        d_id = self.dictionary_dropdown.currentData()
        self.dictionary_model.update_current_index(d_id)

    def look_up_word(self, word):
        self.search_box.setQuery(TextFilterQuery(word, False, True, False))


class SpeakerQueryDialog(QtWidgets.QDialog):
    def __init__(self, corpus_model: CorpusModel, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = AnchorSettings()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QtWidgets.QVBoxLayout()
        self.setWindowTitle("Find speaker")
        self.setWindowIcon(QtGui.QIcon(":anchor-yellow.svg"))
        self.speaker_dropdown = CompleterLineEdit(self, corpus_model=corpus_model)
        self.speaker_dropdown.line_edit.setPlaceholderText("Filter by speaker")
        self.speaker_dropdown.line_edit.returnPressed.connect(self.accept)
        self.speaker_dropdown.update_completions(corpus_model.speakers)
        layout.addWidget(self.speaker_dropdown)
        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.setLayout(layout)
        # self.speaker_dropdown.setFont(font)
        # self.button_box.setFont(font)
        # self.setStyleSheet(self.settings.style_sheet)
        # self.speaker_dropdown.setStyleSheet(self.settings.combo_box_style_sheet)


class WordQueryDialog(QtWidgets.QDialog):
    def __init__(self, corpus_model: CorpusModel, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = AnchorSettings()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QtWidgets.QVBoxLayout()
        self.setWindowTitle("Change word")
        self.setWindowIcon(QtGui.QIcon(":anchor-yellow.svg"))
        self.word_dropdown = WordCompleterLineEdit(self, corpus_model=corpus_model)
        self.word_dropdown.line_edit.setPlaceholderText("")
        self.word_dropdown.line_edit.returnPressed.connect(self.accept)
        self.word_dropdown.update_completions(corpus_model.words)
        layout.addWidget(self.word_dropdown)
        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.setLayout(layout)
        # self.speaker_dropdown.setFont(font)
        # self.button_box.setFont(font)
        # self.setStyleSheet(self.settings.style_sheet)
        # self.speaker_dropdown.setStyleSheet(self.settings.combo_box_style_sheet)


class ConfirmationDialog(QtWidgets.QDialog):
    def __init__(self, title: str, description: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = AnchorSettings()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QtWidgets.QVBoxLayout()
        self.setWindowTitle(title)
        self.label = QtWidgets.QLabel(description)
        self.setWindowIcon(QtGui.QIcon(":anchor-yellow.svg"))
        layout.addWidget(self.label)
        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Yes
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.setLayout(layout)
        # font = self.settings.font
        # self.setFont(font)
        # self.label.setFont(font)
        # self.button_box.setFont(font)
        # self.setStyleSheet(self.settings.style_sheet)


class SpeakerWidget(QtWidgets.QWidget):
    def __init__(self, *args):
        super(SpeakerWidget, self).__init__(*args)
        self.settings = AnchorSettings()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        speaker_layout = QtWidgets.QVBoxLayout()
        self.corpus_model: Optional[CorpusModel] = None
        top_toolbar = QtWidgets.QToolBar()

        self.speaker_dropdown = CompleterLineEdit(self)
        self.speaker_dropdown.line_edit.setPlaceholderText("Filter by speaker")
        self.speaker_dropdown.line_edit.returnPressed.connect(self.search)
        top_toolbar.addWidget(self.speaker_dropdown)
        self.current_search_query = None
        self.current_search_text = ""
        speaker_layout.addWidget(top_toolbar)
        self.table = SpeakerTableView()
        self.table.horizontalHeader().setSortIndicator(1, QtCore.Qt.SortOrder.DescendingOrder)
        speaker_layout.addWidget(self.table)
        self.current_page = 0
        self.num_pages = 0
        self.pagination_toolbar = PaginationWidget()
        self.pagination_toolbar.pageRequested.connect(self.table.scrollToTop)
        speaker_layout.addWidget(self.pagination_toolbar)
        self.tool_bar_wrapper = QtWidgets.QVBoxLayout()
        self.tool_bar = QtWidgets.QToolBar()
        self.tool_bar.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred
        )
        self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.tool_bar_wrapper.addWidget(self.tool_bar)
        self.cluster_widget = SpeakerClustersWidget(self)
        self.cluster_widget.search_requested.connect(self.search)
        speaker_layout.addWidget(self.cluster_widget)
        self.speakers = None
        self.speaker_model: SpeakerModel = None
        self.speaker_edit = NewSpeakerField()
        self.result_count = 0
        self.tool_bar.addWidget(self.speaker_edit)

        toolbar_wrapper_widget = QtWidgets.QWidget()
        toolbar_wrapper_widget.setLayout(self.tool_bar_wrapper)
        speaker_layout.addWidget(toolbar_wrapper_widget)

        self.setLayout(speaker_layout)
        self.refresh_settings()

    def refresh_cluster(self):
        self.table.cluster_utterances(self.table.selectionModel().currentIndex())

    def search(self, speaker_filter=None):
        # self.speaker_model.set_text_filter(self.search_box.query())
        self.cluster_widget.plot_widget.clear_plot()
        if speaker_filter is None:
            speaker_id = self.speaker_dropdown.current_text()
            if isinstance(speaker_id, str):
                with self.speaker_model.corpus_model.corpus.session() as session:
                    actual_speaker_id = (
                        session.query(Speaker.id).filter(Speaker.name == speaker_id).first()
                    )
                    if actual_speaker_id is None:
                        self.speaker_model.set_speaker_filter(speaker_id)
                        return
                    self.speaker_dropdown.completions[speaker_id] = actual_speaker_id[0]
                    speaker_id = actual_speaker_id[0]
            if speaker_id is None:
                return
            self.speaker_model.set_speaker_filter(speaker_id)
        else:
            self.speaker_model.set_speaker_filter(speaker_filter)
        if self.speaker_model.sort_index != 3:
            self.table.horizontalHeader().setSortIndicator(3, QtCore.Qt.SortOrder.AscendingOrder)
        else:
            self.speaker_model.update_data()
            self.speaker_model.update_result_count()

    def set_models(
        self,
        corpus_model: CorpusModel,
        selection_model: FileSelectionModel,
        speaker_model: SpeakerModel,
    ):
        self.speaker_model = speaker_model
        self.cluster_widget.set_models(corpus_model, selection_model, speaker_model)
        self.speaker_model.corpus_model.corpusLoaded.connect(self.update_speaker_count)
        self.table.set_models(self.speaker_model)
        self.speaker_model.resultCountChanged.connect(self.pagination_toolbar.update_result_count)
        self.pagination_toolbar.offsetRequested.connect(self.speaker_model.set_offset)
        self.pagination_toolbar.set_limit(self.speaker_model.limit)
        self.speaker_model.corpus_model.speakersRefreshed.connect(
            self.speaker_dropdown.update_completions
        )

    def update_speaker_count(self):
        self.pagination_toolbar.update_result_count(
            self.speaker_model.corpus_model.corpus.num_speakers
        )

    def refresh_settings(self):
        self.settings.sync()
        # font = self.settings.font
        # self.speaker_edit.setFont(font)
        # self.speaker_dropdown.setFont(font)
        # self.speaker_dropdown.setStyleSheet(self.settings.combo_box_style_sheet)
        self.table.refresh_settings()
        self.pagination_toolbar.set_limit(
            self.table.settings.value(self.table.settings.RESULTS_PER_PAGE)
        )


class ColorEdit(QtWidgets.QPushButton):  # pragma: no cover
    colorChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super(ColorEdit, self).__init__(parent=parent)
        self.setText("")
        self.clicked.connect(self.open_dialog)
        self.color = None

    def set_color(self, color: typing.Union[str, QtGui.QColor]):
        if isinstance(color, str):
            color = QtGui.QColor(color)
        self.color = color
        self.update_icon()

    def update_icon(self):
        pixmap = QtGui.QPixmap(100, 100)
        pixmap.fill(self.color)
        icon = QtGui.QIcon(pixmap)
        icon.addPixmap(pixmap, QtGui.QIcon.Mode.Disabled)
        self.setIcon(icon)

    def open_dialog(self):
        color = QtWidgets.QColorDialog.getColor()
        if color.isValid() and self.color != color.name():
            self.color = color.name()
            self.update_icon()
            self.colorChanged.emit()


class FontDialog(QtWidgets.QFontDialog):
    def __init__(self, *args):
        super(FontDialog, self).__init__(*args)


class FontEdit(QtWidgets.QPushButton):  # pragma: no cover
    def __init__(self, parent=None):
        super(FontEdit, self).__init__(parent=parent)
        self.font = None
        self.clicked.connect(self.open_dialog)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

    def set_font(self, font: QtGui.QFont):
        self.font = font
        self.update_icon()

    def update_icon(self):
        self.setFont(self.font)
        self.setText(self.font.key().split(",", maxsplit=1)[0])

    def open_dialog(self):
        ok, font = FontDialog.getFont(self.font, self)
        if ok:
            self.font = font
            self.update_icon()


class MfaModelListWidget(QtWidgets.QWidget):
    modelDetailsRequested = QtCore.Signal(object)
    downloadRequested = QtCore.Signal(object)
    model_type = "MFA model"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QtWidgets.QVBoxLayout()

        self.table_widget = BaseTableView()
        self.table_widget.setSortingEnabled(False)
        self.icon_delegate = ModelIconDelegate(self.table_widget)
        self.table_widget.setItemDelegateForColumn(0, self.icon_delegate)

        layout.addWidget(self.table_widget)
        button_layout = QtWidgets.QHBoxLayout()
        self.delete_button = QtWidgets.QPushButton(f"Delete {self.model_type.lower()}")
        self.download_button = QtWidgets.QPushButton(f"Download {self.model_type.lower()}")
        self.delete_button.clicked.connect(self.delete_model)
        self.download_button.clicked.connect(self.download_model)
        button_layout.addWidget(self.delete_button)
        button_layout.addWidget(self.download_button)
        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.model = None

    def delete_model(self):
        row = self.table_widget.selectionModel().currentIndex().row()
        self.model.remove_model(row)

    def download_model(self):
        row = self.table_widget.selectionModel().currentIndex().row()
        self.model.download_model(row)

    def set_model(self, model: MfaModelTableModel):
        self.table_widget.setModel(model)
        self.model = model
        self.table_widget.resizeColumnsToContents()
        self.table_widget.selectionModel().selectionChanged.connect(self.update_select)

    def update_select(self):
        row = self.table_widget.selectionModel().selectedRows(0)
        if not row:
            return
        row = row[0].row()
        self.modelDetailsRequested.emit(row)


class AcousticModelListWidget(MfaModelListWidget):
    model_type = "Acoustic model"


class DictionaryModelListWidget(MfaModelListWidget):
    model_type = "Dictionary"


class G2PModelListWidget(MfaModelListWidget):
    model_type = "G2P model"


class LanguageModelListWidget(MfaModelListWidget):
    model_type = "Language model"


class IvectorExtractorListWidget(MfaModelListWidget):
    model_type = "Ivector extractor"


class CorpusListWidget(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QtWidgets.QVBoxLayout()

        self.table_widget = BaseTableView()
        self.table_widget.setSortingEnabled(False)
        self.icon_delegate = ModelIconDelegate(self.table_widget)
        self.table_widget.setItemDelegateForColumn(0, self.icon_delegate)

        layout.addWidget(self.table_widget)
        button_layout = QtWidgets.QHBoxLayout()
        self.reset_button = QtWidgets.QPushButton("Reset corpus")
        self.delete_button = QtWidgets.QPushButton("Remove corpus")
        self.delete_button.clicked.connect(self.delete_corpus)
        self.reset_button.clicked.connect(self.reset_corpus)
        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.delete_button)
        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.model: CorpusTableModel = None

    def set_model(self, model: CorpusTableModel):
        self.table_widget.setModel(model)
        self.model = model
        self.table_widget.resizeColumnsToContents()

    def delete_corpus(self):
        row = self.table_widget.selectionModel().currentIndex().row()
        self.model.remove_corpus(row)

    def reset_corpus(self):
        row = self.table_widget.selectionModel().currentIndex().row()
        self.model.reset_corpus(row)


class PathSelectWidget(QtWidgets.QWidget):
    def __init__(self, *args, caption="Select a directory", file_filter=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_directory_key = AnchorSettings.DEFAULT_DIRECTORY
        self.caption = caption
        self.file_filter = file_filter
        self.settings = AnchorSettings()
        layout = QtWidgets.QHBoxLayout()
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.textChanged.connect(self.check_existence)
        layout.addWidget(self.path_edit)
        self.select_button = QtWidgets.QPushButton("...")
        layout.addWidget(self.select_button)
        self.exists_label = QtWidgets.QLabel()
        layout.addWidget(self.exists_label)
        self.setLayout(layout)

        self.select_button.clicked.connect(self.select_path)
        self.exists_icon = QtGui.QIcon.fromTheme("emblem-default")
        self.not_exists_icon = QtGui.QIcon.fromTheme("emblem-important")

    def value(self):
        if not self.path_edit.text():
            return None
        if not os.path.exists(self.path_edit.text()):
            return None
        return self.path_edit.text()

    def select_path(self):
        if self.file_filter is not None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                parent=self,
                caption=self.caption,
                dir=self.settings.value(self.default_directory_key),
                filter=self.file_filter,
            )
        else:
            path = QtWidgets.QFileDialog.getExistingDirectory(
                parent=self,
                caption=self.caption,
                dir=self.settings.value(self.default_directory_key),
            )
        if not path:
            return
        self.set_path(path)

    def set_path(self, path):
        self.path_edit.setText(str(path))
        self.check_existence()

    def check_existence(self):
        if not self.path_edit.text():
            return
        if os.path.exists(self.path_edit.text()):
            self.exists_label.setPixmap(self.exists_icon.pixmap(QtCore.QSize(25, 25)))
        else:
            self.exists_label.setPixmap(self.not_exists_icon.pixmap(QtCore.QSize(25, 25)))


class CorpusSelectWidget(PathSelectWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, caption="Select a corpus directory", **kwargs)
        self.default_directory_key = AnchorSettings.DEFAULT_CORPUS_DIRECTORY


class ModelSelectWidget(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        self.default_directory_key = AnchorSettings.DEFAULT_DIRECTORY
        self.caption = "Select a model"
        self.model_type = None
        self.file_filter = "Model files (*.zip)"
        self.settings = AnchorSettings()
        layout = QtWidgets.QHBoxLayout()
        self.model_select = QtWidgets.QComboBox()
        layout.addWidget(self.model_select)
        self.select_button = QtWidgets.QPushButton("New model")
        layout.addWidget(self.select_button)
        self.exists_label = QtWidgets.QLabel()
        layout.addWidget(self.exists_label)
        self.setLayout(layout)
        self.model: MfaModelTableModel = None

        self.select_button.clicked.connect(self.select_path)

    def value(self):
        return self.model_select.currentData()

    def set_model(self, model: MfaModelTableModel):
        self.model = model
        self.model_select.clear()
        for m in model.models:
            if not m.available_locally:
                continue
            self.model_select.addItem(m.name, userData=m.id)
        self.model_select.setCurrentIndex(-1)
        self.model.layoutChanged.connect(self.refresh_combobox)

    def refresh_combobox(self):
        current_model = self.model_select.currentData()
        index = -1
        self.model_select.clear()
        for i, m in enumerate(self.model.models):
            if not m.available_locally or not os.path.exists(m.path):
                continue
            self.model_select.addItem(m.name, userData=m.id)
            if m.id == current_model:
                index = i
        self.model_select.setCurrentIndex(index)

    def select_path(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            parent=self,
            caption=self.caption,
            dir=self.settings.value(self.default_directory_key),
            filter=self.file_filter,
        )
        if not path:
            return
        self.settings.setValue(self.default_directory_key, os.path.dirname(path))
        self.model.add_model(path)


class DictionarySelectWidget(ModelSelectWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model_type = anchor.db.Dictionary
        self.default_directory_key = AnchorSettings.DEFAULT_DICTIONARY_DIRECTORY
        self.caption = "Select a dictionary"
        self.file_filter = "Dictionary files (*.dict *.txt *.yaml)"
        self.select_button.setText("New dictionary")


class AcousticModelSelectWidget(ModelSelectWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model_type = anchor.db.AcousticModel
        self.default_directory_key = AnchorSettings.DEFAULT_ACOUSTIC_DIRECTORY
        self.caption = "Select an acoustic model"


class G2PModelSelectWidget(ModelSelectWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model_type = anchor.db.G2PModel
        self.default_directory_key = AnchorSettings.DEFAULT_G2P_DIRECTORY
        self.caption = "Select a G2P model"


class LanguageModelSelectWidget(ModelSelectWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model_type = anchor.db.LanguageModel
        self.default_directory_key = AnchorSettings.DEFAULT_LM_DIRECTORY
        self.caption = "Select a language model"


class IvectorExtractorSelectWidget(ModelSelectWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model_type = anchor.db.IvectorExtractor
        self.default_directory_key = AnchorSettings.DEFAULT_IVECTOR_DIRECTORY
        self.caption = "Select an ivector extractor"


class CorpusDetailWidget(QtWidgets.QWidget):
    corpusLoadRequested = QtCore.Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form_layout = QtWidgets.QFormLayout()
        self.corpus_model = None
        self.dictionary_model = None
        self.acoustic_model_model = None
        self.g2p_model_model = None
        self.language_model_model = None
        self.ivector_extractor_model = None
        self.corpus_directory_widget = CorpusSelectWidget()
        self.dictionary_widget = DictionarySelectWidget()
        self.acoustic_model_widget = AcousticModelSelectWidget()
        self.g2p_model_widget = G2PModelSelectWidget()
        self.language_model_widget = LanguageModelSelectWidget()
        self.ivector_extractor_widget = IvectorExtractorSelectWidget()
        form_layout.addRow("Corpus directory", self.corpus_directory_widget)
        form_layout.addRow("Dictionary", self.dictionary_widget)
        form_layout.addRow("Acoustic model", self.acoustic_model_widget)
        form_layout.addRow("G2P model", self.g2p_model_widget)
        form_layout.addRow("Language model", self.language_model_widget)
        form_layout.addRow("Ivector extractor", self.ivector_extractor_widget)
        self.language_combobox = QtWidgets.QComboBox()
        for lang in Language:
            self.language_combobox.addItem(lang.value)
        form_layout.addRow("Language", self.language_combobox)
        self.config_path_widget = PathSelectWidget(
            caption="Select a configuration file", file_filter="Config files (*.yaml)"
        )
        form_layout.addRow("Config path", self.config_path_widget)

        self.language_combobox.setEnabled(False)
        self.config_path_widget.setEnabled(False)
        self.load_button = QtWidgets.QPushButton("Load corpus")
        self.load_button.clicked.connect(self.load_corpus)
        form_layout.addWidget(self.load_button)
        self.setLayout(form_layout)

    def set_models(
        self,
        corpus_model: CorpusTableModel,
        dictionary_model: DictionaryModelTableModel,
        acoustic_model_model: AcousticModelTableModel,
        g2p_model_model: G2PModelTableModel,
        language_model_model: LanguageModelTableModel,
        ivector_extractor_model: IvectorExtractorTableModel,
    ):
        self.corpus_model = corpus_model
        self.dictionary_model = dictionary_model
        self.acoustic_model_model = acoustic_model_model
        self.g2p_model_model = g2p_model_model
        self.language_model_model = language_model_model
        self.ivector_extractor_model = ivector_extractor_model
        self.dictionary_widget.set_model(self.dictionary_model)
        self.acoustic_model_widget.set_model(self.acoustic_model_model)
        self.g2p_model_widget.set_model(self.g2p_model_model)
        self.language_model_widget.set_model(self.language_model_model)
        self.ivector_extractor_widget.set_model(self.ivector_extractor_model)

    def load_corpus(self):
        corpus_directory = self.corpus_directory_widget.value()
        if not corpus_directory:
            return
        dictionary_id = self.dictionary_widget.value()
        acoustic_model_id = self.acoustic_model_widget.value()
        g2p_model_id = self.g2p_model_widget.value()
        language_model_id = self.language_model_widget.value()
        ivector_extractor_id = self.ivector_extractor_widget.value()
        self.corpus_model.add_corpus(
            corpus_directory,
            dictionary_id=dictionary_id,
            acoustic_model_id=acoustic_model_id,
            g2p_model_id=g2p_model_id,
            language_model_id=language_model_id,
            ivector_extractor_id=ivector_extractor_id,
        )
        self.corpusLoadRequested.emit()


class DictionaryModelDetailWidget(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form_layout = QtWidgets.QFormLayout()

        self.path_widget = PathSelectWidget(
            caption="Select a dictionary", file_filter="Dictionary files (*.dict *.txt *.yaml)"
        )
        self.version_edit = QtWidgets.QLineEdit()
        self.version_edit.setReadOnly(True)
        self.last_used_edit = QtWidgets.QLineEdit()
        self.last_used_edit.setReadOnly(True)
        self.local_checkbox = QtWidgets.QCheckBox()
        self.phones_text_edit = QtWidgets.QTextEdit()
        self.phones_text_edit.setReadOnly(True)
        self.preview_text_edit = QtWidgets.QTextEdit()
        self.preview_text_edit.setReadOnly(True)
        form_layout.addRow("Model path", self.path_widget)
        form_layout.addRow("Version", self.version_edit)
        form_layout.addRow("Available locally", self.local_checkbox)
        form_layout.addRow("Last used", self.last_used_edit)
        form_layout.addRow("Phones", self.phones_text_edit)
        form_layout.addRow("File preview", self.preview_text_edit)

        self.setLayout(form_layout)
        self.model = None

    def set_model(self, model):
        self.model = model

    def update_details(self, row):
        dictionary = self.model.models[row]
        self.path_widget.set_path(dictionary.path)
        self.last_used_edit.setText(str(dictionary.last_used))
        self.local_checkbox.setChecked(
            dictionary.available_locally and os.path.exists(dictionary.path)
        )
        if os.path.exists(dictionary.path):
            with mfa_open(dictionary.path) as f:
                lines = []
                for line in f:
                    lines.append(line)
                    if len(lines) >= 50:
                        break
            self.preview_text_edit.setText("".join(lines))


class AcousticModelDetailWidget(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form_layout = QtWidgets.QFormLayout()

        self.path_widget = PathSelectWidget(
            caption="Select an acoustic model", file_filter="Model files (*.zip)"
        )
        self.version_edit = QtWidgets.QLineEdit()
        self.version_edit.setReadOnly(True)
        self.local_checkbox = QtWidgets.QCheckBox()
        self.last_used_edit = QtWidgets.QLineEdit()
        self.last_used_edit.setReadOnly(True)
        self.phones_text_edit = QtWidgets.QTextEdit()
        self.phones_text_edit.setReadOnly(True)
        form_layout.addRow("Model path", self.path_widget)
        form_layout.addRow("Version", self.version_edit)
        form_layout.addRow("Available locally", self.local_checkbox)
        form_layout.addRow("Last used", self.last_used_edit)
        form_layout.addRow("Phones", self.phones_text_edit)

        self.setLayout(form_layout)
        self.model = None

    def set_model(self, model):
        self.model = model

    def update_details(self, row):
        model = self.model.models[row]
        self.path_widget.set_path(model.path)
        self.last_used_edit.setText(str(model.last_used))
        self.local_checkbox.setChecked(model.available_locally and os.path.exists(model.path))
        if os.path.exists(model.path):
            from montreal_forced_aligner.models import AcousticModel

            am = AcousticModel(model.path)
            phones = am.meta["phones"]
            self.version_edit.setText(am.meta["version"])
            self.phones_text_edit.setText("\n".join(sorted(phones)))


class G2PModelDetailWidget(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form_layout = QtWidgets.QFormLayout()

        self.path_widget = PathSelectWidget(
            caption="Select a G2P model", file_filter="Model files (*.zip)"
        )
        self.version_edit = QtWidgets.QLineEdit()
        self.version_edit.setReadOnly(True)
        self.local_checkbox = QtWidgets.QCheckBox()
        self.last_used_edit = QtWidgets.QLineEdit()
        self.last_used_edit.setReadOnly(True)
        self.phones_text_edit = QtWidgets.QTextEdit()
        self.phones_text_edit.setReadOnly(True)
        self.graphemes_text_edit = QtWidgets.QTextEdit()
        self.graphemes_text_edit.setReadOnly(True)
        form_layout.addRow("Model path", self.path_widget)
        form_layout.addRow("Version", self.version_edit)
        form_layout.addRow("Available locally", self.local_checkbox)
        form_layout.addRow("Last used", self.last_used_edit)
        form_layout.addRow("Phones", self.phones_text_edit)
        form_layout.addRow("Graphemes", self.graphemes_text_edit)

        self.setLayout(form_layout)
        self.model = None

    def set_model(self, model):
        self.model = model

    def update_details(self, row):
        model = self.model.models[row]
        self.path_widget.set_path(model.path)
        self.last_used_edit.setText(str(model.last_used))
        self.local_checkbox.setChecked(model.available_locally and os.path.exists(model.path))
        if os.path.exists(model.path):
            from montreal_forced_aligner.models import G2PModel

            m = G2PModel(model.path)
            self.version_edit.setText(m.meta["version"])
            phones = m.meta["phones"]
            self.phones_text_edit.setText("\n".join(sorted(phones)))
            graphemes = m.meta["graphemes"]
            self.graphemes_text_edit.setText("\n".join(sorted(graphemes)))


class LanguageModelDetailWidget(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form_layout = QtWidgets.QFormLayout()

        self.path_widget = PathSelectWidget(
            caption="Select a language model", file_filter="Model files (*.zip)"
        )
        self.version_edit = QtWidgets.QLineEdit()
        self.version_edit.setReadOnly(True)
        self.local_checkbox = QtWidgets.QCheckBox()
        self.last_used_edit = QtWidgets.QLineEdit()
        self.last_used_edit.setReadOnly(True)
        form_layout.addRow("Model path", self.path_widget)
        form_layout.addRow("Version", self.version_edit)
        form_layout.addRow("Available locally", self.local_checkbox)
        form_layout.addRow("Last used", self.last_used_edit)

        self.setLayout(form_layout)
        self.model = None

    def set_model(self, model):
        self.model = model

    def update_details(self, row):
        model = self.model.models[row]
        self.path_widget.set_path(model.path)
        self.last_used_edit.setText(str(model.last_used))
        self.local_checkbox.setChecked(model.available_locally and os.path.exists(model.path))
        if os.path.exists(model.path):
            from montreal_forced_aligner.models import LanguageModel

            m = LanguageModel(model.path)
            self.version_edit.setText(m.meta["version"])


class IvectorExtractorDetailWidget(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form_layout = QtWidgets.QFormLayout()

        self.path_widget = PathSelectWidget(
            caption="Select an ivector extractor", file_filter="Model files (*.zip)"
        )
        self.version_edit = QtWidgets.QLineEdit()
        self.version_edit.setReadOnly(True)
        self.last_used_edit = QtWidgets.QLineEdit()
        self.last_used_edit.setReadOnly(True)
        self.local_checkbox = QtWidgets.QCheckBox()
        form_layout.addRow("Model path", self.path_widget)
        form_layout.addRow("Version", self.version_edit)
        form_layout.addRow("Available locally", self.local_checkbox)
        form_layout.addRow("Last used", self.last_used_edit)

        self.download_button = QtWidgets.QPushButton("Download ivector extractor")
        form_layout.addWidget(self.download_button)
        self.setLayout(form_layout)
        self.model = None

    def set_model(self, model):
        self.model = model

    def update_details(self, row):
        model = self.model.models[row]
        self.path_widget.set_path(model.path)
        self.last_used_edit.setText(str(model.last_used))
        self.local_checkbox.setChecked(model.available_locally and os.path.exists(model.path))
        if os.path.exists(model.path):
            from montreal_forced_aligner.models import IvectorExtractorModel

            m = IvectorExtractorModel(model.path)
            self.version_edit.setText(m.meta["version"])
