from montreal_forced_aligner.g2p.generator import PyniniDictionaryGenerator as Generator, G2P_DISABLED

from montreal_forced_aligner.corpus.base import get_wav_info

import anchor.qrc_resources

from PyQt5 import QtGui, QtCore, QtWidgets, QtMultimedia, QtSvg

import pyqtgraph as pg
import librosa
import numpy as np
import re

outside_column_ratio = 0.2
outside_column_minimum = 250


class DetailedMessageBox(QtWidgets.QMessageBox):  # pragma: no cover
    # Adapted from http://stackoverflow.com/questions/2655354/how-to-allow-resizing-of-qmessagebox-in-pyqt4
    def __init__(self, *args, **kwargs):
        super(DetailedMessageBox, self).__init__(*args, **kwargs)
        self.setWindowTitle('Error encountered')
        self.setIcon(QtWidgets.QMessageBox.Critical)
        self.setStandardButtons(QtWidgets.QMessageBox.Close)
        self.setText("Something went wrong!")
        self.setInformativeText("Please copy the text below and send to Michael.")

        self.setMinimumWidth(200)

    def resizeEvent(self, event):
        result = super(DetailedMessageBox, self).resizeEvent(event)
        details_box = self.findChild(QtWidgets.QTextEdit)
        if details_box is not None:
            details_box.setFixedHeight(details_box.sizeHint().height())
        return result



class MediaPlayer(QtMultimedia.QMediaPlayer):  # pragma: no cover
    timeChanged = QtCore.pyqtSignal(object)
    def __init__(self):
        super(MediaPlayer, self).__init__()
        self.max_time = None
        self.min_time = None
        self.start_time = 0
        self.sr = None
        self.setNotifyInterval(1)
        self.positionChanged.connect(self.checkStop)
        self.buf = QtCore.QBuffer()

    def currentTime(self):
        pos = self.position()
        return pos / 1000

    def setMaxTime(self, max_time):
        self.max_time = max_time * 1000

    def setMinTime(self, min_time):  # Positions for MediaPlayer are in milliseconds, no SR required
        self.min_time = min_time * 1000
        if self.start_time < self.min_time:
            self.start_time = self.min_time

    def setStartTime(self, start_time):  # Positions for MediaPlayer are in milliseconds, no SR required
        self.start_time = start_time * 1000

    def setCurrentTime(self, time):
        if self.state() == QtMultimedia.QMediaPlayer.PlayingState:
            return
        pos = time * 1000
        self.setPosition(pos)

    def checkStop(self, position):
        if self.state() == QtMultimedia.QMediaPlayer.PlayingState:
            self.timeChanged.emit(self.currentTime())
            if self.max_time is not None:
                if position > self.max_time + 3:
                    self.stop()


def create_icon(name, default_only=False):
    if name == 'trash':
        icon = QtGui.QIcon()
        icon.addFile(f':disabled/trash.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
        icon.addFile(f':disabled/trash.svg', mode=QtGui.QIcon.Disabled)
        icon.addFile(f':disabled/trash.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.Off)
    elif name == 'volume-up':
        if default_only:
            icon = QtGui.QIcon()
            icon.addFile(f':volume-up.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
            icon.addFile(f':disabled/volume-mute.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.On)
        else:
            icon = QtGui.QIcon()
            icon.addFile(f':volume-up.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
            icon.addFile(f':disabled/volume-up.svg', mode=QtGui.QIcon.Disabled)
            icon.addFile(f':hover/volume-mute.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.On)
            icon.addFile(f':hover/volume-up.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.Off)
            icon.addFile(f':disabled/volume-mute.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.On)
    elif name == 'play':
        if default_only:
            icon = QtGui.QIcon()
            icon.addFile(f':play.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
            icon.addFile(f':pause.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.On)
            icon.addFile(f':hover/play.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.Off)
            icon.addFile(f':hover/pause.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.On)
        else:
            icon = QtGui.QIcon()
            icon.addFile(f':play.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
            icon.addFile(f':hover/play.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.Off)
    elif name == 'clear':
        icon = QtGui.QIcon(':clear.svg')
        icon.addFile(':disabled/clear.svg', mode=QtGui.QIcon.Mode.Disabled)
    else:
        if default_only:
            return QtGui.QIcon(f':{name}.svg')
        icon = QtGui.QIcon()
        icon.addFile(f':{name}.svg', mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.Off)
        icon.addFile(f':disabled/{name}.svg', mode=QtGui.QIcon.Mode.Disabled)
        icon.addFile(f':hover/{name}.svg', mode=QtGui.QIcon.Mode.Active)
        icon.addFile(f':checked/{name}.svg', mode=QtGui.QIcon.Mode.Normal, state=QtGui.QIcon.State.On)
    return icon


def create_buttonless_icon(name):
    icon = QtGui.QIcon(f':hover/{name}.svg')
    return icon


class DefaultAction(QtWidgets.QAction):
    def __init__(self, icon_name, default_icon=None, triggered_icon=None, buttonless=False, **kwargs):
        super(DefaultAction, self).__init__(**kwargs)
        self.triggered_timer = QtCore.QTimer(self)
        self.triggered.connect(self.start_trigger_state)
        self.triggered_timer.timeout.connect(self.end_trigger_state)
        self.icon_name = icon_name
        if buttonless:
            self.default_icon = create_buttonless_icon(icon_name)
            self.triggered_icon = QtGui.QIcon(f':highlighted/{icon_name}.svg')
        else:
            if default_icon is not None:
                self.default_icon = icon_name
            else:
                self.default_icon = create_icon(icon_name)
            if triggered_icon is not None:
                self.triggered_icon = triggered_icon
            else:
                self.triggered_icon = QtGui.QIcon(f':hover/{icon_name}.svg')
        self.setIcon(self.default_icon)

    def update_icons(self, use_mfa):
        if use_mfa:
            self.default_icon = create_icon(self.icon_name)
            self.triggered_icon = QtGui.QIcon(f':hover/{self.icon_name}.svg')
        else:
            self.default_icon = create_icon(self.icon_name, default_only=True)
            self.triggered_icon = self.default_icon
        self.setIcon(self.default_icon)



    def start_trigger_state(self):
        if self.isCheckable():
            return
        self.triggered_timer.start(250)
        for w in self.associatedWidgets():
            if not isinstance(w, QtWidgets.QToolButton):
                continue
            w.setFocus()
            self.setIcon(self.triggered_icon)

    def end_trigger_state(self):
        self.triggered_timer.stop()
        for w in self.associatedWidgets():
            if not isinstance(w, QtWidgets.QToolButton):
                continue
            w.clearFocus()
            self.setIcon(self.default_icon)


class AnchorAction(QtWidgets.QAction):
    def __init__(self, icon_name, **kwargs):
        super(AnchorAction, self).__init__(**kwargs)
        self.icon_name = icon_name
        if icon_name == 'volume':
            self.widget = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            self.widget.setTickInterval(1)
            self.widget.setMaximum(100)
            self.widget.setMinimum(0)
            self.widget.setMaximumWidth(100)
            self.widget.setSliderPosition(100)
        elif icon_name == 'speaker':
            self.widget = SpeakerDropDown()
            self.widget.setDefaultAction(self)
            self.setIcon(create_icon('speaker'))

    def update_icons(self, use_mfa):
        if not self.icon_name == 'speaker':
            return
        if use_mfa:
            self.setIcon(create_icon('speaker'))
        else:
            self.setIcon(create_icon('speaker', default_only=True))




class NewSpeakerField(QtWidgets.QLineEdit):
    enableAddSpeaker = QtCore.pyqtSignal(object)
    @property
    def _internal_layout(self):
        if not hasattr(self, "_internal_layout_"):
            self._internal_layout_ = QtWidgets.QHBoxLayout(self)
            self._internal_layout_.addStretch()
        self._internal_layout_.setContentsMargins(1, 1,1, 1)
        self._internal_layout_.setSpacing(0)
        return self._internal_layout_

    def add_button(self, button):
        self._internal_layout.insertWidget(self._internal_layout.count(), button)
        button.setFocusProxy(self)

    def _fix_cursor_position(self, button):
        self.setTextMargins(button.geometry().right(), 0, 0, 0)

    def __init__(self, *args):
        super(NewSpeakerField, self).__init__(*args)
        self.setObjectName('new_speaker_field')
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        clear_icon = QtGui.QIcon()
        clear_icon.addFile(':clear.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
        clear_icon.addFile(':disabled/clear.svg', mode=QtGui.QIcon.Active)

        self.clear_action = QtWidgets.QAction(icon=clear_icon, parent=self)
        self.clear_action.triggered.connect(self.clear)
        self.clear_action.setVisible(False)

        self.textChanged.connect(self.check_contents)

        self.tool_bar = QtWidgets.QToolBar()
        self.tool_bar.addAction(self.clear_action)
        w = self.tool_bar.widgetForAction(self.clear_action)
        w.setObjectName('clear_new_speaker_field')
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


class SpeakerDropDown(QtWidgets.QToolButton):
    def __init__(self, *args):
        super(SpeakerDropDown, self).__init__(*args)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.current_speaker = ''
        self.menu = QtWidgets.QMenu(self)
        self.speakers = []
        self.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
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
                self.menu.addAction(s)

        if self.current_speaker not in speakers:
            self.setCurrentSpeaker('')

    def setCurrentSpeaker(self, speaker):
        self.current_speaker = speaker
        self.setText(speaker)



class UtteranceListWidget(QtWidgets.QGroupBox):  # pragma: no cover
    utteranceChanged = QtCore.pyqtSignal(object, object)
    fileChanged = QtCore.pyqtSignal(object)
    utteranceMerged = QtCore.pyqtSignal()
    utteranceDeleted = QtCore.pyqtSignal(object)
    updateView = QtCore.pyqtSignal(object, object)

    def __init__(self,  *args):
        super(UtteranceListWidget, self).__init__('File', *args)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QtWidgets.QVBoxLayout()


        self.file_dropdown = QtWidgets.QComboBox()
        self.file_dropdown.currentTextChanged.connect(self.fileChanged.emit)
        self.file_dropdown.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.file_dropdown)

        self.table_widget = DefaultTable(use_oov_header=True)
        self.table_widget.setColumnCount(4)

        self.utterance_id_column_index = 1
        self.begin_column_index = self.utterance_id_column_index
        self.table_widget.setHorizontalHeaderLabels(['found', 'Utterance', 'Speaker', 'Text'])
        self.icon_delegate = IconDelegate(self.table_widget)
        self.table_widget.setItemDelegateForColumn(0, self.icon_delegate)
        self.table_widget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table_widget.horizontalHeader().setSectionResizeMode(self.utterance_id_column_index, QtWidgets.QHeaderView.Interactive)

        self.deleted_utts = []
        self.tool_bar_wrapper = QtWidgets.QVBoxLayout()
        self.tool_bar = QtWidgets.QToolBar()
        self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.tool_bar_wrapper.addWidget(self.tool_bar, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.table_widget)
        layout.addLayout(self.tool_bar_wrapper)
        self.setLayout(layout)
        self.corpus = None
        self.dictionary = None
        self.current_file = None
        self.error_color = '#D40000'

    def update_config(self, config):
        colors = config.color_options
        font = config.font_options
        self.error_background_color = colors['error_background_color']
        self.error_color = colors['error_text_color']
        self.table_widget.setFont(font['font'])
        self.table_widget.horizontalHeader().setFont(font['header_font'])
        self.file_dropdown.setFont(font['font'])
        self.setFont(font['header_font'])
        self.icon_delegate.update_config(config)
        self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        column_ratio = outside_column_ratio
        column_width = int(column_ratio * config['width'])
        column_width = max(column_width, outside_column_minimum)
        self.setFixedWidth(column_width)
        widget_widths = 0
        for a in self.tool_bar.actions():
            for w in a.associatedWidgets():
                if not isinstance(w, QtWidgets.QToolButton):
                    continue
                widget_widths += w.sizeHint().width()

        if widget_widths + 30 > self.width():
            self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)

    def save_file(self):
        self.saveFile.emit(self.current_file)

    def update_file_name(self, file_name):
        self.current_file = file_name
        self.refresh_list()

    def update_utterance(self, cell):
        if not cell:
            return
        utterance = self.table_widget.item(cell.row(), self.utterance_id_column_index).text()
        if self.corpus.segments:
            self.current_file = self.corpus.segments[utterance]['file_name']
        else:
            self.current_file = utterance
        self.utteranceChanged.emit(utterance, False)

    def update_and_zoom_utterance(self, cell):
        if not cell:
            return
        utterance = self.table_widget.item(cell.row(), self.utterance_id_column_index).text()
        if self.corpus.segments:
            self.current_file = self.corpus.segments[utterance]['file_name']
        else:
            self.current_file = utterance
        self.utteranceChanged.emit(utterance, True)

    def update_utterance_text(self, utterance):
        t = self.corpus.text_mapping[utterance]
        for r in range(self.table_widget.rowCount()):
            if self.table_widget.item(r, self.utterance_id_column_index).text() == utterance:
                oov_found = False
                if self.dictionary is not None:
                    words = t.split(' ')
                    for w in words:
                        if not self.dictionary.check_word(w):
                            oov_found = True
                            break
                t = QtWidgets.QTableWidgetItem()
                if oov_found:
                    t.setCheckState(QtCore.Qt.CheckState.Checked)
                else:
                    t.setCheckState(QtCore.Qt.CheckState.Unchecked)
                self.table_widget.setItem(r, 0, t)
                break

    def get_current_selection(self):
        utts = []
        for i in self.table_widget.selectedItems():
            if i.column() == self.utterance_id_column_index:
                utts.append(i.text())
        return utts

    def restore_deleted_utts(self):
        for utt_data in self.deleted_utts:
            self.corpus.add_utterance(**utt_data)

        self.refresh_list()
        self.table_widget.clearSelection()
        self.utteranceDeleted.emit(False)
        self.deleted_utts = []

    def delete_utterances(self):
        utts = self.get_current_selection()
        if len(utts) < 1:
            return
        for old_utt in utts:
            if old_utt in self.corpus.segments:
                seg = self.corpus.segments[old_utt]
                speaker = self.corpus.utt_speak_mapping[old_utt]
                file = self.corpus.utt_file_mapping[old_utt]
                text = self.corpus.text_mapping[old_utt]
                utt_data = {'utterance': old_utt, 'seg': seg, 'speaker': speaker, 'file': file,
                            'text': text}
                self.deleted_utts.append(utt_data)
                self.corpus.delete_utterance(old_utt)
        self.refresh_list()
        self.table_widget.clearSelection()
        self.utteranceDeleted.emit(True)

    def split_utterances(self):
        utts = self.get_current_selection()
        if len(utts) != 1:
            return
        old_utt = utts[0]
        if old_utt in self.corpus.segments:
            seg = self.corpus.segments[old_utt]
            speaker = self.corpus.utt_speak_mapping[old_utt]
            file = self.corpus.utt_file_mapping[old_utt]
            filename = seg['file_name']
            beg = seg['begin']
            end = seg['end']
            channel = seg['channel']
            utt_text = self.corpus.text_mapping[old_utt]
            duration = end - beg
            split_time = beg + (duration / 2)
        else:
            return

        first_utt = '{}-{}-{}-{}'.format(speaker, filename, beg, split_time).replace('.', '-')
        first_seg = {'file_name': filename, 'begin': beg, 'end': split_time, 'channel': channel}
        self.corpus.add_utterance(first_utt, speaker, file, utt_text, seg=first_seg)

        second_utt_text = ''
        if utt_text == 'speech':  # Check for segmentation
            second_utt_text = 'speech'

        second_utt = '{}-{}-{}-{}'.format(speaker, filename, split_time, end).replace('.', '-')
        second_seg = {'file_name': filename, 'begin': split_time, 'end': end, 'channel': channel}
        self.corpus.add_utterance(second_utt, speaker, file, second_utt_text, seg=second_seg)

        self.corpus.delete_utterance(old_utt)

        self.refresh_list()
        self.utteranceMerged.emit()
        self.table_widget.clearSelection()
        self.select_utterance(first_utt)
        self.utteranceChanged.emit(first_utt, False)
        self.updateView.emit(None, None)
        self.setFileSaveable(True)

    def merge_utterances(self):
        utts = {}
        rows = []
        for i in self.table_widget.selectedItems():
            if i.column() == 0:
                utts[i.row()] = i.text()
                rows.append(i.row())
        if len(rows) < 2:
            return
        row = None
        for r in sorted(rows):
            if row is not None:
                if r - row != 1:
                    return
            row = r
        min_begin = 1000000000
        max_end = 0
        text = ''
        speaker = None
        file = None
        for r, old_utt in sorted(utts.items(), key=lambda x: x[0]):
            if old_utt in self.corpus.segments:
                seg = self.corpus.segments[old_utt]
                if speaker is None:
                    speaker = self.corpus.utt_speak_mapping[old_utt]
                    file = self.corpus.utt_file_mapping[old_utt]
                filename = seg['file_name']
                beg = seg['begin']
                end = seg['end']
                channel = seg['channel']
                if beg < min_begin:
                    min_begin = beg
                if end > max_end:
                    max_end = end
                utt_text = self.corpus.text_mapping[old_utt]
                if utt_text == 'speech' and text.strip() == 'speech':
                    continue
                text += utt_text + ' '
            else:
                return
        text = text[:-1]
        new_utt = '{}-{}-{}-{}'.format(speaker, filename, min_begin, max_end).replace('.', '-')
        new_seg = {'file_name': filename, 'begin': min_begin, 'end': max_end, 'channel': channel}
        self.corpus.add_utterance(new_utt, speaker, file, text, seg=new_seg)

        for r, old_utt in sorted(utts.items(), key=lambda x: x[0]):
            self.corpus.delete_utterance(old_utt)
        self.refresh_list()
        self.table_widget.clearSelection()
        self.utteranceMerged.emit()
        self.select_utterance(new_utt)
        self.utteranceChanged.emit(new_utt, False)
        self.setFileSaveable(True)

    def create_utterance(self, speaker, begin, end, channel):
        begin = round(begin, 4)
        end = round(end, 4)
        text = ''
        file = self.current_file
        new_utt = '{}-{}-{}-{}'.format(speaker, file, begin, end).replace('.', '-')
        new_seg = {'file_name': file, 'begin': begin, 'end': end, 'channel': channel}
        self.corpus.add_utterance(new_utt, speaker, file, text, seg=new_seg)
        self.refresh_list()
        self.table_widget.clearSelection()
        self.utteranceMerged.emit()
        self.select_utterance(new_utt)
        self.utteranceChanged.emit(new_utt, False)
        self.setFileSaveable(True)

    def select_utterance(self, utt, zoom=False):
        self.table_widget.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        if utt is None:
            self.table_widget.clearSelection()
        else:
            for r in range(self.table_widget.rowCount()):
                if self.table_widget.item(r, self.utterance_id_column_index).text() == utt:
                    self.table_widget.selectRow(r)
                    break
        self.table_widget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        cur = self.get_current_selection()
        if not cur:
            return
        if zoom:
            if self.corpus.segments:
                min_time = 100000
                max_time = 0
                for u in cur:
                    beg = self.corpus.segments[u]['begin']
                    end = self.corpus.segments[u]['end']
                    if beg < min_time:
                        min_time = beg
                    if end > max_time:
                        max_time = end
                min_time -= 1
                max_time += 1
        else:
            min_time = None
            max_time = None
        self.updateView.emit(min_time, max_time)

    def refresh_corpus(self, utt=None):
        self.refresh_list()
        self.table_widget.clearSelection()
        self.select_utterance(utt)

    def update_corpus(self, corpus):
        self.corpus = corpus
        if self.corpus:
            if not self.corpus.segments:
                self.file_dropdown.clear()
                self.file_dropdown.hide()
                self.current_file = None
                self.table_widget.setColumnCount(4)
                self.table_widget.setHorizontalHeaderLabels(['', 'Utterance', 'Speaker', 'Text'])
            else:
                self.file_dropdown.show()
                self.refresh_file_dropdown()
                self.table_widget.setColumnCount(6)
                self.table_widget.setHorizontalHeaderLabels(['', 'Utterance', 'Speaker', 'Begin', 'End', 'Text'])
                self.begin_column_index = 3

            self.table_widget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
            self.table_widget.horizontalHeader().setSectionResizeMode(self.utterance_id_column_index, QtWidgets.QHeaderView.Interactive)
            self.table_widget.horizontalHeader().setSectionResizeMode(self.table_widget.horizontalHeader().count()-1, QtWidgets.QHeaderView.Interactive)
            self.table_widget.currentItemChanged.connect(self.update_utterance)
            self.table_widget.itemDoubleClicked.connect(self.update_and_zoom_utterance)
        else:
            self.file_dropdown.clear()
            self.file_dropdown.hide()
            try:
                self.table_widget.currentItemChanged.disconnect(self.update_utterance)
            except TypeError:
                pass
        self.refresh_list()

    def update_dictionary(self, dictionary):
        self.dictionary = dictionary
        self.refresh_list()

    def refresh_file_dropdown(self):
        self.file_dropdown.clear()
        for fn in sorted(self.corpus.file_utt_mapping):

            self.file_dropdown.addItem(fn)

    def refresh_list(self):
        if not self.corpus:
            self.table_widget.setRowCount(0)
            return
        sort_column = self.table_widget.horizontalHeader().sortIndicatorSection()
        sort_order = self.table_widget.horizontalHeader().sortIndicatorOrder()
        if self.corpus.segments:
            ref_index = self.begin_column_index
        else:
            ref_index = self.utterance_id_column_index
        if sort_column != ref_index:
            self.table_widget.horizontalHeader().setSortIndicator(ref_index, QtCore.Qt.SortOrder.AscendingOrder)
        self.table_widget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.table_widget.clearContents()

        if self.corpus.segments:
            file = self.file_dropdown.currentText()
            if not file:
                return
            self.table_widget.setRowCount(len(self.corpus.file_utt_mapping[file]))
            for i, u in enumerate(sorted(self.corpus.file_utt_mapping[file], key=lambda x: self.corpus.segments[x]['begin'])):
                t = self.corpus.text_mapping[u]
                self.table_widget.setItem(i, self.utterance_id_column_index, QtWidgets.QTableWidgetItem(u))
                self.table_widget.setItem(i, 2, QtWidgets.QTableWidgetItem(self.corpus.utt_speak_mapping[u]))
                if u in self.corpus.segments:
                    item = QtWidgets.QTableWidgetItem()
                    item.setData(QtCore.Qt.ItemDataRole.EditRole, self.corpus.segments[u]['begin'])
                    self.table_widget.setItem(i, 3, item)
                    item = QtWidgets.QTableWidgetItem()
                    item.setData(QtCore.Qt.ItemDataRole.EditRole, self.corpus.segments[u]['end'])
                    self.table_widget.setItem(i, 4, item)
                item = QtWidgets.QTableWidgetItem()
                item.setData(QtCore.Qt.ItemDataRole.EditRole, t)
                self.table_widget.setItem(i, 5, item)
                oov_found = False
                if self.dictionary is not None:
                    words = t.split(' ')
                    for w in words:
                        if not w:
                            continue
                        if not self.dictionary.check_word(w):
                            oov_found = True
                            break
                t = QtWidgets.QTableWidgetItem()
                if oov_found:
                    t.setCheckState(QtCore.Qt.CheckState.Checked)
                else:
                    t.setCheckState(QtCore.Qt.CheckState.Unchecked)
                self.table_widget.setItem(i, 0, t)
        else:
            self.table_widget.setRowCount(len(self.corpus.text_mapping))
            if self.corpus is not None:
                for i, (u, t) in enumerate(sorted(self.corpus.text_mapping.items())):
                    self.table_widget.setItem(i, self.utterance_id_column_index, QtWidgets.QTableWidgetItem(u))
                    self.table_widget.setItem(i, 2, QtWidgets.QTableWidgetItem(self.corpus.utt_speak_mapping[u]))
                    oov_found = False
                    if self.dictionary is not None:
                        words = t.split(' ')
                        for w in words:
                            if not self.dictionary.check_word(w):
                                oov_found = True
                                break
                    item = QtWidgets.QTableWidgetItem()
                    item.setData(QtCore.Qt.ItemDataRole.EditRole, t)
                    self.table_widget.setItem(i, 4, item)
                    t = QtWidgets.QTableWidgetItem()
                    if oov_found:
                        t.setCheckState(QtCore.Qt.CheckState.Checked)
                    else:
                        t.setCheckState(QtCore.Qt.CheckState.Unchecked)
                    self.table_widget.setItem(i, 0, t)
        self.table_widget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table_widget.horizontalHeader().setSectionResizeMode(self.utterance_id_column_index, QtWidgets.QHeaderView.Interactive)
        self.table_widget.horizontalHeader().setSectionResizeMode(self.table_widget.horizontalHeader().count()-1, QtWidgets.QHeaderView.Interactive)

        if sort_column != self.begin_column_index:
            self.table_widget.horizontalHeader().setSortIndicator(sort_column, sort_order)

class TranscriptionWidget(QtWidgets.QTextEdit):  # pragma: no cover
    def __init__(self, *args):
        super(TranscriptionWidget, self).__init__(*args)
        self.setAcceptRichText(False)
        # Default dictionary based on the current locale.
        self.dictionary = None
        self.highlighter = Highlighter(self.document())

    def setDictionary(self, dictionary):
        self.dictionary = dictionary
        self.highlighter.setDict(self.dictionary)


class SelectedUtterance(pg.LinearRegionItem):  # pragma: no cover
    dragFinished = QtCore.pyqtSignal(object)
    def mouseDragEvent(self, ev):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return

        if ev.isFinish():
            pos = ev.pos()
            self.dragFinished.emit(pos)
            return

        ev.accept()


def construct_text_region(utt, view_min, view_max, point_min, point_max, sr, speaker_ind,
                          selected_range_color='blue', selected_line_color='g',
                          break_line_color=1.0, text_color=1.0, interval_background_color=0.25,
                          plot_text_font=None, plot_text_width=400):  # pragma: no cover
    y_range = point_max - point_min
    b_s = utt['begin'] * sr
    e_s = utt['end'] * sr
    if not isinstance(selected_range_color, QtGui.QColor):
        selected_range_color = QtGui.QColor(selected_range_color)
    if not isinstance(interval_background_color, QtGui.QColor):
        interval_background_color = QtGui.QColor(interval_background_color)
    selected_range_color.setAlpha(75)
    #interval_background_color.setAlpha(90)
    reg_brush = pg.mkBrush(selected_range_color)

    reg = SelectedUtterance([b_s, e_s], pen=pg.mkPen(selected_line_color, width=3), brush=reg_brush)
    reg.setZValue(-10)
    reg.movable = False
    mid_b = utt['begin']
    mid_e = utt['end']
    speaker_tier_range = (y_range / 2)
    b_s_for_text = b_s
    e_s_for_text = e_s

    if view_min > mid_b and mid_e - view_min > 1:
        b_s_for_text = view_min * sr
    if view_max < mid_e and view_max - mid_b > 1:
        e_s_for_text = view_max * sr
    text_dur = e_s_for_text - b_s_for_text
    mid_point = b_s_for_text + (text_dur * 0.5)  # * self.sr
    t = pg.TextItem(utt['text'], anchor=(0.5, 0.5), color=text_color)
    top_point = point_min - speaker_tier_range * (speaker_ind - 1)
    y_mid_point = top_point - (speaker_tier_range / 2)
    t.setPos(mid_point, y_mid_point)
    t.setFont(plot_text_font)
    if t.textItem.boundingRect().width() > plot_text_width:
        t.setTextWidth(plot_text_width)
    pen = pg.mkPen(break_line_color, width=3)
    pen.setCapStyle(QtCore.Qt.FlatCap)
    begin_line = pg.PlotCurveItem([b_s, b_s], [top_point, top_point - speaker_tier_range],
                                  pen=pg.mkPen(pen))
    end_line = pg.PlotCurveItem([e_s, e_s], [top_point, top_point - speaker_tier_range],
                                pen=pg.mkPen(pen))
    begin_line.setClickable(False)
    end_line.setClickable(False)
    fill_brush = pg.mkBrush(interval_background_color)
    fill_between = pg.FillBetweenItem(begin_line, end_line, brush=fill_brush)

    return t, reg, fill_between


def construct_text_box(utt, view_min, view_max, point_min, point_max, sr, speaker_ind,
                       break_line_color=1.0, text_color=1.0, interval_background_color=0.25,
                       plot_text_font=None, plot_text_width=400):  # pragma: no cover
    y_range = point_max - point_min
    b_s = utt['begin'] * sr
    e_s = utt['end'] * sr
    pen = pg.mkPen(break_line_color, width=3)
    pen.setCapStyle(QtCore.Qt.FlatCap)
    mid_b = utt['begin']
    mid_e = utt['end']
    speaker_tier_range = (y_range / 2)
    b_s_for_text = b_s
    e_s_for_text = e_s
    if view_min > mid_b and mid_e - view_min > 1:
        b_s_for_text = view_min * sr
    if view_max < mid_e and view_max - mid_b > 1:
        e_s_for_text = view_max * sr
    text_dur = e_s_for_text - b_s_for_text
    mid_point = b_s_for_text + (text_dur * 0.5)  # * self.sr
    t = pg.TextItem(utt['text'], anchor=(0.5, 0.5), color=text_color)
    top_point = point_min - speaker_tier_range * (speaker_ind - 1)
    y_mid_point = top_point - (speaker_tier_range / 2)
    t.setPos(mid_point, y_mid_point)
    t.setFont(plot_text_font)
    if t.textItem.boundingRect().width() > plot_text_width:
        t.setTextWidth(plot_text_width)
    begin_line = pg.PlotCurveItem([b_s, b_s], [top_point, top_point - speaker_tier_range],
                                  pen=pg.mkPen(pen))
    end_line = pg.PlotCurveItem([e_s, e_s], [top_point, top_point - speaker_tier_range],
                                pen=pg.mkPen(pen))
    begin_line.setClickable(False)
    end_line.setClickable(False)
    fill_brush = pg.mkBrush(interval_background_color)
    fill_between = pg.FillBetweenItem(begin_line, end_line, brush=fill_brush)
    fill_between.setZValue(-5)
    return t, begin_line, end_line, fill_between

class Highlighter(QtGui.QSyntaxHighlighter):

    WORDS = r'\S+'

    def __init__(self, *args):
        super(Highlighter, self).__init__(*args)

        self.dict = None
        self.search_term = None
        self.spellcheck_format = QtGui.QTextCharFormat()
        self.underline_color = '#ffd60a'
        self.spellcheck_format.setUnderlineColor(QtCore.Qt.red)
        self.spellcheck_format.setUnderlineStyle(QtGui.QTextCharFormat.SpellCheckUnderline)
        self.keyword_color = '#ffd60a'
        self.keyword_text_color = '#000000'

    def update_config(self, config):
        color_config = config.color_options
        font_config = config.font_options
        self.keyword_color = color_config['keyword_color']
        self.keyword_text_color = color_config['keyword_text_color']
        self.underline_color =  color_config['underline_color']
        self.spellcheck_format.setFontWeight(font_config['big_font'].weight())
        self.spellcheck_format.setUnderlineColor(QtGui.QColor(self.underline_color))

    def setDict(self, dict):
        self.dict = dict

    def setSearchTerm(self, search_term):
        self.search_term = search_term
        self.rehighlight()

    def highlightBlock(self, text):
        if self.dict:
            for word_object in re.finditer(self.WORDS, text):
                if not self.dict.check_word(word_object.group()):
                    self.setFormat(word_object.start(),
                        word_object.end() - word_object.start(), self.spellcheck_format)
        if self.search_term:
            for word_object in re.finditer(self.search_term, text):
                for i in range(word_object.start(), word_object.end()):
                    f = self.format(i)
                    f.setBackground(QtGui.QColor(self.keyword_color))
                    f.setForeground(QtGui.QColor(self.keyword_text_color))
                    self.setFormat(i, 1, f)


class UtteranceDetailWidget(QtWidgets.QWidget):  # pragma: no cover
    lookUpWord = QtCore.pyqtSignal(object)
    createWord = QtCore.pyqtSignal(object)
    saveUtterance = QtCore.pyqtSignal(object, object)
    selectUtterance = QtCore.pyqtSignal(object, object)
    createUtterance = QtCore.pyqtSignal(object, object, object, object)
    refreshCorpus = QtCore.pyqtSignal(object)
    utteranceUpdated = QtCore.pyqtSignal(object)
    utteranceChanged = QtCore.pyqtSignal(object)
    audioPlaying = QtCore.pyqtSignal(object)

    def __init__(self, parent):
        super(UtteranceDetailWidget, self).__init__(parent=parent)
        self.corpus = None
        self.utterance = None
        self.audio = None
        self.sr = None
        self.current_time = 0
        self.min_time = 0
        self.max_time = None
        self.selected_min = None
        self.selected_max = None
        self.background_color = '#000000'
        self.m_audioOutput = MediaPlayer()
        # self.m_audioOutput.error.connect(self.showError)
        self.m_audioOutput.timeChanged.connect(self.notified)
        self.m_audioOutput.stateChanged.connect(self.handleAudioState)
        # self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self.ax = pg.PlotWidget()
        # self.ax.setFocusPolicy(QtCore.Qt.NoFocus)
        self.line = pg.InfiniteLine(
            pos=-20,
            pen=pg.mkPen('r', width=1),
            movable=False  # We have our own code to handle dragless moving.
        )
        self.ax.getPlotItem().hideAxis('left')
        self.ax.getPlotItem().setMouseEnabled(False, False)
        # self.ax.getPlotItem().setFocusPolicy(QtCore.Qt.NoFocus)
        self.ax.addItem(self.line)
        self.ax.getPlotItem().setMenuEnabled(False)
        self.ax.scene().sigMouseClicked.connect(self.update_current_time)
        layout = QtWidgets.QVBoxLayout()
        self.scroll_bar_wrapper = QtWidgets.QHBoxLayout()
        self.pan_left_button = QtWidgets.QToolButton()
        self.pan_left_button.setObjectName('pan_left_button')
        self.pan_right_button = QtWidgets.QToolButton()
        self.pan_right_button.setObjectName('pan_right_button')
        self.scroll_bar_wrapper.addWidget(self.pan_left_button)

        self.scroll_bar = QtWidgets.QScrollBar(QtCore.Qt.Orientation.Horizontal)
        self.scroll_bar.setObjectName('time_scroll_bar')

        #self.scroll_bar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.scroll_bar.valueChanged.connect(self.update_from_slider)
        scroll_bar_layout = QtWidgets.QVBoxLayout()
        scroll_bar_layout.addWidget(self.scroll_bar, 1)
        self.scroll_bar_wrapper.addLayout(scroll_bar_layout)
        self.scroll_bar_wrapper.addWidget(self.pan_right_button)


        self.tool_bar_wrapper = QtWidgets.QVBoxLayout()
        self.tool_bar = QtWidgets.QToolBar()
        self.tool_bar_wrapper.addWidget(self.tool_bar, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        self.text_widget = TranscriptionWidget()
        self.text_widget.setMaximumHeight(100)
        self.text_widget.textChanged.connect(self.update_utterance_text)
        self.text_widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)

        self.text_widget.customContextMenuRequested.connect(self.generate_context_menu)
        text_layout = QtWidgets.QHBoxLayout()
        text_layout.addWidget(self.text_widget)

        layout.addWidget(self.ax)
        layout.addLayout(self.scroll_bar_wrapper)
        layout.addLayout(self.tool_bar_wrapper)
        layout.addLayout(text_layout)
        self.setLayout(layout)
        self.wav_path = None
        self.channels = 1
        self.wave_data = None
        self.long_file = None
        self.show_all_speakers = False
        self.sr = None
        self.file_utts = []
        self.selected_utterance = None
        self.previous_volume = 100

    def update_show_speakers(self, state):
        self.show_all_speakers = state > 0
        self.update_plot(self.min_time, self.max_time)

    def update_mute_status(self, is_muted):
        self.m_audioOutput.setMuted(is_muted)
        main_window = self.sender().parent()
        if is_muted:
            self.previous_volume = self.m_audioOutput.volume()
            main_window.change_volume_act.widget.setValue(0)
        else:
            main_window.change_volume_act.widget.setValue(self.previous_volume)

    def update_config(self, config):
        color_config = config.plot_color_options
        self.background_color = color_config['background_color']
        self.axis_color = color_config['axis_color']
        self.play_line_color = color_config['play_line_color']
        self.selected_range_color = color_config['selected_range_color']
        self.selected_interval_color = color_config['selected_interval_color']
        self.selected_line_color = color_config['selected_line_color']
        self.break_line_color = color_config['break_line_color']
        self.text_color = color_config['text_color']
        self.wave_line_color = color_config['wave_line_color']
        self.interval_background_color = color_config['interval_background_color']

        self.plot_text_width = config['plot_text_width']

        font_config = config.font_options

        self.plot_text_font = font_config['font']

        self.axis_text_font = font_config['axis_font']

        self.edit_text_font = font_config['big_font']
        self.text_widget.setFont(self.edit_text_font)

        self.tool_bar.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding,QtWidgets.QSizePolicy.MinimumExpanding)

        self.tool_bar.setFont(font_config['big_font'])
        s = self.tool_bar.size()
        icon_ratio = 0.03
        icon_height = int(icon_ratio*config['height'])
        if icon_height < 24:
            icon_height = 24
        self.tool_bar.setIconSize(QtCore.QSize(icon_height, icon_height))
        icon_height = 25
        self.pan_left_button.setIconSize(QtCore.QSize(icon_height, icon_height))
        self.pan_right_button.setIconSize(QtCore.QSize(icon_height, icon_height))


        self.form_font = font_config['form_font']


        self.update_plot(self.min_time, self.max_time)

        self.text_widget.highlighter.update_config(config)

    def update_from_slider(self, value):
        if self.max_time is None:
            return
        cur_window = self.max_time - self.min_time
        self.update_plot(value, value + cur_window)

    def update_utterance_text(self):
        if self.utterance is None:
            return
        new_text = self.text_widget.toPlainText().strip().lower()
        if new_text != self.corpus.text_mapping[self.utterance]:
            self.utteranceChanged.emit(True)

            self.corpus.text_mapping[self.utterance] = new_text

        for u in self.file_utts:
            if u['utt'] == self.utterance:
                u['text'] = new_text
                break
        self.update_plot(self.min_time, self.max_time)
        self.utteranceUpdated.emit(self.utterance)

    def update_plot_scale(self):
        self.p2.setGeometry(self.p1.vb.sceneBoundingRect())

    def reset(self):
        self.utterance = None
        self.file_name = None
        self.wave_data = None
        self.wav_path = None
        try:
            self.scroll_bar.valueChanged.disconnect(self.update_from_slider)
        except TypeError:
            pass
        self.ax.getPlotItem().clear()
        self.reset_text()

    def update_corpus(self, corpus):
        self.wave_data = None
        self.corpus = corpus
        if corpus is None:
            self.reset()
        if self.utterance:
            self.reset_text()

    def update_dictionary(self, dictionary):
        self.text_widget.setDictionary(dictionary)

    def generate_context_menu(self, location):

        menu = self.text_widget.createStandardContextMenu()
        cursor = self.text_widget.cursorForPosition(location)
        cursor.select(QtGui.QTextCursor.WordUnderCursor)
        word = cursor.selectedText()
        # add extra items to the menu
        lookUpAction = QtWidgets.QAction("Look up '{}' in dictionary".format(word), self)
        createAction = QtWidgets.QAction("Add pronunciation for '{}'".format(word), self)
        lookUpAction.triggered.connect(lambda: self.lookUpWord.emit(word))
        createAction.triggered.connect(lambda: self.createWord.emit(word))
        menu.addAction(lookUpAction)
        menu.addAction(createAction)
        # show the menu
        menu.exec_(self.text_widget.mapToGlobal(location))

    def update_current_time(self, ev):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        point = self.ax.getPlotItem().vb.mapSceneToView(ev.scenePos())
        x = point.x()
        y = point.y()
        y_range = self.max_point - self.min_point
        speaker_tier_range = (y_range / 2)
        move_line = False
        time = x / self.sr
        if y < self.min_point:
            speaker = None
            for k, s_id in self.speaker_mapping.items():
                top_pos = self.min_point - speaker_tier_range * (s_id - 1)
                bottom_pos = top_pos - speaker_tier_range
                if bottom_pos < y < top_pos:
                    speaker = k
                    break
            utt = None
            for u in self.file_utts:
                if u['end'] < time:
                    continue
                if u['begin'] > time:
                    break
                if u['speaker'] != speaker:
                    continue
                utt = u
            if utt is not None:
                zoom = ev.double()
                if modifiers == QtCore.Qt.ControlModifier and utt is not None:
                    self.selectUtterance.emit(utt['utt'], zoom)
                else:
                    if utt['utt'] != self.utterance or zoom:
                        self.selectUtterance.emit(None, zoom)
                        self.selectUtterance.emit(utt['utt'], zoom)
                        self.update_utterance(utt['utt'], zoom)
                self.m_audioOutput.setMaxTime(self.selected_max)
                self.m_audioOutput.setCurrentTime(self.selected_min)
            elif ev.double():
                beg = time - 0.5
                end = time + 0.5
                channel = 0
                if self.channels > 1:
                    ind = self.corpus.speaker_ordering[self.file_name].index(speaker)
                    if ind >= len(self.corpus.speaker_ordering[self.file_name]) / 2:
                        channel = 1
                self.createUtterance.emit(speaker, beg, end, channel)
                return
            else:
                move_line = True
        elif ev.double():
            beg = time - 0.5
            end = time + 0.5
            channel = 0
            if self.channels > 1:
                if y < 2:
                    channel = 1
                if self.file_name not in self.corpus.speaker_ordering:
                    self.corpus.speaker_ordering[self.file_name] = ['speech']
                if channel == 0:
                    ind = 0
                else:
                    ind = int(round(len(self.corpus.speaker_ordering[self.file_name]) / 2))
                speaker = self.corpus.speaker_ordering[self.file_name][ind]
                self.createUtterance.emit(speaker, beg, end, channel)
                return

        else:
            move_line = True
        if move_line:
            self.current_time = x / self.sr
            if self.current_time < self.min_time:
                self.current_time = self.min_time
                x = self.current_time * self.sr
            if self.current_time > self.max_time:
                self.current_time = self.max_time
                x = self.current_time * self.sr

            self.line.setPos(x)
            self.m_audioOutput.setStartTime(self.current_time)
            self.m_audioOutput.setCurrentTime(self.current_time)
            self.m_audioOutput.setMaxTime(self.max_time)

    def refresh_view(self):
        self.refresh_utterances()
        self.update_plot(self.min_time, self.max_time)

    def refresh_utterances(self):
        self.file_utts = []
        if not self.file_name:
            return
        self.wav_path = self.corpus.utt_wav_mapping[self.file_name]
        self.wav_info = get_wav_info(self.wav_path)
        self.scroll_bar.setMaximum(self.wav_info['duration'])
        if self.file_name in self.corpus.file_utt_mapping:
            for u in self.corpus.file_utt_mapping[self.file_name]:
                begin = self.corpus.segments[u]['begin']
                end = self.corpus.segments[u]['end']
                self.file_utts.append({'utt': u, 'begin': begin,
                                       'end': end, 'text': self.corpus.text_mapping[u],
                                       'speaker': self.corpus.utt_speak_mapping[u]})
        else:
            u = self.file_name
            self.file_utts.append({'utt': u, 'begin': 0,
                                   'end': self.wav_info['duration'], 'text': self.corpus.text_mapping[u],
                                   'speaker': self.corpus.utt_speak_mapping[u]})
        self.file_utts.sort(key=lambda x: x['begin'])

    def update_file_name(self, file_name):
        if not self.corpus:
            self.file_name = None
            self.wave_data = None
            return
        if file_name == self.file_name:
            return
        self.file_name = file_name
        if file_name in self.corpus.utt_speak_mapping:
            self.long_file = False
        else:
            self.long_file = True
        if self.wav_path != self.corpus.utt_wav_mapping[file_name]:
            self.refresh_utterances()
        self.wav_path = self.corpus.utt_wav_mapping[file_name]
        try:
            self.scroll_bar.valueChanged.disconnect(self.update_from_slider)
        except TypeError:
            pass
        self.scroll_bar.valueChanged.connect(self.update_from_slider)
        self.channels = self.wav_info['num_channels']
        end = min(10, self.wav_info['duration'])
        self.update_plot(0, end)
        p = QtCore.QUrl.fromLocalFile(self.wav_path)
        self.m_audioOutput.setMedia(QtMultimedia.QMediaContent(p))
        self.updatePlayTime(0)
        self.m_audioOutput.setMinTime(0)
        self.m_audioOutput.setStartTime(0)
        self.m_audioOutput.setMaxTime(end)
        self.m_audioOutput.setCurrentTime(0)

    def update_utterance(self, utterance, zoom=False):
        if utterance is None:
            return
        self.utterance = utterance
        self.reset_text()
        if self.utterance in self.corpus.segments:
            segment = self.corpus.segments[self.utterance]
            file_name = segment['file_name']
            begin = segment['begin']
            end = segment['end']
            begin = float(begin)
            end = float(end)
            self.update_file_name(file_name)
            self.selected_min = begin
            self.selected_max = end
            # if self.max_time is not None and self.min_time is not None:
            #    if self.min_time + 1 <= end <= self.max_time - 1:
            #        return
            #    if self.min_time + 1 <= begin <= self.max_time - 1:
            #        return
            self.long_file = True
            begin -= 1
            end += 1
        else:
            self.update_file_name(self.utterance)
            self.long_file = False
            self.wave_data = None
            begin = 0
            end = self.wav_info['duration']
        if not zoom:
            begin, end = None, None
        self.update_plot(begin, end)
        if self.long_file:
            self.m_audioOutput.setMaxTime(self.selected_max)
        self.updatePlayTime(self.selected_min)
        self.m_audioOutput.setStartTime(self.selected_min)
        self.m_audioOutput.setCurrentTime(self.selected_min)
        self.m_audioOutput.setMaxTime(self.selected_max)

    def update_selected_times(self, region):
        self.selected_min, self.selected_max = region.getRegion()
        self.selected_min /= self.sr
        self.selected_max /= self.sr
        self.updatePlayTime(self.selected_min)
        self.m_audioOutput.setStartTime(self.selected_min)
        self.m_audioOutput.setCurrentTime(self.selected_min)
        self.m_audioOutput.setMaxTime(self.selected_max)

    def update_selected_speaker(self, pos):
        pos = pos.y()
        if pos > self.min_point:
            return
        y_range = self.max_point - self.min_point
        speaker_tier_range = (y_range / 2)
        new_speaker = None
        for k, s_id in self.speaker_mapping.items():
            top_pos = self.min_point - speaker_tier_range * (s_id - 1)
            bottom_pos = top_pos - speaker_tier_range
            if top_pos > pos > bottom_pos:
                new_speaker = k
        if new_speaker != self.selected_utterance['speaker']:
            self.updateSpeaker.emit(self.utterance, new_speaker)

    def update_plot(self, begin, end):
        self.ax.getPlotItem().clear()
        self.ax.getPlotItem().getAxis('bottom').setPen(self.axis_color)
        self.ax.getPlotItem().getAxis('bottom').setTextPen(self.axis_color)
        self.ax.getPlotItem().getAxis('bottom').setTickFont(self.axis_text_font)
        self.ax.setBackground(self.background_color)
        if self.corpus is None:
            return
        if self.wav_path is None:
            return
        from functools import partial
        if begin is None and end is None:
            begin = self.min_time
            end = self.max_time
        if end is None:
            return
        if end <= 0:
            end = self.max_time
        if begin < 0:
            begin = 0
        if self.long_file:
            duration = end - begin
            self.wave_data, self.sr = librosa.load(self.wav_path, offset=begin, duration=duration + 2, sr=None, mono=False)

        elif self.wave_data is None:
            self.wave_data, self.sr = librosa.load(self.wav_path, sr=None)
            # Normalize y1 between 0 and 2
            self.wave_data /= np.max(np.abs(self.wave_data), axis=0)  # between -1 and 1
            self.wave_data += 1  # shift to 0 and 2
        #self.m_audioOutput.setData(self.wave_data, self.sr)
        begin_samp = int(begin * self.sr)
        end_samp = int(end * self.sr)
        window_size = end - begin
        try:
            self.scroll_bar.valueChanged.disconnect(self.update_from_slider)
        except TypeError:
            pass
        self.scroll_bar.setValue(begin)
        self.scroll_bar.setPageStep(window_size)
        self.scroll_bar.setMaximum(self.wav_info['duration'] - window_size)
        self.scroll_bar.valueChanged.connect(self.update_from_slider)
        self.min_time = begin
        self.max_time = end
        self.ax.addItem(self.line)
        self.updatePlayTime(self.min_time)
        wave_pen = pg.mkPen(self.wave_line_color, width=1)
        if len(self.wave_data.shape) > 1 and self.wave_data.shape[0] == 2:
            if not self.long_file:
                y0 = self.wave_data[0, begin_samp:end_samp]
                y1 = self.wave_data[1, begin_samp:end_samp]
                x = np.arange(start=begin_samp, stop=end_samp)
            else:
                y0 = self.wave_data[0, :]
                y1 = self.wave_data[1, :]
                x = np.arange(start=begin_samp, stop=begin_samp + y0.shape[0])

            # Normalize y0 between 2 and 4
            y0 /= np.max(np.abs(y0), axis=0)  # between -1 and 1
            y0[np.isnan(y0)] = 0
            y0 += 3  # shift to 2 and 4
            # Normalize y1 between 0 and 2
            y1 /= np.max(np.abs(y1), axis=0)  # between -1 and 1
            y1[np.isnan(y1)] = 0
            y1 += 1  # shift to 0 and 2
            pen = pg.mkPen(self.break_line_color, width=1)
            pen.setStyle(QtCore.Qt.DotLine)
            sub_break_line = pg.InfiniteLine(
                pos=2,
                angle=0,
                pen=pen,
                movable=False  # We have our own code to handle dragless moving.
            )
            self.ax.addItem(sub_break_line)

            self.ax.plot(x, y0, pen=wave_pen)
            self.ax.plot(x, y1, pen=wave_pen)
            self.min_point = 0
            self.max_point = 4

        else:
            if not self.long_file:
                y = self.wave_data[begin_samp:end_samp]
                x = np.arange(start=begin_samp, stop=begin_samp + y.shape[0])
            else:
                y = self.wave_data
                y /= np.max(np.abs(y), axis=0)  # between -1 and 1
                y += 1  # shift to 0 and 2
                x = np.arange(start=begin_samp, stop=begin_samp + y.shape[0])
            self.min_point = 0
            self.max_point = 2
            self.ax.plot(x, y, pen=wave_pen)

        if self.file_name in self.corpus.speaker_ordering:
            break_line = pg.InfiniteLine(
                pos=self.min_point,
                angle=0,
                pen=pg.mkPen(self.break_line_color, width=2),
                movable=False  # We have our own code to handle dragless moving.
            )
            self.ax.addItem(break_line)

            y_range = self.max_point - self.min_point
            speaker_tier_range = (y_range / 2)
            speaker_ind = 1
            self.speaker_mapping = {}
            # Figure out speaker mapping first
            speakers = set()
            if not self.show_all_speakers:
                for u in self.file_utts:
                    if u['end'] - self.min_time <= 0:
                        continue
                    if self.max_time - u['begin'] <= 0:
                        break
                    speakers.add(u['speaker'])
            for sp in self.corpus.speaker_ordering[self.file_name]:
                if not self.show_all_speakers and sp not in speakers:
                    continue
                if sp not in self.speaker_mapping:
                    self.speaker_mapping[sp] = speaker_ind
                    speaker_ind += 1

            for u in self.file_utts:
                if u['end'] - self.min_time <= 0:
                    continue
                if self.max_time - u['begin'] <= 0:
                    break
                s_id = self.speaker_mapping[u['speaker']]
                if u['utt'] == self.utterance:
                    self.selected_utterance = u
                    t, reg, fill = construct_text_region(u, self.min_time, self.max_time, self.min_point, self.max_point,
                                                         self.sr, s_id, selected_range_color=self.selected_range_color,
                                                         selected_line_color=self.selected_line_color,
                                                         break_line_color=self.break_line_color,
                                                         text_color=self.text_color, plot_text_font=self.plot_text_font,
                                                         interval_background_color=self.selected_interval_color,
                                                         plot_text_width=self.plot_text_width)

                    self.ax.addItem(fill)
                    self.ax.addItem(reg)
                    func = partial(self.update_utt_times, u)
                    reg.sigRegionChangeFinished.connect(func)
                    reg.sigRegionChangeFinished.connect(self.update_selected_times)
                    reg.dragFinished.connect(self.update_selected_speaker)
                else:
                    t, bl, el, fill = construct_text_box(u, self.min_time, self.max_time, self.min_point, self.max_point,
                                                         self.sr, s_id, break_line_color=self.break_line_color,
                                                         text_color=self.text_color, plot_text_font=self.plot_text_font,
                                                         interval_background_color=self.interval_background_color,
                                                         plot_text_width=self.plot_text_width)
                    self.ax.addItem(bl)
                    self.ax.addItem(el)
                    self.ax.addItem(fill)
                if u['end'] - self.min_time <= 1:
                    continue
                if self.max_time < u['begin'] <= 1:
                    continue
                self.ax.addItem(t)
            num_speakers = speaker_ind - 1
            min_y = self.min_point - speaker_tier_range * num_speakers
            self.ax.setYRange(min_y, self.max_point)
            for k, s_id in self.speaker_mapping.items():
                t = pg.TextItem(k, anchor=(0, 0), color=self.text_color)
                t.setFont(self.plot_text_font)
                top_pos = self.min_point - speaker_tier_range * (s_id - 1)
                bottom_pos = top_pos - speaker_tier_range
                mid_pos = ((top_pos - bottom_pos) / 2) + bottom_pos
                t.setPos(begin_samp, top_pos)
                self.ax.addItem(t)
                break_line = pg.InfiniteLine(
                    pos=bottom_pos,
                    angle=0,
                    pen=pg.mkPen(self.break_line_color, width=1),
                    movable=False  # We have our own code to handle dragless moving.
                )
                self.ax.addItem(break_line)
        else:
            self.ax.setYRange(self.min_point, self.max_point)
        self.ax.setXRange(begin_samp, end_samp)
        self.ax.getPlotItem().getAxis('bottom').setScale(1 / self.sr)
        self.m_audioOutput.setMinTime(self.min_time)
        self.m_audioOutput.setMaxTime(self.max_time)

    def set_search_term(self, term):
        self.text_widget.highlighter.setSearchTerm(term)

    def update_utt_times(self, utt, x):
        beg, end = x.getRegion()
        new_begin = round(beg / self.sr, 4)
        new_end = round(end / self.sr, 4)
        if new_end - new_begin > 100:
            x.setRegion((utt['begin'] * self.sr, utt['end'] * self.sr))
            return
        utt['begin'] = new_begin
        utt['end'] = new_end
        x.setSpan(int(new_begin * self.sr), int(new_end * self.sr))
        old_utt = utt['utt']
        speaker = self.corpus.utt_speak_mapping[old_utt]
        file = self.corpus.utt_file_mapping[old_utt]
        text = self.corpus.text_mapping[old_utt]
        if old_utt in self.corpus.segments:
            seg = self.corpus.segments[old_utt]
            filename = seg['file_name']
            new_utt = '{}-{}-{}-{}'.format(speaker, filename, utt['begin'], utt['end']).replace('.', '-')
            new_seg = {'file_name': filename, 'begin': utt['begin'], 'end': utt['end'], 'channel': seg['channel']}
            utt['utt'] = new_utt
        else:
            new_seg = None
        self.corpus.delete_utterance(old_utt)
        self.corpus.add_utterance(new_utt, speaker, file, text, seg=new_seg)
        self.utterance = new_utt
        self.update_plot(self.min_time, self.max_time)
        self.refreshCorpus.emit(new_utt)

    def reset_text(self):
        if not self.corpus or self.utterance not in self.corpus.text_mapping:
            self.utterance = None
            self.audio = None
            self.sr = None
            self.text_widget.setText('')
            return
        text = self.corpus.text_mapping[self.utterance]
        self.text_widget.setText(text)

    def showError(self, e):
        reply = DetailedMessageBox()
        reply.setDetailedText(str(e))
        ret = reply.exec_()

    def play_audio(self):
        if self.m_audioOutput.state() in [QtMultimedia.QMediaPlayer.StoppedState,
                                          QtMultimedia.QMediaPlayer.PausedState]:
            self.m_audioOutput.play()
        elif self.m_audioOutput.state() == QtMultimedia.QMediaPlayer.PlayingState:
            self.m_audioOutput.pause()

    def zoom_in(self):
        shift = round((self.max_time - self.min_time) * 0.25, 3)
        cur_duration = self.max_time - self.min_time
        if cur_duration < 2:
            return
        if cur_duration - 2 * shift < 1:
            shift = (cur_duration - 1) / 2
        self.min_time += shift
        self.max_time -= shift
        cur_time = self.m_audioOutput.currentTime()
        self.update_plot(self.min_time, self.max_time)
        self.m_audioOutput.setStartTime(cur_time)
        self.m_audioOutput.setCurrentTime(cur_time)
        self.updatePlayTime(cur_time)

    def zoom_out(self):
        shift = round((self.max_time - self.min_time) * 0.25, 3)
        cur_duration = self.max_time - self.min_time
        if cur_duration + 2 * shift > 20:
            shift = (20 - cur_duration) / 2
        self.min_time -= shift
        self.max_time += shift
        if self.max_time > self.wav_info['duration']:
            self.max_time = self.wav_info['duration']
        if self.min_time < 0:
            self.min_time = 0
        cur_time = self.m_audioOutput.currentTime()
        self.update_plot(self.min_time, self.max_time)
        self.m_audioOutput.setStartTime(cur_time)
        self.m_audioOutput.setCurrentTime(cur_time)
        self.updatePlayTime(cur_time)

    def pan_left(self):
        self.scroll_bar.triggerAction(self.scroll_bar.SliderAction.SliderSingleStepSub)

    def pan_right(self):
        self.scroll_bar.triggerAction(self.scroll_bar.SliderAction.SliderSingleStepAdd)

    def updatePlayTime(self, time):
        if not time:
            return
        #if self.max_time and time > self.max_time:
        #    return
        if self.sr:
            pos = int(time * self.sr)
            self.line.setPos(pos)

    def notified(self, current_time):
        if self.m_audioOutput.min_time is None:
            return
        self.updatePlayTime(current_time)

    def handleAudioState(self, state):
        if state == QtMultimedia.QMediaPlayer.StoppedState:
            self.m_audioOutput.setPosition(self.m_audioOutput.start_time)
            self.updatePlayTime(self.m_audioOutput.currentTime())
            self.audioPlaying.emit(False)

class SearchField(QtWidgets.QLineEdit):
    searchActivated = QtCore.pyqtSignal(object)
    @property
    def _internal_layout(self):
        if not hasattr(self, "_internal_layout_"):
            self._internal_layout_ = QtWidgets.QHBoxLayout(self)
            self._internal_layout_.addStretch()
        self._internal_layout_.setContentsMargins(1, 1,1, 1)
        self._internal_layout_.setSpacing(0)
        return self._internal_layout_

    def add_button(self, button):
        self._internal_layout.insertWidget(self._internal_layout.count(), button)
        #QtCore.QTimer.singleShot(0, partial(self._fix_cursor_position, button))
        button.setFocusProxy(self)

    def _fix_cursor_position(self, button):
        self.setTextMargins(button.geometry().right(), 0, 0, 0)

    def __init__(self, *args):
        super(SearchField, self).__init__(*args)
        self.setObjectName('search_field')
        self.returnPressed.connect(self.activate)

        clear_icon = QtGui.QIcon()
        clear_icon.addFile(':clear.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
        clear_icon.addFile(':disabled/clear.svg', mode=QtGui.QIcon.Active)
        self.clear_action = QtWidgets.QAction(icon=clear_icon, parent=self)
        self.clear_action.triggered.connect(self.clear)
        self.clear_action.triggered.connect(self.returnPressed.emit)
        self.clear_action.setVisible(False)
        self.textChanged.connect(self.check_contents)

        regex_icon = QtGui.QIcon()
        regex_icon.addFile(':regex.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
        regex_icon.addFile(':highlighted/regex.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.On)

        self.regex_action = QtWidgets.QAction(icon=regex_icon, parent=self)
        self.regex_action.setCheckable(True)
        self.regex_action.toggled.connect(self.activate)

        word_icon = QtGui.QIcon()
        word_icon.addFile(':word.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
        word_icon.addFile(':highlighted/word.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.On)
        self.word_action = QtWidgets.QAction(icon=word_icon, parent=self)
        self.word_action.setCheckable(True)
        self.word_action.toggled.connect(self.activate)

        self.tool_bar = QtWidgets.QToolBar()
        self.tool_bar.addAction(self.clear_action)
        w = self.tool_bar.widgetForAction(self.clear_action)
        w.setObjectName('clear_search_field')
        w.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.tool_bar.addAction(self.regex_action)
        w = self.tool_bar.widgetForAction(self.regex_action)
        w.setObjectName('regex_search_field')
        w.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.tool_bar.addAction(self.word_action)
        w = self.tool_bar.widgetForAction(self.word_action)
        w.setObjectName('word_search_field')
        w.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        self.add_button(self.tool_bar)

    def activate(self):
        self.searchActivated.emit(self.query())

    def setFont(self, a0: QtGui.QFont) -> None:
        super(SearchField, self).setFont(a0)
        self.regex_action.setFont(a0)
        self.word_action.setFont(a0)
        self.clear_action.setFont(a0)

    def check_contents(self):
        if self.text():
            self.clear_action.setVisible(True)
        else:
            self.clear_action.setVisible(False)

    def setQuery(self, query):
        self.setText(query[0])
        self.regex_action.toggled.disconnect(self.activate)
        self.word_action.toggled.disconnect(self.activate)
        self.regex_action.setChecked(query[1])
        self.word_action.setChecked(query[2])
        self.regex_action.toggled.connect(self.activate)
        self.word_action.toggled.connect(self.activate)
        self.activate()

    def query(self):
        text = super(SearchField, self).text().lower()
        regex_flag = self.regex_action.isChecked()
        word_flag = self.word_action.isChecked()
        return text, regex_flag, word_flag

    def text(self) -> str:
        text = super(SearchField, self).text()
        text = text.lower()
        if not text:
            return text
        if not self.regex_action.isChecked():
            text = re.escape(text)
        if self.word_action.isChecked():
            if not text.startswith(r'\b'):
                text = r'\b'+ text
            if not text.endswith(r'\b'):
                text += r'\b'
        return text

class HorizontalSpacer(QtWidgets.QWidget):
    def __init__(self, *args):
        super(HorizontalSpacer, self).__init__(*args)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)


class NoWrapDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super(NoWrapDelegate, self).__init__(parent)
        self.doc = QtGui.QTextDocument(self)

    def update_config(self, config):
        color_config = config.color_options
        font = config.font_options
        self.doc.setDefaultFont(font['font'])
        self.keyword_text_color = color_config['keyword_text_color']
        self.underline_color =  color_config['underline_color']
        self.selection_color =  color_config['selection_color']

    def sizeHint(self, option: 'QStyleOptionViewItem', index: QtCore.QModelIndex) -> QtCore.QSize:
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        self.doc.setPlainText(options.text)
        style = QtWidgets.QApplication.style() if options.widget is None \
            else options.widget.style()
        textRect = style.subElementRect(
            QtWidgets.QStyle.SE_ItemViewItemText, options)

        if index.column() != 0:
            textRect.adjust(5, 0, 0, 0)

        the_constant = 4
        margin = (option.rect.height() - options.fontMetrics.height()) // 2
        margin = margin - the_constant
        textRect.setTop(textRect.top() + margin)
        return textRect.size()


    def paint(self, painter, option, index):
        option.palette.setColor(QtGui.QPalette.Active, QtGui.QPalette.Window, QtGui.QColor(self.selection_color))
        painter.save()
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        self.doc.setPlainText(options.text)
        options.text = ""
        style = QtWidgets.QApplication.style() if options.widget is None \
            else options.widget.style()
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, options, painter)

        ctx = QtGui.QAbstractTextDocumentLayout.PaintContext()
        if option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, QtGui.QColor(self.selection_color))
            ctx.palette.setColor(QtGui.QPalette.Text, option.palette.color(
                QtGui.QPalette.Active, QtGui.QPalette.HighlightedText))
        else:
            ctx.palette.setColor(QtGui.QPalette.Text, option.palette.color(
                QtGui.QPalette.Active, QtGui.QPalette.Text))

        textRect = style.subElementRect(
            QtWidgets.QStyle.SE_ItemViewItemText, options)

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
        self._filters = []
        self.keyword_color = '#ffd60a'
        self.keyword_text_color = '#000000'
        self.current_doc_width = 100
        self.minimum_doc_size = 100
        self.margin = 5
        self.doc.setDocumentMargin(self.margin)

    def update_config(self, config):
        color_config = config.color_options
        font = config.font_options
        self.doc.setDefaultFont(font['font'])
        self.keyword_color = color_config['keyword_color']
        self.keyword_text_color = color_config['keyword_text_color']
        self.underline_color =  color_config['underline_color']
        self.selection_color =  color_config['selection_color']


    def sizeHint(self, option: 'QStyleOptionViewItem', index: QtCore.QModelIndex) -> QtCore.QSize:
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        self.doc.setPlainText(options.text)
        self.apply_highlight()
        options.text = ""
        style = QtWidgets.QApplication.style() if options.widget is None \
            else options.widget.style()
        textRect = style.subElementRect(
            QtWidgets.QStyle.SE_ItemViewItemText, options)
        textRect.setWidth(self.current_doc_width)

        if textRect.width() < self.minimum_doc_size:
            textRect.setWidth(self.minimum_doc_size)

        self.doc.setTextWidth(textRect.width())
        doc_height = self.doc.documentLayout().documentSize().height()
        textRect.setHeight(doc_height)
        return textRect.size()

    def paint(self, painter, option, index):
        option.palette.setColor(QtGui.QPalette.Active, QtGui.QPalette.Window, QtGui.QColor(self.selection_color))
        painter.save()
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        self.doc.setPlainText(options.text)
        self.apply_highlight()
        options.text = ""
        style = QtWidgets.QApplication.style() if options.widget is None \
            else options.widget.style()
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, options, painter)

        ctx = QtGui.QAbstractTextDocumentLayout.PaintContext()
        if option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, QtGui.QColor(self.selection_color))
            ctx.palette.setColor(QtGui.QPalette.Text, option.palette.color(
                QtGui.QPalette.Active, QtGui.QPalette.HighlightedText))
        else:
            ctx.palette.setColor(QtGui.QPalette.Text, option.palette.color(
                QtGui.QPalette.Active, QtGui.QPalette.Text))

        textRect = style.subElementRect(
            QtWidgets.QStyle.SE_ItemViewItemText, options)

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
        fmt.setBackground(QtGui.QColor(self.keyword_color))
        fmt.setForeground(QtGui.QColor(self.keyword_text_color))
        for f in self.filters():
            f = QtCore.QRegExp(f)
            highlightCursor = QtGui.QTextCursor(self.doc)
            while not highlightCursor.isNull() and not highlightCursor.atEnd():
                highlightCursor = self.doc.find(f, highlightCursor)
                if not highlightCursor.isNull():
                    highlightCursor.mergeCharFormat(fmt)
        cursor.endEditBlock()

    @QtCore.pyqtSlot(list)
    def setFilters(self, filters):
        if self._filters == filters: return
        self._filters = filters

    def filters(self):
        return self._filters

class OovHeaderView(QtWidgets.QHeaderView):

    def paintSection(self, painter: QtGui.QPainter, rect: QtCore.QRect, logicalIndex: int) -> None:
        if logicalIndex == 0:
            painter.save()
            super(OovHeaderView, self).paintSection(painter, rect, logicalIndex)
            painter.restore()
            painter.save()
            icon = QtGui.QIcon(':disabled/oov-check.svg')
            margin = 10
            rect_height = rect.height()-margin
            rect.translate(margin, int(margin/2))
            rect.setHeight(rect_height)
            actual_size = icon.actualSize(QtCore.QSize(rect.width(), rect.height()))
            rect.setSize(actual_size)
            icon.paint(painter, rect, QtCore.Qt.AlignmentFlag.AlignCenter)
            painter.restore()
        else:
            super(OovHeaderView, self).paintSection(painter, rect, logicalIndex)


class IconDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super(IconDelegate, self).__init__(parent)

    def update_config(self, config):
        color_config = config.color_options
        self.selection_color = color_config['selection_color']
        self.error_background_color = color_config['error_background_color']
        if self.error_background_color == '#FFFFFF':
            self.error_background_color = color_config['error_color']

    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> QtCore.QSize:
        if index.column() != 0:
            return super(IconDelegate, self).sizeHint(option, index)
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        if options.checkState == QtCore.Qt.CheckState.Checked:
            icon = QtGui.QIcon(':exclamation.svg')
            return icon.actualSize(QtCore.QSize(options.rect.width(), options.rect.height()))
        return QtCore.QSize()

    def paint(self, painter: QtGui.QPainter, option, index) -> None:
        if index.column() != 0:
            return super(IconDelegate, self).paint(painter, option, index)
        option.palette.setColor(QtGui.QPalette.Active, QtGui.QPalette.Window, QtGui.QColor(self.selection_color))
        painter.save()
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        text = index.data(QtCore.Qt.ItemDataRole.DisplayRole)

        if options.checkState == QtCore.Qt.CheckState.Checked:
            icon = QtGui.QIcon(':exclamation.svg')
            painter.fillRect(options.rect, QtGui.QColor(self.error_background_color))
            icon.paint(painter, options.rect, QtCore.Qt.AlignmentFlag.AlignCenter)
        elif option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, QtGui.QColor(self.selection_color))

        painter.restore()


class QueryDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super(QueryDelegate, self).__init__(parent)
        self.doc = QtGui.QTextDocument(self)

    def update_config(self, config):
        color_config = config.color_options
        self.selection_color =  color_config['selection_color']

    def paint(self, painter: QtGui.QPainter, option, index) -> None:
        option.palette.setColor(QtGui.QPalette.Active, QtGui.QPalette.Window, QtGui.QColor(self.selection_color))
        painter.save()
        options = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        options.decorationPosition = options.Position.Right
        icon_margin = 4
        options.decorationSize.setWidth((2 *options.decorationSize.width()) + icon_margin )

        flags = index.data(QtCore.Qt.ItemDataRole.DecorationRole)
        regex, word = False, False
        if flags:
            regex, word = flags
        self.doc.setPlainText(options.text)
        options.text = ""
        style = QtWidgets.QApplication.style() if options.widget is None \
            else options.widget.style()
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, options, painter)

        ctx = QtGui.QAbstractTextDocumentLayout.PaintContext()
        if option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, QtGui.QColor(self.selection_color))
            ctx.palette.setColor(QtGui.QPalette.Text, option.palette.color(
                QtGui.QPalette.Active, QtGui.QPalette.HighlightedText))
        else:
            ctx.palette.setColor(QtGui.QPalette.Text, option.palette.color(
                QtGui.QPalette.Active, QtGui.QPalette.Text))


        decorationRect = style.subElementRect(
            QtWidgets.QStyle.SE_ItemViewItemDecoration, options, options.widget)

        height = decorationRect.height()
        decorationRect.setWidth(height)

        offset = 0

        if regex:
            if option.state & QtWidgets.QStyle.State_Selected:
                regexImage = QtGui.QIcon(":checked/regex.svg")
            else:
                regexImage = QtGui.QIcon(":highlighted/regex.svg")
            regexImage.paint(painter, decorationRect)
        offset += height + icon_margin
        if word:
            decorationRect.translate(offset, 0)
            if option.state & QtWidgets.QStyle.State_Selected:
                wordImage = QtGui.QIcon(":checked/word.svg")
            else:
                wordImage = QtGui.QIcon(":highlighted/word.svg")
            wordImage.paint(painter, decorationRect, options.decorationAlignment)

        textRect = style.subElementRect(
            QtWidgets.QStyle.SE_ItemViewItemText, options)

        the_constant = 4
        margin = (option.rect.height() - options.fontMetrics.height()) // 2
        margin = margin - the_constant
        textRect.setTop(textRect.top() + margin)

        painter.translate(textRect.topLeft())
        painter.setClipRect(textRect.translated(-textRect.topLeft()))
        self.doc.documentLayout().draw(painter, ctx)

        painter.restore()


class HistoryDropDown(QtWidgets.QComboBox):
    newQuery = QtCore.pyqtSignal(object)
    def __init__(self, *args):
        super(HistoryDropDown, self).__init__(*args)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setEditable(False)
        self.history = ['Search history...']
        self.current_query = None
        self.addItem(self.history[0])
        self.setCurrentIndex(0)
        self.query_delegate = QueryDelegate(self)
        self.setItemDelegate(self.query_delegate)
        self.currentIndexChanged.connect(self.check_current)

    def clear_current(self):
        self.setCurrentIndex(0)

    def set_current(self, query):
        self.current_query = query

    def check_current(self, index):
        if not self.history:
            return
        if index == 0:
            self.current_query = None
            return
        query = self.history[index]
        if query == self.current_query:
            return
        self.current_query = query
        self.newQuery.emit(self.current_query)

    def set_history(self, history):
        if history == self.history[1:]:
            return
        self.currentIndexChanged.disconnect(self.check_current)
        if self.currentIndex() < 0:
            self.setCurrentIndex(0)
        if self.history:
            current_query = self.history[self.currentIndex()]
        else:
            current_query = history[0]
        self.clear()
        self.addItem(self.history[0])
        self.history = self.history[:1]
        for i,h in enumerate(history):
            self.addItem(h[0])
            self.setItemData(i+1,(h[1], h[2]), QtCore.Qt.ItemDataRole.DecorationRole)
            if h == current_query:
                self.setCurrentIndex(i+1)
            self.history.append(h)
        self.currentIndexChanged.connect(self.check_current)


class DefaultTable(QtWidgets.QTableWidget):
    def __init__(self, *args, use_oov_header=False):
        super(DefaultTable, self).__init__(*args)
        if use_oov_header:
            self.header = OovHeaderView(QtCore.Qt.Orientation.Horizontal, self)
            self.header.setSectionsClickable(True)
            self.setHorizontalHeader(self.header)
        self.setCornerButtonEnabled(False)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setHighlightSections(False)
        self.verticalHeader().setSectionsClickable(False)

        self.setAlternatingRowColors(True)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSortIndicatorShown(True)
        self.setSortingEnabled(True)
        self.setDragEnabled(False)
        self.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setSelectionBehavior(QtWidgets.QTableView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)


class DefaultTableView(QtWidgets.QTableView):
    def __init__(self, *args, use_oov_header=False):
        super(DefaultTableView, self).__init__(*args)
        self.setCornerButtonEnabled(False)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setHighlightSections(False)
        self.verticalHeader().setSectionsClickable(False)

        self.setAlternatingRowColors(True)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSortIndicatorShown(True)
        self.setSortingEnabled(True)
        self.setDragEnabled(False)
        self.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setSelectionBehavior(QtWidgets.QTableView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)


class TableModel(QtCore.QAbstractTableModel):
    def __init__(self, header_data):
        super().__init__()
        self._header_data = header_data
        self._data = []

    def update_data(self, data):
        self.layoutAboutToBeChanged.emit()
        self._data = data
        self.layoutChanged.emit()

    def headerData(self, index, orientation, role):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if orientation == QtCore.Qt.Orientation.Horizontal:
                return self._header_data[index]
            else:
                return index + 1


    def data(self, index, role):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._data[index.row()][index.column()]

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self._header_data)

class MyProxy(QtCore.QSortFilterProxyModel):
    def __init__(self, *args):
        super(MyProxy, self).__init__(*args)
        self.setDynamicSortFilter(True)

    def headerData(self, section, orientation, role):
        # if display role of vertical headers
        if orientation == QtCore.Qt.Orientation.Vertical and role == QtCore.Qt.ItemDataRole.DisplayRole:
            # return the actual row number
            return section + 1
        # for other cases, rely on the base implementation
        return super(MyProxy, self).headerData(section, orientation, role)

class SearchWidget(QtWidgets.QWidget):
    searchNew = QtCore.pyqtSignal(object)
    showUtterance = QtCore.pyqtSignal(object, object)
    def __init__(self, parent=None):
        super(SearchWidget, self).__init__(parent=parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QtWidgets.QVBoxLayout()

        search_wrapper = QtWidgets.QVBoxLayout()
        self.search_field = SearchField()

        self.table_widget = DefaultTableView()
        self.table_widget.verticalHeader().setVisible(True)
        self.table_widget.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.table_widget.setAutoScroll(False)
        self.table_widget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table_widget.horizontalHeader().sectionResized.connect(self.recalculate_column_width)
        self.table_widget.horizontalHeader().sortIndicatorChanged.connect(self.table_widget.resizeRowsToContents)
        self.utterance_id_column_index = 0

        self.table_model = TableModel(['Utterance', 'Speaker', 'Text'])
        self.proxy_model = MyProxy()
        self.proxy_model.setSourceModel(self.table_model)
        self.table_widget.setModel(self.proxy_model)

        self.table_widget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)

        self.table_widget.selectionModel().selectionChanged.connect(self.update_index)
        self.table_widget.setVisible(False)
        self.empty_label = QtWidgets.QLabel('No results were found')
        self.empty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop |QtCore.Qt.AlignmentFlag.AlignHCenter)

        self.empty_label.setVisible(False)
        self.empty_label.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.nowrap_delegate = NoWrapDelegate(self.table_widget)
        self.highlight_delegate = HighlightDelegate(self.table_widget)
        self.table_widget.horizontalHeader().setMinimumSectionSize(self.highlight_delegate.minimum_doc_size)
        self.table_widget.setItemDelegateForColumn(0, self.nowrap_delegate)
        self.table_widget.setItemDelegateForColumn(2, self.highlight_delegate)

        search_wrapper.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop |QtCore.Qt.AlignmentFlag.AlignHCenter)
        search_wrapper.addWidget(self.search_field)
        self.search_history_widget = HistoryDropDown()
        self.search_history_widget.newQuery.connect(self.search_from_history)

        self.search_toolbar = QtWidgets.QToolBar()
        spacer = HorizontalSpacer()
        self.search_toolbar.addWidget(self.search_history_widget)
        self.search_toolbar.addWidget(spacer)
        search_wrapper.addWidget(self.search_toolbar)
        search_wrapper_widget = QtWidgets.QWidget()
        search_wrapper_widget.setLayout(search_wrapper)
        layout.addWidget(search_wrapper_widget, alignment=QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.empty_label, alignment=QtCore.Qt.AlignmentFlag.AlignTop |QtCore.Qt.AlignmentFlag.AlignHCenter, stretch=1)
        layout.addWidget(self.table_widget)
        self.setLayout(layout)
        self.search_field.searchActivated.connect(self.search)

        self.current_search_value = ''
        self.current_search_text = ''
        self.current_search_query = None
        self.current_search_results = []
        self.current_search_index = 0
        self.corpus = None
        self.current_file_name = None
        self.history = []
        self.currently_searching = False

    def update_corpus(self, corpus):
        self.corpus = corpus

    def update_config(self, config):
        font_config = config.font_options
        self.table_widget.setFont(font_config['font'])
        self.table_widget.horizontalHeader().setFont(font_config['header_font'])
        self.table_widget.verticalHeader().setFont(font_config['header_font'])
        self.search_field.setFont(font_config['font'])
        self.empty_label.setFont(font_config['font'])
        self.search_history_widget.setFont(font_config['font'])
        self.highlight_delegate.update_config(config)
        self.nowrap_delegate.update_config(config)
        self.search_history_widget.query_delegate.selection_color = self.highlight_delegate.selection_color
        self.table_widget.repaint()

    def load_history(self, history):
        self.history = history
        self.search_history_widget.set_history(self.history)

    def update_file_name(self, file_name):
        self.current_file_name = file_name

    def update_history(self, query):
        if self.history and self.history[0] ==query:
            return
        self.history = [x for x in self.history if x != query]
        self.history.insert(0, query)
        self.search_history_widget.newQuery.disconnect(self.search_from_history)
        self.search_history_widget.set_current(query)
        self.search_history_widget.set_history(self.history)
        self.search_history_widget.newQuery.connect(self.search_from_history)

    def search_from_history(self, query):
        if not query:
            return
        self.search_field.setQuery(query)

    def recalculate_column_width(self, index, oldSize, newSize):
        if index != 2:
            return
        self.highlight_delegate.current_doc_width = newSize
        self.table_widget.resizeRowsToContents()

    def search(self):

        query = self.search_field.query()
        if query == self.current_search_query:
            self.next()
            return
        try:
            self.table_widget.selectionModel().selectionChanged.disconnect(self.update_index)
        except TypeError:
            pass
        new_data = []

        self.current_search_results = []
        try:
            self.table_widget.horizontalHeader().sortIndicatorChanged.disconnect(self.table_widget.resizeRowsToContents)
        except TypeError:
            pass
        self.empty_label.setVisible(False)
        self.table_widget.setVisible(False)

        self.current_search_index = 0
        value = self.search_field.text()
        if not value:
            self.table_model.update_data(new_data)
            self.current_search_query = None
            self.search_history_widget.clear_current()
            self.searchNew.emit(value)
            return
        self.current_search_text = value
        self.current_search_query = query
        if not self.corpus:
            self.table_model.update_data(new_data)
            return
        if not self.current_search_text:
            self.table_model.update_data(new_data)
            return
        self.update_history(self.search_field.query())
        self.current_search_value = re.compile(self.current_search_text)
        self.searchNew.emit(self.current_search_value)
        self.highlight_delegate.setFilters([self.current_search_text])
        for k, v in self.corpus.text_mapping.items():
            if self.corpus.utt_file_mapping[k] != self.current_file_name:
                continue
            if re.search(self.current_search_value, v):
                self.current_search_results.append(k)
        if not self.current_search_results:
            self.empty_label.setVisible(True)
            self.table_model.update_data(new_data)
            return
        if self.corpus.segments:
            self.current_search_results.sort(key=lambda x: self.corpus.segments[x]['begin'])

        self.empty_label.setVisible(False)
        self.table_widget.setVisible(True)

        self.table_widget.selectionModel().clearSelection()
        for i,u in enumerate(self.current_search_results):
            new_data.append([u, self.corpus.utt_speak_mapping[u], self.corpus.text_mapping[u]])

        self.table_model.update_data(new_data)
        self.table_widget.horizontalHeader().sortIndicatorChanged.connect(self.table_widget.resizeRowsToContents)

        self.table_widget.selectionModel().selectionChanged.connect(self.update_index)

    def update_index(self):
        rows = self.table_widget.selectionModel().selectedRows(0)
        if not rows:
            return
        row = rows[0]
        self.current_search_index = row.row()
        index = self.proxy_model.index(self.current_search_index,self.utterance_id_column_index)
        utterance = self.proxy_model.data(index)
        self.showUtterance.emit(None, True)
        self.showUtterance.emit(utterance, True)

    def next(self):
        if not self.current_search_results:
            return
        if self.current_search_text !=  self.search_field.text():
            self.search()
            return
        if self.current_search_index < len(self.current_search_results) - 1:
            self.current_search_index += 1
        else:
            self.current_search_index = 0
        self.table_widget.selectRow(self.current_search_index)



class DictionaryWidget(QtWidgets.QWidget):
    dictionaryError = QtCore.pyqtSignal(object)
    dictionaryModified = QtCore.pyqtSignal()

    def __init__(self, *args):
        super(DictionaryWidget, self).__init__(*args)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        dict_layout = QtWidgets.QVBoxLayout()
        self.table = DefaultTable()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.AllEditTriggers)
        self.ignore_errors = False
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnCount(2)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.setHorizontalHeaderLabels(['Word', 'Pronunciation'])
        self.table.cellChanged.connect(self.dictionary_edited)
        dict_layout.addWidget(self.table)
        self.tool_bar_wrapper = QtWidgets.QVBoxLayout()
        self.tool_bar = QtWidgets.QToolBar()
        self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.tool_bar_wrapper.addWidget(self.tool_bar, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        dict_layout.addLayout(self.tool_bar_wrapper)

        self.setLayout(dict_layout)

    def dictionary_edited(self):
        self.dictionaryModified.emit()

    def update_config(self, config):
        font = config.font_options
        self.table.setFont(font['font'])
        self.table.horizontalHeader().setFont(font['header_font'])
        self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        widget_widths = 0
        for a in self.tool_bar.actions():
            for w in a.associatedWidgets():
                if not isinstance(w, QtWidgets.QToolButton):
                    continue
                widget_widths += w.sizeHint().width()
        if widget_widths + 30 > self.parent().width():
            self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)

    def update_g2p(self, g2p_model):
        self.g2p_model = g2p_model

    def update_dictionary(self, dictionary):
        self.dictionary = dictionary
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.table.cellChanged.disconnect(self.dictionary_edited)
        self.table.clearContents()
        if not dictionary:
            self.table.setRowCount(0)
            return
        self.table.setRowCount(len(self.dictionary))
        cur_index = 0
        for word, prons in sorted(self.dictionary.words.items()):
            for p in prons:
                pronunciation = ' '.join(p['pronunciation'])
                self.table.setItem(cur_index, 0, QtWidgets.QTableWidgetItem(word))
                self.table.setItem(cur_index, 1, QtWidgets.QTableWidgetItem(pronunciation))
                cur_index += 1
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.cellChanged.connect(self.dictionary_edited)

    def create_dictionary_for_save(self):
        from collections import defaultdict
        words = defaultdict(list)
        phones = set()
        for i in range(self.table.rowCount()):
            word = self.table.item(i, 0).text()
            pronunciation = self.table.item(i, 1).text()
            pronunciation = tuple(pronunciation.split(' '))
            phones.update(pronunciation)
            pron = {'pronunciation': pronunciation, 'probability': None}
            words[word].append(pron)
            new_phones = phones - self.dictionary.phones
            if new_phones and not self.ignore_errors:
                self.dictionaryError.emit(f"Found new phones ({', '.join(new_phones)}) in pronunciation for {word} /{pronunciation}/. "
                                          f"Please correct the pronunciation or click the Ignore Errors button.")
                return
        return words

    def create_pronunciation(self, word):
        if self.dictionary is None:
            return
        if not word:
            return
        pronunciation = None
        if self.g2p_model is not None and not G2P_DISABLED:
            gen = Generator(self.g2p_model, [word])
            results = gen.generate()
            pronunciation = results[word][0]
            pron = {'pronunciation': tuple(pronunciation.split(' ')), 'probability': 1}
            self.dictionary.words[word].append(pron)
        for i in range(self.table.rowCount()):
            row_text = self.table.item(i, 0).text()
            if not row_text:
                continue
            if row_text < word:
                continue
            self.table.insertRow(i)
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(word))
            if pronunciation is not None:
                self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(pronunciation))
            self.table.scrollToItem(self.table.item(i, 0))
            self.table.selectRow(i)
            break

    def look_up_word(self, word):
        if self.dictionary is None:
            return
        if not word:
            return
        for i in range(self.table.rowCount()):
            if self.table.item(i, 0).text() == word:
                self.table.scrollToItem(self.table.item(i, 0))
                self.table.selectRow(i)
                break


class SpeakerWidget(QtWidgets.QWidget):
    def __init__(self, *args):
        super(SpeakerWidget, self).__init__(*args)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        speaker_layout = QtWidgets.QVBoxLayout()
        self.table = DefaultTable()
        self.table.setColumnCount(2)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.table.setHorizontalHeaderLabels(['Speaker', 'Utterances'])
        speaker_layout.addWidget(self.table)

        self.tool_bar_wrapper = QtWidgets.QVBoxLayout()
        self.tool_bar = QtWidgets.QToolBar()
        self.tool_bar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.tool_bar_wrapper.addWidget(self.tool_bar)

        self.speaker_edit = NewSpeakerField()

        self.tool_bar.addWidget(self.speaker_edit)

        toolbar_wrapper_widget = QtWidgets.QWidget()
        toolbar_wrapper_widget.setLayout(self.tool_bar_wrapper)
        speaker_layout.addWidget(toolbar_wrapper_widget)

        self.setLayout(speaker_layout)

    def update_corpus(self, corpus):
        self.corpus = corpus
        self.refresh_speakers()

    def update_config(self, config):
        font = config.font_options
        self.table.setFont(font['font'])
        self.table.horizontalHeader().setFont(font['header_font'])
        self.speaker_edit.setFont(font['font'])
        self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        widget_widths = 0
        for a in self.tool_bar.actions():
            for w in a.associatedWidgets():
                if not isinstance(w, QtWidgets.QToolButton):
                    continue
                widget_widths += w.sizeHint().width()

        if widget_widths + 30 > self.width():
            self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)

    def refresh_speakers(self):
        if self.corpus is None:
            return
        for i in range(1,self.table.horizontalHeader().count()):
            self.table.horizontalHeader().setSectionResizeMode(i, QtWidgets.QHeaderView.Fixed)
        self.table.clearContents()
        speakers = sorted(self.corpus.speak_utt_mapping.keys())
        self.table.setRowCount(len(speakers))

        for i, s in enumerate(speakers):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(s))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(str(len(self.corpus.speak_utt_mapping[s]))))
        for i in range(1,self.table.horizontalHeader().count()):
            self.table.horizontalHeader().setSectionResizeMode(i, QtWidgets.QHeaderView.ResizeToContents)


class InformationWidget(QtWidgets.QTabWidget):  # pragma: no cover

    def __init__(self, parent):
        super(InformationWidget, self).__init__(parent=parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        # self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.dictionary = None
        self.corpus = None
        self.g2p_model = None

        self.search_widget = SearchWidget()

        self.dictionary_widget = DictionaryWidget()

        self.speaker_widget = SpeakerWidget()

        self.addTab(self.search_widget, create_icon('search'), 'Search')
        self.addTab(self.dictionary_widget, create_icon('book'), 'Dictionary')
        self.addTab(self.speaker_widget, create_icon('speaker'), 'Speakers')

        self.currentChanged.connect(self.refresh)
        self.config = None

    def refresh(self, index):
        widget = self.widget(index)
        widget.update_config(self.config)

    def update_config(self, config):
        self.config = config
        column_ratio = outside_column_ratio
        column_width = int(column_ratio * config['width'])
        column_width = max(column_width, outside_column_minimum)
        self.setFixedWidth(column_width)
        self.setFont(config.font_options['header_font'])
        self.speaker_widget.update_config(config)
        self.dictionary_widget.update_config(config)
        self.search_widget.update_config(config)

        if config.is_mfa:
            self.setTabIcon(0, create_icon('search'))
            self.setTabIcon(1, create_icon('book'))
            self.setTabIcon(2, create_icon('speaker'))
        else:
            self.setTabIcon(0, create_icon('search', default_only=True))
            self.setTabIcon(1, create_icon('book', default_only=True))
            self.setTabIcon(2, create_icon('speaker', default_only=True))
