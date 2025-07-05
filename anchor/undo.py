from __future__ import annotations

import collections
import typing
import unicodedata

import pynini.lib
import sqlalchemy
from montreal_forced_aligner.data import WordType, WorkflowType
from montreal_forced_aligner.db import (
    CorpusWorkflow,
    File,
    Phone,
    PhoneInterval,
    Pronunciation,
    Speaker,
    Utterance,
    Word,
    WordInterval,
    bulk_update,
)
from PySide6 import QtCore, QtGui
from sqlalchemy.orm import make_transient

if typing.TYPE_CHECKING:
    from anchor.models import (
        CorpusModel,
        DiarizationModel,
        DictionaryTableModel,
        FileUtterancesModel,
        SpeakerModel,
        TextFilterQuery,
    )


class CorpusCommand(QtGui.QUndoCommand):
    def __init__(self, corpus_model: CorpusModel):
        super().__init__()
        self.corpus_model = corpus_model
        self.resets_tier = False

    def _redo(self, session) -> None:
        pass

    def _undo(self, session) -> None:
        pass

    def update_data(self):
        if self.resets_tier:
            self.corpus_model.refreshTiers.emit()

    def redo(self) -> None:
        with self.corpus_model.edit_lock:
            try:
                self._redo(self.corpus_model.session)
                self.corpus_model.session.commit()
            except Exception:
                self.corpus_model.session.rollback()
                raise
            # while True:
            #    try:
            #        with self.corpus_model.session.begin_nested():
            #            self._redo()
            #        break
            #    except psycopg2.errors.DeadlockDetected:
            #        pass

        self.update_data()

    def undo(self) -> None:
        with self.corpus_model.edit_lock:
            try:
                self._undo(self.corpus_model.session)
                self.corpus_model.session.commit()
            except Exception:
                self.corpus_model.session.rollback()
                raise
            # while True:
            #    try:
            #        with self.corpus_model.session.begin_nested():
            #            self._undo()
            #        break
            #    except psycopg2.errors.DeadlockDetected:
            #        pass
        self.update_data()


class FileCommand(CorpusCommand):
    def __init__(self, file_model: FileUtterancesModel):
        super().__init__(file_model.corpus_model)
        self.file_model = file_model


class DictionaryCommand(QtGui.QUndoCommand):
    def __init__(self, dictionary_model: DictionaryTableModel):
        super().__init__()
        self.dictionary_model = dictionary_model

    def _redo(self, session) -> None:
        pass

    def _undo(self, session) -> None:
        pass

    def redo(self) -> None:
        with self.dictionary_model.corpus_model.edit_lock:
            with self.dictionary_model.corpus_model.session() as session:
                self._redo(session)
                session.commit()

        self.dictionary_model.update_data()

    def undo(self) -> None:
        with self.dictionary_model.corpus_model.edit_lock:
            with self.dictionary_model.corpus_model.session() as session:
                self._undo(session)
                session.commit()
        self.dictionary_model.update_data()


class SpeakerCommand(QtGui.QUndoCommand):
    def __init__(self, speaker_model: SpeakerModel):
        super().__init__()
        self.speaker_model = speaker_model
        self.auto_refresh = True
        self.resets_tier = False

    def _redo(self, session) -> None:
        pass

    def _undo(self, session) -> None:
        pass

    def update_data(self):
        if self.auto_refresh:
            self.speaker_model.update_data()
        if self.resets_tier:
            self.speaker_model.corpus_model.refreshTiers.emit()

    def redo(self) -> None:
        with self.speaker_model.corpus_model.edit_lock:
            with self.speaker_model.corpus_model.session() as session:
                self._redo(session)
                session.commit()
        self.update_data()

    def undo(self) -> None:
        with self.speaker_model.corpus_model.edit_lock:
            with self.speaker_model.corpus_model.session() as session:
                self._undo(session)
                session.commit()
        self.update_data()


class DeleteUtteranceCommand(FileCommand):
    def __init__(self, deleted_utterances: list[Utterance], file_model: FileUtterancesModel):
        super().__init__(file_model)
        self.deleted_utterances = deleted_utterances
        self.resets_tier = True
        self.channels = [
            x.channel if x.channel is not None else 0 for x in self.deleted_utterances
        ]
        self.setText(
            QtCore.QCoreApplication.translate("DeleteUtteranceCommand", "Delete utterances")
        )

    def _redo(self, session) -> None:
        for utt in self.deleted_utterances:
            session.delete(utt)

    def _undo(self, session) -> None:
        for i, utt in enumerate(self.deleted_utterances):
            make_transient(utt)
            for x in utt.phone_intervals:
                make_transient(x)
            for x in utt.word_intervals:
                make_transient(x)
            if utt.channel is None:
                utt.channel = self.channels[i]
            session.add(utt)

    def redo(self) -> None:
        super().redo()
        self.corpus_model.delete_table_utterances(self.deleted_utterances)
        self.file_model.delete_table_utterances(self.deleted_utterances)
        self.corpus_model.changeCommandFired.emit()

    def undo(self) -> None:
        super().undo()
        self.corpus_model.add_table_utterances(self.deleted_utterances)
        self.file_model.add_table_utterances(self.deleted_utterances)
        self.corpus_model.changeCommandFired.emit()


class SplitUtteranceCommand(FileCommand):
    def __init__(
        self,
        merged_utterance: Utterance,
        split_utterances: list[Utterance],
        file_model: FileUtterancesModel,
        update_table: bool = True,
    ):
        super().__init__(file_model)
        self.merged_utterance = merged_utterance
        self.split_utterances = split_utterances
        self.resets_tier = True
        self.update_table = update_table
        self.channels = [x.channel if x.channel is not None else 0 for x in self.split_utterances]
        self.setText(
            QtCore.QCoreApplication.translate("SplitUtteranceCommand", "Split utterances")
        )

    def _redo(self, session) -> None:
        session.delete(self.merged_utterance)
        for u in self.split_utterances:
            if u.id is not None:
                make_transient(u)
            for x in u.phone_intervals:
                make_transient(x)
            for x in u.word_intervals:
                make_transient(x)
            if u.channel is None:
                u.channel = self.merged_utterance.channel
            session.add(u)

    def _undo(self, session) -> None:
        if self.merged_utterance.channel is None:
            self.merged_utterance.channel = self.split_utterances[0].channel
        make_transient(self.merged_utterance)
        for x in self.merged_utterance.phone_intervals:
            make_transient(x)
        for x in self.merged_utterance.word_intervals:
            make_transient(x)
        for x in self.merged_utterance.reference_phone_intervals:
            make_transient(x)
        for x in self.merged_utterance.reference_word_intervals:
            make_transient(x)
        session.add(self.merged_utterance)
        for u in self.split_utterances:
            session.delete(u)

    def redo(self) -> None:
        super().redo()
        self.corpus_model.split_table_utterances(self.merged_utterance, self.split_utterances)
        self.file_model.split_table_utterances(self.merged_utterance, self.split_utterances)
        self.corpus_model.changeCommandFired.emit()

    def undo(self) -> None:
        super().undo()
        self.corpus_model.merge_table_utterances(self.merged_utterance, self.split_utterances)
        self.file_model.merge_table_utterances(self.merged_utterance, self.split_utterances)
        self.corpus_model.changeCommandFired.emit()


class MergeUtteranceCommand(FileCommand):
    def __init__(
        self,
        unmerged_utterances: list[Utterance],
        merged_utterance: Utterance,
        file_model: FileUtterancesModel,
    ):
        super().__init__(file_model)
        self.unmerged_utterances = unmerged_utterances
        self.merged_utterance = merged_utterance
        self.resets_tier = True
        self.channel = self.merged_utterance.channel
        if self.channel is None:
            self.channel = 0
        self.setText(
            QtCore.QCoreApplication.translate("MergeUtteranceCommand", "Merge utterances")
        )

    def _redo(self, session) -> None:
        for old_utt in self.unmerged_utterances:
            session.delete(old_utt)
        make_transient(self.merged_utterance)
        if self.merged_utterance.channel is None:
            self.merged_utterance.channel = self.channel
        session.add(self.merged_utterance)

    def _undo(self, session) -> None:
        for old_utt in self.unmerged_utterances:
            make_transient(old_utt)
            if old_utt.channel is None:
                old_utt.channel = self.channel
            for x in old_utt.phone_intervals:
                make_transient(x)
            for x in old_utt.word_intervals:
                make_transient(x)
            session.add(old_utt)
        session.delete(self.merged_utterance)

    def redo(self) -> None:
        super().redo()
        self.corpus_model.merge_table_utterances(self.merged_utterance, self.unmerged_utterances)
        self.file_model.merge_table_utterances(self.merged_utterance, self.unmerged_utterances)
        self.corpus_model.changeCommandFired.emit()

    def undo(self) -> None:
        super().undo()
        self.corpus_model.split_table_utterances(self.merged_utterance, self.unmerged_utterances)
        self.file_model.split_table_utterances(self.merged_utterance, self.unmerged_utterances)
        self.corpus_model.changeCommandFired.emit()


class MergeSpeakersCommand(CorpusCommand):
    def __init__(self, speakers: list[int], corpus_model: CorpusModel):
        super().__init__(corpus_model)
        self.merged_speaker = speakers.pop(0)
        self.speakers = speakers
        self.resets_tier = True
        self.utt_mapping = collections.defaultdict(list)
        self.file_mapping = collections.defaultdict(list)
        self.files = []
        self.setText(QtCore.QCoreApplication.translate("MergeSpeakersCommand", "Merge speakers"))

    def finish_recalculate(self, result=None, **kwargs):
        if result is not None:
            self.corpus_model.speaker_plda = result

    def update_data(self):
        super().update_data()
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

    def _redo(self, session) -> None:
        if not self.files:
            q = session.query(Utterance.id, Utterance.file_id, Utterance.speaker_id).filter(
                Utterance.speaker_id.in_(self.speakers)
            )
            for utt_id, file_id, speaker_id in q:
                self.utt_mapping[speaker_id].append(utt_id)
                self.file_mapping[speaker_id].append(file_id)
                self.files.append(file_id)
        session.query(Utterance).filter(Utterance.speaker_id.in_(self.speakers)).update(
            {Utterance.speaker_id: self.merged_speaker}
        )
        session.query(File).filter(File.id.in_(self.files)).update({File.modified: True})
        session.query(Speaker).filter(
            Speaker.id.in_(self.speakers + [self.merged_speaker])
        ).update({Speaker.modified: True})

    def _undo(self, session) -> None:
        for speaker, utts in self.utt_mapping.items():
            session.query(Utterance).filter(Utterance.id.in_(utts)).update(
                {Utterance.speaker_id: speaker}
            )
        session.query(File).filter(File.id.in_(self.files)).update({File.modified: True})
        session.query(Speaker).filter(
            Speaker.id.in_(self.speakers + [self.merged_speaker])
        ).update({Speaker.modified: True})


class CreateUtteranceCommand(FileCommand):
    def __init__(self, new_utterance: Utterance, file_model: FileUtterancesModel):
        super().__init__(file_model)
        self.new_utterance = new_utterance
        self.channel = self.new_utterance.channel
        if self.channel is None:
            self.channel = 0
        self.setText(
            QtCore.QCoreApplication.translate("CreateUtteranceCommand", "Create utterance")
        )

    def _redo(self, session) -> None:
        make_transient(self.new_utterance)
        if self.new_utterance.channel is None:
            self.new_utterance.channel = self.channel
        session.add(self.new_utterance)

    def _undo(self, session) -> None:
        session.delete(self.new_utterance)

    def update_data(self):
        super().update_data()

    def redo(self) -> None:
        super().redo()
        self.corpus_model.add_table_utterances([self.new_utterance])
        self.file_model.add_table_utterances([self.new_utterance])
        self.corpus_model.changeCommandFired.emit()

    def undo(self) -> None:
        super().undo()
        self.corpus_model.delete_table_utterances([self.new_utterance])
        self.file_model.delete_table_utterances([self.new_utterance])
        self.corpus_model.changeCommandFired.emit()


class UpdateUtteranceTimesCommand(FileCommand):
    def __init__(
        self, utterance: Utterance, begin: float, end: float, file_model: FileUtterancesModel
    ):
        super().__init__(file_model)
        self.utterance = utterance
        self.new_begin = begin
        self.old_begin = utterance.begin
        self.new_end = end
        self.old_end = utterance.end
        self.setText(
            QtCore.QCoreApplication.translate(
                "UpdateUtteranceTimesCommand", "Update utterance times"
            )
        )

    def _set_times(self, session, begin, end):
        self.utterance.begin = begin
        self.utterance.end = end
        self.utterance.xvector = None
        self.utterance.ivector = None
        self.utterance.features = None
        if self.utterance.phone_intervals:
            self.utterance.phone_intervals[0].begin = begin
            self.utterance.phone_intervals[-1].end = end
        if self.utterance.word_intervals:
            self.utterance.word_intervals[0].begin = begin
            self.utterance.word_intervals[-1].end = end
        if self.utterance.reference_phone_intervals:
            self.utterance.reference_phone_intervals[0].begin = begin
            self.utterance.reference_phone_intervals[-1].end = end
        if self.utterance.reference_word_intervals:
            self.utterance.reference_word_intervals[0].begin = begin
            self.utterance.reference_word_intervals[-1].end = end
        session.merge(self.utterance)

    def _redo(self, session) -> None:
        self._set_times(session, self.new_begin, self.new_end)

    def _undo(self, session) -> None:
        self._set_times(session, self.old_begin, self.old_end)

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()
        self.corpus_model.update_utterance_table_row(self.utterance)


class DeleteReferenceIntervalsCommand(FileCommand):
    def __init__(self, utterance: Utterance, file_model: FileUtterancesModel):
        super().__init__(file_model)
        self.utterance = utterance
        self.reference_intervals = None
        self.reference_word_intervals = None
        self.reference_workflow = None

    def _redo(self, session) -> None:
        if self.reference_intervals is None:
            self.reference_intervals = self.utterance.reference_phone_intervals
            self.reference_word_intervals = self.utterance.reference_word_intervals
        self.utterance.reference_phone_intervals = []
        self.utterance.reference_word_intervals = []
        self.utterance.manual_alignments = False
        session.merge(self.utterance)

    def _undo(self, session) -> None:
        reference_phone_intervals = []
        for pi in self.reference_intervals:
            make_transient(pi)
            reference_phone_intervals.append(pi)
        reference_word_intervals = []
        for wi in self.reference_word_intervals:
            make_transient(wi)
            reference_word_intervals.append(wi)
        self.utterance.manual_alignments = True
        self.utterance.reference_phone_intervals = sorted(
            reference_phone_intervals, key=lambda x: x.begin
        )
        self.utterance.reference_word_intervals = sorted(
            reference_word_intervals, key=lambda x: x.begin
        )
        session.merge(self.utterance)

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()
        self.file_model.phoneTierChanged.emit(self.utterance)


class UpdatePhoneBoundariesCommand(FileCommand):
    def __init__(
        self,
        utterance: Utterance,
        first_phone_interval: PhoneInterval,
        second_phone_interval: PhoneInterval,
        new_time: float,
        file_model: FileUtterancesModel,
    ):
        super().__init__(file_model)
        self.utterance = utterance
        self.old_manual_alignments = utterance.manual_alignments
        self.first_phone_interval = first_phone_interval
        self.second_phone_interval = second_phone_interval
        self.first_word_interval = None
        self.second_word_interval = None
        self.at_word_boundary = (
            self.first_phone_interval.word_interval_id
            != self.second_phone_interval.word_interval_id
        )
        if True or self.at_word_boundary:
            if isinstance(self.first_phone_interval, PhoneInterval):
                word_intervals = utterance.word_intervals
            else:
                word_intervals = utterance.reference_word_intervals
            for wi in word_intervals:
                if self.first_word_interval is not None and self.second_word_interval is not None:
                    break
                if wi.id == first_phone_interval.word_interval_id:
                    self.first_word_interval = wi
                elif wi.id == second_phone_interval.word_interval_id:
                    self.second_word_interval = wi
        self.speaker_id = utterance.speaker_id
        self.old_time = second_phone_interval.begin
        self.new_time = new_time
        self.setText(
            QtCore.QCoreApplication.translate(
                "UpdatePhoneBoundariesCommand", "Update phone boundaries"
            )
        )

    def _set_time(self, session, new_time, manual_alignments):
        if not self.old_manual_alignments:
            self.utterance.manual_alignments = manual_alignments
            session.merge(self.utterance)
        self.first_phone_interval.end = new_time
        self.second_phone_interval.begin = new_time
        session.merge(self.utterance)
        session.merge(self.first_phone_interval)
        session.merge(self.second_phone_interval)
        if self.at_word_boundary:
            if self.first_word_interval is not None:
                self.first_word_interval.end = new_time
                session.merge(self.first_word_interval)
            if self.second_word_interval is not None:
                self.second_word_interval.begin = new_time
                session.merge(self.second_word_interval)

    def _redo(self, session) -> None:
        self._set_time(session, self.new_time, True)

    def _undo(self, session) -> None:
        self._set_time(session, self.old_time, self.old_manual_alignments)

    def id(self) -> int:
        return 2

    def mergeWith(self, other: UpdatePhoneBoundariesCommand) -> bool:
        if (
            other.id() != self.id()
            or other.first_phone_interval.id != self.first_phone_interval.id
            or other.second_phone_interval.id != self.second_phone_interval.id
        ):
            return False
        self.new_time = other.new_time
        return True

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()


class DeletePhoneIntervalCommand(FileCommand):
    def __init__(
        self,
        utterance: Utterance,
        phone_interval: PhoneInterval,
        previous_phone_interval: typing.Optional[PhoneInterval],
        following_phone_interval: typing.Optional[PhoneInterval],
        time_point: typing.Optional[float],
        file_model: FileUtterancesModel,
    ):
        super().__init__(file_model)
        self.word_interval_lookup = "word_intervals"
        self.phone_interval_lookup = "phone_intervals"
        self.using_reference = not isinstance(phone_interval, PhoneInterval)
        if self.using_reference:
            self.word_interval_lookup = "reference_word_intervals"
            self.phone_interval_lookup = "reference_phone_intervals"
        self.utterance = utterance
        self.old_manual_alignments = utterance.manual_alignments
        self.phone_interval = phone_interval
        self.previous_phone_interval = previous_phone_interval
        self.has_previous = previous_phone_interval is not None
        self.has_following = following_phone_interval is not None
        self.following_phone_interval = following_phone_interval
        self.new_time = time_point
        self.first_word_interval = None
        self.second_word_interval = None
        previous_word_interval_id = (
            self.previous_phone_interval.word_interval_id
            if self.previous_phone_interval is not None
            else None
        )
        word_interval_id = self.phone_interval.word_interval_id
        following_word_interval_id = (
            self.following_phone_interval.word_interval_id
            if self.following_phone_interval is not None
            else None
        )
        self.word_interval = None
        for wi in getattr(self.utterance, self.word_interval_lookup):
            if wi.id == self.phone_interval.word_interval_id:
                self.word_interval = wi
                break
        self.single_phone_word = (
            word_interval_id != previous_word_interval_id
            and word_interval_id != following_word_interval_id
        )

        self.at_word_boundary = previous_word_interval_id != following_word_interval_id
        if self.at_word_boundary:
            for wi in getattr(self.utterance, self.word_interval_lookup):
                if self.first_word_interval is not None and self.second_word_interval is not None:
                    break
                if wi.id == previous_word_interval_id:
                    self.first_word_interval = wi
                if wi.id == following_word_interval_id:
                    self.second_word_interval = wi
        elif not self.has_previous:
            for wi in getattr(self.utterance, self.word_interval_lookup):
                if wi.id == following_word_interval_id:
                    self.second_word_interval = wi
                    break
        elif not self.has_following:
            for wi in getattr(self.utterance, self.word_interval_lookup):
                if wi.id == previous_word_interval_id:
                    self.first_word_interval = wi
                    break
        self.first_word_interval_end = None
        if self.first_word_interval is not None:
            self.first_word_interval_end = self.first_word_interval.end
        self.second_word_interval_begin = None
        if self.second_word_interval is not None:
            self.second_word_interval_begin = self.second_word_interval.begin
        self.speaker_id = utterance.speaker_id
        self.setText(
            QtCore.QCoreApplication.translate(
                "DeletePhoneIntervalCommand", "Delete phone interval"
            )
        )

    def _redo(self, session) -> None:
        if self.has_previous and self.has_following:
            new_time = (
                self.new_time
                if self.new_time is not None
                else (self.phone_interval.begin + self.phone_interval.end) / 2
            )
            self.previous_phone_interval.end = new_time
            self.following_phone_interval.begin = new_time
            if self.at_word_boundary:
                self.first_word_interval.end = new_time
                self.second_word_interval.begin = new_time
                session.merge(self.first_word_interval)
                session.merge(self.second_word_interval)
        elif self.has_following:
            self.following_phone_interval.begin = self.phone_interval.begin
            self.second_word_interval.begin = self.phone_interval.begin
            session.merge(self.second_word_interval)
        elif self.has_previous:
            self.previous_phone_interval.end = self.phone_interval.end
            self.first_word_interval.end = self.phone_interval.end
            session.merge(self.first_word_interval)
        if self.has_previous:
            session.merge(self.previous_phone_interval)
        if self.has_following:
            session.merge(self.following_phone_interval)

        phone_intervals = []
        for pi in getattr(self.utterance, self.phone_interval_lookup):
            if pi.id == self.phone_interval.id:
                continue
            session.merge(pi)
            phone_intervals.append(pi)
        setattr(self.utterance, self.phone_interval_lookup, phone_intervals)
        if self.single_phone_word:
            word_intervals = []
            for wi in getattr(self.utterance, self.word_interval_lookup):
                if wi.id == self.word_interval.id:
                    continue
                session.merge(wi)
                word_intervals.append(wi)
            setattr(self.utterance, self.word_interval_lookup, word_intervals)
        if not self.old_manual_alignments:
            self.utterance.manual_alignments = True
        session.merge(self.utterance)

    def _undo(self, session) -> None:
        if self.single_phone_word:
            word_intervals = []
            for wi in getattr(self.utterance, self.word_interval_lookup):
                session.merge(wi)
                word_intervals.append(wi)
            make_transient(self.word_interval)
            word_intervals.append(self.word_interval)
            setattr(
                self.utterance,
                self.word_interval_lookup,
                sorted(word_intervals, key=lambda x: x.begin),
            )
        phone_intervals = []
        for pi in getattr(self.utterance, self.phone_interval_lookup):
            session.merge(pi)
            phone_intervals.append(pi)
        make_transient(self.phone_interval)
        phone_intervals.append(self.phone_interval)
        setattr(
            self.utterance,
            self.phone_interval_lookup,
            sorted(phone_intervals, key=lambda x: x.begin),
        )
        session.merge(self.utterance)

        if not self.old_manual_alignments:
            self.utterance.manual_alignments = self.old_manual_alignments
        if self.has_previous:
            self.previous_phone_interval.end = self.phone_interval.begin
            session.merge(self.previous_phone_interval)
        if self.has_following:
            self.following_phone_interval.begin = self.phone_interval.end
            session.merge(self.following_phone_interval)
        if self.second_word_interval_begin is not None:
            self.second_word_interval.begin = self.second_word_interval_begin
            session.merge(self.second_word_interval)
        if self.first_word_interval_end is not None:
            self.first_word_interval.end = self.first_word_interval_end
            session.merge(self.first_word_interval)

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()
        self.file_model.phoneTierChanged.emit(self.utterance)


class InsertPhoneIntervalCommand(FileCommand):
    def __init__(
        self,
        utterance: Utterance,
        phone_interval: PhoneInterval,
        previous_phone_interval: typing.Optional[PhoneInterval],
        following_phone_interval: typing.Optional[PhoneInterval],
        file_model: FileUtterancesModel,
        word_interval: WordInterval = None,
    ):
        super().__init__(file_model)
        self.word_interval_lookup = "word_intervals"
        self.phone_interval_lookup = "phone_intervals"
        self.using_reference = not isinstance(phone_interval, PhoneInterval)
        if self.using_reference:
            self.word_interval_lookup = "reference_word_intervals"
            self.phone_interval_lookup = "reference_phone_intervals"
        self.utterance = utterance
        self.old_manual_alignments = utterance.manual_alignments
        self.phone_interval = phone_interval
        self.previous_phone_interval = previous_phone_interval
        self.has_previous = previous_phone_interval is not None
        self.has_following = following_phone_interval is not None
        self.following_phone_interval = following_phone_interval
        self.word_interval = word_interval
        self.previous_word_interval_id = (
            previous_phone_interval.word_interval_id if self.has_previous else None
        )
        self.following_word_interval_id = (
            following_phone_interval.word_interval_id if self.has_following else None
        )
        self.initial_word_boundary = (
            self.has_previous
            and self.previous_word_interval_id != self.phone_interval.word_interval_id
        )
        self.final_word_boundary = (
            self.has_following
            and self.following_word_interval_id != self.phone_interval.word_interval_id
        )

        self.old_time_boundary = (
            self.previous_phone_interval.end
            if self.has_previous
            else self.following_phone_interval.begin
        )
        self.previous_word_interval_end = None
        self.following_word_interval_begin = None
        for wi in getattr(self.utterance, self.word_interval_lookup):
            if (
                self.previous_word_interval_id is not None
                and wi.id == self.previous_word_interval_id
            ):
                self.previous_word_interval_end = wi.end
            elif (
                self.following_word_interval_id is not None
                and wi.id == self.following_word_interval_id
            ):
                self.following_word_interval_begin = wi.begin
        self.speaker_id = utterance.speaker_id
        self.setText(
            QtCore.QCoreApplication.translate(
                "InsertPhoneIntervalCommand", "Insert phone interval"
            )
        )

    def _redo(self, session) -> None:
        word_intervals = []
        if self.word_interval is not None:
            for wi in getattr(self.utterance, self.word_interval_lookup):
                session.merge(wi)
                if wi.id == self.previous_word_interval_id:
                    wi.end = self.phone_interval.begin
                if wi.id == self.following_word_interval_id:
                    wi.begin = self.phone_interval.end
                word_intervals.append(wi)
            make_transient(self.word_interval)
            word_intervals.append(self.word_interval)
        else:
            for wi in getattr(self.utterance, self.word_interval_lookup):
                session.merge(wi)
                if self.initial_word_boundary:
                    if wi.id == self.previous_word_interval_id:
                        wi.end = self.phone_interval.begin
                    elif wi.id == self.phone_interval.word_interval_id:
                        wi.begin = self.phone_interval.begin
                if self.final_word_boundary:
                    if wi.id == self.following_word_interval_id:
                        wi.begin = self.phone_interval.end
                    elif wi.id == self.phone_interval.word_interval_id:
                        wi.end = self.phone_interval.end
                word_intervals.append(wi)
        setattr(
            self.utterance,
            self.word_interval_lookup,
            sorted(word_intervals, key=lambda x: x.begin),
        )
        phone_intervals = []
        for pi in getattr(self.utterance, self.phone_interval_lookup):
            session.merge(pi)
            if self.has_previous and pi.id == self.previous_phone_interval.id:
                pi.end = self.phone_interval.begin
            if self.has_following and pi.id == self.following_phone_interval.id:
                pi.begin = self.phone_interval.end
            phone_intervals.append(pi)
        make_transient(self.phone_interval)
        self.phone_interval.utterance_id = self.utterance.id
        phone_intervals.append(self.phone_interval)

        setattr(
            self.utterance,
            self.phone_interval_lookup,
            sorted(phone_intervals, key=lambda x: x.begin),
        )
        if not self.old_manual_alignments:
            self.utterance.manual_alignments = True
        session.merge(self.utterance)

    def _undo(self, session) -> None:
        phone_intervals = []
        for pi in getattr(self.utterance, self.phone_interval_lookup):
            if pi.id == self.phone_interval.id:
                continue
            session.merge(pi)
            if self.has_previous and pi.id == self.previous_phone_interval.id:
                pi.end = self.old_time_boundary
            if self.has_following and pi.id == self.following_phone_interval.id:
                pi.begin = self.old_time_boundary
            phone_intervals.append(pi)
        setattr(self.utterance, self.phone_interval_lookup, phone_intervals)
        word_intervals = []
        if self.word_interval is not None:
            for wi in getattr(self.utterance, self.word_interval_lookup):
                if wi.id == self.word_interval.id:
                    continue
                session.merge(wi)
                word_intervals.append(wi)
        else:
            for wi in getattr(self.utterance, self.word_interval_lookup):
                session.merge(wi)
                if self.initial_word_boundary:
                    if wi.id == self.previous_word_interval_id:
                        wi.end = self.previous_word_interval_end
                    elif wi.id == self.phone_interval.word_interval_id:
                        wi.begin = self.previous_word_interval_end
                if self.final_word_boundary:
                    if wi.id == self.following_word_interval_id:
                        wi.begin = self.following_word_interval_begin
                    elif wi.id == self.phone_interval.word_interval_id:
                        wi.end = self.following_word_interval_begin
                word_intervals.append(wi)
        setattr(self.utterance, self.word_interval_lookup, word_intervals)
        session.merge(self.utterance)
        if not self.old_manual_alignments:
            self.utterance.manual_alignments = self.old_manual_alignments

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()
        self.file_model.phoneTierChanged.emit(self.utterance)


class UpdateWordIntervalPronunciationCommand(FileCommand):
    def __init__(
        self,
        utterance: Utterance,
        word_interval: WordInterval,
        pronunciation: Pronunciation,
        file_model: FileUtterancesModel,
    ):
        super().__init__(file_model)
        self.utterance = utterance
        self.word_interval = word_interval
        self.old_pronunciation_id = self.word_interval.pronunciation_id
        self.new_pronunciation = pronunciation
        self.old_phone_intervals = None
        self.new_phone_intervals = None

        self.setText(
            QtCore.QCoreApplication.translate(
                "UpdateWordIntervalPronunciationCommand", "Update pronunciation for word interval"
            )
        )

    def _redo(self, session) -> None:
        phone_intervals = []
        word_intervals = []
        for pi in self.utterance.phone_intervals:
            if pi.word_interval_id != self.word_interval.id:
                session.merge(pi)
                phone_intervals.append(pi)
            elif self.old_phone_intervals is None:
                word_intervals.append(pi)
        if self.old_phone_intervals is None:
            self.old_phone_intervals = word_intervals
        if self.new_phone_intervals is None:
            self.new_phone_intervals = []
            new_phones = self.new_pronunciation.pronunciation.split()

            next_pk = session.query(sqlalchemy.func.max(PhoneInterval.id)).scalar() + 1
            begin = self.word_interval.begin
            phone_duration = (self.word_interval.end - self.word_interval.begin) / len(new_phones)
            for p in new_phones:
                end = begin + phone_duration
                pi = PhoneInterval(
                    id=next_pk,
                    begin=begin,
                    end=end,
                    phone=self.corpus_model.phones[p],
                    word_interval=self.word_interval,
                    word_interval_id=self.word_interval.id,
                )
                self.new_phone_intervals.append(pi)
                begin = end
                next_pk += 1
            self.new_phone_intervals[-1].end = self.word_interval.end
        for pi in self.new_phone_intervals:
            make_transient(pi)
            phone_intervals.append(pi)
        self.utterance.phone_intervals = sorted(phone_intervals, key=lambda x: x.begin)

        session.merge(self.utterance)
        self.word_interval.pronunciation_id = self.new_pronunciation.id
        session.merge(self.word_interval)

    def _undo(self, session) -> None:
        phone_intervals = []
        for pi in self.utterance.phone_intervals:
            if pi.word_interval_id != self.word_interval.id:
                session.merge(pi)
                phone_intervals.append(pi)
        for pi in self.old_phone_intervals:
            make_transient(pi)
            phone_intervals.append(pi)

        self.utterance.phone_intervals = sorted(phone_intervals, key=lambda x: x.begin)

        session.merge(self.utterance)
        self.word_interval.pronunciation_id = self.old_pronunciation_id
        session.merge(self.word_interval)

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()
        self.file_model.phoneTierChanged.emit(self.utterance)


class UpdateWordIntervalWordCommand(FileCommand):
    def __init__(
        self,
        utterance: Utterance,
        word_interval: WordInterval,
        word: typing.Union[Word, str],
        file_model: FileUtterancesModel,
    ):
        super().__init__(file_model)
        self.utterance = utterance
        self.word_interval = word_interval
        self.old_word = self.word_interval.word
        self.new_word = word
        self.need_words_refreshed = isinstance(word, str)

        self.setText(
            QtCore.QCoreApplication.translate(
                "UpdateWordIntervalPronunciationCommand", "Update pronunciation for word interval"
            )
        )

    def _redo(self, session) -> None:
        session.merge(self.utterance)
        if isinstance(self.new_word, str):
            max_id, max_mapping_id = session.query(
                sqlalchemy.func.max(Word.id), sqlalchemy.func.max(Word.mapping_id)
            ).first()
            dictionary_id = self.utterance.speaker.dictionary_id
            if not dictionary_id:
                dictionary_id = 1

            self.new_word = Word(
                id=max_id + 1,
                mapping_id=max_mapping_id + 1,
                word=self.new_word,
                count=1,
                dictionary_id=dictionary_id,
                word_type=WordType.speech,
            )
            session.merge(self.new_word)

        self.word_interval.word = self.new_word
        self.word_interval.word_id = self.new_word.id
        session.merge(self.word_interval)

    def _undo(self, session) -> None:
        session.merge(self.utterance)
        self.word_interval.word = self.old_word
        self.word_interval.word_id = self.old_word.id
        session.merge(self.word_interval)

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()
        self.file_model.phoneTierChanged.emit(self.utterance)
        if self.need_words_refreshed:
            self.corpus_model.refresh_words()
            self.need_words_refreshed = False


class UpdatePhoneIntervalCommand(FileCommand):
    def __init__(
        self,
        utterance: Utterance,
        phone_interval: PhoneInterval,
        new_phone: Phone,
        file_model: FileUtterancesModel,
    ):
        super().__init__(file_model)
        self.utterance = utterance
        self.old_manual_alignments = utterance.manual_alignments
        self.phone_interval = phone_interval
        self.old_phone = self.phone_interval.phone
        self.new_phone = new_phone
        self.setText(
            QtCore.QCoreApplication.translate(
                "UpdatePhoneIntervalCommand", "Update phone interval"
            )
        )

    def _redo(self, session) -> None:
        if not self.old_manual_alignments:
            self.utterance.manual_alignments = True
            session.merge(self.utterance)
        self.phone_interval.phone = self.new_phone
        self.phone_interval.phone_id = self.new_phone.id
        session.merge(self.phone_interval)

    def _undo(self, session) -> None:
        if not self.old_manual_alignments:
            self.utterance.manual_alignments = self.old_manual_alignments
            session.merge(self.utterance)
        self.phone_interval.phone = self.old_phone
        self.phone_interval.phone_id = self.old_phone.id
        session.merge(self.phone_interval)

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()
        self.file_model.phoneTierChanged.emit(self.utterance)


class UpdateUtteranceTextCommand(FileCommand):
    def __init__(self, utterance: Utterance, new_text: str, file_model: FileUtterancesModel):
        super().__init__(file_model)
        self.utterance = utterance
        self.speaker_id = utterance.speaker_id
        self.old_text = utterance.text
        self.new_text = new_text
        self.setText(
            QtCore.QCoreApplication.translate(
                "UpdateUtteranceTextCommand", "Update utterance text"
            )
        )
        try:
            self.tokenizer = self.corpus_model.corpus.get_tokenizer(
                self.corpus_model.corpus.get_dict_id_for_speaker(
                    self.corpus_model.get_speaker_name(self.speaker_id)
                )
            )
        except (AttributeError, KeyError):
            self.tokenizer = None

    def _process_text(self, session, text: str):
        self.utterance.text = text
        if self.tokenizer is not None:
            text = unicodedata.normalize("NFKC", text)
            normalized_text, normalized_character_text, oovs = self.tokenizer(text)
            self.utterance.normalized_text = normalized_text
            self.utterance.normalized_character_text = normalized_character_text
            self.utterance.oovs = " ".join(oovs)
        self.utterance.ignored = not text
        session.merge(self.utterance)

    def _redo(self, session) -> None:
        self._process_text(session, self.new_text)

    def _undo(self, session) -> None:
        self._process_text(session, self.old_text)

    def id(self) -> int:
        return 1

    def mergeWith(self, other: UpdateUtteranceTextCommand) -> bool:
        if other.id() != self.id() or other.utterance.id != self.utterance.id:
            return False
        self.new_text = other.new_text
        return True

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()
        self.corpus_model.update_utterance_table_row(self.utterance)


class ReplaceAllCommand(CorpusCommand):
    def __init__(
        self, search_query: TextFilterQuery, replacement_string: str, corpus_model: CorpusModel
    ):
        super().__init__(corpus_model)
        self.search_query = search_query
        self.replacement_string = replacement_string
        self.old_texts = {}
        self.new_texts = None
        self.current_texts = None
        self.setText(QtCore.QCoreApplication.translate("ReplaceAllCommand", "Replace all"))

    def _redo(self, session) -> None:
        mapping = [{"id": k, "text": v} for k, v in self.new_texts.items()]
        session.bulk_update_mappings(Utterance, mapping)
        self.current_texts = self.new_texts

    def _undo(self, session) -> None:
        mapping = [{"id": k, "text": v} for k, v in self.old_texts.items()]
        session.bulk_update_mappings(Utterance, mapping)
        self.current_texts = self.old_texts

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()
        self.corpus_model.update_texts(self.current_texts)
        self.corpus_model.statusUpdate.emit(
            f"Replaced {len(self.current_texts)} instances of {self.search_query.generate_expression()}"
        )

    def finish_replace_all(self, result):
        if result is None:
            return
        search_string, old_texts, new_texts = result
        self.old_texts = old_texts
        self.new_texts = new_texts
        self.current_texts = self.new_texts
        self.update_data()

    def redo(self) -> None:
        if self.new_texts is None:
            self.corpus_model.runFunction.emit(
                "Replacing query",
                self.finish_replace_all,
                [self.search_query, self.replacement_string],
            )
        else:
            super().redo()


class ChangeSpeakerCommand(SpeakerCommand):
    def __init__(
        self,
        utterance_ids: typing.Union[typing.List[int], typing.List[typing.List[int]]],
        old_speaker_id: int = None,
        new_speaker_id: int = None,
        speaker_model: typing.Union[SpeakerModel, DiarizationModel] = None,
    ):
        super().__init__(speaker_model)
        self.data: typing.List[typing.List[int]] = []
        if new_speaker_id is None:
            self.data = utterance_ids
        else:
            self.utterance_ids = utterance_ids
        self.old_speaker_id = old_speaker_id
        self.new_speaker_id = new_speaker_id
        self.auto_refresh = False
        self.setText(QtCore.QCoreApplication.translate("ChangeSpeakerCommand", "Change speakers"))

    def finish_recalculate(self, result=None):
        if result is not None:
            self.speaker_model.corpus_model.speaker_plda = result

    def update_data(self):
        pass

    def finish_changing_speaker(self, data: typing.List[typing.List[int]]):
        self.data = data
        self.utterance_ids = [x[0] for x in self.data]
        self.speaker_model.corpus_model.runFunction.emit(
            "Recalculating speaker ivectors",
            self.finish_recalculate,
            [
                {
                    "plda": self.speaker_model.corpus_model.plda,
                    "speaker_plda": self.speaker_model.corpus_model.speaker_plda,
                }
            ],
        )
        from anchor.models import SpeakerModel

        if self.auto_refresh:
            self.speaker_model.update_data()
        if self.resets_tier:
            self.speaker_model.corpus_model.refreshTiers.emit()
        self.speaker_model.corpus_model.changeCommandFired.emit()
        self.speaker_model.corpus_model.statusUpdate.emit(
            f"Changed speaker for {len(self.utterance_ids)} utterances"
        )
        if isinstance(self.speaker_model, SpeakerModel):
            self.speaker_model.indices_updated(self.utterance_ids, self.new_speaker_id)

    def _redo(self, session) -> None:
        self.speaker_model.corpus_model.runFunction.emit(
            "Changing speakers",
            self.finish_changing_speaker,
            [
                self.data if self.data else self.utterance_ids,
                self.new_speaker_id,
                self.old_speaker_id,
            ],
        )

    def _undo(self, session) -> None:
        undo_data = [[x[0], x[2], x[1]] for x in self.data]
        self.speaker_model.corpus_model.runFunction.emit(
            "Changing speakers",
            self.finish_changing_speaker,
            [undo_data, self.old_speaker_id, self.new_speaker_id],
        )


class UpdateSpeakerCommand(SpeakerCommand):
    def __init__(self, speaker_id: int, old_name: str, new_name: str, speaker_model: SpeakerModel):
        super().__init__(speaker_model)
        self.speaker_id = speaker_id
        self.old_name = old_name
        self.new_name = new_name
        self.setText(
            QtCore.QCoreApplication.translate("UpdateSpeakerCommand", "Update speaker name")
        )

    def _redo(self, session) -> None:
        session.query(Speaker).filter(Speaker.id == self.speaker_id).update(
            {Speaker.name: self.new_name}
        )

    def _undo(self, session) -> None:
        session.query(Speaker).filter(Speaker.id == self.speaker_id).update(
            {Speaker.name: self.old_name}
        )


class UpdateUtteranceSpeakerCommand(FileCommand):
    def __init__(
        self,
        utterances: typing.Union[Utterance, typing.List[Utterance]],
        new_speaker: typing.Union[Speaker, int],
        file_model: FileUtterancesModel,
    ):
        super().__init__(file_model)
        if not isinstance(utterances, list):
            utterances = [utterances]
        self.utterances = utterances
        self.utterance_ids = [x.id for x in utterances]
        self.file_ids = set([x.file_id for x in utterances])
        self.old_speaker_ids = [x.speaker_id for x in utterances]
        if isinstance(new_speaker, int):
            self.new_speaker_id = new_speaker
        else:
            self.new_speaker_id = new_speaker.id
        self.setText(
            QtCore.QCoreApplication.translate(
                "UpdateUtteranceSpeakerCommand", "Update utterance speaker"
            )
        )

    def finish_recalculate(self, result=None, **kwargs):
        if result is not None:
            self.corpus_model.speaker_plda = result

    def _redo(self, session) -> None:
        if self.new_speaker_id <= 0:
            self.new_speaker_id = session.query(sqlalchemy.func.max(Speaker.id)).scalar() + 1
            speaker = session.get(Speaker, self.old_speaker_ids[0])
            original_name = speaker.name
            index = 1
            while True:
                speaker_name = f"{original_name}_{index}"
                t = session.query(Speaker).filter(Speaker.name == speaker_name).first()
                if t is None:
                    break
                index += 1
            session.execute(
                sqlalchemy.insert(Speaker).values(
                    id=self.new_speaker_id, name=speaker_name, dictionary_id=speaker.dictionary_id
                )
            )
            session.flush()
        mappings = []
        for u in self.utterances:
            u.speaker_id = self.new_speaker_id
            mappings.append({"id": u.id, "speaker_id": self.new_speaker_id})
        bulk_update(self.corpus_model.session, Utterance, mappings)

    def _undo(self, session) -> None:
        mappings = []
        for i, u in enumerate(self.utterances):
            u.speaker_id = self.old_speaker_ids[i]
            mappings.append({"id": u.id, "speaker_id": self.old_speaker_ids[i]})
        bulk_update(self.corpus_model.session, Utterance, mappings)

    def update_data(self):
        super().update_data()
        self.corpus_model.set_file_modified(self.file_ids)
        self.corpus_model.change_speaker_table_utterances(self.utterances)
        self.file_model.change_speaker_table_utterances(self.utterances)
        self.corpus_model.changeCommandFired.emit()
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


class UpdatePronunciationCommand(DictionaryCommand):
    def __init__(
        self,
        pronunciation_id: int,
        old_pronunciation: str,
        new_pronunciation: str,
        dictionary_model: DictionaryTableModel,
    ):
        super().__init__(dictionary_model)
        self.pronunciation_id = pronunciation_id
        self.old_pronunciation = old_pronunciation
        self.new_pronunciation = new_pronunciation
        self.setText(
            QtCore.QCoreApplication.translate("UpdatePronunciationCommand", "Update pronunciation")
        )

    def _redo(self, session) -> None:
        session.query(Pronunciation).filter(Pronunciation.id == self.pronunciation_id).update(
            {Pronunciation.pronunciation: self.new_pronunciation}
        )

    def _undo(self, session) -> None:
        session.query(Pronunciation).filter(Pronunciation.id == self.pronunciation_id).update(
            {Pronunciation.pronunciation: self.old_pronunciation}
        )


class ChangeWordTypeCommand(DictionaryCommand):
    def __init__(
        self,
        word_id: int,
        old_word_type: WordType,
        new_word_type: WordType,
        dictionary_model: DictionaryTableModel,
    ):
        super().__init__(dictionary_model)
        self.word_id = word_id
        self.old_word_type = old_word_type
        self.new_word_type = new_word_type
        self.setText(
            QtCore.QCoreApplication.translate("UpdatePronunciationCommand", "Update pronunciation")
        )

    def _redo(self, session) -> None:
        session.query(Word).filter(Word.id == self.word_id).update(
            {Word.word_type: self.new_word_type}
        )

    def _undo(self, session) -> None:
        session.query(Word).filter(Word.id == self.word_id).update(
            {Word.word_type: self.old_word_type}
        )


class AddPronunciationCommand(DictionaryCommand):
    def __init__(
        self,
        word: str,
        pronunciation: str,
        dictionary_model: DictionaryTableModel,
        word_id: typing.Optional[int] = None,
    ):
        super().__init__(dictionary_model)
        self.pronunciation = pronunciation
        self.oov_phone = dictionary_model.corpus_model.corpus.oov_phone
        if not self.pronunciation:
            if dictionary_model.g2p_generator is not None:
                try:
                    self.pronunciation = dictionary_model.g2p_generator.rewriter(word)[0][0]
                except (pynini.lib.rewrite.Error, IndexError):
                    self.pronunciation = self.oov_phone
            else:
                self.pronunciation = self.oov_phone
        self.pronunciation_id = None
        self.word_id = word_id
        self.word = word
        self.setText(
            QtCore.QCoreApplication.translate("AddPronunciationCommand", "Add pronunciation")
        )

    def _redo(self, session) -> None:
        if self.word_id is None:
            q = session.query(Word.id).filter(Word.word == self.word).first()
            if q is not None:
                self.word_id = q[0]
            if self.word_id is None:
                self.word_id = session.query(sqlalchemy.func.max(Word.id)).scalar() + 1
                word_mapping_id = (
                    session.query(sqlalchemy.func.max(Word.mapping_id))
                    .filter(Word.dictionary_id == self.dictionary_model.current_dictionary_id)
                    .scalar()
                    + 1
                )
                session.execute(
                    sqlalchemy.insert(Word).values(
                        id=self.word_id,
                        mapping_id=word_mapping_id,
                        word=self.word,
                        dictionary_id=self.dictionary_model.current_dictionary_id,
                        word_type=WordType.speech,
                    )
                )
        self.pronunciation_id = (
            session.query(Pronunciation.id)
            .filter(
                Pronunciation.word_id == self.word_id,
                Pronunciation.pronunciation == self.oov_phone,
            )
            .scalar()
        )
        if self.pronunciation_id is None:
            self.pronunciation_id = (
                session.query(sqlalchemy.func.max(Pronunciation.id)).scalar() + 1
            )
            session.execute(
                sqlalchemy.insert(Pronunciation).values(
                    word_id=self.word_id,
                    id=self.pronunciation_id,
                    pronunciation=self.pronunciation,
                )
            )
        else:
            session.query(Pronunciation).filter(Pronunciation.id == self.pronunciation_id).update(
                {Pronunciation.pronunciation: self.pronunciation}
            )
        session.query(Word).filter(Word.id == self.word_id).update(
            {Word.word_type: WordType.speech}
        )

    def _undo(self, session) -> None:
        session.execute(
            sqlalchemy.delete(Pronunciation).where(Pronunciation.id == self.pronunciation_id)
        )
        count = (
            session.query(sqlalchemy.func.count(Pronunciation.id))
            .filter(Pronunciation.word_id == self.word_id)
            .scalar()
        )
        if count == 0:
            session.query(Word).filter(Word.id == self.word_id).update(
                {Word.word_type: WordType.oov}
            )


class DeletePronunciationCommand(DictionaryCommand):
    def __init__(
        self, pronunciation_ids: typing.List[int], dictionary_model: DictionaryTableModel
    ):
        super().__init__(dictionary_model)
        self.pronunciation_ids = pronunciation_ids
        self.pronunciations = []
        self.setText(
            QtCore.QCoreApplication.translate("DeletePronunciationCommand", "Delete pronunciation")
        )

    def _redo(self, session) -> None:
        if not self.pronunciations:
            self.pronunciations = (
                session.query(Pronunciation)
                .filter(Pronunciation.id.in_(self.pronunciation_ids))
                .all()
            )
        session.query(Pronunciation).filter(Pronunciation.id.in_(self.pronunciation_ids)).delete()

    def _undo(self, session) -> None:
        for p in self.pronunciations:
            make_transient(p)
            session.merge(p)


class DeleteWordCommand(DictionaryCommand):
    def __init__(self, word_ids: typing.List[int], dictionary_model: DictionaryTableModel):
        super().__init__(dictionary_model)
        self.word_ids = word_ids
        self.words = []
        self.setText(
            QtCore.QCoreApplication.translate("DeletePronunciationCommand", "Delete pronunciation")
        )

    def _redo(self, session) -> None:
        if not self.words:
            query = (
                session.query(Word)
                .options(sqlalchemy.orm.selectinload(Word.pronunciations))
                .filter(Word.id.in_(self.word_ids))
            )
            self.words = []
            for word in query:
                if word not in self.words:
                    self.words.append(word)

        for w in self.words:
            session.delete(w)

    def _undo(self, session) -> None:
        for w in self.words:
            make_transient(w)
            for p in w.pronunciations:
                make_transient(p)
            session.merge(w)


class UpdateWordCommand(DictionaryCommand):
    def __init__(
        self, word_id: int, old_word: str, new_word: str, dictionary_model: DictionaryTableModel
    ):
        super().__init__(dictionary_model)
        self.word_id = word_id
        self.old_word = old_word
        self.new_word = new_word
        self.setText(QtCore.QCoreApplication.translate("UpdateWordCommand", "Update orthography"))

    def _redo(self, session) -> None:
        session.query(Word).filter(Word.id == self.word_id).update({Word.word: self.new_word})

    def _undo(self, session) -> None:
        session.query(Word).filter(Word.id == self.word_id).update({Word.word: self.old_word})
