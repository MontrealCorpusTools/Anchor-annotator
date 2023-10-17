from __future__ import annotations

import re
import typing
from typing import TYPE_CHECKING, Optional

import numpy as np
from montreal_forced_aligner.data import (  # noqa
    ClusterType,
    DistanceMetric,
    ManifoldAlgorithm,
    PhoneSetType,
    PhoneType,
    WordType,
)
from montreal_forced_aligner.db import Corpus, Phone, Speaker, Utterance  # noqa
from montreal_forced_aligner.utils import DatasetType, inspect_database  # noqa
from PySide6 import QtCore, QtGui, QtMultimedia, QtSvgWidgets, QtWidgets

import anchor.resources_rc  # noqa
from anchor.models import (
    CorpusModel,
    CorpusSelectionModel,
    DiarizationModel,
    DictionaryTableModel,
    OovModel,
    SpeakerModel,
    TextFilterQuery,
)
from anchor.plot import UtteranceClusterView, UtteranceView
from anchor.settings import AnchorSettings
from anchor.workers import Worker

if TYPE_CHECKING:
    from anchor.main import MainWindow

outside_column_ratio = 0.2
outside_column_minimum = 250


class ErrorButtonBox(QtWidgets.QDialogButtonBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Close)
        self.report_bug_button = QtWidgets.QPushButton("Report bug")
        self.report_bug_button.setIcon(QtGui.QIcon(":external-link.svg"))
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
        self.corpus_model = None
        self.selection_model = None
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1)
        self.timer.timeout.connect(self.checkStop)
        # self.positionChanged.connect(self.checkStop)
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
        self.mediaStatusChanged.connect(self.update_load)
        self.fade_in_anim = QtCore.QPropertyAnimation(self._audio_output, b"volume")
        self.fade_in_anim.setDuration(10)
        self.fade_in_anim.setStartValue(0.1)
        self.fade_in_anim.setEndValue(self._audio_output.volume())
        self.fade_in_anim.setEasingCurve(QtCore.QEasingCurve.Type.Linear)
        self.fade_in_anim.setKeyValueAt(0.1, 0.1)

        self.fade_out_anim = QtCore.QPropertyAnimation(self._audio_output, b"volume")
        self.fade_out_anim.setDuration(5)
        self.fade_out_anim.setStartValue(self._audio_output.volume())
        self.fade_out_anim.setEndValue(0)
        self.fade_out_anim.setEasingCurve(QtCore.QEasingCurve.Type.Linear)
        self.fade_out_anim.setKeyValueAt(0.1, self._audio_output.volume())
        self.fade_out_anim.finished.connect(super().pause)
        self.file_path = None

    def update_load(self, state):
        if state == self.MediaStatus.LoadedMedia:
            self.reset_position()
            self.audioReady.emit(True)

    def handle_error(self, *args):
        print("ERROR")
        print(args)

    def play(self) -> None:
        if self.startTime() is None:
            return
        self._audio_output.setVolume(0.1)
        if (
            self.playbackState() == QtMultimedia.QMediaPlayer.PlaybackState.StoppedState
            or self.currentTime() < self.startTime()
            or self.currentTime() >= self.maxTime()
        ):
            self.setCurrentTime(self.startTime())
        super(MediaPlayer, self).play()
        self.fade_in_anim.start()

    def startTime(self):
        if self.selection_model.selected_min_time is not None:
            return self.selection_model.selected_min_time
        return self.selection_model.min_time

    def maxTime(self):
        if self.selection_model.selected_max_time is not None:
            return self.selection_model.selected_max_time
        return self.selection_model.max_time

    def reset_position(self):
        state = self.playbackState()
        if state == QtMultimedia.QMediaPlayer.PlaybackState.StoppedState:
            self.timer.stop()
            self.setCurrentTime(self.startTime())
            self.timeChanged.emit(self.currentTime())
        elif state == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
            self.timer.start()
        elif state == QtMultimedia.QMediaPlayer.PlaybackState.PausedState:
            self.timer.stop()

    def update_audio_device(self):
        self._audio_output.setDevice(self.devices.defaultAudioOutput())

    def refresh_settings(self):
        self.settings.sync()
        o = None
        for o in QtMultimedia.QMediaDevices.audioOutputs():
            if o.id() == self.settings.value(self.settings.AUDIO_DEVICE):
                break
        self._audio_output.setDevice(o)

    def set_corpus_models(
        self, corpus_model: Optional[CorpusModel], selection_model: Optional[CorpusSelectionModel]
    ):
        self.corpus_model = corpus_model
        self.selection_model = selection_model
        if corpus_model is None:
            return
        # self.selection_model.fileAboutToChange.connect(self.unload_file)
        self.selection_model.fileChanged.connect(self.loadNewFile)
        self.selection_model.viewChanged.connect(self.update_times)
        self.selection_model.selectionAudioChanged.connect(self.update_selection_times)
        self.selection_model.currentTimeChanged.connect(self.update_selection_times)

    def set_volume(self, volume: int):
        if self.audioOutput() is None:
            return
        linearVolume = QtMultimedia.QAudio.convertVolume(
            volume / 100.0,
            QtMultimedia.QAudio.VolumeScale.LogarithmicVolumeScale,
            QtMultimedia.QAudio.VolumeScale.LinearVolumeScale,
        )
        self.audioOutput().setVolume(linearVolume)

    def volume(self) -> int:
        if self.audioOutput() is None:
            return 100
        volume = self.audioOutput().volume()
        volume = QtMultimedia.QAudio.convertVolume(
            volume / 100.0,
            QtMultimedia.QAudio.VolumeScale.LinearVolumeScale,
            QtMultimedia.QAudio.VolumeScale.LogarithmicVolumeScale,
        )
        return int(volume)

    def update_selection_times(self):
        self.setCurrentTime(self.startTime())

    def update_times(self):
        if (
            self.playbackState() == QtMultimedia.QMediaPlayer.PlaybackState.StoppedState
            or self.currentTime() < self.startTime()
            or self.currentTime() > self.maxTime()
        ):
            self.setCurrentTime(self.startTime())

    def loadNewFile(self, *args):
        self.audioReady.emit(False)
        self.stop()
        try:
            new_file = self.selection_model.current_file.sound_file.sound_file_path
        except Exception:
            self.setSource(QtCore.QUrl())
            return
        if (
            self.selection_model.max_time is None
            or self.selection_model.current_file is None
            or self.selection_model.current_file.duration is None
        ):
            self.setSource(QtCore.QUrl())
            return
        self.channels = self.selection_model.current_file.num_channels
        self.setSource(f"file:///{new_file}")
        self.setPosition(0)
        self.audioReady.emit(True)

    def currentTime(self):
        pos = self.position()
        return pos / 1000

    def setMaxTime(self, max_time):
        if max_time is None:
            return
        self.max_time = max_time * 1000

    def setMinTime(
        self, min_time
    ):  # Positions for MediaPlayer are in milliseconds, no SR required
        if min_time is None:
            min_time = 0
        self.min_time = int(min_time * 1000)
        self.setCurrentTime(min_time)

    def setCurrentTime(self, time):
        if time is None:
            time = 0
        if self.playbackState() == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
            return
        pos = int(time * 1000)
        self.setPosition(pos)
        self.timeChanged.emit(self.currentTime())

    def checkStop(self):
        if not self.hasAudio():
            self.stop()
            self.setSource(
                QtCore.QUrl.fromLocalFile(
                    self.selection_model.current_file.sound_file.sound_file_path
                )
            )
            self.play()
            return
        if self.playbackState() == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
            if self.maxTime() is None or self.currentTime() > self.maxTime():
                self.stop()
                self.reset_position()
        self.timeChanged.emit(self.currentTime())


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
        clear_icon = QtGui.QIcon()
        clear_icon.addFile(":clear.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.Off)
        clear_icon.addFile(":disabled/clear.svg", mode=QtGui.QIcon.Mode.Active)

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


class AnchorTableView(QtWidgets.QTableView):
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

    def setModel(self, model: QtCore.QAbstractItemModel) -> None:
        super(AnchorTableView, self).setModel(model)
        self.model().newResults.connect(self.scrollToTop)
        self.selectionModel().clear()
        self.horizontalHeader().sortIndicatorChanged.connect(self.model().update_sort)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        copy_combo = QtCore.QKeyCombination(QtCore.Qt.Modifier.CTRL, QtCore.Qt.Key.Key_C)
        if event.keyCombination() == copy_combo:
            clipboard = QtGui.QGuiApplication.clipboard()
            current = self.selectionModel().currentIndex()
            text = self.selectionModel().model().data(current, QtCore.Qt.ItemDataRole.DisplayRole)
            clipboard.setText(str(text))

    def refresh_settings(self):
        self.settings.sync()
        self.horizontalHeader().setFont(self.settings.font)
        self.setFont(self.settings.font)
        fm = QtGui.QFontMetrics(self.settings.font)
        minimum = 100
        for i in range(self.horizontalHeader().count()):
            text = self.model().headerData(
                i, QtCore.Qt.Orientation.Horizontal, QtCore.Qt.ItemDataRole.DisplayRole
            )

            width = fm.boundingRect(text).width() + (3 * self.settings.sort_indicator_padding)
            if width < minimum and i != 0:
                minimum = width
            self.setColumnWidth(i, width)
        self.horizontalHeader().setMinimumSectionSize(minimum)


class UtteranceListTable(AnchorTableView):
    def __init__(self, *args):
        super().__init__(*args)
        self.header = HeaderView(QtCore.Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(self.header)

    def set_models(self, model: CorpusModel, selection_model: CorpusSelectionModel):
        self.setModel(model)
        self.setSelectionModel(selection_model)
        self.doubleClicked.connect(self.selectionModel().focusUtterance)
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
        self.corpus_model = corpus_model
        layout = QtWidgets.QHBoxLayout()
        self.line_edit = QtWidgets.QLineEdit(self)
        # self.model = QtCore.QStringListModel(self)
        # self.completer.setModel(self.model)
        layout.addWidget(self.line_edit)
        clear_icon = QtGui.QIcon()
        clear_icon.addFile(":clear.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.Off)
        clear_icon.addFile(":disabled/clear.svg", mode=QtGui.QIcon.Mode.Active)
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
        model = QtCore.QStringListModel(list(self.completions.keys()))
        completer = QtWidgets.QCompleter(self)
        completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        completer.setModelSorting(QtWidgets.QCompleter.ModelSorting.CaseInsensitivelySortedModel)
        completer.setCompletionMode(QtWidgets.QCompleter.CompletionMode.PopupCompletion)
        completer.popup().setUniformItemSizes(True)
        completer.popup().setLayoutMode(QtWidgets.QListView.LayoutMode.Batched)
        completer.setModel(model)
        self.line_edit.setCompleter(completer)
        # self.line_edit.textChanged.connect(completer.setCompletionPrefix)


class ClearableDropDown(QtWidgets.QWidget):
    def __init__(self, *args):
        super(ClearableDropDown, self).__init__(*args)
        self.combo_box = QtWidgets.QComboBox(self)
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.combo_box)
        clear_icon = QtGui.QIcon()
        clear_icon.addFile(":clear.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.Off)
        clear_icon.addFile(":disabled/clear.svg", mode=QtGui.QIcon.Mode.Active)
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
        self.current_page = 0
        self.limit = 1
        self.num_pages = 1
        self.result_count = 0
        self.next_page_action = QtGui.QAction(
            icon=QtGui.QIcon(":caret-right.svg"), text="Next page"
        )
        self.previous_page_action = QtGui.QAction(
            icon=QtGui.QIcon(":caret-left.svg"), text="Previous page"
        )
        self.page_label = QtWidgets.QLabel("Page 1 of 1")
        self.addAction(self.previous_page_action)
        self.addWidget(self.page_label)
        self.addAction(self.next_page_action)
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
        self.pagination_toolbar.pageRequested.connect(self.table_widget.scrollToTop())
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
            self.selection_model.update_view_times(force_update=True)
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
        font = self.settings.font
        header_font = self.settings.big_font

        self.file_dropdown.setFont(font)
        self.setFont(header_font)
        self.icon_delegate.refresh_settings()
        self.highlight_delegate.refresh_settings()
        self.nowrap_delegate.refresh_settings()
        self.search_box.setFont(font)
        self.replace_box.setFont(font)
        self.search_box.setStyleSheet(self.settings.search_box_style_sheet)
        self.replace_box.setStyleSheet(self.settings.search_box_style_sheet)
        self.table_widget.refresh_settings()
        self.pagination_toolbar.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))

    def search(self):
        self.selection_model.clearSelection()
        new_query = (
            self.search_box.query,
            self.file_dropdown.current_text(),
            self.speaker_dropdown.current_text(),
            self.oov_button.isChecked(),
        )
        if new_query != self.cached_query:
            self.pagination_toolbar.reset()
            self.corpus_model.current_offset = 0
        self.corpus_model.search(
            self.search_box.query(),
            self.file_dropdown.current_text(),
            self.speaker_dropdown.current_text(),
            oovs=self.oov_button.isChecked(),
        )
        self.corpus_model.set_text_filter(self.search_box.query())

    def replace(self):
        search_query = self.search_box.query()
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
        selection_model: CorpusSelectionModel,
        dictionary_model: DictionaryTableModel,
    ):
        self.corpus_model = corpus_model
        self.selection_model = selection_model
        self.dictionary_model = dictionary_model
        self.corpus_model.textFilterChanged.connect(self.plot_widget.set_search_term)
        self.selection_model.viewChanged.connect(self.update_to_slider)
        self.selection_model.fileChanged.connect(self.update_to_slider)
        self.plot_widget.set_models(corpus_model, selection_model, self.dictionary_model)

    def update_to_slider(self):
        with QtCore.QSignalBlocker(self.scroll_bar):
            if self.selection_model.current_file is None or self.selection_model.min_time is None:
                return
            if (
                self.selection_model.min_time == 0
                and self.selection_model.max_time == self.selection_model.current_file.duration
            ):
                self.scroll_bar.setPageStep(10)
                self.scroll_bar.setEnabled(False)
                self.pan_left_button.setEnabled(False)
                self.pan_right_button.setEnabled(False)
                self.scroll_bar.setMaximum(0)
                return
            duration_ms = int(self.selection_model.current_file.duration * 1000)
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

    def refresh_settings(self):
        if not self.has_logo:
            return
        self.settings.sync()
        font = self.settings.big_font
        self.text_label.setFont(font)
        self.exit_label.setFont(font)

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

        clear_icon = QtGui.QIcon()
        clear_icon.addFile(":clear.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.Off)
        clear_icon.addFile(":disabled/clear.svg", mode=QtGui.QIcon.Mode.Active)
        self.clear_action = QtGui.QAction(icon=clear_icon, parent=self)
        self.clear_action.triggered.connect(self.clear)
        self.clear_action.setVisible(False)
        self.textChanged.connect(self.check_contents)
        self.add_internal_action(self.clear_action, "clear_field")

    def setFont(self, a0: QtGui.QFont) -> None:
        super().setFont(a0)
        self.clear_action.setFont(a0)

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
        self.returnPressed.connect(self.activate)

        self.clear_action.triggered.connect(self.returnPressed.emit)

        regex_icon = QtGui.QIcon()
        regex_icon.addFile(":regex.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.Off)
        regex_icon.addFile(
            ":highlighted/regex.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.On
        )

        self.regex_action = QtGui.QAction(icon=regex_icon, parent=self)
        self.regex_action.setCheckable(True)

        word_icon = QtGui.QIcon()
        word_icon.addFile(":word.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.Off)
        word_icon.addFile(
            ":highlighted/word.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.On
        )
        self.word_action = QtGui.QAction(icon=word_icon, parent=self)
        self.word_action.setCheckable(True)

        case_icon = QtGui.QIcon()
        case_icon.addFile(":case.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.Off)
        case_icon.addFile(
            ":highlighted/case.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.On
        )
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

    def setFont(self, a0: QtGui.QFont) -> None:
        super().setFont(a0)
        self.regex_action.setFont(a0)
        self.word_action.setFont(a0)
        self.case_action.setFont(a0)

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
            self.regex_action.isChecked() or self.word_action.isChecked(),
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
        self.doc.setDefaultFont(self.settings.font)

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
        self.doc.setDefaultFont(self.settings.font)

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
        self.setHighlightSections(False)
        self.setStretchLastSection(True)
        self.setSortIndicatorShown(True)
        self.setSectionsClickable(True)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.generate_context_menu)

    def sectionSizeFromContents(self, logicalIndex: int) -> QtCore.QSize:
        settings = AnchorSettings()
        size = super().sectionSizeFromContents(logicalIndex)
        size.setWidth(size.width() + settings.text_padding + 3 + settings.sort_indicator_padding)
        return size

    def showHideColumn(self):
        index = self.model()._header_data.index(self.sender().text())
        self.setSectionHidden(index, not self.isSectionHidden(index))

    def generate_context_menu(self, location):
        menu = QtWidgets.QMenu()
        m: CorpusModel = self.model()
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
        menu.exec_(self.mapToGlobal(location))


class IconDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super(IconDelegate, self).__init__(parent)
        from anchor.main import AnchorSettings

        self.settings = AnchorSettings()

    def refresh_settings(self):
        self.settings.sync()

    def sizeHint(
        self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex
    ) -> QtCore.QSize:
        if index.column() != 0:
            return super(IconDelegate, self).sizeHint(option, index)
        size = int(self.settings.icon_size / 2)
        return QtCore.QSize(size, size)

    def paint(self, painter: QtGui.QPainter, option, index) -> None:
        if index.column() != 0:
            return super(IconDelegate, self).paint(painter, option, index)
        painter.save()
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        if options.checkState == QtCore.Qt.CheckState.Checked:
            icon = QtGui.QIcon(":disabled/oov-check.svg")
            icon.paint(painter, options.rect, QtCore.Qt.AlignmentFlag.AlignCenter)

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
        self.cancel_action.setIcon(QtGui.QIcon(":clear.svg"))
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
        self.done_icon = QtGui.QIcon(":check-circle.svg")
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

        self.cluster_algorithm_dropdown = QtWidgets.QComboBox()
        for ct in ClusterType:
            self.cluster_algorithm_dropdown.addItem(ct.name)

        self.metric_dropdown = QtWidgets.QComboBox()
        for m in DistanceMetric:
            self.metric_dropdown.addItem(m.name)

        self.row_indices = {}
        self.cluster_algorithm_dropdown.setCurrentIndex(
            self.cluster_algorithm_dropdown.findText(
                self.settings.value(self.settings.CLUSTER_TYPE)
            )
        )

        self.visualization_size_edit = QtWidgets.QSpinBox(self)
        self.visualization_size_edit.setMinimum(100)
        self.visualization_size_edit.setMaximum(10000)
        self.visualization_size_edit.setValue(5000)
        self.form_layout.addRow("Visualization limit", self.visualization_size_edit)
        self.perplexity_edit = ThresholdWidget(self)
        self.form_layout.addRow("Perplexity", self.perplexity_edit)
        self.metric_dropdown.setCurrentIndex(
            self.metric_dropdown.findText(self.settings.value(self.settings.CLUSTERING_METRIC))
        )
        self.form_layout.addRow("Distance metric", self.metric_dropdown)
        self.form_layout.addRow("Cluster algorithm", self.cluster_algorithm_dropdown)
        self.n_clusters_edit = QtWidgets.QSpinBox(self)
        self.n_clusters_edit.setMinimum(0)
        self.n_clusters_edit.setMaximum(600)
        self.row_indices["n_clusters"] = self.form_layout.rowCount()
        self.form_layout.addRow("Number of clusters", self.n_clusters_edit)
        self.distance_threshold_edit = ThresholdWidget(self)
        self.row_indices["distance_threshold"] = self.form_layout.rowCount()
        self.form_layout.addRow("Distance threshold", self.distance_threshold_edit)

        self.min_cluster_size_edit = QtWidgets.QSpinBox(self)
        self.min_cluster_size_edit.setMinimum(3)
        self.min_cluster_size_edit.setMaximum(600)
        self.row_indices["min_cluster_size"] = self.form_layout.rowCount()
        self.form_layout.addRow("Minimum cluster size", self.min_cluster_size_edit)

        self.recluster_button = QtWidgets.QPushButton("Recluster")
        self.recluster_button.setEnabled(False)
        self.form_layout.addWidget(self.recluster_button)

        self.n_clusters_edit.setValue(self.settings.value(self.settings.CLUSTERING_N_CLUSTERS))
        self.distance_threshold_edit.setValue(
            self.settings.value(self.settings.CLUSTERING_DISTANCE_THRESHOLD)
        )
        self.min_cluster_size_edit.setValue(
            self.settings.value(self.settings.CLUSTERING_MIN_CLUSTER_SIZE)
        )
        self.perplexity_edit.setValue(30.0)
        self.scroll_area.setLayout(self.form_layout)
        layout.addWidget(self.scroll_area)
        self.scroll_area.setFixedWidth(
            500 + self.scroll_area.verticalScrollBar().sizeHint().width()
        )
        self.scroll_area.setFixedHeight(300)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLayout(layout)
        self.update_current_cluster_algorithm()
        self.cluster_algorithm_dropdown.currentIndexChanged.connect(
            self.update_current_cluster_algorithm
        )
        self.metric_dropdown.currentIndexChanged.connect(self.update_current_metric)

    def update_current_metric(self):
        metric = self.metric_dropdown.currentText()
        self.settings.setValue(self.settings.CLUSTERING_METRIC, metric)

    def update_current_cluster_algorithm(self):
        current_algorithm = self.cluster_algorithm_dropdown.currentText()

        if current_algorithm in ["kmeans", "spectral", "agglomerative"]:
            self.form_layout.setRowVisible(self.row_indices["n_clusters"], True)
        else:
            self.form_layout.setRowVisible(self.row_indices["n_clusters"], False)

        if current_algorithm in ["optics", "hdbscan", "dbscan", "agglomerative"]:
            self.form_layout.setRowVisible(self.row_indices["distance_threshold"], True)
        else:
            self.form_layout.setRowVisible(self.row_indices["distance_threshold"], False)

        if current_algorithm in ["optics", "hdbscan", "dbscan"]:
            self.form_layout.setRowVisible(self.row_indices["min_cluster_size"], True)
        else:
            self.form_layout.setRowVisible(self.row_indices["min_cluster_size"], False)
        self.settings.setValue(self.settings.CLUSTER_TYPE, current_algorithm)
        self.settings.sync()

    @property
    def cluster_kwargs(self):
        self.settings.sync()
        current_algorithm = ClusterType[self.settings.value(self.settings.CLUSTER_TYPE)]
        metric = DistanceMetric[self.settings.value(self.settings.CLUSTERING_METRIC)]
        kwargs = {
            "cluster_type": current_algorithm,
            "metric_type": metric,
            "limit": int(self.visualization_size_edit.value()),
        }
        if current_algorithm in [
            ClusterType.kmeans,
            ClusterType.spectral,
            ClusterType.agglomerative,
        ]:
            val = self.n_clusters_edit.value()
            self.settings.setValue(self.settings.CLUSTERING_N_CLUSTERS, val)
            kwargs["n_clusters"] = val

        val = self.distance_threshold_edit.value()
        self.settings.setValue(self.settings.CLUSTERING_DISTANCE_THRESHOLD, val)
        kwargs["distance_threshold"] = val

        val = self.min_cluster_size_edit.value()
        self.settings.setValue(self.settings.CLUSTERING_MIN_CLUSTER_SIZE, val)
        kwargs["min_cluster_size"] = val

        return kwargs

    @property
    def manifold_kwargs(self):
        kwargs = {
            "metric_type": DistanceMetric[self.metric_dropdown.currentText()],
            "limit": int(self.visualization_size_edit.value()),
            "perplexity": float(self.perplexity_edit.value()),
        }
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
        layout = QtWidgets.QVBoxLayout()
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
            b.setFont(self.settings.font)
            b.clicked.connect(self.press)
            b.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            b.installEventFilter(self)

            scroll_layout.addWidget(b, row_index, col_index)
            col_index += 1
            if col_index >= column_count:
                col_index = 0
                row_index += 1
        layout.addWidget(self.scroll_area)
        widget.setLayout(scroll_layout)
        self.scroll_area.setWidget(widget)
        self.setLayout(layout)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.scroll_area.setMinimumWidth(
            widget.sizeHint().width() + self.scroll_area.verticalScrollBar().sizeHint().width()
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
        p = self.pos()
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

        accept_icon = QtGui.QIcon()
        accept_icon.addFile(
            ":check-circle.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.Off
        )
        accept_icon.addFile(
            ":highlighted/check-circle.svg",
            mode=QtGui.QIcon.Mode.Normal,
            state=QtGui.QIcon.State.On,
        )

        self.accept_action = QtGui.QAction(icon=accept_icon, parent=self)
        self.accept_action.triggered.connect(self.returnPressed.emit)

        cancel_icon = QtGui.QIcon()
        cancel_icon.addFile(":undo.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.Off)
        cancel_icon.addFile(
            ":highlighted/undo.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.On
        )

        self.cancel_action = QtGui.QAction(icon=cancel_icon, parent=self)
        self.cancel_action.triggered.connect(self.cancel)
        keyboard_icon = QtGui.QIcon()
        keyboard_icon.addFile(
            ":keyboard.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.Off
        )
        keyboard_icon.addFile(
            ":highlighted/keyboard.svg", mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.On
        )

        self.keyboard_widget = QtWidgets.QPushButton(self)
        self.keyboard_widget.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.keyboard_widget.setIcon(keyboard_icon)
        self.keyboard = IpaKeyboard(phones)
        self.keyboard.installEventFilter(self)
        self.keyboard.inputPhone.connect(self.add_phone)
        self.keyboard_widget.setMenu(self.keyboard)

        self.addWidget(self.input)
        self.addWidget(self.keyboard_widget)
        self.addAction(self.accept_action)
        self.addAction(self.cancel_action)

    def setFont(self, a0: QtGui.QFont) -> None:
        super().setFont(a0)
        self.keyboard_widget.setFont(a0)
        self.input.setFont(a0)

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
            isinstance(watched, (IpaKeyboard))
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
        size = int(self.settings.icon_size / 2)
        x = r.left() + r.width() - self.settings.icon_size
        y = r.top()
        options = QtWidgets.QStyleOptionViewItem(option)
        options.rect = QtCore.QRect(x, y, size, r.height())
        self.initStyleOption(options, index)
        icon = QtGui.QIcon(":external-link.svg")
        icon.paint(painter, options.rect, QtCore.Qt.AlignmentFlag.AlignCenter)

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
        size = int(self.settings.icon_size / 2)
        x = r.left() + r.width() - self.settings.icon_size
        y = r.top()
        options = QtWidgets.QStyleOptionViewItem(option)
        options.rect = QtCore.QRect(x, y, size, r.height())
        self.initStyleOption(options, index)
        icon = QtGui.QIcon(":rotate.svg")
        icon.paint(painter, options.rect, QtCore.Qt.AlignmentFlag.AlignCenter)

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
        editor.setStyleSheet(self.settings.search_box_style_sheet)
        editor.setFont(self.settings.font)
        return editor

    def setEditorData(
        self,
        editor: PronunciationInput,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> None:
        editor.setText(index.model().data(index, QtCore.Qt.ItemDataRole.EditRole))

    def setModelData(
        self,
        editor: PronunciationInput,
        model: DictionaryTableModel,
        index: typing.Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
    ) -> None:
        value = editor.text().strip()
        if editor.original_text != value:
            model.setData(index, value, QtCore.Qt.ItemDataRole.EditRole)
            model.submit()

    def updateEditorGeometry(
        self,
        editor: PronunciationInput,
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
        editor.setStyleSheet(self.settings.search_box_style_sheet)
        editor.setFont(self.settings.font)
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
        self.header = HeaderView(QtCore.Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(self.header)
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
        self.header = HeaderView(QtCore.Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(self.header)
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

        elif index.column() == 1:
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
        self.header = HeaderView(QtCore.Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(self.header)
        self.button_delegate = ButtonDelegate(":magnifying-glass.svg", self)
        self.edit_delegate = EditableDelegate(self)
        self.speaker_delegate = SpeakerViewDelegate(self)
        self.setItemDelegateForColumn(1, self.speaker_delegate)
        self.setItemDelegateForColumn(0, self.edit_delegate)
        self.setItemDelegateForColumn(4, self.button_delegate)
        self.setItemDelegateForColumn(5, self.button_delegate)
        self.clicked.connect(self.cluster_utterances)
        self.doubleClicked.connect(self.search_speaker)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)

        self.customContextMenuRequested.connect(self.generate_context_menu)
        self.add_speaker_action = QtGui.QAction("Compare speakers", self)
        self.add_speaker_action.triggered.connect(self.add_speakers)

    def add_speakers(self):
        selected_rows = self.selectionModel().selectedRows(0)
        if not selected_rows:
            return
        speakers = [self.speaker_model.speakerAt(index.row()) for index in selected_rows]
        self.speaker_model.change_current_speaker(speakers)

    def generate_context_menu(self, location):
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(self.settings.menu_style_sheet)
        menu.addAction(self.add_speaker_action)
        menu.exec_(self.mapToGlobal(location))

    def set_models(self, model: SpeakerModel):
        self.speaker_model = model
        self.setModel(model)
        self.refresh_settings()

    def cluster_utterances(self, index: QtCore.QModelIndex):
        if not index.isValid() or index.column() < 4:
            return
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
        name_label.setFont(self.settings.font)
        info_layout.addRow(name_label, self.label)
        path_label = QtWidgets.QLabel("Path")
        path_label.setFont(self.settings.font)
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
        self.label.setFont(self.settings.font)
        self.path_label.setFont(self.settings.font)
        # self.path_label.setWordWrap(True)

    def refresh(self):
        self.tree.clear()
        if self.model is not None:
            self.label.setText(self.model.name)
            self.path_label.setText(str(self.model.source))
            meta = self.model.meta
            for k, v in meta.items():
                node = QtWidgets.QTreeWidgetItem(self.tree)

                label = QtWidgets.QLabel(str(k))
                label.setFont(self.settings.font)
                self.tree.setItemWidget(node, 0, label)
                if isinstance(v, dict):
                    for k2, v2 in v.items():
                        child_node = QtWidgets.QTreeWidgetItem(node)

                        label = QtWidgets.QLabel(str(k2))
                        label.setFont(self.settings.font)
                        self.tree.setItemWidget(child_node, 0, label)

                        label = QtWidgets.QLabel(str(v2))
                        label.setWordWrap(True)
                        label.setFont(self.settings.font)
                        self.tree.setItemWidget(child_node, 1, label)
                else:
                    label = QtWidgets.QLabel(str(v))
                    label.setWordWrap(True)
                    label.setFont(self.settings.font)
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
        if self.corpus_model.acoustic_model is not None:
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


class SpeakerViewDelegate(QtWidgets.QStyledItemDelegate):
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
        size = int(self.settings.icon_size / 2)
        x = r.left() + r.width() - self.settings.icon_size
        y = r.top()
        options = QtWidgets.QStyleOptionViewItem(option)
        options.rect = QtCore.QRect(x, y, size, r.height())
        self.initStyleOption(options, index)
        icon = QtGui.QIcon(":external-link.svg")
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
        size = int(self.settings.icon_size / 2)
        x = r.left() + r.width() - self.settings.icon_size
        y = r.top()
        options = QtWidgets.QStyleOptionViewItem(option)
        options.rect = QtCore.QRect(x, y, size, r.height())
        self.initStyleOption(options, index)
        icon = QtGui.QIcon(self.icon_path)
        icon.paint(painter, options.rect, QtCore.Qt.AlignmentFlag.AlignCenter)

        painter.restore()


class SpeakerClustersWidget(QtWidgets.QWidget):
    search_requested = QtCore.Signal(object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        self.search_requested.emit(mean_ivector)

    def change_speaker(self):
        if len(self.speaker_model.current_speakers) > 1:
            print(self.plot_widget.updated_indices)
            if not self.plot_widget.updated_indices:
                return
            previous_speakers = set(
                [
                    self.speaker_model.utt2spk[self.speaker_model.utterance_ids[x]]
                    for x in self.plot_widget.updated_indices
                ]
            )
            for s_id in self.plot_widget.brushes.keys():
                print("NEW", s_id)
                current_indices = [
                    x
                    for x in self.plot_widget.updated_indices
                    if self.speaker_model.cluster_labels[x] == s_id
                    and self.speaker_model.utt2spk[self.speaker_model.utterance_ids[x]] != s_id
                ]
                print(current_indices)
                if not current_indices:
                    continue
                if s_id <= 0:
                    utterance_ids = self.speaker_model.utterance_ids[current_indices].tolist()
                    self.speaker_model.change_speaker(
                        utterance_ids, self.speaker_model.current_speakers[0], s_id
                    )
                    continue

                for old_id in previous_speakers:
                    if s_id == old_id:
                        continue
                    utterance_ids = [
                        x
                        for x in self.speaker_model.utterance_ids[current_indices].tolist()
                        if self.speaker_model.utt2spk[x] == old_id
                    ]

                    if not utterance_ids:
                        continue
                    self.speaker_model.change_speaker(utterance_ids, old_id, s_id)
            self.plot_widget.updated_indices = set()
            self.plot_widget.selected_indices = set()
        else:
            if not self.plot_widget.selected_indices:
                return
            indices = np.array(list(self.plot_widget.selected_indices))
            utterance_ids = self.speaker_model.utterance_ids[indices].tolist()
            self.speaker_model.change_speaker(
                utterance_ids, self.speaker_model.current_speakers[0], 0
            )

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
        self.header = HeaderView(QtCore.Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(self.header)
        self.setSortingEnabled(False)
        self.speaker_delegate = SpeakerViewDelegate(self)
        self.button_delegate = ButtonDelegate(":compress.svg", self)
        self.setItemDelegateForColumn(0, self.speaker_delegate)
        self.setItemDelegateForColumn(1, self.speaker_delegate)
        self.setItemDelegateForColumn(3, self.speaker_delegate)
        self.setItemDelegateForColumn(6, self.button_delegate)
        self.setItemDelegateForColumn(7, self.button_delegate)
        self.doubleClicked.connect(self.search_utterance)
        self.clicked.connect(self.reassign_utterance)
        self.diarization_model: Optional[DiarizationModel] = None
        self.selection_model: Optional[CorpusSelectionModel] = None
        self.set_reference_utterance_action = QtGui.QAction("Use utterance as reference", self)
        self.set_reference_utterance_action.triggered.connect(self.set_reference_utterance)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.generate_context_menu)

    def generate_context_menu(self, location):
        menu = QtWidgets.QMenu()
        menu.addAction(self.set_reference_utterance_action)
        menu.exec_(self.mapToGlobal(location))

    def set_reference_utterance(self):
        rows = self.selectionModel().selectedRows()
        if not rows:
            return
        utterance_id = self.diarization_model._utterance_ids[rows[0].row()]
        self.diarization_model.set_utterance_filter(utterance_id)
        self.referenceUtteranceSelected.emit(
            self.diarization_model.data(
                self.diarization_model.createIndex(rows[0].row(), 0),
                QtCore.Qt.ItemDataRole.DisplayRole,
            )
        )

    def set_models(self, model: DiarizationModel, selection_model: CorpusSelectionModel):
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
        if not index.isValid() or index.column() not in {0, 1, 3}:
            return
        if index.column() == 0:
            row = index.row()
            utterance_id = self.diarization_model._utterance_ids[row]
            if utterance_id is None:
                return
            with self.diarization_model.corpus_model.corpus.session() as session:
                try:
                    file_id, begin, end, channel = (
                        session.query(
                            Utterance.file_id, Utterance.begin, Utterance.end, Utterance.channel
                        )
                        .filter(Utterance.id == utterance_id)
                        .first()
                    )
                except TypeError:
                    self.selection_model.clearSelection()
                    return
        else:
            if index.column() == 1:
                speaker_id = self.diarization_model._suggested_indices[index.row()]
            else:
                speaker_id = self.diarization_model._speaker_indices[index.row()]
            with self.diarization_model.corpus_model.corpus.session() as session:
                c = session.query(Corpus).first()
                try:
                    file_id, begin, end, channel = (
                        session.query(
                            Utterance.file_id, Utterance.begin, Utterance.end, Utterance.channel
                        )
                        .join(Utterance.speaker)
                        .filter(Utterance.speaker_id == speaker_id)
                        .order_by(
                            c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column)
                        )
                        .first()
                    )
                except TypeError:
                    print(speaker_id)
                    print(
                        session.query(
                            Utterance.file_id, Utterance.begin, Utterance.end, Utterance.channel
                        )
                        .join(Utterance.speaker)
                        .filter(Utterance.speaker_id == speaker_id)
                        .order_by(
                            c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column)
                        )
                    )
                    self.selection_model.clearSelection()
                    return
        self.selection_model.set_current_file(
            file_id,
            begin,
            end,
            channel,
            force_update=True,
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
        self.pagination_toolbar.pageRequested.connect(self.table.scrollToTop())
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

    def set_models(self, model: DiarizationModel, selection_model: CorpusSelectionModel):
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
        layout = QtWidgets.QFormLayout()
        self.acoustic_model_label = QtWidgets.QLabel("Not loaded")
        self.dictionary_label = QtWidgets.QLabel("Not loaded")
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
        layout.addRow(QtWidgets.QLabel("Acoustic model"), self.acoustic_model_label)
        layout.addRow(QtWidgets.QLabel("Dictionary"), self.dictionary_label)
        layout.addRow(QtWidgets.QLabel("Beam"), self.beam)
        layout.addRow(QtWidgets.QLabel("Retry beam"), self.retry_beam)
        layout.addRow(QtWidgets.QLabel("Silence boost factor"), self.silence_boost)
        layout.addRow(QtWidgets.QLabel("Fine tune"), self.fine_tune_check)
        layout.addRow(QtWidgets.QLabel("Cutoff modeling"), self.cutoff_check)
        layout.addWidget(self.button)
        self.text = QtWidgets.QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        self.setLayout(layout)
        self.corpus_model: Optional[CorpusModel] = None

    def refresh(self):
        validate_enabled = True
        if self.corpus_model.has_dictionary:
            self.dictionary_label.setText(self.corpus_model.corpus.dictionary_model.name)
        else:
            validate_enabled = False
            self.dictionary_label.setText("Not loaded")
        if self.corpus_model.acoustic_model is not None:
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
        self.pagination_toolbar.pageRequested.connect(self.table.scrollToTop())
        dict_layout.addWidget(self.pagination_toolbar)

        self.setLayout(dict_layout)
        self.refresh_settings()

    def refresh_settings(self):
        self.settings.sync()
        font = self.settings.font
        self.table.refresh_settings()
        self.pagination_toolbar.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))
        self.search_box.setFont(font)
        self.search_box.setStyleSheet(self.settings.search_box_style_sheet)

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
        self.refresh_word_counts_action.setIcon(QtGui.QIcon(":oov-check.svg"))
        self.refresh_word_counts_action.setEnabled(True)
        self.toolbar.addAction(self.refresh_word_counts_action)
        self.rebuild_lexicon_action = QtGui.QAction(self)
        self.rebuild_lexicon_action.setIcon(QtGui.QIcon(":rotate.svg"))
        self.rebuild_lexicon_action.setEnabled(True)
        self.toolbar.addAction(self.rebuild_lexicon_action)
        dict_layout.addWidget(self.toolbar)
        dict_layout.addWidget(self.table)
        self.pagination_toolbar = PaginationWidget()
        self.pagination_toolbar.pageRequested.connect(self.table.scrollToTop())
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
        font = self.settings.font
        self.table.refresh_settings()
        self.pagination_toolbar.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))
        self.search_box.setFont(font)
        self.search_box.setStyleSheet(self.settings.search_box_style_sheet)

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

        self.speaker_dropdown = CompleterLineEdit(self, corpus_model=corpus_model)
        self.speaker_dropdown.line_edit.setPlaceholderText("Filter by speaker")
        self.speaker_dropdown.line_edit.returnPressed.connect(self.accept())
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
        font = self.settings.font
        self.speaker_dropdown.setFont(font)
        self.setStyleSheet(self.settings.style_sheet)
        self.speaker_dropdown.setStyleSheet(self.settings.combo_box_style_sheet)


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
        self.pagination_toolbar.pageRequested.connect(self.table.scrollToTop())
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
        if speaker_filter is None:
            speaker_id = self.speaker_dropdown.current_text()
            if isinstance(speaker_id, str):
                with self.speaker_model.corpus_model.corpus.session() as session:
                    actual_speaker_id = (
                        session.query(Speaker.id).filter(Speaker.name == speaker_id).first()
                    )
                    if actual_speaker_id is None:
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
        selection_model: CorpusSelectionModel,
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
        font = self.settings.font
        self.speaker_edit.setFont(font)
        self.speaker_dropdown.setFont(font)
        self.speaker_dropdown.setStyleSheet(self.settings.combo_box_style_sheet)
        self.table.refresh_settings()
        self.pagination_toolbar.set_limit(
            self.table.settings.value(self.table.settings.RESULTS_PER_PAGE)
        )


class ColorEdit(QtWidgets.QPushButton):  # pragma: no cover
    def __init__(self, parent=None):
        super(ColorEdit, self).__init__(parent=parent)
        self.clicked.connect(self.open_dialog)

    def set_color(self, color: QtGui.QColor):
        self._color = color
        self.update_icon()

    def update_icon(self):
        pixmap = QtGui.QPixmap(100, 100)
        pixmap.fill(self._color)
        icon = QtGui.QIcon(pixmap)
        icon.addPixmap(pixmap, QtGui.QIcon.Mode.Disabled)
        self.setIcon(icon)

    @property
    def color(self) -> str:
        return self._color.name()

    def open_dialog(self):
        color = QtWidgets.QColorDialog.getColor()
        if color.isValid():
            self._color = color
            self.update_icon()


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
