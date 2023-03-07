from __future__ import annotations

import collections
import typing

import psycopg2.errors
import pynini.lib
import sqlalchemy
from montreal_forced_aligner.data import WordType
from montreal_forced_aligner.db import (
    File,
    Pronunciation,
    Speaker,
    SpeakerOrdering,
    Utterance,
    Word,
)
from PySide6 import QtCore, QtGui
from sqlalchemy.orm import make_transient

if typing.TYPE_CHECKING:
    from anchor.models import CorpusModel, DictionaryTableModel, SpeakerModel, TextFilterQuery


class CorpusCommand(QtGui.QUndoCommand):
    def __init__(self, corpus_model: CorpusModel):
        super().__init__()
        self.corpus_model = corpus_model
        self.resets_tier = False

    def _redo(self) -> None:
        pass

    def _undo(self) -> None:
        pass

    def update_data(self):
        if self.resets_tier:
            self.corpus_model.refreshTiers.emit()

    def redo(self) -> None:
        with self.corpus_model.edit_lock:
            while True:
                try:
                    with self.corpus_model.session.begin_nested():
                        self._redo()
                    break
                except psycopg2.errors.DeadlockDetected:
                    pass
            self.corpus_model.session.commit()

        self.update_data()

    def undo(self) -> None:
        with self.corpus_model.edit_lock:
            while True:
                try:
                    with self.corpus_model.session.begin_nested():
                        self._undo()
                    break
                except psycopg2.errors.DeadlockDetected:
                    pass
            self.corpus_model.session.commit()
        self.update_data()


class DictionaryCommand(QtGui.QUndoCommand):
    def __init__(self, dictionary_model: DictionaryTableModel):
        super().__init__()
        self.dictionary_model = dictionary_model

    def _redo(self) -> None:
        pass

    def _undo(self) -> None:
        pass

    def redo(self) -> None:
        with self.dictionary_model.corpus_model.edit_lock:
            while True:
                try:
                    with self.dictionary_model.corpus_model.session.begin_nested():
                        self._redo()
                        self.dictionary_model.corpus_model.session.flush()
                    break
                except psycopg2.errors.DeadlockDetected:
                    pass
            self.dictionary_model.corpus_model.session.commit()

        self.dictionary_model.update_data()

    def undo(self) -> None:
        with self.dictionary_model.corpus_model.edit_lock:
            while True:
                try:
                    with self.dictionary_model.corpus_model.session.begin_nested():
                        self._undo()
                        self.dictionary_model.corpus_model.session.flush()
                    break
                except psycopg2.errors.DeadlockDetected:
                    pass
            self.dictionary_model.corpus_model.session.commit()
        self.dictionary_model.update_data()


class SpeakerCommand(QtGui.QUndoCommand):
    def __init__(self, speaker_model: SpeakerModel):
        super().__init__()
        self.speaker_model = speaker_model
        self.auto_refresh = True
        self.resets_tier = False

    def _redo(self) -> None:
        pass

    def _undo(self) -> None:
        pass

    def update_data(self):
        if self.auto_refresh:
            self.speaker_model.update_data()
        if self.resets_tier:
            self.speaker_model.corpus_model.refreshTiers.emit()

    def redo(self) -> None:
        with self.speaker_model.corpus_model.edit_lock:
            while True:
                try:
                    with self.speaker_model.corpus_model.session.begin_nested():
                        self._redo()
                        self.speaker_model.corpus_model.session.flush()
                    break
                except psycopg2.errors.DeadlockDetected:
                    pass
            self.speaker_model.corpus_model.session.commit()
        self.update_data()

    def undo(self) -> None:
        with self.speaker_model.corpus_model.edit_lock:
            while True:
                try:
                    with self.speaker_model.corpus_model.session.begin_nested():
                        self._undo()
                        self.speaker_model.corpus_model.session.flush()
                    break
                except psycopg2.errors.DeadlockDetected:
                    pass
            self.speaker_model.corpus_model.session.commit()
        self.update_data()


class DeleteUtteranceCommand(CorpusCommand):
    def __init__(self, deleted_utterances: list[Utterance], corpus_model: CorpusModel):
        super().__init__(corpus_model)
        self.deleted_utterances = deleted_utterances
        self.resets_tier = True
        self.channels = [
            x.channel if x.channel is not None else 0 for x in self.deleted_utterances
        ]
        self.setText(
            QtCore.QCoreApplication.translate("DeleteUtteranceCommand", "Delete utterances")
        )

    def _redo(self) -> None:
        for utt in self.deleted_utterances:
            self.corpus_model.session.delete(utt)

    def _undo(self) -> None:
        for i, utt in enumerate(self.deleted_utterances):
            make_transient(utt)
            for x in utt.phone_intervals:
                x.duration = None
                make_transient(x)
            for x in utt.word_intervals:
                make_transient(x)
            if utt.channel is None:
                utt.channel = self.channels[i]
            self.corpus_model.session.add(utt)

    def redo(self) -> None:
        super().redo()
        self.corpus_model.delete_table_utterances(self.deleted_utterances)
        self.corpus_model.changeCommandFired.emit()

    def undo(self) -> None:
        super().undo()
        self.corpus_model.add_table_utterances(self.deleted_utterances)
        self.corpus_model.changeCommandFired.emit()


class SplitUtteranceCommand(CorpusCommand):
    def __init__(self, split_utterances: list[list[Utterance, ...]], corpus_model: CorpusModel):
        super().__init__(corpus_model)
        self.split_utterances = split_utterances
        self.resets_tier = True
        self.channels = [
            x[0].channel if x[0].channel is not None else 0 for x in self.split_utterances
        ]
        self.setText(
            QtCore.QCoreApplication.translate("SplitUtteranceCommand", "Split utterances")
        )

    def _redo(self) -> None:
        for i, splits in enumerate(self.split_utterances):
            old_utt = splits[0]
            split_utts = splits[1:]
            self.corpus_model.session.delete(old_utt)
            for u in split_utts:
                if u.id is not None:
                    make_transient(u)
                for x in u.phone_intervals:
                    x.duration = None
                    make_transient(x)
                for x in u.word_intervals:
                    make_transient(x)
                if u.channel is None:
                    u.channel = self.channels[i]
                u.duration = None
                u.kaldi_id = None
                self.corpus_model.session.add(u)

    def _undo(self) -> None:
        for i, splits in enumerate(self.split_utterances):
            old_utt = splits[0]
            split_utts = splits[1:]
            if old_utt.channel is None:
                old_utt.channel = self.channels[i]
            old_utt.duration = None
            old_utt.kaldi_id = None
            make_transient(old_utt)
            for x in old_utt.phone_intervals:
                x.duration = None
                make_transient(x)
            for x in old_utt.word_intervals:
                make_transient(x)
            self.corpus_model.session.add(old_utt)
            for u in split_utts:
                self.corpus_model.session.delete(u)

    def redo(self) -> None:
        super().redo()
        for splits in self.split_utterances:
            old_utt = splits[0]
            split_utts = splits[1:]
            self.corpus_model.split_table_utterances(old_utt, split_utts)
        self.corpus_model.changeCommandFired.emit()

    def undo(self) -> None:
        super().undo()
        for splits in self.split_utterances:
            old_utt = splits[0]
            split_utts = splits[1:]
            self.corpus_model.merge_table_utterances(old_utt, split_utts)
        self.corpus_model.changeCommandFired.emit()


class MergeUtteranceCommand(CorpusCommand):
    def __init__(
        self,
        unmerged_utterances: list[Utterance],
        merged_utterance: Utterance,
        corpus_model: CorpusModel,
    ):
        super().__init__(corpus_model)
        self.unmerged_utterances = unmerged_utterances
        self.merged_utterance = merged_utterance
        self.resets_tier = True
        self.channel = self.merged_utterance.channel
        if self.channel is None:
            self.channel = 0
        self.setText(
            QtCore.QCoreApplication.translate("MergeUtteranceCommand", "Merge utterances")
        )

    def _redo(self) -> None:
        for old_utt in self.unmerged_utterances:
            self.corpus_model.session.delete(old_utt)
        make_transient(self.merged_utterance)
        if self.merged_utterance.channel is None:
            self.merged_utterance.channel = self.channel
        self.merged_utterance.kaldi_id = None
        self.merged_utterance.duration = None
        self.corpus_model.session.add(self.merged_utterance)

    def _undo(self) -> None:
        for old_utt in self.unmerged_utterances:
            make_transient(old_utt)
            if old_utt.channel is None:
                old_utt.channel = self.channel
            for x in old_utt.phone_intervals:
                x.duration = None
                make_transient(x)
            for x in old_utt.word_intervals:
                make_transient(x)
            old_utt.duration = None
            old_utt.kaldi_id = None
            self.corpus_model.session.add(old_utt)
        # self.corpus_model.session.refresh(self.merged_utterance)
        self.corpus_model.session.delete(self.merged_utterance)

    def redo(self) -> None:
        super().redo()
        self.corpus_model.merge_table_utterances(self.merged_utterance, self.unmerged_utterances)
        self.corpus_model.changeCommandFired.emit()

    def undo(self) -> None:
        super().undo()
        self.corpus_model.split_table_utterances(self.merged_utterance, self.unmerged_utterances)
        self.corpus_model.changeCommandFired.emit()


class MergeSpeakersCommand(CorpusCommand):
    def __init__(self, speakers: list[int], corpus_model: CorpusModel):
        super().__init__(corpus_model)
        self.merged_speaker = speakers.pop(0)
        self.speakers = speakers
        self.resets_tier = True
        self.utt_mapping = collections.defaultdict(list)
        self.file_mapping = collections.defaultdict(list)
        q = self.corpus_model.session.query(
            Utterance.id, Utterance.file_id, Utterance.speaker_id
        ).filter(Utterance.speaker_id.in_(self.speakers))
        self.files = []
        for utt_id, file_id, speaker_id in q:
            self.utt_mapping[speaker_id].append(utt_id)
            self.file_mapping[speaker_id].append(file_id)
            self.files.append(file_id)
        self.deleted_speakers = [
            self.corpus_model.session.query(Speaker).get(x) for x in self.speakers
        ]
        self.setText(QtCore.QCoreApplication.translate("MergeSpeakersCommand", "Merge speakers"))

    def finish_recalculate(self, *args, **kwargs):
        pass

    def _redo(self) -> None:
        self.corpus_model.session.query(Utterance).filter(
            Utterance.speaker_id.in_(self.speakers)
        ).update({Utterance.speaker_id: self.merged_speaker})
        self.corpus_model.session.query(SpeakerOrdering).filter(
            SpeakerOrdering.c.speaker_id.in_(self.speakers)
        ).update({SpeakerOrdering.c.speaker_id: self.merged_speaker})
        self.corpus_model.session.query(File).filter(File.id.in_(self.files)).update(
            {File.modified: True}
        )
        self.corpus_model.runFunction.emit(
            "Recalculate speaker ivector",
            self.finish_recalculate,
            [
                {
                    "speaker_id": self.merged_speaker,
                }
            ],
        )

        for s in self.deleted_speakers:
            self.corpus_model.session.delete(s)

    def _undo(self) -> None:
        for s in self.deleted_speakers:
            self.corpus_model.session.merge(s)
        for speaker, utts in self.utt_mapping.items():
            self.corpus_model.session.query(Utterance).filter(Utterance.id.in_(utts)).update(
                {Utterance.speaker_id: speaker}
            )
        for speaker, files in self.file_mapping.items():
            self.corpus_model.session.query(SpeakerOrdering).filter(
                SpeakerOrdering.c.file_id.in_(files)
            ).update({SpeakerOrdering.c.speaker_id: speaker})
        self.corpus_model.session.query(File).filter(File.id.in_(self.files)).update(
            {File.modified: True}
        )


class CreateUtteranceCommand(CorpusCommand):
    def __init__(self, new_utterance: Utterance, corpus_model: CorpusModel):
        super().__init__(corpus_model)
        self.new_utterance = new_utterance
        self.resets_tier = True
        self.channel = self.new_utterance.channel
        if self.channel is None:
            self.channel = 0
        self.setText(
            QtCore.QCoreApplication.translate("CreateUtteranceCommand", "Create utterance")
        )

    def _redo(self) -> None:
        make_transient(self.new_utterance)
        self.new_utterance.duration = self.new_utterance.end - self.new_utterance.begin
        if self.new_utterance.channel is None:
            self.new_utterance.channel = self.channel
        self.corpus_model.session.add(self.new_utterance)

    def _undo(self) -> None:
        self.corpus_model.session.delete(self.new_utterance)

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()
        self.corpus_model.add_table_utterances([self.new_utterance])

    def redo(self) -> None:
        super().redo()
        self.corpus_model.add_table_utterances([self.new_utterance])
        self.corpus_model.changeCommandFired.emit()

    def undo(self) -> None:
        super().undo()
        self.corpus_model.delete_table_utterances([self.new_utterance])
        self.corpus_model.changeCommandFired.emit()


class UpdateUtteranceTimesCommand(CorpusCommand):
    def __init__(self, utterance: Utterance, begin: float, end: float, corpus_model: CorpusModel):
        super().__init__(corpus_model)
        self.utterance_id = utterance.id
        self.new_begin = begin
        self.old_begin = utterance.begin
        self.new_end = end
        self.old_end = utterance.end
        self.setText(
            QtCore.QCoreApplication.translate(
                "UpdateUtteranceTimesCommand", "Update utterance times"
            )
        )

    def _redo(self) -> None:
        self.corpus_model.session.query(Utterance).filter(
            Utterance.id == self.utterance_id
        ).update({Utterance.begin: self.new_begin, Utterance.end: self.new_end})

    def _undo(self) -> None:
        self.corpus_model.session.query(Utterance).filter(
            Utterance.id == self.utterance_id
        ).update({Utterance.begin: self.old_begin, Utterance.end: self.old_end})

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()
        self.corpus_model.update_utterance_table_row(self.utterance_id)


class UpdateUtteranceTextCommand(CorpusCommand):
    def __init__(self, utterance: Utterance, new_text: str, corpus_model: CorpusModel):
        super().__init__(corpus_model)
        self.utterance_id = utterance.id
        self.speaker_id = utterance.speaker_id
        self.old_text = utterance.text
        self.new_text = new_text
        self.setText(
            QtCore.QCoreApplication.translate(
                "UpdateUtteranceTextCommand", "Update utterance text"
            )
        )

    def _redo(self) -> None:
        oovs = set()
        for w in self.new_text.split():
            if not self.corpus_model.dictionary_model.check_word(w, self.speaker_id):
                oovs.add(w)
        self.corpus_model.session.query(Utterance).filter(
            Utterance.id == self.utterance_id
        ).update(
            {
                Utterance.text: self.new_text,
                Utterance.normalized_text: self.new_text,  # FIXME: Update this
                Utterance.oovs: " ".join(oovs),
                Utterance.ignored: not self.new_text,
            }
        )

    def _undo(self) -> None:
        oovs = set()
        for w in self.new_text.split():
            if not self.corpus_model.dictionary_model.check_word(w, self.speaker_id):
                oovs.add(w)
        self.corpus_model.session.query(Utterance).filter(
            Utterance.id == self.utterance_id
        ).update(
            {
                Utterance.text: self.old_text,
                Utterance.oovs: " ".join(oovs),
                Utterance.ignored: not self.old_text,
            }
        )

    def update_data(self):
        super().update_data()
        try:
            self.corpus_model.update_utterance_table_row(self.utterance_id)
        except KeyError:
            pass

    def id(self) -> int:
        return 1

    def mergeWith(self, other: UpdateUtteranceTextCommand) -> bool:
        if other.id() != self.id() or other.utterance_id != self.utterance_id:
            return False
        self.new_text = other.new_text
        return True


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

    def _redo(self) -> None:
        mapping = [{"id": k, "text": v} for k, v in self.new_texts.items()]
        self.corpus_model.session.bulk_update_mappings(Utterance, mapping)
        self.current_texts = self.new_texts

    def _undo(self) -> None:
        mapping = [{"id": k, "text": v} for k, v in self.old_texts.items()]
        self.corpus_model.session.bulk_update_mappings(Utterance, mapping)
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
        utterance_ids: typing.List[int],
        old_speaker_id: int,
        new_speaker_id: int,
        speaker_model: SpeakerModel,
    ):
        super().__init__(speaker_model)
        self.utterance_ids = utterance_ids
        self.old_speaker_id = old_speaker_id
        self.new_speaker_id = new_speaker_id
        self.auto_refresh = False
        self.setText(QtCore.QCoreApplication.translate("ChangeSpeakerCommand", "Change speakers"))

    def finish_recalculate(self):
        pass

    def update_data(self):
        super().update_data()
        self.speaker_model.corpus_model.changeCommandFired.emit()
        self.speaker_model.corpus_model.statusUpdate.emit(
            f"Changed speaker for {len(self.utterance_ids)} utterances"
        )
        self.speaker_model.speakersChanged.emit()

    def finish_changing_speaker(self, new_speaker_id):
        self.new_speaker_id = new_speaker_id
        self.speaker_model.indices_updated(self.utterance_ids, self.old_speaker_id)
        self.speaker_model.corpus_model.runFunction.emit(
            "Recalculate speaker ivector",
            self.finish_recalculate,
            [
                {
                    "speaker_id": self.old_speaker_id,
                }
            ],
        )
        self.speaker_model.corpus_model.runFunction.emit(
            "Recalculate speaker ivector",
            self.finish_recalculate,
            [
                {
                    "speaker_id": self.new_speaker_id,
                }
            ],
        )

    def _redo(self) -> None:
        self.speaker_model.corpus_model.runFunction.emit(
            "Changing speakers",
            self.finish_changing_speaker,
            [self.utterance_ids, self.new_speaker_id, self.old_speaker_id],
        )

    def _undo(self) -> None:
        self.speaker_model.corpus_model.runFunction.emit(
            "Changing speakers",
            self.finish_changing_speaker,
            [self.utterance_ids, self.old_speaker_id, self.new_speaker_id],
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

    def _redo(self) -> None:
        self.speaker_model.corpus_model.session.query(Speaker).filter(
            Speaker.id == self.speaker_id
        ).update({Speaker.name: self.new_name})

    def _undo(self) -> None:
        self.speaker_model.corpus_model.session.query(Speaker).filter(
            Speaker.id == self.speaker_id
        ).update({Speaker.name: self.old_name})


class UpdateUtteranceSpeakerCommand(CorpusCommand):
    def __init__(
        self,
        utterance: Utterance,
        new_speaker: typing.Union[Speaker, int],
        corpus_model: CorpusModel,
    ):
        super().__init__(corpus_model)
        self.utterance = utterance
        self.old_speaker = utterance.speaker
        self.new_speaker = new_speaker
        if isinstance(self.new_speaker, Speaker):
            self.new_speaker = self.new_speaker.id
        self.resets_tier = True
        if (
            self.corpus_model.session.query(SpeakerOrdering)
            .filter(
                SpeakerOrdering.c.speaker_id == self.new_speaker,
                SpeakerOrdering.c.file_id == utterance.file_id,
            )
            .first()
            is None
        ):
            self.corpus_model.session.execute(
                sqlalchemy.insert(SpeakerOrdering).values(
                    speaker_id=self.new_speaker, file_id=self.utterance.file_id, index=2
                )
            )
            self.corpus_model.session.commit()
        self.setText(
            QtCore.QCoreApplication.translate(
                "UpdateUtteranceSpeakerCommand", "Update utterance speaker"
            )
        )

    def _redo(self) -> None:
        self.corpus_model.session.query(Utterance).filter(
            Utterance.id == self.utterance.id
        ).update({Utterance.speaker_id: self.new_speaker})

    def _undo(self) -> None:
        self.corpus_model.session.query(Utterance).filter(
            Utterance.id == self.utterance.id
        ).update({Utterance.speaker_id: self.old_speaker.id})

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()
        self.corpus_model.update_data()


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
        self.pronunciation: Pronunciation = self.dictionary_model.corpus_model.session.query(
            Pronunciation
        ).get(pronunciation_id)
        self.old_pronunciation = old_pronunciation
        self.new_pronunciation = new_pronunciation
        self.setText(
            QtCore.QCoreApplication.translate("UpdatePronunciationCommand", "Update pronunciation")
        )

    def _redo(self) -> None:
        self.pronunciation.pronunciation = self.new_pronunciation

    def _undo(self) -> None:
        self.pronunciation.pronunciation = self.old_pronunciation


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
                    self.pronunciation = dictionary_model.g2p_generator.rewriter(word)[0]
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

    def _redo(self) -> None:
        if self.word_id is None:
            self.word_id = (
                self.dictionary_model.corpus_model.session.query(Word.id)
                .filter(Word.word == self.word)
                .first()[0]
            )
            if self.word_id is None:
                self.word_id = (
                    self.dictionary_model.corpus_model.session.query(
                        sqlalchemy.func.max(Word.id)
                    ).scalar()
                    + 1
                )
                word_mapping_id = (
                    self.dictionary_model.corpus_model.session.query(
                        sqlalchemy.func.max(Word.mapping_id)
                    )
                    .filter(Word.dictionary_id == self.dictionary_model.current_dictionary_id)
                    .scalar()
                    + 1
                )
                self.dictionary_model.corpus_model.session.execute(
                    sqlalchemy.insert(Word).values(
                        id=self.word_id,
                        mapping_id=word_mapping_id,
                        word=self.word,
                        dictionary_id=self.dictionary_model.current_dictionary_id,
                        word_type=WordType.speech,
                    )
                )
        self.pronunciation_id = (
            self.dictionary_model.corpus_model.session.query(Pronunciation.id)
            .filter(
                Pronunciation.word_id == self.word_id,
                Pronunciation.pronunciation == self.oov_phone,
            )
            .scalar()
        )
        if self.pronunciation_id is None:
            self.pronunciation_id = (
                self.dictionary_model.corpus_model.session.query(
                    sqlalchemy.func.max(Pronunciation.id)
                ).scalar()
                + 1
            )
            self.dictionary_model.corpus_model.session.execute(
                sqlalchemy.insert(Pronunciation).values(
                    word_id=self.word_id,
                    id=self.pronunciation_id,
                    pronunciation=self.pronunciation,
                    base_pronunciation_id=self.pronunciation_id,
                )
            )
        else:
            self.dictionary_model.corpus_model.session.query(Pronunciation).filter(
                Pronunciation.id == self.pronunciation_id
            ).update({Pronunciation.pronunciation: self.pronunciation})
        self.dictionary_model.corpus_model.session.query(Word).filter(
            Word.id == self.word_id
        ).update({Word.word_type: WordType.speech})

    def _undo(self) -> None:
        self.dictionary_model.corpus_model.session.execute(
            sqlalchemy.delete(Pronunciation).where(Pronunciation.id == self.pronunciation_id)
        )
        count = (
            self.dictionary_model.corpus_model.session.query(
                sqlalchemy.func.count(Pronunciation.id)
            )
            .filter(Pronunciation.word_id == self.word_id)
            .scalar()
        )
        if count == 0:
            self.dictionary_model.corpus_model.session.query(Word).filter(
                Word.id == self.word_id
            ).update({Word.word_type: WordType.oov})


class DeletePronunciationCommand(DictionaryCommand):
    def __init__(
        self, pronunciation_ids: typing.List[int], dictionary_model: DictionaryTableModel
    ):
        super().__init__(dictionary_model)
        self.pronunciation_ids = pronunciation_ids
        self.pronunciations = (
            self.dictionary_model.corpus_model.session.query(Pronunciation)
            .filter(Pronunciation.id.in_(pronunciation_ids))
            .all()
        )
        self.setText(
            QtCore.QCoreApplication.translate("DeletePronunciationCommand", "Delete pronunciation")
        )

    def _redo(self) -> None:
        self.dictionary_model.corpus_model.session.query(Pronunciation).filter(
            Pronunciation.id.in_(self.pronunciation_ids)
        ).delete()

    def _undo(self) -> None:
        for p in self.pronunciations:
            make_transient(p)
            self.dictionary_model.corpus_model.session.merge(p)


class DeleteWordCommand(DictionaryCommand):
    def __init__(self, word_ids: typing.List[int], dictionary_model: DictionaryTableModel):
        super().__init__(dictionary_model)
        self.word_id = word_ids
        query = (
            self.dictionary_model.corpus_model.session.query(Word, Word.pronunciations)
            .join(Word.pronunciations)
            .filter(Word.id.in_(word_ids))
        )
        self.words = []
        self.pronunciations = []
        for word, pronunciation in query:
            if word not in self.words:
                self.words.append(word)
            self.pronunciations.append(pronunciation)
        self.setText(
            QtCore.QCoreApplication.translate("DeletePronunciationCommand", "Delete pronunciation")
        )

    def _redo(self) -> None:
        for p in self.pronunciations:
            self.dictionary_model.corpus_model.session.delete(p)
        for w in self.words:
            self.dictionary_model.corpus_model.session.delete(w)

    def _undo(self) -> None:
        for w in self.words:
            make_transient(w)
            self.dictionary_model.corpus_model.session.merge(w)
        for p in self.pronunciations:
            make_transient(p)
            self.dictionary_model.corpus_model.session.merge(p)


class UpdateWordCommand(DictionaryCommand):
    def __init__(
        self, word_id: int, old_word: str, new_word: str, dictionary_model: DictionaryTableModel
    ):
        super().__init__(dictionary_model)
        self.word_id = word_id
        self.word: Word = self.dictionary_model.corpus_model.session.query(Word).get(word_id)
        self.old_word = old_word
        self.new_word = new_word
        self.setText(QtCore.QCoreApplication.translate("UpdateWordCommand", "Update orthography"))

    def _redo(self) -> None:
        self.word.word = self.new_word

    def _undo(self) -> None:
        self.word.word = self.old_word
