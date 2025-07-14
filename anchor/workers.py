from __future__ import annotations

import collections
import csv
import datetime
import logging
import os
import shutil
import sys
import threading
import time
import traceback
import typing
from pathlib import Path
from queue import Empty, Queue
from threading import Lock

import dataclassy
import librosa
import numpy as np
import psycopg2.errors
import scipy
import scipy.signal
import soundfile
import sqlalchemy
import tqdm
import yaml
from _kalpy.feat import compute_pitch
from _kalpy.ivector import Plda, ivector_normalize_length
from _kalpy.matrix import DoubleVector, FloatVector
from kalpy.feat.mfcc import MfccComputer
from kalpy.feat.pitch import PitchComputer
from montreal_forced_aligner import config
from montreal_forced_aligner.alignment import PretrainedAligner
from montreal_forced_aligner.config import IVECTOR_DIMENSION, XVECTOR_DIMENSION
from montreal_forced_aligner.corpus.acoustic_corpus import (
    AcousticCorpus,
    AcousticCorpusWithPronunciations,
)
from montreal_forced_aligner.corpus.classes import FileData
from montreal_forced_aligner.data import (
    DatasetType,
    DistanceMetric,
    Language,
    ManifoldAlgorithm,
    PhoneType,
    TextFileType,
    WordType,
    WorkflowType,
)
from montreal_forced_aligner.db import (
    Corpus,
    CorpusWorkflow,
    Dictionary,
    Dictionary2Job,
    File,
    Phone,
    Job,
    PhoneInterval,
    Pronunciation,
    ReferencePhoneInterval,
    ReferenceWordInterval,
    SoundFile,
    Speaker,
    SpeakerOrdering,
    TextFile,
    Utterance,
    Word,
    WordInterval,
    bulk_update,
    full_load_utterance,
)
from montreal_forced_aligner.diarization.multiprocessing import visualize_clusters
from montreal_forced_aligner.diarization.speaker_diarizer import SpeakerDiarizer
from montreal_forced_aligner.dictionary.multispeaker import MultispeakerDictionary
from montreal_forced_aligner.g2p.generator import PyniniValidator as Generator
from montreal_forced_aligner.helper import mfa_open
from montreal_forced_aligner.models import (
    MODEL_TYPES,
    AcousticModel,
    IvectorExtractorModel,
    LanguageModel,
)
from montreal_forced_aligner.online.alignment import (
    align_utterance_online,
    update_utterance_intervals,
)
from montreal_forced_aligner.online.transcription import (
    transcribe_utterance_online,
    transcribe_utterance_online_speechbrain,
    transcribe_utterance_online_whisper,
)
from montreal_forced_aligner.transcription import Transcriber
from montreal_forced_aligner.transcription.models import MfaFasterWhisperPipeline, load_model
from montreal_forced_aligner.utils import ProgressCallback, inspect_database
from montreal_forced_aligner.vad.models import FOUND_SPEECHBRAIN, MfaVAD
from montreal_forced_aligner.vad.segmenter import TranscriptionSegmenter, VadSegmenter
from montreal_forced_aligner.validation.corpus_validator import PretrainedValidator
from PySide6 import QtCore
from sklearn import discriminant_analysis
from sqlalchemy.orm import joinedload, selectinload, subqueryload

import anchor.db
from anchor.settings import AnchorSettings

if typing.TYPE_CHECKING:
    from anchor.models import CorpusModel, TextFilterQuery

logger = logging.getLogger("anchor")


@dataclassy.dataclass
class SpeakerPlda:
    test_ivectors: typing.List[DoubleVector]
    counts: typing.List[int]
    suggested_ids: typing.List[int]
    suggested_names: typing.List[str]


def load_speaker_plda(
    session: sqlalchemy.orm.Session,
    plda: Plda,
    minimum_count=2,
    ignore_counts=False,
    progress_callback: ProgressCallback = None,
    stopped: typing.Optional[threading.Event] = None,
) -> SpeakerPlda:
    c = session.query(Corpus).first()
    suggested_query = session.query(
        Speaker.id, Speaker.name, c.speaker_ivector_column, Speaker.num_utterances
    ).filter(
        c.speaker_ivector_column != None, Speaker.num_utterances >= minimum_count  # noqa
    )
    if progress_callback is not None:
        progress_callback.update_total(suggested_query.count())
    test_ivectors = []
    suggested_ids = []
    suggested_names = []
    counts = []
    for s_id, s_name, s_ivector, utt_count in suggested_query:
        if progress_callback is not None:
            progress_callback.increment_progress(1)
        if stopped is not None and stopped.is_set():
            return
        kaldi_ivector = DoubleVector()
        kaldi_ivector.from_numpy(s_ivector)
        ivector_normalize_length(kaldi_ivector)
        test_ivector = plda.transform_ivector(kaldi_ivector, utt_count)
        test_ivectors.append(test_ivector)
        suggested_ids.append(s_id)
        suggested_names.append(s_name)
        if ignore_counts:
            utt_count = 1
        counts.append(utt_count)
    return SpeakerPlda(test_ivectors, counts, suggested_ids, suggested_names)


def load_speaker_space(
    session: sqlalchemy.orm.Session,
    minimum_count=4,
    perplexity=30.0,
    metric="cosine",
    progress_callback: ProgressCallback = None,
    stopped: typing.Optional[threading.Event] = None,
) -> SpeakerPlda:
    c = session.query(Corpus).first()
    suggested_query = (
        session.query(Utterance.speaker_id, c.utterance_ivector_column).filter(
            c.utterance_ivector_column != None, Speaker.num_utterances >= minimum_count  # noqa
        )  # noqa
    ).join(Utterance.speaker)
    if progress_callback is not None:
        progress_callback.update_total(suggested_query.count())
    test_ivectors = []
    ids = []
    for s_id, s_ivector in suggested_query:
        if progress_callback is not None:
            progress_callback.increment_progress(1)
        if stopped is not None and stopped.is_set():
            return
        test_ivectors.append(s_ivector)
        ids.append(s_id)
    test_ivectors = np.array(test_ivectors)
    ids = np.array(ids)
    lda = discriminant_analysis.LinearDiscriminantAnalysis(n_components=2).fit(test_ivectors, ids)
    return lda


class WorkerSignals(QtCore.QObject):
    """
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        tuple (exctype, value, traceback.format_exc() )

    result
        object data returned from processing, anything

    progress
        int indicating % progress

    """

    finished = QtCore.Signal()
    error = QtCore.Signal(tuple)
    result = QtCore.Signal(object)
    stream_result = QtCore.Signal(object)
    progress = QtCore.Signal(int, str)
    total = QtCore.Signal(int)

    def __init__(self, name):
        super().__init__()
        self.name = name


class Worker(QtCore.QRunnable):
    """
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    """

    name = "N/A"

    def __init__(self, *args, use_mp=False, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.args = args
        self.kwargs = kwargs
        self.stopped = threading.Event()
        self.settings = AnchorSettings()
        self.signals = WorkerSignals(self.name)
        self.use_mp = use_mp

        # Add the callback to our kwargs
        self.progress_callback = ProgressCallback(
            callback=self.signals.progress.emit, total_callback=self.signals.total.emit
        )
        if not use_mp:
            self.kwargs["progress_callback"] = self.progress_callback
        self.kwargs["stopped"] = self.stopped

    def _run(self):
        pass

    def cancel(self):
        self.stopped.set()

    @QtCore.Slot()
    def run(self):
        """
        Initialise the runner function with passed args, kwargs.
        """

        # Retrieve args/kwargs here; and fire processing using them
        try:
            if self.use_mp:
                queue = Queue()
                kwargs = {}
                kwargs.update(self.kwargs)
                kwargs["queue"] = queue
                p = threading.Thread(target=self._run)
                p.start()
                result = queue.get()
                p.join()
                if isinstance(result, Exception):
                    raise result
            else:
                result = self._run()
        except Exception:
            exctype, value = sys.exc_info()[:2]

            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class ClosestSpeakerThread(threading.Thread):
    def __init__(
        self,
        Session,
        threshold,
        plda: Plda,
        speaker_plda: SpeakerPlda,
        job_q: Queue,
        return_q: Queue,
        done_adding: threading.Event,
        done_processing: threading.Event,
        stopped: threading.Event,
        speaker_id: typing.Optional[int] = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.session = Session
        self.job_q = job_q
        self.return_q = return_q
        self.done_adding = done_adding
        self.done_processing = done_processing
        self.plda = plda
        self.speaker_plda = speaker_plda
        self.speaker_id = speaker_id
        self.threshold = threshold
        self.stopped = stopped

    def run(self):
        with self.session() as session:
            c = session.query(Corpus).first()
            while True:
                try:
                    result = self.job_q.get(timeout=3)
                except Empty:
                    if self.done_adding.is_set():
                        break
                    if self.stopped.is_set():
                        break
                    continue
                if self.stopped.is_set():
                    continue
                if len(result) == 2:  # Merge speaker use case
                    s_id, s_ivector = result
                    if self.plda is None:
                        suggested_query = session.query(
                            Speaker.id,
                        ).order_by(c.speaker_ivector_column.cosine_distance(s_ivector))

                        suggested_query = suggested_query.filter(
                            c.speaker_ivector_column.cosine_distance(s_ivector) <= self.threshold,
                            Speaker.id != s_id,
                        ).limit(1)
                        suggested_id = suggested_query.first()
                        if suggested_id is None:
                            self.return_q.put((s_id, []))
                            continue
                        suggested_id = suggested_id[0]
                    else:
                        kaldi_ivector = DoubleVector()
                        kaldi_ivector.from_numpy(s_ivector.astype(np.float64))
                        kaldi_ivector = self.plda.transform_ivector(kaldi_ivector, 1)
                        index, score = self.plda.classify_utterance(
                            kaldi_ivector,
                            self.speaker_plda.test_ivectors,
                            self.speaker_plda.counts,
                        )
                        suggested_id = self.speaker_plda.suggested_ids[index]
                        if suggested_id == s_id or score < self.threshold:
                            self.return_q.put((s_id, []))
                            continue
                    self.return_q.put((suggested_id, [s_id]))
                else:
                    u_id, s_id, u_ivector, distance = result
                    if self.plda is None:
                        suggested_query = (
                            session.query(
                                Speaker.id,
                            )
                            .filter(
                                c.speaker_ivector_column.cosine_distance(u_ivector)
                                < min(distance - 0.05, self.threshold),
                                # self.threshold,
                                Speaker.id != s_id,
                            )
                            .order_by(c.speaker_ivector_column.cosine_distance(u_ivector))
                            .limit(1)
                        )
                        if self.speaker_id is not None:
                            suggested_query = suggested_query.filter(Speaker.id == self.speaker_id)
                        suggested_id = suggested_query.first()
                        if suggested_id is None:
                            self.return_q.put(None)
                            continue
                        suggested_id = suggested_id[0]
                    else:
                        kaldi_ivector = DoubleVector()
                        kaldi_ivector.from_numpy(u_ivector.astype(np.float64))
                        ivector_normalize_length(kaldi_ivector)
                        kaldi_ivector = self.plda.transform_ivector(kaldi_ivector, 1)
                        index, score = self.plda.classify_utterance(
                            kaldi_ivector,
                            self.speaker_plda.test_ivectors,
                            self.speaker_plda.counts,
                        )
                        suggested_id = self.speaker_plda.suggested_ids[index]
                        if self.speaker_id is not None and suggested_id != self.speaker_id:
                            self.return_q.put(None)
                            continue
                        if suggested_id == s_id or score < self.threshold:
                            self.return_q.put(None)
                            continue
                    self.return_q.put((u_id, suggested_id, s_id))
        self.done_processing.set()


class SpeakerQueryThread(threading.Thread):
    def __init__(
        self,
        Session,
        job_q: Queue,
        done_adding: threading.Event,
        stopped: threading.Event,
        progress_callback,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.session = Session
        self.job_q = job_q
        self.done_adding = done_adding
        self.stopped = stopped
        self.progress_callback = progress_callback

    def run(self):
        with self.session() as session:
            c = session.query(Corpus).first()
            query = (
                session.query(Speaker.id, c.speaker_ivector_column)
                .filter(c.speaker_ivector_column != None, Speaker.num_utterances <= 2)  # noqa
                .order_by(sqlalchemy.func.random())
            )
            query_count = query.count()
            if self.progress_callback is not None:
                self.progress_callback.update_total(query_count)
            for s_id, s_ivector in query:
                if self.stopped is not None and self.stopped.is_set():
                    break
                self.job_q.put((s_id, s_ivector))
        self.done_adding.set()


class MismatchedUtteranceQueryThread(threading.Thread):
    def __init__(
        self,
        Session,
        threshold: float,
        plda: Plda,
        speaker_plda: SpeakerPlda,
        speaker_id: typing.Optional[int],
        job_q: Queue,
        done_adding: threading.Event,
        stopped: threading.Event,
        progress_callback,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.session = Session
        self.plda = plda
        self.threshold = threshold
        self.speaker_plda = speaker_plda
        self.speaker_id = speaker_id
        self.job_q = job_q
        self.done_adding = done_adding
        self.stopped = stopped
        self.progress_callback = progress_callback

    def run(self):
        with self.session() as session:
            c = session.query(Corpus).first()
            if self.plda is None:
                query = (
                    session.query(
                        Utterance.id,
                        Speaker.id,
                        c.utterance_ivector_column,
                        c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column),
                    ).join(Utterance.speaker)
                    # .filter(c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column) > 0.5)
                    # .order_by(c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column).desc())
                )
                if False and self.threshold is not None:
                    query = query.filter(
                        sqlalchemy.or_(
                            c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column)
                            > self.threshold,
                            Speaker.num_utterances < 3,
                        )
                    )
                query_count = query.count()
                if self.progress_callback is not None:
                    self.progress_callback.update_total(query_count)
                for u_id, s_id, u_ivector, distance in query:
                    if self.stopped is not None and self.stopped.is_set():
                        break
                    self.job_q.put((u_id, s_id, u_ivector, distance))
            else:
                query = (
                    session.query(Utterance.id, Speaker.id, c.utterance_ivector_column)
                    .join(Utterance.speaker)
                    .filter(Speaker.id.in_(self.speaker_plda.suggested_ids))
                    .filter(
                        c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column) > 0.4
                    )
                    .order_by(
                        c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column).desc()
                    )
                )
                query_count = query.count()
                if self.progress_callback is not None:
                    self.progress_callback.update_total(query_count)
                for u_id, s_id, u_ivector in query:
                    if self.stopped is not None and self.stopped.is_set():
                        break
                    index = self.speaker_plda.suggested_ids.index(s_id)
                    s_ivector = self.speaker_plda.test_ivectors[index]
                    utt_count = self.speaker_plda.counts[index]
                    kaldi_ivector = DoubleVector()
                    kaldi_ivector.from_numpy(u_ivector)
                    ivector_normalize_length(kaldi_ivector)
                    kaldi_ivector = self.plda.transform_ivector(kaldi_ivector, 1)
                    score = self.plda.LogLikelihoodRatio(s_ivector, utt_count, kaldi_ivector)
                    if score < 0:
                        self.job_q.put((u_id, s_id, u_ivector, score))
        self.done_adding.set()


class ClosestUtteranceThread(threading.Thread):
    def __init__(
        self,
        Session,
        threshold,
        plda,
        job_q: Queue,
        return_q: Queue,
        done_adding: threading.Event,
        done_processing: threading.Event,
        stopped: threading.Event,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.session = Session
        self.job_q = job_q
        self.return_q = return_q
        self.done_adding = done_adding
        self.done_processing = done_processing
        self.threshold = threshold
        self.plda = plda
        self.stopped = stopped

    def run(self):
        deleted = set()
        with self.session() as session:
            c = session.query(Corpus).first()
            while True:
                try:
                    u_id, u_text, u_ivector, file_name = self.job_q.get(timeout=3)
                except Empty:
                    if self.done_adding.is_set():
                        break
                    if self.stopped.is_set():
                        break
                    continue
                if self.stopped.is_set():
                    continue
                if file_name in deleted:
                    continue
                duplicates = (
                    session.query(Utterance.text, File.name)
                    .join(Utterance.file)
                    .filter(
                        Utterance.id < u_id,
                        Utterance.text == u_text,
                        c.utterance_ivector_column.cosine_distance(u_ivector) <= self.threshold,
                    )
                    .all()
                )
                deleted.update([x[1] for x in duplicates])
                self.return_q.put((u_id, u_text, file_name, duplicates))
        self.done_processing.set()


class UtteranceQueryThread(threading.Thread):
    def __init__(
        self,
        Session,
        plda: Plda,
        job_q: Queue,
        done_adding: threading.Event,
        stopped: threading.Event,
        progress_callback,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.session = Session
        self.plda = plda
        self.job_q = job_q
        self.done_adding = done_adding
        self.stopped = stopped
        self.progress_callback = progress_callback

    def run(self):
        with self.session() as session:
            c = session.query(Corpus).first()
            query = (
                session.query(Utterance.id, Utterance.text, c.utterance_ivector_column, File.name)
                .join(Utterance.file)
                .filter(utterance_ivector_column != None)  # noqa
                .order_by(Utterance.id.desc())
            )
            query_count = query.count()
            if self.progress_callback is not None:
                self.progress_callback.update_total(query_count)
            for row in query:
                if self.stopped is not None and self.stopped.is_set():
                    break
                self.job_q.put(row)
        self.done_adding.set()


class ExportFilesWorker(Worker):
    def __init__(self, session: sqlalchemy.orm.scoped_session, use_mp=False):
        super().__init__(use_mp=use_mp)
        self.session = session

    def _run(self):
        with self.session() as session:
            try:
                mappings = []
                output_directory = session.query(Corpus.path).first()[0]
                files = (
                    session.query(File)
                    .options(
                        subqueryload(File.utterances),
                        subqueryload(File.speakers),
                        joinedload(File.sound_file, innerjoin=True).load_only(SoundFile.duration),
                        joinedload(File.text_file, innerjoin=False).load_only(TextFile.file_type),
                    )
                    .filter(File.modified == True)  # noqa
                )

                if self.progress_callback is not None:
                    self.progress_callback.update_total(files.count())
                for f in files:
                    if not f.utterances:
                        logger.debug(f"Skipping {f.name} for no utterances")
                        continue
                    if self.stopped.is_set():
                        session.rollback()
                        break
                    try:
                        f.save(
                            output_directory,
                            overwrite=True,
                            output_format=TextFileType.TEXTGRID.value,
                        )
                    except Exception:
                        logger.error(f"Error writing {f.name}")
                        raise
                    mappings.append({"id": f.id, "modified": False})
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)
                session.commit()
                while True:
                    try:
                        with session.begin_nested():
                            session.bulk_update_mappings(File, mappings)
                        break
                    except psycopg2.errors.DeadlockDetected:
                        pass
                session.commit()
            except Exception:
                session.rollback()
                raise


class ReplaceAllWorker(Worker):
    def __init__(self, session, search_query, replacement_string, use_mp=False):
        super().__init__(use_mp=use_mp)
        self.session = session
        self.search_query = search_query
        self.replacement_string = replacement_string

    def _run(self):
        with self.session() as session:
            try:
                old_texts = {}
                new_texts = {}

                filter_regex = self.search_query.generate_expression(posix=True)
                text_column = Utterance.text

                columns = [Utterance.id, Utterance.text]
                utterances = session.query(*columns)

                utterances = utterances.filter(text_column.op("~")(filter_regex))
                if self.progress_callback is not None:
                    self.progress_callback.update_total(utterances.count())
                for u_id, text in utterances:
                    if self.stopped is not None and self.stopped.is_set():
                        session.rollback()
                        return
                    old_texts[u_id] = text

                utterance_table = Utterance.__table__
                utterance_statement = sqlalchemy.update(utterance_table)

                utterance_statement = utterance_statement.where(
                    utterance_table.c.text.op("~")(filter_regex)
                )
                utterance_statement = utterance_statement.values(
                    text=sqlalchemy.func.regexp_replace(
                        utterance_table.c.text, filter_regex, self.replacement_string, "g"
                    ),
                    normalized_text=sqlalchemy.func.regexp_replace(
                        utterance_table.c.normalized_text,
                        filter_regex,
                        self.replacement_string,
                        "g",
                    ),
                ).execution_options(synchronize_session="fetch")
                utterance_statement = utterance_statement.returning(
                    utterance_table.c.id, utterance_table.c.file_id, utterance_table.c.text
                )
                while True:
                    try:
                        with session.begin_nested():
                            results = session.execute(utterance_statement)
                            file_ids = []
                            for u_id, f_id, text in results:
                                if self.progress_callback is not None:
                                    self.progress_callback.increment_progress(1)
                                new_texts[u_id] = text
                                file_ids.append(f_id)
                            if file_ids:
                                session.query(File).filter(File.id.in_(file_ids)).update(
                                    {
                                        File.modified: True,
                                    }
                                )
                        break
                    except psycopg2.errors.DeadlockDetected:
                        pass
                if self.stopped is not None and self.stopped.is_set():
                    session.rollback()
                    return
                session.commit()
            except Exception:
                session.rollback()
                raise
        return self.search_query.generate_expression(), old_texts, new_texts


class ChangeSpeakerWorker(Worker):
    def __init__(self, session, utterance_ids, new_speaker_id, old_speaker_id, use_mp=False):
        super().__init__(
            use_mp=use_mp,
        )
        self.session = session
        self.utterance_ids = utterance_ids
        self.new_speaker_id = new_speaker_id
        self.old_speaker_id = old_speaker_id

    def _run(self):
        per_utterance = isinstance(self.utterance_ids[0], list)
        with self.session() as session:
            try:
                if (not per_utterance and self.new_speaker_id <= 0) or (
                    per_utterance and any(x[-1] <= 0 for x in self.utterance_ids)
                ):
                    new_speaker_id = session.query(sqlalchemy.func.max(Speaker.id)).scalar() + 1
                    speaker = session.query(Speaker).get(self.old_speaker_id)
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
                            id=new_speaker_id,
                            name=speaker_name,
                            dictionary_id=speaker.dictionary_id,
                        )
                    )
                    session.flush()
                else:
                    new_speaker_id = self.new_speaker_id
                if not per_utterance:
                    utterance_ids = self.utterance_ids
                    if not utterance_ids:
                        query = session.query(Utterance.id).filter(
                            Utterance.speaker_id == self.old_speaker_id
                        )
                        utterance_ids.extend(x for x, in query)
                    mapping = [{"id": x, "speaker_id": new_speaker_id} for x in utterance_ids]
                    return_data = [[x, self.old_speaker_id, new_speaker_id] for x in utterance_ids]
                    speaker_ids = [new_speaker_id, self.old_speaker_id]
                else:
                    utterance_ids = [int(x[0]) for x in self.utterance_ids]
                    mapping = []
                    return_data = []
                    speaker_ids = set()
                    for u_id, s_id, new_s_id in self.utterance_ids:
                        if new_s_id <= 0:
                            new_s_id = new_speaker_id
                        mapping.append({"id": u_id, "speaker_id": new_s_id})
                        speaker_ids.add(s_id)
                        speaker_ids.add(new_s_id)
                        return_data.append([u_id, s_id, new_s_id])
                file_ids = [
                    x[0]
                    for x in session.query(File.id)
                    .join(File.utterances)
                    .filter(Utterance.id.in_(utterance_ids))
                    .distinct()
                ]
                bulk_update(session, Utterance, mapping)
                session.query(Speaker).filter(Speaker.id.in_(speaker_ids)).update(
                    {Speaker.modified: True}
                )
                session.query(File).filter(File.id.in_(file_ids)).update({File.modified: True})

                if self.stopped is not None and self.stopped.is_set():
                    session.rollback()
                    return
                session.commit()
            except Exception as e:
                logger.warning(e)
                session.rollback()
                raise
        return return_data


class BreakUpSpeakerWorker(Worker):
    def __init__(self, session, utterance_ids, old_speaker_id, use_mp=False):
        super().__init__(use_mp=use_mp)
        self.session = session
        self.utterance_ids = utterance_ids
        self.old_speaker_id = old_speaker_id

    def _run(self):
        with self.session() as session:
            try:
                if not self.utterance_ids:
                    query = session.query(Utterance.id).filter(
                        Utterance.speaker_id == self.old_speaker_id
                    )
                    self.utterance_ids.extend(x for x, in query)
                file_ids = [
                    x[0]
                    for x in session.query(File.id)
                    .join(File.utterances)
                    .filter(Utterance.id.in_(self.utterance_ids))
                    .distinct()
                ]
                mapping = []
                new_speakers = []
                new_speaker_id = session.query(sqlalchemy.func.max(Speaker.id)).scalar() + 1
                speaker = session.query(Speaker).get(self.old_speaker_id)
                original_name = speaker.name
                index = 1
                speaker_names = {
                    x[0]
                    for x in session.query(Speaker.name).filter(
                        Speaker.name.like(f"{original_name}%")
                    )
                }
                for x in self.utterance_ids:
                    while True:
                        speaker_name = f"{original_name}_{index}"
                        if speaker_name not in speaker_names:
                            break
                        index += 1
                    speaker_names.add(speaker_name)
                    new_speakers.append(
                        {
                            "id": new_speaker_id,
                            "name": speaker_name,
                            "modified": True,
                            "dictionary_id": speaker.dictionary_id,
                        }
                    )

                    mapping.append({"id": x, "speaker_id": new_speaker_id})
                    new_speaker_id += 1
                session.bulk_insert_mappings(Speaker, new_speakers)
                session.flush()
                bulk_update(session, Utterance, mapping)
                session.query(Speaker).filter(Speaker.id == self.old_speaker_id).update(
                    {Speaker.modified: True}
                )
                session.query(File).filter(File.id.in_(file_ids)).update({File.modified: True})

                if self.stopped is not None and self.stopped.is_set():
                    session.rollback()
                    return
                session.commit()
            except Exception as e:
                logger.warning(e)
                session.rollback()
                raise
        return self.utterance_ids


class RecalculateSpeakerWorker(Worker):
    def __init__(self, session, plda, speaker_plda, use_mp=False):
        super().__init__(use_mp=use_mp)
        self.session = session
        self.plda = plda
        self.speaker_plda = speaker_plda

    def _run(self):
        with self.session() as session:
            try:
                modified_speakers = [
                    x for x, in session.query(Speaker.id).filter(Speaker.modified == True)  # noqa
                ]
                if modified_speakers:
                    modified_files = [
                        x
                        for x, in session.query(File.id)
                        .join(Utterance.file)
                        .filter(
                            File.modified == True,  # noqa
                            Utterance.speaker_id.in_(modified_speakers),
                        )
                        .distinct()
                    ]
                    if self.progress_callback is not None:
                        self.progress_callback.update_total(
                            len(modified_speakers) + len(modified_files)
                        )
                    session.execute(
                        sqlalchemy.delete(SpeakerOrdering).where(
                            SpeakerOrdering.c.file_id.in_(modified_files)
                        )
                    )
                    session.commit()
                    insert_mapping = []
                    for file_id in modified_files:
                        if self.stopped is not None and self.stopped.is_set():
                            session.rollback()
                            return
                        if self.progress_callback is not None:
                            self.progress_callback.increment_progress(1)
                        speaker_ids = [
                            x
                            for x, in session.query(Utterance.speaker_id)
                            .filter(Utterance.file_id == file_id)
                            .distinct()
                        ]
                        for s in speaker_ids:
                            insert_mapping.append(
                                {"speaker_id": s, "file_id": file_id, "index": 1}
                            )
                    if insert_mapping:
                        session.execute(sqlalchemy.insert(SpeakerOrdering).values(insert_mapping))
                    session.flush()
                c = session.query(Corpus).first()
                ivector_column = "ivector"
                if c.xvectors_loaded:
                    ivector_column = "xvector"

                update_mapping = []
                for s_id in modified_speakers:
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)
                    if self.stopped is not None and self.stopped.is_set():
                        session.rollback()
                        return
                    old_ivectors = np.array(
                        [
                            x[0]
                            for x in session.query(c.utterance_ivector_column).filter(
                                Utterance.speaker_id == s_id,
                                c.utterance_ivector_column != None,  # noqa
                            )
                        ]
                    )
                    old_speaker_ivector = None
                    if old_ivectors.shape[0] > 0:
                        old_speaker_ivector = np.mean(old_ivectors, axis=0)
                    update_mapping.append(
                        {
                            "id": s_id,
                            "modified": False,
                            "num_utterances": old_ivectors.shape[0],
                            ivector_column: old_speaker_ivector,
                        }
                    )
                    if self.speaker_plda is not None and old_speaker_ivector is not None:
                        kaldi_speaker_ivector = DoubleVector()
                        kaldi_speaker_ivector.from_numpy(old_speaker_ivector)
                        ivector_normalize_length(kaldi_speaker_ivector)
                        kaldi_speaker_ivector = self.plda.transform_ivector(
                            kaldi_speaker_ivector, old_ivectors.shape[0]
                        )
                        if s_id in self.speaker_plda.suggested_ids:
                            index = self.speaker_plda.suggested_ids.index(s_id)
                            self.speaker_plda.test_ivectors[index] = kaldi_speaker_ivector
                            self.speaker_plda.counts[index] = old_ivectors.shape[0]
                        else:
                            self.speaker_plda.suggested_ids.append(s_id)
                            suggested_name = (
                                session.query(Speaker.name).filter(Speaker.id == s_id).first()[0]
                            )
                            self.speaker_plda.suggested_names.append(suggested_name)
                            self.speaker_plda.test_ivectors.append(kaldi_speaker_ivector)
                            self.speaker_plda.counts.append(old_ivectors.shape[0])
                    elif old_speaker_ivector is not None:
                        if (
                            self.speaker_plda is not None
                            and s_id in self.speaker_plda.suggested_ids
                        ):
                            index = self.speaker_plda.suggested_ids.index(s_id)
                            self.speaker_plda.suggested_ids.pop(index)
                            self.speaker_plda.test_ivectors.pop(index)
                            self.speaker_plda.counts.pop(index)
                            self.speaker_plda.suggested_names.pop(index)

                if update_mapping:
                    bulk_update(session, Speaker, update_mapping)
                session.commit()
                if self.speaker_plda is None and self.plda is not None:
                    self.speaker_plda = load_speaker_plda(
                        session,
                        self.plda,
                        progress_callback=self.progress_callback,
                        stopped=self.stopped,
                    )
                return self.speaker_plda
            except Exception:
                session.rollback()
                raise


class QueryUtterancesWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session

    def _run(self):
        with self.session() as session:
            c = session.query(Corpus).first()
            count_only = self.kwargs.get("count", False)
            has_ivectors = self.kwargs.get("has_ivectors", False)
            filter_nulls = self.kwargs.get("filter_nulls", [])
            columns = [
                Utterance.id,
                Utterance.file_id,
                Utterance.speaker_id,
                Utterance.oovs,
                File.name,
                Speaker.name,
                Utterance.begin,
                Utterance.end,
                Utterance.duration,
                Utterance.text,
                Utterance.alignment_log_likelihood,
                Utterance.speech_log_likelihood,
                Utterance.duration_deviation,
                Utterance.snr,
                Utterance.phone_error_rate,
                Utterance.alignment_score,
                Utterance.transcription_text,
                Utterance.word_error_rate,
            ]
            if has_ivectors and c.utterance_ivector_column is not None:
                columns.append(
                    c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column)
                )
                columns.append(Utterance.diarization_variance)
            speaker_filter = self.kwargs.get("speaker_filter", None)
            file_filter = self.kwargs.get("file_filter", None)
            text_filter: TextFilterQuery = self.kwargs.get("text_filter", None)
            sort_index = self.kwargs.get("sort_index", None)
            utterances = session.query(*columns).join(Utterance.speaker).join(Utterance.file)

            if self.kwargs.get("oovs_only", False):
                utterances = utterances.filter(Utterance.oovs != "")
            if speaker_filter is not None:
                if isinstance(speaker_filter, int):
                    utterances = utterances.filter(Utterance.speaker_id == speaker_filter)
                else:
                    utterances = utterances.filter(Speaker.name == speaker_filter)
            if file_filter is not None:
                if isinstance(file_filter, int):
                    utterances = utterances.filter(Utterance.file_id == file_filter)
                else:
                    utterances = utterances.filter(File.name == file_filter)
            if text_filter is not None:
                if self.kwargs.get("oovs_only", False):
                    text_column = Utterance.oovs
                else:
                    text_column = Utterance.text
                filter_regex = text_filter.generate_expression(posix=True)
                utterances = utterances.filter(text_column.op("~")(filter_regex))
            for i, null_check in enumerate(filter_nulls):
                if null_check:
                    column = columns[i + 3]
                    utterances = utterances.filter(column != None)  # noqa
            if count_only:
                try:
                    return utterances.count()
                except psycopg2.errors.InvalidRegularExpression:
                    return 0
            if self.progress_callback is not None:
                self.progress_callback.update_total(self.kwargs.get("limit", 100))
            if sort_index is not None and sort_index + 3 <= len(columns) - 1:
                sort_column = columns[sort_index + 3]
                if self.kwargs.get("sort_desc", False):
                    sort_column = sort_column.desc()
                utterances = utterances.order_by(sort_column, Utterance.id)
            else:
                utterances = utterances.order_by(File.name, Utterance.begin)
            utterances = utterances.limit(self.kwargs.get("limit", 100)).offset(
                self.kwargs.get("current_offset", 0)
            )
            data = []
            indices = []
            file_indices = []
            speaker_indices = []
            reversed_indices = {}
            try:
                for i, u in enumerate(utterances):
                    if self.stopped is not None and self.stopped.is_set():
                        return
                    data.append(list(u[3:]))
                    indices.append(u[0])
                    file_indices.append(u[1])
                    speaker_indices.append(u[2])
                    reversed_indices[u[0]] = i
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)

            except psycopg2.errors.InvalidRegularExpression:
                pass
        return data, indices, file_indices, speaker_indices, reversed_indices


class QuerySpeakersWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session

    def _run(self):
        with self.session() as session:
            c = session.query(Corpus).first()
            text_filter = self.kwargs.get("text_filter", None)
            speaker_filter = self.kwargs.get("speaker_filter", None)
            sort_index = self.kwargs.get("sort_index", None)
            if self.kwargs.get("count", False):
                speakers = session.query(Speaker.name)
                if text_filter is not None:
                    filter_regex = text_filter.generate_expression(posix=True)
                    text_column = Speaker.name
                    speakers = speakers.filter(text_column.op("~")(filter_regex))
                return speakers.count()

            if self.progress_callback is not None:
                self.progress_callback.update_total(self.kwargs.get("limit", 100))
            columns = [
                Speaker.id,
                Speaker.name,
                Speaker.num_utterances,
                Speaker.dictionary_id,
            ]
            if not speaker_filter:
                columns.append(
                    sqlalchemy.func.max(
                        c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column)
                    )
                )
            elif isinstance(speaker_filter, int):
                speaker_ivector = (
                    session.query(c.speaker_ivector_column)
                    .filter(Speaker.id == speaker_filter)
                    .first()[0]
                )
                columns.append(c.speaker_ivector_column.cosine_distance(speaker_ivector))
            else:
                speaker_ivector = speaker_filter
                columns.append(c.speaker_ivector_column.cosine_distance(speaker_ivector))

            speakers = (
                session.query(*columns)
                .join(Speaker.utterances)
                .group_by(Speaker.id, Speaker.name, Speaker.dictionary_id)
            )
            if not c.ivectors_calculated and not c.xvectors_loaded:
                if speaker_filter is not None:
                    if isinstance(speaker_filter, int):
                        speakers = speakers.filter(Speaker.id == speaker_filter)
                    else:
                        speakers = speakers.filter(Speaker.name == speaker_filter)
            if text_filter is not None and text_filter.text:
                filter_regex = text_filter.generate_expression(posix=True)
                text_column = columns[1]
                if not text_filter.case_sensitive:
                    text_column = sqlalchemy.func.lower(text_column)
                speakers = speakers.filter(text_column.op("~")(filter_regex))
            if sort_index is not None:
                sort_column = columns[sort_index + 1]
                if self.kwargs.get("sort_desc", False):
                    sort_column = sort_column.desc()
                speakers = speakers.order_by(sort_column)
            speakers = speakers.limit(self.kwargs.get("limit", 100)).offset(
                self.kwargs.get("current_offset", 0)
            )
            data = []
            indices = []
            for w in speakers:
                if self.stopped is not None and self.stopped.is_set():
                    return
                d = list(w)
                indices.append(d.pop(0))
                data.append(d)
                if self.progress_callback is not None:
                    self.progress_callback.increment_progress(1)
        return data, indices


class ClusterSpeakerUtterancesWorker(Worker):
    def __init__(
        self,
        session,
        use_mp=False,
        speaker_ids: typing.List[int] = None,
        distance_threshold: float = None,
        limit: int = 500,
        **kwargs,
    ):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session
        self.speaker_ids = speaker_ids
        self.distance_threshold = distance_threshold
        self.limit = limit

    def _run(self):
        with self.session() as session:
            c = session.query(Corpus).first()
            speaker_name, ivector, utt_count = (
                session.query(Speaker.name, c.speaker_ivector_column, Speaker.num_utterances)
                .filter(
                    Speaker.id == self.speaker_ids[0], c.utterance_ivector_column != None  # noqa
                )
                .first()
            )
            if utt_count < 1:
                return None
            query = (
                session.query(
                    Utterance.speaker_id,
                    c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column),
                )
                .join(Utterance.speaker)
                .filter(c.utterance_ivector_column != None)  # noqa
            )
            query = query.filter(Utterance.speaker_id.in_(self.speaker_ids))
            query = query.order_by(Utterance.id)
            additional_data = (
                session.query(
                    Utterance.speaker_id,
                    c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column),
                )
                .join(Utterance.speaker)
                .filter(
                    c.utterance_ivector_column != None,  # noqa
                )
                .filter(~Utterance.speaker_id.in_(self.speaker_ids))
            )
            if self.distance_threshold:
                additional_data = additional_data.filter(
                    c.utterance_ivector_column.cosine_distance(ivector) <= self.distance_threshold
                )
            additional_data = additional_data.order_by(
                c.utterance_ivector_column.cosine_distance(ivector)
            ).limit(min(query.count(), self.limit))
            cluster_ids = []
            distances = []
            for speaker_id, distance in query:
                cluster_ids.append(speaker_id)
                distances.append(distance)
            for speaker_id, distance in additional_data:
                cluster_ids.append(speaker_id)
                distances.append(distance)
            cluster_ids = np.array(cluster_ids)
            distances = np.array(distances)
            distances = (distances - distances.min()) / distances.max()
        return self.speaker_ids, cluster_ids, distances


class CalculateSpeakerIvectorsWorker(Worker):
    def __init__(
        self,
        session,
        use_mp=False,
        speaker_ids: typing.List[int] = None,
        limit: int = 500,
        distance_threshold: float = None,
        **kwargs,
    ):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session
        self.speaker_ids = speaker_ids
        self.distance_threshold = distance_threshold
        self.limit = limit

    def _run(self):
        if self.progress_callback is not None:
            self.progress_callback.update_total(3)
        with self.session() as session:
            c = session.query(Corpus).first()
            speaker_name, ivector, utt_count = (
                session.query(Speaker.name, c.speaker_ivector_column, Speaker.num_utterances)
                .filter(
                    Speaker.id == self.speaker_ids[0], c.utterance_ivector_column != None  # noqa
                )
                .first()
            )
            if utt_count < 1:
                return None
            utterances = session.query(
                Utterance.id,
                Utterance.speaker_id,
                c.utterance_ivector_column,
            ).filter(
                c.utterance_ivector_column != None  # noqa
            )
            utterances = utterances.filter(Utterance.speaker_id.in_(self.speaker_ids))
            utterances = utterances.order_by(Utterance.id)
            additional_data = (
                session.query(Utterance.id, Utterance.speaker_id, c.utterance_ivector_column)
                .filter(
                    c.utterance_ivector_column != None,  # noqa
                )
                .filter(~Utterance.speaker_id.in_(self.speaker_ids))
            )
            if self.distance_threshold:
                additional_data = additional_data.filter(
                    c.utterance_ivector_column.cosine_distance(ivector) <= self.distance_threshold
                )
            additional_data = additional_data.order_by(
                c.utterance_ivector_column.cosine_distance(ivector)
            ).limit(min(utterances.count(), self.limit))

            ivectors = []
            utterance_ids = []
            utt2spk = {}
            for i, (u_id, s_id, u_ivector) in enumerate(utterances):
                ivectors.append(u_ivector)
                utterance_ids.append(u_id)
                utt2spk[u_id] = s_id
            for i, (u_id, s_id, u_ivector) in enumerate(additional_data):
                ivectors.append(u_ivector)
                utterance_ids.append(u_id)
                utt2spk[u_id] = s_id
        return self.speaker_ids, np.array(utterance_ids), utt2spk, np.array(ivectors)


class SpeakerMdsWorker(Worker):
    def __init__(
        self,
        session,
        use_mp=False,
        speaker_ids: typing.List[int] = None,
        limit: int = 500,
        plda: Plda = None,
        perplexity: float = 30.0,
        distance_threshold: float = None,
        speaker_space: discriminant_analysis.LinearDiscriminantAnalysis = None,
        metric_type: str = "cosine",
        **kwargs,
    ):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session
        self.speaker_ids = speaker_ids
        self.distance_threshold = distance_threshold
        self.limit = limit
        self.plda = plda
        self.perplexity = perplexity
        self.speaker_space = speaker_space
        self.metric_type = metric_type
        if isinstance(self.metric_type, str):
            self.metric_type = DistanceMetric[self.metric_type]
        if self.plda is None:
            self.metric_type = DistanceMetric.cosine

    def _run(self):
        with self.session() as session:
            c = session.query(Corpus).first()

            if c.xvectors_loaded:
                dim = XVECTOR_DIMENSION
            else:
                dim = IVECTOR_DIMENSION
            speaker_name, ivector, utt_count = (
                session.query(Speaker.name, c.speaker_ivector_column, Speaker.num_utterances)
                .filter(
                    Speaker.id == self.speaker_ids[0], c.utterance_ivector_column != None  # noqa
                )
                .first()
            )
            query = (
                session.query(c.utterance_ivector_column)
                .filter(
                    Utterance.speaker_id.in_(self.speaker_ids),
                    c.utterance_ivector_column != None,  # noqa
                )
                .order_by(Utterance.id)
            )
            num_utterances = query.count()
            if num_utterances < 1:
                return None
            additional_data = (
                session.query(c.utterance_ivector_column)
                .filter(
                    c.utterance_ivector_column != None,  # noqa
                )
                .filter(~Utterance.speaker_id.in_(self.speaker_ids))
            )
            if self.distance_threshold:
                additional_data = additional_data.filter(
                    c.utterance_ivector_column.cosine_distance(ivector) <= self.distance_threshold
                )
            additional_data = additional_data.order_by(
                c.utterance_ivector_column.cosine_distance(ivector)
            ).limit(min(query.count(), self.limit))
            random_data = (
                session.query(c.utterance_ivector_column)
                .filter(
                    c.utterance_ivector_column != None,  # noqa
                )
                .filter(~Utterance.speaker_id.in_(self.speaker_ids))
                .order_by(c.utterance_ivector_column.cosine_distance(ivector).desc())
                .limit(self.limit)
            )
            additional_data_count = additional_data.count()
            ivectors = np.empty(
                (num_utterances + additional_data_count + random_data.count(), dim),
                dtype="float32",
            )
            for i, (ivector,) in enumerate(query):
                ivectors[i, :] = ivector
            for i, (ivector,) in enumerate(additional_data):
                ivectors[i + num_utterances, :] = ivector
            for i, (ivector,) in enumerate(random_data):
                ivectors[i + num_utterances + additional_data_count, :] = ivector
            if self.metric_type is DistanceMetric.plda:
                counts = np.ones(
                    (num_utterances + additional_data.count() + self.limit,), dtype="int32"
                )
                ivectors = np.array(self.plda.transform_ivectors(ivectors, counts))
                self.metric_type = DistanceMetric.cosine
            if ivectors.shape[0] <= self.perplexity:
                self.perplexity = ivectors.shape[0] - 1
            if self.speaker_space is not None:
                points = self.speaker_space.transform(ivectors)
            else:
                points = visualize_clusters(
                    ivectors,
                    ManifoldAlgorithm.tsne,
                    self.metric_type,
                    self.perplexity,
                    self.plda,
                    quick=False,
                )
            points = points[: -random_data.count(), :]
        return self.speaker_ids, points


class AlignmentAnalysisWorker(Worker):
    def __init__(
        self,
        session,
        use_mp=False,
        speaker_id: int = None,
        phone_id: int = None,
        word_filter: TextFilterQuery = None,
        less_than: float = None,
        greater_than: float = None,
        measure: str = "duration",
        exclude_manual: bool = False,
        word_mode: bool = False,
        relative_duration: bool = False,
        limit: int = 100,
        current_offset: int = 0,
        sort_index: int = None,
        sort_desc: bool = False,
        **kwargs,
    ):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session
        self.speaker_id = speaker_id
        self.phone_id = phone_id
        self.less_than = less_than
        self.greater_than = greater_than
        self.measure = measure
        self.word_filter = word_filter
        self.exclude_manual = exclude_manual
        self.word_mode = word_mode
        self.relative_duration = relative_duration

        self.limit = limit
        self.current_offset = current_offset
        self.sort_index = sort_index
        self.sort_desc = sort_desc

    def _run(self):
        count_only = self.kwargs.get("count", False)
        if not count_only and self.progress_callback is not None:
            self.progress_callback.update_total(self.limit)

        with self.session() as session:
            indices = []
            file_indices = []
            speaker_indices = []
            utterance_ids = []
            reversed_indices = {}
            data = []
            if not self.word_mode:
                if not count_only and self.relative_duration:
                    duration_column = sqlalchemy.sql.label(
                        "duration",
                        (PhoneInterval.duration - Phone.mean_duration) / Phone.sd_duration,
                    )
                else:
                    duration_column = PhoneInterval.duration
                goodness_column = PhoneInterval.phone_goodness
                columns = [
                    PhoneInterval.id,
                    PhoneInterval.utterance_id,
                    Utterance.file_id,
                    Utterance.speaker_id,
                    Utterance.begin,
                    Utterance.end,
                    File.name,
                    Speaker.name,
                    Phone.phone,
                    duration_column,
                    goodness_column,
                    Word.word,
                ]
                query = (
                    session.query(*columns)
                    .join(PhoneInterval.utterance)
                    .join(PhoneInterval.phone)
                    .join(Utterance.speaker)
                    .join(Utterance.file)
                    .join(PhoneInterval.word_interval)
                    .join(WordInterval.word)
                )
            else:
                if not count_only and self.relative_duration:
                    duration_column = sqlalchemy.sql.label(
                        "duration",
                        sqlalchemy.func.sum(PhoneInterval.duration)
                        / sqlalchemy.func.sum(Phone.mean_duration),
                    )
                else:
                    duration_column = sqlalchemy.func.avg(PhoneInterval.duration)
                goodness_column = sqlalchemy.func.min(PhoneInterval.phone_goodness)
                columns = [
                    WordInterval.id,
                    WordInterval.utterance_id,
                    Utterance.file_id,
                    Utterance.speaker_id,
                    Utterance.begin,
                    Utterance.end,
                    File.name,
                    Speaker.name,
                    sqlalchemy.func.string_agg(
                        Phone.phone,
                        sqlalchemy.dialects.postgresql.aggregate_order_by(
                            sqlalchemy.literal_column("' '"), PhoneInterval.begin
                        ),
                    ),
                    duration_column,
                    goodness_column,
                    Word.word,
                ]
                query = (
                    session.query(*columns)
                    .join(PhoneInterval.utterance)
                    .join(PhoneInterval.phone)
                    .join(Utterance.speaker)
                    .join(Utterance.file)
                    .join(PhoneInterval.word_interval)
                    .join(WordInterval.word)
                    .group_by(
                        WordInterval.id,
                        Utterance.id,
                        Utterance.file_id,
                        Utterance.speaker_id,
                        Utterance.begin,
                        Utterance.end,
                        File.name,
                        Speaker.name,
                        Word.word,
                    )
                )

            if self.speaker_id is not None:
                if isinstance(self.speaker_id, int):
                    query = query.filter(Utterance.speaker_id == self.speaker_id)
                else:
                    query = query.filter(Speaker.name == self.speaker_id)
            if self.phone_id is not None:
                if isinstance(self.phone_id, int):
                    query = query.filter(PhoneInterval.phone_id == self.phone_id)
                else:
                    query = query.filter(Phone.phone == self.phone_id)
            else:
                query = query.filter(Phone.phone_type.in_([PhoneType.non_silence]))
            if self.exclude_manual:
                query = query.filter(Utterance.manual_alignments == False)  # noqa
            if self.measure == "duration":
                measure_column = duration_column
            else:
                measure_column = goodness_column
            if self.less_than is not None or self.greater_than is not None:
                if self.less_than is not None:
                    query = query.filter(measure_column < self.less_than)
                if self.greater_than is not None:
                    query = query.filter(measure_column > self.greater_than)
            if self.word_filter is not None and self.word_filter.text:
                filter_regex = self.word_filter.generate_expression(posix=True)
                query = query.filter(Word.word.op("~")(filter_regex))
            if count_only:
                try:
                    return query.count()
                except psycopg2.errors.InvalidRegularExpression:
                    return 0
            if self.sort_index is not None and self.sort_index + 6 <= len(columns) - 1:
                sort_column = columns[self.sort_index + 6]
                if self.sort_desc:
                    sort_column = sort_column.desc()
                query = query.order_by(sort_column, Utterance.id, PhoneInterval.begin)
            else:
                if self.word_mode:
                    query = query.order_by(duration_column, Utterance.id, WordInterval.id)
                else:
                    query = query.order_by(duration_column, Utterance.id, PhoneInterval.begin)
            query = query.limit(self.limit).offset(self.current_offset)
            try:
                for i, u in enumerate(query):
                    if self.stopped is not None and self.stopped.is_set():
                        return
                    phone_interval_id = u[0]
                    utterance_id = u[1]
                    file_id = u[2]
                    speaker_id = u[3]
                    begin = u[4]
                    end = u[5]
                    file_name = u[6]
                    indices.append(phone_interval_id)
                    reversed_indices[phone_interval_id] = i
                    file_indices.append(file_id)
                    speaker_indices.append(speaker_id)

                    utterance_ids.append(utterance_id)
                    utterance_name = f"{file_name} ({begin:.3f}-{end:.3f})"
                    data.append([utterance_name, *u[7:]])
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)

            except psycopg2.errors.InvalidRegularExpression:
                pass
        return data, indices, utterance_ids, file_indices, speaker_indices, reversed_indices


class SpeakerDiarizationWorker(Worker):
    def __init__(
        self,
        session,
        use_mp=False,
        speaker_id: int = None,
        alternate_speaker_id: int = None,
        reference_utterance_id: int = None,
        threshold: float = None,
        metric: typing.Union[str, DistanceMetric] = DistanceMetric.cosine,
        plda: Plda = None,
        speaker_plda: SpeakerPlda = None,
        limit: int = 100,
        inverted: bool = False,
        utterance_based: bool = False,
        text_filter: TextFilterQuery = None,
        **kwargs,
    ):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session
        self.speaker_id = speaker_id
        self.alternate_speaker_id = alternate_speaker_id
        self.reference_utterance_id = reference_utterance_id
        self.threshold = threshold
        self.metric = metric
        self.plda = plda
        self.speaker_plda = speaker_plda
        self.limit = limit
        self.inverted = inverted
        self.utterance_based = utterance_based
        self.text_filter = text_filter

        if isinstance(self.metric, str):
            self.metric = DistanceMetric[self.metric]
        if self.metric is DistanceMetric.plda:
            if self.plda is None:
                self.metric = DistanceMetric.cosine

    def _run(self):
        count_only = self.kwargs.get("count", False)
        if not count_only and self.progress_callback is not None:
            self.progress_callback.update_total(self.limit)

        with self.session() as session:
            c = session.query(Corpus).first()
            suggested_indices = []
            speaker_indices = []
            utterance_ids = []
            data = []
            if self.inverted or self.speaker_id is None:
                if (
                    self.metric is DistanceMetric.plda
                    and not count_only
                    and self.speaker_plda is None
                ):
                    speaker_plda = load_speaker_plda(session, self.plda, minimum_count=2)
                elif self.speaker_plda is not None:
                    speaker_plda = self.speaker_plda

            if self.reference_utterance_id is not None:
                utterance_query = (
                    session.query(
                        File.id,
                        File.name,
                        Utterance.begin,
                        Utterance.end,
                        c.utterance_ivector_column,
                        c.speaker_ivector_column.cosine_distance(c.utterance_ivector_column),
                        Speaker.id,
                        c.speaker_ivector_column,
                        Speaker.num_utterances,
                        Speaker.name,
                    )
                    .join(Utterance.file)
                    .join(Utterance.speaker)
                    .filter(Utterance.id == self.reference_utterance_id)
                    .first()
                )
                if utterance_query is None:
                    return
                (
                    file_id,
                    file_name,
                    begin,
                    end,
                    ivector,
                    original_distance,
                    speaker_id,
                    original_speaker_ivector,
                    original_num_utts,
                    speaker_name,
                ) = utterance_query
                speaker_query = session.query(
                    Speaker.id, Speaker.name, c.speaker_ivector_column.cosine_distance(ivector)
                ).filter(Speaker.id != speaker_id)
                if count_only:
                    return speaker_query.count()
                kaldi_ivector = DoubleVector()
                kaldi_ivector.from_numpy(ivector)
                kaldi_ivector = self.plda.transform_ivector(kaldi_ivector, 1)
                if self.metric is DistanceMetric.plda:
                    kaldi_original_speaker_ivector = DoubleVector()
                    kaldi_original_speaker_ivector.from_numpy(original_speaker_ivector)
                    kaldi_original_speaker_ivector = self.plda.transform_ivector(
                        kaldi_ivector, original_num_utts
                    )
                    original_distance = self.plda.LogLikelihoodRatio(
                        kaldi_original_speaker_ivector, original_num_utts, kaldi_ivector
                    )
                speaker_query = speaker_query.order_by(
                    c.speaker_ivector_column.cosine_distance(ivector)
                )
                speaker_query = speaker_query.limit(self.limit).offset(
                    self.kwargs.get("current_offset", 0)
                )

                for (
                    suggested_id,
                    suggested_name,
                    other_speaker_ivector,
                    other_num_utts,
                    distance,
                ) in speaker_query:
                    if self.stopped is not None and self.stopped.is_set():
                        session.rollback()
                        return
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)
                    if self.metric is DistanceMetric.plda:
                        kaldi_other_speaker_ivector = DoubleVector()
                        kaldi_other_speaker_ivector.from_numpy(ivector)
                        kaldi_other_speaker_ivector = self.plda.transform_ivector(
                            kaldi_other_speaker_ivector, other_num_utts
                        )
                        distance = self.plda.LogLikelihoodRatio(
                            kaldi_other_speaker_ivector, other_num_utts, kaldi_ivector
                        )
                    distance -= original_distance
                    utterance_ids.append(self.reference_utterance_id)
                    suggested_indices.append(suggested_id)
                    speaker_indices.append(speaker_id)
                    utterance_name = f"{file_name} ({begin:.3f}-{end:.3f})"
                    data.append(
                        [
                            utterance_name,
                            suggested_name,
                            other_num_utts,
                            speaker_name,
                            original_num_utts,
                            distance,
                        ]
                    )
            elif self.inverted and self.speaker_id is not None:
                utterance_query = (
                    session.query(
                        Utterance.id,
                        File.id,
                        File.name,
                        Utterance.begin,
                        Utterance.end,
                        c.utterance_ivector_column,
                        c.speaker_ivector_column,
                        Speaker.num_utterances,
                        c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column),
                        Speaker.name,
                    )
                    .join(Utterance.file)
                    .join(Utterance.speaker)
                    .filter(c.utterance_ivector_column != None)  # noqa
                    .filter(Utterance.speaker_id == self.speaker_id)
                )
                if count_only:
                    return utterance_query.count()
                if self.reference_utterance_id is not None:
                    reference_ivector = (
                        session.query(c.utterance_ivector_column)
                        .filter(Utterance.id == self.reference_utterance_id)
                        .first()[0]
                    )
                    utterance_query = utterance_query.order_by(
                        c.utterance_ivector_column.cosine_distance(reference_ivector).desc()
                    )
                else:
                    utterance_query = utterance_query.order_by(
                        c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column).desc()
                    )
                if self.threshold is None:
                    utterance_query = utterance_query.limit(self.limit).offset(
                        self.kwargs.get("current_offset", 0)
                    )

                for (
                    utt_id,
                    file_id,
                    file_name,
                    begin,
                    end,
                    ivector,
                    original_speaker_ivector,
                    original_speaker_num_utts,
                    original_distance,
                    speaker_name,
                ) in utterance_query:
                    if self.stopped is not None and self.stopped.is_set():
                        session.rollback()
                        return
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)
                    if self.metric is DistanceMetric.plda:
                        kaldi_ivector = DoubleVector()
                        kaldi_ivector.from_numpy(ivector)
                        ivector_normalize_length(kaldi_ivector)
                        kaldi_ivector = self.plda.transform_ivector(kaldi_ivector, 1)
                        kaldi_original_speaker_ivector = FloatVector()
                        kaldi_original_speaker_ivector.from_numpy(original_speaker_ivector)
                        kaldi_original_speaker_ivector = self.plda.transform_ivector(
                            kaldi_original_speaker_ivector, original_speaker_num_utts
                        )
                        original_distance = self.plda.LogLikelihoodRatio(
                            kaldi_original_speaker_ivector,
                            original_speaker_num_utts,
                            kaldi_ivector,
                        )
                        if (
                            self.alternate_speaker_id is not None
                            and self.alternate_speaker_id in speaker_plda.suggested_ids
                        ):
                            index = speaker_plda.suggested_ids.index(self.alternate_speaker_id)
                            suggested_id = self.alternate_speaker_id
                            suggested_count = speaker_plda.counts[index]
                            suggested_name = speaker_plda.suggested_names[index]
                            distance = self.plda.LogLikelihoodRatio(
                                speaker_plda.test_ivectors[index],
                                speaker_plda.counts[index],
                                kaldi_ivector,
                            )
                        else:
                            index, distance = self.plda.classify_utterance(
                                kaldi_ivector, speaker_plda.test_ivectors, speaker_plda.counts
                            )
                            suggested_name = speaker_plda.suggested_names[index]
                            suggested_count = speaker_plda.counts[index]
                            suggested_id = speaker_plda.suggested_ids[index]
                            if suggested_id == self.speaker_id:
                                continue
                        if self.threshold is not None and distance < self.threshold:
                            continue
                    else:
                        ivector_subquery = (
                            session.query(c.utterance_ivector_column)
                            .filter(Utterance.id == utt_id)
                            .subquery()
                        )
                        suggested_speaker_query = session.query(
                            Speaker.id,
                            Speaker.name,
                            Speaker.num_utterances,
                            c.speaker_ivector_column.cosine_distance(ivector_subquery),
                        ).filter(Speaker.id != self.speaker_id)
                        if self.alternate_speaker_id is not None:
                            suggested_speaker_query = suggested_speaker_query.filter(
                                Speaker.id == self.alternate_speaker_id
                            )
                        suggested_speaker_query = suggested_speaker_query.order_by(
                            c.speaker_ivector_column.cosine_distance(ivector_subquery)
                        ).limit(1)
                        r = suggested_speaker_query.first()
                        if r is None:
                            continue
                        suggested_id, suggested_name, suggested_count, distance = r
                        if (
                            self.threshold is not None
                            and distance is not None
                            and distance > self.threshold
                        ):
                            continue
                    distance -= original_distance
                    utterance_ids.append(utt_id)
                    suggested_indices.append(suggested_id)
                    speaker_indices.append(self.speaker_id)
                    utterance_name = f"{file_name} ({begin:.3f}-{end:.3f})"
                    data.append(
                        [
                            utterance_name,
                            suggested_name,
                            suggested_count,
                            speaker_name,
                            original_speaker_num_utts,
                            distance,
                        ]
                    )
                    if len(data) >= self.limit:
                        break
            elif self.inverted:
                utterance_query = (
                    session.query(
                        Utterance.id,
                        File.id,
                        File.name,
                        Utterance.begin,
                        Utterance.end,
                        c.utterance_ivector_column,
                        c.speaker_ivector_column,
                        Speaker.num_utterances,
                        c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column),
                        Speaker.name,
                        Speaker.id,
                    )
                    .join(Utterance.file)
                    .join(Utterance.speaker)
                    .filter(c.utterance_ivector_column != None)  # noqa
                )
                if count_only:
                    return utterance_query.count()
                utterance_query = utterance_query.order_by(
                    c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column).desc()
                )
                if self.threshold is None:
                    utterance_query = utterance_query.limit(self.limit).offset(
                        self.kwargs.get("current_offset", 0)
                    )
                else:
                    utterance_query = utterance_query.limit(500000)

                for (
                    utt_id,
                    file_id,
                    file_name,
                    begin,
                    end,
                    ivector,
                    original_speaker_ivector,
                    original_speaker_num_utts,
                    original_distance,
                    speaker_name,
                    speaker_id,
                ) in utterance_query:
                    if self.stopped is not None and self.stopped.is_set():
                        break
                    if self.metric is DistanceMetric.plda:
                        kaldi_ivector = DoubleVector()
                        kaldi_ivector.from_numpy(ivector)
                        ivector_normalize_length(kaldi_ivector)
                        kaldi_ivector = self.plda.transform_ivector(kaldi_ivector, 1)
                        kaldi_original_speaker_ivector = FloatVector()
                        kaldi_original_speaker_ivector.from_numpy(original_speaker_ivector)
                        kaldi_original_speaker_ivector = self.plda.transform_ivector(
                            kaldi_original_speaker_ivector, original_speaker_num_utts
                        )
                        original_distance = self.plda.LogLikelihoodRatio(
                            kaldi_original_speaker_ivector,
                            original_speaker_num_utts,
                            kaldi_ivector,
                        )
                        if (
                            self.alternate_speaker_id is not None
                            and self.alternate_speaker_id in speaker_plda.suggested_ids
                        ):
                            index = speaker_plda.suggested_ids.index(self.alternate_speaker_id)
                            suggested_id = self.alternate_speaker_id
                            suggested_count = speaker_plda.counts[index]
                            suggested_name = speaker_plda.suggested_names[index]
                            distance = self.plda.LogLikelihoodRatio(
                                speaker_plda.test_ivectors[index],
                                speaker_plda.counts[index],
                                kaldi_ivector,
                            )
                        else:
                            index, distance = self.plda.classify_utterance(
                                kaldi_ivector, speaker_plda.test_ivectors, speaker_plda.counts
                            )
                            suggested_name = speaker_plda.suggested_names[index]
                            suggested_count = speaker_plda.counts[index]
                            suggested_id = speaker_plda.suggested_ids[index]
                            if suggested_id == speaker_id:
                                continue
                        if self.threshold is not None and distance < self.threshold:
                            continue
                    else:
                        ivector_subquery = (
                            session.query(c.utterance_ivector_column)
                            .filter(Utterance.id == utt_id)
                            .subquery()
                        )
                        suggested_speaker_query = session.query(
                            Speaker.id,
                            Speaker.name,
                            Speaker.num_utterances,
                            c.speaker_ivector_column.cosine_distance(ivector_subquery),
                        ).filter(Speaker.id != speaker_id)
                        if self.alternate_speaker_id is not None:
                            suggested_speaker_query = suggested_speaker_query.filter(
                                Speaker.id == self.alternate_speaker_id
                            )
                        suggested_speaker_query = suggested_speaker_query.order_by(
                            c.speaker_ivector_column.cosine_distance(ivector_subquery)
                        ).limit(1)
                        r = suggested_speaker_query.first()
                        if r is None:
                            continue
                        suggested_id, suggested_name, suggested_count, distance = r
                        if (
                            self.threshold is not None
                            and distance is not None
                            and distance > self.threshold
                        ):
                            continue
                    distance -= original_distance
                    utterance_ids.append(utt_id)
                    suggested_indices.append(suggested_id)
                    speaker_indices.append(speaker_id)
                    utterance_name = f"{file_name} ({begin:.3f}-{end:.3f})"
                    data.append(
                        [
                            utterance_name,
                            suggested_name,
                            suggested_count,
                            speaker_name,
                            original_speaker_num_utts,
                            distance,
                        ]
                    )
                    if len(data) >= self.limit:
                        break
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)
            elif self.speaker_id is not None:
                query = session.query(
                    Speaker.name, c.speaker_ivector_column, Speaker.num_utterances
                )
                if isinstance(self.speaker_id, int):
                    query = query.filter(Speaker.id == self.speaker_id)
                else:
                    query = query.filter(Speaker.name == self.speaker_id)
                r = query.first()
                if r is None:
                    return data, utterance_ids, suggested_indices
                suggested_name, ivector, utt_count = r

                if self.metric is DistanceMetric.plda:
                    kaldi_speaker_ivector = DoubleVector()
                    kaldi_speaker_ivector.from_numpy(ivector)
                    kaldi_speaker_ivector = self.plda.transform_ivector(
                        kaldi_speaker_ivector, utt_count
                    )
                query = (
                    session.query(
                        Utterance.id,
                        File.id,
                        File.name,
                        Utterance.begin,
                        Utterance.end,
                        Speaker.id,
                        Speaker.name,
                        Speaker.num_utterances,
                        c.utterance_ivector_column,
                        c.utterance_ivector_column.cosine_distance(ivector),
                    )
                    .join(Utterance.file)
                    .join(Utterance.speaker)
                    .filter(Utterance.speaker_id != self.speaker_id)
                    .filter(c.utterance_ivector_column != None)  # noqa
                )
                if self.text_filter is not None and self.text_filter.text:
                    filter_regex = self.text_filter.generate_expression(posix=True)
                    query = query.filter(Utterance.text.op("~")(filter_regex))
                if self.alternate_speaker_id is not None:
                    query = query.filter(Utterance.speaker_id == self.alternate_speaker_id)
                if self.threshold is not None:
                    query = query.filter(
                        c.utterance_ivector_column.cosine_distance(ivector) <= self.threshold
                    )
                if count_only:
                    return query.count()
                if self.text_filter is None or not self.text_filter.text:
                    query = query.order_by(c.utterance_ivector_column.cosine_distance(ivector))
                query = query.limit(self.limit).offset(self.kwargs.get("current_offset", 0))
                for (
                    utt_id,
                    file_id,
                    file_name,
                    begin,
                    end,
                    original_id,
                    speaker_name,
                    original_count,
                    utterance_ivector,
                    distance,
                ) in query:
                    if self.stopped is not None and self.stopped.is_set():
                        session.rollback()
                        return
                    if distance is None:
                        continue
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)
                    if self.metric is DistanceMetric.plda:
                        kaldi_utterance_ivector = DoubleVector()
                        kaldi_utterance_ivector.from_numpy(utterance_ivector)
                        ivector_normalize_length(kaldi_utterance_ivector)
                        kaldi_utterance_ivector = self.plda.transform_ivector(
                            kaldi_utterance_ivector, 1
                        )
                        distance = self.plda.LogLikelihoodRatio(
                            kaldi_speaker_ivector, utt_count, kaldi_utterance_ivector
                        )
                    utterance_ids.append(utt_id)
                    suggested_indices.append(self.speaker_id)
                    speaker_indices.append(original_id)
                    utterance_name = f"{file_name} ({begin:.3f}-{end:.3f})"
                    data.append(
                        [
                            utterance_name,
                            suggested_name,
                            utt_count,
                            speaker_name,
                            original_count,
                            distance,
                        ]
                    )
            else:
                query = (
                    session.query(
                        Utterance.id,
                        File.id,
                        File.name,
                        Utterance.begin,
                        Utterance.end,
                        c.utterance_ivector_column,
                        Speaker.name,
                        Speaker.id,
                        Speaker.num_utterances,
                    )
                    .join(Utterance.file)
                    .join(Utterance.speaker)
                    .filter(c.utterance_ivector_column != None)  # noqa
                    .filter(Speaker.num_utterances == 1)
                )
                if self.text_filter is not None and self.text_filter.text:
                    filter_regex = self.text_filter.generate_expression(posix=True)
                    query = query.filter(Utterance.text.op("~")(filter_regex))
                if count_only:
                    return query.count()
                query = query.order_by(sqlalchemy.func.random())

                if self.threshold is None:
                    query = query.limit(self.limit).offset(self.kwargs.get("current_offset", 0))
                # else:
                #    query = query.limit(limit*100)
                for (
                    utt_id,
                    file_id,
                    file_name,
                    begin,
                    end,
                    ivector,
                    speaker_name,
                    speaker_id,
                    speaker_num_utterances,
                ) in query:
                    if self.stopped is not None and self.stopped.is_set():
                        break
                    if self.metric is DistanceMetric.plda:
                        kaldi_ivector = DoubleVector()
                        kaldi_ivector.from_numpy(ivector)
                        ivector_normalize_length(kaldi_ivector)
                        kaldi_ivector = self.plda.transform_ivector(kaldi_ivector, 1)
                        index, distance = self.plda.classify_utterance(
                            kaldi_ivector, speaker_plda.test_ivectors, speaker_plda.counts
                        )
                        suggested_name = speaker_plda.suggested_names[index]
                        suggested_count = speaker_plda.counts[index]
                        suggested_id = speaker_plda.suggested_ids[index]
                        if suggested_id == speaker_id:
                            continue
                        if self.threshold is not None and distance < self.threshold:
                            continue
                    else:
                        if self.utterance_based:
                            sub_query = (
                                session.query(
                                    Speaker.id,
                                    Speaker.name,
                                    Speaker.num_utterances,
                                    c.speaker_ivector_column.cosine_distance(ivector).label(
                                        "distance"
                                    ),
                                )
                                .join(Speaker.utterances)
                                .filter(
                                    Speaker.id != speaker_id,
                                )
                                .order_by(c.utterance_ivector_column.cosine_distance(ivector))
                                .limit(100)
                                .subquery()
                            )

                            suggested_speaker_query = (
                                session.query(
                                    sub_query.c.id,
                                    sub_query.c.name,
                                    sub_query.c.num_utterances,
                                    sub_query.c.distance,
                                )
                                .group_by(
                                    sub_query.c.id,
                                    sub_query.c.name,
                                    sub_query.c.num_utterances,
                                    sub_query.c.distance,
                                )
                                .order_by(sqlalchemy.func.count(sub_query.c.id).desc())
                            )

                        else:
                            suggested_speaker_query = session.query(
                                Speaker.id,
                                Speaker.name,
                                Speaker.num_utterances,
                                c.speaker_ivector_column.cosine_distance(ivector),
                            ).filter(
                                Speaker.id != speaker_id,
                            )
                            suggested_speaker_query = suggested_speaker_query.order_by(
                                c.speaker_ivector_column.cosine_distance(ivector)
                            ).limit(5)
                        r = suggested_speaker_query.all()
                        if not r:
                            continue
                        suggested_id = []
                        suggested_name = []
                        suggested_count = []
                        distance = []
                        for s_id, s_name, s_count, d in r:
                            suggested_id.append(s_id)
                            suggested_name.append(s_name)
                            suggested_count.append(s_count)
                            distance.append(d)
                        if len(suggested_id) == 1:
                            suggested_id = suggested_id[0]
                            suggested_name = suggested_name[0]
                            suggested_count = suggested_count[0]
                            distance = distance[0]
                        if self.threshold is not None:
                            if isinstance(distance, list) and distance[0] > self.threshold:
                                continue
                            elif (
                                not isinstance(distance, list)
                                and distance is not None
                                and distance > self.threshold
                            ):
                                continue
                        if distance is None:
                            continue
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)

                    utterance_ids.append(utt_id)
                    suggested_indices.append(suggested_id)
                    speaker_indices.append(speaker_id)
                    utterance_name = f"{file_name} ({begin:.3f}-{end:.3f})"
                    data.append(
                        [
                            utterance_name,
                            suggested_name,
                            suggested_count,
                            speaker_name,
                            speaker_num_utterances,
                            distance,
                        ]
                    )
                    if len(data) >= self.limit:
                        break
            d = np.array([x[-1] if not isinstance(x[-1], list) else x[-1][0] for x in data])
            if self.metric is DistanceMetric.plda:
                d *= -1
            indices = np.argsort(d)
            utterance_ids = [utterance_ids[x] for x in indices]
            suggested_indices = [suggested_indices[x] for x in indices]
            speaker_indices = [speaker_indices[x] for x in indices]
            data = [data[x] for x in indices]
        return data, utterance_ids, suggested_indices, speaker_indices


class SpeakerComparisonWorker(Worker):
    def __init__(
        self,
        session,
        use_mp=False,
        speaker_id: int = None,
        alternate_speaker_id: int = None,
        reference_utterance_id: int = None,
        threshold: float = None,
        metric: typing.Union[str, DistanceMetric] = DistanceMetric.cosine,
        plda: Plda = None,
        speaker_plda: SpeakerPlda = None,
        limit: int = 100,
        inverted: bool = False,
        text_filter: TextFilterQuery = None,
        **kwargs,
    ):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session
        self.speaker_id = speaker_id
        self.alternate_speaker_id = alternate_speaker_id
        self.reference_utterance_id = reference_utterance_id
        self.threshold = threshold
        self.metric = metric
        self.plda = plda
        self.speaker_plda = speaker_plda
        self.limit = limit
        self.inverted = inverted
        self.text_filter = text_filter

        if isinstance(self.metric, str):
            self.metric = DistanceMetric[self.metric]
        if self.metric is DistanceMetric.plda:
            if self.plda is None:
                self.metric = DistanceMetric.cosine

    def _run(self):
        count_only = self.kwargs.get("count", False)
        if not count_only and self.progress_callback is not None:
            self.progress_callback.update_total(self.limit)

        with self.session() as session:
            c = session.query(Corpus).first()
            suggested_indices = []
            speaker_indices = []
            utterance_ids = []
            data = []
            if self.inverted or self.speaker_id is None:
                if (
                    self.metric is DistanceMetric.plda
                    and not count_only
                    and self.speaker_plda is None
                ):
                    speaker_plda = load_speaker_plda(session, self.plda, minimum_count=2)
                elif self.speaker_plda is not None:
                    speaker_plda = self.speaker_plda
            found_set = set()
            if self.speaker_id is not None:
                query = session.query(
                    Speaker.name, c.speaker_ivector_column, Speaker.num_utterances
                )
                if isinstance(self.speaker_id, int):
                    query = query.filter(Speaker.id == self.speaker_id)
                else:
                    query = query.filter(Speaker.name == self.speaker_id)
                r = query.first()
                if r is None:
                    return data, utterance_ids, suggested_indices
                suggested_name, ivector, utt_count = r

                if self.metric is DistanceMetric.plda:
                    kaldi_speaker_ivector = DoubleVector()
                    kaldi_speaker_ivector.from_numpy(ivector)
                    kaldi_speaker_ivector = self.plda.transform_ivector(
                        kaldi_speaker_ivector, utt_count
                    )
                query = session.query(
                    Speaker.id,
                    Speaker.name,
                    Speaker.num_utterances,
                    c.speaker_ivector_column,
                    c.speaker_ivector_column.cosine_distance(ivector),
                ).filter(Speaker.id != self.speaker_id)
                if self.alternate_speaker_id is not None:
                    query = query.filter(Speaker.id == self.alternate_speaker_id)
                if self.threshold is not None:
                    query = query.filter(
                        c.speaker_ivector_column.cosine_distance(ivector) <= self.threshold
                    )

                if count_only:
                    return query.count()
                query = query.limit(self.limit).offset(self.kwargs.get("current_offset", 0))
                for (
                    original_id,
                    speaker_name,
                    original_count,
                    original_ivector,
                    distance,
                ) in query:
                    if self.stopped is not None and self.stopped.is_set():
                        session.rollback()
                        return
                    if distance is None:
                        continue
                    if (self.speaker_id, original_id) in found_set:
                        continue
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)
                    if self.metric is DistanceMetric.plda:
                        kaldi_utterance_ivector = DoubleVector()
                        kaldi_utterance_ivector.from_numpy(original_ivector)
                        ivector_normalize_length(kaldi_utterance_ivector)
                        kaldi_utterance_ivector = self.plda.transform_ivector(
                            kaldi_utterance_ivector, original_count
                        )
                        distance = self.plda.LogLikelihoodRatio(
                            kaldi_speaker_ivector, utt_count, kaldi_utterance_ivector
                        )
                    utterance_ids.append(None)
                    suggested_indices.append(self.speaker_id)
                    speaker_indices.append(original_id)
                    found_set.add((self.speaker_id, original_id))
                    utterance_name = ""
                    data.append(
                        [
                            utterance_name,
                            suggested_name,
                            utt_count,
                            speaker_name,
                            original_count,
                            distance,
                        ]
                    )
            else:
                query = (
                    session.query(
                        Speaker.id, c.speaker_ivector_column, Speaker.name, Speaker.num_utterances
                    )
                    .filter(c.speaker_ivector_column != None)  # noqa
                    .filter(Speaker.num_utterances > 0)
                )
                if self.text_filter is not None and self.text_filter.text:
                    filter_regex = self.text_filter.generate_expression(posix=True)
                    query = query.join(Speaker.utterances)
                    query = query.filter(Utterance.text.op("~")(filter_regex)).distinct()
                if count_only:
                    return query.count()
                if self.text_filter is None or not self.text_filter.text:
                    # query = query.order_by(c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column).desc())
                    query = query.order_by(sqlalchemy.func.random())
                    # query = query.order_by(Utterance.duration.desc())

                if self.threshold is None:
                    query = query.limit(self.limit).offset(self.kwargs.get("current_offset", 0))
                for speaker_id, ivector, speaker_name, num_utterances in query:
                    if self.stopped is not None and self.stopped.is_set():
                        break
                    if self.metric is DistanceMetric.plda:
                        kaldi_ivector = DoubleVector()
                        kaldi_ivector.from_numpy(ivector)
                        kaldi_ivector = self.plda.transform_ivector(kaldi_ivector, 1)
                        index, distance = self.plda.classify_utterance(
                            kaldi_ivector, speaker_plda.test_ivectors, speaker_plda.counts
                        )
                        suggested_name = speaker_plda.suggested_names[index]
                        suggested_count = speaker_plda.counts[index]
                        suggested_id = speaker_plda.suggested_ids[index]
                        if suggested_id == speaker_id:
                            continue
                        if self.threshold is not None and distance < self.threshold:
                            continue
                    else:
                        suggested_speaker_query = session.query(
                            Speaker.id,
                            Speaker.name,
                            Speaker.num_utterances,
                            c.speaker_ivector_column.cosine_distance(ivector),
                        ).filter(
                            Speaker.id != speaker_id,
                            # Speaker.num_utterances <= 200
                        )
                        suggested_speaker_query = suggested_speaker_query.order_by(
                            c.speaker_ivector_column.cosine_distance(ivector)
                        ).limit(1)
                        r = suggested_speaker_query.first()
                        if r is None:
                            continue
                        suggested_id, suggested_name, suggested_count, distance = r
                        if self.threshold is not None:
                            if distance is not None and distance > self.threshold:
                                continue
                        if distance is None:
                            continue
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)
                    if suggested_count < num_utterances:
                        speaker_id, suggested_id = suggested_id, speaker_id
                        speaker_name, suggested_name = suggested_name, speaker_name
                        num_utterances, suggested_count = suggested_count, num_utterances
                    if (speaker_id, suggested_id) in found_set:
                        continue
                    if (suggested_id, speaker_id) in found_set:
                        continue
                    found_set.add((speaker_id, suggested_id))
                    utterance_ids.append(None)
                    suggested_indices.append(suggested_id)
                    speaker_indices.append(speaker_id)
                    utterance_name = ""
                    data.append(
                        [
                            utterance_name,
                            suggested_name,
                            suggested_count,
                            speaker_name,
                            num_utterances,
                            distance,
                        ]
                    )
                    if len(data) >= self.limit:
                        break
            d = np.array([x[-1] for x in data])
            if self.metric is DistanceMetric.plda:
                d *= -1
            indices = np.argsort(d)
            utterance_ids = [utterance_ids[x] for x in indices]
            suggested_indices = [suggested_indices[x] for x in indices]
            speaker_indices = [speaker_indices[x] for x in indices]
            data = [data[x] for x in indices]
        return data, utterance_ids, suggested_indices, speaker_indices


class DuplicateFilesWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session

    def _run(self):
        threshold = self.kwargs.get("threshold", 0.01)
        working_directory = self.kwargs.get("working_directory")
        plda = self.kwargs.get("plda", None)
        to_delete = set()
        original_files = set()
        info_path = os.path.join(working_directory, "duplicate_info.tsv")
        with mfa_open(info_path, "w") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["original_file", "original_text", "duplicate_file", "duplicate_text"],
                delimiter="\t",
            )

            num_jobs = config.NUM_JOBS
            job_queue = Queue()
            return_queue = Queue()
            done_adding = threading.Event()
            done_processing = threading.Event()
            query_thread = UtteranceQueryThread(
                self.session, plda, job_queue, done_adding, self.stopped, self.progress_callback
            )
            query_thread.start()
            threads = []
            for i in range(num_jobs):
                threads.append(
                    ClosestUtteranceThread(
                        self.session,
                        threshold,
                        plda,
                        job_queue,
                        return_queue,
                        done_adding,
                        done_processing,
                        self.stopped,
                    )
                )
                threads[i].start()
            while True:
                try:
                    r = return_queue.get(timeout=2)
                except Empty:
                    if done_processing.is_set():
                        break
                    if self.stopped.is_set():
                        break
                    continue
                u_id, u_text, orig_file_name, duplicates = r
                if self.progress_callback is not None:
                    self.progress_callback.increment_progress(1)
                if orig_file_name in to_delete:
                    continue
                original_files.update(orig_file_name)
                if len(duplicates) == 0:
                    continue
                line = {"original_file": orig_file_name, "original_text": u_text}
                duplicate_files = {}
                for text, file_name in duplicates:
                    if file_name in original_files:
                        continue
                    if file_name not in duplicate_files:
                        duplicate_files[file_name] = text
                to_delete.update(duplicate_files.keys())
                for dup_file_name, dup_text in duplicate_files.items():
                    line["duplicate_file"] = dup_file_name
                    line["duplicate_text"] = dup_text
                    writer.writerow(line)
                    f.flush()
        with mfa_open(os.path.join(working_directory, "to_delete.txt"), "w") as f:
            for line in sorted(to_delete):
                f.write(f"{line}\n")
        return len(to_delete), info_path


class MergeSpeakersWorker(Worker):
    def __init__(
        self,
        session,
        use_mp=False,
        threshold=None,
        metric="cosine",
        plda: Plda = None,
        speaker_id: int = None,
        speaker_plda: SpeakerPlda = None,
        **kwargs,
    ):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session
        self.threshold = threshold
        self.metric = metric
        self.plda = plda
        self.speaker_id = speaker_id
        self.speaker_plda = speaker_plda
        if isinstance(self.metric, str):
            self.metric = DistanceMetric[self.metric]
        if self.metric is DistanceMetric.plda:
            if self.plda is None:
                self.metric = DistanceMetric.cosine

    def _run(self):
        speaker_counts = collections.Counter()
        deleted = set()
        with self.session() as session:
            if self.metric is not DistanceMetric.plda:
                self.plda = None
            elif self.speaker_plda is None:
                speaker_plda = load_speaker_plda(session, self.plda)
            c = session.query(Corpus).first()
            data = []
            query_count = session.query(Speaker.id).count()
            if self.progress_callback is not None:
                self.progress_callback.update_total(query_count)
            if self.speaker_id is None:
                num_jobs = config.NUM_JOBS
                job_queue = Queue()
                return_queue = Queue()
                done_adding = threading.Event()
                done_processing = threading.Event()
                query_thread = SpeakerQueryThread(
                    self.session, job_queue, done_adding, self.stopped, self.progress_callback
                )
                query_thread.start()
                threads = []
                merged_count = 0
                for i in range(num_jobs):
                    threads.append(
                        ClosestSpeakerThread(
                            self.session,
                            self.threshold,
                            self.plda,
                            speaker_plda,
                            job_queue,
                            return_queue,
                            done_adding,
                            done_processing,
                            self.stopped,
                        )
                    )
                    threads[i].start()
                while True:
                    try:
                        r = return_queue.get(timeout=2)
                    except Empty:
                        if done_processing.is_set():
                            break
                        if self.stopped is not None and self.stopped.is_set():
                            break
                        continue
                    suggested_id, to_merge = r
                    if suggested_id in deleted:
                        continue
                    if suggested_id is None:
                        continue
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)
                    if not to_merge:
                        continue
                    for s_id in to_merge:
                        if self.stopped is not None and self.stopped.is_set():
                            session.rollback()
                            return
                        file_ids = [
                            x
                            for x, in session.query(Utterance.file_id)
                            .filter(Utterance.speaker_id == s_id)
                            .distinct()
                        ]
                        merged_count += 1
                        logger.debug(f"Merged {merged_count} total speaker so far")
                        session.query(Utterance).filter(Utterance.speaker_id == s_id).update(
                            {Utterance.speaker_id: suggested_id}
                        )
                        session.query(SpeakerOrdering).filter(
                            SpeakerOrdering.c.file_id.in_(file_ids),
                            SpeakerOrdering.c.speaker_id.in_([s_id, suggested_id]),
                        ).delete()
                        speaker_ordering_mapping = []
                        for f in file_ids:
                            speaker_ordering_mapping.append(
                                {"speaker_id": suggested_id, "file_id": f, "index": 1}
                            )
                        session.execute(
                            sqlalchemy.insert(SpeakerOrdering), speaker_ordering_mapping
                        )
                        session.query(File).filter(File.id.in_(file_ids)).update(
                            {File.modified: True}
                        )
                    session.query(Speaker).filter(Speaker.id.in_(to_merge)).delete()
                    session.query(Speaker).filter(Speaker.id == suggested_id).update(
                        {Speaker.modified: True}
                    )
                    deleted.update(to_merge)
                    if self.progress_callback is not None:
                        query_count -= len(to_merge)
                        self.progress_callback.update_total(query_count)
                    session.commit()

                query_thread.join()
                for t in threads:
                    t.join()
                return merged_count
            else:
                ivector = (
                    session.query(c.speaker_ivector_column)
                    .filter(Speaker.id == self.speaker_id)
                    .first()[0]
                )
                query = (
                    session.query(Speaker.id)
                    .filter(Speaker.id != self.speaker_id)
                    .filter(c.speaker_ivector_column.cosine_distance(ivector) <= self.threshold)
                )
                query_count = query.count()
                if self.progress_callback is not None:
                    self.progress_callback.update_total(query_count)
                for (s_id,) in query:
                    if self.stopped is not None and self.stopped.is_set():
                        session.rollback()
                        return
                    data.append((s_id, self.speaker_id))
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)
                updated_speakers = {}
                if self.progress_callback is not None:
                    self.progress_callback.update_total(len(data))
                    self.progress_callback.set_progress(0)
                for s_id, suggested_id in data:
                    if self.stopped is not None and self.stopped.is_set():
                        session.rollback()
                        return
                    if s_id in updated_speakers:
                        s_id = updated_speakers[s_id]
                    if suggested_id in updated_speakers:
                        suggested_id = updated_speakers[suggested_id]
                    if (
                        suggested_id not in speaker_counts
                        or speaker_counts[s_id] > speaker_counts[suggested_id]
                    ):
                        suggested_id, s_id = s_id, suggested_id

                    updated_speakers[s_id] = suggested_id
                    for k, v in updated_speakers.items():
                        if v == s_id:
                            updated_speakers[k] = suggested_id
                    speaker_counts[suggested_id] += speaker_counts[s_id]
                    file_ids = [
                        x
                        for x, in session.query(SpeakerOrdering.file_id).filter(
                            SpeakerOrdering.speaker_id == s_id
                        )
                    ]
                    session.query(Utterance).filter(Utterance.speaker_id == s_id).update(
                        {Utterance.speaker_id: suggested_id}
                    )
                    session.query(SpeakerOrdering).filter(
                        SpeakerOrdering.file_id.in_(file_ids),
                        SpeakerOrdering.speaker_id.in_([s_id, suggested_id]),
                    ).delete()
                    speaker_ordering_mapping = []
                    for f in file_ids:
                        speaker_ordering_mapping.append(
                            {"speaker_id": suggested_id, "file_id": f, "index": 1}
                        )
                    session.execute(sqlalchemy.insert(SpeakerOrdering), speaker_ordering_mapping)
                    session.query(File).filter(File.id.in_(file_ids)).update({File.modified: True})
                    session.flush()
                    if self.progress_callback is not None:
                        self.progress_callback.increment_progress(1)
                session.commit()
                sq = (
                    session.query(Speaker.id, sqlalchemy.func.count().label("utterance_count"))
                    .outerjoin(Speaker.utterances)
                    .group_by(Speaker.id)
                    .subquery()
                )
                sq2 = sqlalchemy.select(sq.c.id).where(sq.c.utterance_count == 0)
                session.query(Speaker).filter(Speaker.id.in_(sq2)).delete(
                    synchronize_session="fetch"
                )
                session.commit()


class MismatchedUtterancesWorker(Worker):
    def __init__(
        self,
        session,
        use_mp=False,
        threshold=None,
        metric="cosine",
        plda: Plda = None,
        speaker_id: int = None,
        speaker_plda: SpeakerPlda = None,
        **kwargs,
    ):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session
        self.threshold = threshold
        self.metric = metric
        self.plda = plda
        self.speaker_id = speaker_id
        self.speaker_plda = speaker_plda
        if isinstance(self.metric, str):
            self.metric = DistanceMetric[self.metric]

    def _run(self):
        with self.session() as session:
            if self.metric is not DistanceMetric.plda:
                self.plda = None
            elif self.speaker_plda is None:
                self.speaker_plda = load_speaker_plda(session, self.plda)
            num_jobs = config.NUM_JOBS
            job_queue = Queue()
            return_queue = Queue()
            done_adding = threading.Event()
            done_processing = threading.Event()
            query_thread = MismatchedUtteranceQueryThread(
                self.session,
                self.threshold if self.plda is None else None,
                self.plda,
                self.speaker_plda,
                self.speaker_id,
                job_queue,
                done_adding,
                self.stopped,
                self.progress_callback,
            )
            query_thread.start()
            threads = []
            merged_count = 0
            for i in range(num_jobs):
                threads.append(
                    ClosestSpeakerThread(
                        self.session,
                        self.threshold,
                        self.plda,
                        self.speaker_plda,
                        job_queue,
                        return_queue,
                        done_adding,
                        done_processing,
                        self.stopped,
                        speaker_id=self.speaker_id,
                    )
                )
                threads[i].start()
            while True:
                try:
                    r = return_queue.get(timeout=2)
                except Empty:
                    if done_processing.is_set():
                        break
                    if self.stopped is not None and self.stopped.is_set():
                        break
                    continue
                if self.progress_callback is not None:
                    self.progress_callback.increment_progress(1)
                if r is None:
                    continue
                if self.stopped is not None and self.stopped.is_set():
                    session.rollback()
                    return
                u_id, suggested_id, s_id = r
                file_id = session.query(Utterance.file_id).filter(Utterance.id == u_id).first()[0]
                merged_count += 1
                logger.debug(f"Reassigned {merged_count} total utterances so far")
                session.query(Utterance).filter(Utterance.id == u_id).update(
                    {Utterance.speaker_id: suggested_id}
                )

                if (
                    session.query(SpeakerOrdering)
                    .filter(
                        SpeakerOrdering.c.file_id == file_id,
                        SpeakerOrdering.c.speaker_id == suggested_id,
                    )
                    .first()
                    is None
                ):
                    session.execute(
                        sqlalchemy.insert(SpeakerOrdering),
                        {"speaker_id": suggested_id, "file_id": file_id, "index": 1},
                    )

                session.query(File).filter(File.id == file_id).update({File.modified: True})
                session.query(Speaker).filter(Speaker.id.in_([suggested_id, s_id])).update(
                    {Speaker.modified: True}
                )
                session.commit()

            query_thread.join()
            for t in threads:
                t.join()
            return merged_count


class BulkUpdateSpeakerUtterancesWorker(Worker):
    def __init__(
        self,
        session,
        use_mp=False,
        threshold=None,
        metric="cosine",
        plda: Plda = None,
        speaker_id: int = None,
        speaker_plda: SpeakerPlda = None,
        **kwargs,
    ):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session
        self.threshold = threshold
        self.metric = metric
        self.plda = plda
        self.speaker_id = speaker_id
        self.speaker_plda = speaker_plda
        if isinstance(self.metric, str):
            self.metric = DistanceMetric[self.metric]

    def _run(self):
        with self.session() as session:
            c = session.query(Corpus).first()
            update_mapping = []
            modified_speakers = set()
            modified_files = set()
            speaker_name, ivector, utt_count = (
                session.query(Speaker.name, c.speaker_ivector_column, Speaker.num_utterances)
                .filter(Speaker.id == self.speaker_id)
                .first()
            )
            query = (
                session.query(
                    Utterance.id,
                    Utterance.file_id,
                    Utterance.speaker_id,
                    c.utterance_ivector_column,
                )
                .join(Utterance.speaker)
                .filter(Utterance.speaker_id != self.speaker_id)
            )
            if self.metric is DistanceMetric.plda:
                kaldi_speaker_ivector = DoubleVector()
                kaldi_speaker_ivector.from_numpy(ivector)
                kaldi_speaker_ivector = self.plda.transform_ivector(
                    kaldi_speaker_ivector, utt_count
                )
                query = query.filter(c.utterance_ivector_column.cosine_distance(ivector) <= 0.5)
            else:
                query = query.filter(
                    c.utterance_ivector_column.cosine_distance(ivector) <= self.threshold
                )
            query = query.order_by(c.utterance_ivector_column.cosine_distance(ivector))

            if self.progress_callback is not None:
                self.progress_callback.update_total(query.count())
            for utt_id, file_id, s_id, utterance_ivector in query:
                if self.stopped is not None and self.stopped.is_set():
                    session.rollback()
                    return
                if self.progress_callback is not None:
                    self.progress_callback.increment_progress(1)
                if self.metric is DistanceMetric.plda:
                    kaldi_utterance_ivector = DoubleVector()
                    kaldi_utterance_ivector.from_numpy(utterance_ivector)
                    ivector_normalize_length(kaldi_utterance_ivector)
                    kaldi_utterance_ivector = self.plda.transform_ivector(
                        kaldi_utterance_ivector, 1
                    )
                    score = self.plda.LogLikelihoodRatio(
                        kaldi_speaker_ivector, utt_count, kaldi_utterance_ivector
                    )
                    if score < self.threshold:
                        continue

                update_mapping.append({"id": utt_id, "speaker_id": self.speaker_id})
                modified_files.add(file_id)
                modified_speakers.add(s_id)
            if update_mapping:
                modified_speakers.add(self.speaker_id)
                bulk_update(session, Utterance, update_mapping)
                session.flush()
                session.query(Speaker).filter(Speaker.id.in_(modified_speakers)).update(
                    {Speaker.modified: True}
                )
                session.query(File).filter(File.id.in_(modified_files)).update(
                    {File.modified: True}
                )
                session.commit()
        logger.debug(
            f"Updated {len(update_mapping)} utterances, {len(modified_speakers)} speakers, {len(modified_files)} files"
        )


class FileUtterancesWorker(Worker):
    def __init__(self, session, file_id, use_mp=False, **kwargs):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session
        self.file_id = file_id

    def _run(self):
        utterances = (
            self.session.query(Utterance)
            .options(
                selectinload(Utterance.phone_intervals).options(
                    joinedload(PhoneInterval.phone, innerjoin=True),
                ),
                selectinload(Utterance.reference_phone_intervals).options(
                    joinedload(ReferencePhoneInterval.phone, innerjoin=True),
                ),
                selectinload(Utterance.word_intervals).options(
                    joinedload(WordInterval.word, innerjoin=True),
                    joinedload(WordInterval.pronunciation, innerjoin=True),
                ),
                selectinload(Utterance.reference_word_intervals).options(
                    joinedload(ReferenceWordInterval.word, innerjoin=True),
                ),
                joinedload(Utterance.speaker, innerjoin=True),
            )
            .filter(Utterance.file_id == self.file_id)
            .order_by(Utterance.begin)
            .all()
        )
        return utterances, self.file_id


class QueryOovWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session

    def _run(self):
        with self.session() as session:
            text_filter = self.kwargs.get("text_filter", None)
            sort_index = self.kwargs.get("sort_index", None)
            columns = [Word.word, Word.count, Word.id]
            text_column = Word.word

            if self.progress_callback is not None:
                self.progress_callback.update_total(self.kwargs.get("limit", 100))

            words = session.query(*columns).filter(Word.word_type == WordType.oov)
            if text_filter is not None:
                filter_regex = text_filter.generate_expression(posix=True)
                words = words.filter(text_column.op("~")(filter_regex))
            if self.kwargs.get("count", False):
                return words.count()
            if sort_index is not None and sort_index < len(columns):
                sort_column = columns[sort_index]
                if self.kwargs.get("sort_desc", False):
                    sort_column = sort_column.desc()
            else:
                sort_column = text_column
            words = words.order_by(sort_column, Word.id)

            words = words.limit(self.kwargs.get("limit", 100)).offset(
                self.kwargs.get("current_offset", 0)
            )
            data = []
            indices = []
            for word, count, w_id in words:
                if self.stopped is not None and self.stopped.is_set():
                    return
                data.append([word, count])
                indices.append(w_id)
                if self.progress_callback is not None:
                    self.progress_callback.increment_progress(1)

        return data, indices


class QueryDictionaryWorker(Worker):
    def __init__(self, session, use_mp=False, dictionary_id: int = None, **kwargs):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session
        self.dictionary_id = dictionary_id

    def _run(self):
        with self.session() as session:
            text_filter = self.kwargs.get("text_filter", None)
            sort_index = self.kwargs.get("sort_index", None)
            filter_unused = self.kwargs.get("filter_unused", False)

            if self.progress_callback is not None:
                self.progress_callback.update_total(self.kwargs.get("limit", 100))
            columns = [
                Word.word,
                Word.word_type,
                Word.count,
                Pronunciation.pronunciation,
                Word.id,
                Pronunciation.id,
            ]
            text_column = Word.word
            words = session.query(*columns).join(Word.pronunciations)
            if self.dictionary_id is not None:
                words = words.filter(Word.dictionary_id == self.dictionary_id)
            if filter_unused:
                words = words.filter(Word.count > 0)
            if text_filter is not None:
                filter_regex = text_filter.generate_expression(posix=True)
                words = words.filter(text_column.op("~")(filter_regex))
            if self.kwargs.get("count", False):
                return words.count()
            if sort_index is not None and sort_index < len(columns):
                sort_column = columns[sort_index]
                if self.kwargs.get("sort_desc", False):
                    sort_column = sort_column.desc()
            else:
                sort_column = text_column
            words = words.order_by(sort_column, Word.id, Pronunciation.id)

            words = words.limit(self.kwargs.get("limit", 100)).offset(
                self.kwargs.get("current_offset", 0)
            )
            data = []
            indices = []
            pron_indices = []
            for word, word_type, count, pron, w_id, p_id in words:
                if self.stopped is not None and self.stopped.is_set():
                    return
                indices.append(w_id)
                pron_indices.append(p_id)
                data.append([word, word_type, count, pron])
                if self.progress_callback is not None:
                    self.progress_callback.increment_progress(1)

        return data, indices, pron_indices


class ExportLexiconWorker(Worker):
    def __init__(self, corpus: AcousticCorpusWithPronunciations, dictionary_id: int, use_mp=False, **kwargs):
        super().__init__(use_mp=use_mp, **kwargs)
        self.corpus = corpus
        self.dictionary_id = dictionary_id

    def _run(self):
        with self.corpus.session() as session:
            dictionary_path = (
                session.query(Dictionary.path).filter(Dictionary.id == self.dictionary_id).scalar()
            )
        self.corpus.export_lexicon(self.dictionary_id, dictionary_path, probability=True)


class LoadSpeakersWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session

    def _run(self):
        begin = time.time()
        conn = self.session.bind.raw_connection()
        speakers = {}
        id_mapping = {}
        try:
            cursor = conn.cursor()
            cursor.execute("select speaker.name, speaker.id from speaker order by speaker.name")
            query = cursor.fetchall()
            for s_name, s_id in query:
                speakers[s_name] = s_id
                id_mapping[s_id] = s_name
            cursor.close()
        finally:
            conn.close()
        logger.debug(f"Loading all speaker names took {time.time() - begin:.3f} seconds.")
        return speakers, id_mapping


class LoadFilesWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(session, use_mp=use_mp, **kwargs)
        self.session = session

    def _run(self):
        begin = time.time()
        conn = self.session.bind.raw_connection()
        files = {}
        try:
            cursor = conn.cursor()
            cursor.execute("select file.name, file.id from file order by file.name")
            query = cursor.fetchall()
            for f_name, f_id in query:
                files[f_name] = f_id
            cursor.close()
        finally:
            conn.close()
        logger.debug(f"Loading all file names took {time.time() - begin:.3f} seconds.")
        return files


class LoadDictionariesWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(use_mp=use_mp, **kwargs)
        self.session = session

    def _run(self):
        dictionaries = []
        word_sets = {}
        speaker_mapping = {}
        with self.session() as session:
            query = session.query(Dictionary.id, Dictionary.name)
            for dict_id, dict_name in query:
                dictionaries.append([dict_id, dict_name])
                word_sets[dict_id] = {
                    x[0]
                    for x in session.query(Word.word).filter(
                        Word.dictionary_id == dict_id,
                        Word.word_type.in_(WordType.speech_types()),
                    )
                }
                for (s_id,) in session.query(Speaker.id).filter(Speaker.dictionary_id == dict_id):
                    speaker_mapping[s_id] = dict_id

        return dictionaries, word_sets, speaker_mapping


class LexiconFstBuildWorker(Worker):
    def __init__(self, corpus_model, use_mp=False, dictionary_id: int = None, **kwargs):
        super().__init__(corpus_model, use_mp=use_mp, **kwargs)
        self.corpus_model = corpus_model
        self.dictionary_id = dictionary_id

    def _run(self):
        lexicon_compiler = self.corpus_model.corpus.build_lexicon_compiler(
            self.dictionary_id, self.corpus_model.acoustic_model, disambiguation=True
        )
        return lexicon_compiler, self.dictionary_id


class FunctionWorker(QtCore.QThread):  # pragma: no cover
    def __init__(self, name, *args):
        super().__init__(*args)
        self.settings = AnchorSettings()
        self.signals = WorkerSignals(name)
        self.stopped = threading.Event()
        self.lock = Lock()

    def setParams(self, kwargs):
        self.kwargs = kwargs
        self.kwargs["progress_callback"] = self.signals.progress
        self.kwargs["stopped"] = self.stopped
        self.total = None

    def stop(self):
        self.stopped.set()


class AutoWaveformWorker(Worker):  # pragma: no cover
    def __init__(self, y, normalized_min, normalized_max, begin, end, channel, *args):
        super().__init__("Scaling waveform", *args)
        self.y = y
        self.normalized_min = normalized_min
        self.normalized_max = normalized_max
        self.begin = begin
        self.end = end
        self.channel = channel

    def run(self):
        self.stopped.clear()
        if self.y.shape[0] == 0:
            return
        max_val = np.max(np.abs(self.y), axis=0)
        if np.isnan(max_val):
            return
        normalized = self.y / max_val
        normalized[np.isnan(normalized)] = 0

        height = self.normalized_max - self.normalized_min

        new_height = height / 2
        mid_point = self.normalized_min + new_height
        normalized = normalized * 0.5 + mid_point
        if self.stopped.is_set():
            return
        self.signals.result.emit((normalized, self.begin, self.end, self.channel))


class WaveformWorker(Worker):  # pragma: no cover
    def __init__(self, file_path, *args):
        super().__init__("Loading waveform", *args)
        self.file_path = file_path

    def run(self):
        try:
            y, _ = soundfile.read(self.file_path)
        except soundfile.LibsndfileError:
            logger.warning(f"Could not read {self.file_path}")
            y = None
        self.signals.result.emit((y, self.file_path))


class SpeakerTierWorker(Worker):  # pragma: no cover
    def __init__(
        self,
        session,
        file_id,
        *args,
        query_alignment=False,
        utterance_id=None,
        begin=None,
        end=None,
    ):
        super().__init__("Generating speaker tier", *args)
        self.query_alignment = query_alignment
        self.session = session
        self.file_id = file_id
        self.utterance_id = utterance_id
        self.begin = begin
        self.end = end
        self.settings = AnchorSettings()

    def run(self):
        if self.session is None:
            return
        with self.session() as session:
            file = session.get(File, self.file_id)
            show_phones = self.settings.value(
                self.settings.TIER_ALIGNED_PHONES_VISIBLE
            ) or self.settings.value(self.settings.TIER_REFERENCE_PHONES_VISIBLE)
            show_words = self.settings.value(self.settings.TIER_ALIGNED_WORDS_VISIBLE)
            utterances = session.query(Utterance)
            if self.query_alignment:
                if show_phones:
                    utterances = utterances.options(
                        selectinload(Utterance.phone_intervals).options(
                            joinedload(PhoneInterval.phone, innerjoin=True),
                        ),
                        selectinload(Utterance.reference_phone_intervals).options(
                            joinedload(ReferencePhoneInterval.phone, innerjoin=True),
                        ),
                    )
                if show_words:
                    utterances = utterances.options(
                        selectinload(Utterance.word_intervals).options(
                            joinedload(WordInterval.word, innerjoin=True),
                        ),
                    )
                    utterances = utterances.options(
                        selectinload(Utterance.reference_word_intervals).options(
                            joinedload(ReferenceWordInterval.word, innerjoin=True),
                        ),
                    )
            utterances = utterances.filter(
                Utterance.file_id == self.file_id,
            ).order_by(Utterance.begin)

            if self.utterance_id is not None:
                utterances = utterances.filter(Utterance.id == self.utterance_id)
            if file.duration > 500 and self.begin is not None and self.end is not None:
                cached_begin = self.begin - 30
                cached_end = self.end + 30
                utterances = utterances.filter(
                    Utterance.end >= cached_begin,
                    Utterance.begin <= cached_end,
                )
            else:
                cached_begin = None
                cached_end = None
            utterances = utterances.all()
            if (
                file.duration > 500
                and self.begin is not None
                and self.end is not None
                and utterances
            ):
                cached_begin = min(cached_begin, utterances[0].begin)
                cached_end = max(cached_end, utterances[-1].end)
            self.signals.result.emit((utterances, self.file_id, cached_begin, cached_end))


class SpectrogramWorker(Worker):  # pragma: no cover
    def __init__(self, y, sample_rate, begin, end, channel, *args):
        super().__init__("Generating spectrogram", *args)
        self.y = y
        self.sample_rate = sample_rate
        self.begin = begin
        self.end = end
        self.channel = channel

    def run(self):
        dynamic_range = self.settings.value(self.settings.SPEC_DYNAMIC_RANGE)
        n_fft = self.settings.value(self.settings.SPEC_N_FFT)
        time_steps = self.settings.value(self.settings.SPEC_N_TIME_STEPS)
        window_size = self.settings.value(self.settings.SPEC_WINDOW_SIZE)
        pre_emph_coeff = self.settings.value(self.settings.SPEC_PREEMPH)
        max_freq = self.settings.value(self.settings.SPEC_MAX_FREQ)
        if self.y.shape[0] == 0:
            self.signals.result.emit(None)
            return
        duration = self.y.shape[0] / self.sample_rate
        if duration > self.settings.value(self.settings.SPEC_MAX_TIME):
            self.signals.result.emit(None)
            return
        max_sr = 2 * max_freq
        if self.sample_rate > max_sr:
            self.y = scipy.signal.resample(
                self.y, int(self.y.shape[0] * max_sr / self.sample_rate)
            )
            self.sample_rate = max_sr
        self.y = librosa.effects.preemphasis(self.y, coef=pre_emph_coeff)
        begin_samp = int(self.begin * self.sample_rate)
        end_samp = int(self.end * self.sample_rate)
        window_size = round(window_size, 6)
        window_size_samp = int(window_size * self.sample_rate)
        duration_samp = end_samp - begin_samp
        if time_steps >= duration_samp:
            step_size_samples = 1
        else:
            step_size_samples = int(duration_samp / time_steps)
        stft = librosa.amplitude_to_db(
            np.abs(
                librosa.stft(
                    self.y,
                    n_fft=n_fft,
                    win_length=window_size_samp,
                    hop_length=step_size_samples,
                    center=True,
                )
            ),
            top_db=dynamic_range,
        )
        min_db, max_db = np.min(stft), np.max(stft)
        self.signals.result.emit((stft, self.channel, self.begin, self.end, min_db, max_db))


class MfccWorker(Worker):  # pragma: no cover
    def __init__(self, y, sample_rate, begin, end, channel, *args):
        super().__init__("Generating spectrogram", *args)
        self.y = y
        self.sample_rate = sample_rate
        self.begin = begin
        self.end = end
        self.channel = channel

        self.mfcc_computer = MfccComputer(
            use_energy=False,
            raw_energy=False,
            frame_shift=10,
            frame_length=25,
            snip_edges=False,
            low_frequency=20,
            high_frequency=7800,
            sample_frequency=16000,
            allow_downsample=True,
            allow_upsample=True,
            dither=0.0,
            energy_floor=0.0,
            num_coefficients=13,
            num_mel_bins=23,
            cepstral_lifter=22,
            preemphasis_coefficient=0.97,
        )

    def run(self):
        if self.y.shape[0] == 0:
            self.signals.result.emit(None)
            return
        duration = self.y.shape[0] / self.sample_rate
        if duration > self.settings.value(self.settings.SPEC_MAX_TIME):
            self.signals.result.emit(None)
            return
        if self.sample_rate > self.mfcc_computer.sample_frequency:
            self.y = scipy.signal.resample(
                self.y,
                int(self.y.shape[0] * self.mfcc_computer.sample_frequency / self.sample_rate),
            )
            self.sample_rate = self.mfcc_computer.sample_frequency
        stft = self.mfcc_computer.compute_mfccs(self.y).T
        min_db, max_db = np.min(stft), np.max(stft)
        self.signals.result.emit((stft, self.channel, self.begin, self.end, min_db, max_db))


class PitchWorker(Worker):  # pragma: no cover
    def __init__(self, y, sample_rate, begin, end, channel, normalized_min, normalized_max, *args):
        super().__init__("Generating pitch track", *args)
        self.y = y
        self.sample_rate = sample_rate
        self.begin = begin
        self.end = end
        self.channel = channel
        self.min_f0 = self.settings.value(self.settings.PITCH_MIN_F0)
        self.max_f0 = self.settings.value(self.settings.PITCH_MAX_F0)
        self.frame_shift = self.settings.value(self.settings.PITCH_FRAME_SHIFT)
        self.frame_length = self.settings.value(self.settings.PITCH_FRAME_LENGTH)
        self.penalty_factor = self.settings.value(self.settings.PITCH_PENALTY_FACTOR)
        self.delta_pitch = self.settings.value(self.settings.PITCH_DELTA_PITCH)
        self.normalized_min = normalized_min
        self.normalized_max = normalized_max
        self.pitch_computer = PitchComputer(
            frame_shift=self.frame_shift,
            frame_length=self.frame_length,
            sample_frequency=sample_rate,
            min_f0=self.min_f0,
            max_f0=self.max_f0,
            penalty_factor=self.penalty_factor,
            delta_pitch=self.delta_pitch,
            add_pov_feature=True,
            add_normalized_log_pitch=False,
            add_delta_pitch=False,
            add_raw_log_pitch=True,
        )

    def run(self):
        if self.y.shape[0] == 0:
            return
        duration = self.end - self.begin
        if duration < 0.1:
            self.signals.result.emit(None)
            return
        if duration > self.settings.value(self.settings.PITCH_MAX_TIME):
            self.signals.result.emit(None)
            return
        pitch_track = compute_pitch(
            self.y, self.pitch_computer.extraction_opts, self.pitch_computer.process_opts
        ).numpy()
        if len(pitch_track.shape) < 2:
            self.signals.result.emit(
                (None, None, self.channel, self.begin, self.end, self.min_f0, self.max_f0)
            )
            return
        voiced_track = pitch_track[:, 0]
        pitch_track = np.exp(pitch_track[:, 1])
        min_nccf = np.min(voiced_track)
        max_nccf = np.max(voiced_track)
        threshold = min_nccf + (max_nccf - min_nccf) * 0.45
        voiced_frames = np.where(
            (voiced_track <= threshold) & (pitch_track < self.max_f0) & (pitch_track > self.min_f0)
        )
        if not len(voiced_frames) or voiced_frames[0].shape[0] == 0:
            normalized = None
        else:
            voiceless_frames = np.where(
                (voiced_track > threshold)
                | (pitch_track >= self.max_f0)
                | (pitch_track <= self.min_f0)
            )
            min_f0 = int(np.min(pitch_track[voiced_frames])) - 1
            max_f0 = int(np.max(pitch_track[voiced_frames])) + 1
            normalized = (pitch_track - min_f0) / (max_f0 - min_f0)

            height = self.normalized_max - self.normalized_min
            normalized *= height
            normalized = normalized + self.normalized_min
            normalized[voiceless_frames] = np.nan
        self.signals.result.emit(
            (
                normalized,
                voiced_track,
                self.channel,
                self.begin,
                self.end,
                self.min_f0,
                self.max_f0,
            )
        )


class DownloadWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Downloading model", *args)

    def set_params(self, db_string: str, model_type: str, model_name: str, model_manager):
        self.db_string = db_string
        self.model_type = model_type
        self.model_name = model_name
        self.model_manager = model_manager

    def run(self):
        try:
            engine = sqlalchemy.create_engine(self.db_string)
            with sqlalchemy.orm.Session(engine) as session:
                model = (
                    session.query(anchor.db.MODEL_TYPES[self.model_type])
                    .filter_by(name=self.model_name)
                    .first()
                )
                if model.available_locally:
                    return
                self.model_manager.download_model(self.model_type, self.model_name)
                model.available_locally = True
                model.path = MODEL_TYPES[self.model_type].get_pretrained_path(self.model_name)
                model.last_used = datetime.datetime.now()
                session.commit()
            self.signals.result.emit((self.model_type, self.model_name))  # Done

        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            self.signals.finished.emit()  # Done


class ImportCorpusWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Importing corpus", *args)
        self.corpus_path = None
        self.dictionary_path = None
        self.reset = None

    def stop(self):
        if hasattr(self, "corpus") and self.corpus is not None:
            self.corpus.stopped.set()

    def set_params(self, corpus_path: str, dictionary_path: str, reset=False):
        self.corpus_path = corpus_path
        self.dictionary_path = dictionary_path
        self.reset = reset

    def run(self):
        config.CLEAN = self.reset
        corpus_name = os.path.basename(self.corpus_path)
        dataset_type = inspect_database(corpus_name)
        if (
            dataset_type is DatasetType.ACOUSTIC_CORPUS_WITH_DICTIONARY
            and self.dictionary_path is None
        ):
            string = f"postgresql+psycopg2://@/{corpus_name}?host={config.database_socket()}"
            try:
                engine = sqlalchemy.create_engine(
                    string,
                    poolclass=sqlalchemy.NullPool,
                    pool_reset_on_return=None,
                    isolation_level="AUTOCOMMIT",
                    logging_name="inspect_dataset_engine",
                ).execution_options(logging_token="inspect_dataset_engine")
                with sqlalchemy.orm.Session(engine) as session:
                    dictionary = (
                        session.query(Dictionary.path)
                        .filter(Dictionary.path != "", Dictionary.path != ".")
                        .first()
                    )
                    if dictionary is not None:
                        self.dictionary_path = dictionary[0]
            except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.ProgrammingError):
                pass
        try:
            if dataset_type is DatasetType.NONE:
                if (
                    self.dictionary_path
                    and os.path.exists(self.dictionary_path)
                    and str(self.dictionary_path) != "."
                ):
                    self.corpus = AcousticCorpusWithPronunciations(
                        corpus_directory=self.corpus_path, dictionary_path=self.dictionary_path
                    )
                    self.corpus.initialize_database()
                    self.corpus.dictionary_setup()
                    self.corpus.write_lexicon_information(write_disambiguation=False)
                else:
                    self.corpus = AcousticCorpusWithPronunciations(
                        corpus_directory=self.corpus_path
                    )
                    self.corpus.initialize_database()
                    self.corpus.create_default_dictionary()

            elif (
                dataset_type is DatasetType.ACOUSTIC_CORPUS_WITH_DICTIONARY
                and self.dictionary_path
                and str(self.dictionary_path) != "."
                and os.path.exists(self.dictionary_path)
            ):
                self.corpus = AcousticCorpusWithPronunciations(
                    corpus_directory=self.corpus_path, dictionary_path=self.dictionary_path
                )
                self.corpus.inspect_database()
            else:
                self.corpus = AcousticCorpusWithPronunciations(corpus_directory=self.corpus_path)
                self.corpus.inspect_database()
                self.corpus.create_default_dictionary()
            self.corpus._load_corpus()
            if self.dictionary_path and os.path.exists(self.dictionary_path):
                self.corpus.initialize_jobs()

                self.corpus.normalize_text()
                try:
                    self.corpus.load_alignment_lexicon_compilers()
                except Exception:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    error_text = "\n".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
                    logger.debug(error_text)
            with self.corpus.session() as session:
                session.execute(
                    sqlalchemy.text(
                        "CREATE INDEX IF NOT EXISTS utterance_text_ix ON utterance USING gin (text gin_trgm_ops);"
                    )
                )
            session.commit()
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
            self.signals.result.emit(None)
        else:
            if self.corpus.stopped.is_set():
                self.signals.result.emit(None)
            else:
                self.signals.result.emit(self.corpus)  # Return the result of the processing
        finally:
            self.corpus = None
            self.signals.finished.emit()  # Done


class ReloadCorpusWorker(ImportCorpusWorker):
    def __init__(self, *args):
        FunctionWorker.__init__(self, "Reloading corpus", *args)

    def set_params(self, corpus_path: str, dictionary_path: str):
        self.corpus_path = corpus_path
        self.dictionary_path = dictionary_path

    def run(self):
        self.settings.sync()
        try:
            if self.dictionary_path and os.path.exists(self.dictionary_path):
                self.corpus = AcousticCorpusWithPronunciations(
                    corpus_directory=self.corpus_path, dictionary_path=self.dictionary_path
                )
            else:
                self.corpus = AcousticCorpus(corpus_directory=self.corpus_path)
            self.corpus._db_engine = self.corpus.construct_engine()
            file_count = self.corpus_model.session.query(File).count()
            files = self.corpus_model.session.query(File).options(
                joinedload(File.sound_file, innerjoin=True),
                joinedload(File.text_file, innerjoin=True),
                selectinload(File.utterances).joinedload(Utterance.speaker, innerjoin=True),
            )
            utterance_mapping = []
            with tqdm.tqdm(total=file_count, disable=getattr(self, "quiet", False)) as pbar:
                for file in files:
                    file_data = FileData.parse_file(
                        file.name,
                        file.sound_file.sound_file_path,
                        file.text_file.text_file_path,
                        file.relative_path,
                        self.corpus.speaker_characters,
                    )
                    utterances = {(u.speaker.name, u.begin, u.end): u for u in file.utterances}

                    for utt_data in file_data.utterances:
                        key = (utt_data.speaker_name, utt_data.begin, utt_data.end)
                        if key in utterances:
                            utt = utterances[key]
                        elif len(utterances) == 1:
                            utt = list(utterances.values())[0]
                        else:
                            mid_point = utt_data.begin + ((utt_data.end - utt_data.begin) / 2)
                            for k in utterances.keys():
                                if k[0] != utt_data.speaker_name:
                                    continue
                                if k[1] < mid_point < k[2]:
                                    utt = utterances[k]
                                    break
                            else:
                                continue
                        utterance_mapping.append(
                            {
                                "id": utt.id,
                                "text": utt_data.text,
                                "normalized_text": utt_data.normalized_text,
                            }
                        )
                    pbar.update(1)
                bulk_update(self.corpus_model.session, Utterance, utterance_mapping)
                self.corpus_model.session.commit()

        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            if self.corpus.stopped.is_set():
                self.signals.result.emit(None)
            else:
                self.signals.result.emit(self.corpus)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done
            self.corpus = None


class LoadReferenceWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Loading reference alignments", *args)
        self.corpus: typing.Optional[AcousticCorpus] = None

    def set_params(self, corpus: AcousticCorpus, reference_directory: Path):
        self.corpus = corpus
        self.reference_directory = reference_directory

    def run(self):
        self.settings.sync()
        try:
            with self.corpus.session() as session:
                session.query(ReferencePhoneInterval).delete(synchronize_session=False)
                session.query(CorpusWorkflow).filter(
                    CorpusWorkflow.workflow_type == WorkflowType.reference
                ).delete(synchronize_session=False)
                session.execute(sqlalchemy.update(Corpus).values(has_reference_alignments=False))
                session.commit()
            self.corpus.load_reference_alignments(self.reference_directory)
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            self.signals.result.emit(self.corpus)  # Done
            self.signals.finished.emit()  # Done


class ImportDictionaryWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Importing dictionary", *args)

    def set_params(self, corpus: AcousticCorpus, dictionary_path: str):
        self.corpus = corpus
        self.dictionary_path = dictionary_path

    def run(self):
        self.corpus_temp_dir = os.path.join(self.settings.temp_directory, "corpus")
        try:
            corpus = AcousticCorpusWithPronunciations(
                corpus_directory=self.corpus.corpus_directory, dictionary_path=self.dictionary_path
            )
            shutil.rmtree(corpus.output_directory, ignore_errors=True)
            with corpus.session() as session:
                session.query(Corpus).update({Corpus.text_normalized: False})
                session.query(PhoneInterval).delete()
                session.query(WordInterval).delete()
                session.query(Pronunciation).delete()
                session.query(Word).delete()
                session.query(Phone).delete()
                session.execute(sqlalchemy.update(Speaker).values(dictionary_id=None))
                session.flush()
                d = session.query(Dictionary).filter(Dictionary.name=='.').first()
                if d is not None:
                    d.delete()
                session.flush()
                session.execute(
                    sqlalchemy.update(CorpusWorkflow).values(
                        done=False, alignments_collected=False, score=None
                    )
                )
                session.execute(Dictionary2Job.delete())
                session.query(Dictionary).delete()
                session.commit()
            corpus.dictionary_setup()
            with corpus.session() as session:
                d = session.query(Dictionary).filter(Dictionary.name==self.dictionary_path.stem).first()
                jobs = session.query(Job).all()
                for j in jobs:
                    j.dictionaries = [d]
                session.execute(
                    sqlalchemy.update(Speaker).values(dictionary_id=d.id)
                )
                session.commit()
            corpus.text_normalized = False
            corpus.normalize_text()
            self.signals.result.emit(corpus)  # Done
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            self.signals.finished.emit()  # Done


class OovCountWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Counting OOVs", *args)

    def set_params(self, corpus: AcousticCorpus):
        self.corpus = corpus

    def run(self):
        try:
            with self.corpus.session() as session:
                session.query(Word).filter(Word.word_type == WordType.oov).delete()
                session.commit()
            self.corpus.text_normalized = False
            self.corpus.normalize_text()
            self.signals.result.emit(self.corpus)  # Done
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            self.signals.finished.emit()  # Done


class ImportAcousticModelWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Importing acoustic model", *args)

    def set_params(self, model_path: str):
        self.model_path = model_path

    def run(self):
        if not self.model_path:
            return
        for_transcription = True
        try:
            if str(self.model_path) == "whisper":
                cuda = self.settings.value(self.settings.CUDA)
                run_opts = None
                vad_model = None
                if cuda:
                    run_opts = {"device": "cuda"}
                if FOUND_SPEECHBRAIN:
                    vad_model = MfaVAD.from_hparams(
                        source="speechbrain/vad-crdnn-libriparty",
                        savedir=os.path.join(config.TEMPORARY_DIRECTORY, "models", "VAD"),
                        run_opts=run_opts,
                    )
                vad_options = {
                    "apply_energy_VAD": False,
                    "double_check": False,
                    "activation_th": 0.5,
                    "deactivation_th": 0.25,
                    "en_activation_th": 0.5,
                    "en_deactivation_th": 0.4,
                    "speech_th": 0.5,
                    "close_th": 0.333,
                    "len_th": 0.333,
                }
                acoustic_model = load_model(
                    "large-v3",
                    device="cuda" if cuda else "cpu",
                    download_root=os.path.join(
                        config.TEMPORARY_DIRECTORY,
                        "models",
                        "Whisper",
                    ),
                    threads=config.NUM_JOBS,
                    vad_model=vad_model,
                    vad_options=vad_options,
                )
            elif str(self.model_path) == "speechbrain":
                acoustic_model = "speechbrain"
            else:
                for_transcription = False
                acoustic_model = AcousticModel(self.model_path)
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit((acoustic_model, for_transcription))  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class ImportLanguageModelWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Importing language model", *args)

    def set_params(self, model_path: str):
        self.model_path = model_path

    def run(self):
        if not self.model_path:
            return
        try:
            language_model = LanguageModel(self.model_path)
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(language_model)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class ImportG2PModelWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Importing G2P model", *args)

    def set_params(self, model_path: str):
        self.model_path = model_path

    def run(self):
        if not self.model_path:
            return
        try:
            generator = Generator(g2p_model_path=self.model_path, num_pronunciations=5)
            generator.setup()
        except shutil.ReadError:
            self.signals.result.emit(None)
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(generator)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class ImportIvectorExtractorWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Importing ivector extractor", *args)

    def set_params(self, model_path: str):
        self.model_path = model_path

    def run(self):
        if not self.model_path:
            return
        try:
            if str(self.model_path) in {"speechbrain", "pyannote"}:
                model = str(self.model_path)
            else:
                model = IvectorExtractorModel(self.model_path)
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(model)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class AlignUtteranceWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Aligning utterance", *args)
        self.corpus_model: typing.Optional[CorpusModel] = None
        self.utterance_id: typing.Optional[int] = None

    def set_params(self, corpus_model: CorpusModel, utterance_id: int):
        self.corpus_model = corpus_model
        self.utterance_id = utterance_id

    def run(self):
        self.settings.sync()
        self.corpus_model.check_align_lexicon_compiler()
        try:
            with self.corpus_model.corpus.session() as session:
                utterance = (
                    session.query(Utterance)
                    .options(
                        joinedload(Utterance.file, innerjoin=True).joinedload(
                            File.sound_file, innerjoin=True
                        ),
                        joinedload(Utterance.speaker, innerjoin=True),
                    )
                    .get(self.utterance_id)
                )
                session.query(PhoneInterval).filter(
                    PhoneInterval.utterance_id == utterance.id
                ).delete(synchronize_session=False)
                session.flush()
                session.query(WordInterval).filter(
                    WordInterval.utterance_id == utterance.id
                ).delete(synchronize_session=False)
                session.flush()
                ctm = align_utterance_online(
                    self.corpus_model.acoustic_model,
                    utterance.to_kalpy(),
                    self.corpus_model.align_lexicon_compiler,
                )
                update_utterance_intervals(session, utterance, ctm)
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(self.utterance_id)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class TranscribeUtteranceWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Transcribing utterance", *args)
        self.corpus_model: typing.Optional[CorpusModel] = None
        self.utterance_id: typing.Optional[int] = None

    def set_params(self, corpus_model: CorpusModel, utterance_id: int):
        self.corpus_model = corpus_model
        self.utterance_id = utterance_id

    def run(self):
        self.settings.sync()
        if isinstance(self.corpus_model.acoustic_model, AcousticModel):
            self.corpus_model.check_align_lexicon_compiler()
        language = Language[self.settings.value(self.settings.LANGUAGE)]
        try:
            with self.corpus_model.corpus.session() as session:
                utterance = (
                    session.query(Utterance)
                    .options(
                        joinedload(Utterance.file, innerjoin=True).joinedload(
                            File.sound_file, innerjoin=True
                        ),
                        joinedload(Utterance.speaker, innerjoin=True),
                    )
                    .get(self.utterance_id)
                )
                if isinstance(self.corpus_model.acoustic_model, AcousticModel):
                    transcription = transcribe_utterance_online(
                        self.corpus_model.acoustic_model,
                        utterance.to_kalpy(),
                        self.corpus_model.align_lexicon_compiler,
                    )
                elif isinstance(self.corpus_model.acoustic_model, MfaFasterWhisperPipeline):
                    self.corpus_model.acoustic_model.set_language(language)
                    transcription = transcribe_utterance_online_whisper(
                        self.corpus_model.acoustic_model,
                        utterance.to_kalpy().segment,
                    )
                else:
                    transcription = transcribe_utterance_online_speechbrain(
                        self.corpus_model.acoustic_model,
                        utterance.to_kalpy(),
                    )
                utterance.transcription_text = transcription
                session.commit()
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(
                (self.utterance_id, transcription)
            )  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class SegmentUtteranceWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Segmenting utterance", *args)
        self.corpus_model: typing.Optional[CorpusModel] = None

    def set_params(self, corpus_model: CorpusModel, utterance_id: int):
        self.corpus_model = corpus_model
        self.utterance_id = utterance_id

    def run(self):
        self.settings.sync()
        g2p_model_path = None
        if self.corpus_model.g2p_model is not None:
            g2p_model_path = self.corpus_model.g2p_model.source
        else:
            self.corpus_model.check_transcribe_lexicon_compiler()
        segmenter = TranscriptionSegmenter(
            acoustic_model_path=self.corpus_model.acoustic_model.source,
            g2p_model_path=g2p_model_path,
            corpus_directory=self.corpus_model.corpus.corpus_directory,
            dictionary_path=self.corpus_model.corpus.dictionary_model.path,
            speechbrain=True,
        )
        try:
            segmenter.inspect_database()
            segmenter.corpus_output_directory = self.corpus_model.corpus.corpus_output_directory
            segmenter.dictionary_output_directory = (
                self.corpus_model.corpus.dictionary_output_directory
            )
            segmenter.non_silence_phones = self.corpus_model.corpus.non_silence_phones
            segmenter.acoustic_model = self.corpus_model.acoustic_model
            segmenter.g2p_model = self.corpus_model.g2p_model
            if self.corpus_model.g2p_model is not None:
                segmenter.lexicon_compilers = {
                    x: self.corpus_model.transcribe_lexicon_compiler
                    for x in self.corpus_model.corpus.dictionary_base_names.keys()
                }
            sub_utterances = segmenter.segment_transcript(self.utterance_id)
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(
                (self.utterance_id, sub_utterances)
            )  # Return the result of the processing
        finally:
            segmenter.cleanup_logger()
            self.signals.finished.emit()  # Done


class TrimUtteranceWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Trimming utterance", *args)
        self.corpus_model: typing.Optional[CorpusModel] = None
        self.vad_model: typing.Optional[MfaVAD] = None
        self.utterance_id = None

    def set_vad_model(self, vad_model):
        self.vad_model = vad_model

    def set_params(self, corpus_model: CorpusModel, utterance_id: int):
        self.corpus_model = corpus_model
        self.utterance_id = utterance_id

    def run(self):
        self.settings.sync()
        if self.vad_model is None:
            segmenter = VadSegmenter(
                corpus_directory=self.corpus_model.corpus.corpus_directory,
            )
            try:
                segmenter.inspect_database()
                segments = segmenter.segment_utterance(self.utterance_id, allow_empty=False)
                begin = segments[0].begin
                end = segments[-1].end
            except Exception:
                exctype, value = sys.exc_info()[:2]
                self.signals.error.emit((exctype, value, traceback.format_exc()))
            else:
                self.signals.result.emit(
                    (self.utterance_id, begin, end)
                )  # Return the result of the processing
            finally:
                segmenter.cleanup_logger()
                self.signals.finished.emit()  # Done
        else:
            try:
                with self.corpus_model.session() as session:
                    utterance = full_load_utterance(session, self.utterance_id)
                    segment = utterance.to_kalpy().segment
                    # Compute the boundaries of the speech segments
                    segments = self.vad_model.segment_utterance(segment, apply_energy_vad=True)
                    try:
                        begin = segments[0].begin
                        end = segments[-1].end
                    except IndexError:
                        begin, end = segment.begin, segment.end
            except Exception:
                exctype, value = sys.exc_info()[:2]
                self.signals.error.emit((exctype, value, traceback.format_exc()))
            else:
                self.signals.result.emit(
                    (self.utterance_id, begin, end)
                )  # Return the result of the processing
            finally:
                self.signals.finished.emit()  # Done


class AlignmentWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Aligning", *args)
        self.corpus: typing.Optional[AcousticCorpusWithPronunciations] = None
        self.dictionary: typing.Optional[MultispeakerDictionary] = None
        self.acoustic_model: typing.Optional[AcousticModel] = None
        self.verify_transcripts = False
        self.parameters = {}

    def set_params(
        self,
        corpus: AcousticCorpusWithPronunciations,
        acoustic_model: AcousticModel,
        verify_transcripts: bool = False,
        parameters=None,
    ):
        self.corpus = corpus
        self.acoustic_model = acoustic_model
        self.parameters = parameters
        self.verify_transcripts = verify_transcripts
        if self.parameters is None:
            self.parameters = {}

    def run(self):
        self.settings.sync()
        aligner = PretrainedAligner(
            acoustic_model_path=self.acoustic_model.source,
            corpus_directory=self.corpus.corpus_directory,
            dictionary_path=self.corpus.dictionary_model.path,
            **self.parameters,
        )
        try:
            logger.info("Resetting any previous alignments...")
            with self.corpus.session() as session:
                if self.verify_transcripts:
                    workflow_types = [WorkflowType.transcript_verification]
                else:
                    workflow_types = [WorkflowType.online_alignment, WorkflowType.alignment]
                alignment_workflows = [
                    x
                    for x, in session.query(CorpusWorkflow.id).filter(
                        CorpusWorkflow.workflow_type.in_(workflow_types)
                    )
                ]

                session.query(PhoneInterval).delete(synchronize_session=False)
                session.query(WordInterval).delete(synchronize_session=False)
                session.query(CorpusWorkflow).filter(
                    CorpusWorkflow.id.in_(alignment_workflows)
                ).delete(synchronize_session=False)
                session.execute(
                    sqlalchemy.update(Corpus).values(
                        features_generated=False,
                        text_normalized=False,
                        alignment_evaluation_done=False,
                        alignment_done=False,
                    )
                )
                session.execute(sqlalchemy.update(Speaker).values(cmvn=None, fmllr=False))
                if self.verify_transcripts:
                    session.execute(
                        sqlalchemy.update(Utterance).values(
                            features=None,
                            ignored=False,
                            alignment_log_likelihood=None,
                            duration_deviation=None,
                            speech_log_likelihood=None,
                            transcription_text=None,
                        )
                    )
                else:
                    session.execute(
                        sqlalchemy.update(Utterance).values(
                            features=None,
                            ignored=False,
                            alignment_log_likelihood=None,
                            duration_deviation=None,
                            speech_log_likelihood=None,
                        )
                    )
                session.commit()
            logger.info("Reset complete!")
            aligner.inspect_database()
            aligner.clean_working_directory()
            aligner.corpus_output_directory = self.corpus.corpus_output_directory
            aligner.dictionary_output_directory = self.corpus.dictionary_output_directory
            aligner.acoustic_model = self.acoustic_model
            if self.verify_transcripts:
                aligner.verify_transcripts()
            else:
                aligner.align()
                aligner.analyze_alignments()
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            aligner.cleanup_logger()
            self.signals.finished.emit()  # Done


class ComputeIvectorWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Computing ivectors", *args)
        self.corpus_model: typing.Optional[CorpusModel] = None
        self.reset = False
        self.parameters = {}

    def set_params(
        self,
        corpus_model: CorpusModel,
        reset=False,
        parameters=None,
    ):
        self.corpus_model = corpus_model
        self.parameters = parameters
        self.reset = reset
        if self.parameters is None:
            self.parameters = {}

    def run(self):
        self.settings.sync()
        diarizer = SpeakerDiarizer(
            ivector_extractor_path=self.corpus_model.ivector_extractor.source
            if self.corpus_model.ivector_extractor not in {"speechbrain", "pyannote"}
            else self.corpus_model.ivector_extractor,
            corpus_directory=self.corpus_model.corpus.corpus_directory,
            cuda=self.settings.value(self.settings.CUDA),
            **self.parameters,
        )
        try:
            logger.debug("Beginning ivector computation")
            if self.reset:
                logger.info("Resetting ivectors...")
                self.corpus_model.corpus.reset_features()
            else:
                time.sleep(1.0)
                with self.corpus_model.corpus.session() as session:
                    logger.debug("Dropping indexes...")
                    session.execute(
                        sqlalchemy.text("DROP INDEX IF EXISTS utterance_xvector_index;")
                    )
                    session.execute(sqlalchemy.text("DROP INDEX IF EXISTS speaker_xvector_index;"))
                    session.execute(
                        sqlalchemy.text("DROP INDEX IF EXISTS utterance_ivector_index;")
                    )
                    session.execute(sqlalchemy.text("DROP INDEX IF EXISTS speaker_ivector_index;"))
                    session.execute(
                        sqlalchemy.text("DROP INDEX IF EXISTS utterance_plda_vector_index;")
                    )
                    session.execute(
                        sqlalchemy.text("DROP INDEX IF EXISTS speaker_plda_vector_index;")
                    )
                    session.commit()
            diarizer.inspect_database()
            diarizer.initialize_jobs()
            diarizer.corpus_output_directory = self.corpus_model.corpus.corpus_output_directory
            diarizer.dictionary_output_directory = (
                self.corpus_model.corpus.dictionary_output_directory
            )
            diarizer.setup()
            # with diarizer.session() as session:
            #    speaker_space = load_speaker_space(session)
            # self.signals.result.emit(speaker_space)
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            diarizer.cleanup_logger()
            self.signals.finished.emit()  # Done


class ComputePldaWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Computing PLDA", *args)
        self.corpus: typing.Optional[AcousticCorpusWithPronunciations] = None
        self.ivector_extractor: typing.Optional[IvectorExtractorModel] = None
        self.reset = False

    def set_params(
        self,
        corpus: AcousticCorpusWithPronunciations,
        ivector_extractor: IvectorExtractorModel,
        reset=False,
        parameters=None,
    ):
        self.corpus = corpus
        self.ivector_extractor = ivector_extractor
        self.parameters = parameters
        self.reset = reset
        if self.parameters is None:
            self.parameters = {}

    def run(self):
        self.settings.sync()
        diarizer = SpeakerDiarizer(
            ivector_extractor_path=self.ivector_extractor.source
            if self.ivector_extractor not in {"speechbrain", "pyannote"}
            else self.ivector_extractor,
            corpus_directory=self.corpus.corpus_directory,
            cuda=self.settings.value(self.settings.CUDA),
            **self.parameters,
        )
        self.corpus.session.close_all()
        try:
            diarizer.inspect_database()
            diarizer.corpus_output_directory = self.corpus.corpus_output_directory
            diarizer.dictionary_output_directory = self.corpus.dictionary_output_directory
            diarizer.compute_plda(minimum_utterance_count=2)
            with diarizer.session() as session:
                speaker_plda = load_speaker_plda(session, diarizer.plda)
            self.signals.result.emit((diarizer.plda, speaker_plda))
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            diarizer.cleanup_logger()
            self.signals.finished.emit()  # Done


class ClusterUtterancesWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Clustering utterances", *args)
        self.corpus: typing.Optional[AcousticCorpusWithPronunciations] = None
        self.ivector_extractor: typing.Optional[IvectorExtractorModel] = None

    def set_params(
        self,
        corpus: AcousticCorpusWithPronunciations,
        ivector_extractor: IvectorExtractorModel,
        parameters=None,
    ):
        self.corpus = corpus
        self.ivector_extractor = ivector_extractor
        self.parameters = parameters
        if self.parameters is None:
            self.parameters = {}

    def run(self):
        self.settings.sync()
        self.parameters["cluster_type"] = "kmeans"
        self.parameters["distance_threshold"] = None
        self.parameters["metric"] = self.settings.value(self.settings.CLUSTERING_METRIC)
        self.parameters["expected_num_speakers"] = self.corpus.num_speakers
        diarizer = SpeakerDiarizer(
            ivector_extractor_path=self.ivector_extractor.source
            if self.ivector_extractor not in {"speechbrain", "pyannote"}
            else self.ivector_extractor,
            corpus_directory=self.corpus.corpus_directory,
            cuda=self.settings.value(self.settings.CUDA),
            cluster=True,
            use_pca=False,
            **self.parameters,
        )
        try:
            logger.debug("Beginning clustering")

            diarizer.inspect_database()
            diarizer.corpus_output_directory = self.corpus.corpus_output_directory
            diarizer.dictionary_output_directory = self.corpus.dictionary_output_directory
            if not diarizer.has_any_ivectors():
                diarizer.setup()
            else:
                diarizer.initialized = True
                diarizer.create_new_current_workflow(WorkflowType.speaker_diarization)
            diarizer.cluster_utterances()
            with diarizer.session() as session:
                session.query(File).update(modified=True)
                session.commit()
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            diarizer.cleanup_logger()
            self.signals.finished.emit()  # Done


class ClassifySpeakersWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Clustering utterances", *args)
        self.corpus: typing.Optional[AcousticCorpusWithPronunciations] = None
        self.ivector_extractor: typing.Optional[IvectorExtractorModel] = None

    def set_params(
        self,
        corpus: AcousticCorpusWithPronunciations,
        ivector_extractor: IvectorExtractorModel,
        parameters=None,
    ):
        self.corpus = corpus
        self.ivector_extractor = ivector_extractor
        self.parameters = parameters
        if self.parameters is None:
            self.parameters = {}

    def run(self):
        self.settings.sync()
        diarizer = SpeakerDiarizer(
            ivector_extractor_path=self.ivector_extractor.source
            if self.ivector_extractor not in {"speechbrain", "pyannote"}
            else self.ivector_extractor,
            corpus_directory=self.corpus.corpus_directory,  # score_threshold = 0.5,
            cluster=False,
            cuda=self.settings.value(self.settings.CUDA),
            **self.parameters,
        )
        try:
            logger.debug("Beginning speaker classification")
            diarizer.inspect_database()
            diarizer.corpus_output_directory = self.corpus.corpus_output_directory
            diarizer.dictionary_output_directory = self.corpus.dictionary_output_directory
            diarizer.classify_speakers()
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            diarizer.cleanup_logger()
            self.signals.finished.emit()  # Done


class AlignmentEvaluationWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Evaluating alignments", *args)
        self.corpus: typing.Optional[AcousticCorpusWithPronunciations] = None
        self.dictionary: typing.Optional[MultispeakerDictionary] = None
        self.acoustic_model: typing.Optional[AcousticModel] = None

    def set_params(
        self,
        corpus: AcousticCorpusWithPronunciations,
        acoustic_model: AcousticModel,
        custom_mapping_path: str,
    ):
        self.corpus = corpus
        self.acoustic_model = acoustic_model
        self.custom_mapping_path = custom_mapping_path

    def run(self):
        self.settings.sync()
        aligner = PretrainedAligner(
            acoustic_model_path=self.acoustic_model.source,
            corpus_directory=self.corpus.corpus_directory,
            dictionary_path=self.corpus.dictionary_model.path,
        )
        try:
            self.corpus.alignment_evaluation_done = False
            with self.corpus.session() as session:
                session.execute(sqlalchemy.update(Corpus).values(alignment_evaluation_done=False))
                session.execute(
                    sqlalchemy.update(Utterance).values(
                        phone_error_rate=None, alignment_score=None
                    )
                )
                session.commit()
            aligner.inspect_database()
            aligner.corpus_output_directory = self.corpus.corpus_output_directory
            aligner.dictionary_output_directory = self.corpus.dictionary_output_directory
            aligner.acoustic_model = self.acoustic_model
            mapping = None
            if self.custom_mapping_path and os.path.exists(self.custom_mapping_path):
                with open(self.custom_mapping_path, "r", encoding="utf8") as f:
                    mapping = yaml.safe_load(f)
            aligner.evaluate_alignments(mapping=mapping)
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            aligner.cleanup_logger()
            self.signals.finished.emit()  # Done


class TranscriptionWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Transcribing", *args)
        self.corpus: typing.Optional[
            typing.Union[AcousticCorpus, AcousticCorpusWithPronunciations]
        ] = None
        self.acoustic_model: typing.Optional[AcousticModel] = None
        self.language_model: typing.Optional[LanguageModel] = None

    def set_params(
        self,
        corpus: AcousticCorpusWithPronunciations,
        acoustic_model: AcousticModel,
        language_model: LanguageModel,
    ):
        self.corpus = corpus
        self.acoustic_model = acoustic_model
        self.language_model = language_model

    def run(self):
        self.settings.sync()
        transcriber = Transcriber(
            acoustic_model_path=self.acoustic_model.source,
            language_model_path=self.language_model.source,
            corpus_directory=self.corpus.corpus_directory,
            dictionary_path=self.corpus.dictionary_model.path,
            evaluation_mode=True,
            max_language_model_weight=17,
            min_language_model_weight=16,
            word_insertion_penalties=[1.0],
        )
        try:
            with self.corpus.session() as session:
                session.query(PhoneInterval).delete(synchronize_session="fetch")
                session.query(WordInterval).delete(synchronize_session="fetch")
                session.query(CorpusWorkflow).filter(
                    CorpusWorkflow.workflow_type == WorkflowType.transcription
                ).delete()
                session.query(Utterance).update({Utterance.transcription_text: None})
                session.commit()
            transcriber.inspect_database()
            transcriber.corpus_output_directory = self.corpus.corpus_output_directory
            transcriber.dictionary_output_directory = self.corpus.dictionary_output_directory
            transcriber.acoustic_model = self.acoustic_model
            transcriber.language_model = self.language_model
            transcriber.setup()
            transcriber.transcribe()
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            transcriber.cleanup_logger()
            self.signals.finished.emit()  # Done


class ValidationWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Validating", *args)
        self.corpus: typing.Optional[AcousticCorpusWithPronunciations] = None
        self.acoustic_model: typing.Optional[AcousticModel] = None
        self.frequent_word_count = 100
        self.test_transcriptions = True

    def set_params(
        self,
        corpus: AcousticCorpusWithPronunciations,
        acoustic_model: AcousticModel,
        target_num_ngrams,
        test_transcriptions=True,
    ):
        self.corpus = corpus
        self.acoustic_model = acoustic_model
        self.target_num_ngrams = target_num_ngrams
        self.test_transcriptions = test_transcriptions

    def run(self):
        self.settings.sync()
        config.CLEAN = False
        validator = PretrainedValidator(
            acoustic_model_path=self.acoustic_model.source,
            corpus_directory=self.corpus.corpus_directory,
            dictionary_path=self.corpus.dictionary_model.path,
            test_transcriptions=self.test_transcriptions,
            target_num_ngrams=self.target_num_ngrams,
            first_max_active=750,
        )
        try:
            with self.corpus.session() as session:
                session.query(PhoneInterval).delete(synchronize_session="fetch")
                session.query(WordInterval).delete(synchronize_session="fetch")
                session.query(CorpusWorkflow).filter(
                    CorpusWorkflow.workflow_type == WorkflowType.per_speaker_transcription
                ).delete()
                session.query(Utterance).update({Utterance.transcription_text: None})
                session.commit()
            validator.inspect_database()
            validator.corpus_output_directory = self.corpus.corpus_output_directory
            validator.dictionary_output_directory = self.corpus.dictionary_output_directory
            validator.acoustic_model = self.acoustic_model
            validator.create_new_current_workflow(WorkflowType.alignment)
            validator.setup()
            validator.align()
            validator.test_utterance_transcriptions()
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            validator.cleanup_logger()
            self.signals.finished.emit()  # Done
