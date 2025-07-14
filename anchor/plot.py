from __future__ import annotations

import functools
import logging
import os.path
import re
import typing
from typing import Optional

import numpy as np
import pyqtgraph as pg
import sqlalchemy
from kalpy.gmm.data import CtmInterval
from _kalpy.util import align_intervals
from montreal_forced_aligner.db import (
    PhoneInterval,
    Pronunciation,
    ReferencePhoneInterval,
    ReferenceWordInterval,
    Speaker,
    Utterance,
    Word,
    WordInterval,
)
from montreal_forced_aligner.dictionary.mixins import (
    DEFAULT_PUNCTUATION,
    DEFAULT_WORD_BREAK_MARKERS,
)
from montreal_forced_aligner.tokenization.simple import SimpleTokenizer
from PySide6 import QtCore, QtGui, QtWidgets

from anchor import workers
from anchor.models import (
    CorpusModel,
    CorpusSelectionModel,
    DictionaryTableModel,
    FileSelectionModel,
    FileUtterancesModel,
    SpeakerModel,
    TextFilterQuery,
)
from anchor.settings import AnchorSettings

pg.setConfigOption("imageAxisOrder", "row-major")  # best performance
pg.setConfigOptions(antialias=True)

logger = logging.getLogger("anchor")


class ClusterLegendItem(pg.ItemSample):
    def mouseClickEvent(self, event):
        event.ignore()


class ClusterLegend(pg.LegendItem):
    changeCluster = QtCore.Signal(object)

    def mouseClickEvent(self, event):
        """Use the mouseClick event to toggle the visibility of the plotItem"""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            pos = event.pos()
            origin = self.pos()
            current_row_top = origin.y()
            index = -1
            for row in range(self.layout.rowCount()):
                item = self.layout.itemAt(row, 0)
                if item:
                    if current_row_top <= pos.y() <= current_row_top + item.height():
                        self.changeCluster.emit(index)
                        break
                    index += 1
                    current_row_top += item.height()

            # self.changeCluster.emit(self.item.)

        event.accept()

    def mouseDragEvent(self, ev):
        ev.ignore()


class ScatterPlot(pg.ScatterPlotItem):
    selectPoints = QtCore.Signal(object, object)

    def __init__(self, *args, **kwargs):
        super(ScatterPlot, self).__init__(*args, **kwargs)
        self.selection_area = pg.RectROI((0, 0), (10, 10))
        self.selection_area.hide()
        self.selection_area.setParentItem(self)
        self.distances = None

    def mouseDragEvent(self, ev):
        if ev.modifiers() in [
            QtCore.Qt.KeyboardModifier.ControlModifier,
            QtCore.Qt.KeyboardModifier.ShiftModifier,
        ] and ev.button() in [
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.MouseButton.MiddleButton,
        ]:
            ev.accept()
            if ev.isFinish():
                self.selection_area.hide()
            else:
                self.selection_area.show()

            pos = ev.pos()
            start_pos = ev.buttonDownPos()
            self.selection_area.setPos(start_pos)
            width = pos.x() - start_pos.x()
            height = pos.y() - start_pos.y()
            self.selection_area.setSize((width, height))
            x_series, y_series = self.getData()
            selected_indices = []
            right = max(pos.x(), start_pos.x())
            left = min(pos.x(), start_pos.x())
            bottom = min(pos.y(), start_pos.y())
            top = max(pos.y(), start_pos.y())
            for i, x in enumerate(x_series):
                y = y_series[i]
                if left <= x <= right and bottom <= y <= top:
                    selected_indices.append(i)
            self.selectPoints.emit(selected_indices, True)

    def mouseClickEvent(self, ev):
        if (
            ev.button() == QtCore.Qt.MouseButton.LeftButton
            or ev.button() == QtCore.Qt.MouseButton.RightButton
        ):
            pts = self.pointsAt(ev.pos())
            if len(pts) > 0:
                self.ptsClicked = pts
                ev.accept()
                if ev.modifiers() in [
                    QtCore.Qt.KeyboardModifier.ControlModifier,
                    QtCore.Qt.KeyboardModifier.ShiftModifier,
                ]:
                    self.selectPoints.emit({self.ptsClicked[0]._index}, False)
                else:
                    self.selectPoints.emit({self.ptsClicked[0]._index}, True)
                self.sigClicked.emit(self, self.ptsClicked, ev)
            else:
                ev.ignore()
        else:
            ev.ignore()

    def hoverEvent(self, ev):
        if self.opts["hoverable"]:
            old = self.data["hovered"]

            if ev.exit:
                new = np.zeros_like(self.data["hovered"])
            else:
                new = self._maskAt(ev.pos())

            if self._hasHoverStyle():
                self.data["sourceRect"][old ^ new] = 0
                self.data["hovered"] = new
                self.updateSpots()

            points = self.points()[new][-1:]
            # Show information about hovered points in a tool tip

            self.sigHovered.emit(self, points, ev)


class UtteranceClusterView(pg.PlotWidget):
    utteranceRequested = QtCore.Signal(object)
    plotAvailable = QtCore.Signal(object)
    selectionUpdated = QtCore.Signal()

    def __init__(self, *args):
        super().__init__(*args)
        self.settings = AnchorSettings()
        plot_theme = self.settings.plot_theme
        self.setBackground(plot_theme.background_color)
        self.corpus_model = None
        self.speaker_model: SpeakerModel = None
        self.selection_model: FileSelectionModel = None
        self.updated_indices = set()
        self.brushes = {-1: pg.mkBrush(0.5)}
        self.scatter_item = ScatterPlot()
        self.scatter_item.selectPoints.connect(self.update_selection)
        self.addItem(self.scatter_item)
        self.hideButtons()
        self.getPlotItem().setDefaultPadding(0)
        self.getPlotItem().hideAxis("left")
        self.getPlotItem().hideAxis("bottom")
        # self.getPlotItem().enableAutoRange()
        # self.getPlotItem().setMouseEnabled(False, False)

        self.getPlotItem().setMenuEnabled(False)
        self.scatter_item.sigClicked.connect(self.update_point)
        self.legend_item = ClusterLegend(
            offset=(10, 10),
            sampleType=ClusterLegendItem,
            brush=pg.mkBrush(self.settings.value(self.settings.PRIMARY_BASE_COLOR)),
            pen=pg.mkPen(self.settings.value(self.settings.MAIN_TEXT_COLOR)),
            labelTextColor=self.settings.value(self.settings.MAIN_TEXT_COLOR),
        )
        self.pen_colormap = pg.ColorMap(None, [0.0, 1.0])
        self.pens = []
        self.legend_item.changeCluster.connect(self.change_cluster)
        self.legend_item.setParentItem(self.getPlotItem())
        self.legend_item.setFont(self.settings.font)
        self.selected_indices = set()
        # self.addItem(self.legend_item)
        self.selected_pen = pg.mkPen(
            self.settings.value(self.settings.PRIMARY_LIGHT_COLOR), width=2
        )
        self.updated_pen = pg.mkPen(self.settings.value(self.settings.MAIN_TEXT_COLOR), width=2)
        self.hover_pen = pg.mkPen(self.settings.value(self.settings.ACCENT_LIGHT_COLOR), width=2)
        self.selection_timer = QtCore.QTimer()
        self.selection_timer.setInterval(300)
        self.selection_timer.timeout.connect(self.send_selection_update)
        self.brush_needs_update = False
        self.spk_name_to_id = {}

    def send_selection_update(self):
        self.selection_timer.stop()
        self.selectionUpdated.emit()

    def change_cluster(self, cluster_id):
        if not self.selected_indices:
            return
        if cluster_id >= 0:
            cluster_id = self.speaker_model.current_speakers[cluster_id]
        self.updated_indices.update(
            [
                x
                for x in self.selected_indices
                if self.speaker_model.utt2spk[self.speaker_model.utterance_ids[x]] != cluster_id
            ]
        )

        self.speaker_model.cluster_labels[np.array(list(self.selected_indices))] = cluster_id
        brushes = [
            self.brushes[x if x in self.speaker_model.current_speakers else -1]
            for x in self.speaker_model.cluster_labels
        ]
        self.scatter_item.setBrush(brushes)
        self.update_highlight()

    def set_models(
        self,
        corpus_model: CorpusModel,
        selection_model: FileSelectionModel,
        speaker_model: SpeakerModel,
    ):
        self.corpus_model = corpus_model
        self.selection_model = selection_model
        self.speaker_model = speaker_model
        self.speaker_model.clustered.connect(self.update_plot)
        self.speaker_model.mdsFinished.connect(self.update_plot)
        self.speaker_model.mdsAboutToChange.connect(self.update_plot)
        self.speaker_model.speakersChanged.connect(self.update_plot)

    def clear_plot(self):
        self.legend_item.clear()
        self.scatter_item.clear()
        self.getPlotItem().update()

    def update_point(self, sender, spots, ev: pg.GraphicsScene.mouseEvents.MouseClickEvent):
        spot = spots[0]
        index = spot._index
        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            utterance_id = int(self.speaker_model.utterance_ids[index])
            utterance = self.corpus_model.session.query(Utterance).get(utterance_id)
            if utterance is None:
                return
            self.selection_model.set_current_file(
                utterance.file_id,
                utterance.begin,
                utterance.end,
                utterance.id,
                utterance.speaker_id,
                force_update=True,
                single_utterance=False,
            )
        else:
            brush_indices = list(self.brushes.keys())
            current_cluster = self.speaker_model.cluster_labels[index]
            current_index = brush_indices.index(current_cluster)
            current_index += 1
            self.updated_indices.add(index)
            if current_index >= len(brush_indices):
                current_index = 0
            current_cluster = brush_indices[current_index]
            self.speaker_model.cluster_labels[index] = current_cluster
            spot.setBrush(self.brushes[current_cluster])
            self.selected_indices = set()
            self.update_highlight()
        ev.accept()

    def update_plot(self, reset=True):
        self.clear_plot()
        if self.speaker_model.mds is None or self.speaker_model.cluster_labels is None:
            return
        if len(self.speaker_model.cluster_labels) != self.speaker_model.mds.shape[0]:
            return
        self.selected_indices = set()
        self.updated_indices = set()
        self.spk_name_to_id = {}
        self.brushes = {-1: pg.mkBrush(0.5)}
        for i, s_id in enumerate(self.speaker_model.current_speakers):
            self.brushes[s_id] = pg.mkBrush(
                pg.intColor(i, len(self.speaker_model.current_speakers))
            )
        with self.speaker_model.corpus_model.corpus.session() as session:
            for k, v in self.brushes.items():
                if k < 0:
                    label = "Noise"
                else:
                    label = session.query(Speaker.name).filter(Speaker.id == k).first()[0]
                self.legend_item.addItem(pg.ScatterPlotItem(brush=v, name=label), label)
        brushes = [
            self.brushes[x if x in self.speaker_model.current_speakers else -1]
            for x in self.speaker_model.cluster_labels
        ]
        self.pens = [pg.mkPen(x, width=2) for x in self.speaker_model.distances]
        xmin, xmax = np.min(self.speaker_model.mds[:, 0]), np.max(self.speaker_model.mds[:, 0])
        ymin, ymax = np.min(self.speaker_model.mds[:, 1]), np.max(self.speaker_model.mds[:, 1])
        xrange = xmax - xmin
        yrange = ymax - ymin
        extra_padding_x = xrange * 0.05
        extra_padding_y = yrange * 0.05
        legend_padding = xrange * 0.25
        xrange += legend_padding
        if reset:
            self.getPlotItem().setLimits(
                xMin=xmin - legend_padding - extra_padding_x,
                xMax=xmax + extra_padding_x,
                yMin=ymin - extra_padding_y,
                yMax=ymax + extra_padding_y,
                maxXRange=xrange + 2 * extra_padding_x,
                maxYRange=yrange + 2 * extra_padding_y,
            )
            self.getPlotItem().setRange(
                xRange=[xmin - legend_padding - extra_padding_x, xmax + extra_padding_x],
                yRange=[ymin - extra_padding_y, ymax + extra_padding_y],
                update=False,
            )

        self.scatter_item.setData(
            pos=self.speaker_model.mds,
            size=10,
            brush=brushes,
            pen=self.pens,
            hoverPen=self.hover_pen,
            hoverable=True,
        )
        self.plotAvailable.emit(True)

    def highlight_cluster(self, cluster_id):
        self.selected_indices = set(np.where(self.speaker_model.cluster_labels == cluster_id)[0])
        self.update_highlight()

    def update_selection(self, selected_points, reset=True):
        if reset:
            new_selection = set(selected_points)
        else:
            new_selection = self.selected_indices.symmetric_difference(selected_points)
        if new_selection == self.selected_indices:
            return
        self.selected_indices = new_selection
        self.selection_timer.start()
        self.update_highlight()

    def update_highlight(self):
        if self.speaker_model.mds is None:
            return
        num_utterances = self.speaker_model.mds.shape[0]
        pens = []
        for i in range(num_utterances):
            if i in self.selected_indices:
                pens.append(self.selected_pen)
            elif i in self.updated_indices:
                pens.append(self.updated_pen)
            else:
                pens.append(self.pens[i])
        self.scatter_item.setPen(pens)


class TimeAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        strings = super().tickStrings(values, scale, spacing)
        strings = [x.replace("-", "") for x in strings]
        return strings


class AudioPlotItem(pg.PlotItem):
    def __init__(self, top_point, bottom_point):
        super().__init__(axisItems={"bottom": TimeAxis("bottom")})
        self.settings = AnchorSettings()
        self.plot_theme = self.settings.plot_theme
        self.setDefaultPadding(0)
        self.setClipToView(True)

        self.getAxis("bottom").setPen(self.plot_theme.break_line_color)
        self.getAxis("bottom").setTextPen(self.plot_theme.break_line_color)
        self.getAxis("bottom").setTickFont(self.settings.small_font)
        rect = QtCore.QRectF()
        rect.setTop(top_point)
        rect.setBottom(bottom_point)
        rect.setLeft(0)
        rect.setRight(10)
        rect = rect.normalized()
        self.setRange(rect=rect)
        self.hideAxis("left")
        self.setMouseEnabled(False, False)

        self.setMenuEnabled(False)
        self.hideButtons()


class SpeakerTierItem(pg.PlotItem):
    def __init__(self, top_point, bottom_point):
        super().__init__()
        self.settings = AnchorSettings()
        self.setDefaultPadding(0)
        self.setClipToView(True)
        self.hideAxis("left")
        self.hideAxis("bottom")
        rect = QtCore.QRectF()
        rect.setTop(top_point)
        rect.setBottom(bottom_point)
        rect.setLeft(0)
        rect.setRight(10)
        rect = rect.normalized()
        self.setRange(rect=rect)
        self.setMouseEnabled(False, False)

        self.setMenuEnabled(False)
        self.hideButtons()

    def contextMenuEvent(self, event: QtWidgets.QGraphicsSceneContextMenuEvent):
        vb = self.getViewBox()
        item = self.items[0]
        x = vb.mapFromItemToView(self, event.pos()).x()
        begin = max(x - 0.5, 0)
        end = min(x + 0.5, item.selection_model.model().file.duration)
        for x in item.visible_utterances.values():
            if begin >= x.item_min and end <= x.item_max:
                event.accept()
                return
            if begin < x.item_max and begin > x.item_max:
                begin = x.item_max
            if end > x.item_min and end < x.item_min:
                end = x.item_min
                break
        if end - begin > 0.001:
            menu = QtWidgets.QMenu()

            a = QtGui.QAction(menu)
            a.setText("Create utterance")
            a.triggered.connect(functools.partial(item.create_utterance, begin=begin, end=end))
            menu.addAction(a)

            menu.setStyleSheet(item.settings.menu_style_sheet)
            menu.exec_(event.screenPos())


class UtteranceView(QtWidgets.QWidget):
    undoRequested = QtCore.Signal()
    redoRequested = QtCore.Signal()
    playRequested = QtCore.Signal()

    def __init__(self, *args):
        super().__init__(*args)
        self.settings = AnchorSettings()
        self.corpus_model: typing.Optional[CorpusModel] = None
        self.file_model: typing.Optional[FileUtterancesModel] = None
        self.dictionary_model: typing.Optional[DictionaryTableModel] = None
        self.selection_model: typing.Optional[FileSelectionModel] = None
        layout = QtWidgets.QVBoxLayout()
        self.bottom_point = 0
        self.top_point = 8
        self.height = self.top_point - self.bottom_point
        self.separator_point = (self.height / 2) + self.bottom_point

        # self.break_line.setZValue(30)
        self.audio_layout = pg.GraphicsLayoutWidget()
        self.audio_layout.viewport().setAttribute(
            QtCore.Qt.WidgetAttribute.WA_AcceptTouchEvents, False
        )
        self.audio_layout.centralWidget.layout.setContentsMargins(0, 0, 0, 0)
        self.audio_layout.centralWidget.layout.setSpacing(0)
        self.plot_theme = self.settings.plot_theme
        self.audio_layout.setBackground(self.plot_theme.background_color)
        self.audio_plot = AudioPlots(2, 1, 0)
        self.audio_plot_item = AudioPlotItem(2, 0)
        self.audio_plot_item.addItem(self.audio_plot)
        # self.audio_plot.setZValue(0)
        self.audio_layout.addItem(self.audio_plot_item)

        self.show_all_speakers = False
        self.show_transcription = True
        self.show_alignment = True
        self.speaker_tier_layout = pg.GraphicsLayoutWidget()
        self.speaker_tier_layout.viewport().setAttribute(
            QtCore.Qt.WidgetAttribute.WA_AcceptTouchEvents, False
        )
        self.speaker_tier_layout.setAspectLocked(False)
        self.speaker_tier_layout.centralWidget.layout.setContentsMargins(0, 0, 0, 0)
        self.speaker_tier_layout.centralWidget.layout.setSpacing(0)
        self.speaker_tier_layout.setBackground(self.plot_theme.background_color)
        self.speaker_tiers: dict[SpeakerTier] = {}
        self.speaker_tier_items = {}
        self.search_term = None
        self.default_speaker_id = None
        self.extra_tiers = {}
        self.tier_scroll_area = QtWidgets.QScrollArea()
        self.audio_scroll_area = QtWidgets.QScrollArea()
        self.audio_scroll_area.setContentsMargins(0, 0, 0, 0)
        self.tier_scroll_area.setWidget(self.speaker_tier_layout)
        self.tier_scroll_area.setWidgetResizable(True)
        self.tier_scroll_area.setContentsMargins(0, 0, 0, 0)
        self.tier_scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll_layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.audio_scroll_area)
        scroll_layout.addWidget(self.audio_layout)
        self.audio_scroll_area.setLayout(scroll_layout)
        layout.addWidget(self.tier_scroll_area)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        scroll_layout.setSpacing(0)
        self.setLayout(layout)

    def set_models(
        self,
        corpus_model: CorpusModel,
        file_model: FileUtterancesModel,
        selection_model: FileSelectionModel,
        dictionary_model: DictionaryTableModel,
    ):
        self.corpus_model = corpus_model
        self.file_model = file_model
        self.corpus_model.corpusLoaded.connect(self.set_extra_tiers)
        self.selection_model = selection_model
        self.dictionary_model = dictionary_model
        for t in self.speaker_tiers.values():
            t.set_models(corpus_model, selection_model, dictionary_model)
        self.audio_plot.set_models(self.selection_model)
        self.selection_model.viewChanged.connect(self.update_plot)
        self.selection_model.searchTermChanged.connect(self.set_search_term)
        # self.corpus_model.utteranceTextUpdated.connect(self.refresh_utterance_text)
        self.selection_model.resetView.connect(self.reset_plot)
        self.file_model.utterancesReady.connect(self.finalize_loading_utterances)
        self.selection_model.spectrogramReady.connect(self.finalize_loading_spectrogram)
        self.selection_model.pitchTrackReady.connect(self.finalize_loading_pitch_track)
        self.selection_model.waveformReady.connect(self.finalize_loading_auto_wave_form)
        self.selection_model.speakerRequested.connect(self.set_default_speaker)
        self.file_model.selectionRequested.connect(self.finalize_loading_utterances)
        self.file_model.speakersChanged.connect(self.finalize_loading_utterances)
        self.corpus_model.refreshTiers.connect(self.finalize_loading_utterances)

    def refresh_theme(self):
        self.audio_layout.setBackground(self.plot_theme.background_color)
        self.speaker_tier_layout.setBackground(self.plot_theme.background_color)
        self.audio_plot.wave_form.update_theme()
        self.audio_plot.spectrogram.update_theme()
        self.audio_plot.pitch_track.update_theme()
        self.audio_plot_item.getAxis("bottom").setPen(self.plot_theme.break_line_color)
        self.audio_plot_item.getAxis("bottom").setTextPen(self.plot_theme.break_line_color)

    def refresh(self):
        self.finalize_loading_utterances()
        self.finalize_loading_auto_wave_form()
        self.finalize_loading_pitch_track()
        self.finalize_loading_spectrogram()

    def finalize_loading_utterances(self):
        if self.file_model.file is None:
            return
        scroll_to = None
        self.speaker_tiers = {}
        self.speaker_tier_items = {}
        self.speaker_tier_layout.clear()
        available_speakers = {}
        num_visible_speakers = min(
            len(self.file_model.speakers), self.settings.value(self.settings.TIER_MAX_SPEAKERS)
        )
        speaker_tier_height = (self.separator_point - self.bottom_point) / num_visible_speakers
        for i, speaker_id in enumerate(self.file_model.speakers):
            speaker_name = self.corpus_model.get_speaker_name(speaker_id)
            top_point = i * speaker_tier_height
            bottom_point = top_point - speaker_tier_height
            tier = SpeakerTier(
                top_point,
                bottom_point,
                speaker_id,
                speaker_name,
                self.corpus_model,
                self.file_model,
                self.selection_model,
                self.dictionary_model,
                search_term=self.search_term,
            )
            tier.draggingLine.connect(self.audio_plot.update_drag_line)
            tier.lineDragFinished.connect(self.audio_plot.hide_drag_line)
            tier.receivedWheelEvent.connect(self.audio_plot.wheelEvent)
            tier.receivedGestureEvent.connect(self.audio_plot.gestureEvent)
            tier.set_extra_tiers(self.extra_tiers)
            tier.setZValue(30)
            available_speakers[speaker_name] = speaker_id
            self.speaker_tiers[speaker_id] = tier
        for i, (key, tier) in enumerate(self.speaker_tiers.items()):
            tier.set_available_speakers(available_speakers)
            tier.refresh()
            top_point = i * speaker_tier_height
            bottom_point = top_point - speaker_tier_height
            tier_item = SpeakerTierItem(top_point, bottom_point)
            tier_item.setRange(
                xRange=[self.selection_model.plot_min, self.selection_model.plot_max]
            )
            tier_item.addItem(tier)
            self.speaker_tier_items[key] = tier_item
            self.speaker_tier_layout.addItem(tier_item, i, 0)
            if tier.speaker_id == self.default_speaker_id:
                scroll_to = i
        row_height = self.tier_scroll_area.height()
        self.speaker_tier_layout.setFixedHeight(
            len(self.speaker_tiers) * row_height / num_visible_speakers
        )
        if len(self.file_model.speakers) > num_visible_speakers:
            self.tier_scroll_area.verticalScrollBar().setSingleStep(row_height)
            self.tier_scroll_area.verticalScrollBar().setPageStep(row_height)
            self.tier_scroll_area.verticalScrollBar().setMinimum(0)
            self.tier_scroll_area.verticalScrollBar().setMaximum(
                len(self.speaker_tiers) * row_height
            )
            self.tier_scroll_area.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn
            )
            self.audio_layout.centralWidget.layout.setContentsMargins(
                0, 0, self.settings.scroll_bar_height, 0
            )
            if scroll_to is not None:
                self.tier_scroll_area.verticalScrollBar().setValue(
                    scroll_to * self.tier_scroll_area.height()
                )
                self.default_speaker_id = None
        else:
            self.audio_layout.centralWidget.layout.setContentsMargins(0, 0, 0, 0)
            self.tier_scroll_area.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )

    def set_default_speaker(self, speaker_id):
        self.default_speaker_id = speaker_id

    def finalize_loading_spectrogram(self):
        self.audio_plot.spectrogram.hide()
        if self.selection_model.spectrogram is None:
            self.audio_plot.spectrogram.clear()
            return
        self.audio_plot.spectrogram.setData(
            self.selection_model.spectrogram,
            self.selection_model.selected_channel,
            self.selection_model.plot_min,
            self.selection_model.plot_max,
            self.selection_model.min_db,
            self.selection_model.max_db,
        )

    def finalize_loading_pitch_track(self):
        self.audio_plot.pitch_track.hide()
        self.audio_plot.pitch_track.clear()
        if self.selection_model.pitch_track_y is None:
            return
        self.audio_plot.pitch_track.setData(
            x=self.selection_model.pitch_track_x,
            y=self.selection_model.pitch_track_y,
            connect="finite",
        )
        self.audio_plot.pitch_track.set_range(
            self.settings.value(self.settings.PITCH_MIN_F0),
            self.settings.value(self.settings.PITCH_MAX_F0),
            self.selection_model.plot_max,
        )
        self.audio_plot.pitch_track.show()

    def finalize_loading_auto_wave_form(self):
        self.audio_plot.wave_form.hide()
        if self.selection_model.waveform_y is None:
            return
        self.audio_plot_item.setRange(
            xRange=[self.selection_model.plot_min, self.selection_model.plot_max]
        )
        self.audio_plot.update_plot()
        self.audio_plot.wave_form.setData(
            x=self.selection_model.waveform_x, y=self.selection_model.waveform_y
        )
        self.audio_plot.wave_form.show()

    def set_extra_tiers(self):
        self.extra_tiers = {}
        self.extra_tiers["Normalized text"] = "normalized_text"
        if self.corpus_model.has_transcriptions or self.corpus_model.transcription_acoustic_model is not None:

            self.extra_tiers["Transcription"] = "transcription_text"
        if self.corpus_model.has_alignments and "Words" not in self.extra_tiers:
            self.extra_tiers["Words"] = "word_intervals"
            self.extra_tiers["Phones"] = "phone_intervals"
        if (
            self.corpus_model.has_reference_alignments
            and "Reference phones" not in self.extra_tiers
        ):
            self.extra_tiers["Reference words"] = "reference_word_intervals"
            self.extra_tiers["Reference phones"] = "reference_phone_intervals"

    def set_search_term(self, term: TextFilterQuery = None):
        if term is None:
            term = self.corpus_model.text_filter
        if not term:
            return
        self.search_term = term
        for tier in self.speaker_tiers.values():
            tier.setSearchTerm(term)

    def reset_text_grid(self):
        for tier in self.speaker_tiers.values():
            tier.reset_tier()

    def refresh_text_grid(self):
        for tier in self.speaker_tiers.values():
            tier.refresh(reset_bounds=True)

    def draw_text_grid(self):
        scroll_to = None
        for i, (key, tier) in enumerate(self.speaker_tiers.items()):
            self.speaker_tier_items[key].hide()
            tier.refresh()
            if tier.speaker_id == self.default_speaker_id:
                scroll_to = i
                tier_height = self.speaker_tier_items[key].height()
            self.speaker_tier_items[key].setRange(
                xRange=[self.selection_model.plot_min, self.selection_model.plot_max]
            )
            self.speaker_tier_items[key].show()
        if scroll_to is not None:
            self.tier_scroll_area.verticalScrollBar().setValue(scroll_to * tier_height)
            self.default_speaker_id = None

    def update_show_speakers(self, state):
        self.show_all_speakers = state > 0
        self.update_plot()

    def reset_plot(self, *args):
        self.reset_text_grid()
        self.audio_plot.wave_form.clear()
        self.audio_plot.pitch_track.clear()
        self.audio_plot.spectrogram.clear()

    def update_plot(self, *args):
        if self.corpus_model.rowCount() == 0:
            return
        if self.file_model.file is None or self.selection_model.min_time is None:
            return
        self.audio_plot.update_plot()
        self.draw_text_grid()

    def update_selected_speaker(self, utterance, pos):
        if pos > self.separator_point:
            return
        new_speaker_id = None
        old_speaker_id = None
        for tier in self.speaker_tiers.values():
            if tier.speaker_id == utterance.speaker_id:
                old_speaker_id = tier.speaker_id
            if tier.top_point > pos > tier.bottom_point:
                new_speaker_id = tier.speaker_id
        if new_speaker_id is not None and new_speaker_id != old_speaker_id:
            self.file_model.update_utterance_speaker(utterance, new_speaker_id)


class UtteranceLine(pg.InfiniteLine):
    hoverChanged = QtCore.Signal(object)
    snapModeChanged = QtCore.Signal(object)

    def __init__(
        self, *args, movingPen=None, view_min=None, view_max=None, initial=True, **kwargs
    ):
        super(UtteranceLine, self).__init__(*args, **kwargs)
        self.movingPen = movingPen
        self.initial = initial
        self.view_min = view_min
        self.view_max = view_max
        self.bounding_width = 0.1
        self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)

    def hoverEvent(self, ev):
        if (
            (not ev.isExit())
            and self.movable
            and (
                (self.initial and self.pos().x() - self.mapToParent(ev.pos()).x() < 0)
                or (not self.initial and self.pos().x() - self.mapToParent(ev.pos()).x() > 0)
            )
            and ev.acceptDrags(QtCore.Qt.MouseButton.LeftButton)
        ):
            self.setMouseHover(True)
            self._boundingRect = None
            self.hoverChanged.emit(True)
        else:
            self.setMouseHover(False)
            self.hoverChanged.emit(False)
            self._boundingRect = None

    def mouseDragEvent(self, ev):
        if self.movable and ev.button() == QtCore.Qt.MouseButton.LeftButton:
            self.snapModeChanged.emit(ev.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier)
            if ev.isStart() and (
                (self.initial and self.pos().x() - self.mapToParent(ev.buttonDownPos()).x() < 0)
                or (
                    not self.initial
                    and self.pos().x() - self.mapToParent(ev.buttonDownPos()).x() > 0
                )
            ):
                self.moving = True
                self._boundingRect = None
                self.currentPen = self.movingPen
                self.cursorOffset = self.pos() - self.mapToParent(ev.buttonDownPos())
                self.startPosition = self.pos()
            ev.accept()

            if not self.moving:
                return
            p = self.cursorOffset + self.mapToParent(ev.pos())
            p.setY(self.startPosition.y())
            if p.x() > self.view_max:
                p.setX(self.view_max)
            if p.x() < self.view_min:
                p.setX(self.view_min)
            self.setPos(p)
            self.sigDragged.emit(self)
            if ev.isFinish():
                self.currentPen = self.pen
                self._boundingRect = None
                self._bounds = None
                self._lastViewSize = None
                self.moving = False
                self.sigPositionChangeFinished.emit(self)
                self.update()

    def _computeBoundingRect(self):
        # br = UIGraphicsItem.boundingRect(self)
        vr = self.viewRect()  # bounds of containing ViewBox mapped to local coords.
        if vr is None:
            return QtCore.QRectF()

        # add a 4-pixel radius around the line for mouse interaction.
        px = self.pixelLength(
            direction=pg.Point(1, 0), ortho=True
        )  # get pixel length orthogonal to the line
        if px is None:
            px = 0
        pw = max(self.pen.width() / 2, self.hoverPen.width() / 2)
        w = max(self.bounding_width, self._maxMarkerSize + pw) + 1
        w = w * px
        br = QtCore.QRectF(vr)
        if self.initial:
            br.setBottom(-w)
            br.setTop(0)
        else:
            br.setTop(w)
            br.setBottom(0)

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


class Menu(QtWidgets.QMenu):
    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        return super().mousePressEvent(e)

    def leaveEvent(self, e: QtCore.QEvent) -> None:
        self.hide()
        return super().leaveEvent(e)

    def hideEvent(self, e: QtGui.QHideEvent) -> None:
        return super().hideEvent(e)


class TextEdit(QtWidgets.QTextEdit):
    lostFocus = QtCore.Signal()
    gainedFocus = QtCore.Signal()
    menuRequested = QtCore.Signal(object, object)
    doubleClicked = QtCore.Signal()

    def __init__(self, dictionary_model, speaker_id, *args):
        super().__init__(*args)
        self.settings = AnchorSettings()
        self.dictionary_model: DictionaryTableModel = dictionary_model
        self.speaker_id = speaker_id
        self.setCursor(QtCore.Qt.CursorShape.IBeamCursor)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)

        self.customContextMenuRequested.connect(self.generate_context_menu)

        self.setAcceptRichText(False)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.verticalScrollBar().setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWordWrapMode(QtGui.QTextOption.WrapMode.WordWrap)

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(e)

    def dragMoveEvent(self, e: QtGui.QDragMoveEvent) -> None:
        e.ignore()

    def dragEnterEvent(self, e: QtGui.QDragMoveEvent) -> None:
        e.ignore()

    def dragLeaveEvent(self, e: QtGui.QDragMoveEvent) -> None:
        e.ignore()

    def focusOutEvent(self, e: QtGui.QFocusEvent) -> None:
        self.lostFocus.emit()
        return super().focusOutEvent(e)

    def focusInEvent(self, e: QtGui.QFocusEvent) -> None:
        self.gainedFocus.emit()
        return super().focusInEvent(e)

    def generate_context_menu(self, location):
        cursor = self.cursorForPosition(location)
        cursor.select(QtGui.QTextCursor.SelectionType.WordUnderCursor)
        word = cursor.selectedText()
        self.menuRequested.emit(word, self.mapToGlobal(location))


class UtterancePGTextItem(pg.TextItem):
    def __init__(
        self,
        begin: float,
        end: float,
        text: str,
        selection_model: FileSelectionModel,
        top_point=None,
        bottom_point=None,
        per_tier_range=None,
        anchor=(0, 0),
        border=None,
        fill=None,
        dictionary_model: Optional[DictionaryTableModel] = None,
        speaker_id: int = 0,
        editable: bool = True,
    ):
        self.anchor = pg.Point(anchor)
        self.rotateAxis = None
        if selection_model.settings.right_to_left:
            begin, end = -end, -begin
        self.begin = begin
        self.end = end
        self.selection_model = selection_model
        self.angle = 0
        self.dictionary_model = dictionary_model
        self.speaker_id = speaker_id
        pg.GraphicsObject.__init__(self)
        self.editable = editable
        self.text_edit = TextEdit(dictionary_model, speaker_id)
        self.text_edit.cursorPositionChanged.connect(self.update)

        self.textItem = QtWidgets.QGraphicsProxyWidget(self)
        self.textItem.setWidget(self.text_edit)
        self.text_edit.setPlainText(text)
        self._lastTransform = None
        self._lastScene = None
        self._bounds = QtCore.QRectF()
        self.fill = pg.mkBrush(fill)
        self.border = pg.mkPen(border)
        self._cached_pixel_size = None
        self.cached_duration = None
        self.top_point = top_point
        self.bottom_point = bottom_point
        self.per_tier_range = per_tier_range
        self.view_min = self.selection_model.plot_min
        self.view_max = self.selection_model.plot_max
        self.selection_model.viewChanged.connect(self.update_view_times)

    def update_times(self, begin, end):
        self.begin = begin
        self.end = end
        if self.end <= self.view_min or self.begin >= self.view_max:
            return
        if (
            self.view_min <= self.begin < self.view_max
            or self.view_max >= self.end > self.view_min
            or (self.begin <= self.view_min and self.end >= self.view_max)
        ):
            self.update_pos()

    def update_view_times(self, begin, end):
        self.view_min = begin
        self.view_max = end
        if self.end <= self.view_min or self.begin >= self.view_max:
            return
        if (
            self.view_min <= self.begin < self.view_max
            or self.view_max >= self.end > self.view_min
            or (self.begin <= self.view_min and self.end >= self.view_max)
        ):
            self.update_pos()

    def update_pos(self):
        visible_begin = max(self.begin, self.view_min)
        visible_end = min(self.end, self.view_max)
        duration = visible_end - visible_begin
        vb = self.getViewBox()
        if vb is None:
            return
        self._cached_pixel_size = vb.viewPixelSize()
        x_margin_px = 25
        y_margin_top_px = 25
        y_margin_bottom_px = 10
        bounding_pixel_width = duration / self._cached_pixel_size[0]
        width = max(int(bounding_pixel_width - (2 * x_margin_px)), 0)
        bounding_pixel_height = abs(self.per_tier_range) / self._cached_pixel_size[1]
        y_margin = y_margin_top_px * self._cached_pixel_size[1]
        x_margin = x_margin_px * self._cached_pixel_size[0]
        height = max(int(bounding_pixel_height - ((y_margin_top_px + y_margin_bottom_px))), 0)
        self.setPos(visible_begin + x_margin, self.top_point - y_margin)
        self.textItem.setGeometry(0, 0, width, height)
        self.text_edit.setFixedWidth(width)
        self.text_edit.setFixedHeight(height)

    def boundingRect(self):
        br = QtCore.QRectF()  # bounds of containing ViewBox mapped to local coords.
        if self._cached_pixel_size is None:
            self.update_pos()
        visible_begin = max(self.begin, self.view_min)
        visible_end = min(self.end, self.view_max)

        br.setLeft(visible_begin)
        br.setRight(visible_end)

        br.setTop(self.top_point)
        br.setBottom(self.bottom_point)
        return br


class PhonePGTextItem(pg.TextItem):
    def __init__(
        self,
        text: str = "",
        color=None,
        font=None,
        html=None,
        anchor=(0, 0),
        border=None,
        fill=None,
        phones=None,
    ):
        from anchor.widgets import PronunciationInput

        self.anchor = pg.Point(anchor)
        self.rotateAxis = None
        self.angle = 0
        if phones is None:
            phones = []
        pg.GraphicsObject.__init__(self)
        self.text_edit = PronunciationInput(phones)

        self.textItem = QtWidgets.QGraphicsProxyWidget(self)
        self.textItem.setWidget(self.text_edit)
        self._lastTransform = None
        self._lastScene = None
        self._bounds = QtCore.QRectF()
        self.text_edit.setText(text)
        self.fill = pg.mkBrush(fill)
        self.border = pg.mkPen(border)

    def setPlainText(self, text):
        """
        Set the plain text to be rendered by this item.

        See QtGui.QGraphicsTextItem.setPlainText().
        """
        if text != self.toPlainText():
            self.text_edit.setText(text)
            self.updateTextPos()

    def toPlainText(self):
        return self.text_edit.text()


class TranscriberErrorHighlighter(QtGui.QSyntaxHighlighter):
    WORDS = r"\S+"

    def __init__(self, *args):
        super().__init__(*args)
        self.alignment = None
        self.settings = AnchorSettings()
        self.plot_theme = self.settings.plot_theme

        self.keyword_color = self.plot_theme.error_color
        self.keyword_text_color = self.plot_theme.error_text_color
        self.highlight_format = QtGui.QTextCharFormat()
        self.highlight_format.setBackground(self.keyword_color)
        self.highlight_format.setForeground(self.keyword_text_color)
        self.search_term = None

    def setSearchTerm(self, search_term: TextFilterQuery):
        if search_term != self.search_term:
            self.search_term = search_term
            self.rehighlight()

    def set_alignment(self, alignment):
        if self.alignment is None or [(x.label, y.label) for x, y in alignment] != [(x.label, y.label) for x, y in self.alignment]:
            self.alignment = alignment
            self.rehighlight()

    def highlightBlock(self, text):
        if self.alignment:
            current_align_ind = 0
            for word_object in re.finditer(self.WORDS, text.lower()):
                sa, sb = self.alignment[current_align_ind]
                if sb.label == "-":
                    start = word_object.start() - 1
                    if start < 0:
                        start = 0
                    count = 1
                    self.setFormat(
                        start,
                        count,
                        self.highlight_format,
                    )
                    while sb.label != word_object.group():
                        current_align_ind += 1
                        sa, sb = self.alignment[current_align_ind]
                if sb.label == word_object.group():
                    if sb.label != sa.label:
                        self.setFormat(
                            word_object.start(),
                            word_object.end() - word_object.start(),
                            self.highlight_format,
                        )
                    current_align_ind += 1
            if current_align_ind < len(self.alignment):
                self.setFormat(
                    len(text) - 1,
                    1,
                    self.highlight_format,
                )

        if self.search_term:
            if not self.search_term.case_sensitive:
                text = text.lower()
            filter_regex = self.search_term.generate_expression()
            for word_object in re.finditer(filter_regex, text):
                for i in range(word_object.start(), word_object.end()):
                    f = self.format(i)
                    f.setFontWeight(QtGui.QFont.Weight.Bold)
                    f.setBackground(QtGui.QColor(self.plot_theme.break_line_color))
                    f.setForeground(QtGui.QColor(self.plot_theme.background_color))
                    self.setFormat(i, 1, f)


class TextItem(pg.TextItem):
    def __init__(
        self, text="", color=(200, 200, 200), html=None, anchor=(0, 0), border=None, fill=None
    ):
        """
        ==============  =================================================================================
        **Arguments:**
        *text*          The text to display
        *color*         The color of the text (any format accepted by pg.mkColor)
        *html*          If specified, this overrides both *text* and *color*
        *anchor*        A QPointF or (x,y) sequence indicating what region of the text box will
                        be anchored to the item's position. A value of (0,0) sets the upper-left corner
                        of the text box to be at the position specified by setPos(), while a value of (1,1)
                        sets the lower-right corner.
        *border*        A pen to use when drawing the border
        *fill*          A brush to use when filling within the border
        *angle*         Angle in degrees to rotate text. Default is 0; text will be displayed upright.
        *rotateAxis*    If None, then a text angle of 0 always points along the +x axis of the scene.
                        If a QPointF or (x,y) sequence is given, then it represents a vector direction
                        in the parent's coordinate system that the 0-degree line will be aligned to. This
                        Allows text to follow both the position and orientation of its parent while still
                        discarding any scale and shear factors.
        ==============  =================================================================================


        The effects of the `rotateAxis` and `angle` arguments are added independently. So for example:

          * rotateAxis=None, angle=0 -> normal horizontal text
          * rotateAxis=None, angle=90 -> normal vertical text
          * rotateAxis=(1, 0), angle=0 -> text aligned with x axis of its parent
          * rotateAxis=(0, 1), angle=0 -> text aligned with y axis of its parent
          * rotateAxis=(1, 0), angle=90 -> text orthogonal to x axis of its parent
        """

        self.anchor = pg.Point(anchor)
        self.rotateAxis = None
        # self.angle = 0
        pg.GraphicsObject.__init__(self)
        self.textItem = QtWidgets.QGraphicsTextItem(text)
        self.textItem.setParentItem(self)
        self._lastTransform = None
        self._lastScene = None
        self.angle = 0
        self._bounds = QtCore.QRectF()
        self.setText(text, color)
        self.fill = pg.mkBrush(fill)
        self.border = pg.mkPen(border)


class IntervalTextRegion(pg.GraphicsObject):
    audioSelected = QtCore.Signal(object, object)

    def __init__(
        self,
        interval,
        color,
        top_point,
        height,
        font=None,
        border=None,
        background_brush=None,
        hover_brush=None,
        selected_brush=None,
        dictionary_model=None,
        speaker_id=None,
    ):
        self.background_brush = background_brush
        self.hover_brush = hover_brush
        self.selected_brush = selected_brush
        self.border = border
        self.dictionary_model = dictionary_model
        self.speaker_id = speaker_id
        super().__init__()
        text = interval.label
        self.text_item = TextItem(text, color=color, anchor=(0.5, 0.5))
        self.text_item.setParentItem(self)

        self.picture = QtGui.QPicture()
        self.interval = interval
        self.top_point = top_point
        self.left_point = interval.begin
        self._bounds = None
        self.width = interval.end - interval.begin
        self.height = height
        self.mouseHovering = False
        self.selected = False
        self.currentBrush = self.background_brush
        self.text_item.setPos(
            (self.interval.begin + self.interval.end) / 2, self.top_point - (self.height / 2)
        )
        self.begin_line = pg.InfiniteLine()
        self.rect = QtCore.QRectF(
            left=self.interval.begin,
            top=self.top_point,
            width=self.interval.end - self.interval.begin,
            height=self.height,
        )
        self.rect.setTop(self.top_point)
        self.rect.setBottom(self.top_point - self.height)
        self._generate_picture()

    def setSelected(self, selected):
        if selected:
            new_brush = self.selected_brush
        else:
            new_brush = self.background_brush
        if new_brush != self.currentBrush:
            self.currentBrush = new_brush
            self._generate_picture()

    def _generate_picture(self):
        painter = QtGui.QPainter(self.picture)
        painter.setPen(self.border)
        painter.setBrush(self.currentBrush)
        painter.drawRect(self.rect)
        painter.end()

    def mouseClickEvent(self, ev):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return
        self.audioSelected.emit(self.interval.begin, self.interval.end)
        ev.accept()

    def boundingRect(self):
        br = QtCore.QRectF(self.picture.boundingRect())
        return br

    def paint(self, painter: QtGui.QPainter, *args):
        painter.drawPicture(0, 0, self.picture)


class TextAttributeRegion(pg.GraphicsObject):
    def __init__(
        self,
        parent,
        begin: float,
        end: float,
        text: str,
        top_point,
        height,
        selection_model: FileSelectionModel,
        dictionary_model=None,
        speaker_id=None,
        plot_theme=None,
    ):
        super().__init__()
        self.begin = begin
        self.end = end
        self.text = text
        self.plot_theme = plot_theme
        self.settings = AnchorSettings()
        if self.plot_theme is None:
            self.plot_theme = self.settings.plot_theme
        self.dictionary_model = dictionary_model
        self.speaker_id = speaker_id
        self.selection_model = selection_model
        self.top_point = top_point
        self.left_point = begin
        self._bounds = None
        self.width = end - begin
        self.height = height
        self.bottom_point = self.top_point - self.height
        self.setParentItem(parent)

        self.text_item = UtterancePGTextItem(
            self.begin,
            self.end,
            self.text,
            self.selection_model,
            anchor=(0, 0),
            top_point=self.top_point,
            bottom_point=self.bottom_point,
            per_tier_range=self.height,
            dictionary_model=self.dictionary_model,
            speaker_id=self.speaker_id,
            border=pg.mkPen(self.parentItem().settings.accent_light_color),
        )
        self.text_item.setParentItem(self)
        self.text_edit = self.text_item.text_edit
        self.text_edit.setReadOnly(True)
        self.text_edit.setViewportMargins(
            self.parentItem().text_margin_pixels,
            self.parentItem().text_margin_pixels,
            self.parentItem().text_margin_pixels,
            self.parentItem().text_margin_pixels,
        )
        self.text_edit.setStyleSheet(self.parentItem().settings.interval_style_sheet)

        self.selected = False
        self.currentBrush = self.parentItem().currentBrush
        self.text_item.setPos((self.begin + self.end) / 2, self.top_point - (self.height / 2))
        self._cached_pixel_size = None
        self.cached_bounds = None

    def boundingRect(self):
        visible_begin = max(self.begin, self.selection_model.plot_min)
        visible_end = min(self.end, self.selection_model.plot_max)
        br = QtCore.QRectF(
            visible_begin,
            self.bottom_point,
            visible_end - visible_begin,
            abs(self.top_point - self.bottom_point),
        )
        return br

    def paint(self, painter, option, widget=...):
        return


class TranscriberTextRegion(TextAttributeRegion):
    transcribeRequested = QtCore.Signal(object)

    def __init__(
        self,
        parent,
        item,
        top_point,
        height,
        selection_model: CorpusSelectionModel,
        dictionary_model=None,
        speaker_id=None,
        alignment=None,
        search_term=None,
        plot_theme=None,
    ):
        super().__init__(
            parent,
            item.begin,
            item.end,
            item.transcription_text,
            top_point,
            height,
            selection_model,
            dictionary_model,
            speaker_id,
            plot_theme,
        )
        self.item = item
        self.text_edit.setPlaceholderText("Double click to transcribe...")
        self.text_edit.doubleClicked.connect(self.transcribe_utterance)
        self.highlighter = TranscriberErrorHighlighter(self.text_edit.document())
        if alignment is not None:
            self.highlighter.set_alignment(alignment)
        if search_term:
            self.highlighter.setSearchTerm(search_term)

    def transcribe_utterance(self):
        if not self.text_edit.toPlainText():
            self.transcribeRequested.emit(self.item.id)

    def mouseDoubleClickEvent(self, event):
        self.transcribe_utterance()
        super().mouseDoubleClickEvent(event)


class NormalizedTextRegion(TextAttributeRegion):
    def __init__(
        self,
        parent,
        begin: float,
        end: float,
        text: str,
        top_point,
        height,
        selection_model: CorpusSelectionModel,
        dictionary_model=None,
        search_term=None,
        speaker_id=None,
        plot_theme=None,
    ):
        super().__init__(
            parent,
            begin,
            end,
            text,
            top_point,
            height,
            selection_model,
            dictionary_model,
            speaker_id,
            plot_theme,
        )

        self.highlighter = Highlighter(self.text_item.text_edit.document())
        self.highlighter.set_models(dictionary_model)
        self.highlighter.set_speaker(speaker_id)
        if search_term:
            self.highlighter.setSearchTerm(search_term)

    def boundingRect(self):
        br = super().boundingRect()
        return br


class Highlighter(QtGui.QSyntaxHighlighter):
    WORDS = rf"[^\s{''.join(DEFAULT_WORD_BREAK_MARKERS)+''.join(DEFAULT_PUNCTUATION)}]+"

    def __init__(self, *args):
        super(Highlighter, self).__init__(*args)
        self.settings = AnchorSettings()
        self.speaker_id = None
        self.dictionary_model: Optional[DictionaryTableModel] = None
        self.search_term: Optional[TextFilterQuery] = None
        self.spellcheck_format = QtGui.QTextCharFormat()
        self.spellcheck_format.setFontWeight(QtGui.QFont.Weight.ExtraBold)
        self.spellcheck_format.setUnderlineColor(self.settings.error_color)
        self.spellcheck_format.setUnderlineStyle(
            QtGui.QTextCharFormat.UnderlineStyle.SingleUnderline
        )

    def set_speaker(self, speaker_id: int):
        self.speaker_id = speaker_id

    def set_models(self, dictionary_model: DictionaryTableModel):
        self.dictionary_model = dictionary_model

    def setSearchTerm(self, search_term: TextFilterQuery):
        if search_term != self.search_term:
            self.search_term = search_term
            self.rehighlight()

    def highlightBlock(self, text):
        self.settings.sync()
        self.spellcheck_format.setUnderlineColor(self.settings.error_color)
        words = self.WORDS
        try:
            tokenizers = self.dictionary_model.corpus_model.corpus.get_tokenizers()
            dictionary_id = self.dictionary_model.corpus_model.corpus.get_dict_id_for_speaker(
                self.speaker_id
            )
            if isinstance(tokenizers, dict) and dictionary_id is not None:
                tokenizer = self.dictionary_model.corpus_model.corpus.get_tokenizer(dictionary_id)
            else:
                tokenizer = tokenizers
            if isinstance(tokenizer, SimpleTokenizer):
                extra_symbols = "".join(tokenizer.punctuation) + "".join(
                    tokenizer.word_break_markers
                )
                words = rf"[^\s{extra_symbols}]+"
        except Exception:
            pass
        if self.dictionary_model is not None and self.dictionary_model.word_sets:
            for word_object in re.finditer(words, text):
                if not self.dictionary_model.check_word(word_object.group(), self.speaker_id):
                    self.setFormat(
                        word_object.start(),
                        word_object.end() - word_object.start(),
                        self.spellcheck_format,
                    )
        if self.search_term:
            if not self.search_term.case_sensitive:
                text = text.lower()
            filter_regex = self.search_term.generate_expression()
            for word_object in re.finditer(filter_regex, text):
                for i in range(word_object.start(), word_object.end()):
                    f = self.format(i)
                    f.setFontWeight(QtGui.QFont.Weight.Bold)
                    f.setBackground(QtGui.QColor(self.settings.accent_base_color))
                    f.setForeground(QtGui.QColor(self.settings.primary_very_dark_color))
                    self.setFormat(i, 1, f)


class MfaRegion(pg.LinearRegionItem):
    textEdited = QtCore.Signal(object, object)
    undoRequested = QtCore.Signal()
    redoRequested = QtCore.Signal()
    playRequested = QtCore.Signal()
    selectRequested = QtCore.Signal(object, object, object)
    audioSelected = QtCore.Signal(object, object)
    viewRequested = QtCore.Signal(object, object)

    def __init__(
        self,
        item,
        corpus_model: CorpusModel,
        file_model: FileUtterancesModel,
        dictionary_model: typing.Optional[DictionaryTableModel],
        selection_model: FileSelectionModel,
        bottom_point: float = 0,
        top_point: float = 1,
    ):
        pg.GraphicsObject.__init__(self)
        self.item = item

        self.settings = AnchorSettings()
        self.plot_theme = self.settings.plot_theme

        self.item_min = self.item.begin
        self.item_max = self.item.end
        if selection_model.settings.right_to_left:
            self.item_min, self.item_max = -self.item_max, -self.item_min
        self.corpus_model = corpus_model
        self.file_model = file_model
        self.dictionary_model = dictionary_model
        self.selection_model = selection_model
        self.bottom_point = bottom_point
        self.top_point = top_point
        self.span = (self.bottom_point, self.top_point)
        self.text_margin_pixels = 2
        self.height = abs(self.top_point - self.bottom_point)

        self.interval_background_color = self.plot_theme.interval_background_color
        self.hover_line_color = self.plot_theme.hover_line_color
        self.moving_line_color = self.plot_theme.moving_line_color

        self.break_line_color = self.plot_theme.break_line_color
        self.text_color = self.plot_theme.text_color
        self.selected_interval_color = self.plot_theme.selected_interval_color
        self.plot_text_font = self.settings.big_font
        self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
        self.pen = pg.mkPen(self.break_line_color, width=3)
        self.pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
        self.border_pen = pg.mkPen(self.break_line_color, width=2)
        self.border_pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)

        if self.selection_model.checkSelected(getattr(self.item, "id", None)):
            self.background_brush = pg.mkBrush(self.selected_interval_color)
        else:
            # self.interval_background_color.setAlpha(0)
            self.background_brush = pg.mkBrush(self.interval_background_color)

        self.hoverPen = pg.mkPen(self.hover_line_color, width=3)
        self.movingPen = pg.mkPen(
            self.moving_line_color, width=3, style=QtCore.Qt.PenStyle.DashLine
        )
        self.orientation = "vertical"
        self.bounds = QtCore.QRectF()
        self.blockLineSignal = False
        self.moving = False
        self.mouseHovering = False
        self.swapMode = "sort"
        self.clipItem = None
        self._boundingRectCache = None
        self.movable = False
        self.cached_visible_duration = None
        self.cached_view = None
        self.currentBrush = self.background_brush
        self.picture = QtGui.QPicture()
        self.rect = QtCore.QRectF(
            left=self.item_min,
            top=self.top_point,
            width=self.item_max - self.item_min,
            height=self.height,
        )
        self.rect.setTop(self.top_point)
        self.rect.setLeft(self.item_min)
        self.rect.setRight(self.item_max)
        self.rect.setBottom(self.bottom_point)
        self._generate_picture()
        self.sigRegionChanged.connect(self.update_bounds)
        self.sigRegionChangeFinished.connect(self.update_bounds)
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)

    def update_bounds(self):
        beg, end = self.getRegion()
        self.rect.setLeft(beg)
        self.rect.setRight(end)
        self._generate_picture()

    def _generate_picture(self):
        if self.selection_model is None:
            return
        painter = QtGui.QPainter(self.picture)
        painter.setPen(self.border_pen)
        painter.setBrush(self.currentBrush)
        painter.drawRect(self.rect)
        painter.end()

    def paint(self, painter, *args):
        painter.drawPicture(0, 0, self.picture)

    def mouseClickEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return
        self.audioSelected.emit(self.item_min, self.item_max)
        ev.accept()

    def mouseDoubleClickEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return
        self.audioSelected.emit(self.item_min, self.item_max)
        padding = (self.item_max - self.item_min) / 2
        self.viewRequested.emit(self.item_min - padding, self.item_max + padding)
        ev.accept()

    def setSelected(self, selected: bool):
        if selected:
            new_brush = pg.mkBrush(self.selected_interval_color)
        else:
            new_brush = pg.mkBrush(self.interval_background_color)
        if new_brush != self.currentBrush:
            self.currentBrush = new_brush
            self._generate_picture()
        self.update()

    def setMouseHover(self, hover: bool):
        # Inform the item that the mouse is(not) hovering over it
        if self.mouseHovering == hover:
            return
        self.mouseHovering = hover
        self.popup(hover)
        self.update()

    def select_self(self, deselect=False, reset=True):
        self.selected = True
        if self.selected and not deselect and not reset:
            return

    def boundingRect(self):
        try:
            visible_begin = max(self.item_min, self.selection_model.plot_min)
            visible_end = min(self.item_max, self.selection_model.plot_max)
        except TypeError:
            visible_begin = self.item_min
            visible_end = self.item_max
        br = QtCore.QRectF(self.picture.boundingRect())
        br.setLeft(visible_begin)
        br.setRight(visible_end)

        br.setTop(self.top_point)
        br.setBottom(self.bottom_point + 0.01)
        br = br.normalized()

        if self._boundingRectCache != br:
            self._boundingRectCache = br
            self.prepareGeometryChange()
        return br


class IntervalLine(pg.InfiniteLine):
    hoverChanged = QtCore.Signal(object, object)

    def __init__(
        self,
        pos,
        index=None,
        index_count=None,
        pen=None,
        movingPen=None,
        hoverPen=None,
        bottom_point: float = 0,
        top_point: float = 1,
        bound_min=None,
        bound_max=None,
        movable=True,
    ):
        super().__init__(
            pos,
            angle=90,
            span=(bottom_point, top_point),
            pen=pen,
            hoverPen=hoverPen,
            movable=movable,
        )
        self.index = index
        self.index_count = index_count
        self.initial = index <= 0
        self.final = index >= index_count - 1
        self.bound_min = bound_min
        self.bound_max = bound_max
        self.movingPen = movingPen
        self.bounding_width = 0.1
        if self.movable:
            self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)

    def setMouseHover(self, hover):
        if hover and self.movable:
            self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        elif self.movable:
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        self.hoverChanged.emit(hover, self)
        super().setMouseHover(hover)

    def _computeBoundingRect(self):
        # br = UIGraphicsItem.boundingRect(self)
        vr = self.viewRect()  # bounds of containing ViewBox mapped to local coords.
        if vr is None:
            return QtCore.QRectF()

        # add a 4-pixel radius around the line for mouse interaction.
        px = self.pixelLength(
            direction=pg.Point(1, 0), ortho=True
        )  # get pixel length orthogonal to the line
        if px is None:
            px = 0
        pw = max(self.pen.width() / 2, self.hoverPen.width() / 2)
        w = max(self.bounding_width, self._maxMarkerSize + pw) + 5
        w = w * px
        br = QtCore.QRectF(vr)
        br.setBottom(-w)
        br.setTop(w)

        left = self.span[0]
        right = self.span[1]

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

    def hoverEvent(self, ev):
        if (
            (not ev.isExit())
            and self.movable
            # and (
            #    (self.initial and self.pos().x() - self.mapToParent(ev.pos()).x() < 0)
            #    or (not self.initial and self.pos().x() - self.mapToParent(ev.pos()).x() > 0)
            # )
            and ev.acceptDrags(QtCore.Qt.MouseButton.LeftButton)
        ):
            self.setMouseHover(True)
        else:
            self.setMouseHover(False)

    def mouseDragEvent(self, ev):
        if self.movable and ev.button() == QtCore.Qt.MouseButton.LeftButton:
            if ev.isStart():
                self.moving = True
                self._boundingRect = None
                self.currentPen = self.movingPen
                self.cursorOffset = self.pos() - self.mapToParent(ev.buttonDownPos())
                self.startPosition = self.pos()
            ev.accept()

            if not self.moving:
                return
            p = self.cursorOffset + self.mapToParent(ev.pos())
            p.setY(self.startPosition.y())
            if p.x() >= self.bound_max - 0.01:
                p.setX(self.bound_max - 0.01)
            if p.x() <= self.bound_min + 0.01:
                p.setX(self.bound_min + 0.01)
            self.setPos(p)
            self.sigDragged.emit(self)
            if ev.isFinish():
                self.currentPen = self.pen
                self.moving = False
                self.sigPositionChangeFinished.emit(self)


class IntervalTier(pg.GraphicsObject):
    highlightRequested = QtCore.Signal(object)

    def __init__(
        self,
        parent: UtteranceRegion,
        utterance: Utterance,
        intervals: typing.List[typing.Union[PhoneInterval, WordInterval]],
        selection_model: FileSelectionModel,
        top_point: float,
        bottom_point: float,
        lookup: typing.Optional[str] = None,
        movable: bool = False,
    ):
        super().__init__()
        self.setParentItem(parent)
        self.intervals = intervals
        self.lookup = lookup
        self.settings = AnchorSettings()
        self.plot_theme = self.settings.plot_theme
        self.anchor = pg.Point((0.5, 0.5))
        self.plot_text_font = self.settings.font
        self.movable = movable

        self.background_color = self.plot_theme.background_color
        self.hover_line_color = self.plot_theme.hover_line_color
        self.moving_line_color = self.plot_theme.moving_line_color
        self.break_line_color = self.plot_theme.break_line_color
        self.text_color = self.plot_theme.text_color
        self.selected_interval_color = self.plot_theme.selected_interval_color
        self.highlight_interval_color = self.plot_theme.break_line_color
        self.highlight_text_color = self.plot_theme.background_color

        self.top_point = top_point
        self.bottom_point = bottom_point
        self.selection_model = selection_model
        self.utterance = utterance
        self.lines = []
        self.selected = []

        self._boundingRectCache = None
        self._cached_pixel_size = None

        self.hoverPen = pg.mkPen(self.hover_line_color, width=3)
        self.movingPen = pg.mkPen(
            self.moving_line_color, width=3, style=QtCore.Qt.PenStyle.DashLine
        )
        self.border_pen = pg.mkPen(self.break_line_color, width=3)
        self.border_pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
        self.text_pen = pg.mkPen(self.text_color)
        self.text_brush = pg.mkBrush(self.text_color)
        self.highlight_text_pen = pg.mkPen(self.highlight_text_color)
        self.highlight_text_brush = pg.mkBrush(self.highlight_text_color)
        self.search_term = None
        self.search_regex = None
        self.update_intervals(self.utterance)

    def refresh_boundaries(self, interval_id, new_time):
        for index, interval in enumerate(self.intervals):
            if interval.id == interval_id:
                try:
                    self.lines[index].setPos(new_time)
                except IndexError:
                    pass
                break
        self.refresh_tier()

    def update_intervals(self, utterance):
        self.intervals = sorted(
            getattr(utterance, self.lookup, self.intervals), key=lambda x: x.begin
        )
        for line in self.lines:
            if line.scene() is not None:
                line.scene().removeItem(line)
        self.lines = []
        bound_min = self.utterance.begin
        for i, interval in enumerate(self.intervals):
            if i == 0:
                continue

            line = IntervalLine(
                interval.begin,
                index=i - 1,
                index_count=len(self.intervals) - 1,
                bound_min=bound_min,
                bound_max=interval.end,
                bottom_point=self.bottom_point,
                top_point=self.top_point,
                pen=self.border_pen,
                movingPen=self.movingPen,
                hoverPen=self.hoverPen,
                movable=self.movable,
            )
            line.setZValue(30)
            line.setParentItem(self)
            # line.sigPositionChanged.connect(self._lineMoved)
            self.lines.append(line)
            bound_min = interval.begin
        self.refresh_tier()

    def refresh_tier(self):
        self.regenerate_text_boxes()
        self.update()

    def regenerate_text_boxes(self):
        self.array = pg.Qt.internals.PrimitiveArray(QtCore.QRectF, 4)
        self.selected_array = pg.Qt.internals.PrimitiveArray(QtCore.QRectF, 4)
        self.array.resize(len(self.intervals))
        self.selected = []
        memory = self.array.ndarray()

        fm = QtGui.QFontMetrics(self.plot_text_font)
        for i, interval in enumerate(self.intervals):
            memory[i, 0] = interval.begin
            memory[i, 2] = interval.end - interval.begin
            if interval.label not in self.parentItem().painter_path_cache:
                symbol = QtGui.QPainterPath()

                symbol.addText(0, 0, self.plot_text_font, interval.label)
                br = symbol.boundingRect()

                # getting transform object
                tr = QtGui.QTransform()

                # translating
                tr.translate(-br.x() - br.width() / 2.0, fm.height() / 2.0)
                self.parentItem().painter_path_cache[interval.label] = tr.map(symbol)

        memory[:, 1] = self.bottom_point
        memory[:, 3] = self.top_point - self.bottom_point

    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            if any(line.mouseHovering for line in self.lines):
                e.ignore()
                return
            time = e.pos().x()

            margin = 21 * self._cached_pixel_size[0]
            if time <= self.utterance.begin + margin or time >= self.utterance.end - margin:
                e.ignore()
                return
            memory = self.array.ndarray()
            if memory.shape[0] > 0:
                index = np.searchsorted(memory[:, 0], time) - 1
                interval = self.intervals[index]
                self.selection_model.select_audio(interval.begin, interval.end)
                self.highlightRequested.emit(TextFilterQuery(interval.label, word=True))
                e.accept()
                return

        return super().mousePressEvent(e)

    def set_search_term(self, search_term: TextFilterQuery):
        self.search_term = search_term
        self.search_regex = None
        if self.search_term is not None and self.search_term.text:
            self.search_regex = re.compile(self.search_term.generate_expression())
            self.selected = []
            for i, interval in enumerate(self.intervals):
                if self.search_regex.search(interval.label):
                    self.selected.append(interval)
            self.selected_array.resize(len(self.selected))
            if self.selected:
                memory = self.selected_array.ndarray()
                for i, interval in enumerate(self.selected):
                    memory[i, 0] = interval.begin
                    memory[i, 2] = interval.end - interval.begin
                memory[:, 1] = self.bottom_point
                memory[:, 3] = self.top_point - self.bottom_point

    def paint(self, painter, *args):
        vb = self.getViewBox()
        px = vb.viewPixelSize()
        inst = self.array.instances()
        br = self.boundingRect()
        painter.save()
        painter.setPen(self.border_pen)
        painter.drawRect(br)
        painter.restore()
        total_time = self.selection_model.max_time - self.selection_model.min_time
        if self.selected:
            selected_inst = self.selected_array.instances()
            painter.save()
            painter.setPen(self.highlight_text_pen)
            painter.setBrush(pg.mkBrush(self.highlight_interval_color))
            painter.drawRects(selected_inst)
            painter.restore()
        for i, interval in enumerate(self.intervals):
            r = inst[i]
            visible_begin = max(r.left(), self.selection_model.plot_min)
            visible_end = min(r.right(), self.selection_model.plot_max)
            visible_duration = visible_end - visible_begin
            if visible_duration / total_time <= 0.0075:
                continue
            x = (r.left() + r.right()) / 2
            painter.save()
            options = QtGui.QTextOption()
            options.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            painter.setRenderHint(painter.RenderHint.Antialiasing, True)
            text_pen = self.text_pen
            text_brush = self.text_brush
            if self.search_regex is not None:
                if self.search_regex.search(interval.label):
                    text_pen = self.highlight_text_pen
                    text_brush = self.highlight_text_brush
            painter.setPen(text_pen)
            painter.setBrush(text_brush)
            painter.translate(x, (self.top_point + self.bottom_point) / 2)
            path = self.parentItem().painter_path_cache[interval.label]
            painter.scale(px[0], -px[1])
            painter.drawPath(path)
            painter.restore()

    def boundingRect(self):
        br = QtCore.QRectF(
            self.utterance.begin,
            self.bottom_point,
            self.utterance.end - self.utterance.begin,
            abs(self.top_point - self.bottom_point),
        )
        vb = self.getViewBox()
        self._cached_pixel_size = vb.viewPixelSize()
        if self._boundingRectCache != br:
            self._boundingRectCache = br
            self.prepareGeometryChange()
        return br


class WordIntervalTier(IntervalTier):
    wordPronunciationChanged = QtCore.Signal(object, object)
    wordChanged = QtCore.Signal(object, object)

    def __init__(
        self,
        parent,
        utterance: Utterance,
        intervals: typing.List[WordInterval],
        selection_model: FileSelectionModel,
        top_point,
        bottom_point,
        lookup=None,
    ):
        super().__init__(
            parent, utterance, intervals, selection_model, top_point, bottom_point, lookup=lookup
        )

    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == QtCore.Qt.MouseButton.RightButton:
            time = e.pos().x()
            memory = self.array.ndarray()
            if memory.shape[0] > 0:
                index = np.searchsorted(memory[:, 0], time) - 1
                interval = self.intervals[index]
                self.selection_model.select_audio(interval.begin, interval.end)
                self.highlightRequested.emit(TextFilterQuery(interval.label, word=True))
                menu = self.construct_context_menu(interval)
                menu.exec_(e.screenPos())
                e.accept()
                return

        return super().mousePressEvent(e)

    def construct_context_menu(
        self, word_interval: typing.Union[WordInterval, ReferenceWordInterval]
    ):
        menu = QtWidgets.QMenu()
        a = QtGui.QAction(menu)
        a.setText("Change word...")
        a.triggered.connect(lambda triggered, x=word_interval: self.change_word(x))
        menu.addAction(a)
        if isinstance(word_interval, WordInterval):
            change_pronunciation_menu = QtWidgets.QMenu("Change pronunciation")
            parent: UtteranceRegion = self.parentItem()
            pronunciations = (
                parent.corpus_model.session.query(Pronunciation)
                .filter(
                    Pronunciation.word_id == word_interval.word_id,
                )
                .all()
            )
            for pron in pronunciations:
                if pron.id == word_interval.pronunciation_id:
                    continue
                a = QtGui.QAction(menu)
                a.setText(pron.pronunciation)
                a.triggered.connect(
                    lambda triggered, x=word_interval, y=pron: self.update_pronunciation(x, y)
                )
                change_pronunciation_menu.addAction(a)
            menu.addMenu(change_pronunciation_menu)
            change_pronunciation_menu.setStyleSheet(self.settings.menu_style_sheet)
        menu.setStyleSheet(self.settings.menu_style_sheet)
        return menu

    def change_word(self, word_interval: typing.Union[WordInterval, ReferenceWordInterval]):
        from anchor.widgets import WordQueryDialog

        parent: UtteranceRegion = self.parentItem()

        dialog = WordQueryDialog(parent.corpus_model)
        if dialog.exec_():
            word = dialog.word_dropdown.current_text()
            self.wordChanged.emit(word_interval, word)

    def update_pronunciation(
        self,
        word_interval: typing.Union[WordInterval, ReferenceWordInterval],
        pronunciation: Pronunciation,
    ):
        self.wordPronunciationChanged.emit(word_interval, pronunciation)


class PhoneIntervalTier(IntervalTier):
    draggingLine = QtCore.Signal(object)
    lineDragFinished = QtCore.Signal(object)
    phoneBoundaryChanged = QtCore.Signal(object, object, object)
    phoneIntervalChanged = QtCore.Signal(object, object)
    phoneIntervalInserted = QtCore.Signal(object, object, object, object, object, object)
    phoneIntervalDeleted = QtCore.Signal(object, object, object, object)
    deleteReferenceAlignments = QtCore.Signal()

    def __init__(
        self,
        parent,
        utterance: Utterance,
        intervals: typing.List[PhoneInterval, ReferencePhoneInterval],
        selection_model: FileSelectionModel,
        top_point,
        bottom_point,
        lookup=None,
    ):
        super().__init__(
            parent,
            utterance,
            intervals,
            selection_model,
            top_point,
            bottom_point,
            lookup=lookup,
            movable=True,
        )

    def update_intervals(self, utterance):
        self.intervals = sorted(
            getattr(utterance, self.lookup, self.intervals), key=lambda x: x.begin
        )
        for line in self.lines:
            if line.scene() is not None:
                line.scene().removeItem(line)
        self.lines = []
        bound_min = self.utterance.begin
        for i, interval in enumerate(self.intervals):
            if i == 0:
                continue

            line = IntervalLine(
                interval.begin,
                index=i - 1,
                index_count=len(self.intervals) - 1,
                bound_min=bound_min,
                bound_max=interval.end,
                bottom_point=self.bottom_point,
                top_point=self.top_point,
                pen=self.border_pen,
                movingPen=self.movingPen,
                hoverPen=self.hoverPen,
                movable=self.movable,
            )
            line.setZValue(30)
            line.setParentItem(self)
            line.sigPositionChangeFinished.connect(self.lineMoveFinished)
            # line.sigPositionChanged.connect(self._lineMoved)
            self.lines.append(line)
            bound_min = interval.begin
            line.sigPositionChanged.connect(self.draggingLine.emit)
            line.sigPositionChangeFinished.connect(self.lineDragFinished.emit)
            line.hoverChanged.connect(self.update_hover)
        self.refresh_tier()

    def update_hover(self, hovered, time):
        if hovered:
            self.draggingLine.emit(time)
        else:
            self.lineDragFinished.emit(time)

    def lineMoveFinished(self):
        sender: IntervalLine = self.sender()
        self.phoneBoundaryChanged.emit(
            self.intervals[sender.index], self.intervals[sender.index + 1], sender.pos().x()
        )
        if sender.index != 0:
            self.lines[sender.index - 1].bound_max = sender.pos().x()
        if sender.index != len(self.lines) - 1:
            self.lines[sender.index + 1].bound_min = sender.pos().x()
        self.regenerate_text_boxes()
        self.update()

    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == QtCore.Qt.MouseButton.RightButton:
            time = e.pos().x()
            memory = self.array.ndarray()
            if memory.shape[0] > 0:
                index = np.searchsorted(memory[:, 0], time) - 1
                interval = self.intervals[index]
                self.selection_model.select_audio(interval.begin, interval.end)
                self.highlightRequested.emit(TextFilterQuery(interval.label, word=True))
                initial = (time - interval.begin) < (interval.end - time)
                menu = self.construct_context_menu(index, interval, initial)
                menu.exec_(e.screenPos())
                e.accept()
                return

        return super().mousePressEvent(e)

    def update_phone(self, phone_interval, phone):
        self.phoneIntervalChanged.emit(phone_interval, phone)

    def insert_phone_interval(self, index: int, initial: bool):
        previous_interval = None
        following_interval = None
        if initial:
            following_interval = self.intervals[index]
            word_interval_id = following_interval.word_interval_id
            if index > 0:
                previous_interval = self.intervals[index - 1]
            begin = following_interval.begin
            end = (following_interval.begin + following_interval.end) / 2
        else:
            previous_interval = self.intervals[index]
            word_interval_id = previous_interval.word_interval_id
            if index < len(self.intervals) - 1:
                following_interval = self.intervals[index + 1]
            begin = (previous_interval.begin + previous_interval.end) / 2
            end = previous_interval.end
        self.phoneIntervalInserted.emit(
            previous_interval, following_interval, word_interval_id, begin, end, self.lookup
        )

    def insert_silence_interval(self, index: int, initial: bool):
        previous_interval = None
        following_interval = None
        if initial:
            following_interval = self.intervals[index]
            if index > 0:
                previous_interval = self.intervals[index - 1]
            begin = following_interval.begin
            end = (following_interval.begin + following_interval.end) / 2
        else:
            previous_interval = self.intervals[index]
            if index < len(self.intervals) - 1:
                following_interval = self.intervals[index + 1]
            begin = (previous_interval.begin + previous_interval.end) / 2
            end = previous_interval.end
        self.phoneIntervalInserted.emit(
            previous_interval, following_interval, None, begin, end, self.lookup
        )

    def delete_phone_interval(self, index: int, initial: bool):
        previous_interval = None
        interval = self.intervals[index]
        following_interval = None
        if index > 0:
            previous_interval = self.intervals[index - 1]
        if index < len(self.intervals) - 1:
            following_interval = self.intervals[index + 1]
        if initial:
            time_point = interval.end
        else:
            time_point = interval.begin
        self.phoneIntervalDeleted.emit(interval, previous_interval, following_interval, time_point)

    def delete_reference(self):
        self.deleteReferenceAlignments.emit()

    def construct_context_menu(
        self,
        index,
        phone_interval: typing.Union[PhoneInterval, ReferencePhoneInterval],
        initial=True,
    ):
        menu = QtWidgets.QMenu()
        change_phone_menu = QtWidgets.QMenu("Change phone")
        for phone_label, phone in sorted(
            self.parentItem().corpus_model.phones.items(), key=lambda x: x[0]
        ):
            if phone_label == phone_interval.label:
                continue
            a = QtGui.QAction(menu)
            a.setText(phone_label)
            a.triggered.connect(
                lambda triggered, x=phone_interval, y=phone: self.update_phone(x, y)
            )
            change_phone_menu.addAction(a)
        menu.addMenu(change_phone_menu)
        a = QtGui.QAction(menu)
        a.setText("Insert silence/word")
        a.triggered.connect(
            lambda triggered, x=index, y=initial: self.insert_silence_interval(x, y)
        )
        menu.addAction(a)

        a = QtGui.QAction(menu)
        a.setText("Insert interval")
        a.triggered.connect(lambda triggered, x=index, y=initial: self.insert_phone_interval(x, y))
        menu.addAction(a)

        a = QtGui.QAction(menu)
        a.setText("Delete interval")
        a.triggered.connect(lambda triggered, x=index, y=initial: self.delete_phone_interval(x, y))
        menu.addAction(a)
        if self.lookup.startswith("reference"):
            a = QtGui.QAction(menu)
            a.setText("Delete reference alignments")
            a.triggered.connect(self.delete_reference)
            menu.addAction(a)
        change_phone_menu.setStyleSheet(self.settings.menu_style_sheet)
        menu.setStyleSheet(self.settings.menu_style_sheet)
        return menu


class UtteranceRegion(MfaRegion):
    phoneBoundaryChanged = QtCore.Signal(object, object, object, object)
    phoneIntervalChanged = QtCore.Signal(object, object, object)
    wordPronunciationChanged = QtCore.Signal(object, object, object)
    wordChanged = QtCore.Signal(object, object, object)
    phoneIntervalInserted = QtCore.Signal(object, object, object, object, object)
    phoneIntervalDeleted = QtCore.Signal(object, object, object, object, object)
    deleteReferenceAlignments = QtCore.Signal(object)
    lookUpWord = QtCore.Signal(object)
    createWord = QtCore.Signal(object)
    transcribeRequested = QtCore.Signal(object)
    draggingLine = QtCore.Signal(object)
    lineDragFinished = QtCore.Signal(object)
    wordBoundariesChanged = QtCore.Signal(object, object)
    phoneTiersChanged = QtCore.Signal(object)

    def __init__(
        self,
        parent,
        utterance: Utterance,
        corpus_model: CorpusModel,
        file_model: FileUtterancesModel,
        dictionary_model: DictionaryTableModel,
        selection_model: FileSelectionModel,
        bottom_point: float = 0,
        top_point: float = 1,
        extra_tiers=None,
        available_speakers=None,
        search_term=None,
    ):
        super().__init__(
            utterance,
            corpus_model,
            file_model,
            dictionary_model,
            selection_model,
            bottom_point,
            top_point,
        )
        self.setParentItem(parent)
        plot_theme = self.settings.plot_theme
        self.hide()
        self.item = utterance
        self.selection_model = selection_model
        if extra_tiers is None:
            extra_tiers = {}
        self.extra_tiers = extra_tiers
        self.extra_tier_intervals = {}
        visible_tiers = self.settings.visible_tiers
        self.num_tiers = len([x for x in extra_tiers if visible_tiers[x]]) + 1
        self.per_tier_range = (top_point - bottom_point) / self.num_tiers
        self.selected = self.selection_model.checkSelected(self.item.id)

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
            UtteranceLine(
                QtCore.QPointF(self.item_min, 0),
                angle=90,
                initial=True,
                view_min=self.selection_model.plot_min,
                view_max=self.selection_model.plot_max,
                **lineKwds,
            ),
            UtteranceLine(
                QtCore.QPointF(self.item_max, 0),
                angle=90,
                initial=False,
                view_min=self.selection_model.plot_min,
                view_max=self.selection_model.plot_max,
                **lineKwds,
            ),
        ]
        self.snap_mode = False
        self.initial_line_moving = False
        for line in self.lines:
            line.setZValue(30)
            line.setParentItem(self)
            line.sigPositionChangeFinished.connect(self.lineMoveFinished)
            line.hoverChanged.connect(self.popup)
            line.sigPositionChanged.connect(self.draggingLine.emit)
            line.sigPositionChangeFinished.connect(self.lineDragFinished.emit)
            line.snapModeChanged.connect(self.update_snap_mode)
        self.lines[0].sigPositionChanged.connect(self._line0Moved)
        self.lines[1].sigPositionChanged.connect(self._line1Moved)

        self.corpus_model.utteranceTextUpdated.connect(self.update_text_from_model)
        self.original_text = self.item.text
        self.text_item = NormalizedTextRegion(
            self,
            self.item.begin,
            self.item.end,
            self.item.text,
            self.top_point,
            self.per_tier_range,
            self.selection_model,
            dictionary_model=dictionary_model,
            search_term=search_term,
            speaker_id=utterance.speaker_id,
        )
        self._painter_path_cache = {}
        self.text_edit = self.text_item.text_edit
        self.text_edit.gainedFocus.connect(self.select_self)
        self.text_edit.menuRequested.connect(self.generate_text_edit_menu)
        self.text_edit.setReadOnly(False)
        self.corpus_model.editableChanged.connect(self.change_editing)
        self.text_edit.installEventFilter(self)
        self.timer = QtCore.QTimer()
        self.text_edit.textChanged.connect(self.refresh_timer)
        self.text_edit.lostFocus.connect(self.save_changes)
        self.text_edit.gainedFocus.connect(self.select_self)
        self.text_edit.menuRequested.connect(self.generate_text_edit_menu)
        self.timer.timeout.connect(self.save_changes)
        self._cached_pixel_size = None
        self.normalized_text = None
        self.transcription_text = None
        i = -1
        self.file_model.phoneTierChanged.connect(self.update_phone_tiers)
        for tier_name, lookup in self.extra_tiers.items():
            if not visible_tiers[tier_name]:
                continue
            i += 1
            tier_top_point = self.top_point - ((i + 1) * self.per_tier_range)
            tier_bottom_point = tier_top_point - self.per_tier_range

            if lookup == "normalized_text":
                self.normalized_text = NormalizedTextRegion(
                    self,
                    self.item.begin,
                    self.item.end,
                    self.item.normalized_text,
                    tier_top_point,
                    self.per_tier_range,
                    self.selection_model,
                    dictionary_model=dictionary_model,
                    search_term=search_term,
                    speaker_id=utterance.speaker_id,
                )
                self.normalized_text.text_edit.gainedFocus.connect(self.select_self)
                self.normalized_text.text_edit.menuRequested.connect(self.generate_text_edit_menu)
                continue
            elif lookup == "transcription_text":
                self.transcription_text = TranscriberTextRegion(
                    self,
                    self.item,
                    tier_top_point,
                    self.per_tier_range,
                    self.selection_model,
                    dictionary_model=dictionary_model,
                    search_term=search_term,
                    speaker_id=utterance.speaker_id,
                    plot_theme=self.plot_theme,
                )
                self.transcription_text.transcribeRequested.connect(self.transcribeRequested.emit)
                self.transcription_text.setParentItem(self)
                self.transcription_text.text_edit.gainedFocus.connect(self.select_self)
                self.transcription_text.text_edit.menuRequested.connect(
                    self.generate_text_edit_menu
                )
                if self.normalized_text is not None:
                    self.normalized_text.text_edit.textChanged.connect(
                        self.update_transcription_highlight
                    )
                self.transcription_text.text_edit.textChanged.connect(
                    self.update_transcription_highlight
                )
                self.update_transcription_highlight()
                continue
            intervals = getattr(self.item, lookup)

            self.extra_tier_intervals[tier_name] = []

            if intervals is None:
                continue
            if not isinstance(intervals, list):
                intervals = [intervals]
            min_confidence = None
            max_confidence = None
            cmap = pg.ColorMap(
                None,
                [
                    plot_theme.error_color,
                    plot_theme.interval_background_color,
                ],
            )
            cmap.linearize()
            if "phone_intervals" in lookup:
                if lookup != "reference_phone_intervals":
                    for interval in intervals:
                        if interval.confidence is None:
                            continue
                        if min_confidence is None or interval.confidence < min_confidence:
                            min_confidence = interval.confidence
                        if max_confidence is None or interval.confidence > max_confidence:
                            max_confidence = interval.confidence
                interval_tier = PhoneIntervalTier(
                    self,
                    self.item,
                    intervals,
                    self.selection_model,
                    top_point=tier_top_point,
                    bottom_point=tier_bottom_point,
                    lookup=lookup,
                )
                interval_tier.draggingLine.connect(self.draggingLine.emit)
                interval_tier.lineDragFinished.connect(self.lineDragFinished.emit)
                interval_tier.phoneBoundaryChanged.connect(self.change_phone_boundaries)
                interval_tier.phoneIntervalChanged.connect(self.change_phone_interval)
                interval_tier.phoneIntervalDeleted.connect(self.delete_phone_interval)
                interval_tier.phoneIntervalInserted.connect(self.insert_phone_interval)
                self.phoneTiersChanged.connect(interval_tier.update_intervals)
                if lookup.startswith("reference"):
                    interval_tier.deleteReferenceAlignments.connect(
                        self.delete_reference_alignments
                    )
                self.extra_tier_intervals[tier_name].append(interval_tier)

            elif "word_intervals" in lookup:
                interval_tier = WordIntervalTier(
                    self,
                    self.item,
                    intervals,
                    self.selection_model,
                    top_point=tier_top_point,
                    bottom_point=tier_bottom_point,
                    lookup=lookup,
                )
                self.wordBoundariesChanged.connect(interval_tier.refresh_boundaries)
                interval_tier.highlightRequested.connect(self.set_search_term)
                interval_tier.wordPronunciationChanged.connect(self.change_word_pronunciation)
                interval_tier.wordChanged.connect(self.change_word)
                self.phoneTiersChanged.connect(interval_tier.update_intervals)
                if self.transcription_text is not None:
                    interval_tier.highlightRequested.connect(
                        self.transcription_text.highlighter.setSearchTerm
                    )
                if self.normalized_text is not None:
                    interval_tier.highlightRequested.connect(
                        self.normalized_text.highlighter.setSearchTerm
                    )
                self.extra_tier_intervals[tier_name].append(interval_tier)

            for interval in intervals:
                if "phone_intervals" in lookup or "word_intervals" in lookup:
                    continue
                else:
                    interval_reg = IntervalTextRegion(
                        interval,
                        self.text_color,
                        border=pg.mkPen(plot_theme.break_line_color, width=1),
                        top_point=tier_top_point,
                        height=self.per_tier_range,
                        background_brush=self.background_brush,
                        selected_brush=pg.mkBrush(self.selected_interval_color),
                        plot_theme=self.plot_theme,
                    )
                    interval_reg.audioSelected.connect(self.setSelected)
                    interval_reg.setParentItem(self)

                interval_reg.audioSelected.connect(self.audioSelected.emit)
                interval_reg.viewRequested.connect(self.viewRequested.emit)
                self.extra_tier_intervals[tier_name].append(interval_reg)
        self.selection_model.viewChanged.connect(self.update_view_times)
        self.lookUpWord.connect(self.dictionary_model.lookup_word)
        self.createWord.connect(self.dictionary_model.add_word)
        self.show()
        self.available_speakers = available_speakers

    def update_snap_mode(self, snap_mode):
        self.snap_mode = snap_mode

    def _line0Moved(self):
        self.lineMoved(0)
        self.initial_line_moving = True

    def _line1Moved(self):
        self.lineMoved(1)
        self.initial_line_moving = False

    def delete_reference_alignments(self):
        self.deleteReferenceAlignments.emit(self.item)

    def update_phone_tiers(self, utterance):
        if utterance.id != self.item.id:
            return
        self.phoneTiersChanged.emit(utterance)

    def update_transcription_highlight(self):
        if self.item.normalized_text and self.item.transcription_text:
            ref_intervals = [CtmInterval(0.0, 0.0, w) for w in self.item.normalized_text.lower().split()]
            test_intervals = [CtmInterval(0.0, 0.0, w) for w in self.item.transcription_text.lower().split()]
            alignment = align_intervals(ref_intervals, test_intervals, "<eps>", {})
            self.transcription_text.highlighter.set_alignment(alignment)

    def set_search_term(self, term):
        self.text_item.highlighter.setSearchTerm(term)
        if self.transcription_text is not None:
            self.transcription_text.highlighter.setSearchTerm(term)
        if self.normalized_text is not None:
            self.normalized_text.highlighter.setSearchTerm(term)
        for tier in self.extra_tier_intervals.values():
            if tier and isinstance(tier[0], IntervalTier):
                tier[0].set_search_term(term)

    @property
    def painter_path_cache(self):
        if self.parentItem() is None:
            return self._painter_path_cache
        return self.parentItem().painter_path_cache

    def update_edit_fields(self):
        begin, end = self.getRegion()
        self.text_item.text_item.update_times(begin, end)
        if self.normalized_text is not None:
            self.normalized_text.text_item.update_times(begin, end)
        if self.transcription_text is not None:
            self.transcription_text.text_item.update_times(begin, end)
        self.phoneTiersChanged.emit(self.item)

    def change_editing(self, editable: bool):
        self.lines[0].movable = editable
        self.lines[1].movable = editable
        self.text_edit.setReadOnly(not editable)

    def popup(self, hover: bool):
        if hover or self.moving or self.lines[0].moving or self.lines[1].moving:
            self.setZValue(30)
        else:
            self.setZValue(0)

    def setMovable(self, m=True):
        """Set lines to be movable by the user, or not. If lines are movable, they will
        also accept HoverEvents."""
        for line in self.lines:
            line.setMovable(m)
        self.movable = False
        self.setAcceptHoverEvents(False)

    def construct_context_menu(self):
        menu = QtWidgets.QMenu()
        change_speaker_menu = QtWidgets.QMenu("Change speaker")
        a = QtGui.QAction(menu)
        a.setText("New speaker")
        a.triggered.connect(self.update_speaker)
        change_speaker_menu.addAction(a)
        for speaker_name, speaker_id in self.available_speakers.items():
            if speaker_id == self.item.speaker_id:
                continue
            a = QtGui.QAction(menu)
            a.setText(speaker_name)
            a.triggered.connect(self.update_speaker)
            change_speaker_menu.addAction(a)
        a = QtGui.QAction(menu)
        a.setText("Find speaker...")
        a.triggered.connect(self.find_speaker)
        change_speaker_menu.addAction(a)
        menu.addMenu(change_speaker_menu)

        visible_tiers_menu = QtWidgets.QMenu("Visible tiers")
        visible_tiers = self.settings.visible_tiers
        for tier_name in self.extra_tiers.keys():
            a = QtGui.QAction(visible_tiers_menu)
            a.setCheckable(True)
            if visible_tiers.get(tier_name, True):
                a.setChecked(True)
            a.setText(f"Show {tier_name}")
            a.toggled.connect(self.update_tier_visibility)
            visible_tiers_menu.addAction(a)
        menu.addMenu(visible_tiers_menu)
        menu.addSeparator()

        a = QtGui.QAction(menu)
        a.setText("Split utterance")
        a.triggered.connect(self.split_utterance)
        menu.addAction(a)

        a = QtGui.QAction(menu)
        a.setText("Delete utterance")
        a.triggered.connect(self.delete_utterance)
        menu.addAction(a)
        change_speaker_menu.setStyleSheet(self.settings.menu_style_sheet)
        visible_tiers_menu.setStyleSheet(self.settings.menu_style_sheet)
        menu.setStyleSheet(self.settings.menu_style_sheet)
        return menu

    def generate_text_edit_menu(self, word, location):
        menu = self.construct_context_menu()
        menu.addSeparator()
        if self.dictionary_model.check_word(word, speaker_id=self.item.speaker_id):
            lookUpAction = QtGui.QAction(f'Look up "{word}" in dictionary', self)
            lookUpAction.triggered.connect(lambda: self.lookUpWord.emit(word))
            lookUpAction.triggered.connect(menu.hide)
            menu.addAction(lookUpAction)
        else:
            createAction = QtGui.QAction(f'Add pronunciation for "{word}"', self)
            createAction.triggered.connect(lambda: self.createWord.emit(word))
            createAction.triggered.connect(menu.hide)
            menu.addAction(createAction)
        menu.setStyleSheet(self.settings.menu_style_sheet)
        menu.exec_(location)

    def contextMenuEvent(self, ev: QtWidgets.QGraphicsSceneContextMenuEvent):
        menu = self.construct_context_menu()
        menu.exec_(ev.screenPos())

    def update_tier_visibility(self, checked):
        sender = self.sender()
        if not isinstance(sender, QtGui.QAction):
            return
        tier_name = sender.text().split(maxsplit=1)[-1]
        self.settings.setValue(self.settings.tier_visibility_mapping[tier_name], checked)
        self.settings.sync()
        self.corpus_model.refreshTiers.emit()

    def find_speaker(self):
        from anchor.widgets import SpeakerQueryDialog

        dialog = SpeakerQueryDialog(self.corpus_model)
        if dialog.exec_():
            speaker_id = dialog.speaker_dropdown.current_text()
            if isinstance(speaker_id, int):
                self.file_model.update_utterance_speaker(self.item, speaker_id)

    def update_speaker(self):
        sender = self.sender()
        if not isinstance(sender, QtGui.QAction):
            return
        speaker_name = sender.text()
        if speaker_name == "New speaker":
            speaker_id = 0
        else:
            speaker_id = self.available_speakers[speaker_name]
        self.file_model.update_utterance_speaker(self.item, speaker_id)

    def split_utterance(self):
        self.file_model.split_utterances([self.item])

    def delete_utterance(self):
        self.file_model.delete_utterances([self.item])

    def refresh_timer(self):
        self.timer.start(500)
        self.update()

    def select_self(self, deselect=False, reset=True):
        self.setSelected(not deselect)
        self.selectRequested.emit(self.item.id, deselect, reset)

    def mouseDoubleClickEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return
        deselect = False
        reset = True
        if ev.modifiers() in [
            QtCore.Qt.KeyboardModifier.ControlModifier,
            QtCore.Qt.KeyboardModifier.ShiftModifier,
        ]:
            reset = False
            if self.selected:
                deselect = True
                self.selected = False
            else:
                self.selected = True
        else:
            self.selected = True
        self.select_self(deselect=deselect, reset=reset)
        ev.accept()

    def mouseClickEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return
        deselect = False
        reset = True
        if ev.modifiers() in [
            ev.modifiers().ControlModifier,
            ev.modifiers().ShiftModifier,
        ]:
            reset = False
            if self.selected:
                deselect = True
                self.selected = False
            else:
                self.selected = True
        else:
            self.selected = True
        self.select_self(deselect=deselect, reset=reset)
        ev.accept()

    def update_view_times(self):
        self.lines[0].view_min = self.selection_model.plot_min
        self.lines[0].view_max = self.selection_model.plot_max
        self.lines[1].view_min = self.selection_model.plot_min
        self.lines[1].view_max = self.selection_model.plot_max
        self.update()

    def boundingRect(self):
        br = QtCore.QRectF(self.viewRect())  # bounds of containing ViewBox mapped to local coords.
        vb = self.getViewBox()
        self._cached_pixel_size = vb.viewPixelSize()
        rng = self.getRegion()

        br.setLeft(rng[0])
        br.setRight(rng[1])

        br.setTop(self.top_point)
        br.setBottom(self.bottom_point)

        x_margin_px = 40
        self.size_calculated = True
        for line in self.lines:
            line.bounding_width = int(x_margin_px / 2)
        br = br.normalized()

        if self._boundingRectCache != br:
            self._boundingRectCache = br
            self.prepareGeometryChange()

        return br

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.KeyPress:
            key_event = QtGui.QKeyEvent(event)
            undo_combo = QtCore.QKeyCombination(QtCore.Qt.Modifier.CTRL, QtCore.Qt.Key.Key_Z)
            redo_combo = QtCore.QKeyCombination(
                QtCore.Qt.Modifier.CTRL | QtCore.Qt.Modifier.SHIFT, QtCore.Qt.Key.Key_Z
            )
            if key_event.key() == QtCore.Qt.Key.Key_Tab:
                self.playRequested.emit()
                return True
            if (
                key_event.keyCombination() == undo_combo
                and not self.text_edit.document().isUndoAvailable()
            ):
                self.undoRequested.emit()
                return True
            if (
                key_event.keyCombination() == redo_combo
                and not self.text_edit.document().isRedoAvailable()
            ):
                self.redoRequested.emit()
                return True

        return super().eventFilter(obj, event)

    def update_text_from_model(self, utterance_id, new_text):
        try:
            if utterance_id != self.item.id or new_text == self.original_text:
                return
        except sqlalchemy.orm.exc.DetachedInstanceError:
            self.corpus_model.session.refresh(self.item)
            if utterance_id != self.item.id or new_text == self.original_text:
                return
        self.original_text = new_text
        with QtCore.QSignalBlocker(self.text_item.text_edit):
            position = self.text_edit.textCursor().position()
            end_offset = self.text_edit.document().characterCount() - position
            self.text_edit.setPlainText(new_text)
            cursor = self.text_edit.textCursor()
            position = self.text_edit.document().characterCount() - end_offset
            if position > self.text_edit.document().characterCount():
                position = self.text_edit.document().characterCount()
            cursor.setPosition(position)
            self.text_edit.setTextCursor(cursor)
            self.text_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.update()

    def change_phone_boundaries(
        self, first_phone_interval, second_phone_interval, new_time: float
    ):
        self.phoneBoundaryChanged.emit(
            self.item, first_phone_interval, second_phone_interval, new_time
        )
        if first_phone_interval.word_interval_id != second_phone_interval.word_interval_id:
            self.wordBoundariesChanged.emit(first_phone_interval.word_interval_id, new_time)

    def change_phone_interval(self, phone_interval, new_phone_id):
        self.phoneIntervalChanged.emit(self.item, phone_interval, new_phone_id)

    def change_word(self, word_interval, word):
        self.wordChanged.emit(self.item, word_interval, word)

    def change_word_pronunciation(self, word_interval, pronunciation):
        self.wordPronunciationChanged.emit(self.item, word_interval, pronunciation)

    def delete_phone_interval(self, interval, previous_interval, following_interval, time_point):
        self.phoneIntervalDeleted.emit(
            self.item, interval, previous_interval, following_interval, time_point
        )
        if (
            previous_interval is None
            or following_interval is None
            or previous_interval.word_interval_id != following_interval.word_interval_id
        ):
            self.wordBoundariesChanged.emit(previous_interval.word_interval_id, time_point)

    def insert_phone_interval(
        self,
        previous_interval,
        following_interval,
        word_interval_id,
        begin=None,
        end=None,
        lookup="phone_intervals",
    ):
        if begin is None:
            begin = (
                (previous_interval.begin + previous_interval.end) / 2
                if previous_interval is not None
                else self.item.begin
            )
        if end is None:
            end = (
                (following_interval.begin + following_interval.end) / 2
                if following_interval is not None
                else self.item.end
            )
        inserting_word_interval = word_interval_id is None
        word_interval = None
        if inserting_word_interval:
            previous_word_interval_id = (
                previous_interval.word_interval_id if previous_interval is not None else None
            )
            following_word_interval_id = (
                following_interval.word_interval_id if following_interval is not None else None
            )
            at_word_boundary = previous_word_interval_id != following_word_interval_id
            if not at_word_boundary:
                return
            if not lookup.startswith("reference"):
                word_interval_id = self.corpus_model.corpus.get_next_primary_key(WordInterval)
                word = self.corpus_model.corpus.session.get(Word, 1)
                word_interval = WordInterval(
                    id=word_interval_id,
                    word=word,
                    begin=begin,
                    end=end,
                )
            else:
                word_interval_id = self.corpus_model.corpus.get_next_primary_key(
                    ReferenceWordInterval
                )
                word = self.corpus_model.corpus.session.get(Word, 1)
                word_interval = ReferenceWordInterval(
                    id=word_interval_id,
                    word=word,
                    begin=begin,
                    end=end,
                )
        elif not lookup.startswith("reference"):
            for x in self.item.word_intervals:
                if x.id == word_interval_id:
                    word_interval = x
                    break
        else:
            for x in self.item.reference_word_intervals:
                if x.id == word_interval_id:
                    word_interval = x
                    break
        if not lookup.startswith("reference"):
            next_pk = self.corpus_model.corpus.get_next_primary_key(PhoneInterval)
            phone_interval = PhoneInterval(
                id=next_pk,
                phone=self.corpus_model.phones["sil"],
                begin=begin,
                end=end,
                word_interval=word_interval,
                word_interval_id=word_interval_id,
            )
        else:
            next_pk = self.corpus_model.corpus.get_next_primary_key(ReferencePhoneInterval)
            phone_interval = ReferencePhoneInterval(
                id=next_pk,
                phone=self.corpus_model.phones["sil"],
                begin=begin,
                end=end,
                word_interval=word_interval,
                word_interval_id=word_interval_id,
            )
        self.phoneIntervalInserted.emit(
            self.item,
            phone_interval,
            previous_interval,
            following_interval,
            word_interval if inserting_word_interval else None,
        )

    def save_changes(self):
        text = self.text_edit.toPlainText()
        if self.original_text == text:
            return
        self.original_text = text
        self.textEdited.emit(self.item, text)
        if self.normalized_text:
            self.normalized_text.text_edit.setPlainText(self.item.normalized_text)


class WaveForm(pg.PlotCurveItem):
    def __init__(self, bottom_point, top_point):
        self.settings = AnchorSettings()
        self.top_point = top_point
        self.bottom_point = bottom_point
        self.mid_point = (self.top_point + self.bottom_point) / 2
        pen = pg.mkPen(self.settings.plot_theme.wave_line_color, width=1)
        super(WaveForm, self).__init__()
        self.setPen(pen)
        self.channel = 0
        self.y = None
        self.selection_model = None
        self.setAcceptHoverEvents(False)

    def update_theme(self):
        pen = pg.mkPen(self.settings.plot_theme.wave_line_color, width=1)
        self.setPen(pen)

    def hoverEvent(self, ev):
        return

    def set_models(self, selection_model: CorpusSelectionModel):
        self.selection_model = selection_model


class PitchTrack(pg.PlotCurveItem):
    def __init__(self, bottom_point, top_point):
        self.settings = AnchorSettings()
        self.plot_theme = self.settings.plot_theme
        self.top_point = top_point
        self.bottom_point = bottom_point
        self.mid_point = (self.top_point + self.bottom_point) / 2
        pen = pg.mkPen(self.plot_theme.pitch_color, width=3)
        super().__init__()
        self.setPen(pen)
        self.channel = 0
        self.y = None
        self.selection_model = None
        self.setAcceptHoverEvents(False)
        self.min_label = pg.TextItem(
            str(self.settings.PITCH_MIN_F0),
            self.plot_theme.pitch_color,
            anchor=(1, 1),
        )
        self.min_label.setFont(self.settings.font)
        self.min_label.setParentItem(self)
        self.max_label = pg.TextItem(
            str(self.settings.PITCH_MAX_F0),
            self.plot_theme.pitch_color,
            anchor=(1, 0),
        )
        self.max_label.setFont(self.settings.font)
        self.max_label.setParentItem(self)

    def update_theme(self):
        pen = pg.mkPen(self.plot_theme.pitch_color, width=3)
        self.setPen(pen)
        self.min_label.setColor(self.plot_theme.pitch_color)
        self.max_label.setColor(self.plot_theme.pitch_color)

    def hoverEvent(self, ev):
        return

    def set_range(self, min_f0, max_f0, end):
        self.min_label.setText(f"{min_f0} Hz")
        self.max_label.setText(f"{max_f0} Hz")
        self.min_label.setPos(end, self.bottom_point)
        self.max_label.setPos(end, self.top_point)

    def set_models(self, selection_model: CorpusSelectionModel):
        self.selection_model = selection_model


class Spectrogram(pg.ImageItem):
    def __init__(self, bottom_point, top_point):
        self.settings = AnchorSettings()
        self.plot_theme = self.settings.plot_theme
        self.top_point = top_point
        self.bottom_point = bottom_point
        self.selection_model = None
        self.channel = 0
        super(Spectrogram, self).__init__()
        self.cmap = pg.ColorMap(
            None,
            [
                self.plot_theme.background_color,
                self.plot_theme.spectrogram_color,
            ],
        )
        self.cmap.linearize()
        self.color_bar = pg.ColorBarItem(colorMap=self.cmap)
        self.color_bar.setImageItem(self)
        self.setAcceptHoverEvents(False)
        self.cached_begin = None
        self.cached_end = None
        self.cached_channel = None
        self.stft = None

    def update_theme(self):
        self.cmap = pg.ColorMap(
            None,
            [
                self.plot_theme.background_color,
                self.plot_theme.spectrogram_color,
            ],
        )
        self.cmap.linearize()
        self.color_bar.setColorMap(self.cmap)
        self.color_bar.setImageItem(self)
        self.update()

    def set_models(self, selection_model: CorpusSelectionModel):
        self.selection_model = selection_model

    def boundingRect(self):
        br = super(Spectrogram, self).boundingRect()
        return br

    def setData(self, stft, channel, begin, end, min_db, max_db):
        self.stft = stft
        self.min_db = min_db
        self.max_db = max_db
        self.cached_end = end
        self.cached_begin = begin
        self.cached_channel = channel
        duration = self.cached_end - self.cached_begin
        rect = [self.cached_begin, self.bottom_point, duration, self.top_point - self.bottom_point]
        self.setLevels([self.min_db, self.max_db], update=False)
        self.setImage(self.stft, colorMap=self.cmap, rect=rect)
        self.show()


class SelectionArea(pg.LinearRegionItem):
    def __init__(self, top_point, bottom_point, brush, clipItem, pen):
        self.settings = AnchorSettings()
        self.selection_model: typing.Optional[CorpusSelectionModel] = None
        super(SelectionArea, self).__init__(
            values=(-10, -5),
            span=(bottom_point / top_point, 1),
            brush=brush,
            movable=False,
            # clipItem=clipItem,
            pen=pen,
            orientation="vertical",
        )
        self.setZValue(30)
        self.lines[0].label = pg.InfLineLabel(
            self.lines[0], text="", position=1, anchors=[(1, 0), (1, 0)]
        )
        self.lines[1].label = pg.InfLineLabel(
            self.lines[1], text="", position=1, anchors=[(0, 0), (0, 0)]
        )
        font = self.settings.font
        font.setBold(True)
        self.lines[0].label.setFont(font)
        self.lines[1].label.setFont(font)

    def set_model(self, selection_model: CorpusSelectionModel):
        self.selection_model = selection_model
        self.selection_model.selectionAudioChanged.connect(self.update_region)

    def update_region(self):
        begin = self.selection_model.selected_min_time
        end = self.selection_model.selected_max_time
        if (
            begin is None
            or end is None
            or (begin == self.selection_model.plot_min and end == self.selection_model.plot_max)
        ):
            self.setVisible(False)
        else:
            self.setRegion([begin, end])
            self.lines[0].label.setText(
                f"{begin:.3f}", self.settings.plot_theme.selected_range_color
            )
            self.lines[1].label.setText(
                f"{end:.3f}", self.settings.plot_theme.selected_range_color
            )
            self.setVisible(True)


class AudioPlots(pg.GraphicsObject):
    def __init__(self, top_point, separator_point, bottom_point):
        super().__init__()
        self.settings = AnchorSettings()
        self.plot_theme = self.settings.plot_theme
        self.selection_model: typing.Optional[FileSelectionModel] = None
        self.top_point = top_point
        self.separator_point = separator_point
        self.bottom_point = bottom_point
        self.wave_form = WaveForm(separator_point, self.top_point)
        self.spectrogram = Spectrogram(self.bottom_point, separator_point)
        self.pitch_track = PitchTrack(self.bottom_point, separator_point)
        self.wave_form.setParentItem(self)
        self.spectrogram.setParentItem(self)
        self.pitch_track.setParentItem(self)
        self.grabGesture(QtCore.Qt.PinchGesture)
        color = self.plot_theme.selected_range_color
        color.setAlphaF(0.25)
        self.selection_brush = pg.mkBrush(color)
        self.background_pen = pg.mkPen(self.plot_theme.background_color)
        self.background_brush = pg.mkBrush(self.plot_theme.background_color)
        self.selection_area = SelectionArea(
            top_point=self.top_point,
            bottom_point=self.bottom_point,
            brush=self.selection_brush,
            clipItem=self,
            pen=pg.mkPen(self.plot_theme.selected_interval_color),
        )
        self.selection_area.setParentItem(self)

        self.play_timer = QtCore.QTimer()
        self.play_timer.setInterval(1)
        self.play_timer.timeout.connect(self.update_play_line)

        self.play_line = pg.InfiniteLine(
            pos=-20,
            span=(0, 1),
            pen=pg.mkPen("r", width=1),
            movable=False,  # We have our own code to handle dragless moving.
        )
        self.play_line.setParentItem(self)

        self.update_line = pg.InfiniteLine(
            pos=-20,
            span=(0, 1),
            pen=pg.mkPen(
                self.plot_theme.selected_interval_color,
                width=3,
                style=QtCore.Qt.PenStyle.DashLine,
            ),
            movable=False,  # We have our own code to handle dragless moving.
        )
        self.update_line.setParentItem(self)
        self.update_line.hide()
        self.setAcceptHoverEvents(True)
        self.picture = QtGui.QPicture()
        self.rect = QtCore.QRectF(
            left=0, top=self.top_point, width=10, height=self.top_point - self.bottom_point
        )
        self.rect.setTop(self.top_point)
        self.rect.setBottom(self.bottom_point)
        self._generate_picture()

    def update_drag_line(self, line: UtteranceLine):
        self.update_line.setPos(line.pos())
        self.update_line.show()

    def hide_drag_line(self):
        self.update_line.hide()

    def sceneEvent(self, ev):
        if ev.type() == QtCore.QEvent.Gesture:
            return self.gestureEvent(ev)
        return super().sceneEvent(ev)

    def gestureEvent(self, ev):
        ev.accept()
        pinch = ev.gesture(QtCore.Qt.PinchGesture)
        if pinch is not None:
            delta = pinch.scaleFactor()
            sc = delta
            center = self.getViewBox().mapToView(pinch.centerPoint())
            self.selection_model.zoom(sc, center.x())

    def wheelEvent(self, ev: QtWidgets.QGraphicsSceneWheelEvent):
        ev.accept()
        delta = ev.delta()
        sc = 1.001**delta
        if ev.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            center = self.getViewBox().mapSceneToView(ev.scenePos())
            self.selection_model.zoom(sc, center.x())
        else:
            self.selection_model.pan(sc)

    def mouseDragEvent(self, ev):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return
        if self.selection_model.plot_min is None:
            ev.ignore()
            return
        min_time = max(min(ev.buttonDownPos().x(), ev.pos().x()), self.selection_model.plot_min)
        max_time = min(max(ev.buttonDownPos().x(), ev.pos().x()), self.selection_model.plot_max)
        if ev.isStart():
            self.selection_area.setVisible(True)
        if ev.isFinish():
            self.selection_model.select_audio(min_time, max_time)
        ev.accept()

    def mouseClickEvent(self, ev):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return
        if ev.modifiers() in [
            QtCore.Qt.KeyboardModifier.ControlModifier,
            QtCore.Qt.KeyboardModifier.ShiftModifier,
        ]:
            time = ev.pos().x()
            if self.selection_model.selected_max_time is not None:
                if (
                    self.selection_model.selected_min_time
                    < time
                    < self.selection_model.selected_max_time
                ):
                    if (
                        time - self.selection_model.selected_min_time
                        < self.selection_model.selected_max_time - time
                    ):
                        min_time = time
                        max_time = self.selection_model.selected_max_time
                    else:
                        min_time = self.selection_model.selected_min_time
                        max_time = time
                else:
                    min_time = min(
                        time,
                        self.selection_model.selected_min_time,
                        self.selection_model.selected_max_time,
                    )
                    max_time = max(
                        time,
                        self.selection_model.selected_min_time,
                        self.selection_model.selected_max_time,
                    )
            else:
                min_time = min(time, self.selection_model.selected_min_time)
                max_time = max(time, self.selection_model.selected_min_time)
            self.selection_area.setRegion((min_time, max_time))
            self.selection_area.setVisible(True)
            self.selection_model.select_audio(min_time, max_time)
        else:
            self.selection_model.request_start_time(ev.pos().x(), update=True)
        ev.accept()

    def hoverEvent(self, ev):
        if not ev.isExit():
            # the mouse is hovering over the image; make sure no other items
            # will receive left click/drag events from here.

            ev.acceptDrags(QtCore.Qt.MouseButton.LeftButton)
            ev.acceptClicks(QtCore.Qt.MouseButton.LeftButton)

    def set_models(self, selection_model: CorpusSelectionModel):
        self.selection_model = selection_model
        self.wave_form.set_models(selection_model)
        self.spectrogram.set_models(selection_model)
        self.selection_area.set_model(selection_model)

    def _generate_picture(self):
        if self.selection_model is None:
            return
        painter = QtGui.QPainter(self.picture)
        painter.setPen(self.background_pen)
        painter.setBrush(self.background_brush)
        painter.drawRect(self.rect)
        painter.end()

    def paint(self, painter, *args):
        painter.save()
        painter.drawPicture(0, 0, self.picture)
        painter.restore()

    def boundingRect(self):
        br = QtCore.QRectF(self.picture.boundingRect())
        return br

    def update_play_line(self, time=None):
        if time is None:
            return
        self.play_line.setVisible(
            self.selection_model.min_time <= time <= self.selection_model.max_time
        )
        self.play_line.setPos(time)

    def update_plot(self):
        self.setVisible(False)
        self.play_line.setVisible(False)
        if (
            self.selection_model.model().file is None
            or self.selection_model.model().file.sound_file is None
            or not os.path.exists(self.selection_model.model().file.sound_file.sound_file_path)
        ):
            return
        self.rect.setLeft(self.selection_model.plot_min)
        self.rect.setRight(self.selection_model.plot_max)
        self._generate_picture()
        # self.selection_area.update_region()
        self.setVisible(True)


class SpeakerTier(pg.GraphicsObject):
    receivedWheelEvent = QtCore.Signal(object)
    receivedGestureEvent = QtCore.Signal(object)
    draggingLine = QtCore.Signal(object)
    lineDragFinished = QtCore.Signal(object)

    def __init__(
        self,
        top_point,
        bottom_point,
        speaker_id: int,
        speaker_name: str,
        corpus_model: CorpusModel,
        file_model: FileUtterancesModel,
        selection_model: FileSelectionModel,
        dictionary_model: DictionaryTableModel,
        search_term: str = None,
    ):
        super().__init__()
        self.file_model = file_model
        self.corpus_model = corpus_model
        self.selection_model = selection_model
        self.dictionary_model = dictionary_model
        self.settings = AnchorSettings()
        self.plot_theme = self.settings.plot_theme
        self.search_term = search_term
        self.speaker_id = speaker_id
        self.speaker_name = speaker_name
        self.speaker_index = 0
        self.top_point = top_point
        self.speaker_label = pg.TextItem(self.speaker_name, color=self.plot_theme.break_line_color)
        self.speaker_label.setFont(self.settings.font)
        self.speaker_label.setParentItem(self)
        self.speaker_label.setZValue(40)
        self.bottom_point = bottom_point
        self.annotation_range = self.top_point - self.bottom_point
        self.extra_tiers = {}
        self.visible_utterances: dict[int, UtteranceRegion] = {}
        self.background_brush = pg.mkBrush(self.plot_theme.background_color)
        self.border = pg.mkPen(self.plot_theme.break_line_color)
        self.picture = QtGui.QPicture()
        self.has_visible_utterances = False
        self.has_selected_utterances = False
        self.rect = QtCore.QRectF(
            left=self.selection_model.plot_min,
            riht=self.selection_model.plot_max,
            top=self.top_point,
            bottom=self.bottom_point,
        )
        self._generate_picture()
        self.corpus_model.lockCorpus.connect(self.lock)
        self.corpus_model.refreshUtteranceText.connect(self.refreshTexts)
        self.selection_model.selectionChanged.connect(self.update_select)
        self.selection_model.model().utterancesReady.connect(self.refresh)
        self.available_speakers = {}
        self.painter_path_cache = {}
        self.grabGesture(QtCore.Qt.PinchGesture)

    def wheelEvent(self, ev):
        self.receivedWheelEvent.emit(ev)

    def sceneEvent(self, ev):
        if ev.type() == QtCore.QEvent.Gesture:
            return self.gestureEvent(ev)
        return super().sceneEvent(ev)

    def gestureEvent(self, ev):
        ev.accept()
        pinch = ev.gesture(QtCore.Qt.PinchGesture)
        if pinch is not None:
            self.receivedGestureEvent.emit(ev)

    def create_utterance(self, begin, end):
        self.file_model.create_utterance(self.speaker_id, begin, end)

    def boundingRect(self):
        return QtCore.QRectF(self.picture.boundingRect())

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def _generate_picture(self):
        speaker_name = self.corpus_model.get_speaker_name(self.speaker_id)
        if speaker_name != self.speaker_name:
            self.speaker_name = speaker_name
            self.speaker_label.setText(self.speaker_name)
        self.picture = QtGui.QPicture()
        painter = QtGui.QPainter(self.picture)
        painter.setPen(self.border)

        painter.setBrush(self.background_brush)
        painter.drawRect(self.rect)
        painter.end()

    def set_extra_tiers(self, extra_tiers):
        self.extra_tiers = extra_tiers

    def set_available_speakers(self, available_speakers):
        self.available_speakers = available_speakers

    def lock(self):
        for utt in self.visible_utterances.values():
            utt.setMovable(False)

    def unlock(self):
        for utt in self.visible_utterances.values():
            utt.setMovable(True)

    def setSearchTerm(self, term):
        for utt in self.visible_utterances.values():
            utt.text_item.highlighter.setSearchTerm(term)
            utt.set_search_term(term)

    def refreshTexts(self, utt_id, text):
        for reg in self.visible_utterances.values():
            if reg.item.id != utt_id:
                continue
            with QtCore.QSignalBlocker(reg):
                reg.text_edit.setPlainText(text)
            break

    def reset_tier(self):
        for reg in self.visible_utterances.values():
            if reg.scene() is not None:
                reg.scene().removeItem(reg)
        self.visible_utterances = {}

    def refresh(self, *args, reset_bounds=False):
        self.hide()
        if self.selection_model.plot_min is None:
            return
        self.has_visible_utterances = False
        self.has_selected_utterances = False
        self.speaker_label.setPos(self.selection_model.plot_min, self.top_point)
        cleanup_ids = []
        model_visible_utterances = self.selection_model.visible_utterances()
        visible_ids = {x.id: x for x in model_visible_utterances}
        for reg in self.visible_utterances.values():
            reg.hide()
            if reset_bounds and reg.item.id in visible_ids:
                with QtCore.QSignalBlocker(reg):
                    reg.item.begin, reg.item.end = (
                        visible_ids[reg.item.id].begin,
                        visible_ids[reg.item.id].end,
                    )
                    reg.setRegion((reg.item.begin, reg.item.end))
                reg.update_edit_fields()

            item_min, item_max = reg.getRegion()
            if (
                self.selection_model.min_time - item_max > 15
                or item_min - self.selection_model.max_time > 15
                or (
                    reg.item.id not in visible_ids
                    and (
                        item_min < self.selection_model.max_time
                        or item_max > self.selection_model.min_time
                    )
                )
            ):
                if reg.scene() is not None:
                    reg.scene().removeItem(reg)
                cleanup_ids.append(reg.item.id)
        self.visible_utterances = {
            k: v for k, v in self.visible_utterances.items() if k not in cleanup_ids
        }
        for u in model_visible_utterances:
            if u.speaker_id != self.speaker_id:
                continue
            if u.id in self.visible_utterances:
                self.visible_utterances[u.id].setSelected(self.selection_model.checkSelected(u.id))
                self.visible_utterances[u.id].show()
                continue
            self.has_visible_utterances = True
            # Utterance region always at the top
            reg = UtteranceRegion(
                self,
                u,
                self.corpus_model,
                self.file_model,
                self.dictionary_model,
                selection_model=self.selection_model,
                extra_tiers=self.extra_tiers,
                available_speakers=self.available_speakers,
                bottom_point=self.bottom_point,
                top_point=self.top_point,
                search_term=self.search_term,
            )
            reg.sigRegionChanged.connect(self.check_utterance_bounds)
            reg.sigRegionChangeFinished.connect(self.update_utterance)
            reg.draggingLine.connect(self.draggingLine.emit)
            reg.sigRegionChangeFinished.connect(self.lineDragFinished.emit)
            reg.undoRequested.connect(self.corpus_model.undoRequested.emit)
            reg.undoRequested.connect(self.corpus_model.undoRequested.emit)
            reg.redoRequested.connect(self.corpus_model.redoRequested.emit)
            reg.playRequested.connect(self.corpus_model.playRequested.emit)
            reg.audioSelected.connect(self.selection_model.select_audio)
            reg.viewRequested.connect(self.selection_model.set_view_times)
            reg.textEdited.connect(self.update_utterance_text)
            reg.phoneBoundaryChanged.connect(self.update_phone_boundaries)
            reg.phoneIntervalChanged.connect(self.update_phone_interval)
            reg.wordPronunciationChanged.connect(self.update_word_pronunciation)
            reg.wordChanged.connect(self.update_word)
            reg.phoneIntervalInserted.connect(self.insert_phone_interval)
            reg.phoneIntervalDeleted.connect(self.delete_phone_interval)
            reg.deleteReferenceAlignments.connect(self.delete_reference_alignments)
            reg.transcribeRequested.connect(self.corpus_model.transcribeRequested.emit)
            reg.selectRequested.connect(self.selection_model.update_select)
            self.visible_utterances[u.id] = reg

        self.show()

    def delete_reference_alignments(self, utterance: Utterance):
        self.selection_model.model().delete_reference_alignments(utterance)

    def update_phone_boundaries(
        self, utterance: Utterance, first_phone_interval, second_phone_interval, new_time: float
    ):
        self.selection_model.model().update_phone_boundaries(
            utterance, first_phone_interval, second_phone_interval, new_time
        )

    def update_phone_interval(self, utterance: Utterance, phone_interval, phone_id):
        self.selection_model.model().update_phone_interval(utterance, phone_interval, phone_id)

    def update_word_pronunciation(
        self, utterance: Utterance, word_interval: WordInterval, pronunciation: Pronunciation
    ):
        self.selection_model.model().update_word_pronunciation(
            utterance, word_interval, pronunciation
        )

    def update_word(
        self, utterance: Utterance, word_interval: WordInterval, word: typing.Union[Word, str]
    ):
        self.selection_model.model().update_word(utterance, word_interval, word)

    def insert_phone_interval(
        self, utterance: Utterance, interval, previous_interval, following_interval, word_interval
    ):
        self.selection_model.model().insert_phone_interval(
            utterance, interval, previous_interval, following_interval, word_interval
        )

    def delete_phone_interval(
        self, utterance: Utterance, interval, previous_interval, following_interval, time_point
    ):
        self.selection_model.model().delete_phone_interval(
            utterance, interval, previous_interval, following_interval, time_point
        )

    def update_utterance_text(self, utterance, new_text):
        self.selection_model.model().update_utterance_text(utterance, text=new_text)

    def update_select(self):
        selected_rows = {x.id for x in self.selection_model.selected_utterances()}
        for r in self.visible_utterances.values():
            if r.item.id in selected_rows:
                r.setSelected(True)
            else:
                r.setSelected(False)

    def check_utterance_bounds(self):
        reg: UtteranceRegion = self.sender()
        with QtCore.QSignalBlocker(reg):
            beg, end = reg.getRegion()
            if self.settings.right_to_left:
                if end > 0:
                    reg.setRegion([beg, 0])
                    return
                if (
                    self.selection_model.model().file is not None
                    and -end > self.selection_model.model().file.duration
                ):
                    reg.setRegion([beg, self.selection_model.model().file.duration])
                    return
            else:
                if beg < 0:
                    reg.setRegion([0, end])
                    return
                if (
                    self.selection_model.model().file is not None
                    and end > self.selection_model.model().file.duration
                ):
                    reg.setRegion([beg, self.selection_model.model().file.duration])
                    return
            prev_r = None
            for r in sorted(self.visible_utterances.values(), key=lambda x: x.item_min):
                if r.item.id == reg.item.id:
                    if reg.initial_line_moving and reg.snap_mode and prev_r is not None:
                        other_begin, other_end = prev_r.getRegion()
                        prev_r.setRegion([other_begin, beg])
                        break
                    continue
                other_begin, other_end = r.getRegion()
                if other_begin <= beg < other_end or beg <= other_begin < other_end < end:
                    if reg.initial_line_moving and reg.snap_mode:
                        r.setRegion([other_begin, beg])
                    else:
                        reg.setRegion([other_end, end])
                    break
                if other_begin < end <= other_end or end > other_begin > other_end > beg:
                    if (
                        False
                        and not reg.initial_line_moving
                        and reg.snap_mode
                        and prev_r is not None
                        and prev_r.item.id == reg.item.id
                    ):
                        r.setRegion([end, other_end])
                    else:
                        reg.setRegion([beg, other_begin])
                    break
                prev_r = r

            reg.update_edit_fields()
        reg.select_self()
        reg.update()

    def update_utterance(self):
        reg = self.sender()
        utt = reg.item

        beg, end = reg.getRegion()
        new_begin = round(beg, 4)
        new_end = round(end, 4)
        if new_begin == utt.begin and new_end == utt.end:
            return
        self.selection_model.model().update_utterance_times(utt, begin=new_begin, end=new_end)
        self.selection_model.request_start_time(new_begin)
        reg.update_edit_fields()
        self.lineDragFinished.emit(True)
