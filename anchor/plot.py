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
from Bio import pairwise2
from line_profiler_pycharm import profile
from montreal_forced_aligner.data import CtmInterval
from montreal_forced_aligner.db import Speaker, Utterance
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

        self.setBackground(self.settings.value(self.settings.PRIMARY_VERY_DARK_COLOR))
        self.corpus_model = None
        self.speaker_model: SpeakerModel = None
        self.selection_model: CorpusSelectionModel = None
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
        self.legend_item.changeCluster.connect(self.change_cluster)
        self.legend_item.setParentItem(self.getPlotItem())
        self.legend_item.setFont(self.settings.font)
        self.selected_indices = set()
        # self.addItem(self.legend_item)
        self.selected_pen = pg.mkPen(self.settings.value(self.settings.MAIN_TEXT_COLOR), width=2)
        self.updated_pen = pg.mkPen(self.settings.value(self.settings.MAIN_TEXT_COLOR), width=2)
        self.hover_pen = pg.mkPen(self.settings.value(self.settings.ACCENT_LIGHT_COLOR), width=2)
        self.base_pen = pg.mkPen(self.settings.value(self.settings.PRIMARY_DARK_COLOR), width=1)
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
        selection_model: CorpusSelectionModel,
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
            self.selection_model.set_current_utterance(utterance_id)
            self.selection_model.current_utterance_id = utterance_id
            self.selection_model.set_current_file(
                utterance.file_id,
                utterance.begin,
                utterance.end,
                utterance.channel,
                force_update=True,
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
            pen=self.base_pen,
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
                pens.append(self.base_pen)
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
        self.setDefaultPadding(0)
        self.setClipToView(True)

        self.getAxis("bottom").setPen(self.settings.value(self.settings.ACCENT_LIGHT_COLOR))
        self.getAxis("bottom").setTextPen(self.settings.value(self.settings.ACCENT_LIGHT_COLOR))
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
        self.audio_layout.centralWidget.layout.setContentsMargins(0, 0, 0, 0)
        self.audio_layout.centralWidget.layout.setSpacing(0)
        self.audio_layout.setBackground(self.settings.value(self.settings.PRIMARY_VERY_DARK_COLOR))
        self.audio_plot = AudioPlots(2, 1, 0)
        self.audio_plot_item = AudioPlotItem(2, 0)
        self.audio_plot_item.addItem(self.audio_plot)
        # self.audio_plot.setZValue(0)
        self.audio_layout.addItem(self.audio_plot_item)

        self.show_all_speakers = False
        self.show_transcription = True
        self.show_alignment = True
        self.speaker_tier_layout = pg.GraphicsLayoutWidget()
        self.speaker_tier_layout.setAspectLocked(False)
        self.speaker_tier_layout.centralWidget.layout.setContentsMargins(0, 0, 0, 0)
        self.speaker_tier_layout.centralWidget.layout.setSpacing(0)
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
        # self.corpus_model.utteranceTextUpdated.connect(self.refresh_utterance_text)
        self.selection_model.resetView.connect(self.reset_plot)
        self.file_model.utterancesReady.connect(self.finalize_loading_utterances)
        self.selection_model.spectrogramReady.connect(self.finalize_loading_spectrogram)
        self.selection_model.pitchTrackReady.connect(self.finalize_loading_pitch_track)
        self.selection_model.waveformReady.connect(self.finalize_loading_auto_wave_form)
        self.selection_model.speakerRequested.connect(self.set_default_speaker)
        self.file_model.selectionRequested.connect(self.finalize_loading_utterances)

    def finalize_loading_utterances(self):
        if self.file_model.file is None:
            return
        scroll_to = None

        self.speaker_tiers = {}
        self.speaker_tier_items = {}
        self.speaker_tier_layout.clear()
        available_speakers = {}
        speaker_tier_height = self.separator_point - self.bottom_point
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
        row_height = self.audio_plot_item.height()
        self.speaker_tier_layout.setFixedHeight(len(self.speaker_tiers) * row_height)
        if len(self.speaker_tiers) > 1:
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
                # self.tier_scroll_area.scrollContentsBy(0, scroll_to * tier_height)
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
        if self.corpus_model.has_alignments and "Words" not in self.extra_tiers:
            self.extra_tiers["Words"] = "aligned_word_intervals"
            self.extra_tiers["Phones"] = "aligned_phone_intervals"
        if self.corpus_model.has_reference_alignments and "Reference" not in self.extra_tiers:
            self.extra_tiers["Reference"] = "reference_phone_intervals"
        if (
            self.corpus_model.has_transcribed_alignments
            and "Transcription" not in self.extra_tiers
        ):
            self.extra_tiers["Transcription"] = "transcription_text"
            self.extra_tiers["Transcribed words"] = "transcribed_word_intervals"
            self.extra_tiers["Transcribed phones"] = "transcribed_phone_intervals"
        if (
            self.corpus_model.has_per_speaker_transcribed_alignments
            and "Transcription" not in self.extra_tiers
        ):
            self.extra_tiers["Transcription"] = "transcription_text"
            self.extra_tiers["Transcribed words"] = "per_speaker_transcribed_word_intervals"
            self.extra_tiers["Transcribed phones"] = "per_speaker_transcribed_phone_intervals"

    def set_search_term(self):
        term = self.corpus_model.text_filter
        if not term:
            return
        self.search_term = term
        for tier in self.speaker_tiers.values():
            tier.setSearchTerm(term)

    def reset_text_grid(self):
        for tier in self.speaker_tiers.values():
            tier.reset_tier()

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
    lookUpWord = QtCore.Signal(object)
    createWord = QtCore.Signal(object)
    lostFocus = QtCore.Signal()

    def __init__(self, dictionary_model, speaker_id, *args):
        super().__init__(*args)
        self.settings = AnchorSettings()
        self.dictionary_model: DictionaryTableModel = dictionary_model
        self.speaker_id = speaker_id
        self.lookUpWord.connect(self.dictionary_model.lookup_word)
        self.createWord.connect(self.dictionary_model.add_word)
        self.setCursor(QtCore.Qt.CursorShape.IBeamCursor)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)

        self.customContextMenuRequested.connect(self.generate_context_menu)

        self.setAcceptRichText(False)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.verticalScrollBar().setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWordWrapMode(QtGui.QTextOption.WrapMode.WordWrap)

    def dragMoveEvent(self, e: QtGui.QDragMoveEvent) -> None:
        e.ignore()

    def dragEnterEvent(self, e: QtGui.QDragMoveEvent) -> None:
        e.ignore()

    def dragLeaveEvent(self, e: QtGui.QDragMoveEvent) -> None:
        e.ignore()

    def focusOutEvent(self, e: QtGui.QFocusEvent) -> None:
        self.lostFocus.emit()
        return super().focusOutEvent(e)

    def generate_context_menu(self, location):
        menu = Menu(self)
        cursor = self.cursorForPosition(location)
        cursor.select(QtGui.QTextCursor.SelectionType.WordUnderCursor)
        word = cursor.selectedText()
        # add extra items to the menu
        menu.addSeparator()
        if self.dictionary_model.check_word(word, speaker_id=self.speaker_id):
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
        # show the menu
        menu.exec_(self.mapToGlobal(location))


class UtterancePGTextItem(pg.TextItem):
    def __init__(
        self,
        begin: float,
        end: float,
        text: str,
        selection_model: CorpusSelectionModel,
        top_point=None,
        bottom_point=None,
        per_tier_range=None,
        color=None,
        font=None,
        html=None,
        anchor=(0, 0),
        border=None,
        fill=None,
        dictionary_model: Optional[DictionaryTableModel] = None,
        speaker_id: int = 0,
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
        self.text_edit = TextEdit(dictionary_model, speaker_id)
        self.text_edit.cursorPositionChanged.connect(self.update)

        # self.text_edit.setAutoFillBackground(False)
        # self.text_edit.viewport().setAutoFillBackground(False)
        self.textItem = QtWidgets.QGraphicsProxyWidget(self)
        self.textItem.setWidget(self.text_edit)
        self._lastTransform = None
        self._lastScene = None
        self._bounds = QtCore.QRectF()
        if font:
            self.text_edit.setFont(font)
        self.text_edit.setPlainText(text)
        self.fill = pg.mkBrush(fill)
        self.border = pg.mkPen(border)
        self._cached_pixel_size = None
        self.cached_duration = None
        self.top_point = top_point
        self.bottom_point = bottom_point
        self.per_tier_range = per_tier_range
        self.view_min = self.selection_model.plot_min
        self.view_max = self.selection_model.plot_max
        self.selection_model.viewChanged.connect(self.update_times)

    def update_times(self, begin, end):
        self.view_min = begin
        self.view_max = end
        if self.end <= self.view_min or self.begin >= self.view_max:
            return
        self.hide()
        if (
            self.view_min <= self.begin < self.view_max
            or self.view_max >= self.end > self.view_min
            or (self.begin <= self.view_min and self.end >= self.view_max)
        ):
            self.show()

    def boundingRect(self):
        br = QtCore.QRectF(self.viewRect())  # bounds of containing ViewBox mapped to local coords.
        vb = self.getViewBox()
        if self.begin is None or self.view_min is None:
            return br
        visible_begin = max(self.begin, self.view_min)
        visible_end = min(self.end, self.view_max)

        br.setLeft(visible_begin)
        br.setRight(visible_end)

        br.setTop(self.top_point)
        # br.setBottom(self.top_point-self.per_tier_range)
        br.setBottom(self.bottom_point)
        duration = visible_end - visible_begin
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

        # self.text_edit.setAutoFillBackground(False)
        # self.text_edit.viewport().setAutoFillBackground(False)
        self.textItem = QtWidgets.QGraphicsProxyWidget(self)
        self.textItem.setWidget(self.text_edit)
        self._lastTransform = None
        self._lastScene = None
        self._bounds = QtCore.QRectF()
        if font:
            self.text_edit.setFont(font)
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
        self.keyword_color = self.settings.error_color
        self.keyword_text_color = self.settings.primary_very_dark_color
        self.highlight_format = QtGui.QTextCharFormat()
        self.highlight_format.setBackground(self.keyword_color)
        self.highlight_format.setForeground(self.keyword_text_color)
        self.search_term = None

    def setSearchTerm(self, search_term: TextFilterQuery):
        if search_term != self.search_term:
            self.search_term = search_term
            self.rehighlight()

    def set_alignment(self, alignment):
        self.alignment = alignment

    def highlightBlock(self, text):
        if not self.alignment:
            return
        current_align_ind = 0
        for word_object in re.finditer(self.WORDS, text):
            while self.alignment.seqB[current_align_ind] != word_object.group():
                current_align_ind += 1
            sb = self.alignment.seqB[current_align_ind]
            sa = self.alignment.seqA[current_align_ind]
            if sb == word_object.group() and sb != sa:
                self.setFormat(
                    word_object.start(),
                    word_object.end() - word_object.start(),
                    self.highlight_format,
                )
                current_align_ind += 1
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
        interval: CtmInterval,
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
        self.text = TextItem(text, color=color, anchor=(0.5, 0.5))
        self.text.setParentItem(self)

        self.font = font
        self.text.textItem.setFont(font)
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
        self.text.setPos(
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
    audioSelected = QtCore.Signal(object, object)

    def __init__(
        self,
        parent,
        begin: float,
        end: float,
        text: str,
        top_point,
        height,
        selection_model: CorpusSelectionModel,
        border=None,
        dictionary_model=None,
        speaker_id=None,
    ):
        super().__init__()
        self.begin = begin
        self.end = end
        self.text = text
        self.border = border
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
        self.text = UtterancePGTextItem(
            self.begin,
            self.end,
            self.text,
            self.selection_model,
            anchor=(0, 0),
            top_point=self.top_point,
            bottom_point=self.bottom_point,
            per_tier_range=self.height,
            dictionary_model=self.dictionary_model,
            font=self.parentItem().settings.font,
            speaker_id=self.speaker_id,
            color=self.parentItem().text_color,
            border=pg.mkPen(self.parentItem().settings.accent_light_color),
        )
        self.text.setFont(self.parentItem().plot_text_font)
        self.text.setParentItem(self)
        self.text_edit = self.text.text_edit
        self.text_edit.setReadOnly(True)
        self.text_edit.setViewportMargins(
            self.parentItem().text_margin_pixels,
            self.parentItem().text_margin_pixels,
            self.parentItem().text_margin_pixels,
            self.parentItem().text_margin_pixels,
        )
        self.text_edit.setStyleSheet(self.parentItem().settings.interval_style_sheet)

        self.picture = QtGui.QPicture()
        self.mouseHovering = False
        self.selected = False
        self.currentBrush = self.parentItem().background_brush
        self.text.setPos((self.begin + self.end) / 2, self.top_point - (self.height / 2))
        self.begin_line = pg.InfiniteLine()
        self.rect = QtCore.QRectF(
            left=self.begin,
            top=self.top_point,
            width=self.end - self.begin,
            height=self.height,
        )
        self.rect.setTop(self.top_point)
        self.rect.setBottom(self.top_point - self.height)
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
        self.audioSelected.emit(self.begin, self.end)
        ev.accept()

    def boundingRect(self):
        br = QtCore.QRectF(self.picture.boundingRect())
        return br

    def paint(self, painter: QtGui.QPainter, *args):
        painter.drawPicture(0, 0, self.picture)


class TranscriberTextRegion(TextAttributeRegion):
    viewRequested = QtCore.Signal(object, object)
    audioSelected = QtCore.Signal(object, object)

    def __init__(
        self,
        parent,
        begin: float,
        end: float,
        text: str,
        top_point,
        height,
        selection_model: CorpusSelectionModel,
        border=None,
        dictionary_model=None,
        speaker_id=None,
        alignment=None,
        search_term=None,
    ):
        super().__init__(
            parent,
            begin,
            end,
            text,
            top_point,
            height,
            selection_model,
            border,
            dictionary_model,
            speaker_id,
        )

        self.highlighter = TranscriberErrorHighlighter(self.text_edit.document())
        if alignment is not None:
            self.highlighter.set_alignment(alignment)
        if search_term:
            self.highlighter.setSearchTerm(search_term)


class NormalizedTextRegion(TextAttributeRegion):
    viewRequested = QtCore.Signal(object, object)
    audioSelected = QtCore.Signal(object, object)

    def __init__(
        self,
        parent,
        begin: float,
        end: float,
        text: str,
        top_point,
        height,
        selection_model: CorpusSelectionModel,
        border=None,
        dictionary_model=None,
        search_term=None,
        speaker_id=None,
    ):
        super().__init__(
            parent,
            begin,
            end,
            text,
            top_point,
            height,
            selection_model,
            border,
            dictionary_model,
            speaker_id,
        )

        self.highlighter = Highlighter(self.text_edit.document())
        self.highlighter.set_models(dictionary_model)
        self.highlighter.set_speaker(speaker_id)
        if search_term:
            self.highlighter.setSearchTerm(search_term)


class Highlighter(QtGui.QSyntaxHighlighter):
    WORDS = r"\S+"

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
        if self.dictionary_model is not None and self.dictionary_model.word_sets:
            for word_object in re.finditer(self.WORDS, text):
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

    settings = AnchorSettings()

    @profile
    def __init__(
        self,
        item: CtmInterval,
        corpus_model: CorpusModel,
        file_model: FileUtterancesModel,
        dictionary_model: typing.Optional[DictionaryTableModel],
        selection_model: FileSelectionModel,
        bottom_point: float = 0,
        top_point: float = 1,
    ):
        pg.GraphicsObject.__init__(self)
        self.item = item

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

        self.selected_range_color = self.settings.value(self.settings.PRIMARY_BASE_COLOR).lighter()
        self.interval_background_color = self.settings.value(self.settings.PRIMARY_DARK_COLOR)
        self.hover_line_color = self.settings.value(self.settings.ERROR_COLOR)
        self.moving_line_color = self.settings.value(self.settings.ERROR_COLOR)

        self.break_line_color = self.settings.value(self.settings.ACCENT_LIGHT_COLOR)
        self.text_color = self.settings.value(self.settings.MAIN_TEXT_COLOR)
        self.selected_interval_color = self.settings.value(self.settings.PRIMARY_BASE_COLOR)
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
        self.setBrush(self.background_brush)
        self.movable = False
        self.cached_visible_duration = None
        self.cached_view = None

    def paint(self, p, *args):
        p.setBrush(self.currentBrush)
        p.setPen(self.border_pen)
        p.drawRect(self.boundingRect())

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
            self.setBrush(pg.mkBrush(self.selected_interval_color))
        else:
            # self.interval_background_color.setAlpha(0)
            self.setBrush(pg.mkBrush(self.interval_background_color))
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


class AlignmentRegion(MfaRegion):
    @profile
    def __init__(
        self,
        phone_interval: CtmInterval,
        corpus_model: CorpusModel,
        file_model: FileUtterancesModel,
        selection_model: CorpusSelectionModel,
        bottom_point: float = 0,
        top_point: float = 1,
    ):
        super().__init__(
            phone_interval,
            corpus_model,
            file_model,
            None,
            selection_model,
            bottom_point,
            top_point,
        )
        self.original_text = self.item.label

        self.text = pg.TextItem(
            self.item.label, anchor=(0.5, 0.5), color=self.text_color  # , border=pg.mkColor("r")
        )
        self.text.setVisible(False)

        self.text.setFont(self.settings.font)
        options = QtGui.QTextOption()
        options.setWrapMode(QtGui.QTextOption.WrapMode.NoWrap)
        self.text.textItem.document().setDefaultTextOption(options)
        self.text.setParentItem(self)
        self.per_tier_range = self.top_point - self.bottom_point

    def viewRangeChanged(self):
        if (self.item_max - self.item_min) / (
            self.selection_model.max_time - self.selection_model.min_time
        ) < 0.001:
            self.hide()
        else:
            self.show()
        super().viewRangeChanged()

    def boundingRect(self):
        br = QtCore.QRectF(self.viewRect())  # bounds of containing ViewBox mapped to local coords.
        vb = self.getViewBox()

        pixel_size = vb.viewPixelSize()

        br.setLeft(self.item_min)
        br.setRight(self.item_max)

        br.setTop(self.top_point)
        # br.setBottom(self.top_point-self.per_tier_range)
        br.setBottom(self.bottom_point + 0.01)
        try:
            visible_begin = max(self.item_min, self.selection_model.plot_min)
            visible_end = min(self.item_max, self.selection_model.plot_max)
        except TypeError:
            return br
        visible_duration = visible_end - visible_begin
        x_margin_px = 8
        available_text_width = visible_duration / pixel_size[0] - (2 * x_margin_px)
        self.text.setVisible(available_text_width > 10)
        if visible_duration != self.cached_visible_duration:
            self.cached_visible_duration = visible_duration

            self.text.setPos(
                visible_begin + (visible_duration / 2), self.top_point - (self.per_tier_range / 2)
            )
        br = br.normalized()

        if self._boundingRectCache != br:
            self._boundingRectCache = br
            self.prepareGeometryChange()
        return br


class PhoneRegion(AlignmentRegion):
    def __init__(
        self,
        phone_interval: CtmInterval,
        corpus_model: CorpusModel,
        file_model: FileUtterancesModel,
        selection_model: CorpusSelectionModel,
        bottom_point: float = 0,
        top_point: float = 1,
    ):
        super().__init__(
            phone_interval, corpus_model, file_model, selection_model, bottom_point, top_point
        )


class WordRegion(AlignmentRegion):
    highlightRequested = QtCore.Signal(object)

    def __init__(
        self,
        word_interval: CtmInterval,
        corpus_model: CorpusModel,
        file_model: FileUtterancesModel,
        selection_model: CorpusSelectionModel,
        bottom_point: float = 0,
        top_point: float = 1,
    ):
        super().__init__(
            word_interval, corpus_model, file_model, selection_model, bottom_point, top_point
        )

    def mouseClickEvent(self, ev: QtGui.QMouseEvent):
        search_term = TextFilterQuery(self.item.label, word=True)
        self.highlightRequested.emit(search_term)
        super().mouseClickEvent(ev)


class UtteranceRegion(MfaRegion):
    @profile
    def __init__(
        self,
        utterance: workers.UtteranceData,
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

        for line in self.lines:
            line.setZValue(30)
            line.setParentItem(self)
            line.sigPositionChangeFinished.connect(self.lineMoveFinished)
        self.lines[0].sigPositionChanged.connect(self._line0Moved)
        self.lines[1].sigPositionChanged.connect(self._line1Moved)
        self.lines[0].hoverChanged.connect(self.popup)
        self.lines[1].hoverChanged.connect(self.popup)

        self.corpus_model.utteranceTextUpdated.connect(self.update_text_from_model)
        self.original_text = self.item.text
        self.text = UtterancePGTextItem(
            self.item.begin,
            self.item.end,
            self.item.text,
            self.selection_model,
            anchor=(0, 0),
            top_point=self.top_point,
            bottom_point=self.bottom_point,
            per_tier_range=self.per_tier_range,
            dictionary_model=self.dictionary_model,
            font=self.settings.font,
            speaker_id=self.item.speaker_id,
            color=self.text_color,
            border=pg.mkPen(self.settings.accent_light_color),
        )
        self.text.setFont(self.plot_text_font)
        self.text.setParentItem(self)

        self.text_edit = self.text.text_edit
        if not self.corpus_model.editable:
            self.text_edit.setReadOnly(True)
        self.corpus_model.editableChanged.connect(self.change_editing)
        self.text_edit.setViewportMargins(
            self.text_margin_pixels,
            self.text_margin_pixels,
            self.text_margin_pixels,
            self.text_margin_pixels,
        )
        self.text_edit.setStyleSheet(self.settings.interval_style_sheet)
        self.text_edit.installEventFilter(self)
        self.highlighter = Highlighter(self.text_edit.document())
        self.highlighter.set_models(dictionary_model)
        self.highlighter.set_speaker(self.item.speaker_id)
        if search_term:
            self.highlighter.setSearchTerm(search_term)
        self.timer = QtCore.QTimer()
        self.text_edit.textChanged.connect(self.refresh_timer)
        self.text_edit.lostFocus.connect(self.save_changes)
        self.timer.timeout.connect(self.save_changes)
        self._cached_pixel_size = None
        self.normalized_text = None
        i = -1
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
                    border=pg.mkPen(self.settings.accent_light_color),
                    dictionary_model=dictionary_model,
                    search_term=search_term,
                    speaker_id=utterance.speaker_id,
                )
                continue
            alignment = None
            intervals = getattr(self.item, lookup)
            if lookup in {"transcription_text", "normalized_text"}:
                if (
                    lookup == "transcription_text"
                    and self.item.text
                    and self.item.transcription_text
                ):
                    alignment = pairwise2.align.globalms(
                        self.item.text.split(),
                        self.item.transcription_text.split(),
                        0,
                        -2,
                        -1,
                        -1,
                        gap_char=["-"],
                        one_alignment_only=True,
                    )[0]

            self.extra_tier_intervals[tier_name] = []

            if intervals is None:
                continue
            for interval in intervals:
                # if (interval.end - interval.begin) /(self.selection_model.max_time -self.selection_model.min_time) < 0.01:
                #    continue
                if lookup == "transcription_text":
                    interval_reg = TranscriberTextRegion(
                        self,
                        self.item.begin,
                        self.item.end,
                        self.item.transcription_text,
                        tier_top_point,
                        self.per_tier_range,
                        self.selection_model,
                        border=pg.mkPen(self.settings.accent_light_color),
                        alignment=alignment,
                        dictionary_model=dictionary_model,
                        search_term=search_term,
                        speaker_id=utterance.speaker_id,
                    )
                elif "phone_intervals" in lookup:
                    interval_reg = PhoneRegion(
                        interval,
                        self.corpus_model,
                        self.file_model,
                        selection_model=selection_model,
                        top_point=tier_top_point,
                        bottom_point=tier_bottom_point,
                    )
                    interval_reg.setParentItem(self)
                elif "word_intervals" in lookup:
                    interval_reg = WordRegion(
                        interval,
                        self.corpus_model,
                        self.file_model,
                        selection_model=selection_model,
                        top_point=tier_top_point,
                        bottom_point=tier_bottom_point,
                    )
                    interval_reg.setParentItem(self)
                    interval_reg.highlightRequested.connect(self.highlighter.setSearchTerm)

                else:
                    interval_reg = IntervalTextRegion(
                        interval,
                        self.text_color,
                        border=pg.mkPen(self.settings.accent_light_color, width=3),
                        top_point=tier_top_point,
                        height=self.per_tier_range,
                        font=self.settings.font,
                        background_brush=self.background_brush,
                        selected_brush=pg.mkBrush(self.selected_range_color),
                    )
                    interval_reg.setParentItem(self)

                interval_reg.audioSelected.connect(self.audioSelected.emit)
                interval_reg.viewRequested.connect(self.viewRequested.emit)
                self.extra_tier_intervals[tier_name].append(interval_reg)
        self.selection_model.viewChanged.connect(self.update_view_times)
        self.show()
        self.available_speakers = available_speakers

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

    def contextMenuEvent(self, ev: QtWidgets.QGraphicsSceneContextMenuEvent):
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
        menu.exec_(ev.screenPos())

    def update_tier_visibility(self, checked):
        tier_name = self.sender().text().split(maxsplit=1)[-1]
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
        speaker_name = self.sender().text()
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
        with QtCore.QSignalBlocker(self.text.text_edit):
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

    def save_changes(self):
        text = self.text_edit.toPlainText()
        self.timer.stop()
        if self.original_text == text:
            return
        self.original_text = text
        self.textEdited.emit(self.item, text)


class WaveForm(pg.PlotCurveItem):
    def __init__(self, bottom_point, top_point):
        self.settings = AnchorSettings()
        self.top_point = top_point
        self.bottom_point = bottom_point
        self.mid_point = (self.top_point + self.bottom_point) / 2
        pen = pg.mkPen(self.settings.value(self.settings.MAIN_TEXT_COLOR), width=1)
        super(WaveForm, self).__init__()
        self.setPen(pen)
        self.channel = 0
        self.y = None
        self.selection_model = None
        self.setAcceptHoverEvents(False)

    def hoverEvent(self, ev):
        return

    def set_models(self, selection_model: CorpusSelectionModel):
        self.selection_model = selection_model


class PitchTrack(pg.PlotCurveItem):
    def __init__(self, bottom_point, top_point):
        self.settings = AnchorSettings()
        self.top_point = top_point
        self.bottom_point = bottom_point
        self.mid_point = (self.top_point + self.bottom_point) / 2
        pen = pg.mkPen(self.settings.value(self.settings.PRIMARY_LIGHT_COLOR), width=3)
        super().__init__()
        self.setPen(pen)
        self.channel = 0
        self.y = None
        self.selection_model = None
        self.setAcceptHoverEvents(False)
        self.min_label = pg.TextItem(
            str(self.settings.PITCH_MIN_F0),
            self.settings.value(self.settings.PRIMARY_VERY_LIGHT_COLOR),
            anchor=(1, 1),
        )
        self.min_label.setFont(self.settings.font)
        self.min_label.setParentItem(self)
        self.max_label = pg.TextItem(
            str(self.settings.PITCH_MAX_F0),
            self.settings.value(self.settings.PRIMARY_VERY_LIGHT_COLOR),
            anchor=(1, 0),
        )
        self.max_label.setFont(self.settings.font)
        self.max_label.setParentItem(self)

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
        self.top_point = top_point
        self.bottom_point = bottom_point
        self.selection_model = None
        self.channel = 0
        super(Spectrogram, self).__init__()
        self.cmap = pg.ColorMap(
            None, [self.settings.primary_very_dark_color, self.settings.accent_light_color]
        )
        self.cmap.linearize()
        self.color_bar = pg.ColorBarItem(colorMap=self.cmap)
        self.color_bar.setImageItem(self)
        self.setAcceptHoverEvents(False)
        self.cached_begin = None
        self.cached_end = None
        self.cached_channel = None
        self.stft = None

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
            self.lines[0].label.setText(f"{begin:.3f}", self.settings.error_color)
            self.lines[1].label.setText(f"{end:.3f}", self.settings.error_color)
            self.setVisible(True)


class AudioPlots(pg.GraphicsObject):
    def __init__(self, top_point, separator_point, bottom_point):
        super().__init__()
        self.settings = AnchorSettings()
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
        color = self.settings.error_color
        color.setAlphaF(0.25)
        self.selection_brush = pg.mkBrush(color)
        self.background_pen = pg.mkPen(self.settings.accent_light_color)
        self.background_brush = pg.mkBrush(self.settings.primary_very_dark_color)
        self.selection_area = SelectionArea(
            top_point=self.top_point,
            bottom_point=self.bottom_point,
            brush=self.selection_brush,
            clipItem=self,
            pen=pg.mkPen(self.settings.error_color),
        )
        self.selection_area.setParentItem(self)

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
            pen=pg.mkPen(self.settings.error_color, width=3, style=QtCore.Qt.PenStyle.DashLine),
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
            self.selection_model.request_start_time(ev.pos().x())
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

    def update_play_line(self, time):
        if time is None:
            return
        self.play_line.setPos(time)

    def update_plot(self):
        if (
            self.selection_model.model().file is None
            or self.selection_model.model().file.sound_file is None
            or not os.path.exists(self.selection_model.model().file.sound_file.sound_file_path)
        ):
            return
        self.rect.setLeft(self.selection_model.plot_min)
        self.rect.setRight(self.selection_model.plot_max)
        self._generate_picture()
        self.update_play_line(self.selection_model.plot_min)
        self.selection_area.update_region()
        self.update()


class SpeakerTier(pg.GraphicsObject):
    receivedWheelEvent = QtCore.Signal(object)
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
        self.search_term = search_term
        self.speaker_id = speaker_id
        self.speaker_name = speaker_name
        self.speaker_index = 0
        self.top_point = top_point
        self.speaker_label = pg.TextItem(self.speaker_name, color=self.settings.accent_base_color)
        self.speaker_label.setFont(self.settings.font)
        self.speaker_label.setParentItem(self)
        self.speaker_label.setZValue(40)
        self.bottom_point = bottom_point
        self.annotation_range = self.top_point - self.bottom_point
        self.extra_tiers = {}
        self.visible_utterances: dict[str, UtteranceRegion] = {}
        self.background_brush = pg.mkBrush(self.settings.primary_very_dark_color)
        self.border = pg.mkPen(self.settings.accent_light_color)
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

    def wheelEvent(self, ev):
        self.receivedWheelEvent.emit(ev)

    def mouseClickEvent(self, ev):
        if ev.button() != QtCore.Qt.MouseButton.RightButton:
            ev.ignore()
            return
        x = ev.pos().x()
        begin = max(x - 0.5, 0)
        end = min(x + 0.5, self.selection_model.model().file.duration)
        for x in self.visible_utterances.values():
            if begin >= x.item_min and end <= x.item_max:
                ev.accept()
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
            a.triggered.connect(functools.partial(self.create_utterance, begin=begin, end=end))
            menu.addAction(a)
            menu.setStyleSheet(self.settings.menu_style_sheet)
            menu.exec_(ev.screenPos())

    def contextMenuEvent(self, ev):
        x = ev.pos().x()
        begin = max(x - 0.5, 0)
        end = min(x + 0.5, self.selection_model.model().file.duration)
        for x in self.visible_utterances.values():
            if begin >= x.item_min and end <= x.item_max:
                ev.accept()
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
            a.triggered.connect(functools.partial(self.create_utterance, begin=begin, end=end))
            menu.addAction(a)
            menu.setStyleSheet(self.settings.menu_style_sheet)
            menu.exec_(ev.screenPos())

    def create_utterance(self, begin, end):
        self.file_model.create_utterance(self.speaker_id, begin, end)

    def setSearchterm(self, term):
        self.search_term = term
        for reg in self.visible_utterances.values():
            reg.highlighter.setSearchTerm(term)

    def boundingRect(self):
        return QtCore.QRectF(self.picture.boundingRect())

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def _generate_picture(self):
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
            utt.highlighter.setSearchTerm(term)

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

    @profile
    def refresh(self, *args):
        self.hide()
        if self.selection_model.plot_min is None:
            return
        # self.rect.setLeft(self.selection_model.plot_min)
        # self.rect.setRight(self.selection_model.plot_max)
        # self._generate_picture()
        self.has_visible_utterances = False
        self.has_selected_utterances = False
        self.speaker_label.setPos(self.selection_model.plot_min, self.top_point)
        cleanup_ids = []
        model_visible_utterances = self.selection_model.visible_utterances()
        visible_ids = [x.id for x in model_visible_utterances]
        for reg in self.visible_utterances.values():
            reg.hide()
            if (
                self.selection_model.min_time - reg.item.end > 15
                or reg.item.begin - self.selection_model.max_time > 15
                or (
                    reg.item.id not in visible_ids
                    and (
                        reg.item.begin < self.selection_model.max_time
                        or reg.item.end > self.selection_model.min_time
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
            reg.lines[0].sigPositionChanged.connect(self.draggingLine.emit)
            reg.lines[0].sigPositionChangeFinished.connect(self.lineDragFinished.emit)
            reg.lines[1].sigPositionChanged.connect(self.draggingLine.emit)
            reg.lines[0].sigPositionChangeFinished.connect(self.lineDragFinished.emit)
            reg.undoRequested.connect(self.corpus_model.undoRequested.emit)
            reg.undoRequested.connect(self.corpus_model.undoRequested.emit)
            reg.redoRequested.connect(self.corpus_model.redoRequested.emit)
            reg.playRequested.connect(self.corpus_model.playRequested.emit)
            reg.audioSelected.connect(self.selection_model.select_audio)
            reg.viewRequested.connect(self.selection_model.set_view_times)
            reg.textEdited.connect(self.update_utterance_text)
            reg.selectRequested.connect(self.selection_model.update_select)
            reg.setParentItem(self)
            self.visible_utterances[u.id] = reg

        self.show()

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
        reg = self.sender()
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
            for r in self.visible_utterances.values():
                if r == reg:
                    continue
                other_begin, other_end = r.getRegion()
                if other_begin <= beg < other_end:
                    reg.setRegion([other_end, end])
                    break
                if other_begin < end <= other_end:
                    reg.setRegion([beg, other_begin])
                    break
            reg.text.begin, reg.text.end = reg.getRegion()
            reg.text.update_times(self.selection_model.plot_min, self.selection_model.plot_max)
            if reg.normalized_text is not None:
                reg.normalized_text.text.begin, reg.normalized_text.text.end = reg.getRegion()
                reg.normalized_text.text.update_times(
                    self.selection_model.plot_min, self.selection_model.plot_max
                )
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
        self.selection_model.select_audio(new_begin, None)
        reg.text.begin = new_begin
        reg.text.end = new_end
        reg.update()
        self.lineDragFinished.emit(True)
