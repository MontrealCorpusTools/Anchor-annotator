from __future__ import annotations

import collections
import typing

import pynini.lib
import sqlalchemy
from montreal_forced_aligner.data import WordType
from montreal_forced_aligner.db import File, Pronunciation, Speaker, Utterance, Word
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
            self._redo(self.corpus_model.session)
            self.corpus_model.session.commit()
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
            self._undo(self.corpus_model.session)
            self.corpus_model.session.commit()
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

    def _redo(self, session) -> None:
        self.utterance.begin = self.new_begin
        self.utterance.end = self.new_end
        self.utterance.xvector = None
        self.utterance.ivector = None
        self.utterance.features = None
        session.merge(self.utterance)

    def _undo(self, session) -> None:
        self.utterance.begin = self.old_begin
        self.utterance.end = self.old_end
        self.utterance.xvector = None
        self.utterance.ivector = None
        self.utterance.features = None
        session.merge(self.utterance)

    def update_data(self):
        super().update_data()
        self.corpus_model.changeCommandFired.emit()
        self.corpus_model.update_utterance_table_row(self.utterance)


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

    def _redo(self, session) -> None:
        oovs = set()
        for w in self.new_text.split():
            if not self.corpus_model.dictionary_model.check_word(w, self.speaker_id):
                oovs.add(w)
        self.utterance.text = self.new_text
        self.utterance.normalized_text = self.new_text  # FIXME: Update this
        self.utterance.oovs = " ".join(oovs)
        self.utterance.ignored = not self.new_text
        session.merge(self.utterance)

    def _undo(self, session) -> None:
        oovs = set()
        for w in self.new_text.split():
            if not self.corpus_model.dictionary_model.check_word(w, self.speaker_id):
                oovs.add(w)
        self.utterance.text = self.old_text
        self.utterance.normalized_text = self.old_text  # FIXME: Update this
        self.utterance.oovs = " ".join(oovs)
        self.utterance.ignored = not self.old_text
        session.merge(self.utterance)

    def id(self) -> int:
        return 1

    def mergeWith(self, other: UpdateUtteranceTextCommand) -> bool:
        if other.id() != self.id() or other.utterance.id != self.utterance.id:
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
        for u in self.utterances:
            u.speaker_id = self.new_speaker_id
        session.query(Speaker).filter(
            Speaker.id.in_(self.old_speaker_ids + [self.new_speaker_id])
        ).update({Speaker.modified: True})

    def _undo(self, session) -> None:
        for i, u in enumerate(self.utterances):
            u.speaker_id = self.old_speaker_ids[i]
        session.query(Speaker).filter(
            Speaker.id.in_(self.old_speaker_ids + [self.new_speaker_id])
        ).update({Speaker.modified: True})

    def update_data(self):
        super().update_data()
        self.corpus_model.set_file_modified(self.file_ids)
        self.corpus_model.change_speaker_table_utterances(self.utterances)
        self.file_model.change_speaker_table_utterances(self.utterances)
        self.corpus_model.changeCommandFired.emit()
        self.corpus_model.update_data()
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

    def _redo(self, session) -> None:
        if self.word_id is None:
            self.word_id = session.query(Word.id).filter(Word.word == self.word).first()[0]
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
