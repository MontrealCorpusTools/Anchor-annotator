from __future__ import annotations

import datetime
import logging
import os
import re
import subprocess
import typing
import unicodedata
from threading import Lock
from typing import Any, Optional, Union

import numpy as np
import pynini.lib.rewrite
import sqlalchemy
import yaml
from _kalpy.ivector import Plda
from dataclassy import dataclass
from kalpy.fstext.lexicon import LexiconCompiler
from kalpy.utterance import Utterance as KalpyUtterance
from montreal_forced_aligner import config
from montreal_forced_aligner.corpus.acoustic_corpus import (
    AcousticCorpus,
    AcousticCorpusWithPronunciations,
)
from montreal_forced_aligner.data import PhoneType, WordType, WorkflowType
from montreal_forced_aligner.db import (
    CorpusWorkflow,
    File,
    Grapheme,
    Phone,
    PhoneInterval,
    Pronunciation,
    Speaker,
    Utterance,
    Word,
    WordInterval,
)
from montreal_forced_aligner.g2p.generator import PyniniValidator
from montreal_forced_aligner.models import (
    AcousticModel,
    G2PModel,
    IvectorExtractorModel,
    LanguageModel,
)
from montreal_forced_aligner.utils import mfa_open
from PySide6 import QtCore
from sqlalchemy.orm import joinedload

import anchor.db
from anchor import undo, workers
from anchor.settings import AnchorSettings

if typing.TYPE_CHECKING:
    from montreal_forced_aligner.models import ModelManager

logger = logging.getLogger("anchor")


# noinspection PyUnresolvedReferences
@dataclass(slots=True)
class TextFilterQuery:
    text: str
    regex: bool = False
    word: bool = False
    case_sensitive: bool = False
    graphemes: typing.Collection[str] = None

    @property
    def search_text(self):
        if not self.case_sensitive:
            return self.text.lower()
        return self.text

    def generate_expression(self, posix=False):
        word_symbols = r"\w"
        if self.graphemes:
            dash_prefix = "-" if "-" in self.graphemes else ""
            graphemes = "".join([x for x in self.graphemes if x != "-"])
            word_symbols = rf"[{dash_prefix}\w{graphemes}]"
        text = self.text
        if not self.case_sensitive:
            text = text.lower()
        if not text:
            return text
        if not self.regex:
            text = re.escape(text)
        word_break_set = r"\b"
        if self.word:
            if not text.startswith(word_break_set):
                text = word_break_set + text
            if not text.endswith(word_break_set):
                text += word_break_set
        if posix:
            if text.startswith(r"\b"):
                text = rf"((?<!{word_symbols})|(?<=^))" + text[2:]
            if text.endswith(r"\b"):
                text = text[:-2] + rf"((?!{word_symbols})|(?=$))"
        if not self.case_sensitive:
            text = "(?i)" + text
        return text


class TableModel(QtCore.QAbstractTableModel):
    runFunction = QtCore.Signal(object, object, object)  # Function plus finished processor
    resultCountChanged = QtCore.Signal(int)
    newResults = QtCore.Signal()

    def __init__(self, header_data, parent=None):
        super().__init__(parent)
        self._header_data = header_data
        self._data = []
        self.result_count = None
        self.sort_index = None
        self.sort_order = None
        self.current_offset = 0
        self.limit = 1
        self.text_filter = None

    def set_text_filter(self, text_filter: typing.Optional[TextFilterQuery]):
        if text_filter != self.text_filter:
            self.current_offset = 0
        self.text_filter = text_filter
        self.update_data()
        self.update_result_count()

    def set_limit(self, limit: int):
        self.limit = limit

    def set_offset(self, offset):
        self.current_offset = offset
        self.update_data()
        self.update_result_count()

    def update_sort(self, column, order):
        self.sort_index = column
        self.sort_order = order
        self.update_data()
        self.update_result_count()

    def query_count(self, **kwargs):
        pass

    def query_data(self, **kwargs):
        pass

    def finalize_result_count(self, result_count=None):
        if isinstance(result_count, int):
            self.result_count = result_count
        self.resultCountChanged.emit(self.result_count)

    def update_result_count(self):
        self.result_count = None
        self.runFunction.emit(self.query_count, self.finalize_result_count, [])

    def update_data(self):
        self.runFunction.emit(self.query_data, self.finish_update_data, [])

    def finish_update_data(self, *args, **kwargs):
        self.layoutAboutToBeChanged.emit()
        self._data = []
        self.layoutChanged.emit()

    def headerData(self, index, orientation, role=None, *args, **kwargs):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._header_data[index]

    def data(self, index, role=None):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._data[index.row()][index.column()]

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self._header_data)


class FileUtterancesModel(QtCore.QAbstractListModel):
    addCommand = QtCore.Signal(object)
    selectionRequested = QtCore.Signal(object)

    waveformReady = QtCore.Signal()
    utterancesReady = QtCore.Signal()
    speakersChanged = QtCore.Signal()
    phoneTierChanged = QtCore.Signal(object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.utterances = []
        self.file = None
        self.y = None
        self.speakers = []
        self._indices = []
        self._speaker_indices = []
        self.reversed_indices = {}
        self.speaker_channel_mapping = {}
        self.corpus_model: typing.Optional[CorpusModel] = None
        self.closing = False
        self.cached_begin = None
        self.cached_end = None

        self.thread_pool = QtCore.QThreadPool()
        self.thread_pool.setMaxThreadCount(4)

    def get_utterance(self, utterance_id: int) -> Utterance:
        try:
            return self.utterances[self.reversed_indices[utterance_id]]
        except KeyError:
            return None

    def set_corpus_model(self, corpus_model: CorpusModel):
        self.corpus_model = corpus_model

    def clean_up_for_close(self):
        self.closing = True

    def set_file(self, file_id, utterance_id=None, begin=None, end=None):
        self.file = (
            self.corpus_model.session.query(File).options(joinedload(File.sound_file)).get(file_id)
        )
        self.y = None
        self.get_utterances(utterance_id, begin, end)
        waveform_worker = workers.WaveformWorker(self.file.sound_file.sound_file_path)
        waveform_worker.signals.result.connect(self.finalize_loading_wave_form)
        self.thread_pool.start(waveform_worker)

    def finalize_loading_utterances(self, results):
        if self.closing:
            return
        utterances, file_id, self.cached_begin, self.cached_end = results
        if file_id != self.file.id:
            return
        self.utterances = utterances
        for i, u in enumerate(utterances):
            if u.speaker_id not in self.speakers:
                self.speakers.append(u.speaker_id)
            self._speaker_indices.append(u.speaker_id)
            self.reversed_indices[u.id] = i
            self._indices.append(u.id)
            if self.file.num_channels > 1 and u.speaker_id not in self.speaker_channel_mapping:
                self.speaker_channel_mapping[u.speaker_id] = u.channel
        self.utterancesReady.emit()

    def finalize_loading_wave_form(self, results):
        if self.closing:
            return
        y, file_path = results
        if self.file is None or file_path != self.file.sound_file.sound_file_path:
            return
        self.y = y
        self.waveformReady.emit()

    def get_utterances(self, utterance_id=None, begin=None, end=None):
        parent_index = self.index(0, 0)
        self.beginRemoveRows(parent_index, 0, len(self.utterances))
        self.utterances = []
        self.speakers = []
        self._indices = []
        self._speaker_indices = []
        self.speaker_channel_mapping = {}
        self.reversed_indices = {}
        self.endRemoveRows()
        if self.file is None:
            return
        speaker_tier_worker = workers.SpeakerTierWorker(
            self.corpus_model.session,
            self.file.id,
            query_alignment=(
                self.corpus_model.has_alignments
                or self.corpus_model.has_reference_alignments
            ),
            utterance_id=utterance_id,
            begin=begin,
            end=end,
        )
        speaker_tier_worker.signals.result.connect(self.finalize_loading_utterances)
        self.thread_pool.start(speaker_tier_worker)

    def create_utterance(self, speaker_id: Optional[int], begin: float, end: float):
        if not self.corpus_model.editable:
            return
        channel = 0
        if speaker_id is None:
            speaker_id = self.corpus_model.corpus.add_speaker(
                "speech", session=self.corpus_model.session
            ).id
        if self.file.num_channels > 1:
            if speaker_id not in self.speaker_channel_mapping:
                self.speaker_channel_mapping[speaker_id] = 0
            channel = self.speaker_channel_mapping[speaker_id]
        begin = round(begin, 4)
        end = round(end, 4)
        text = ""
        next_pk = self.corpus_model.corpus.get_next_primary_key(Utterance)
        new_utt = Utterance(
            id=next_pk,
            speaker_id=speaker_id,
            file_id=self.file.id,
            begin=begin,
            end=end,
            channel=channel,
            text=text,
            normalized_text=text,
            oovs=text,
        )
        self.addCommand.emit(undo.CreateUtteranceCommand(new_utt, self))
        self.corpus_model.set_file_modified(self.file.id)
        self.corpus_model.set_speaker_modified(speaker_id)

    def add_table_utterances(self, utterances: typing.List[Utterance]):
        for utterance in utterances:
            if len(self.utterances) > 0:
                for i, u in enumerate(self.utterances):
                    if u.begin < utterance.begin:
                        continue
                    break
                else:
                    i = len(self.utterances) - 1
            else:
                i = 0
            parent_index = self.index(i, 0)
            self.beginInsertRows(parent_index, i, i + 1)
            self.utterances.insert(i, utterance)
            self._indices.insert(i, utterance.id)
            self._speaker_indices.insert(i, utterance.speaker_id)
            self.endInsertRows()
        self.reversed_indices = {u: j for j, u in enumerate(self._indices)}
        self.selectionRequested.emit(utterances)

    def delete_table_utterances(self, utterances: typing.List[Utterance]):
        for utterance in utterances:
            try:
                index = self.reversed_indices.pop(utterance.id)
            except KeyError:
                continue
            parent_index = self.index(index, 0)
            self.beginRemoveRows(parent_index, index, index + 1)
            _ = self.utterances.pop(index)
            _ = self._indices.pop(index)
            _ = self._speaker_indices.pop(index)
            self.reversed_indices = {u: j for j, u in enumerate(self._indices)}
            self.endRemoveRows()
        self.selectionRequested.emit(None)

    def change_speaker_table_utterances(self, utterances: typing.List[Utterance]):
        for utterance in utterances:
            try:
                index = self.reversed_indices[utterance.id]
            except KeyError:
                continue
            if utterance.speaker_id not in self.speakers:
                self.speakers.append(utterance.speaker_id)
                self.speaker_channel_mapping[utterance.speaker_id] = utterance.channel
                self.speakersChanged.emit()
            self._speaker_indices[index] = utterance.speaker_id

    def merge_table_utterances(
        self, merged_utterance: Utterance, split_utterances: typing.List[Utterance]
    ):
        self.delete_table_utterances(split_utterances)
        self.add_table_utterances([merged_utterance])

    def split_table_utterances(
        self, merged_utterance: Utterance, split_utterances: typing.List[Utterance]
    ):
        self.delete_table_utterances([merged_utterance])
        self.add_table_utterances(split_utterances)

    def update_phone_boundaries(
        self,
        utterance: Utterance,
        first_phone_interval: PhoneInterval,
        second_phone_interval: PhoneInterval,
        new_time: float,
    ):
        if not self.corpus_model.editable:
            return
        if first_phone_interval.end == new_time and second_phone_interval.begin == new_time:
            return
        self.addCommand.emit(
            undo.UpdatePhoneBoundariesCommand(
                utterance, first_phone_interval, second_phone_interval, new_time, self
            )
        )
        self.corpus_model.set_file_modified(self.file.id)

    def delete_reference_alignments(self, utterance: Utterance):
        if not self.corpus_model.editable:
            return
        self.addCommand.emit(undo.DeleteReferenceIntervalsCommand(utterance, self))
        self.corpus_model.set_file_modified(self.file.id)

    def update_phone_interval(
        self, utterance: Utterance, phone_interval: PhoneInterval, phone: Phone
    ):
        if not self.corpus_model.editable:
            return
        if phone_interval.phone_id == phone.id:
            return
        self.addCommand.emit(
            undo.UpdatePhoneIntervalCommand(utterance, phone_interval, phone, self)
        )
        self.corpus_model.set_file_modified(self.file.id)

    def update_word_pronunciation(
        self, utterance: Utterance, word_interval: WordInterval, pronunciation: Pronunciation
    ):
        if not self.corpus_model.editable:
            return
        if word_interval.pronunciation_id == pronunciation.id:
            return
        self.addCommand.emit(
            undo.UpdateWordIntervalPronunciationCommand(
                utterance, word_interval, pronunciation, self
            )
        )
        self.corpus_model.set_file_modified(self.file.id)

    def update_word(
        self, utterance: Utterance, word_interval: WordInterval, word: typing.Union[Word, str]
    ):
        if not self.corpus_model.editable:
            return
        if isinstance(word, Word) and word_interval.word_id == word.id:
            return
        self.addCommand.emit(
            undo.UpdateWordIntervalWordCommand(utterance, word_interval, word, self)
        )
        self.corpus_model.set_file_modified(self.file.id)

    def insert_phone_interval(
        self,
        utterance: Utterance,
        phone_interval,
        previous_interval: PhoneInterval,
        following_interval: PhoneInterval,
        word_interval: WordInterval,
    ):
        if not self.corpus_model.editable:
            return
        self.addCommand.emit(
            undo.InsertPhoneIntervalCommand(
                utterance,
                phone_interval,
                previous_interval,
                following_interval,
                self,
                word_interval,
            )
        )
        self.corpus_model.set_file_modified(self.file.id)

    def delete_phone_interval(
        self,
        utterance: Utterance,
        phone_interval: PhoneInterval,
        previous_interval: PhoneInterval,
        following_interval: PhoneInterval,
        time_point: float,
    ):
        if not self.corpus_model.editable:
            return
        self.addCommand.emit(
            undo.DeletePhoneIntervalCommand(
                utterance, phone_interval, previous_interval, following_interval, time_point, self
            )
        )
        self.corpus_model.set_file_modified(self.file.id)

    def update_utterance_text(self, utterance: Utterance, text):
        if not self.corpus_model.editable:
            return
        if text != utterance.text:
            self.addCommand.emit(undo.UpdateUtteranceTextCommand(utterance, text, self))
            self.corpus_model.set_file_modified(self.file.id)

    def refresh_utterances(self):
        for utterance in self.utterances:
            self.corpus_model.session.refresh(utterance)

    def update_utterance_speaker(self, utterance: typing.Union[Utterance, int], speaker_id: int):
        if not self.corpus_model.editable:
            return
        if isinstance(utterance, int):
            if utterance not in self.reversed_indices:
                return
            utterance = self.utterances[self.reversed_indices[utterance]]
        old_speaker_id = utterance.speaker_id
        if old_speaker_id == speaker_id:
            return
        self.addCommand.emit(undo.UpdateUtteranceSpeakerCommand(utterance, speaker_id, self))
        self.corpus_model.set_file_modified(self.file.id)
        self.corpus_model.set_speaker_modified(speaker_id)
        self.corpus_model.set_speaker_modified(old_speaker_id)

    def update_utterance_times(
        self,
        utterance: typing.Union[Utterance, int],
        begin: Optional[float] = None,
        end: Optional[float] = None,
    ):
        if not self.corpus_model.editable:
            return
        if isinstance(utterance, int):
            if utterance not in self.reversed_indices:
                return
            utterance = self.utterances[self.reversed_indices[utterance]]

        if utterance.begin == begin and utterance.end == end:
            return
        self.addCommand.emit(undo.UpdateUtteranceTimesCommand(utterance, begin, end, self))
        self.corpus_model.set_file_modified(self.file.id)

    def split_vad_utterance(
        self, original_utterance_id, replacement_utterance_data: typing.List[KalpyUtterance]
    ):
        if not replacement_utterance_data:
            return
        utt = self.utterances[self.reversed_indices[original_utterance_id]]
        replacement_utterances = []
        next_pk = self.corpus_model.corpus.get_next_primary_key(Utterance)
        speaker_id = utt.speaker_id
        for new_utt in replacement_utterance_data:
            replacement_utterances.append(
                Utterance(
                    id=next_pk,
                    begin=new_utt.segment.begin,
                    end=new_utt.segment.end,
                    speaker_id=speaker_id,
                    file_id=self.file.id,
                    text=new_utt.transcript,
                    normalized_text=new_utt.transcript,
                    features="",
                    in_subset=False,
                    ignored=False,
                    channel=new_utt.segment.channel,
                )
            )
            next_pk += 1
        self.addCommand.emit(
            undo.SplitUtteranceCommand(utt, replacement_utterances, self, update_table=False)
        )
        self.corpus_model.set_file_modified(self.file.id)
        self.corpus_model.set_speaker_modified(speaker_id)

    def split_utterances(self, utterance: Utterance):
        if not self.corpus_model.editable:
            return
        beg = utterance.begin
        end = utterance.end
        duration = end - beg
        first_text = []
        second_text = []
        speaker_id = utterance.speaker_id
        if (
            utterance.text
            and utterance.normalized_text
            and " " not in utterance.text
            and " " in utterance.normalized_text
        ):
            t = utterance.normalized_text.split()
            mid_ind = int(len(t) / 2)
            first_text = t[:mid_ind]
            second_text = t[mid_ind:]
        elif utterance.text:
            t = utterance.text.split()
            mid_ind = int(len(t) / 2)
            first_text = t[:mid_ind]
            second_text = t[mid_ind:]
        split_time = beg + (duration / 2)
        oovs = set()
        for w in first_text:
            if not self.corpus_model.dictionary_model.check_word(w, speaker_id):
                oovs.add(w)
        next_pk = self.corpus_model.corpus.get_next_primary_key(Utterance)
        first_utt = Utterance(
            id=next_pk,
            speaker_id=speaker_id,
            file_id=self.file.id,
            begin=beg,
            end=split_time,
            channel=utterance.channel,
            text=" ".join(first_text) + " ",
            normalized_text=" ".join(first_text),
            oovs=" ".join(oovs),
        )
        next_pk += 1
        oovs = set()
        for w in second_text:
            if not self.corpus_model.dictionary_model.check_word(w, utterance.speaker_id):
                oovs.add(w)
        second_utt = Utterance(
            id=next_pk,
            speaker_id=speaker_id,
            file_id=self.file.id,
            begin=split_time,
            end=end,
            channel=utterance.channel,
            text=" " + " ".join(second_text),
            normalized_text=" ".join(second_text),
            oovs=" ".join(oovs),
        )
        self.addCommand.emit(undo.SplitUtteranceCommand(utterance, [first_utt, second_utt], self))
        self.corpus_model.set_file_modified(self.file.id)
        self.corpus_model.set_speaker_modified(speaker_id)
        self.selectionRequested.emit([first_utt, second_utt])

    def merge_utterances(self, utterances: list[Utterance]):
        if not self.corpus_model.editable:
            return
        if not utterances:
            return
        min_begin = 1000000000
        max_end = 0
        text = ""
        normalized_text = ""
        speaker_id = None
        channel = None
        prev_index = None
        for old_utt in sorted(utterances, key=lambda x: x.begin):
            index = self.reversed_indices[old_utt.id]
            if prev_index is not None:
                if index - prev_index != 1:
                    return
            prev_index = index
            if speaker_id is None:
                speaker_id = old_utt.speaker_id
            if channel is None:
                channel = old_utt.channel
            if old_utt.begin < min_begin:
                min_begin = old_utt.begin
            if old_utt.end > max_end:
                max_end = old_utt.end
            utt_text = old_utt.text
            if utt_text == "speech" and text.strip() == "speech":
                continue
            text += utt_text + " "
            normalized_text += old_utt.normalized_text + " "
        text = re.sub(r"\s+", " ", text[:-1])
        normalized_text = re.sub(r"\s+", " ", normalized_text[:-1])
        next_pk = self.corpus_model.corpus.get_next_primary_key(Utterance)
        oovs = set()
        for w in text.split():
            if not self.corpus_model.dictionary_model.check_word(w, speaker_id):
                oovs.add(w)
        new_utt = Utterance(
            id=next_pk,
            speaker_id=speaker_id,
            file_id=self.file.id,
            begin=min_begin,
            end=max_end,
            channel=channel,
            text=text,
            normalized_text=normalized_text,
            oovs=" ".join(oovs),
        )
        self.addCommand.emit(undo.MergeUtteranceCommand(utterances, new_utt, self))
        self.corpus_model.set_file_modified(self.file.id)
        self.corpus_model.set_speaker_modified(speaker_id)
        self.selectionRequested.emit([new_utt])

    def delete_utterances(self, utterances: typing.List[Utterance]):
        if not self.corpus_model.editable:
            return
        if not utterances:
            return
        speaker_ids = set(x.speaker_id for x in utterances)
        self.addCommand.emit(undo.DeleteUtteranceCommand(utterances, self))
        self.corpus_model.set_file_modified(self.file.id)
        for speaker_id in speaker_ids:
            self.corpus_model.set_speaker_modified(speaker_id)

    def rowCount(self, parent=None):
        return len(self.utterances)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self.utterances[index.row()]


class FileSelectionModel(QtCore.QItemSelectionModel):
    fileAboutToChange = QtCore.Signal()
    fileChanged = QtCore.Signal()
    channelChanged = QtCore.Signal()
    resetView = QtCore.Signal()
    viewChanged = QtCore.Signal(object, object)
    selectionAudioChanged = QtCore.Signal(object)
    currentUtteranceChanged = QtCore.Signal(object)
    speakerRequested = QtCore.Signal(object)
    searchTermChanged = QtCore.Signal(object)

    spectrogramReady = QtCore.Signal()
    waveformReady = QtCore.Signal()
    pitchTrackReady = QtCore.Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = AnchorSettings()
        self.min_time = 0
        self.max_time = 10
        self.selected_min_time = None
        self.selected_max_time = None
        self.x = None
        self.y = None
        self.top_point = 2
        self.bottom_point = 0
        self.separator_point = 1
        self.selected_channel = 0
        self.spectrogram = None
        self.min_db = None
        self.max_db = None
        self.pitch_track_x = None
        self.pitch_track_y = None
        self.waveform_x = None
        self.waveform_y = None
        self.requested_utterance_id = None
        self.closing = False

        self.thread_pool = QtCore.QThreadPool()
        self.thread_pool.setMaxThreadCount(self.settings.value(self.settings.PLOT_THREAD_COUNT))
        self.model().waveformReady.connect(self.load_audio_selection)
        self.model().utterancesReady.connect(self.finalize_set_new_file)
        self.viewChanged.connect(self.load_audio_selection)
        self.model().selectionRequested.connect(self.update_selected_utterances)
        self.view_change_timer = QtCore.QTimer()
        self.view_change_timer.setSingleShot(True)
        self.view_change_timer.setInterval(10)
        self.view_change_timer.timeout.connect(self.send_selection_update)

    def selected_utterances(self):
        utts = []
        m = self.model()
        for index in self.selectedRows(0):
            utt = m.utterances[index.row()]
            utts.append(utt)
        return utts

    def load_audio_selection(self):
        if self.model().y is None:
            return
        begin_samp = int(self.min_time * self.model().file.sample_rate)
        end_samp = int(self.max_time * self.model().file.sample_rate)
        if self.model().cached_begin is not None and (
            self.min_time < self.model().cached_begin + 5
            or self.max_time > self.model().cached_end - 5
        ):
            self.model().get_utterances(begin=self.min_time, end=self.max_time)
        if len(self.model().y.shape) > 1:
            y = self.model().y[begin_samp:end_samp, self.selected_channel]
        else:
            y = self.model().y[begin_samp:end_samp]
        if self.settings.value(self.settings.SPECTRAL_FEATURES) == "mfcc":
            spectrogram_worker = workers.MfccWorker(
                y,
                self.model().file.sound_file.sample_rate,
                self.min_time,
                self.max_time,
                self.selected_channel,
            )
        else:
            spectrogram_worker = workers.SpectrogramWorker(
                y,
                self.model().file.sound_file.sample_rate,
                self.min_time,
                self.max_time,
                self.selected_channel,
            )
        spectrogram_worker.signals.result.connect(self.finalize_loading_spectrogram)
        self.thread_pool.start(spectrogram_worker)

        pitch_track_worker = workers.PitchWorker(
            y,
            self.model().file.sound_file.sample_rate,
            self.min_time,
            self.max_time,
            self.selected_channel,
            self.bottom_point,
            self.separator_point,
        )
        pitch_track_worker.signals.result.connect(self.finalize_loading_pitch_track)
        self.thread_pool.start(pitch_track_worker)

        auto_waveform_worker = workers.AutoWaveformWorker(
            y,
            self.separator_point,
            self.top_point,
            self.min_time,
            self.max_time,
            self.selected_channel,
        )
        auto_waveform_worker.signals.result.connect(self.finalize_loading_auto_wave_form)
        self.thread_pool.start(auto_waveform_worker)

    def clean_up_for_close(self):
        self.closing = True

    @property
    def plot_min(self):
        if self.settings.right_to_left:
            return -self.max_time
        return self.min_time

    @property
    def plot_max(self):
        if self.settings.right_to_left:
            return -self.min_time
        return self.max_time

    def finalize_loading_spectrogram(self, results):
        if self.closing:
            return
        if results is None:
            self.spectrogram = None
            self.min_db = None
            self.max_db = None
            self.spectrogramReady.emit()
            return
        stft, channel, begin, end, min_db, max_db = results
        if begin != self.min_time or end != self.max_time:
            return
        if self.settings.right_to_left:
            stft = np.flip(stft, 1)
        self.spectrogram = stft
        self.min_db = self.min_db
        self.max_db = self.max_db
        self.spectrogramReady.emit()

    def finalize_loading_pitch_track(self, results):
        if self.closing:
            return
        if results is None:
            self.pitch_track_y = None
            self.pitch_track_x = None
            self.pitchTrackReady.emit()
            return
        pitch_track, voicing_track, channel, begin, end, min_f0, max_f0 = results
        if begin != self.min_time or end != self.max_time:
            return
        if self.settings.right_to_left:
            pitch_track = np.flip(pitch_track, 0)
        self.pitch_track_y = pitch_track
        if pitch_track is None:
            return
        x = np.linspace(
            start=self.plot_min,
            stop=self.plot_max,
            num=pitch_track.shape[0],
        )
        self.pitch_track_x = x
        self.pitchTrackReady.emit()

    def finalize_loading_auto_wave_form(self, results):
        if self.closing:
            return
        y, begin, end, channel = results
        if begin != self.min_time or end != self.max_time:
            return
        if self.settings.right_to_left:
            y = np.flip(y, 0)
        x = np.linspace(start=self.plot_min, stop=self.plot_max, num=y.shape[0])
        self.waveform_x = x
        self.waveform_y = y
        self.waveformReady.emit()

    def select_audio(self, begin, end):
        if end is not None and end - begin < 0.025:
            end = None
        self.selected_min_time = begin
        self.selected_max_time = end
        if self.selected_min_time != self.min_time or end is not None:
            self.selectionAudioChanged.emit(False)

    def request_start_time(self, start_time, update=False):
        if start_time >= self.max_time:
            return
        if start_time < self.min_time:
            return
        self.selected_min_time = start_time
        self.selected_max_time = None
        self.selectionAudioChanged.emit(update)

    def set_current_channel(self, channel):
        if channel == self.selected_channel:
            return
        self.selected_channel = channel
        self.load_audio_selection()

    def get_selected_wave_form(self):
        if self.y is None:
            return None, None
        if len(self.y.shape) > 1 and self.y.shape[0] == 2:
            return self.x, self.y[self.selected_channel, :]
        return self.x, self.y

    def zoom(self, factor, mid_point=None):
        if factor == 0 or self.min_time is None:
            return
        cur_duration = self.max_time - self.min_time
        if mid_point is None:
            mid_point = self.min_time + (cur_duration / 2)
        new_duration = cur_duration / factor
        new_begin = mid_point - (mid_point - self.min_time) / factor
        new_begin = max(new_begin, 0)
        new_end = min(new_begin + new_duration, self.model().file.duration)
        if new_end - new_begin <= 0.025:
            return
        self.set_view_times(new_begin, new_end)

    def pan(self, factor):
        if self.min_time is None:
            return
        if factor < 1:
            factor = 1 - factor
            right = True
        else:
            right = False
            factor = factor - 1
        if right and self.max_time == self.model().file.duration:
            return
        if not right and self.min_time == 0:
            return
        cur_duration = self.max_time - self.min_time
        shift = factor * cur_duration
        if right:
            new_begin = self.min_time + shift
            new_end = self.max_time + shift
        else:
            new_begin = self.min_time - shift
            new_end = self.max_time - shift
        if new_begin < 0:
            new_end = new_end + abs(new_begin)
            new_begin = 0
        if new_end > self.model().file.duration:
            new_begin -= self.model().file.duration - new_end
            new_end = self.model().file.duration
        self.set_view_times(new_begin, new_end)

    def zoom_in(self):
        if self.model().file is None:
            return
        self.zoom(1.5)

    def zoom_out(self):
        if self.model().file is None:
            return
        self.zoom(0.5)

    def zoom_to_selection(self):
        if self.selected_min_time is not None and self.selected_max_time is not None:
            begin = self.selected_min_time
            end = self.selected_max_time
        elif len(self.selectedRows(0)) > 0:
            m = self.model()
            begin = 100000
            end = 0
            for index in self.selectedRows(0):
                u = m.utterances[index.row()]
                if u.begin < begin:
                    begin = u.begin
                if u.end > end:
                    end = u.end
        else:
            return
        self.set_view_times(begin, end)

    def update_from_slider(self, value):
        if not self.max_time:
            return
        cur_window = self.max_time - self.min_time
        self.set_view_times(value, value + cur_window)

    def visible_utterances(self) -> typing.List[Utterance]:
        file_utts = []
        if not self.model().file:
            return file_utts
        if self.model().rowCount() > 1:
            for u in self.model().utterances:
                if u.begin >= self.max_time:
                    break
                if u.end <= self.min_time:
                    continue
                file_utts.append(u)
        else:
            file_utts.extend(self.model().utterances)
        return file_utts

    def model(self) -> FileUtterancesModel:
        return super().model()

    def set_view_times(self, begin, end, new_file=False):
        begin = max(begin, 0)
        end = min(end, self.model().file.duration)
        if (begin, end) == (self.min_time, self.max_time):
            return
        self.min_time = begin
        self.max_time = end
        if (
            self.selected_max_time is not None
            and not self.min_time <= self.selected_min_time <= self.max_time
        ):
            self.selected_min_time = self.min_time
        if (
            self.selected_max_time is not None
            and not self.min_time <= self.selected_max_time <= self.max_time
        ):
            self.selected_max_time = None
        self.view_change_timer.start()

    def send_selection_update(self):
        self.viewChanged.emit(self.min_time, self.max_time)

    def set_search_term(self, word):
        query = TextFilterQuery(word, word=True)
        self.searchTermChanged.emit(query)

    def set_current_file(
        self,
        file_id,
        begin,
        end,
        utterance_id,
        speaker_id,
        force_update=False,
        single_utterance=False,
    ):
        try:
            new_file = (
                self.model().file is None
                or self.model().file.id != file_id
                or self.model().file.duration >= 500
            )
        except sqlalchemy.orm.exc.DetachedInstanceError:
            new_file = True
        if force_update and single_utterance:
            new_file = True
        self.requested_utterance_id = utterance_id
        self.selected_min_time = None
        self.selected_max_time = None
        if new_file:
            self.fileAboutToChange.emit()
            if single_utterance:
                self.model().set_file(file_id, utterance_id=utterance_id)
            else:
                self.model().set_file(file_id, begin=begin, end=end)
            self.speakerRequested.emit(speaker_id)
        else:
            self.finalize_set_new_file()
            self.speakerRequested.emit(speaker_id)
        self.set_view_times(begin, end, new_file=True)

    def finalize_set_new_file(self):
        if self.requested_utterance_id is None:
            return
        utterance = self.model().get_utterance(self.requested_utterance_id)
        if utterance is None:
            return
        self.update_select(self.requested_utterance_id, reset=True)
        self.selected_channel = 0
        if utterance is not None and utterance.channel is not None:
            self.selected_channel = utterance.channel
        self.fileChanged.emit()

    def checkSelected(self, utterance_id: int):
        m = self.model()
        for index in self.selectedRows(0):
            if utterance_id == m._indices[index.row()]:
                return True
        return False

    def update_selected_utterances(self, utterances):
        super().clearSelection()
        super().clearCurrentIndex()
        if not utterances:
            return
        flags = QtCore.QItemSelectionModel.SelectionFlag.Rows
        flags |= QtCore.QItemSelectionModel.SelectionFlag.Select
        current_index = None
        for u in utterances:
            if u.id not in self.model().reversed_indices:
                continue
            current_index = u.id
            row = self.model().reversed_indices[u.id]

            index = self.model().index(row, 0)
            if not index.isValid():
                return
            self.select(index, flags)
        self.currentUtteranceChanged.emit(current_index)

    def update_select(self, utterance_id: int, deselect=False, reset=False):
        if reset and [x.id for x in self.selected_utterances()] == [utterance_id]:
            return
        flags = QtCore.QItemSelectionModel.SelectionFlag.Rows
        if reset:
            flags |= QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
        elif deselect:
            flags |= QtCore.QItemSelectionModel.SelectionFlag.Deselect
        else:
            flags |= QtCore.QItemSelectionModel.SelectionFlag.Select
        if utterance_id not in self.model().reversed_indices:
            return
        row = self.model().reversed_indices[utterance_id]

        index = self.model().index(row, 0)
        if not index.isValid():
            return
        self.select(index, flags)
        if not deselect:
            self.select_audio(self.model().utterances[row].begin, self.model().utterances[row].end)
        self.currentUtteranceChanged.emit(utterance_id)


class CorpusSelectionModel(QtCore.QItemSelectionModel):
    fileChanged = QtCore.Signal()
    channelChanged = QtCore.Signal()
    resetView = QtCore.Signal()
    fileAboutToChange = QtCore.Signal()
    fileViewRequested = QtCore.Signal(object, object, object, object, object)
    selectionAudioChanged = QtCore.Signal()
    currentTimeChanged = QtCore.Signal(object)
    currentUtteranceChanged = QtCore.Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = AnchorSettings()
        self.min_time = 0
        self.max_time = 10
        self.selected_min_time = None
        self.selected_max_time = None
        self.x = None
        self.y = None
        self.current_utterance_id = None
        self.selected_channel = 0
        # self.viewChanged.connect(self.update_selected_waveform)
        # self.fileChanged.connect(self.update_selected_waveform)
        self.currentRowChanged.connect(self.switch_utterance)
        # self.selectionChanged.connect(self.update_selection_audio)
        # self.selectionChanged.connect(self.update_selection_audio)
        # self.model().newResults.connect(self.check_selection)
        self.model().unlockCorpus.connect(self.fileChanged.emit)
        self.model().layoutChanged.connect(self._update_selection)

    def set_current_utterance(self, utterance_id):
        self.current_utterance_id = utterance_id
        self.currentUtteranceChanged.emit()

    def check_selection(self):
        if self.currentIndex().row() == -1 and self.model().rowCount() > 0:
            self.update_select_rows([0])
        elif self.model().rowCount() == 0:
            self.clearSelection()

    def clearSelection(self) -> None:
        self.fileAboutToChange.emit()
        self.current_utterance_id = None
        self.min_time = None
        self.max_time = None
        self.selected_min_time = None
        self.selected_max_time = None
        super().clearCurrentIndex()
        super().clearSelection()
        self.fileChanged.emit()

    def update_select_rows(self, rows: list[int]):
        super().clearCurrentIndex()
        super().clearSelection()
        if not rows:
            return
        for r in rows:
            index = self.model().index(r, 0)
            if not index.isValid():
                continue
            self.setCurrentIndex(
                index,
                QtCore.QItemSelectionModel.SelectionFlag.SelectCurrent
                | QtCore.QItemSelectionModel.SelectionFlag.Rows,
            )

    def update_selected_utterances(self, utterances):
        if not utterances:
            return
        first = True
        for u in utterances:
            if u.id not in self.model().reversed_indices:
                continue
            row = self.model().reversed_indices[u.id]

            index = self.model().index(row, 0)
            if not index.isValid():
                return
            if not first:
                flags = QtCore.QItemSelectionModel.SelectionFlag.Rows
                flags |= QtCore.QItemSelectionModel.SelectionFlag.Select
            else:
                flags = QtCore.QItemSelectionModel.SelectionFlag.Rows
                flags |= QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                first = False
            self.select(index, flags)

    def update_select(self, utterance_id: int, deselect=False, reset=False, focus=False):
        if reset and self.selected_utterances() == [utterance_id]:
            return
        flags = QtCore.QItemSelectionModel.SelectionFlag.Rows
        if reset:
            flags |= QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
        elif deselect:
            flags |= QtCore.QItemSelectionModel.SelectionFlag.Deselect
        else:
            flags |= QtCore.QItemSelectionModel.SelectionFlag.Select
        if utterance_id not in self.model().reversed_indices:
            return
        row = self.model().reversed_indices[utterance_id]
        if focus:
            flags |= QtCore.QItemSelectionModel.SelectionFlag.Current
            if row == self.currentIndex().row():
                self.fileViewRequested.emit(*self.model().audio_info_for_utterance(row))

        index = self.model().index(row, 0)
        if not index.isValid():
            return
        self.select(index, flags)

    def _update_selection(self):
        index = self.currentIndex()
        if not index.isValid():
            return
        m = self.model()
        try:
            self.current_utterance_id = m._indices[index.row()]
        except IndexError:
            self.current_utterance_id = None

    def selected_utterances(self):
        current_utterance = self.current_utterance_id
        if current_utterance is None:
            return []
        utts = [current_utterance]
        m = self.model()
        for index in self.selectedRows(1):
            if current_utterance is not None and m._indices[index.row()] == current_utterance:
                continue
            utt = m.utterance_id_at(index)
            if utt is None:
                continue
            if current_utterance is None:
                current_utterance = utt
            utts.append(utt)
        return utts

    def currentText(self):
        index = self.currentIndex()
        if not index:
            return
        if not index.isValid():
            return
        m = self.model()

        text = m.data(m.index(index.row(), m.text_column), QtCore.Qt.ItemDataRole.DisplayRole)
        return text

    def switch_utterance(self, new_index, old_index):
        if not self.model().fully_loaded:
            return
        if not isinstance(new_index, QtCore.QModelIndex):
            row = 0
        else:
            if not new_index.isValid():
                return
            row = new_index.row()
        utt = self.model().utterance_id_at(row)
        if utt is None:
            return
        if utt == self.current_utterance_id:
            return
        self.current_utterance_id = utt
        self.currentUtteranceChanged.emit()
        self.fileViewRequested.emit(*self.model().audio_info_for_utterance(row))

    def model(self) -> CorpusModel:
        return super().model()

    def focus_utterance(self, index):
        m = self.model()
        row = index.row()
        utt_id = m.utterance_id_at(row)
        if utt_id is None:
            self.min_time = 0
            self.max_time = 1
            self.fileAboutToChange()
            self.fileChanged.emit()
            return
        self.current_utterance_id = utt_id
        self.currentUtteranceChanged.emit()
        self.fileViewRequested.emit(*self.model().audio_info_for_utterance(row))


class OovModel(TableModel):
    def __init__(self, parent=None):
        super().__init__(["OOV word", "Count"], parent=parent)
        self.settings = AnchorSettings()
        self.corpus_model: Optional[CorpusModel] = None
        self.sort_index = None
        self.sort_order = None
        self.text_filter = None
        self.current_offset = 0
        self.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))
        self._data = []
        self.indices = []

    def set_corpus_model(self, corpus_model: CorpusModel):
        self.corpus_model = corpus_model
        self.corpus_model.corpusLoading.connect(self.refresh)
        self.corpus_model.dictionaryChanged.connect(self.refresh)

    def refresh(self):
        self.update_result_count()
        self.update_data()

    def finish_update_data(self, result, *args, **kwargs):
        if result is None:
            return
        self.layoutAboutToBeChanged.emit()
        self._data, self.indices = result
        self.layoutChanged.emit()
        self.newResults.emit()

    @property
    def query_kwargs(self) -> typing.Dict[str, typing.Any]:
        kwargs = {
            "text_filter": self.text_filter,
            "limit": self.limit,
            "current_offset": self.current_offset,
        }
        if self.sort_index is not None:
            kwargs["sort_index"] = self.sort_index
            kwargs["sort_desc"] = self.sort_order == QtCore.Qt.SortOrder.DescendingOrder
        return kwargs

    @property
    def count_kwargs(self) -> typing.Dict[str, typing.Any]:
        kwargs = self.query_kwargs
        kwargs["count"] = True
        return kwargs

    def update_result_count(self):
        self.runFunction.emit(
            "Counting OOV results", self.finalize_result_count, [self.count_kwargs]
        )

    def update_data(self):
        self.runFunction.emit("Querying OOVs", self.finish_update_data, [self.query_kwargs])


class DictionaryTableModel(TableModel):
    dictionariesRefreshed = QtCore.Signal(object)
    wordCountsRefreshed = QtCore.Signal()
    requestLookup = QtCore.Signal(object)

    def __init__(self, parent=None):
        super().__init__(["Word", "Word type", "Count", "Pronunciation"], parent=parent)
        self.settings = AnchorSettings()
        self.current_dictionary = None
        self.corpus_model: Optional[CorpusModel] = None
        self.sort_index = None
        self.sort_order = None
        self.text_filter = None
        self.filter_unused = False
        self.current_offset = 0
        self.current_dictionary_id = None
        self._data = []
        self.word_indices = []
        self.pron_indices = []
        self.g2p_generator: typing.Optional[PyniniValidator] = None
        self.word_sets = {}
        self.speaker_mapping = {}

        self.graphemes = []
        self.reference_phone_set = set()
        self.custom_mapping = {}

    @property
    def phones(self):
        phones = [x.phone for x in self.corpus_model.phones.values() if x.phone_type == PhoneType.non_silence]
        if self.corpus_model.corpus.position_dependent_phones:
            phones = sorted(set(x.rsplit("_", maxsplit=1)[0] for x in phones))
        return phones

    def set_custom_mapping(self, path):
        with mfa_open(path, "r") as f:
            self.custom_mapping = {k: v for k, v in yaml.safe_load(f).items() if k in self.phones}
        for v in self.custom_mapping.values():
            self.reference_phone_set.update(v)

    def check_word(self, word, speaker_id) -> bool:
        try:
            dictionary_id = self.speaker_mapping[speaker_id]
        except KeyError:
            return True
        if dictionary_id is not None and self.word_sets[dictionary_id]:
            return unicodedata.normalize("NFKC", word.lower()) in self.word_sets[dictionary_id]
        return True

    def lookup_word(self, word: str) -> None:
        self.requestLookup.emit(word)

    def set_g2p_generator(self, generator: PyniniValidator) -> None:
        self.g2p_generator = generator

    def update_current_index(self, dict_id) -> None:
        if self.current_dictionary_id != dict_id:
            self.current_dictionary_id = dict_id
            self.update_result_count()
            self.update_data()

    def set_corpus_model(self, corpus_model: CorpusModel) -> None:
        self.corpus_model = corpus_model
        self.corpus_model.corpusLoading.connect(self.setup)

    def setup(self) -> None:
        self.refresh_dictionaries()
        specials = self.corpus_model.corpus.specials_set
        specials.update(
            [
                "#0",
                "<space>",
            ]
        )
        self.graphemes = [
            x
            for x, in self.corpus_model.session.query(Grapheme.grapheme).filter(
                ~Grapheme.grapheme.in_(specials)
            )
        ]

    def flags(
        self, index: Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex]
    ) -> QtCore.Qt.ItemFlag:
        if not index.isValid():
            return QtCore.Qt.ItemFlag.ItemIsEnabled
        flags = super().flags(index)
        if index.column() in [0, 3]:
            flags |= QtCore.Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(
        self,
        index: Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
        value: Any,
        role: int = ...,
    ) -> bool:
        if index.isValid() and role == QtCore.Qt.ItemDataRole.EditRole:
            if index.column() == 0:
                self.corpus_model.addCommand.emit(
                    undo.UpdateWordCommand(
                        self.word_indices[index.row()],
                        self._data[index.row()][index.column()],
                        value,
                        self,
                    )
                )
            elif index.column() == 3:
                self.corpus_model.addCommand.emit(
                    undo.UpdatePronunciationCommand(
                        self.pron_indices[index.row()],
                        self._data[index.row()][index.column()],
                        value,
                        self,
                    )
                )
            return True
        return False

    def add_word(self, word, word_id=None):
        self.requestLookup.emit(word)
        self.add_pronunciation(word, word_id)

    def change_word_type(self, word_id: int, current_word_type: WordType):
        if current_word_type is WordType.speech:
            new_word_type = WordType.interjection
        else:
            new_word_type = WordType.speech
        self.corpus_model.addCommand.emit(
            undo.ChangeWordTypeCommand(word_id, current_word_type, new_word_type, self)
        )

    def add_pronunciation(
        self,
        word: str,
        word_id: int = None,
        pronunciation: str = None,
    ):
        if pronunciation is None:
            if self.g2p_generator is None:
                pronunciation = ""
            else:
                try:
                    existing_pronunciations = set()
                    for r in range(self.rowCount()):
                        if self.word_indices[r] != word_id:
                            continue
                        existing_pronunciations.add(self._data[r][2])
                    candidates = self.g2p_generator.rewriter(word)
                    for c, _ in candidates:
                        if c in existing_pronunciations:
                            continue
                        pronunciation = c
                        break
                    else:
                        pronunciation = "spn"
                except pynini.lib.rewrite.Error:
                    pronunciation = "spn"
        self.corpus_model.addCommand.emit(
            undo.AddPronunciationCommand(word, pronunciation, self, word_id=word_id)
        )

    def delete_words(self, word_ids: typing.List[int]):
        self.corpus_model.addCommand.emit(undo.DeleteWordCommand(word_ids, self))

    def delete_pronunciations(self, pronunciation_ids: typing.List[int]):
        self.corpus_model.addCommand.emit(undo.DeletePronunciationCommand(pronunciation_ids, self))

    def data(self, index, role=None):
        if not index.isValid() or index.row() > len(self._data) - 1:
            return
        data = self._data[index.row()][index.column()]
        if role == QtCore.Qt.ItemDataRole.DisplayRole or role == QtCore.Qt.ItemDataRole.EditRole:
            if index.column() == 1:
                data = str(data).split(".")[-1]
            return data

    def finish_refresh_word_counts(self):
        self.corpus_model.session.expire_all()
        self.update_result_count()
        self.update_data()
        self.wordCountsRefreshed.emit()

    def finish_rebuilding_lexicons(self, result):
        lexicon_compiler, dictionary_id = result
        self.corpus_model.corpus.lexicon_compilers[dictionary_id] = lexicon_compiler

    def refresh(self):
        self.update_result_count()
        self.update_data()

    def finish_update_data(self, result, *args, **kwargs):
        if result is None:
            return
        self.layoutAboutToBeChanged.emit()
        self._data, self.word_indices, self.pron_indices = result
        self.layoutChanged.emit()
        self.newResults.emit()

    def finish_update_dictionaries(self, result):
        self.dictionaries, self.word_sets, self.speaker_mapping = result
        self.dictionariesRefreshed.emit(self.dictionaries)

    @property
    def query_kwargs(self) -> typing.Dict[str, typing.Any]:
        kwargs = {
            "dictionary_id": self.current_dictionary_id,
            "text_filter": self.text_filter,
            "limit": self.limit,
            "current_offset": self.current_offset,
            "filter_unused": self.filter_unused,
        }
        if self.sort_index is not None:
            kwargs["sort_index"] = self.sort_index
            kwargs["sort_desc"] = self.sort_order == QtCore.Qt.SortOrder.DescendingOrder
        return kwargs

    @property
    def count_kwargs(self) -> typing.Dict[str, typing.Any]:
        kwargs = self.query_kwargs
        kwargs["count"] = True
        return kwargs

    def refresh_dictionaries(self):
        self.runFunction.emit("Loading dictionaries", self.finish_update_dictionaries, [])

    def update_result_count(self):
        self.runFunction.emit(
            "Counting dictionary results", self.finalize_result_count, [self.count_kwargs]
        )

    def update_word_counts(self):
        self.runFunction.emit(
            "Calculating OOVs",
            self.finish_refresh_word_counts,
            [{"dictionary_id": self.current_dictionary_id}],
        )

    def rebuild_lexicons(self):
        self.runFunction.emit(
            "Rebuilding lexicon FSTs",
            self.finish_rebuilding_lexicons,
            [{"dictionary_id": self.current_dictionary_id}],
        )

    def update_data(self):
        self.runFunction.emit("Querying dictionary", self.finish_update_data, [self.query_kwargs])


class SpeakerModel(TableModel):
    clustered = QtCore.Signal()
    mdsFinished = QtCore.Signal()
    speakersChanged = QtCore.Signal(object)
    mdsAboutToChange = QtCore.Signal()

    NAME_COLUMN = 0
    UTTERANCE_COUNT_COLUMN = 1
    IVECTOR_COLUMN = 3

    def __init__(self, parent=None):
        super().__init__(
            ["Speaker", "Utterances", "Dictionary", "Ivector distance", "View"],
            parent=parent,
        )
        self.settings = AnchorSettings()
        self.speaker_count = None
        self.text_filter = None
        self.speaker_filter = None
        self.sort_index = 1
        self.sort_order = QtCore.Qt.SortOrder.DescendingOrder
        self.all_speakers = []
        self.corpus_model: Optional[CorpusModel] = None
        self.current_speakers: typing.List[int] = []
        self.num_clusters = None
        self.speaker_space = None
        self.mds = None
        self.perplexity = 30.0
        self.cluster_labels = None
        self.distances = None
        self.ivectors = None
        self.utterance_ids = None
        self.alternate_speaker_ids = []
        self.cluster_kwargs = {}
        self.manifold_kwargs = {}
        self.utt2spk = {}

    def indices_updated(self, utterance_ids, speaker_id):
        for u_id in utterance_ids:
            self.utt2spk[u_id] = speaker_id
        speakers = set(self.utt2spk.values())
        self.current_speakers = [x for x in self.current_speakers if x in speakers]
        self.speakersChanged.emit(False)

    def change_speaker(self, utterance_ids, old_speaker_id, new_speaker_id):
        self.corpus_model.addCommand.emit(
            undo.ChangeSpeakerCommand(utterance_ids, old_speaker_id, new_speaker_id, self)
        )

    def change_speakers(self, data, old_speaker_id):
        self.corpus_model.addCommand.emit(
            undo.ChangeSpeakerCommand(data, old_speaker_id=old_speaker_id, speaker_model=self)
        )

    def finish_recalculate(self, result=None):
        if result is not None:
            self.corpus_model.speaker_plda = result

    def finish_breaking_up_speaker(self, utterance_ids):
        self.utterance_ids = utterance_ids
        self.corpus_model.runFunction.emit(
            "Recalculating speaker ivectors",
            self.finish_recalculate,
            [
                {
                    "plda": self.corpus_model.plda,
                    "speaker_plda": self.corpus_model.speaker_plda,
                }
            ],
        )

        self.update_data()
        self.corpus_model.refreshTiers.emit()
        self.corpus_model.changeCommandFired.emit()
        self.corpus_model.statusUpdate.emit(
            f"Created new speakers for {len(self.utterance_ids)} utterances"
        )

    def break_up_speaker(self, old_speaker_id):
        self.corpus_model.runFunction.emit(
            "Breaking up speaker",
            self.finish_breaking_up_speaker,
            [[], old_speaker_id],
        )

    def set_speaker_filter(self, speaker_filter: typing.Union[int, np.ndarray]):
        if isinstance(speaker_filter, int):
            self.current_speakers = [speaker_filter]
        self.speaker_filter = speaker_filter

    def setData(
        self,
        index: Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex],
        value: Any,
        role: int = ...,
    ) -> bool:
        if index.isValid() and role == QtCore.Qt.ItemDataRole.EditRole:
            if index.column() == 0:
                self.corpus_model.addCommand.emit(
                    undo.UpdateSpeakerCommand(
                        self._indices[index.row()],
                        self._data[index.row()][index.column()],
                        value,
                        self,
                    )
                )
            return True
        return False

    def data(self, index, role=None):
        if index.column() > 3:
            return None
        if role == QtCore.Qt.ItemDataRole.DisplayRole or role == QtCore.Qt.ItemDataRole.EditRole:
            return self._data[index.row()][index.column()]
        return super().data(index, role)

    def flags(
        self, index: Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex]
    ) -> QtCore.Qt.ItemFlag:
        if not index.isValid():
            return QtCore.Qt.ItemFlag.ItemIsEnabled
        flags = super().flags(index)
        if index.column() == 0:
            flags |= QtCore.Qt.ItemFlag.ItemIsEditable
        return flags

    def speakerAt(self, row: int):
        return self._indices[row]

    def set_corpus_model(self, corpus_model: CorpusModel):
        self.corpus_model = corpus_model
        self.corpus_model.corpusLoading.connect(self.update_data)

    @property
    def query_kwargs(self) -> typing.Dict[str, typing.Any]:
        kwargs = {
            "limit": self.limit,
            "current_offset": self.current_offset,
            "text_filter": self.text_filter,
            "speaker_filter": self.speaker_filter,
        }
        if self.sort_index is not None:
            kwargs["sort_index"] = self.sort_index
            kwargs["sort_desc"] = self.sort_order == QtCore.Qt.SortOrder.DescendingOrder
        return kwargs

    def finish_update_data(self, result, *args, **kwargs):
        if result is None:
            return
        self.layoutAboutToBeChanged.emit()
        self._data, self._indices = result
        self.layoutChanged.emit()
        self.newResults.emit()

    def finish_clustering(self, result, *args, **kwargs):
        if result is None:
            return
        speaker_ids, c_labels, distances = result
        if speaker_ids != self.current_speakers:
            return
        self.cluster_labels = c_labels
        self.distances = distances
        self.num_clusters = np.max(c_labels) + 1
        self.clustered.emit()

    def finish_mds(self, result, *args, **kwargs):
        if result is None:
            return
        speaker_ids, mds = result
        if speaker_ids != self.current_speakers:
            return
        self.mds = mds
        self.mdsFinished.emit()

    def update_data(self):
        self.runFunction.emit("Querying speakers", self.finish_update_data, [self.query_kwargs])

    @property
    def count_kwargs(self) -> typing.Dict[str, typing.Any]:
        kwargs = self.query_kwargs
        kwargs["count"] = True
        return kwargs

    def update_result_count(self):
        self.runFunction.emit(
            "Counting speaker results", self.finalize_result_count, [self.count_kwargs]
        )

    def change_current_speaker(self, speaker_id: typing.Union[int, typing.List[int]], reset=False):
        self.mds = None
        self.cluster_labels = None
        self.distances = None
        if reset:
            self.current_speakers = []
        if isinstance(speaker_id, int):
            speaker_id = [speaker_id]
        if (
            isinstance(self.speaker_filter, int)
            and self.speaker_filter not in self.current_speakers
        ):
            self.current_speakers.append(self.speaker_filter)
        for s_id in speaker_id:
            if s_id not in self.current_speakers:
                self.current_speakers.append(s_id)
        self.cluster_speaker_utterances()
        self.load_speaker_ivectors()
        self.mds_speaker_utterances()

    def finish_load_ivectors(self, result, *args, **kwargs):
        if result is None:
            return
        speaker_ids, utterance_ids, utt2spk, ivectors = result
        if speaker_ids != self.current_speakers:
            return
        self.utterance_ids = utterance_ids
        self.ivectors = ivectors
        self.utt2spk = utt2spk

    def load_speaker_ivectors(self):
        if not self.current_speakers:
            return
        self.ivectors = None
        self.runFunction.emit(
            "Loading speaker ivectors",
            self.finish_load_ivectors,
            [
                {
                    "speaker_ids": self.current_speakers,
                    "plda": self.corpus_model.plda,
                    "speaker_plda": self.corpus_model.speaker_plda,
                    "working_directory": os.path.join(
                        self.corpus_model.corpus.output_directory, "speaker_diarization"
                    ),
                    "limit": self.manifold_kwargs.get("limit", 500),
                    "distance_threshold": self.manifold_kwargs.get("distance_threshold", 0.0),
                }
            ],
        )

    def update_cluster_kwargs(self, kwargs):
        if kwargs != self.cluster_kwargs:
            self.cluster_kwargs = kwargs
            self.cluster_speaker_utterances()
        else:
            self.clustered.emit()

    def update_manifold_kwargs(self, kwargs):
        if kwargs != self.manifold_kwargs:
            self.manifold_kwargs = kwargs
            self.mds_speaker_utterances()
        else:
            self.mdsFinished.emit()

    def cluster_speaker_utterances(self):
        self.cluster_labels = None
        self.distances = None
        self.num_clusters = None
        if self.corpus_model.corpus is None:
            return
        if not self.current_speakers:
            self.mdsFinished.emit()
            return
        kwargs = {
            "speaker_ids": self.current_speakers,
            "plda": self.corpus_model.plda,
            "speaker_plda": self.corpus_model.speaker_plda,
        }
        kwargs.update(self.cluster_kwargs)
        self.runFunction.emit("Clustering speaker utterances", self.finish_clustering, [kwargs])

    def mds_speaker_utterances(self):
        self.mds = None
        if self.corpus_model.corpus is None:
            return
        if not self.current_speakers:
            return
        kwargs = {
            "speaker_ids": self.current_speakers,
            "perplexity": self.perplexity,
            "plda": self.corpus_model.plda,
            "speaker_plda": self.corpus_model.speaker_plda,
            "speaker_space": self.speaker_space,
        }
        kwargs.update(self.manifold_kwargs)
        self.mdsAboutToChange.emit()
        self.runFunction.emit("Generating speaker MDS", self.finish_mds, [kwargs])


class AlignmentAnalysisModel(TableModel):
    def __init__(self, parent=None):
        columns = [
            "Utterance",
            "Speaker",
            "Phone",
            "Duration",
            "Log-likelihood",
            "Word",
        ]
        super().__init__(columns, parent=parent)
        self.settings = AnchorSettings()
        self.utterance_ids = []
        self.file_ids = []
        self.speaker_ids = []
        self.indices = []
        self.reversed_indices = {}
        self.corpus_model: Optional[CorpusModel] = None
        self.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))
        self.speaker_filter = None
        self.phone_filter = None
        self.less_than = None
        self.greater_than = None
        self.measure = "duration"
        self.exclude_manual = False
        self.relative_duration = False
        self.word_mode = False
        self.sort_index = None
        self.sort_order = None

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.column() > 5:
            return None
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            d = self._data[index.row()][index.column()]
            if index.column() in {3, 4}:
                try:
                    return float(d)
                except TypeError:
                    return "N/A"
            return d
        return super().data(index, role)

    def set_less_than(self, less_than: float):
        if less_than != self.less_than:
            self.current_offset = 0
        self.less_than = less_than

    def set_greater_than(self, greater_than: float):
        if greater_than != self.greater_than:
            self.current_offset = 0
        self.greater_than = greater_than

    def set_exclude_manual(self, exclude_manual: bool):
        if exclude_manual != self.exclude_manual:
            self.current_offset = 0
        self.exclude_manual = exclude_manual

    def set_measure(self, measure: str):
        measure = measure.lower() if measure == "Duration" else "phone_goodness"
        if measure != self.measure:
            self.current_offset = 0
        self.measure = measure

    def set_speaker_filter(self, speaker_id: typing.Union[int, str, None]):
        if speaker_id and not isinstance(speaker_id, int):
            current_speaker = (
                self.corpus_model.corpus.session.query(Speaker)
                .filter(Speaker.name == speaker_id)
                .first()
            )
            speaker_id = current_speaker.id
        if speaker_id != self.speaker_filter:
            self.current_offset = 0
        self.speaker_filter = speaker_id

    def set_word_mode(self, word_mode):
        if word_mode != self.word_mode:
            self.current_offset = 0
        self.word_mode = word_mode

    def set_relative_duration(self, relative_duration):
        if relative_duration != self.relative_duration:
            self.current_offset = 0
        self.relative_duration = relative_duration

    def set_phone_filter(self, phone_id: typing.Union[int, str, None]):
        if phone_id == "":
            phone_id = None
        if phone_id and not isinstance(phone_id, int):
            phone_id = self.corpus_model.phones[phone_id].id
        if phone_id != self.phone_filter:
            self.current_offset = 0
        self.phone_filter = phone_id

    def set_word_filter(self, text_filter: typing.Optional[TextFilterQuery]):
        if text_filter != self.text_filter:
            self.current_offset = 0
        self.text_filter = text_filter

    def set_corpus_model(self, corpus_model: CorpusModel):
        self.corpus_model = corpus_model
        self.corpus_model.corpusLoading.connect(self.update_data)

    def update_sort(self, column, order):
        self.sort_index = column
        self.sort_order = order
        self.update_data()

    def finish_update_data(self, result, *args, **kwargs):
        self.layoutAboutToBeChanged.emit()
        if result is None:
            self._data = []
            self.indices = []
            self.utterance_ids = []
            self.file_ids = []
            self.speaker_ids = []
            self.reversed_indices = {}
        else:
            (
                self._data,
                self.indices,
                self.utterance_ids,
                self.file_ids,
                self.speaker_ids,
                self.reversed_indices,
            ) = result
        self.layoutChanged.emit()
        self.newResults.emit()

    @property
    def query_kwargs(self) -> typing.Dict[str, typing.Any]:
        kwargs = {
            "limit": self.limit,
            "current_offset": self.current_offset,
            "speaker_id": self.speaker_filter if isinstance(self.speaker_filter, int) else None,
            "phone_id": self.phone_filter if isinstance(self.phone_filter, int) else None,
            "word_filter": self.text_filter,
            "word_mode": self.word_mode,
            "less_than": self.less_than,
            "greater_than": self.greater_than,
            "measure": self.measure,
            "relative_duration": self.relative_duration,
            "exclude_manual": self.exclude_manual,
        }
        if self.sort_index is not None:
            kwargs["sort_index"] = self.sort_index
            kwargs["sort_desc"] = self.sort_order == QtCore.Qt.SortOrder.DescendingOrder
        return kwargs

    @property
    def count_kwargs(self) -> typing.Dict[str, typing.Any]:
        kwargs = self.query_kwargs
        kwargs["count"] = True
        return kwargs

    def update_result_count(self):
        self.runFunction.emit(
            "Counting alignment analysis results",
            self.finalize_result_count,
            [self.count_kwargs],
        )

    def update_data(self):
        if not self.corpus_model.has_alignments:
            return
        self.runFunction.emit("Analyzing alignments", self.finish_update_data, [self.query_kwargs])


class DiarizationModel(TableModel):
    changeUtteranceSpeakerRequested = QtCore.Signal(object, object)

    def __init__(self, parent=None):
        columns = [
            "Utterance",
            "Suggested speaker",
            "#",
            "Current speaker",
            "#",
            "Distance",
            "Reassign?",
            "Merge?",
        ]
        super().__init__(columns, parent=parent)
        self.settings = AnchorSettings()
        self.speaker_count = None
        self.utterance_ids = []
        self.file_ids = []
        self.speaker_indices = []
        self.suggested_indices = []
        self.corpus_model: Optional[CorpusModel] = None
        self.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))
        self.speaker_filter = None
        self.alternate_speaker_filter = None
        self.utterance_filter = None
        self.threshold = None
        self.metric = "cosine"
        self.inverted = False
        self.in_speakers = False
        self.selected_speaker_indices = {}

    def data(self, index, role=None):
        if not index.isValid() or index.column() > 5:
            return None
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            d = self._data[index.row()][index.column()]
            if isinstance(d, list):
                d = d[self.selected_speaker_indices.get(index.row(), 0)]
            if index.column() == 5:
                try:
                    return float(d)
                except TypeError:
                    return "N/A"
            elif index.column() in {2, 4}:
                try:
                    return int(d)
                except TypeError:
                    return "N/A"
            return d
        return super().data(index, role)

    def set_threshold(self, threshold: float):
        if threshold != self.threshold:
            self.current_offset = 0
        self.threshold = threshold

    def set_metric(self, metric: str):
        if metric != self.metric:
            self.current_offset = 0
        self.metric = metric

    def set_inverted(self, inverted: bool):
        if inverted != self.inverted:
            self.current_offset = 0
        self.inverted = inverted

    def set_speaker_lookup(self, in_speakers: bool):
        if in_speakers != self.in_speakers:
            self.current_offset = 0
        self.in_speakers = in_speakers

    def set_utterance_filter(self, utterance_id: int):
        if utterance_id != self.utterance_filter:
            self.current_offset = 0
        self.utterance_filter = utterance_id

    def set_text_filter(self, text_filter: TextFilterQuery):
        if text_filter != self.text_filter:
            self.current_offset = 0
        self.text_filter = text_filter

    def set_speaker_filter(self, speaker_id: typing.Union[int, str, None]):
        if speaker_id != self.speaker_filter:
            self.utterance_filter = None
        self.speaker_filter = speaker_id
        if speaker_id:
            if isinstance(speaker_id, int):
                self.speaker_filter = speaker_id
            else:
                current_speaker = (
                    self.corpus_model.corpus.session.query(Speaker)
                    .filter(Speaker.name == speaker_id)
                    .first()
                )
                self.speaker_filter = current_speaker.id

    def set_alternate_speaker_filter(self, speaker_id: typing.Union[int, str, None]):
        self.alternate_speaker_filter = speaker_id
        if speaker_id:
            if isinstance(speaker_id, int):
                self.alternate_speaker_filter = speaker_id
            else:
                current_speaker = (
                    self.corpus_model.corpus.session.query(Speaker)
                    .filter(Speaker.name == speaker_id)
                    .first()
                )
                self.alternate_speaker_filter = current_speaker.id

    def reassign_utterance(self, row: int):
        if not self.corpus_model.editable:
            return
        utterance_id = self.utterance_ids[row]
        if utterance_id is None:
            return
        speaker_id = self.suggested_indices[row]
        if isinstance(speaker_id, list):
            speaker_id = speaker_id[self.selected_speaker_indices.pop(row, 0)]
        old_speaker_id = self.speaker_indices[row]
        self.corpus_model.addCommand.emit(
            undo.ChangeSpeakerCommand([utterance_id], old_speaker_id, speaker_id, self)
        )
        self.layoutAboutToBeChanged.emit()
        self._data.pop(row)
        self.utterance_ids.pop(row)
        self.suggested_indices.pop(row)
        self.speaker_indices.pop(row)

        self.layoutChanged.emit()

    def can_cycle(self, index):
        return isinstance(self._data[index.row()][index.column()], list)

    def change_suggested_speaker(self, row: int):
        d = self._data[row][1]
        if not isinstance(d, list):
            return
        ind = self.selected_speaker_indices.get(row, 0)
        ind += 1
        if ind > len(d) - 1:
            ind = 0
        self.selected_speaker_indices[row] = ind
        self.dataChanged.emit(self.index(row, 1), self.index(row, 5))

    def merge_speakers(self, row: int):
        speaker_id = self.speaker_indices[row]
        if self.inverted:
            utterance_id = self.utterance_ids[row]
            self.corpus_model.addCommand.emit(
                undo.ChangeSpeakerCommand([utterance_id], speaker_id, 0, self)
            )
        else:
            suggested = self.suggested_indices[row]
            if isinstance(suggested, list):
                suggested = suggested[self.selected_speaker_indices.pop(row, 0)]
            self.corpus_model.merge_speakers([suggested, speaker_id])
        self.layoutAboutToBeChanged.emit()
        self._data.pop(row)
        self.utterance_ids.pop(row)
        self.suggested_indices.pop(row)
        self.speaker_indices.pop(row)

        self.layoutChanged.emit()

    def set_corpus_model(self, corpus_model: CorpusModel):
        self.corpus_model = corpus_model
        self.corpus_model.corpusLoading.connect(self.update_data)

    def finish_update_data(self, result, *args, **kwargs):
        self.layoutAboutToBeChanged.emit()
        self.selected_speaker_indices = {}
        if result is None:
            self._data = []
            self.utterance_ids = []
            self.suggested_indices = []
            self.speaker_indices = []
        else:
            (
                self._data,
                self.utterance_ids,
                self.suggested_indices,
                self.speaker_indices,
            ) = result
        self.layoutChanged.emit()
        self.newResults.emit()

    @property
    def query_kwargs(self) -> typing.Dict[str, typing.Any]:
        kwargs = {
            "limit": self.limit,
            "current_offset": self.current_offset,
            "speaker_id": self.speaker_filter if isinstance(self.speaker_filter, int) else None,
            "alternate_speaker_id": self.alternate_speaker_filter
            if isinstance(self.alternate_speaker_filter, int)
            else None,
            "reference_utterance_id": self.utterance_filter,
            "text_filter": self.text_filter,
            "threshold": self.threshold,
            "metric": self.metric,
            "inverted": self.inverted,
            "in_speakers": self.in_speakers,
            "plda": self.corpus_model.plda,
            "speaker_plda": self.corpus_model.speaker_plda,
        }
        return kwargs

    @property
    def count_kwargs(self) -> typing.Dict[str, typing.Any]:
        kwargs = self.query_kwargs
        kwargs["count"] = True
        return kwargs

    def reassign_utterances(self):
        if not self.corpus_model.corpus.has_any_ivectors():
            return
        kwargs = {
            "speaker_id": self.speaker_filter,
            "threshold": self.threshold,
            "metric": self.metric,
            "plda": self.corpus_model.plda,
            "speaker_plda": self.corpus_model.speaker_plda,
        }
        self.runFunction.emit("Reassigning utterances for speaker", self.update_data, [kwargs])

    def update_result_count(self):
        if self.in_speakers:
            self.runFunction.emit(
                "Counting speaker diarization results",
                self.finalize_result_count,
                [self.count_kwargs],
            )
        else:
            self.runFunction.emit(
                "Counting utterance diarization results",
                self.finalize_result_count,
                [self.count_kwargs],
            )

    def update_data(self):
        if not self.corpus_model.corpus.has_any_ivectors():
            return
        if self.in_speakers:
            self.runFunction.emit(
                "Diarizing speakers", self.finish_update_data, [self.query_kwargs]
            )
        else:
            self.runFunction.emit(
                "Diarizing utterances", self.finish_update_data, [self.query_kwargs]
            )


class CorpusModel(TableModel):
    lockCorpus = QtCore.Signal()
    unlockCorpus = QtCore.Signal()
    undoRequested = QtCore.Signal()
    redoRequested = QtCore.Signal()
    playRequested = QtCore.Signal()
    corpusLoaded = QtCore.Signal()
    corpusLoading = QtCore.Signal()
    addCommand = QtCore.Signal(object)
    statusUpdate = QtCore.Signal(object)
    editableChanged = QtCore.Signal(object)
    filesRefreshed = QtCore.Signal(object)
    speakersRefreshed = QtCore.Signal(object)
    changeCommandFired = QtCore.Signal()
    dictionaryChanged = QtCore.Signal()
    acousticModelChanged = QtCore.Signal()
    ivectorExtractorChanged = QtCore.Signal()
    languageModelChanged = QtCore.Signal()
    g2pModelChanged = QtCore.Signal()
    textFilterChanged = QtCore.Signal()
    databaseSynced = QtCore.Signal(bool)
    filesSaved = QtCore.Signal()
    dictionarySaved = QtCore.Signal()
    selectionRequested = QtCore.Signal(object)
    transcribeRequested = QtCore.Signal(object)
    alignRequested = QtCore.Signal(object)
    requestFileView = QtCore.Signal(object)
    utteranceTextUpdated = QtCore.Signal(object, object)
    refreshUtteranceText = QtCore.Signal(object, object)
    refreshTiers = QtCore.Signal()

    def __init__(self, parent=None):
        header = [
            "OOVs?",
            "File",
            "Speaker",
            "Begin",
            "End",
            "Duration",
            "Text",
            "Log-likelihood",
            "Speech log-likelihood",
            "Phone duration deviation",
            "SNR",
            "PER",
            "Overlap score",
            "Transcription",
            "WER",
            "Ivector distance",
            "Diarization variance",
        ]
        super().__init__(header, parent=parent)
        self.oov_column = header.index("OOVs?")
        self.file_column = header.index("File")
        self.speaker_column = header.index("Speaker")
        self.begin_column = header.index("Begin")
        self.end_column = header.index("End")
        self.duration_column = header.index("Duration")
        self.text_column = header.index("Text")
        self.ivector_distance_column = header.index("Ivector distance")
        self.alignment_header_indices = [
            header.index("Log-likelihood"),
            header.index("Speech log-likelihood"),
            header.index("Phone duration deviation"),
            header.index("SNR"),
        ]
        self.alignment_evaluation_header_indices = [
            header.index("PER"),
            header.index("Overlap score"),
        ]
        self.transcription_header_indices = [
            header.index("Transcription"),
            header.index("WER"),
        ]
        self.diarization_header_indices = [
            header.index("Ivector distance"),
            header.index("Diarization variance"),
        ]
        self.filter_nulls = [False for _ in range(len(header))]
        self.sort_index = None
        self.sort_order = None
        self.file_filter = None
        self.speaker_filter = None
        self.text_filter = None
        self.oovs_only = False
        self.regex = False
        self.edit_lock = Lock()
        self.dictionary_model: Optional[DictionaryTableModel] = None
        self.corpus: Optional[Union[AcousticCorpus, AcousticCorpusWithPronunciations]] = None
        self.acoustic_model: Optional[AcousticModel] = None
        self.transcription_acoustic_model: Optional[typing.Union[AcousticModel, str]] = None
        self.language_model: Optional[LanguageModel] = None
        self.ivector_extractor: Optional[IvectorExtractorModel] = None
        self.g2p_model: Optional[G2PModel] = None
        self.align_lexicon_compiler: Optional[LexiconCompiler] = None
        self.transcribe_lexicon_compiler: Optional[LexiconCompiler] = None
        self.plda: Optional[Plda] = None
        self.speaker_plda = None
        self.segmented = True
        self.reversed_indices = {}
        self._indices = []
        self._file_indices = []
        self._speaker_indices = []
        self._data = []
        self.unsaved_files = set()
        self.files = []
        self.speakers = {}
        self.phones = {}
        self.words = {}
        self.speaker_id_mapping = {}
        self.utterances = None
        self.session: sqlalchemy.orm.scoped_session = None
        self.utterance_count = 0
        self.speaker_count = 0
        self.file_count = 0
        self.editable = True
        self.data_types = {
            "WER": "percent",
            "PER": "percent",
        }
        self.has_alignments = False
        self.has_reference_alignments = False
        self.has_transcribed_alignments = False
        self.has_transcriptions = False
        self.latest_alignment_workflow = None
        self.language = None

    def update_filter_nulls(self, toggled, header_index: int):
        self.filter_nulls[header_index] = toggled
        self.update_data()
        self.update_result_count()

    def update_latest_alignment_workflow(self):
        with self.corpus.session() as session:
            query = (
                session.query(CorpusWorkflow.id)
                .filter(CorpusWorkflow.workflow_type.in_(WorkflowType.alignment_workflows()))
                .order_by(sqlalchemy.desc(CorpusWorkflow.time_stamp))
                .limit(1)
            ).first()
            if query is not None:
                query = query[0]
            self.latest_alignment_workflow = query

    def get_interjection_count(self):
        if self.corpus is None:
            return 0
        with self.corpus.session() as session:
            count = (
                session.query(sqlalchemy.func.count(Word.id))
                .filter(Word.word_type == WordType.interjection)
                .first()[0]
            )
        return count

    def get_speaker_name(self, speaker_id: int):
        if speaker_id not in self.speaker_id_mapping:
            with self.corpus.session() as session:
                speaker_name = session.query(Speaker.name).filter(Speaker.id == speaker_id).first()
                if speaker_name is None:
                    return ""
                speaker_name = speaker_name[0]
                self.speaker_id_mapping[speaker_id] = speaker_name
                self.speakers[speaker_name] = speaker_id
        return self.speaker_id_mapping[speaker_id]

    def get_speaker_id(self, speaker_name: str):
        if speaker_name not in self.speakers:
            with self.corpus.session() as session:
                speaker_id = session.query(Speaker.id).filter(Speaker.name == speaker_name).first()
                if speaker_id is None:
                    return None
                speaker_id = speaker_id[0]
                self.speaker_id_mapping[speaker_id] = speaker_name
                self.speakers[speaker_name] = speaker_id
        return self.speakers[speaker_name]

    def set_dictionary_model(self, dictionary_model: DictionaryTableModel):
        self.dictionary_model = dictionary_model

    @property
    def has_dictionary(self):
        if (
            isinstance(self.corpus, AcousticCorpusWithPronunciations)
            and self.corpus.dictionary_model is not None
        ):
            return True
        return False

    def update_utterance_table_row(self, utterance: typing.Union[int, Utterance]):
        if isinstance(utterance, int):
            utterance_id = utterance
            if utterance_id not in self.reversed_indices:
                return
            utterance = self.session.query(Utterance).get(utterance_id)
        else:
            utterance_id = utterance.id
            if utterance_id not in self.reversed_indices:
                return
        index = self.reversed_indices[utterance_id]
        self.layoutAboutToBeChanged.emit()
        self._data[index][self.text_column] = utterance.text
        self._data[index][self.begin_column] = utterance.begin
        self._data[index][self.end_column] = utterance.end
        self._data[index][self.duration_column] = utterance.end - utterance.begin
        self.layoutChanged.emit()

    def change_speaker_table_utterances(self, utterances: typing.List[Utterance]):
        self.layoutAboutToBeChanged.emit()
        for u in utterances:
            if u.id not in self.reversed_indices:
                continue
            index = self.reversed_indices[u.id]
            self._speaker_indices[index] = u.speaker_id
            self._data[index][self.speaker_column] = self.get_speaker_name(u.speaker_id)
        self.layoutChanged.emit()

    def add_table_utterances(self, utterances: typing.List[Utterance]):
        self.layoutAboutToBeChanged.emit()
        rows = []
        for utterance in utterances:
            speaker_name = self.get_speaker_name(utterance.speaker_id)
            row_data = [
                utterance.oovs,
                utterance.file_name,
                speaker_name,
                utterance.begin,
                utterance.end,
                utterance.end - utterance.begin,
                utterance.text,
            ]
            self._data.append(row_data)
            self._indices.append(utterance.id)
            self._file_indices.append(utterance.file_id)
            self._speaker_indices.append(utterance.speaker_id)
            self.reversed_indices[utterance.id] = len(self._indices) - 1
            rows.append(self.reversed_indices[utterance.id])
        self.layoutChanged.emit()
        self.selectionRequested.emit(rows)

    def delete_table_utterances(self, utterances: typing.List[Utterance]):
        self.layoutAboutToBeChanged.emit()
        for utterance in utterances:
            try:
                index = self.reversed_indices.pop(utterance.id)
            except KeyError:
                continue
            _ = self._data.pop(index)
            _ = self._indices.pop(index)
            _ = self._file_indices.pop(index)
            _ = self._speaker_indices.pop(index)
            self.reversed_indices = {
                k: v if v < index else v - 1 for k, v in self.reversed_indices.items()
            }
        self.layoutChanged.emit()
        self.selectionRequested.emit(None)

    def split_table_utterances(
        self, merged_utterance: Utterance, split_utterances: typing.List[Utterance]
    ):
        try:
            index = self.reversed_indices.pop(merged_utterance.id)
        except KeyError:
            return

        self.layoutAboutToBeChanged.emit()
        first = split_utterances[0]
        file_name = self._data[index][1]
        speaker_name = self._data[index][2]
        row_data = [
            first.oovs,
            file_name,
            speaker_name,
            first.begin,
            first.end,
            first.end - first.begin,
            first.text,
        ]
        self._data[index] = row_data
        self._indices[index] = first.id
        self._file_indices[index] = first.file_id
        self._speaker_indices[index] = first.speaker_id
        self.reversed_indices[first.id] = index
        rows = [index]
        for utterance in split_utterances[1:]:
            index += 1
            rows.append(index)
            self.reversed_indices = {
                k: v if v < index else v + 1 for k, v in self.reversed_indices.items()
            }

            row_data = [
                utterance.oovs,
                file_name,
                speaker_name,
                utterance.begin,
                utterance.end,
                utterance.end - utterance.begin,
                utterance.text,
            ]
            self.reversed_indices[utterance.id] = index
            self._data.insert(index, row_data)
            self._indices.insert(index, utterance.id)
            self._file_indices.insert(index, utterance.file_id)
            self._speaker_indices.insert(index, utterance.speaker_id)
        self.layoutChanged.emit()
        self.selectionRequested.emit(rows)

    def merge_table_utterances(
        self, merged_utterance: Utterance, split_utterances: typing.List[Utterance]
    ):
        try:
            split_utterances = sorted(split_utterances, key=lambda x: self.reversed_indices[x.id])
        except KeyError:
            return
        self.layoutAboutToBeChanged.emit()
        row_data = [
            merged_utterance.oovs,
            merged_utterance.file_name,
            merged_utterance.speaker_name,
            merged_utterance.begin,
            merged_utterance.end,
            merged_utterance.end - merged_utterance.begin,
            merged_utterance.text,
        ]
        first = split_utterances[0]
        index = self.reversed_indices.pop(first.id)
        self._data[index] = row_data
        self._indices[index] = merged_utterance.id
        self._file_indices[index] = merged_utterance.file_id
        self._speaker_indices[index] = merged_utterance.speaker_id
        self.reversed_indices[merged_utterance.id] = index
        rows = [index]
        for utterance in split_utterances[1:]:
            index = self.reversed_indices.pop(utterance.id)
            _ = self._data.pop(index)
            _ = self._indices.pop(index)
            _ = self._file_indices.pop(index)
            _ = self._speaker_indices.pop(index)
            self.reversed_indices = {
                k: v if v < index else v - 1 for k, v in self.reversed_indices.items()
            }
        self.layoutChanged.emit()
        self.selectionRequested.emit(rows)

    def update_sort(self, column, order):
        self.sort_index = column
        self.sort_order = order
        self.update_data()

    def lock_edits(self, checked):
        if checked:
            self.editable = False
            self.session.commit()
            self.editableChanged.emit(self.editable)
        else:
            self.editable = True
            self.editableChanged.emit(self.editable)

    def set_acoustic_model(self, acoustic_model: AcousticModel, for_transcription=False):
        if for_transcription:
            self.transcription_acoustic_model = acoustic_model
        else:
            self.acoustic_model = acoustic_model
        self.acousticModelChanged.emit()

    def set_ivector_extractor(self, ivector_extractor: IvectorExtractorModel):
        self.ivector_extractor = ivector_extractor
        self.ivectorExtractorChanged.emit()

    def set_language_model(self, language_model: LanguageModel):
        self.language_model = language_model
        self.languageModelChanged.emit()

    def set_file_modified(self, file_id: typing.Union[int, typing.List[int]]):
        if isinstance(file_id, int):
            file_id = [file_id]
        data = {File.modified: True}
        self.session.query(File).filter(File.id.in_(file_id)).update(data)
        self.session.commit()

    def set_speaker_modified(self, speaker_id: typing.Union[int, typing.List[int]]):
        if isinstance(speaker_id, int):
            speaker_id = [speaker_id]
        self.session.query(Speaker).filter(Speaker.id.in_(speaker_id)).update(
            {Speaker.modified: True}
        )
        self.session.commit()

    def check_align_lexicon_compiler(self):
        if self.acoustic_model is None:
            return
        if self.align_lexicon_compiler is None:
            dictionary_id = self.dictionary_model.current_dictionary_id
            self.align_lexicon_compiler = self.corpus.build_lexicon_compiler(
                dictionary_id, self.acoustic_model
            )

    def check_transcribe_lexicon_compiler(self):
        if self.acoustic_model is None:
            return
        if self.transcribe_lexicon_compiler is None:
            dictionary_id = self.dictionary_model.current_dictionary_id
            self.transcribe_lexicon_compiler = self.corpus.build_lexicon_compiler(
                dictionary_id, self.acoustic_model, disambiguation=True
            )

    def merge_speakers(self, speakers: list[int]):
        self.addCommand.emit(undo.MergeSpeakersCommand(speakers, self))

    def replace_all(self, search_query: TextFilterQuery, replacement: str):
        self.addCommand.emit(undo.ReplaceAllCommand(search_query, replacement, self))

    def utterance_id_at(self, index) -> Optional[Utterance]:
        if not isinstance(index, int):
            if not index.isValid():
                return None
            index = index.row()
        if index > len(self._indices) - 1:
            return None
        if len(self._indices) == 0:
            return None
        return self._indices[index]

    def audio_info_for_utterance(self, row: int):
        return (
            self._file_indices[row],
            self._data[row][self.begin_column],
            self._data[row][self.end_column],
            self._indices[row],
            self._speaker_indices[row],
        )

    def finish_export_files(self):
        self.filesSaved.emit()

    def export_changes(self):
        self.runFunction.emit("Exporting files", self.finish_export_files, [])

    def setCorpus(self, corpus: Optional[AcousticCorpus]):
        self.corpus = corpus
        if corpus is not None:
            self.session = self.corpus.session
            self.corpusLoading.emit()
            self.refresh_files()
            self.refresh_speakers()
            self.refresh_phones()
            self.refresh_words()
            self.refresh_utterances()
            self.update_latest_alignment_workflow()

    def search(
        self,
        text_filter: TextFilterQuery,
        file_id: typing.Union[int, str, None],
        speaker_id: typing.Union[int, str, None],
        oovs=False,
    ):
        self.text_filter = text_filter
        self.speaker_filter = speaker_id
        self.file_filter = file_id
        self.oovs_only = oovs
        self.textFilterChanged.emit()
        self.refresh_utterances()

    @property
    def fully_loaded(self):
        if not self.files:
            return False
        if not self.speakers:
            return False
        return True

    def finish_update_files(self, files):
        self.files = files
        self.filesRefreshed.emit(self.files)
        if self.fully_loaded:
            self.corpusLoaded.emit()

    def finish_update_speakers(self, result):
        self.speakers, self.speaker_id_mapping = result
        self.speakersRefreshed.emit(self.speakers)
        if self.fully_loaded:
            self.corpusLoaded.emit()

    def refresh_utterances(self):
        self.update_data()
        self.update_result_count()

    def refresh_files(self):
        self.runFunction.emit("Loading files", self.finish_update_files, [])

    def refresh_speakers(self):
        self.runFunction.emit("Loading speakers", self.finish_update_speakers, [])

    def refresh_phones(self):
        self.phones = {}
        with self.corpus.session() as session:
            phones = (
                session.query(Phone)
                .filter(
                    Phone.phone_type.in_([PhoneType.non_silence, PhoneType.oov, PhoneType.silence])
                )
                .all()
            )
            for p in phones:
                self.phones[p.phone] = p

    def refresh_words(self):
        self.words = {}
        with self.corpus.session() as session:
            words = session.query(Word).order_by(Word.word).all()
            for w in words:
                self.words[w.word] = w

    def data(self, index, role):
        if not index.isValid():
            return None
        try:
            data = self._data[index.row()][index.column()]
        except IndexError:
            return None
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            column_name = self.headerData(
                index.column(),
                QtCore.Qt.Orientation.Horizontal,
                QtCore.Qt.ItemDataRole.DisplayRole,
            )
            if column_name in self.data_types:
                if self.data_types[column_name] == "percent":
                    if data is None:
                        if index.column() == self.duration_column:
                            return (
                                self._data[index.row()][self.end_column]
                                - self._data[index.row()][self.begin_column]
                            )
                        return None
                    return f"{data*100:.2f}%"
            return data
        elif role == QtCore.Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            if data:
                return QtCore.Qt.CheckState.Checked
            else:
                return QtCore.Qt.CheckState.Unchecked

    def update_texts(self, texts: typing.Dict[int, str]):
        for utt_id, row_ind in self.reversed_indices.items():
            if utt_id in texts:
                self._data[row_ind][self.text_column] = texts[utt_id]
                index = self.index(row_ind, self.text_column)
                self.dataChanged.emit(index, index, [QtCore.Qt.ItemDataRole.DisplayRole])
                self.refreshUtteranceText.emit(utt_id, texts[utt_id])

    def clear_data(self):
        self.layoutAboutToBeChanged.emit()
        self.reversed_indices = {}
        self._indices = []
        self._file_indices = []
        self._speaker_indices = []
        self._data = []
        self.unsaved_files = set()
        self.files = []
        self.speakers = {}
        self.speaker_id_mapping = {}
        self.layoutChanged.emit()

    def finish_update_data(self, result, *args, **kwargs):
        if not result:
            return
        self.layoutAboutToBeChanged.emit()
        (
            self._data,
            self._indices,
            self._file_indices,
            self._speaker_indices,
            self.reversed_indices,
        ) = result
        self.layoutChanged.emit()
        self.newResults.emit()
        # if len(self._data) > 0:
        #    self.selectionRequested.emit([0])

    @property
    def count_kwargs(self) -> typing.Dict[str, typing.Any]:
        kwargs = self.query_kwargs
        kwargs["count"] = True
        return kwargs

    @property
    def query_kwargs(self) -> typing.Dict[str, typing.Any]:
        kwargs = {
            "speaker_filter": self.speaker_filter,
            "file_filter": self.file_filter,
            "text_filter": self.text_filter,
            "oovs_only": self.oovs_only,
            "limit": self.limit,
            "current_offset": self.current_offset,
            "has_ivectors": self.corpus.has_any_ivectors(),
            "filter_nulls": self.filter_nulls,
        }
        if self.sort_index is not None:
            kwargs["sort_index"] = self.sort_index
            kwargs["sort_desc"] = self.sort_order == QtCore.Qt.SortOrder.DescendingOrder
        return kwargs

    def finalize_result_count(self, result_count):
        if not isinstance(result_count, int):
            return
        self.result_count = result_count
        self.resultCountChanged.emit(self.result_count)

    def update_data(self):
        self.runFunction.emit("Querying utterances", self.finish_update_data, [self.query_kwargs])

    def update_result_count(self):
        self.runFunction.emit(
            "Counting utterance results", self.finalize_result_count, [self.count_kwargs]
        )


class MfaModelTableModel(QtCore.QAbstractTableModel):
    model_type = None

    def __init__(self, session: sqlalchemy.orm.Session, model_manager: ModelManager, parent=None):
        super().__init__(parent)
        self.session = session
        self.model_manager = model_manager
        self._header_data = ["Status", "Name", "Path"]
        model_class = anchor.db.MODEL_TYPES[self.model_type]
        self.models = (
            self.session.query(model_class)
            .filter(model_class.name != "speechbrain")
            .order_by(model_class.name)
            .all()
        )
        self.result_count = None
        self.sort_index = None
        self.sort_order = None
        self.current_offset = 0
        self.limit = 1
        self.text_filter = None
        self.header_mapping = {1: "name", 2: "path"}

    def headerData(self, index, orientation, role=None, *args, **kwargs):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._header_data[index]

    def data(self, index, role=None):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            model = self.models[index.row()]
            if index.column() == 0:
                status = "available"
                if not os.path.exists(model.path):
                    if model.name in self.model_manager.remote_models[self.model_type]:
                        status = "remote"
                    else:
                        status = "unavailable"
                return status
            return str(getattr(model, self.header_mapping[index.column()]))

    def add_model(self, path):
        m = self.session.query(self.model_type).filter_by(path=path).first()
        if m is not None:
            return
        self.layoutAboutToBeChanged.emit()
        m_name = os.path.basename(path)
        m = anchor.db.MODEL_TYPES[self.model_type](name=m_name, path=path, available_locally=True)
        self.session.add(m)
        self.session.commit()
        self.models.append(m)
        self.layoutChanged.emit()

    def download_model(self, row):
        from montreal_forced_aligner.models import MODEL_TYPES

        self.layoutAboutToBeChanged.emit()
        m = self.models[row]
        if m.name in self.model_manager.remote_models[self.model_type]:
            self.model_manager.download_model(self.model_type, m.name)
            m.path = MODEL_TYPES[self.model_type].get_pretrained_path(m.name)
            m.available_locally = True
            m.last_used = datetime.datetime.now()
        self.session.commit()
        self.layoutChanged.emit()

    def remove_model(self, row):
        self.layoutAboutToBeChanged.emit()
        if self.models[row].name in self.model_manager.local_models[self.model_type]:
            os.remove(self.models[row].path)
            self.models[row].path = ""
            self.models[row].available_locally = False
        else:
            m = self.models.pop(row)
            self.session.delete(m)
        self.session.commit()
        self.layoutChanged.emit()

    def rowCount(self, parent=None):
        return len(self.models)

    def columnCount(self, parent=None):
        return len(self._header_data)


class CorpusTableModel(QtCore.QAbstractTableModel):
    corpusDataDeleteRequested = QtCore.Signal()

    def __init__(self, session: sqlalchemy.orm.Session, parent=None):
        super().__init__(parent)
        self._header_data = ["Status", "Name", "Path"]
        self.session = session
        self.corpora = (
            self.session.query(anchor.db.AnchorCorpus).order_by(anchor.db.AnchorCorpus.name).all()
        )
        self.result_count = None
        self.sort_index = None
        self.sort_order = None
        self.current_offset = 0
        self.limit = 1
        self.text_filter = None
        self.header_mapping = {1: "name", 2: "path"}

    def headerData(self, index, orientation, role=None, *args, **kwargs):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._header_data[index]

    def data(self, index, role=None):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            model = self.corpora[index.row()]
            if index.column() == 0:
                status = "unknown"
                if not os.path.exists(model.path):
                    status = "unavailable"
                return status
            return str(getattr(model, self.header_mapping[index.column()]))

    def add_corpus(self, corpus_directory, **kwargs):
        self.layoutAboutToBeChanged.emit()
        self.session.query(anchor.db.AnchorCorpus).update({anchor.db.AnchorCorpus.current: False})
        self.session.commit()
        corpus_name = os.path.basename(corpus_directory)
        c = anchor.db.AnchorCorpus(name=corpus_name, path=corpus_directory, current=True, **kwargs)
        self.session.add(c)
        self.session.commit()
        self.corpora.append(c)
        self.layoutChanged.emit()

    def reset_corpus(self, row):
        corpus = self.corpora[row]
        if corpus.current:
            self.corpusDataDeleteRequested.emit()
        logger.debug(f"Dropping {corpus.name} database...")
        proc = subprocess.run(
            [
                "dropdb",
                f"--host={config.database_socket()}",
                "--if-exists",
                "--force",
                corpus.name,
            ],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            check=True,
            encoding="utf-8",
        )
        logger.debug(f"Stdout: {proc.stdout}")
        logger.debug(f"Stderr: {proc.stderr}")

    def remove_corpus(self, row):
        self.layoutAboutToBeChanged.emit()
        self.reset_corpus(row)
        corpus = self.corpora.pop(row)
        self.session.delete(corpus)
        self.session.commit()
        self.layoutChanged.emit()

    def rowCount(self, parent=None):
        return len(self.corpora)

    def columnCount(self, parent=None):
        return len(self._header_data)


class AcousticModelTableModel(MfaModelTableModel):
    model_type = "acoustic"


class G2PModelTableModel(MfaModelTableModel):
    model_type = "g2p"


class DictionaryModelTableModel(MfaModelTableModel):
    model_type = "dictionary"


class LanguageModelTableModel(MfaModelTableModel):
    model_type = "language_model"


class IvectorExtractorTableModel(MfaModelTableModel):
    model_type = "ivector"
