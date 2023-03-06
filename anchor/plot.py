from __future__ import annotations

import logging
import os.path
import re
import typing
from threading import Lock
from typing import Optional

import numpy as np
import pyqtgraph as pg
import sqlalchemy
from Bio import pairwise2
from montreal_forced_aligner.data import CtmInterval, WorkflowType
from montreal_forced_aligner.db import CorpusWorkflow, Speaker, Utterance
from PySide6 import QtCore, QtGui, QtWidgets

from anchor import workers
from anchor.models import (
    CorpusModel,
    CorpusSelectionModel,
    DictionaryTableModel,
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
        self.speaker_model = None
        self.selection_model = None
        self.brushes = {-1: pg.mkBrush(0.5)}
        self.scatter_item = ScatterPlot()
        self.scatter_item.selectPoints.connect(self.update_selection)
        self.addItem(self.scatter_item)
        self.hideButtons()
        self.getPlotItem().setDefaultPadding(0)
        self.getPlotItem().hideAxis("left")
        self.getPlotItem().hideAxis("bottom")
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
        self.highlight_pen = pg.mkPen(self.settings.value(self.settings.MAIN_TEXT_COLOR), width=3)
        self.hover_pen = pg.mkPen(self.settings.value(self.settings.ACCENT_LIGHT_COLOR), width=3)
        self.base_pen = pg.mkPen(0.5)
        self.selection_timer = QtCore.QTimer()
        self.selection_timer.setInterval(300)
        self.selection_timer.timeout.connect(self.send_selection_update)
        self.brush_needs_update = False

    def send_selection_update(self):
        self.selection_timer.stop()
        self.selectionUpdated.emit()

    def change_cluster(self, cluster_id):
        if not self.selected_indices:
            return
        self.speaker_model.cluster_labels[np.array(list(self.selected_indices))] = cluster_id
        brushes = [self.brushes[x] for x in self.speaker_model.cluster_labels]
        self.scatter_item.setBrush(brushes)

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

    def update_point(self, sender, spots, ev: pg.GraphicsScene.mouseEvents.MouseClickEvent):
        spot = spots[0]
        index = spot._index
        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            utterance_id = int(self.speaker_model.utterance_ids[index])
            utterance = self.corpus_model.session.query(Utterance).get(utterance_id)
            self.selection_model.set_current_file(
                utterance.file_id,
                utterance.begin,
                utterance.end,
                utterance.channel,
                force_update=True,
            )
        else:
            current_cluster = self.speaker_model.cluster_labels[index]
            current_cluster += 1
            if current_cluster >= self.speaker_model.num_clusters:
                current_cluster = -1
            self.speaker_model.cluster_labels[index] = current_cluster
            spot.setBrush(self.brushes[current_cluster])
        ev.accept()

    def update_plot(self):
        self.legend_item.clear()
        if self.speaker_model.mds is None or self.speaker_model.cluster_labels is None:
            self.scatter_item.clear()
            return
        self.brushes = {-1: pg.mkBrush(0.5)}
        for i in range(self.speaker_model.num_clusters):
            self.brushes[i] = pg.mkBrush(pg.intColor(i, self.speaker_model.num_clusters))
        for k, v in self.brushes.items():
            if k < 0:
                label = "Noise"
            else:
                label = f"Cluster {k}"
            self.legend_item.addItem(pg.ScatterPlotItem(brush=v, name=label), label)
        brushes = [self.brushes[x] for x in self.speaker_model.cluster_labels]
        self.scatter_item.setData(
            pos=self.speaker_model.mds,
            size=10,
            brush=brushes,
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
                pens.append(self.highlight_pen)
            else:
                pens.append(self.base_pen)
        self.scatter_item.setPen(pens)


class AudioPlotItem(pg.PlotItem):
    def __init__(self, top_point, bottom_point):
        super().__init__()
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


class UtteranceView(QtWidgets.QWidget):
    undoRequested = QtCore.Signal()
    redoRequested = QtCore.Signal()
    playRequested = QtCore.Signal()

    def __init__(self, *args):
        super().__init__(*args)
        self.settings = AnchorSettings()
        self.corpus_model: typing.Optional[CorpusModel] = None
        self.selection_model: typing.Optional[CorpusSelectionModel] = None
        layout = QtWidgets.QVBoxLayout()
        self.bottom_point = 0
        self.top_point = 8
        self.height = self.top_point - self.bottom_point
        self.separator_point = (self.height / 2) + self.bottom_point
        self.waveform_worker = workers.WaveformWorker()
        self.auto_waveform_worker = workers.AutoWaveformWorker()
        self.spectrogram_worker = workers.SpectrogramWorker()
        self.pitch_track_worker = workers.PitchWorker()
        self.speaker_tier_worker = workers.SpeakerTierWorker()
        self.waveform_worker.signals.result.connect(self.finalize_loading_wave_form)
        self.auto_waveform_worker.signals.result.connect(self.finalize_loading_auto_wave_form)
        self.spectrogram_worker.signals.result.connect(self.finalize_loading_spectrogram)
        self.pitch_track_worker.signals.result.connect(self.finalize_loading_pitch_track)
        self.speaker_tier_worker.signals.result.connect(self.finalize_loading_utterances)
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
        self.search_term = None
        self.lock = Lock()
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

    def clean_up_for_close(self):
        self.spectrogram_worker.stop()
        self.pitch_track_worker.stop()
        self.waveform_worker.stop()
        self.auto_waveform_worker.stop()
        self.speaker_tier_worker.stop()

    def set_models(
        self,
        corpus_model: CorpusModel,
        selection_model: CorpusSelectionModel,
        dictionary_model: DictionaryTableModel,
    ):
        self.corpus_model = corpus_model
        self.corpus_model.corpusLoaded.connect(self.set_extra_tiers)
        self.corpus_model.refreshTiers.connect(self.set_up_new_file)
        self.selection_model = selection_model
        self.dictionary_model = dictionary_model
        for t in self.speaker_tiers.values():
            t.set_models(corpus_model, selection_model, dictionary_model)
        self.audio_plot.set_models(self.selection_model)
        self.selection_model.viewChanged.connect(self.update_plot)
        # self.corpus_model.utteranceTextUpdated.connect(self.refresh_utterance_text)
        self.selection_model.fileChanged.connect(self.set_up_new_file)
        self.selection_model.channelChanged.connect(self.update_channel)
        self.selection_model.resetView.connect(self.reset_plot)

    def finalize_loading_utterances(self, results):
        utterances, file_id = results
        if (
            self.selection_model.current_file is None
            or file_id != self.selection_model.current_file.id
        ):
            return
        self.speaker_tiers = {}
        self.speaker_tier_items = {}
        self.speaker_tier_layout.clear()
        available_speakers = {}
        for u in utterances:
            if u.speaker_id not in self.speaker_tiers:
                tier = SpeakerTier(
                    self.bottom_point,
                    self.separator_point,
                    u.speaker,
                    search_term=self.search_term,
                )
                tier.dragFinished.connect(self.update_selected_speaker)
                tier.draggingLine.connect(self.audio_plot.update_drag_line)
                tier.lineDragFinished.connect(self.audio_plot.hide_drag_line)
                tier.receivedWheelEvent.connect(self.audio_plot.wheelEvent)
                tier.set_models(self.corpus_model, self.selection_model, self.dictionary_model)
                tier.set_extra_tiers(self.extra_tiers)
                tier.setZValue(30)
                available_speakers[u.speaker.name] = u.speaker_id
                self.speaker_tiers[u.speaker_id] = tier
            self.speaker_tiers[u.speaker_id].utterances.append(u)
        for i, (key, tier) in enumerate(self.speaker_tiers.items()):
            tier.set_speaker_index(0, 1)
            tier.set_available_speakers(available_speakers)
            tier.refresh()
            tier_item = SpeakerTierItem(self.bottom_point, self.separator_point)
            tier_item.setRange(
                xRange=[self.selection_model.min_time, self.selection_model.max_time]
            )
            tier_item.addItem(tier)
            self.speaker_tier_items[key] = tier_item
            self.speaker_tier_layout.addItem(tier_item, i, 0)
        row_height = self.audio_plot_item.height()
        if len(self.speaker_tiers) > 1 and len(self.extra_tiers) < 2:
            row_height = int(row_height / 2)
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
        else:
            self.audio_layout.centralWidget.layout.setContentsMargins(0, 0, 0, 0)
            self.tier_scroll_area.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )

    def finalize_loading_wave_form(self, results):
        y, file_path = results
        if (
            self.selection_model.current_file is None
            or file_path != self.selection_model.current_file.sound_file.sound_file_path
        ):
            return
        self.audio_plot.wave_form.y = y
        self.get_latest_waveform()

    def finalize_loading_spectrogram(self, results):
        stft, channel, begin, end, min_db, max_db = results
        if begin != self.selection_model.min_time or end != self.selection_model.max_time:
            return
        self.audio_plot.spectrogram.setData(stft, channel, begin, end, min_db, max_db)

    def finalize_loading_pitch_track(self, results):
        pitch_track, voicing_track, channel, begin, end, min_f0, max_f0 = results
        if begin != self.selection_model.min_time or end != self.selection_model.max_time:
            return
        if pitch_track is None:
            return
        x = np.linspace(
            start=self.selection_model.min_time,
            stop=self.selection_model.max_time,
            num=pitch_track.shape[0],
        )
        self.audio_plot.pitch_track.setData(x=x, y=pitch_track, connect="finite")
        self.audio_plot.pitch_track.set_range(min_f0, max_f0, end)
        self.audio_plot.pitch_track.show()

    def finalize_loading_auto_wave_form(self, results):
        y, begin, end, channel = results
        if begin != self.selection_model.min_time or end != self.selection_model.max_time:
            return
        x = np.linspace(
            start=self.selection_model.min_time, stop=self.selection_model.max_time, num=y.shape[0]
        )
        self.audio_plot.wave_form.setData(x=x, y=y)
        self.audio_plot.wave_form.show()

    def get_utterances(self):
        for tier in self.speaker_tiers.values():
            tier.reset_tier()
            self.speaker_tier_layout.removeItem(tier)
        if self.selection_model.current_file is None:
            return
        self.speaker_tier_worker.stop()
        self.speaker_tier_worker.set_params(
            self.corpus_model.session, self.selection_model.current_file.id
        )
        self.speaker_tier_worker.start()

    def set_extra_tiers(self):
        workflows = (
            self.corpus_model.session.query(CorpusWorkflow)
            .order_by(CorpusWorkflow.time_stamp)
            .all()
        )
        self.extra_tiers = {}
        for w in workflows:
            if w.workflow_type is WorkflowType.alignment:
                if self.show_alignment and "Words" not in self.extra_tiers:
                    self.extra_tiers["Words"] = "aligned_word_intervals"
                    self.extra_tiers["Phones"] = "aligned_phone_intervals"

            elif w.workflow_type is WorkflowType.reference:
                if "Reference" not in self.extra_tiers:
                    self.extra_tiers["Reference"] = "reference_phone_intervals"
            elif w.workflow_type is WorkflowType.transcription:
                if self.show_transcription and "Transcription" not in self.extra_tiers:
                    self.extra_tiers["Transcription"] = "transcription_text"
                    if self.corpus_model.corpus.has_alignments(w.workflow_type):
                        self.extra_tiers["Transcribed words"] = "transcribed_word_intervals"
                        self.extra_tiers["Transcribed phones"] = "transcribed_phone_intervals"
            elif w.workflow_type is WorkflowType.per_speaker_transcription:
                if self.show_transcription and "Transcription" not in self.extra_tiers:
                    self.extra_tiers["Transcription"] = "transcription_text"
                    if self.corpus_model.corpus.has_alignments(w.workflow_type):
                        self.extra_tiers[
                            "Transcribed words"
                        ] = "per_speaker_transcribed_word_intervals"
                        self.extra_tiers[
                            "Transcribed phones"
                        ] = "per_speaker_transcribed_phone_intervals"

    def update_channel(self):
        self.get_latest_waveform()

    def set_up_new_file(self, *args):
        self.audio_plot.spectrogram.hide()
        self.audio_plot.wave_form.hide()
        self.audio_plot.pitch_track.hide()
        self.audio_plot.spectrogram.cached_begin = None
        self.audio_plot.spectrogram.cached_end = None
        self.audio_plot.wave_form.y = None
        for t in self.speaker_tiers.values():
            t.visible_utterances = {}
        self.speaker_tiers = {}
        if self.selection_model.current_file is None:
            return
        self.get_utterances()
        self.waveform_worker.stop()
        self.waveform_worker.set_params(
            self.selection_model.current_file.sound_file.sound_file_path
        )
        self.waveform_worker.start()

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
            tier.refresh()
            if tier.has_visible_utterances and scroll_to is None:
                scroll_to = i
                tier_height = self.speaker_tier_items[key].height()
            self.speaker_tier_items[key].setRange(
                xRange=[self.selection_model.min_time, self.selection_model.max_time]
            )
        if scroll_to is not None:
            self.tier_scroll_area.scrollContentsBy(0, scroll_to * tier_height)

    def update_show_speakers(self, state):
        self.show_all_speakers = state > 0
        self.update_plot()

    def get_latest_waveform(self):
        if self.audio_plot.wave_form.y is None:
            return
        self.audio_plot.wave_form.hide()
        self.audio_plot.spectrogram.hide()
        self.audio_plot.pitch_track.hide()
        begin_samp = int(
            self.selection_model.min_time * self.selection_model.current_file.sample_rate
        )
        end_samp = int(
            self.selection_model.max_time * self.selection_model.current_file.sample_rate
        )
        if len(self.audio_plot.wave_form.y.shape) > 1:
            y = self.audio_plot.wave_form.y[
                begin_samp:end_samp, self.selection_model.selected_channel
            ]
        else:
            y = self.audio_plot.wave_form.y[begin_samp:end_samp]
        self.spectrogram_worker.stop()
        self.spectrogram_worker.set_params(
            y,
            self.selection_model.current_file.sound_file.sample_rate,
            self.selection_model.min_time,
            self.selection_model.max_time,
            self.selection_model.selected_channel,
            self.settings.value(self.settings.SPEC_DYNAMIC_RANGE),
            self.settings.value(self.settings.SPEC_N_FFT),
            self.settings.value(self.settings.SPEC_N_TIME_STEPS),
            self.settings.value(self.settings.SPEC_WINDOW_SIZE),
            self.settings.value(self.settings.SPEC_PREEMPH),
            self.settings.value(self.settings.SPEC_MAX_FREQ),
        )
        self.spectrogram_worker.start()
        if self.selection_model.max_time - self.selection_model.min_time <= 10:
            self.pitch_track_worker.stop()
            self.pitch_track_worker.set_params(
                y,
                self.selection_model.current_file.sound_file.sample_rate,
                self.selection_model.min_time,
                self.selection_model.max_time,
                self.selection_model.selected_channel,
                self.settings.value(self.settings.PITCH_MIN_F0),
                self.settings.value(self.settings.PITCH_MAX_F0),
                self.settings.value(self.settings.PITCH_FRAME_SHIFT),
                self.settings.value(self.settings.PITCH_FRAME_LENGTH),
                self.settings.value(self.settings.PITCH_DELTA_PITCH),
                self.settings.value(self.settings.PITCH_PENALTY_FACTOR),
                self.audio_plot.pitch_track.bottom_point,
                self.audio_plot.pitch_track.top_point,
            )
            self.pitch_track_worker.start()
        self.auto_waveform_worker.stop()
        self.auto_waveform_worker.set_params(
            y,
            self.audio_plot.wave_form.bottom_point,
            self.audio_plot.wave_form.top_point,
            self.selection_model.min_time,
            self.selection_model.max_time,
            self.selection_model.selected_channel,
        )
        self.auto_waveform_worker.start()
        self.audio_plot_item.setRange(
            xRange=[self.selection_model.min_time, self.selection_model.max_time]
        )
        self.audio_plot.update_plot()

    def reset_plot(self, *args):
        self.reset_text_grid()
        self.audio_plot.wave_form.clear()
        self.audio_plot.pitch_track.clear()
        self.audio_plot.spectrogram.clear()

    def update_plot(self, *args):
        if self.corpus_model.rowCount() == 0:
            return
        if self.selection_model.current_file is None or self.selection_model.min_time is None:
            return
        self.get_latest_waveform()
        self.audio_plot.update_plot()
        self.draw_text_grid()

    def update_selected_speaker(self, utterance, pos):
        if pos > self.separator_point:
            return
        new_speaker = None
        old_speaker = None
        for tier in self.speaker_tiers.values():
            if tier.speaker_id == utterance.speaker_id:
                old_speaker = tier.speaker
            if tier.top_point > pos > tier.bottom_point:
                new_speaker = tier.speaker
        if new_speaker is not None and new_speaker != old_speaker:
            self.corpus_model.update_utterance_speaker(utterance, new_speaker)


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


class SpeakerComboBox(QtWidgets.QComboBox):
    popupAboutToBeShown = QtCore.Signal()
    popupAboutToBeHidden = QtCore.Signal()

    def showPopup(self):
        self.popupAboutToBeShown.emit()
        super().showPopup()

    def hidePopup(self):
        self.popupAboutToBeHidden.emit()
        super().hidePopup()


class UtteranceSpeakerDropDownItem(pg.TextItem):
    def __init__(self, utterance, corpus_model: CorpusModel, font=None, anchor=(1, 1)):
        self.corpus_model = corpus_model
        self.anchor = pg.Point(anchor)
        self.rotateAxis = None
        self.angle = 0
        pg.GraphicsObject.__init__(self)
        self.combo_box = SpeakerComboBox()
        self.combo_box.setDisabled(True)
        self.combo_box.popupAboutToBeShown.connect(self.boostZ)
        self.combo_box.popupAboutToBeHidden.connect(self.lowerZ)
        self.utterance = utterance
        self.current_speaker_id = utterance.speaker_id

        self.textItem = QtWidgets.QGraphicsProxyWidget(self)
        # self.textItem.setWidget(self.combo_box)
        # self.corpus_model.runFunction.emit('Getting closest speakers', self.populate_options, [{
        #    'utterance_id': self.utterance.id,
        # }])
        self.combo_box.addItem(utterance.speaker.name, utterance.speaker_id)
        self.combo_box.setCurrentIndex(0)
        self._lastTransform = None
        self._lastScene = None
        self._bounds = QtCore.QRectF()
        if font:
            self.combo_box.setFont(font)
        self.fill = pg.mkBrush(None)
        self.border = pg.mkPen(None)
        self.combo_box.currentIndexChanged.connect(self.update_speaker)

    def update_speaker(self):
        speaker_id = self.combo_box.currentData(QtCore.Qt.ItemDataRole.UserRole)
        if speaker_id is None:
            return
        if speaker_id == self.utterance.speaker_id:
            return
        speaker = self.corpus_model.session.query(Speaker).get(speaker_id)
        self.corpus_model.update_utterance_speaker(self.utterance, speaker)

    def populate_options(self, options):
        self.combo_box.clear()
        with QtCore.QSignalBlocker(self.combo_box):
            found_current = False
            i = -1
            for i, (s_id, s_name) in enumerate(options.items()):
                self.combo_box.addItem(s_name, s_id)
                if s_id == self.utterance.speaker_id:
                    self.combo_box.setCurrentIndex(i)
                    found_current = True
            if not found_current:
                self.combo_box.addItem(self.utterance.speaker.name, self.utterance.speaker_id)
            self.combo_box.setCurrentIndex(i + 1)
            self.combo_box.setDisabled(False)

    def boostZ(self):
        self.setZValue(self.parentItem().zValue() + 30)
        self.update()

    def lowerZ(self):
        self.setZValue(self.parentItem().zValue())
        self.update()


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
        # show the menu
        menu.exec_(self.mapToGlobal(location))


class UtterancePGTextItem(pg.TextItem):
    def __init__(
        self,
        item: Utterance,
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
        self.begin = item.begin
        self.end = item.end
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
        self.text_edit.setPlainText(item.text)
        self.fill = pg.mkBrush(fill)
        self.border = pg.mkPen(border)
        self._cached_pixel_size = None
        self.cached_duration = None
        self.top_point = top_point
        self.bottom_point = bottom_point
        self.per_tier_range = per_tier_range
        self.view_min = self.selection_model.min_time
        self.view_max = self.selection_model.max_time
        self.selection_model.viewChanged.connect(self.update_times)

    def update_times(self, begin, end):
        self.hide()
        self.view_min = begin
        self.view_max = end
        br = self.boundingRect()
        if (
            self.view_min <= self.begin < self.view_max
            or self.view_max >= self.end > self.view_min
            or (self.begin <= self.view_min and self.end >= self.view_max)
        ) and br.width() / self._cached_pixel_size[0] > 100:
            self.show()

    def boundingRect(self):
        br = QtCore.QRectF(self.viewRect())  # bounds of containing ViewBox mapped to local coords.
        vb = self.getViewBox()
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


class TranscriberTextRegion(IntervalTextRegion):
    viewRequested = QtCore.Signal(object, object)
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
        alignment=None,
    ):
        super().__init__(
            interval,
            color,
            top_point,
            height,
            font,
            border,
            background_brush,
            hover_brush,
            selected_brush,
        )

        self.highlighter = TranscriberErrorHighlighter(self.text.textItem.document())
        if alignment is not None:
            self.highlighter.set_alignment(alignment)


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
    dragFinished = QtCore.Signal(object)
    textEdited = QtCore.Signal(object, object)
    undoRequested = QtCore.Signal()
    redoRequested = QtCore.Signal()
    playRequested = QtCore.Signal()
    selectRequested = QtCore.Signal(object, object, object, object)
    audioSelected = QtCore.Signal(object, object)
    viewRequested = QtCore.Signal(object, object)

    settings = AnchorSettings()

    def __init__(
        self,
        item: CtmInterval,
        corpus_model: CorpusModel,
        dictionary_model: typing.Optional[DictionaryTableModel],
        selection_model: CorpusSelectionModel,
        selected: bool = False,
        bottom_point: float = 0,
        top_point: float = 1,
    ):
        pg.GraphicsObject.__init__(self)
        self.item = item

        self.item_min = self.item.begin
        self.item_max = self.item.end
        self.corpus_model = corpus_model
        self.dictionary_model = dictionary_model
        self.selection_model = selection_model
        self.bottom_point = bottom_point
        self.top_point = top_point
        self.selected = selected
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

        if self.selected:
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

        # note LinearRegionItem.Horizontal and LinearRegionItem.Vertical
        # are kept for backward compatibility.
        lineKwds = dict(
            movable=False,
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
                view_min=self.selection_model.min_time,
                view_max=self.selection_model.max_time,
                **lineKwds,
            ),
            UtteranceLine(
                QtCore.QPointF(self.item_max, 0),
                angle=90,
                initial=False,
                view_min=self.selection_model.min_time,
                view_max=self.selection_model.max_time,
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
        self.cached_visible_duration = None
        self.cached_view = None

    def paint(self, p, *args):
        p.setBrush(self.currentBrush)
        p.setPen(self.border_pen)
        p.drawRect(self.boundingRect())

    def mouseDragEvent(self, ev):
        if not self.movable or ev.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        ev.accept()

        if ev.isStart():
            bdp = ev.buttonDownPos()
            self.cursorOffsets = [line.pos() - bdp for line in self.lines]
            self.startPositions = [line.pos() for line in self.lines]
            self.moving = True

        if not self.moving:
            return

        # self.lines[0].blockSignals(True)  # only want to update once
        # for i, l in enumerate(self.lines):
        #    l.setPos(self.cursorOffsets[i] + ev.pos())
        # self.lines[0].blockSignals(False)
        self.prepareGeometryChange()

        if ev.isFinish():
            self.moving = False
            self.dragFinished.emit(ev.pos())
            self.sigRegionChangeFinished.emit(self)
        else:
            self.sigRegionChanged.emit(self)

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

    def change_editing(self, editable: bool):
        self.movable = editable
        self.lines[0].movable = editable
        self.lines[1].movable = editable

    def setSelected(self, selected: bool):
        self.selected = selected
        if self.selected:
            self.setBrush(pg.mkBrush(self.selected_interval_color))
        else:
            # self.interval_background_color.setAlpha(0)
            self.setBrush(pg.mkBrush(self.interval_background_color))
        self.update()

    def popup(self, hover: bool):
        if hover or self.moving or self.lines[0].moving or self.lines[1].moving:
            self.setZValue(30)
        else:
            self.setZValue(0)

    def setMouseHover(self, hover: bool):
        # Inform the item that the mouse is(not) hovering over it
        if self.mouseHovering == hover:
            return
        self.mouseHovering = hover
        self.popup(hover)
        self.update()

    def select_self(self, deselect=False, reset=True, focus=False):
        self.selected = True
        if self.selected and not deselect and not reset:
            return


class AlignmentRegion(MfaRegion):
    def __init__(
        self,
        phone_interval: CtmInterval,
        corpus_model: CorpusModel,
        selection_model: CorpusSelectionModel,
        selected: bool = False,
        bottom_point: float = 0,
        top_point: float = 1,
    ):
        super().__init__(
            phone_interval, corpus_model, None, selection_model, selected, bottom_point, top_point
        )
        self.original_text = self.item.label

        self.text = pg.TextItem(
            self.item.label, anchor=(0.5, 0.5), color=self.text_color, border=pg.mkColor("r")
        )

        self.text.setFont(self.settings.font)
        self.text.setParentItem(self)
        self.per_tier_range = self.top_point - self.bottom_point

    def boundingRect(self):
        br = QtCore.QRectF(self.viewRect())  # bounds of containing ViewBox mapped to local coords.
        vb = self.getViewBox()

        pixel_size = vb.viewPixelSize()
        rng = self.getRegion()

        br.setLeft(rng[0])
        br.setRight(rng[1])

        br.setTop(self.top_point)
        # br.setBottom(self.top_point-self.per_tier_range)
        br.setBottom(self.bottom_point + 0.01)
        try:
            visible_begin = max(rng[0], self.selection_model.min_time)
            visible_end = min(rng[1], self.selection_model.max_time)
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
            self.size_calculated = True
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
        selection_model: CorpusSelectionModel,
        selected: bool = False,
        bottom_point: float = 0,
        top_point: float = 1,
    ):
        super().__init__(
            phone_interval, corpus_model, selection_model, selected, bottom_point, top_point
        )


class WordRegion(AlignmentRegion):
    def __init__(
        self,
        phone_interval: CtmInterval,
        corpus_model: CorpusModel,
        selection_model: CorpusSelectionModel,
        selected: bool = False,
        bottom_point: float = 0,
        top_point: float = 1,
    ):
        super().__init__(
            phone_interval, corpus_model, selection_model, selected, bottom_point, top_point
        )


class UtteranceRegion(MfaRegion):
    def __init__(
        self,
        utterance: Utterance,
        corpus_model: CorpusModel,
        dictionary_model: DictionaryTableModel,
        selection_model: CorpusSelectionModel,
        selected: bool = False,
        bottom_point: float = 0,
        top_point: float = 1,
        extra_tiers=None,
        available_speakers=None,
        search_term=None,
    ):
        super().__init__(
            utterance,
            corpus_model,
            dictionary_model,
            selection_model,
            selected,
            bottom_point,
            top_point,
        )
        self.item = utterance
        self.selection_model = selection_model
        if extra_tiers is None:
            extra_tiers = {}
        self.extra_tiers = extra_tiers
        self.extra_tier_intervals = {}
        self.num_tiers = len(extra_tiers) + 1
        self.per_tier_range = (top_point - bottom_point) / self.num_tiers

        self.setMovable(True)

        self.corpus_model.utteranceTextUpdated.connect(self.update_text_from_model)
        self.original_text = self.item.text
        self.text = UtterancePGTextItem(
            self.item,
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
        self.speaker_dropdown = UtteranceSpeakerDropDownItem(
            self.item, self.corpus_model, font=self.settings.small_font, anchor=(0, 1)
        )

        self.speaker_dropdown.setParentItem(self)
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
        self.text_edit.setStyleSheet(self.settings.generate_interval_style_sheet())
        self.speaker_dropdown.combo_box.setStyleSheet(
            self.settings.generate_combo_box_style_sheet()
        )
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
        self.hide()
        self._cached_pixel_size = None
        for i, (tier_name, lookup) in enumerate(self.extra_tiers.items()):
            intervals = getattr(self.item, lookup)
            alignment = None
            if lookup == "transcription_text":
                if self.item.text and self.item.transcription_text:
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
                intervals = [
                    CtmInterval(self.item.begin, self.item.end, self.item.transcription_text)
                ]

            self.extra_tier_intervals[tier_name] = []
            tier_top_point = self.top_point - ((i + 1) * self.per_tier_range)
            tier_bottom_point = tier_top_point - self.per_tier_range
            if intervals is None:
                continue
            for interval in intervals:
                if lookup == "transcription_text":
                    interval_reg = TranscriberTextRegion(
                        interval,
                        self.text_color,
                        border=pg.mkPen(self.settings.accent_light_color),
                        top_point=tier_top_point,
                        height=self.per_tier_range,
                        font=self.settings.font,
                        alignment=alignment,
                        background_brush=self.background_brush,
                        selected_brush=pg.mkBrush(self.selected_range_color),
                    )
                elif "phone_intervals" in lookup:
                    interval_reg = PhoneRegion(
                        interval,
                        self.corpus_model,
                        selection_model=selection_model,
                        selected=False,
                        top_point=tier_top_point,
                        bottom_point=tier_bottom_point,
                    )
                elif "word_intervals" in lookup:
                    interval_reg = WordRegion(
                        interval,
                        self.corpus_model,
                        selection_model=selection_model,
                        selected=False,
                        top_point=tier_top_point,
                        bottom_point=tier_bottom_point,
                    )

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

                interval_reg.audioSelected.connect(self.audioSelected.emit)
                interval_reg.viewRequested.connect(self.viewRequested.emit)
                interval_reg.setParentItem(self)
                self.extra_tier_intervals[tier_name].append(interval_reg)
        self.selection_model.viewChanged.connect(self.update_view_times)
        self.show()
        self.available_speakers = available_speakers

    def contextMenuEvent(self, ev: QtWidgets.QGraphicsSceneContextMenuEvent):
        menu = QtWidgets.QMenu()
        change_speaker_menu = QtWidgets.QMenu("Change speaker")
        for speaker_name, speaker_id in self.available_speakers.items():
            if speaker_id == self.item.speaker_id:
                continue
            a = QtGui.QAction(speaker_name)
            a.triggered.connect(self.update_speaker)
            change_speaker_menu.addAction(a)
        menu.addMenu(change_speaker_menu)
        menu.exec_(ev.screenPos())

    def update_speaker(self):
        speaker_name = self.sender().text()
        speaker_id = self.available_speakers[speaker_name]
        self.corpus_model.update_utterance_speaker(self.item, speaker_id)

    def refresh_timer(self):
        self.timer.start(500)
        self.update()

    def change_editing(self, editable: bool):
        super().change_editing(editable)
        self.text_edit.setReadOnly(not editable)
        self.speaker_dropdown.combo_box.setEnabled(editable)

    def select_self(self, deselect=False, reset=True, focus=False):
        self.selected = True
        if self.selected and not deselect and not reset:
            return
        self.selectRequested.emit(self.item.id, deselect, reset, focus)

    def mouseDoubleClickEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return
        deselect = False
        reset = True
        if ev.modifiers() == QtCore.Qt.Modifier.CTRL:
            reset = False
            if self.selected:
                deselect = True
                self.selected = False
            else:
                self.selected = True
        else:
            self.selected = True
        self.select_self(deselect=deselect, reset=reset, focus=True)
        ev.accept()

    def mouseClickEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return
        deselect = False
        reset = True
        if ev.modifiers() == QtCore.Qt.Modifier.CTRL:
            reset = False
            if self.selected:
                deselect = True
                self.selected = False
            else:
                self.selected = True
        else:
            self.selected = True
        self.select_self(deselect=deselect, reset=reset, focus=False)
        ev.accept()

    def update_view_times(self, view_min, view_max):
        self.lines[0].view_min = view_min
        self.lines[0].view_max = view_max
        self.lines[1].view_min = view_min
        self.lines[1].view_max = view_max
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
            or (begin == self.selection_model.min_time and end == self.selection_model.max_time)
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
        self.selection_model: typing.Optional[CorpusSelectionModel] = None
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
        if self.selection_model.min_time is None:
            ev.ignore()
            return
        min_time = max(min(ev.buttonDownPos().x(), ev.pos().x()), self.selection_model.min_time)
        max_time = min(max(ev.buttonDownPos().x(), ev.pos().x()), self.selection_model.max_time)
        if ev.isStart():
            self.selection_area.setVisible(True)
        if ev.isFinish():
            self.selection_model.select_audio(min_time, max_time)
        ev.accept()

    def mouseClickEvent(self, ev):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return
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
            self.selection_model.current_file is None
            or self.selection_model.current_file.sound_file is None
            or not os.path.exists(self.selection_model.current_file.sound_file.sound_file_path)
        ):
            return
        self.rect.setLeft(self.selection_model.min_time)
        self.rect.setRight(self.selection_model.max_time)
        self._generate_picture()
        self.update_play_line(self.selection_model.min_time)
        self.selection_area.update_region()
        self.update()


class SpeakerTier(pg.GraphicsObject):
    dragFinished = QtCore.Signal(object, object)
    receivedWheelEvent = QtCore.Signal(object)
    draggingLine = QtCore.Signal(object)
    lineDragFinished = QtCore.Signal(object)

    def __init__(self, bottom_point, top_point, speaker: Speaker, search_term=None):
        super().__init__()
        self.settings = AnchorSettings()
        self.corpus_model: Optional[CorpusModel] = None
        self.selection_model: Optional[CorpusSelectionModel] = None
        self.search_term = search_term
        self.speaker = speaker
        self.speaker_id = speaker.id
        self.speaker_name = speaker.name
        self.speaker_index = 0
        self.textgrid_top_point = top_point
        self.top_point = top_point
        self.speaker_label = pg.TextItem(self.speaker_name, color=self.settings.accent_base_color)
        self.speaker_label.setFont(self.settings.font)
        self.speaker_label.setParentItem(self)
        self.speaker_label.setZValue(40)
        self.bottom_point = bottom_point
        self.textgrid_bottom_point = bottom_point
        self.annotation_range = self.top_point - self.bottom_point
        self.extra_tiers = {}
        self.utterances = []
        self.visible_utterances: dict[str, UtteranceRegion] = {}
        self.background_brush = pg.mkBrush(self.settings.primary_very_dark_color)
        self.border = pg.mkPen(self.settings.accent_light_color)
        self.picture = QtGui.QPicture()

    def wheelEvent(self, ev):
        self.receivedWheelEvent.emit(ev)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return
        x = ev.pos().x()
        begin = max(x - 0.5, 0)
        end = min(x + 0.5, self.selection_model.current_file.duration)
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
            self.corpus_model.create_utterance(
                self.selection_model.current_file, self.speaker, begin, end
            )
            ev.accept()

    def setSearchterm(self, term):
        self.search_term = term
        for reg in self.visible_utterances.values():
            reg.highlighter.setSearchTerm(term)

    def boundingRect(self):
        return QtCore.QRectF(self.picture.boundingRect())

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def set_speaker_index(self, index, num_speakers):
        self.speaker_index = index
        speaker_tier_range = self.annotation_range / num_speakers
        self.top_point = self.textgrid_top_point - (speaker_tier_range * self.speaker_index)
        self.bottom_point = self.top_point - speaker_tier_range
        self.rect = QtCore.QRectF(
            left=self.selection_model.min_time,
            top=self.top_point,
            width=self.selection_model.max_time - self.selection_model.min_time,
            height=speaker_tier_range,
        )
        self.rect.setHeight(speaker_tier_range)
        self._generate_picture()

    def _generate_picture(self):
        self.speaker_label.setPos(self.selection_model.min_time, self.top_point)
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

    def set_models(
        self,
        corpus_model: CorpusModel,
        selection_model: CorpusSelectionModel,
        dictionary_model: DictionaryTableModel,
    ):
        self.corpus_model = corpus_model
        self.selection_model = selection_model
        self.dictionary_model = dictionary_model
        for reg in self.visible_utterances.values():
            reg.highlighter.set_models(self.dictionary_model)
        # self.corpus_model.changeCommandFired.connect(self.refresh)
        self.corpus_model.lockCorpus.connect(self.lock)
        self.corpus_model.refreshUtteranceText.connect(self.refreshTexts)
        self.selection_model.selectionChanged.connect(self.update_select)

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
        self.other_intervals = []

    def refresh(self, *args):
        if self.selection_model.min_time is None:
            return
        self.rect.setLeft(self.selection_model.min_time)
        self.rect.setRight(self.selection_model.max_time)
        self._generate_picture()
        self.has_visible_utterances = False
        for u in self.utterances:
            if u.end < self.selection_model.min_time:
                continue
            if u.begin > self.selection_model.max_time:
                break
            self.has_visible_utterances = True
            if u.id in self.visible_utterances:
                continue
            selected = self.selection_model.checkSelected(u)
            # Utterance region always at the top
            reg = UtteranceRegion(
                u,
                self.corpus_model,
                self.dictionary_model,
                selection_model=self.selection_model,
                selected=selected,
                extra_tiers=self.extra_tiers,
                available_speakers=self.available_speakers,
                bottom_point=self.bottom_point,
                top_point=self.top_point,
                search_term=self.search_term,
            )
            reg.sigRegionChanged.connect(self.check_utterance_bounds)
            reg.sigRegionChangeFinished.connect(self.update_utterance)
            reg.dragFinished.connect(self.update_selected_speaker)
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

    def update_utterance_text(self, utterance, new_text):
        self.corpus_model.update_utterance_text(utterance, text=new_text)

    def update_selected_speaker(self, pos):
        pos = pos.y()
        reg = self.sender()
        utterance = reg.item
        self.dragFinished.emit(utterance, pos)

    def update_select(self):
        selected_rows = {x.id for x in self.selection_model.selectedUtterances()}
        for r in self.visible_utterances.values():
            if r.item.id in selected_rows:
                r.setSelected(True)
            else:
                r.setSelected(False)

    def check_utterance_bounds(self):
        reg = self.sender()
        with QtCore.QSignalBlocker(reg):
            beg, end = reg.getRegion()
            if beg < 0:
                reg.setRegion([0, end])
                return
            if end > self.selection_model.current_file.duration:
                reg.setRegion([beg, self.selection_model.current_file.duration])
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
            reg.text.update_times(self.selection_model.min_time, self.selection_model.max_time)
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
        self.corpus_model.update_utterance_times(utt, begin=new_begin, end=new_end)
        self.selection_model.select_audio(new_begin, None)
        reg.text.begin = new_begin
        reg.text.end = new_end
        reg.update()
        self.lineDragFinished.emit(True)
