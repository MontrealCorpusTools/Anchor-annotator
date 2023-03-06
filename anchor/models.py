from __future__ import annotations

import os
import re
import typing
from threading import Lock
from typing import Any, Optional, Union

import numpy as np
import pynini.lib.rewrite
import sqlalchemy
import yaml
from dataclassy import dataclass
from montreal_forced_aligner.corpus.acoustic_corpus import (
    AcousticCorpus,
    AcousticCorpusWithPronunciations,
)
from montreal_forced_aligner.data import PhoneType
from montreal_forced_aligner.db import File, Phone, Speaker, Utterance
from montreal_forced_aligner.g2p.generator import PyniniValidator
from montreal_forced_aligner.models import (
    AcousticModel,
    G2PModel,
    IvectorExtractorModel,
    LanguageModel,
)
from montreal_forced_aligner.utils import mfa_open
from PySide6 import QtCore
from sqlalchemy.orm import joinedload, scoped_session

from anchor import undo
from anchor.settings import AnchorSettings


# noinspection PyUnresolvedReferences
@dataclass(slots=True)
class TextFilterQuery:
    text: str
    regex: bool = False
    word: bool = False
    case_sensitive: bool = False

    @property
    def search_text(self):
        if not self.case_sensitive:
            return self.text.lower()
        return self.text

    def generate_expression(self, posix=False):
        text = self.text
        if not self.case_sensitive:
            text = text.lower()
        if not text:
            return text
        if not self.regex:
            text = re.escape(text)
        word_break_set = r"\b"
        if posix:
            word_break_set = r"\y"
            text = text.replace(r"\b", word_break_set)
        if self.word:
            if not text.startswith(word_break_set):
                text = word_break_set + text
            if not text.endswith(word_break_set):
                text += word_break_set
        if self.regex or self.word:
            if not self.case_sensitive:
                text = "(?i)" + text

        return text


class TableModel(QtCore.QAbstractTableModel):
    runFunction = QtCore.Signal(object, object, object)  # Function plus finished processor
    resultCountChanged = QtCore.Signal(int)
    newResults = QtCore.Signal()

    def __init__(self, header_data, parent=None):
        super(TableModel, self).__init__(parent)
        self._header_data = header_data
        self._data = []
        self.result_count = None
        self.sort_index = None
        self.sort_order = None
        self.current_offset = 0
        self.limit = 1
        self.text_filter = None

    def set_text_filter(self, text_filter: TextFilterQuery):
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

    def headerData(self, index, orientation, role):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._header_data[index]

    def data(self, index, role=None):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._data[index.row()][index.column()]

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self._header_data)


class CorpusSelectionModel(QtCore.QItemSelectionModel):
    fileChanged = QtCore.Signal()
    channelChanged = QtCore.Signal()
    resetView = QtCore.Signal()
    fileAboutToChange = QtCore.Signal()
    viewChanged = QtCore.Signal(object, object)
    selectionAudioChanged = QtCore.Signal()
    currentTimeChanged = QtCore.Signal(object)

    def __init__(self, *args, **kwargs):
        super(CorpusSelectionModel, self).__init__(*args, **kwargs)
        self.min_time = 0
        self.max_time = 10
        self.selected_min_time = None
        self.selected_max_time = None
        self.current_file: Optional[File] = None
        self.x = None
        self.y = None
        self.current_utterance_id = None
        self.selected_channel = 0
        # self.viewChanged.connect(self.update_selected_waveform)
        # self.fileChanged.connect(self.update_selected_waveform)
        self.currentRowChanged.connect(self.switch_utterance)
        # self.selectionChanged.connect(self.update_selection_audio)
        # self.selectionChanged.connect(self.update_selection_audio)
        # self.model().changeCommandFired.connect(self.expire_current)
        self.model().layoutChanged.connect(self.check_selection)
        self.model().unlockCorpus.connect(self.fileChanged.emit)
        self.model().selectionRequested.connect(self.update_select_rows)

    def check_selection(self):
        if self.currentIndex().row() == -1 and self.model().rowCount() > 0:
            self.update_select_rows([0])
        elif self.model().rowCount() == 0:
            self.clearSelection()

    def set_current_channel(self, channel):
        self.selected_channel = channel
        self.channelChanged.emit()

    def clearSelection(self) -> None:
        self.fileAboutToChange.emit()
        self.current_file = None
        self.current_utterance_id = None
        self.min_time = None
        self.max_time = None
        self.selected_min_time = None
        self.selected_max_time = None
        super(CorpusSelectionModel, self).clearCurrentIndex()
        super(CorpusSelectionModel, self).clearSelection()
        self.fileChanged.emit()

    def update_selected_wavform(self, *args):
        if self.min_time is None or self.current_file is None:
            self.x = None
            self.y = None
        else:
            self.x, self.y = self.current_file.sound_file.normalized_waveform(
                self.min_time, self.max_time
            )

    def get_selected_wave_form(self):
        if self.y is None:
            return None, None
        if len(self.y.shape) > 1 and self.y.shape[0] == 2:
            return self.x, self.y[self.selected_channel, :]
        return self.x, self.y

    def update_select_rows(self, rows: list[int]):
        super(CorpusSelectionModel, self).clearCurrentIndex()
        super(CorpusSelectionModel, self).clearSelection()
        if not rows:
            return
        for r in rows:
            self.setCurrentIndex(
                self.model().index(r, 0),
                QtCore.QItemSelectionModel.SelectionFlag.SelectCurrent
                | QtCore.QItemSelectionModel.SelectionFlag.Rows,
            )

    def update_select(self, utterance_id: int, deselect=False, reset=False, focus=False):
        if reset and [x.id for x in self.selectedUtterances()] == [utterance_id]:
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
                self.update_view_times(force_update=True)
        self.select(self.model().index(row, 0), flags)

    def select_audio(self, begin, end):
        if end is not None and end - begin < 0.025:
            end = None
        self.selected_min_time = begin
        self.selected_max_time = end
        self.selectionAudioChanged.emit()

    def request_start_time(self, start_time):
        if start_time >= self.max_time:
            return
        if start_time < self.min_time:
            return
        self.selected_min_time = start_time
        self.selected_max_time = None
        self.selectionAudioChanged.emit()

    def visible_utts(self) -> typing.List[Utterance]:
        file_utts = []
        if not self.current_file:
            return file_utts
        if self.current_file.num_utterances > 1:
            for u in sorted(self.current_file.utterances, key=lambda x: x.begin):
                if u.begin >= self.max_time:
                    break
                if u.end <= self.min_time:
                    continue
                file_utts.append(u)
        else:
            file_utts.extend(self.current_file.utterances)
        return file_utts

    def currentUtterance(self) -> Optional[Utterance]:
        utts = self.selectedUtterances()
        if not utts:
            return
        return utts[-1]

    def selectedUtterances(self):
        utts = []
        m = self.model()
        current_utterance = m.utteranceAt(self.currentIndex())
        for index in self.selectedRows(1):
            utt = m.utteranceAt(index)
            if utt is None:
                continue
            if current_utterance is None:
                current_utterance = utt
            if utt.file_id != current_utterance.file_id:
                continue
            utts.append(utt)
        return utts

    def currentText(self):
        index = self.currentIndex()
        if not index:
            return
        m = self.model()

        text = m.data(m.index(index.row(), m.text_column), QtCore.Qt.ItemDataRole.DisplayRole)
        return text

    def zoom(self, factor, mid_point=None):
        if factor == 0:
            return
        cur_duration = self.max_time - self.min_time
        if mid_point is None:
            mid_point = self.min_time + (cur_duration / 2)
        new_duration = cur_duration / factor
        new_begin = mid_point - (mid_point - self.min_time) / factor
        new_begin = max(new_begin, 0)
        new_end = min(new_begin + new_duration, self.current_file.duration)
        if new_end - new_begin <= 0.025:
            return
        self.set_view_times(new_begin, new_end)

    def pan(self, factor):
        if factor < 1:
            factor = 1 - factor
            right = True
        else:
            right = False
            factor = factor - 1
        if right and self.max_time == self.current_file.duration:
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
        if new_end > self.current_file.duration:
            new_begin -= self.current_file.duration - new_end
            new_end = self.current_file.duration
        self.set_view_times(new_begin, new_end)

    def zoom_in(self):
        if self.current_file is None:
            return
        self.zoom(1.5)

    def zoom_out(self):
        if self.current_file is None:
            return
        self.zoom(0.5)

    def zoom_to_selection(self):
        if self.selected_min_time is None or self.selected_max_time is None:
            rows = self.selectedRows(1)
            if not rows:
                return
            begin = None
            end = None
            for r in rows:
                u = self.model().utteranceAt(r)
                if u is None:
                    continue
                if u.file_id != self.current_file.id:
                    continue
                if begin is None or begin > u.begin:
                    begin = u.begin
                if end is None or end < u.end:
                    end = u.end
            self.set_view_times(begin, end)
        else:
            self.set_view_times(self.selected_min_time, self.selected_max_time)

    def update_from_slider(self, value):
        if not self.max_time:
            return
        cur_window = self.max_time - self.min_time
        self.set_view_times(value, value + cur_window)

    def update_selection_audio(self):
        begins = self.selectedRows(self.model().begin_column)
        ends = self.selectedRows(self.model().end_column)
        begin = None
        end = None
        if len(begins) > 0:
            for i, b in enumerate(begins):
                b = self.model().data(b, QtCore.Qt.ItemDataRole.DisplayRole)
                e = self.model().data(ends[i], QtCore.Qt.ItemDataRole.DisplayRole)
                if begin is None or begin > b:
                    begin = b
                if end is None or end < e:
                    end = e
            if self.current_file is None or begin > self.current_file.duration:
                begin = None
                end = None
            elif end > self.current_file.duration:
                end = self.current_file.duration
        self.selected_min_time = begin
        self.selected_max_time = end
        self.selectionAudioChanged.emit()

    def switch_utterance(self, new_index, old_index):
        if not isinstance(new_index, QtCore.QModelIndex):
            row = 0
        else:
            row = new_index.row()
        utt = self.model().utteranceAt(row)
        if utt is None:
            return
        if utt.id == self.current_utterance_id:
            return
        self.current_utterance_id = utt.id
        self.set_current_file(
            utt.file_id, utt.begin, utt.end, channel=utt.channel, force_update=True
        )

    def update_view_times(self, *args, force_update=False):
        utts = self.selectedUtterances()
        if len(utts) == 0:
            self.resetView.emit()
            return
        if len(utts) == 1:
            force_update = True
        begin = utts[0].begin
        f_id = utts[0].file_id
        end_ind = -1
        while True:
            if utts[end_ind].file_id == f_id:
                end = utts[end_ind].end
                break
        self.set_current_file(f_id, begin, end, channel=utts[0].channel, force_update=force_update)
        self.selected_min_time = self.min_time

    def model(self) -> CorpusModel:
        return super(CorpusSelectionModel, self).model()

    def checkSelected(self, utterance: Utterance):
        m = self.model()
        for index in self.selectedRows(1):
            if utterance.id == m._indices[index.row()]:
                return True
        return False

    def set_current_file(self, file_id, begin=None, end=None, channel=None, force_update=False):
        if self.current_file is None or self.current_file.id != file_id:
            self.selected_min_time = None
            self.selected_max_time = None
            self.fileAboutToChange.emit()
            self.selected_channel = 0 if channel is None else channel
            self.current_file = (
                self.model().session.query(File).options(joinedload(File.sound_file)).get(file_id)
            )
            self.min_time = begin
            self.max_time = end
            self.fileChanged.emit()
        elif (
            self.current_file is not None
            and begin is not None
            and end is not None
            and force_update
        ):
            self.selected_channel = channel
            self.set_view_times(begin, end)

    def set_view_times(self, begin, end):
        begin = max(begin, 0)
        end = min(end, self.current_file.duration)
        if (begin, end) == (self.min_time, self.max_time):
            return
        self.min_time = begin
        self.max_time = end
        self.selected_min_time = self.min_time
        if self.selected_max_time is not None and self.selected_max_time > self.max_time:
            self.selected_max_time = None
        self.viewChanged.emit(self.min_time, self.max_time)

    def focusUtterance(self, index):
        m = self.model()
        u = m.utteranceAt(index)
        if u is None:
            self.min_time = 0
            self.max_time = 1
            self.fileAboutToChange()
            self.current_file = None
            self.fileChanged.emit()
            return
        self.current_file = u.file
        begin = u.begin
        end = u.end
        padding = 1
        self.set_view_times(begin - padding, end + padding)
        self.selectionAudioChanged.emit()


class OovModel(TableModel):
    def __init__(self, parent=None):
        super().__init__(["OOV word", "Count"], parent=parent)
        self.settings = AnchorSettings()
        self.font = self.settings.font
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
        super().__init__(["Word", "Count", "Pronunciation"], parent=parent)
        self.settings = AnchorSettings()
        self.font = self.settings.font
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
        self.phones = []
        self.reference_phone_set = set()
        self.custom_mapping = {}

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
            return word.lower() in self.word_sets[dictionary_id]
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
        phones = [
            x
            for x, in self.corpus_model.session.query(Phone.phone).filter(
                Phone.phone_type == PhoneType.non_silence
            )
        ]
        if self.corpus_model.corpus.position_dependent_phones:
            phones = sorted(set(x.rsplit("_", maxsplit=1)[0] for x in phones))
        self.phones = phones

    def flags(
        self, index: Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex]
    ) -> QtCore.Qt.ItemFlag:
        if not index.isValid():
            return QtCore.Qt.ItemFlag.ItemIsEnabled
        flags = super().flags(index)
        if index.column() in [0, 2]:
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
            else:
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

    def add_word(self, word, word_id):
        self.requestLookup.emit(word)
        self.add_pronunciation(word, word_id)

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
                    for c in candidates:
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

    def data(self, index, role):
        if not index.isValid() or index.row() > len(self._data) - 1:
            return
        data = self._data[index.row()][index.column()]
        if role == QtCore.Qt.ItemDataRole.DisplayRole or role == QtCore.Qt.ItemDataRole.EditRole:
            return data

    def finish_refresh_word_counts(self):
        self.corpus_model.session.expire_all()
        self.update_result_count()
        self.update_data()
        self.wordCountsRefreshed.emit()

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

    def update_data(self):
        self.runFunction.emit("Querying dictionary", self.finish_update_data, [self.query_kwargs])


class SpeakerModel(TableModel):
    clustered = QtCore.Signal()
    mdsFinished = QtCore.Signal()
    speakersChanged = QtCore.Signal()
    mdsAboutToChange = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(
            ["Speaker", "Utterances", "Dictionary", "Ivector distance", "View"], parent=parent
        )
        self.settings = AnchorSettings()
        self.speaker_count = None
        self.text_filter = None
        self.sort_index = 1
        self.sort_order = QtCore.Qt.SortOrder.DescendingOrder
        self.all_speakers = []
        self.corpus_model: Optional[CorpusModel] = None
        self.current_speaker = None
        self.num_clusters = None
        self.mds = None
        self.cluster_labels = None
        self.ivectors = None
        self.speaker_distances = None
        self.utterance_ids = None
        self.cluster_kwargs = {}
        self.manifold_kwargs = {}

    def indices_updated(self, utterance_ids, speaker_id):
        if speaker_id != self.current_speaker:
            return
        indices = np.where(np.isin(self.utterance_ids, utterance_ids))
        self.cluster_labels = np.delete(self.cluster_labels, indices, axis=0)
        self.utterance_ids = np.delete(self.utterance_ids, indices, axis=0)
        self.mds = np.delete(self.mds, indices, axis=0)
        self.ivectors = np.delete(self.ivectors, indices, axis=0)
        if self.speaker_distances is not None:
            self.speaker_distances = np.delete(self.speaker_distances, indices, axis=0)
        self.speakersChanged.emit()

    def change_speaker(self, utterance_ids, old_speaker_id, new_speaker_id):
        self.corpus_model.addCommand.emit(
            undo.ChangeSpeakerCommand(utterance_ids, old_speaker_id, new_speaker_id, self)
        )

    def set_speaker_filter(self, text_filter: TextFilterQuery):
        if text_filter != self.text_filter:
            self.current_offset = 0
        self.text_filter = text_filter
        self.update_data()
        self.update_result_count()

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
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._data[index.row()][index.column()]
        return super().data(index, role)

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
        speaker_id, c_labels = result
        if speaker_id != self.current_speaker:
            return
        self.cluster_labels = c_labels
        self.num_clusters = np.max(c_labels) + 1
        self.clustered.emit()

    def finish_mds(self, result, *args, **kwargs):
        speaker_id, mds = result
        if speaker_id != self.current_speaker:
            return
        self.mds = mds
        self.mdsFinished.emit()

    def update_data(self):
        self.runFunction.emit("Querying speakers", self.finish_update_data, [self.query_kwargs])

    def change_current_speaker(self, speaker_id):
        if self.current_speaker == speaker_id:
            return
        self.mds = None
        self.cluster_labels = None
        self.current_speaker = speaker_id
        self.cluster_speaker_utterances()
        self.load_speaker_ivectors()
        self.mds_speaker_utterances()

    def finish_load_ivectors(self, result, *args, **kwargs):
        speaker_id, utterance_ids, ivectors, speaker_distances = result
        if speaker_id != self.current_speaker:
            return
        self.utterance_ids = utterance_ids
        self.speaker_distances = speaker_distances
        self.ivectors = ivectors

    def load_speaker_ivectors(self):
        self.ivectors = None
        self.runFunction.emit(
            "Loading speaker ivectors",
            self.finish_load_ivectors,
            [
                {
                    "speaker_id": self.current_speaker,
                    "working_directory": os.path.join(
                        self.corpus_model.corpus.output_directory, "speaker_diarization"
                    ),
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
        if self.corpus_model.corpus is None:
            return
        kwargs = {
            "speaker_id": self.current_speaker,
            "working_directory": os.path.join(
                self.corpus_model.corpus.output_directory, "speaker_diarization"
            ),
        }
        kwargs.update(self.cluster_kwargs)
        self.cluster_labels = None
        self.num_clusters = None
        self.runFunction.emit("Clustering speaker utterances", self.finish_clustering, [kwargs])

    def mds_speaker_utterances(self):
        if self.corpus_model.corpus is None:
            return
        kwargs = {
            "speaker_id": self.current_speaker,
            "working_directory": os.path.join(
                self.corpus_model.corpus.output_directory, "speaker_diarization"
            ),
        }
        kwargs.update(self.manifold_kwargs)
        self.mds = None
        self.mdsAboutToChange.emit()
        self.runFunction.emit("Generating speaker MDS", self.finish_mds, [kwargs])


class MergeSpeakerModel(TableModel):
    mergeAllFinished = QtCore.Signal(object)

    def __init__(self, parent=None):
        super().__init__(["Speaker", "Suggested speaker", "Distance", "Merge?"], parent=parent)
        self.settings = AnchorSettings()
        self.speaker_count = None
        self._speaker_indices = []
        self._suggested_indices = []
        self.corpus_model: Optional[CorpusModel] = None
        self.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))
        self.speaker_filter = None
        self.threshold = None
        self.metric = "cosine"

    def data(self, index, role=None):
        if index.column() > 2:
            return None
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if index.column() == 2:
                return float(self._data[index.row()][index.column()])
            return self._data[index.row()][index.column()]
        return super().data(index, role)

    def speakers_at(self, row: int):
        return self._speaker_indices[row], self._suggested_indices[row]

    def set_threshold(self, threshold: float):
        self.threshold = threshold

    def set_metric(self, metric: str):
        self.metric = metric

    def set_speaker_filter(self, speaker_id: typing.Union[int, str, None]):
        self.speaker_filter = speaker_id

    def merge_all(self):
        if not self.corpus_model.corpus.has_any_ivectors():
            return
        self.runFunction.emit("Merging speakers", self.mergeAllFinished.emit, [self.query_kwargs])

    def merge_speakers(self, row: int):
        speaker_id, suggested_id = self.speakers_at(row)
        speaker_name = self._data[row][0]
        suggested_name = self._data[row][1]
        self.corpus_model.merge_speakers([suggested_id, speaker_id])
        self.layoutAboutToBeChanged.emit()
        self._data.pop(row)
        self._speaker_indices.pop(row)
        self._speaker_indices = [
            x if x != speaker_id else suggested_id for x in self._speaker_indices
        ]
        self._suggested_indices.pop(row)
        self._suggested_indices = [
            x if x != speaker_id else suggested_id for x in self._suggested_indices
        ]
        for d in self._data:
            if d[0] == speaker_name:
                d[0] = suggested_name
            if d[1] == speaker_name:
                d[1] = suggested_name

        self.layoutChanged.emit()

    def set_corpus_model(self, corpus_model: CorpusModel):
        self.corpus_model = corpus_model
        self.corpus_model.corpusLoading.connect(self.update_data)

    def finish_update_data(self, result, *args, **kwargs):
        self.layoutAboutToBeChanged.emit()
        if result is None:
            self._data, self._speaker_indices, self._suggested_indices = [], [], []
        else:
            self._data, self._speaker_indices, self._suggested_indices = result
        self.layoutChanged.emit()
        self.newResults.emit()

    @property
    def query_kwargs(self) -> typing.Dict[str, typing.Any]:
        kwargs = {
            "limit": self.limit,
            "current_offset": self.current_offset,
            "speaker_id": self.speaker_filter,
            "threshold": self.threshold,
            "metric": self.metric,
            "working_directory": os.path.join(
                self.corpus_model.corpus.output_directory, "speaker_diarization"
            ),
        }
        return kwargs

    def update_data(self):
        if not self.corpus_model.corpus.has_any_ivectors():
            return
        self.runFunction.emit("Comparing speakers", self.finish_update_data, [self.query_kwargs])


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
            "PER",
            "Overlap score",
            "Transcription",
            "WER",
            "Ivector distance",
        ]
        super(CorpusModel, self).__init__(header, parent=parent)
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
        ]
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
        self.language_model: Optional[LanguageModel] = None
        self.ivector_extractor: Optional[IvectorExtractorModel] = None
        self.g2p_model: Optional[G2PModel] = None
        self.segmented = True
        self.engine: typing.Optional[sqlalchemy.engine.Engine] = None
        self.reversed_indices = {}
        self._indices = []
        self._file_indices = []
        self._speaker_indices = []
        self._data = []
        self.unsaved_files = set()
        self.files = []
        self.speakers = []
        self.utterances = None
        self.utterance_count = 0
        self.speaker_count = 0
        self.file_count = 0
        self.editable = True
        self.data_types = {
            "WER": "percent",
            "PER": "percent",
        }

    def set_dictionary_model(self, dictionary_model: DictionaryTableModel):
        self.dictionary_model = dictionary_model

    @property
    def has_dictionary(self):
        if isinstance(self.corpus, AcousticCorpusWithPronunciations):
            return True
        return False

    def update_utterance_table_row(self, utterance_id: int):
        if utterance_id not in self.reversed_indices:
            return
        utterance = self.session.query(Utterance).get(utterance_id)
        index = self.reversed_indices[utterance_id]
        self.layoutAboutToBeChanged.emit()
        self._data[index][self.text_column] = utterance.text
        self._data[index][self.begin_column] = utterance.begin
        self._data[index][self.end_column] = utterance.end
        self._data[index][self.duration_column] = utterance.duration
        self.layoutChanged.emit()

    def add_table_utterances(self, utterances: typing.List[Utterance]):
        self.layoutAboutToBeChanged.emit()
        rows = []
        for utterance in utterances:
            row_data = [
                utterance.oovs,
                utterance.file_name,
                utterance.speaker_name,
                utterance.begin,
                utterance.end,
                utterance.duration,
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
            index = self.reversed_indices.pop(utterance.id)
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
        row_data = [
            first.oovs,
            first.file_name,
            first.speaker_name,
            first.begin,
            first.end,
            first.duration,
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
                utterance.file_name,
                utterance.speaker_name,
                utterance.begin,
                utterance.end,
                utterance.duration,
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
            merged_utterance.duration,
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

    def set_acoustic_model(self, acoustic_model: AcousticModel):
        self.acoustic_model = acoustic_model
        self.acousticModelChanged.emit()

    def set_ivector_extractor(self, ivector_extractor: IvectorExtractorModel):
        self.ivector_extractor = ivector_extractor
        self.ivectorExtractorChanged.emit()

    def set_language_model(self, language_model: LanguageModel):
        self.language_model = language_model
        self.languageModelChanged.emit()

    def create_utterance(self, file: File, speaker: Optional[Speaker], begin: float, end: float):
        if not self.editable:
            return
        channel = 0
        if file.num_channels > 1:
            ind = file.speaker_ordering.index(speaker)
            if ind >= len(file.speaker_ordering) / 2:
                channel = 1
        if speaker is None:
            speaker = self.corpus.add_speaker("speech", session=self.session)
        begin = round(begin, 4)
        end = round(end, 4)
        text = ""
        next_pk = self.corpus.get_next_primary_key(Utterance)
        new_utt = Utterance(
            id=next_pk,
            speaker=speaker,
            file_id=file.id,
            begin=begin,
            end=end,
            channel=channel,
            text=text,
        )
        self.addCommand.emit(undo.CreateUtteranceCommand(new_utt, self))
        self.unsaved_files.add(file.id)

    def set_file_modified(self, file_id: typing.Union[int, typing.List[int]]):
        if isinstance(file_id, int):
            file_id = [file_id]
        self.session.query(File).filter(File.id.in_(file_id)).update({File.modified: True})
        self.session.commit()

    def update_utterance_text(self, utterance: Utterance, text):
        if text != utterance.text:
            self.addCommand.emit(undo.UpdateUtteranceTextCommand(utterance, text, self))
            self.set_file_modified(utterance.file_id)

    def update_utterance_times(
        self, utterance: Utterance, begin: Optional[float] = None, end: Optional[float] = None
    ):
        if not self.editable:
            return
        self.addCommand.emit(undo.UpdateUtteranceTimesCommand(utterance, begin, end, self))
        self.set_file_modified(utterance.file_id)

    def update_utterance_speaker(self, utterance: Utterance, speaker: Speaker):
        if not self.editable:
            return
        self.addCommand.emit(undo.UpdateUtteranceSpeakerCommand(utterance, speaker, self))
        self.set_file_modified(utterance.file_id)

    def delete_utterances(self, utterances: list[Utterance]):
        if not self.editable:
            return
        for u in utterances:
            self.set_file_modified(u.file_id)
        self.addCommand.emit(undo.DeleteUtteranceCommand(utterances, self))

    def split_vad_utterance(self, original_utterance_id, replacement_utterance_data):
        utt = self.session.get(Utterance, original_utterance_id)
        self.requestFileView.emit(utt.file_name)
        replacement_utterances = []
        next_pk = self.corpus.get_next_primary_key(Utterance)
        for sd in replacement_utterance_data.values():
            replacement_utterances.append(Utterance(id=next_pk, **sd))
            next_pk += 1
        splitting_utterances = [[utt, *replacement_utterances]]
        self.addCommand.emit(undo.SplitUtteranceCommand(splitting_utterances, self))
        self.set_file_modified([utt[0].file_id for utt in splitting_utterances])

    def split_utterances(self, utterances: list[Utterance]):
        if not self.editable:
            return
        splitting_utterances = []
        for utt in utterances:
            duration = utt.duration
            beg = utt.begin
            end = utt.end
            first_text = ""
            second_text = ""
            if utt.text:
                t = utt.text.split()
                mid_ind = int(len(t) / 2)
                first_text = t[:mid_ind]
                second_text = t[mid_ind:]
            split_time = beg + (duration / 2)
            oovs = set()
            for w in first_text:
                if not self.dictionary_model.check_word(w, utt.speaker_id):
                    oovs.add(w)
            next_pk = self.corpus.get_next_primary_key(Utterance)
            first_utt = Utterance(
                id=next_pk,
                speaker=utt.speaker,
                file=utt.file,
                begin=beg,
                end=split_time,
                channel=utt.channel,
                text=" ".join(first_text),
                oovs=" ".join(oovs),
            )
            next_pk += 1
            oovs = set()
            for w in second_text:
                if not self.dictionary_model.check_word(w, utt.speaker_id):
                    oovs.add(w)
            second_utt = Utterance(
                id=next_pk,
                speaker=utt.speaker,
                file=utt.file,
                begin=split_time,
                end=end,
                channel=utt.channel,
                text=" ".join(second_text),
                oovs=" ".join(oovs),
            )
            splitting_utterances.append([utt, first_utt, second_utt])
        self.addCommand.emit(undo.SplitUtteranceCommand(splitting_utterances, self))
        self.set_file_modified([utt[0].file_id for utt in splitting_utterances])

    def merge_speakers(self, speakers: list[int]):
        self.addCommand.emit(undo.MergeSpeakersCommand(speakers, self))

    def merge_utterances(self, utterances: list[Utterance]):
        if not self.editable:
            return
        min_begin = 1000000000
        max_end = 0
        text = ""
        speaker = None
        file = None
        channel = None
        for old_utt in sorted(utterances, key=lambda x: x.begin):
            if speaker is None:
                speaker = old_utt.speaker
            if file is None:
                file = old_utt.file
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
        text = text[:-1]
        next_pk = self.corpus.get_next_primary_key(Utterance)
        oovs = set()
        for w in text.split():
            if not self.dictionary_model.check_word(w, speaker.id):
                oovs.add(w)
        new_utt = Utterance(
            id=next_pk,
            speaker=speaker,
            file=file,
            begin=min_begin,
            end=max_end,
            channel=channel,
            text=text,
            oovs=" ".join(oovs),
        )
        self.set_file_modified(file.id)
        self.addCommand.emit(undo.MergeUtteranceCommand(utterances, new_utt, self))

    def replace_all(self, search_query: TextFilterQuery, replacement: str):
        self.addCommand.emit(undo.ReplaceAllCommand(search_query, replacement, self))

    def utteranceAt(self, index) -> Optional[Utterance]:
        if not isinstance(index, int):
            index = index.row()

        if index > len(self._indices) - 1:
            return None
        if len(self._indices) == 0:
            return None
        utterance = (
            self.session.query(Utterance)
            .options(
                joinedload(Utterance.file).joinedload(File.sound_file),
                joinedload(Utterance.file).subqueryload(File.speakers),
            )
            .get(self._indices[index])
        )
        return utterance

    def fileAt(self, index) -> int:
        if not isinstance(index, int):
            index = index.row()
        return self._file_indices[index]

    def indexForUtterance(self, utterance_id: int, column: int = 1):
        return self.createIndex(self.reversed_indices[utterance_id], column)

    def rollback_changes(self):
        self.unsaved_files = set()
        self.session.rollback()
        # self.query_session.expire_all()
        self.databaseSynced.emit(False)
        self.update_data()

    def commit_changes(self):
        self.session.bulk_update_mappings(
            File, [{"id": x, "modified": True} for x in self.unsaved_files]
        )

        self.unsaved_files = set()
        self.session.commit()
        self.databaseSynced.emit(True)

    def finish_export_files(self):
        self.filesSaved.emit()

    def export_changes(self):
        self.runFunction.emit("Exporting files", self.finish_export_files, [])

    def setCorpus(self, corpus: Optional[AcousticCorpus]):
        self.corpus = corpus
        if corpus is not None:
            self.session = scoped_session(self.corpus.session)
            self.corpusLoading.emit()
            self.refresh_files()
            self.refresh_speakers()
            self.refresh_utterances()

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

    def finish_update_speakers(self, speakers):
        self.speakers = speakers
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

    def data(self, index, role):
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
