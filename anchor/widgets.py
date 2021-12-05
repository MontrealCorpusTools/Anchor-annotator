from __future__ import annotations
from montreal_forced_aligner.g2p.generator import PyniniGenerator as Generator, G2P_DISABLED

from typing import TYPE_CHECKING

import anchor.qrc_resources

from PySide6 import QtGui, QtCore, QtWidgets, QtMultimedia

import pyqtgraph as pg
import re
from anchor.models import CorpusModel, CorpusSelectionModel, CorpusProxy
from montreal_forced_aligner.corpus.classes import Speaker

if TYPE_CHECKING:
    from anchor.main import MainWindow

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
    timeChanged = QtCore.Signal(object)
    def __init__(self, corpus_model: CorpusModel, selection_model: CorpusSelectionModel):
        super(MediaPlayer, self).__init__()
        self.max_time = None
        self.min_time = None
        self.start_time = 0
        self.sr = None
        self.positionChanged.connect(self.checkStop)
        self.setAudioOutput(QtMultimedia.QAudioOutput())
        self.buf = QtCore.QBuffer()
        self.corpus_model = corpus_model
        self.selection_model = selection_model
        self.corpus_model.fileChanged.connect(self.loadNewFile)
        self.selection_model.viewChanged.connect(self.update_times)
        self.selection_model.selectionAudioChanged.connect(self.update_times)

    def set_volume(self, volume: int):
        if self.audioOutput() is None:
            return
        self.audioOutput().setVolume(volume)

    def update_times(self, min_time, max_time):
        self.setMinTime(min_time)
        self.setMaxTime(max_time)
        self.setCurrentTime(min_time)

    def loadNewFile(self):
        self.channels = self.corpus_model.current_file.num_channels
        end = min(self.selection_model.max_time, self.corpus_model.current_file.duration)
        p = QtCore.QUrl.fromLocalFile(self.corpus_model.current_file.wav_path)
        self.setSource(p)
        self.setMinTime(0)
        self.setStartTime(0)
        self.setMaxTime(end)
        self.setCurrentTime(0)

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
        pos = time * 1000
        self.setPosition(pos)
        self.timeChanged.emit(self.currentTime())

    def checkStop(self, position):
        if self.playbackState() == QtMultimedia.QMediaPlayer.PlayingState:
            self.timeChanged.emit(self.currentTime())
            if self.max_time is not None:
                if position > self.max_time + 3:
                    self.stop()
                    self.setCurrentTime(self.selection_model.min_time)


def create_triggered_icon(name, default_only=False):
    if name == 'play':
        if default_only:
            icon = QtGui.QIcon()
            icon.addFile(f':play.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
            icon.addFile(f':checked/pause.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.On)
            icon.addFile(f':hover/play.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.Off)
            icon.addFile(f':hover/pause.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.On)
        else:
            icon = QtGui.QIcon()
            icon.addFile(f':play.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
            icon.addFile(f':hover/play.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.Off)
    else:
        icon = QtGui.QIcon(f':hover/{name}.svg')
    return icon

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
            icon.addFile(f':disabled/volume-up.svg', mode=QtGui.QIcon.Disabled)
            icon.addFile(f':hover/volume-mute.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.On)
            icon.addFile(f':hover/volume-up.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.Off)
            icon.addFile(f':disabled/volume-mute.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.On)
        else:
            icon = QtGui.QIcon()
            icon.addFile(f':volume-up.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
            icon.addFile(f':disabled/volume-mute.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.On)
    elif name == 'play':
        if default_only:
            icon = QtGui.QIcon()
            icon.addFile(f':play.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
            icon.addFile(f':hover/play.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.Off)
        else:
            icon = QtGui.QIcon()
            icon.addFile(f':play.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
            icon.addFile(f':checked/pause.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.On)
            icon.addFile(f':hover/play.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.Off)
            icon.addFile(f':hover/pause.svg', mode=QtGui.QIcon.Active, state=QtGui.QIcon.On)
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


class DefaultAction(QtGui.QAction):
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
                self.triggered_icon = create_triggered_icon(icon_name)
        self.setIcon(self.default_icon)

    def update_icons(self, use_mfa):
        if use_mfa:
            self.default_icon = create_icon(self.icon_name)
            self.triggered_icon = create_triggered_icon(self.icon_name)
        else:
            self.default_icon = create_icon(self.icon_name, default_only=True)
            self.triggered_icon = create_triggered_icon(self.icon_name, default_only=True)
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


class AnchorAction(QtGui.QAction):
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
    enableAddSpeaker = QtCore.Signal(object)
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

        self.clear_action = QtGui.QAction(icon=clear_icon, parent=self)
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


class HelpDropDown(QtWidgets.QToolButton):
    def __init__(self, *args):
        super(HelpDropDown, self).__init__(*args)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.menu = QtWidgets.QMenu(self)
        self.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
        self.setMenu(self.menu)
        self.clicked.connect(self.showMenu)

    def addAction(self, action: 'QtGui.QAction') -> None:
        self.menu.addAction(action)

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
                self.menu.addAction(s.name)

        if self.current_speaker not in speakers:
            self.setCurrentSpeaker(Speaker(''))

    def setCurrentSpeaker(self, speaker: Speaker):
        self.current_speaker = speaker
        self.setText(speaker.name)



class UtteranceListWidget(QtWidgets.QWidget):  # pragma: no cover
    fileChanged = QtCore.Signal(object)

    def __init__(self,  *args):
        super(UtteranceListWidget, self).__init__(*args)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(100)
        layout = QtWidgets.QVBoxLayout()

        self.file_dropdown = QtWidgets.QComboBox()
        self.file_dropdown.currentTextChanged.connect(self.fileChanged.emit)
        self.file_dropdown.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.file_dropdown)
        self.search_box = SearchBox()
        layout.addWidget(self.search_box)
        self.search_box.search_field.searchActivated.connect(self.search)
        self.current_search_query = None
        self.current_search_text = ''
        self.currently_searching = False

        self.table_widget = DefaultTableView(use_oov_header=True)
        self.corpus_model: CorpusModel = self.parent().corpus_model
        self.proxy_model: CorpusProxy= self.parent().proxy_model
        self.selection_model: CorpusSelectionModel = self.parent().selection_model
        self.table_widget.doubleClicked.connect(self.selection_model.focusUtterance)
        self.table_widget.setModel(self.proxy_model)
        self.table_widget.setSelectionModel(self.selection_model)
        self.highlight_delegate = HighlightDelegate(self.table_widget)
        self.nowrap_delegate = NoWrapDelegate(self.table_widget)

        self.utterance_id_column_index = 1
        self.begin_column_index = self.utterance_id_column_index
        self.icon_delegate = IconDelegate(self.table_widget)
        self.table_widget.setItemDelegateForColumn(0, self.icon_delegate)
        self.table_widget.horizontalHeader().setSectionResizeMode(self.utterance_id_column_index, QtWidgets.QHeaderView.Interactive)

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
        self.highlight_delegate.update_config(config)
        self.search_box.query_delegate.update_config(config)
        self.nowrap_delegate.update_config(config)
        self.search_box.setFont(font['font'])
        self.search_box.search_field.setFont(font['font'])
        self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

    def load_history(self, history):
        self.search_box.set_history(history)

    def search_from_history(self, query):
        if not query:
            return
        self.search_box.setQuery(query)

    def search(self):
        query = self.search_box.query()
        if query == self.current_search_query:
            self.next()
            return
        self.current_search_query = query
        self.current_search_text = self.search_box.text()

        value = self.search_box.text()
        self.proxy_model.setFilterRegularExpression(value)
        print(self.proxy_model.filterRegularExpression())
        self.proxy_model.invalidate()

    def next(self):
        result_count = self.proxy_model.rowCount()
        if result_count == 0:
            return
        if self.current_search_text !=  self.search_box.text():
            self.search()
            return
        current_index = self.selection_model.selectedRows(1)
        if current_index and current_index[0] < result_count - 1:
            current_index = self.proxy_model.index(current_index[0]+1, 1)
        else:
            current_index = self.proxy_model.index(0, 1)
        self.selection_model.select(current_index, QtCore.QItemSelectionModel.SelectionFlag.SelectCurrent|QtCore.QItemSelectionModel.SelectionFlag.Rows)


    def update_corpus(self):
        self.refresh_file_dropdown()

    def refresh_file_dropdown(self):
        self.file_dropdown.clear()
        for file in self.corpus_model.files:
            self.file_dropdown.addItem(file.name)


class TranscriptionWidget(QtWidgets.QTextEdit):  # pragma: no cover
    def __init__(self, corpus_model, selection_model, *args):
        super(TranscriptionWidget, self).__init__(*args)
        self.setAcceptRichText(False)
        # Default dictionary based on the current locale.
        self.dictionary = None
        self.corpus_model = corpus_model
        self.selection_model = selection_model
        self.highlighter = Highlighter(self.document())
        self.textChanged.connect(self.update_utterance_text)
        self.selection_model.currentChanged.connect(self.update_utterance)

    def update_utterance(self):
        text = self.selection_model.currentText()
        if not text:
            text = ''
        print("THIS IS CURRENT TEXT:", text)
        self.textChanged.disconnect(self.update_utterance_text)
        self.setText(text)
        self.textChanged.connect(self.update_utterance_text)

    def update_utterance_text(self):
        if not self.selection_model.selectedUtterances():
            return
        utt = self.selection_model.currentUtterance()
        if utt is None:
            return
        self.textChanged.disconnect(self.update_utterance_text)
        self.corpus_model.sourceModel().update_utterance(utt, text=self.toPlainText())
        self.textChanged.connect(self.update_utterance_text)

    def setDictionary(self, dictionary):
        self.dictionary = dictionary
        self.highlighter.setDict(self.dictionary)

class UtteranceLine(pg.InfiniteLine):

    def __init__(self, *args, movingPen=None, **kwargs):
        super(UtteranceLine, self).__init__(*args, **kwargs)
        self.movingPen = movingPen

    def mouseDragEvent(self, ev):
        if self.movable and ev.button() == QtCore.Qt.MouseButton.LeftButton:
            if ev.isStart():
                self.moving = True
                self.currentPen = self.movingPen
                self.update()
                self.cursorOffset = self.pos() - self.mapToParent(ev.buttonDownPos())
                self.startPosition = self.pos()
            ev.accept()

            if not self.moving:
                return
            p = self.cursorOffset + self.mapToParent(ev.pos())
            p.setY(self.startPosition.y())
            self.setPos(p)
            self.sigDragged.emit(self)
            if ev.isFinish():
                self.currentPen = self.pen
                self.moving = False
                self.sigPositionChangeFinished.emit(self)
                self.boundingRect()
                self.update()

    def _computeBoundingRect(self):
        #br = UIGraphicsItem.boundingRect(self)
        vr = self.viewRect()  # bounds of containing ViewBox mapped to local coords.
        if vr is None:
            return QtCore.QRectF()

        ## add a 4-pixel radius around the line for mouse interaction.

        px = self.pixelLength(direction=pg.Point(1,0), ortho=True)  ## get pixel length orthogonal to the line
        if px is None:
            px = 0
        pw = max(self.pen.width() / 2, self.hoverPen.width() / 2)
        w = max(4, self._maxMarkerSize + pw) + 1
        w = w * px
        br = QtCore.QRectF(vr)
        br.setBottom(-w)
        br.setTop(w)


        if not self.moving:
            left = self.span[0]
            right = self.span[1]
        else:
            length = br.width()
            left = br.left()
            right = br.left() + length

        br.setLeft(left)
        br.setRight(right)
        br = br.normalized()

        vs = self.getViewBox().size()

        if self._bounds != br or self._lastViewSize != vs:
            self._bounds = br
            self._lastViewSize = vs
            self.prepareGeometryChange()

        self._endPoints = (left, right)
        self._lastViewRect = vr

        return self._bounds



class UtteranceRegion(pg.LinearRegionItem):  # pragma: no cover
    dragFinished = QtCore.Signal(object)
    def __init__(self, utterance, config, view_min=0, view_max=10, selected=False, span=(0,1)):
        self.utterance = utterance
        self.selected = selected
        self.config = config
        self.selected_range_color = config['selected_range_color']
        self.selected_range_color.setAlpha(90)
        self.interval_background_color = config['interval_background_color']
        self.hover_line_color = config['hover_line_color']
        self.moving_line_color = config['moving_line_color']

        self.break_line_color = config['break_line_color']
        self.text_color = config['text_color']
        self.selected_interval_color = config['selected_interval_color']
        self.plot_text_font = config['font']
        self.plot_text_width = config['plot_text_width']
        self.span = span
        self.view_min = view_min
        self.view_max = view_max

        self.utterance_min = self.utterance.begin
        self.utterance_max = self.utterance.end
        if self.selected:
            self.background_brush = pg.mkBrush(self.selected_range_color)
        else:
            #self.interval_background_color.setAlpha(0)
            self.background_brush = pg.mkBrush(self.interval_background_color)

        self.pen = pg.mkPen(self.break_line_color, width=3)
        self.hoverPen = pg.mkPen(self.hover_line_color, width=3)
        self.movingPen = pg.mkPen(self.moving_line_color, width=3, style=QtCore.Qt.PenStyle.DashLine)


        pg.GraphicsObject.__init__(self)
        self.orientation = 'vertical'
        self.bounds = QtCore.QRectF()
        self.blockLineSignal = False
        self.moving = False
        self.mouseHovering = False
        self.swapMode = 'sort'
        self.clipItem = None
        self._bounds = None

        # note LinearRegionItem.Horizontal and LinearRegionItem.Vertical
        # are kept for backward compatibility.
        lineKwds = dict(
            movable=True,
            bounds=None,
            span=self.span,
            pen=self.pen,
            hoverPen=self.hoverPen,
            movingPen=self.movingPen,
        )

        self.lines = [
            UtteranceLine(QtCore.QPointF(self.utterance_min, 0), angle=90, **lineKwds),
            UtteranceLine(QtCore.QPointF(self.utterance_max, 0), angle=90, **lineKwds)]

        for l in self.lines:
            l.setParentItem(self)
            l.sigPositionChangeFinished.connect(self.lineMoveFinished)
        self.lines[0].sigPositionChanged.connect(self._line0Moved)
        self.lines[1].sigPositionChanged.connect(self._line1Moved)

        self.text = pg.TextItem(self.utterance.text, anchor=(0.5, 0.5), color=self.text_color)
        self.text.setFont(self.plot_text_font)
        self.text.setParentItem(self)
        self.setBrush(self.background_brush)
        self.setHoverBrush(self.background_brush)

        self.setZValue(-10)
        self.setMovable(True)
        #self.movable = False

    def setSelected(self, selected):
        self.selected = selected
        if self.selected:
            self.background_brush = pg.mkBrush(self.selected_range_color)
        else:
            #self.interval_background_color.setAlpha(0)
            self.background_brush = pg.mkBrush(self.interval_background_color)
        self.setBrush(self.background_brush)
        self.update()


    def boundingRect(self):
        br = QtCore.QRectF(self.viewRect())  # bounds of containing ViewBox mapped to local coords.

        rng = self.getRegion()

        br.setLeft(rng[0])
        br.setRight(rng[1])

        br.setTop(self.span[1])
        br.setBottom(self.span[0])

        x_mid_point = br.left() + (br.width()/2)
        y_mid_point = br.bottom() + abs(br.height()/2)
        self.text.setPos(x_mid_point, y_mid_point)
        if self.text.textItem.boundingRect().width() > self.plot_text_width:
            self.text.setTextWidth(self.plot_text_width)
        br = br.normalized()

        if self._bounds != br:
            self._bounds = br
            self.prepareGeometryChange()

        return br

    def mouseDragEvent(self, ev):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return

        if ev.isFinish():
            pos = ev.pos()
            self.dragFinished.emit(pos)
            return

        ev.accept()



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
        print("SETTING", search_term)
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


class UtteranceView(pg.PlotWidget):
    timeRequested = QtCore.Signal(object)
    def __init__(self, corpus_model: CorpusModel, proxy_model, selection_model: CorpusSelectionModel):
        super(UtteranceView, self).__init__()
        self.corpus_model: CorpusModel = corpus_model
        self.proxy_model = proxy_model
        self.selection_model = selection_model
        self.hideButtons()
        self.selection_model.selectionChanged.connect(self.updateSelection)
        self.selection_model.viewChanged.connect(self.update_plot)
        self.corpus_model.dataChanged.connect(self.update_plot)
        self.corpus_model.layoutChanged.connect(self.update_plot)
        self.line = pg.InfiniteLine(
            pos=-20,
            pen=pg.mkPen('r', width=1),
            movable=False  # We have our own code to handle dragless moving.
        )
        self.wave_line_one = pg.PlotDataItem()
        self.wave_line_two = pg.PlotDataItem()
        self.getPlotItem().hideAxis('left')
        self.getPlotItem().setMouseEnabled(False, False)

        self.addItem(self.line)
        self.getPlotItem().setMenuEnabled(False)
        self.scene().sigMouseClicked.connect(self.update_current_time)

        self.corpus_model.fileChanged.connect(self.set_up_new_file)
        self.show_all_speakers = False
        self.visible_utts = []

    def set_up_new_file(self):
        self.getPlotItem().getAxis('bottom')
        self.update_plot()
        self.selection_model.viewChanged.emit(self.selection_model.min_time, self.selection_model.max_time)

    def update_config(self, config):
        color_config = config.plot_color_options
        self.config = {}
        self.config.update(color_config)
        for k, v in self.config.items():
            if not isinstance(v, QtGui.QColor):
                self.config[k] = QtGui.QColor(v)

        self.axis_color = self.config['axis_color']
        self.background_color = self.config['background_color']
        self.wave_line_color = self.config['wave_line_color']
        self.break_line_color = self.config['break_line_color']
        self.text_color = self.config['text_color']

        self.config['plot_text_width'] = config['plot_text_width']

        font_config = config.font_options

        self.config['font'] = font_config['font']
        self.plot_text_font = font_config['font']

        self.axis_text_font = font_config['axis_font']

    def update_times(self, begin, end):
        self.min_time = begin
        self.max_time = end
        self.update_plot()

    def update_play_line(self, time):
        if not time:
            return
        self.line.setPos(time)
        self.line.update()

    def draw_wave_line(self):
        begin = self.selection_model.min_time
        end = self.selection_model.max_time
        x, y = self.corpus_model.current_file.normalized_waveform(begin, end)
        wave_pen = pg.mkPen(self.wave_line_color, width=1)
        self.wave_line_one.setPen(wave_pen)
        if len(y.shape) > 1 and y.shape[0] == 2:
            self.wave_line_two.setPen(wave_pen)
            pen = pg.mkPen(self.break_line_color, width=1)
            pen.setStyle(QtCore.Qt.DotLine)
            sub_break_line = pg.InfiniteLine(
                pos=2,
                angle=0,
                pen=pen,
                movable=False  # We have our own code to handle dragless moving.
            )
            self.addItem(sub_break_line)
            self.wave_line_one.setData(x=x, y=y[0,:])
            self.wave_line_two.setData(x=x, y=y[1,:])
            self.min_point = 0
            self.max_point = 4
            self.addItem(self.wave_line_one)
            self.addItem(self.wave_line_two)

        else:
            self.min_point = 0
            self.max_point = 2
            self.wave_line_one.setData(x=x, y=y)
            self.addItem(self.wave_line_one)
        self.setXRange(begin, end)

    def updateSelection(self):
        selected_utts = set()
        for row in self.selection_model.selectedRows(1):
            selected_utts.add(self.corpus_model.data(row, QtCore.Qt.ItemDataRole.DisplayRole))
        for reg in self.visible_utts:
            reg.setSelected(reg.utterance in selected_utts)
            reg.update()

    def update_utterance(self):
        reg = self.sender()
        print(reg)
        utt = reg.utterance
        beg, end = reg.getRegion()
        new_begin = round(beg, 4)
        new_end = round(end, 4)
        if new_end - new_begin > 100:
            reg.setRegion((utt['begin'], utt['end']))
            return
        self.corpus_model.update_utterance(utt, begin = new_begin, end=new_end)

    def draw_text_grid(self):
        begin = self.selection_model.min_time
        if self.corpus_model.current_file.num_speakers > 1:
            break_line = pg.InfiniteLine(
                pos=self.min_point,
                angle=0,
                pen=pg.mkPen(self.break_line_color, width=2),
                movable=False  # We have our own code to handle dragless moving.
            )
            self.addItem(break_line)
            self.visible_utts = []
            y_range = self.max_point - self.min_point
            speaker_tier_range = (y_range / 2)
            speaker_ind = 1
            self.speaker_mapping = {}
            visible_utts = self.selection_model.visible_utts()
            print(visible_utts)
            # Figure out speaker mapping first
            speakers = set()
            if not self.show_all_speakers:
                for u in visible_utts:
                    speakers.add(u.speaker)
            for sp in self.corpus_model.current_file.speaker_ordering:
                if not self.show_all_speakers and sp not in speakers:
                    continue
                if sp not in self.speaker_mapping:
                    self.speaker_mapping[sp] = speaker_ind
                    speaker_ind += 1
            num_speakers = speaker_ind - 1
            min_y = self.min_point - speaker_tier_range * num_speakers
            self.setYRange(min_y, self.max_point)
            for u in visible_utts:
                s_id = self.speaker_mapping[u.speaker]
                top_point = (self.min_point - speaker_tier_range * (s_id - 1))
                bottom_point = top_point - speaker_tier_range
                selected = self.selection_model.checkSelected(u)
                reg = UtteranceRegion(u, self.config, selected=selected, span=(bottom_point,top_point))
                reg.sigRegionChangeFinished.connect(self.update_utterance)
                reg.dragFinished.connect(self.update_selected_speaker)
                self.visible_utts.append(reg)
                self.addItem(reg)
            for k, s_id in self.speaker_mapping.items():
                t = pg.TextItem(k.name, anchor=(0, 0), color=self.text_color)
                t.setFont(self.plot_text_font)
                top_pos = self.min_point - speaker_tier_range * (s_id - 1)
                bottom_pos = top_pos - speaker_tier_range
                t.setPos(begin, top_pos)
                self.addItem(t)
                break_line = pg.InfiniteLine(
                    pos=bottom_pos,
                    angle=0,
                    pen=pg.mkPen(self.break_line_color, width=1),
                    movable=False  # We have our own code to handle dragless moving.
                )
                self.addItem(break_line)
        else:
            self.setYRange(self.min_point, self.max_point)

    def update_show_speakers(self, state):
        self.show_all_speakers = state > 0
        self.update_plot()

    def update_plot(self):
        self.getPlotItem().clear()
        self.getPlotItem().getAxis('bottom').setPen(self.axis_color)
        self.getPlotItem().getAxis('bottom').setTextPen(self.axis_color)
        self.getPlotItem().getAxis('bottom').setTickFont(self.axis_text_font)
        self.setBackground(self.background_color)
        if self.corpus_model.rowCount() == 0:
            return
        if self.corpus_model.current_file is None:
            return
        self.addItem(self.line)
        self.update_play_line(self.selection_model.min_time)

        self.draw_wave_line()
        self.draw_text_grid()


    def update_selected_speaker(self, pos):
        pos = pos.y()
        reg = self.sender()
        utterance = reg.utterance
        print(pos, reg)
        print(self.min_point)
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
        self.corpus_model.update_utterance(utterance, speaker=new_speaker)


    def update_current_time(self, ev):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        point = self.getPlotItem().vb.mapSceneToView(ev.scenePos())
        x = point.x()
        y = point.y()
        y_range = self.max_point - self.min_point
        speaker_tier_range = (y_range / 2)
        move_line = False
        time = x
        if y < self.min_point:
            speaker = None
            for k, s_id in self.speaker_mapping.items():
                top_pos = self.min_point - speaker_tier_range * (s_id - 1)
                bottom_pos = top_pos - speaker_tier_range
                if bottom_pos < y < top_pos:
                    speaker = k
                    break
            utt = None
            for reg in self.visible_utts:

                u = reg.utterance
                if u.end < time:
                    continue
                if u.begin > time:
                    break
                if u.speaker != speaker:
                    continue
                utt = u
            if utt is not None:
                index = self.corpus_model.indexForUtterance(utt)
                if modifiers == QtCore.Qt.ControlModifier and utt is not None:
                    self.selection_model.setCurrentIndex(index, QtCore.QItemSelectionModel.SelectionFlag.Select|QtCore.QItemSelectionModel.SelectionFlag.Rows)
                else:
                    self.selection_model.setCurrentIndex(index, QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect|QtCore.QItemSelectionModel.SelectionFlag.Rows)
            elif ev.double():
                beg = time - 0.5
                end = time + 0.5
                self.corpus_model.create_utterance(speaker, beg, end)
                return
            else:
                move_line = True
        elif ev.double():
            beg = time - 0.5
            end = time + 0.5
            self.corpus_model.create_utterance(None, beg, end)
            return

        else:
            move_line = True
        if move_line:
            self.current_time = x
            if self.current_time < self.selection_model.min_time:
                self.current_time = self.selection_model.min_time
                x = self.current_time
            if self.current_time > self.selection_model.max_time:
                self.current_time = self.selection_model.max_time
                x = self.current_time
            self.timeRequested.emit(x)


class UtteranceDetailWidget(QtWidgets.QWidget):  # pragma: no cover
    lookUpWord = QtCore.Signal(object)
    createWord = QtCore.Signal(object)
    saveUtterance = QtCore.Signal(object, object)
    selectUtterance = QtCore.Signal(object, object)
    createUtterance = QtCore.Signal(object, object, object, object)
    refreshCorpus = QtCore.Signal(object)
    utteranceChanged = QtCore.Signal(object)
    audioPlaying = QtCore.Signal(object)

    def __init__(self, parent: MainWindow):
        super(UtteranceDetailWidget, self).__init__(parent=parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.corpus_model: CorpusModel = self.parent().corpus_model
        self.proxy_model: CorpusProxy = self.parent().proxy_model
        self.proxy_model.layoutChanged.connect(self.set_search_term)
        self.selection_model: CorpusSelectionModel = self.parent().selection_model
        self.plot_widget = UtteranceView(self.corpus_model, self.proxy_model, self.selection_model)

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
        self.selection_model.viewChanged.connect(self.update_to_slider)
        scroll_bar_layout = QtWidgets.QVBoxLayout()
        scroll_bar_layout.addWidget(self.scroll_bar, 1)
        self.scroll_bar_wrapper.addLayout(scroll_bar_layout)
        self.scroll_bar_wrapper.addWidget(self.pan_right_button)


        self.tool_bar_wrapper = QtWidgets.QVBoxLayout()
        self.tool_bar = QtWidgets.QToolBar()
        self.tool_bar_wrapper.addWidget(self.tool_bar, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        self.text_widget = TranscriptionWidget(self.proxy_model, self.selection_model)
        self.text_widget.setMaximumHeight(100)
        self.text_widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)

        self.text_widget.customContextMenuRequested.connect(self.generate_context_menu)
        text_layout = QtWidgets.QHBoxLayout()
        text_layout.addWidget(self.text_widget)

        layout.addWidget(self.plot_widget)
        layout.addLayout(self.scroll_bar_wrapper)
        layout.addLayout(self.tool_bar_wrapper)
        layout.addLayout(text_layout)
        layout.setContentsMargins(0,0,0,0)
        self.setLayout(layout)
        self.show_all_speakers = False

    def update_config(self, config):
        self.plot_widget.update_config(config)

        font_config = config.font_options

        self.edit_text_font = font_config['big_font']
        self.text_widget.setFont(self.edit_text_font)

        self.tool_bar.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding,QtWidgets.QSizePolicy.MinimumExpanding)

        self.tool_bar.setFont(font_config['big_font'])
        s = self.tool_bar.size()
        icon_ratio = 0.03
        icon_height = int(icon_ratio*self.height())
        if icon_height < 24:
            icon_height = 24
        self.tool_bar.setIconSize(QtCore.QSize(icon_height, icon_height))
        icon_height = 25
        self.pan_left_button.setIconSize(QtCore.QSize(icon_height, icon_height))
        self.pan_right_button.setIconSize(QtCore.QSize(icon_height, icon_height))


        self.form_font = font_config['form_font']

        self.text_widget.highlighter.update_config(config)

    def update_to_slider(self):
        self.scroll_bar.valueChanged.disconnect(self.update_from_slider)
        begin = self.selection_model.min_time
        end = self.selection_model.max_time
        window_size = end - begin
        self.scroll_bar.setValue(begin)
        self.scroll_bar.setPageStep(window_size)
        self.scroll_bar.setMaximum(self.corpus_model.current_file.duration - window_size)
        self.scroll_bar.valueChanged.connect(self.update_from_slider)

    def update_from_slider(self, value):
        self.selection_model.update_from_slider(value)

    def reset(self):
        try:
            self.scroll_bar.valueChanged.disconnect(self.update_from_slider)
        except TypeError:
            pass
        self.reset_text()

    def update_corpus(self):
        if self.corpus_model.rowCount() == 0:
            self.reset()

    def update_dictionary(self, dictionary):
        self.text_widget.setDictionary(dictionary)

    def generate_context_menu(self, location):

        menu = self.text_widget.createStandardContextMenu()
        cursor = self.text_widget.cursorForPosition(location)
        cursor.select(QtGui.QTextCursor.WordUnderCursor)
        word = cursor.selectedText()
        # add extra items to the menu
        lookUpAction = QtGui.QAction("Look up '{}' in dictionary".format(word), self)
        createAction = QtGui.QAction("Add pronunciation for '{}'".format(word), self)
        lookUpAction.triggered.connect(lambda: self.lookUpWord.emit(word))
        createAction.triggered.connect(lambda: self.createWord.emit(word))
        menu.addAction(lookUpAction)
        menu.addAction(createAction)
        # show the menu
        menu.exec_(self.text_widget.mapToGlobal(location))

    def set_search_term(self):
        term = self.proxy_model.filterRegularExpression().pattern()
        self.text_widget.highlighter.setSearchTerm(term)

    def reset_text(self):
        if not self.corpus or self.utterance not in self.corpus.text_mapping:
            self.text_widget.setText('')
            return
        text = self.corpus.text_mapping[self.utterance]
        self.text_widget.setText(text)

    def showError(self, e):
        reply = DetailedMessageBox()
        reply.setDetailedText(str(e))
        ret = reply.exec_()

    def pan_left(self):
        self.scroll_bar.triggerAction(self.scroll_bar.SliderAction.SliderSingleStepSub)

    def pan_right(self):
        self.scroll_bar.triggerAction(self.scroll_bar.SliderAction.SliderSingleStepAdd)

class SearchField(QtWidgets.QLineEdit):
    searchActivated = QtCore.Signal(object)
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
        self.setObjectName('search_box')
        self.returnPressed.connect(self.activate)

        clear_icon = QtGui.QIcon()
        clear_icon.addFile(':clear.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
        clear_icon.addFile(':disabled/clear.svg', mode=QtGui.QIcon.Active)
        self.clear_action = QtGui.QAction(icon=clear_icon, parent=self)
        self.clear_action.triggered.connect(self.clear)
        self.clear_action.triggered.connect(self.returnPressed.emit)
        self.clear_action.setVisible(False)
        self.textChanged.connect(self.check_contents)

        regex_icon = QtGui.QIcon()
        regex_icon.addFile(':regex.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
        regex_icon.addFile(':highlighted/regex.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.On)

        self.regex_action = QtGui.QAction(icon=regex_icon, parent=self)
        self.regex_action.setCheckable(True)
        self.regex_action.toggled.connect(self.activate)

        word_icon = QtGui.QIcon()
        word_icon.addFile(':word.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)
        word_icon.addFile(':highlighted/word.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.On)
        self.word_action = QtGui.QAction(icon=word_icon, parent=self)
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

class SearchBox(QtWidgets.QComboBox):
    def __init__(self, *args, **kwargs):
        super(SearchBox, self).__init__(*args, **kwargs)
        self.search_field = SearchField()
        self.setLineEdit(self.search_field)
        self.history = []
        self.query_delegate = QueryDelegate(self)
        self.setItemDelegate(self.query_delegate)
        self.currentIndexChanged.connect(self.check_current)
        self.search_field.activate()
        self.search_field.searchActivated.connect(self.update_history)
        self.setCurrentIndex(-1)
        self.search_field.setPlaceholderText('Search current file...')


    def check_current(self, index):
        if not self.history:
            return
        if index < 0:
            self.current_query = None
            return
        query = self.history[index]
        if query == self.search_field.query():
            return
        self.search_field.setQuery(query)
        self.update_history(query)

    def update_history(self, query):
        if not query or not query[0]:
            return
        if self.history and self.history[0] ==query:
            return
        self.history = [x for x in self.history if x != query]
        self.history.insert(0, query)
        self.refresh()

    def refresh(self):
        self.currentIndexChanged.disconnect(self.check_current)
        self.clear()
        for i, h in enumerate(self.history):
            self.addItem(h[0])
            self.setItemData(i,(h[1], h[2]), QtCore.Qt.ItemDataRole.DecorationRole)
        self.currentIndexChanged.connect(self.check_current)

    def set_history(self, history):
        if history == self.history:
            return
        self.history = history
        self.refresh()
        self.setCurrentIndex(-1)

    def query(self):
        return self.search_field.query()

    def text(self):
        return self.search_field.text()

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

    @QtCore.Slot(list)
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
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed|QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked |
                             QtWidgets.QAbstractItemView.EditTrigger.SelectedClicked)



class DefaultTableView(QtWidgets.QTableView):
    def __init__(self, *args, use_oov_header=False):
        super(DefaultTableView, self).__init__(*args)
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
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed|QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked |
                             QtWidgets.QAbstractItemView.EditTrigger.SelectedClicked)



class DictionaryWidget(QtWidgets.QWidget):
    dictionaryError = QtCore.Signal(object)
    dictionaryModified = QtCore.Signal()

    def __init__(self, *args):
        super(DictionaryWidget, self).__init__(*args)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        dict_layout = QtWidgets.QVBoxLayout()
        self.corpus_model = self.parent().corpus_model
        self.table = DefaultTable()
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
        self.corpus_model = self.parent().corpus_model
        self.corpus_model.layoutChanged.connect(self.refresh_speakers)
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

    def update_config(self, config):
        font = config.font_options
        self.table.setFont(font['font'])
        self.table.horizontalHeader().setFont(font['header_font'])
        self.speaker_edit.setFont(font['font'])
        self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

    def refresh_speakers(self):
        for i in range(1,self.table.horizontalHeader().count()):
            self.table.horizontalHeader().setSectionResizeMode(i, QtWidgets.QHeaderView.Fixed)
        self.table.clearContents()
        speakers = self.corpus_model.corpus.speakers
        self.table.setRowCount(len(speakers))

        for i, s in enumerate(speakers):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(s.name))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(str(s.num_utterances)))
        for i in range(1,self.table.horizontalHeader().count()):
            self.table.horizontalHeader().setSectionResizeMode(i, QtWidgets.QHeaderView.ResizeToContents)

