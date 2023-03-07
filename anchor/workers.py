from __future__ import annotations

import collections
import csv
import datetime
import logging
import multiprocessing as mp
import os
import pickle
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
import typing
from io import BytesIO
from pathlib import Path
from queue import Queue
from threading import Lock

import librosa
import numpy as np
import psycopg2.errors
import resampy
import soundfile
import soundfile as sf
import sqlalchemy
import tqdm
import yaml
from montreal_forced_aligner.alignment import PretrainedAligner
from montreal_forced_aligner.config import (
    GLOBAL_CONFIG,
    IVECTOR_DIMENSION,
    MEMORY,
    MFA_PROFILE_VARIABLE,
    PLDA_DIMENSION,
    XVECTOR_DIMENSION,
)
from montreal_forced_aligner.corpus.acoustic_corpus import (
    AcousticCorpus,
    AcousticCorpusWithPronunciations,
)
from montreal_forced_aligner.corpus.classes import FileData
from montreal_forced_aligner.corpus.features import score_plda
from montreal_forced_aligner.data import (
    ClusterType,
    DatasetType,
    DistanceMetric,
    ManifoldAlgorithm,
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
    PhoneInterval,
    Pronunciation,
    SoundFile,
    Speaker,
    SpeakerOrdering,
    TextFile,
    Utterance,
    Word,
    WordInterval,
    bulk_update,
)
from montreal_forced_aligner.diarization.multiprocessing import cluster_matrix, visualize_clusters
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
from montreal_forced_aligner.transcription import Transcriber
from montreal_forced_aligner.utils import (
    ProgressCallback,
    Stopped,
    inspect_database,
    read_feats,
    thirdparty_binary,
)
from montreal_forced_aligner.vad.multiprocessing import segment_utterance
from montreal_forced_aligner.vad.segmenter import TranscriptionSegmenter
from montreal_forced_aligner.validation.corpus_validator import PretrainedValidator
from PySide6 import QtCore
from sqlalchemy.orm import joinedload, selectinload, subqueryload

import anchor.db
from anchor.settings import AnchorSettings

if typing.TYPE_CHECKING:
    from anchor.models import TextFilterQuery

M_LOG_2PI = 1.8378770664093454835606594728112

logger = logging.getLogger("anchor")


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

    def __init__(self, fn, *args, use_mp=False, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.name = fn.__name__
        self.args = args
        self.kwargs = kwargs
        self.use_mp = use_mp
        self.stopped = Stopped()
        self.signals = WorkerSignals(fn.__name__)

        # Add the callback to our kwargs
        if not self.use_mp:
            self.kwargs["progress_callback"] = ProgressCallback(
                callback=self.signals.progress.emit, total_callback=self.signals.total.emit
            )
        self.kwargs["stopped"] = self.stopped

    def cancel(self):
        self.stopped.stop()

    @QtCore.Slot()
    def run(self):
        """
        Initialise the runner function with passed args, kwargs.
        """

        # Retrieve args/kwargs here; and fire processing using them
        try:
            if self.use_mp:
                queue = mp.Queue()
                p = mp.Process(target=self.fn, args=(queue, *self.args), kwargs=self.kwargs)
                p.start()
                result = queue.get()
                p.join()
                if isinstance(result, Exception):
                    raise result
            else:
                result = self.fn(*self.args, **self.kwargs)
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
        job_q: Queue,
        return_q: Queue,
        done_adding: Stopped,
        done_processing: Stopped,
        stopped: Stopped,
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
        self.stopped = stopped

    def run(self):
        with self.session() as session:
            c = session.query(Corpus).first()
            while True:
                try:
                    s_id, s_ivector = self.job_q.get(timeout=3)
                except queue.Empty:
                    if self.done_adding.stop_check():
                        break
                    if self.stopped.stop_check():
                        break
                    continue
                if self.stopped.stop_check():
                    continue
                suggested_query = session.query(
                    Speaker.id,
                ).order_by(c.speaker_ivector_column.cosine_distance(s_ivector))

                suggested_query = suggested_query.filter(
                    c.speaker_ivector_column.cosine_distance(s_ivector) <= self.threshold
                )
                r = [x[0] for x in suggested_query if x[0] != s_id]
                self.return_q.put((s_id, r))
        self.done_processing.stop()


class SpeakerQueryThread(threading.Thread):
    def __init__(
        self,
        Session,
        job_q: Queue,
        done_adding: Stopped,
        stopped: Stopped,
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
            query = session.query(
                Speaker.id,
                c.speaker_ivector_column,
            ).order_by(Speaker.id)
            query_count = query.count()
            if self.progress_callback is not None:
                self.progress_callback.update_total(query_count)
            for s_id, s_ivector in query:
                if self.stopped is not None and self.stopped.stop_check():
                    break
                self.job_q.put((s_id, s_ivector))
        self.done_adding.stop()


def closest_speaker_function(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    utterance_id = kwargs.get("utterance_id", None)
    num_speakers = kwargs.get("num_speakers", 10)
    data = {}
    with Session() as session:
        c = session.query(Corpus).first()
        if utterance_id is not None:
            ivector = (
                session.query(c.utterance_ivector_column)
                .filter(Utterance.id == utterance_id)
                .first()[0]
            )

        else:
            ivector = kwargs.get("ivector", None)
        if ivector is None:
            return {}
        query = (
            session.query(
                Speaker.id, Speaker.name, c.speaker_ivector_column.cosine_distance(ivector)
            )
            .join(Speaker.utterances)
            .filter(c.speaker_ivector_column != None)  # noqa
            .group_by(Speaker.id)
            .having(sqlalchemy.func.count() > 2)
            .order_by(c.speaker_ivector_column.cosine_distance(ivector))
            .limit(num_speakers)
        )
        speaker_ids = []
        speaker_names = []
        distances = []
        for s_id, name, distance in query:
            data[s_id] = name
            speaker_ids.append(s_id)
            speaker_names.append(name)
            distances.append(distance)
        data = {
            speaker_ids[i]: f"{speaker_names[i]} ({distances[i]:.3f})"
            for i in range(len(speaker_ids))
        }
    return data, utterance_id


def merge_speakers_function(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    speaker_id = kwargs.get("speaker_id", None)
    threshold = kwargs.get("threshold", None)
    speaker_counts = collections.Counter()
    deleted = set()
    with Session() as session:
        c = session.query(Corpus).first()
        data = []
        query_count = session.query(Speaker.id).count()
        if progress_callback is not None:
            progress_callback.update_total(query_count)
        if speaker_id is None:
            num_jobs = GLOBAL_CONFIG.profiles["anchor"].num_jobs
            job_queue = Queue()
            return_queue = Queue()
            done_adding = Stopped()
            done_processing = Stopped()
            query_thread = SpeakerQueryThread(
                Session, job_queue, done_adding, stopped, progress_callback
            )
            query_thread.start()
            threads = []
            for i in range(num_jobs):
                threads.append(
                    ClosestSpeakerThread(
                        Session,
                        threshold,
                        job_queue,
                        return_queue,
                        done_adding,
                        done_processing,
                        stopped,
                    )
                )
                threads[i].start()
            while True:
                try:
                    r = return_queue.get(timeout=2)
                except queue.Empty:
                    if done_processing.stop_check():
                        break
                    if stopped.stop_check():
                        break
                    continue
                suggested_id, to_merge = r
                if suggested_id in deleted:
                    continue
                if progress_callback is not None:
                    progress_callback.increment_progress(1)
                if not to_merge:
                    continue
                for s_id in to_merge:
                    if stopped is not None and stopped.stop_check():
                        session.rollback()
                        return
                    file_ids = [
                        x
                        for x, in session.query(SpeakerOrdering.c.file_id).filter(
                            SpeakerOrdering.c.speaker_id == s_id
                        )
                    ]
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
                    session.execute(sqlalchemy.insert(SpeakerOrdering), speaker_ordering_mapping)
                    session.query(File).filter(File.id.in_(file_ids)).update({File.modified: True})
                session.query(Speaker).filter(Speaker.id.in_(to_merge)).delete()
                deleted.update(to_merge)
                if progress_callback is not None:
                    query_count -= len(to_merge)
                    progress_callback.update_total(query_count)
                session.commit()

            query_thread.join()
            for t in threads:
                t.join()
        else:
            ivector = (
                session.query(c.speaker_ivector_column).filter(Speaker.id == speaker_id).first()[0]
            )
            query = (
                session.query(Speaker.id)
                .filter(Speaker.id != speaker_id)
                .filter(c.speaker_ivector_column.cosine_distance(ivector) <= threshold)
            )
            query_count = query.count()
            if progress_callback is not None:
                progress_callback.update_total(query_count)
            for (s_id,) in query:
                if stopped is not None and stopped.stop_check():
                    session.rollback()
                    return
                data.append((s_id, speaker_id))
                if progress_callback is not None:
                    progress_callback.increment_progress(1)
            updated_speakers = {}
            if progress_callback is not None:
                progress_callback.update_total(len(data))
                progress_callback.set_progress(0)
            for s_id, suggested_id in data:
                if stopped is not None and stopped.stop_check():
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
                if progress_callback is not None:
                    progress_callback.increment_progress(1)
            session.commit()
            sq = (
                session.query(Speaker.id, sqlalchemy.func.count().label("utterance_count"))
                .outerjoin(Speaker.utterances)
                .group_by(Speaker.id)
                .subquery()
            )
            sq2 = sqlalchemy.select(sq.c.id).where(sq.c.utterance_count == 0)
            session.query(Speaker).filter(Speaker.id.in_(sq2)).delete(synchronize_session="fetch")
            session.commit()


class ClosestUtteranceThread(threading.Thread):
    def __init__(
        self,
        Session,
        threshold,
        job_q: Queue,
        return_q: Queue,
        done_adding: Stopped,
        done_processing: Stopped,
        stopped: Stopped,
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
        self.stopped = stopped

    def run(self):
        deleted = set()
        with self.session() as session:
            c = session.query(Corpus).first()
            while True:
                try:
                    u_id, u_text, u_ivector, file_name = self.job_q.get(timeout=3)
                except queue.Empty:
                    if self.done_adding.stop_check():
                        break
                    if self.stopped.stop_check():
                        break
                    continue
                if self.stopped.stop_check():
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
        self.done_processing.stop()


class UtteranceQueryThread(threading.Thread):
    def __init__(
        self,
        Session,
        job_q: Queue,
        done_adding: Stopped,
        stopped: Stopped,
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
                session.query(Utterance.id, Utterance.text, c.utterance_ivector_column, File.name)
                .join(Utterance.file)
                .filter(c.utterance_ivector_column != None)  # noqa
                .order_by(Utterance.id.desc())
            )
            query_count = query.count()
            if self.progress_callback is not None:
                self.progress_callback.update_total(query_count)
            for row in query:
                if self.stopped is not None and self.stopped.stop_check():
                    break
                self.job_q.put(row)
        self.done_adding.stop()


def duplicate_files_query(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    threshold = kwargs.get("threshold", 0.01)
    working_directory = kwargs.get("working_directory")
    to_delete = set()
    original_files = set()
    info_path = os.path.join(working_directory, "duplicate_info.tsv")
    with mfa_open(info_path, "w") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["original_file", "original_text", "duplicate_file", "duplicate_text"],
            delimiter="\t",
        )

        num_jobs = GLOBAL_CONFIG.profiles["anchor"].num_jobs
        job_queue = Queue()
        return_queue = Queue()
        done_adding = Stopped()
        done_processing = Stopped()
        query_thread = UtteranceQueryThread(
            Session, job_queue, done_adding, stopped, progress_callback
        )
        query_thread.start()
        threads = []
        for i in range(num_jobs):
            threads.append(
                ClosestUtteranceThread(
                    Session,
                    threshold,
                    job_queue,
                    return_queue,
                    done_adding,
                    done_processing,
                    stopped,
                )
            )
            threads[i].start()
        while True:
            try:
                r = return_queue.get(timeout=2)
            except queue.Empty:
                if done_processing.stop_check():
                    break
                if stopped.stop_check():
                    break
                continue
            u_id, u_text, orig_file_name, duplicates = r
            if progress_callback is not None:
                progress_callback.increment_progress(1)
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


def speaker_comparison_query(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    speaker_id = kwargs.get("speaker_id", None)
    threshold = kwargs.get("threshold", None)
    metric = kwargs.get("metric", DistanceMetric.cosine)
    data = []
    speaker_indices = []
    suggested_indices = []
    limit = kwargs.get("limit", 100)
    offset = kwargs.get("current_offset", 100)
    if progress_callback is not None:
        progress_callback.update_total(limit)
    if metric is DistanceMetric.plda:
        working_directory = kwargs.get("working_directory", None)
        plda_transform_path = os.path.join(working_directory, "plda.pkl")
        try:
            with open(plda_transform_path, "rb") as f:
                plda = pickle.load(f)
        except Exception:
            metric = DistanceMetric.cosine
    with Session() as session:
        c = session.query(Corpus).first()
        if c.plda_calculated:
            dim = PLDA_DIMENSION
        elif c.xvectors_loaded:
            dim = XVECTOR_DIMENSION
        else:
            dim = IVECTOR_DIMENSION
        if speaker_id is None:
            query = (
                session.query(
                    Speaker.id,
                    Speaker.name,
                    c.speaker_ivector_column,
                    sqlalchemy.func.count().label("utterance_count"),
                )
                .join(Speaker.utterances)
                .filter(c.speaker_ivector_column != None)  # noqa
                .group_by(Speaker.id)
                .having(sqlalchemy.func.count() > 2)
                .order_by(sqlalchemy.func.random())
            )
            if threshold is None:
                query = query.limit(limit).offset(offset)
            else:
                query = query.limit(limit * 1000)
            found = set()
            for i, (s_id, s_name, s_ivector, utterance_count) in enumerate(query):
                if stopped is not None and stopped.stop_check():
                    return

                if metric is DistanceMetric.plda:
                    suggested_query = (
                        session.query(Speaker.id, Speaker.name, c.speaker_ivector_column)
                        .filter(Speaker.id != s_id, c.speaker_ivector_column != None)  # noqa
                        .order_by(c.speaker_ivector_column.cosine_distance(s_ivector))
                    )
                    r = suggested_query.limit(100).all()
                    test_ivectors = np.empty((len(r), dim))
                    suggested_ids = []
                    suggested_names = []
                    for i, (suggested_id, suggested_name, suggested_ivector) in enumerate(r):
                        test_ivectors[i, :] = suggested_ivector
                        suggested_ids.append(suggested_id)
                        suggested_names.append(suggested_name)
                    train_ivectors = s_ivector[np.newaxis, :]
                    counts = np.array([utterance_count])[:, np.newaxis]
                    distance_matrix = score_plda(
                        train_ivectors, test_ivectors, plda, normalize=False, counts=counts
                    )
                    index = distance_matrix.argmax(axis=1)[0]
                    suggested_name = suggested_names[index]
                    suggested_id = suggested_ids[index]
                    log_likelihood_ratio = distance_matrix[index, 0]
                    if log_likelihood_ratio < threshold:
                        continue
                    data.append([s_name, suggested_name, log_likelihood_ratio])
                    speaker_indices.append(s_id)
                    suggested_indices.append(suggested_id)
                else:
                    suggested_query = (
                        session.query(
                            Speaker.id,
                            Speaker.name,
                            c.speaker_ivector_column.cosine_distance(s_ivector),
                        )
                        .filter(Speaker.id != s_id)
                        .filter(c.speaker_ivector_column != None)  # noqa
                        .order_by(c.speaker_ivector_column.cosine_distance(s_ivector))
                    )
                    if threshold is not None:
                        suggested_query = suggested_query.filter(
                            c.speaker_ivector_column.cosine_distance(s_ivector) <= threshold
                        )
                    r = suggested_query.limit(1).first()
                    if r is None:
                        continue

                    suggested_id, suggested_name, distance = r
                    key = frozenset([s_id, suggested_id])
                    if key in found:
                        continue
                    found.add(key)
                    suggested_count = (
                        session.query(sqlalchemy.func.count().label("utterance_count"))
                        .filter(Utterance.speaker_id == suggested_id)
                        .scalar()
                    )
                    if not suggested_count:
                        continue
                    if suggested_count < utterance_count:
                        s_name, suggested_name = suggested_name, s_name
                        s_id, suggested_id = suggested_id, s_id
                    data.append([s_name, suggested_name, distance])
                    speaker_indices.append(s_id)
                    suggested_indices.append(suggested_id)
                if progress_callback is not None:
                    progress_callback.increment_progress(1)
                if len(data) == limit:
                    break
        else:
            ivector, speaker_name = (
                session.query(c.speaker_ivector_column, Speaker.name)
                .filter(Speaker.id == speaker_id)
                .first()
            )
            query = (
                session.query(
                    Speaker.id,
                    Speaker.name,
                    c.speaker_ivector_column,
                    c.speaker_ivector_column.cosine_distance(ivector).label("distance"),
                )
                .filter(Speaker.id != speaker_id)
                .order_by(c.speaker_ivector_column.cosine_distance(ivector))
                .limit(limit)
                .offset(offset)
            )

            if metric is DistanceMetric.plda:
                test_ivectors = np.empty((limit, dim))
            for i, (s_id, s_name, s_ivector, distance) in enumerate(query):
                if stopped is not None and stopped.stop_check():
                    session.rollback()
                    return
                if progress_callback is not None:
                    progress_callback.increment_progress(1)
                data.append([s_name, speaker_name, distance])
                speaker_indices.append(s_id)
                suggested_indices.append(speaker_id)
                if metric is DistanceMetric.plda:
                    test_ivectors[i, :] = s_ivector
            if metric is DistanceMetric.plda:
                train_ivectors = ivector[np.newaxis, :]
                distance_matrix = score_plda(train_ivectors, test_ivectors, plda, normalize=False)
                for i in range(len(data)):
                    data[i][2] = distance_matrix[i, 0]
        d = np.array([x[2] for x in data])
        if metric is DistanceMetric.plda:
            d *= -1
        indices = np.argsort(d)
        speaker_indices = [speaker_indices[x] for x in indices]
        suggested_indices = [suggested_indices[x] for x in indices]
        data = [data[x] for x in indices]
        return data, speaker_indices, suggested_indices


def find_speaker_utterance_query(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    speaker_id = kwargs.get("speaker_id")
    limit = kwargs.get("limit", 100)
    if progress_callback is not None:
        progress_callback.update_total(limit)
    with Session() as session:
        c = session.query(Corpus).first()
        ivector = (
            session.query(c.speaker_ivector_column).filter(Speaker.id == speaker_id).first()[0]
        )
        query = (
            session.query(Utterance)
            .options(joinedload(Utterance.file, innerjoin=True))
            .filter(Utterance.speaker_id != speaker_id)
            .order_by(c.speaker_ivector_column.cosine_distance(ivector))
            .limit(limit)
            .offset(kwargs.get("current_offset", 0))
        )
        file_ids = []
        utterance_ids = []
        data = []

        for utterance in query:
            if stopped is not None and stopped.stop_check():
                session.rollback()
                return
            if progress_callback is not None:
                progress_callback.increment_progress(1)

            utterance_ids.append(utterance.id)
            file_ids.append(utterance.file_id)
            data.append([utterance.file_name, utterance.begin, utterance.end])
        return data, utterance_ids, file_ids


def find_outlier_utterances_query(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    speaker_id = kwargs.get("speaker_id")
    limit = kwargs.get("limit", 100)
    if progress_callback is not None:
        progress_callback.update_total(limit)
    with Session() as session:
        c = session.query(Corpus).first()
        ivector = (
            session.query(c.speaker_ivector_column).filter(Speaker.id == speaker_id).first()[0]
        )
        query = (
            session.query(Utterance)
            .options(joinedload(Utterance.file, innerjoin=True))
            .filter(Utterance.speaker_id == speaker_id)
            .order_by(c.utterance_ivector_column.cosine_distance(ivector).desc())
            .limit(limit)
            .offset(kwargs.get("current_offset", 0))
        )
        file_ids = []
        utterance_ids = []
        data = []
        for utterance in query:
            if stopped is not None and stopped.stop_check():
                session.rollback()
                return
            if progress_callback is not None:
                progress_callback.increment_progress(1)
            utterance_ids.append(utterance.id)
            file_ids.append(utterance.file_id)
            data.append([utterance.file_name, utterance.begin, utterance.end])
        return data, utterance_ids, file_ids


def query_function(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    with Session() as session:
        c = session.query(Corpus).first()
        count_only = kwargs.get("count", False)
        has_ivectors = kwargs.get("has_ivectors", False)
        if count_only:
            columns = [Utterance.id]
        else:
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
            ]
            columns.append(Utterance.alignment_log_likelihood)
            columns.append(Utterance.speech_log_likelihood)
            columns.append(Utterance.duration_deviation)
            columns.append(Utterance.phone_error_rate)
            columns.append(Utterance.alignment_score)
            columns.append(Utterance.transcription_text)
            columns.append(Utterance.word_error_rate)
            if has_ivectors:
                columns.append(
                    c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column)
                )
        speaker_filter = kwargs.get("speaker_filter", None)
        file_filter = kwargs.get("file_filter", None)
        text_filter: TextFilterQuery = kwargs.get("text_filter", None)
        sort_index = kwargs.get("sort_index", None)
        utterances = session.query(*columns).join(Utterance.speaker).join(Utterance.file)

        if kwargs.get("oovs_only", False):
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
            if kwargs.get("oovs_only", False):
                text_column = Utterance.oovs
            else:
                text_column = Utterance.text
            filter_regex = text_filter.generate_expression(posix=True)
            if text_filter.regex or text_filter.word:
                utterances = utterances.filter(text_column.op("~")(filter_regex))
            else:
                if not text_filter.case_sensitive:
                    text_column = sqlalchemy.func.lower(text_column)
                utterances = utterances.filter(text_column.contains(text_filter.search_text))
        if count_only:
            try:
                return utterances.count()
            except psycopg2.errors.InvalidRegularExpression:
                return 0
        if progress_callback is not None:
            progress_callback.update_total(kwargs.get("limit", 100))
        if sort_index is not None and sort_index + 3 < len(columns) - 1:
            sort_column = columns[sort_index + 3]
            if kwargs.get("sort_desc", False):
                sort_column = sort_column.desc()
            utterances = utterances.order_by(sort_column, Utterance.id)
        else:
            utterances = utterances.order_by(File.name, Utterance.begin)
        utterances = utterances.limit(kwargs.get("limit", 100)).offset(
            kwargs.get("current_offset", 0)
        )
        data = []
        indices = []
        file_indices = []
        speaker_indices = []
        reversed_indices = {}
        try:
            for i, u in enumerate(utterances):
                if stopped is not None and stopped.stop_check():
                    return
                data.append(list(u[3:]))
                indices.append(u[0])
                file_indices.append(u[1])
                speaker_indices.append(u[2])
                reversed_indices[u[0]] = i
                if progress_callback is not None:
                    progress_callback.increment_progress(1)

        except psycopg2.errors.InvalidRegularExpression:
            pass
    return data, indices, file_indices, speaker_indices, reversed_indices


def file_utterances_function(
    Session,
    file_id,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    with Session() as session:
        utterances = (
            session.query(Utterance)
            .options(
                selectinload(Utterance.phone_intervals).options(
                    joinedload(PhoneInterval.phone, innerjoin=True),
                    joinedload(PhoneInterval.workflow, innerjoin=True),
                ),
                selectinload(Utterance.word_intervals).options(
                    joinedload(WordInterval.word, innerjoin=True),
                    joinedload(WordInterval.workflow, innerjoin=True),
                ),
                joinedload(Utterance.speaker, innerjoin=True),
            )
            .filter(Utterance.file_id == file_id)
            .order_by(Utterance.begin)
            .all()
        )
        return utterances, file_id


def query_dictionary_function(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    with Session() as session:
        text_filter = kwargs.get("text_filter", None)
        sort_index = kwargs.get("sort_index", None)
        dictionary_id = kwargs.get("dictionary_id", None)
        filter_unused = kwargs.get("filter_unused", False)

        if progress_callback is not None:
            progress_callback.update_total(kwargs.get("limit", 100))
        columns = [Word.word, Word.count, Pronunciation.pronunciation, Word.id, Pronunciation.id]
        text_column = Word.word
        words = session.query(*columns).join(Word.pronunciations)
        if dictionary_id is not None:
            words = words.filter(Word.dictionary_id == dictionary_id)
        if filter_unused:
            words = words.filter(Word.count > 0)
        if text_filter is not None:
            filter_regex = text_filter.generate_expression(posix=True)
            if text_filter.regex or text_filter.word:
                words = words.filter(text_column.op("~")(filter_regex))
            else:
                if not text_filter.case_sensitive:
                    text_column = sqlalchemy.func.lower(text_column)
                words = words.filter(text_column.contains(text_filter.search_text))
        if kwargs.get("count", False):
            return words.count()
        if sort_index is not None and sort_index < len(columns):
            sort_column = columns[sort_index]
            if kwargs.get("sort_desc", False):
                sort_column = sort_column.desc()
        else:
            sort_column = text_column
        words = words.order_by(sort_column, Word.id)

        words = words.limit(kwargs.get("limit", 100)).offset(kwargs.get("current_offset", 0))
        data = []
        indices = []
        pron_indices = []
        for word, count, pron, w_id, p_id in words:
            if stopped is not None and stopped.stop_check():
                return
            indices.append(w_id)
            pron_indices.append(p_id)
            data.append([word, count, pron])
            if progress_callback is not None:
                progress_callback.increment_progress(1)

    return data, indices, pron_indices


def query_oovs_function(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    with Session() as session:
        text_filter = kwargs.get("text_filter", None)
        sort_index = kwargs.get("sort_index", None)
        columns = [Word.word, Word.count, Word.id]
        text_column = Word.word

        if progress_callback is not None:
            progress_callback.update_total(kwargs.get("limit", 100))

        words = session.query(*columns).filter(Word.word_type == WordType.oov)
        if text_filter is not None:
            filter_regex = text_filter.generate_expression(posix=True)
            if text_filter.regex or text_filter.word:
                words = words.filter(text_column.op("~")(filter_regex))
            else:
                if not text_filter.case_sensitive:
                    text_column = sqlalchemy.func.lower(text_column)
                words = words.filter(text_column.contains(text_filter.search_text))
        if kwargs.get("count", False):
            return words.count()
        if sort_index is not None and sort_index < len(columns):
            sort_column = columns[sort_index]
            if kwargs.get("sort_desc", False):
                sort_column = sort_column.desc()
        else:
            sort_column = text_column
        words = words.order_by(sort_column, Word.id)

        words = words.limit(kwargs.get("limit", 100)).offset(kwargs.get("current_offset", 0))
        data = []
        indices = []
        for word, count, w_id in words:
            if stopped is not None and stopped.stop_check():
                return
            data.append([word, count])
            indices.append(w_id)
            if progress_callback is not None:
                progress_callback.increment_progress(1)

    return data, indices


def calculate_speaker_ivectors(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    logger.debug(f"Using {GLOBAL_CONFIG.profiles['anchor'].num_jobs} jobs")
    speaker_id = kwargs.pop("speaker_id")
    working_directory = kwargs.pop("working_directory")
    plda_transform_path = os.path.join(working_directory, "plda.pkl")
    metric = kwargs.pop("metric", DistanceMetric.cosine)
    if metric is DistanceMetric.plda:
        try:
            with open(plda_transform_path, "rb") as f:
                plda = pickle.load(f)
        except Exception:
            metric = DistanceMetric.cosine
    if progress_callback is not None:
        progress_callback.update_total(3)
    with Session() as session:
        c = session.query(Corpus).first()
        if c.plda_calculated:
            dim = PLDA_DIMENSION
        elif c.xvectors_loaded:
            dim = XVECTOR_DIMENSION
        else:
            dim = IVECTOR_DIMENSION
        speaker_ivector = (
            session.query(c.speaker_ivector_column).filter(Speaker.id == speaker_id).first()[0]
        )
        utterances = (
            session.query(
                Utterance.id,
                c.utterance_ivector_column,
                c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column),
            )
            .join(Utterance.speaker)
            .filter(Utterance.speaker_id == speaker_id, c.utterance_ivector_column != None)  # noqa
        )

        ivectors = np.empty((utterances.count(), dim))
        utterance_ids = []
        speaker_distance = []
        for i, (u_id, u_ivector, distance) in enumerate(utterances):
            ivectors[i, :] = u_ivector
            utterance_ids.append(u_id)
            speaker_distance.append(distance)
        if metric is DistanceMetric.plda:
            if speaker_ivector is not None:
                speaker_distance = score_plda(
                    speaker_ivector[np.newaxis, :], ivectors, plda, normalize=True, distance=True
                )[:, 0]
            else:
                speaker_distance = None
    return speaker_id, np.array(utterance_ids), ivectors, speaker_distance


def cluster_speaker_utterances(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    speaker_id = kwargs.pop("speaker_id")
    working_directory = kwargs.pop("working_directory")
    cluster_type = kwargs.pop("cluster_type", ClusterType.hdbscan)
    metric_type = kwargs.pop("metric", DistanceMetric.cosine)
    plda_transform_path = os.path.join(working_directory, "plda.pkl")
    plda = None
    try:
        with open(plda_transform_path, "rb") as f:
            plda = pickle.load(f)
    except Exception:
        metric_type = DistanceMetric.cosine
    distance_threshold = kwargs.pop("distance_threshold", None)
    if not distance_threshold:
        distance_threshold = None
    logger.debug(f"Clustering with {cluster_type}...")
    with Session() as session:
        c = session.query(Corpus).first()
        utterance_count = (
            session.query(Utterance)
            .filter(Utterance.speaker_id == speaker_id, c.utterance_ivector_column != None)  # noqa
            .count()
        )
        if c.plda_calculated:
            dim = PLDA_DIMENSION
        elif c.xvectors_loaded:
            dim = XVECTOR_DIMENSION
        else:
            dim = IVECTOR_DIMENSION
        to_fit = np.empty((utterance_count, dim))
        query = session.query(c.utterance_ivector_column).filter(
            Utterance.speaker_id == speaker_id, c.utterance_ivector_column != None  # noqa
        )
        for i, (ivector,) in enumerate(query):
            to_fit[i, :] = ivector
        begin = time.time()
        if cluster_type is ClusterType.agglomerative:
            logger.info("Running Agglomerative Clustering...")
            kwargs["memory"] = MEMORY
            if "n_clusters" not in kwargs:
                kwargs["distance_threshold"] = distance_threshold
            if metric_type is DistanceMetric.plda:
                kwargs["linkage"] = "average"
            elif metric_type is DistanceMetric.cosine:
                kwargs["linkage"] = "average"
        elif cluster_type is ClusterType.dbscan:
            kwargs["distance_threshold"] = distance_threshold
        elif cluster_type is ClusterType.hdbscan:
            kwargs["distance_threshold"] = distance_threshold
            kwargs["memory"] = MEMORY
        elif cluster_type is ClusterType.optics:
            kwargs["distance_threshold"] = distance_threshold
            kwargs["memory"] = MEMORY
        c = cluster_matrix(
            to_fit,
            cluster_type,
            metric=metric_type,
            strict=False,
            no_visuals=True,
            plda=plda,
            **kwargs,
        )
        logger.debug(f"Clustering with {cluster_type} took {time.time() - begin} seconds")
    return speaker_id, c


def mds_speaker_utterances(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    speaker_id = kwargs.pop("speaker_id")
    working_directory = kwargs.pop("working_directory")
    plda_transform_path = os.path.join(working_directory, "plda.pkl")
    metric_type = kwargs.pop("metric", DistanceMetric.cosine)
    plda = None
    try:
        with open(plda_transform_path, "rb") as f:
            plda = pickle.load(f)
    except Exception:
        metric_type = DistanceMetric.cosine
    n_neighbors = 10
    with Session() as session:
        c = session.query(Corpus).first()
        utterance_count = (
            session.query(Utterance)
            .filter(Utterance.speaker_id == speaker_id, c.utterance_ivector_column != None)  # noqa
            .count()
        )
        if c.plda_calculated:
            dim = PLDA_DIMENSION
        elif c.xvectors_loaded:
            dim = XVECTOR_DIMENSION
        else:
            dim = IVECTOR_DIMENSION
        ivectors = np.empty((utterance_count, dim), dtype="float32")
        query = session.query(c.utterance_ivector_column).filter(
            Utterance.speaker_id == speaker_id, c.utterance_ivector_column != None  # noqa
        )
        for i, (ivector,) in enumerate(query):
            ivectors[i, :] = ivector
        points = visualize_clusters(
            ivectors, ManifoldAlgorithm.tsne, metric_type, n_neighbors, plda, quick=True
        )
    return speaker_id, points


def query_speakers_function(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
    **kwargs,
):
    with Session() as session:
        c = session.query(Corpus).first()
        text_filter = kwargs.get("text_filter", None)
        sort_index = kwargs.get("sort_index", None)
        if kwargs.get("count", False):
            speakers = session.query(Speaker.name)
            if text_filter is not None:
                filter_regex = text_filter.generate_expression(posix=True)
                text_column = Speaker.name
                if text_filter.regex or text_filter.word:
                    speakers = speakers.filter(text_column.op("~")(filter_regex))
                else:
                    if not text_filter.case_sensitive:
                        text_column = sqlalchemy.func.lower(text_column)
                    speakers = speakers.filter(text_column.contains(text_filter.search_text))
            return speakers.count()

        if progress_callback is not None:
            progress_callback.update_total(kwargs.get("limit", 100))
        columns = [
            Speaker.id,
            Speaker.name,
            sqlalchemy.func.count(),
            Speaker.dictionary_id,
            sqlalchemy.func.avg(
                c.utterance_ivector_column.cosine_distance(c.speaker_ivector_column)
            ),
        ]

        speakers = (
            session.query(*columns)
            .join(Speaker.utterances)
            .group_by(Speaker.id, Speaker.name, Speaker.dictionary_id)
        )
        if text_filter is not None:
            filter_regex = text_filter.generate_expression(posix=True)
            text_column = columns[1]
            if not text_filter.case_sensitive:
                text_column = sqlalchemy.func.lower(text_column)
            if text_filter.regex or text_filter.word:
                speakers = speakers.filter(text_column.op("~")(filter_regex))
            else:
                speakers = speakers.filter(text_column.contains(text_filter.search_text))
        if sort_index is not None:
            sort_column = columns[sort_index + 1]
            if kwargs.get("sort_desc", False):
                sort_column = sort_column.desc()
            speakers = speakers.order_by(sort_column)
        speakers = speakers.limit(kwargs.get("limit", 100)).offset(kwargs.get("current_offset", 0))
        data = []
        indices = []
        for w in speakers:
            if stopped is not None and stopped.stop_check():
                return
            d = list(w)
            indices.append(d.pop(0))
            data.append(d)
            if progress_callback is not None:
                progress_callback.increment_progress(1)
    return data, indices


def change_speaker_function(
    Session,
    utterance_ids,
    new_speaker_id,
    old_speaker_id,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
):
    with Session() as session:
        try:
            if new_speaker_id == 0:
                new_speaker_id = session.query(sqlalchemy.func.max(Speaker.id)).scalar() + 1
                speaker = session.query(Speaker).get(old_speaker_id)
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
                        id=new_speaker_id, name=speaker_name, dictionary_id=speaker.dictionary_id
                    )
                )
                session.flush()
            file_ids = [
                x[0]
                for x in session.query(File.id)
                .join(File.utterances)
                .filter(Utterance.id.in_(utterance_ids))
                .distinct()
            ]
            mapping = [{"id": x, "speaker_id": new_speaker_id} for x in utterance_ids]
            session.bulk_update_mappings(Utterance, mapping)
            session.execute(
                sqlalchemy.delete(SpeakerOrdering).where(
                    SpeakerOrdering.c.file_id.in_(file_ids),
                    SpeakerOrdering.c.speaker_id.in_([old_speaker_id, new_speaker_id]),
                )
            )
            session.flush()
            so_mapping = [
                {"speaker_id": new_speaker_id, "file_id": f_id, "index": 10} for f_id in file_ids
            ]
            session.execute(sqlalchemy.insert(SpeakerOrdering), so_mapping)

            if stopped is not None and stopped.stop_check():
                session.rollback()
                return
            session.commit()
        except Exception:
            session.rollback()
            raise
    return new_speaker_id


def recalculate_speaker_function(
    Session,
    speaker_id,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
):
    with Session() as session:
        try:
            c = session.query(Corpus).first()
            old_ivectors = np.array(
                [
                    x[0]
                    for x in session.query(c.utterance_ivector_column).filter(
                        Utterance.speaker_id == speaker_id,
                        c.utterance_ivector_column != None,  # noqa
                    )
                ]
            )
            if old_ivectors.shape[0] > 0:
                old_speaker_ivector = np.mean(old_ivectors, axis=0)

                session.execute(
                    sqlalchemy.update(Speaker)
                    .where(Speaker.id == speaker_id)
                    .values({c.speaker_ivector_column: old_speaker_ivector})
                )
            if stopped is not None and stopped.stop_check():
                session.rollback()
                return
            session.commit()
        except Exception:
            session.rollback()
            raise


def replace_function(
    Session,
    search_query: TextFilterQuery,
    replacement_string,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
):
    with Session() as session:
        try:
            old_texts = {}
            new_texts = {}

            filter_regex = search_query.generate_expression(posix=True)
            text_column = Utterance.text

            columns = [Utterance.id, Utterance.text]
            utterances = session.query(*columns)

            if search_query.regex or search_query.word:
                utterances = utterances.filter(text_column.op("~")(filter_regex))
            else:
                if not search_query.case_sensitive:
                    text_column = sqlalchemy.func.lower(text_column)
                utterances = utterances.filter(text_column.contains(search_query.search_text))
            if progress_callback is not None:
                progress_callback.update_total(utterances.count())
            for u_id, text in utterances:
                if stopped is not None and stopped.stop_check():
                    session.rollback()
                    return
                old_texts[u_id] = text

            utterance_table = Utterance.__table__
            utterance_statement = sqlalchemy.update(utterance_table)
            files = session.query(File).filter(File.id == Utterance.file_id)

            if search_query.regex or search_query.word:
                files = files.filter(text_column.op("~")(filter_regex))

                utterance_statement = utterance_statement.where(
                    utterance_table.c.text.op("~")(filter_regex)
                )
                utterance_statement = utterance_statement.values(
                    text=sqlalchemy.func.regexp_replace(
                        utterance_table.c.text, filter_regex, replacement_string, "g"
                    ),
                    normalized_text=sqlalchemy.func.regexp_replace(
                        utterance_table.c.normalized_text, filter_regex, replacement_string, "g"
                    ),
                ).execution_options(synchronize_session="fetch")
                utterance_statement = utterance_statement.returning(
                    utterance_table.c.id, utterance_table.c.text
                )
            else:
                if not search_query.case_sensitive:
                    text_column = sqlalchemy.func.lower(text_column)
                files = files.filter(text_column.contains(search_query.search_text))

                utterance_statement = utterance_statement.where(
                    utterance_table.c.text.contains(search_query.search_text)
                )
                utterance_statement = utterance_statement.values(
                    text=sqlalchemy.func.regexp_replace(
                        utterance_table.c.text, filter_regex, replacement_string, "g"
                    ),
                    normalized_text=sqlalchemy.func.regexp_replace(
                        utterance_table.c.normalized_text, filter_regex, replacement_string, "g"
                    ),
                ).execution_options(synchronize_session="fetch")
                utterance_statement = utterance_statement.returning(
                    utterance_table.c.id, utterance_table.c.text
                )
            while True:
                try:
                    with session.begin_nested():
                        files.update(
                            {
                                File.modified: True,
                            },
                            synchronize_session=False,
                        )
                        results = session.execute(utterance_statement)
                        for u_id, text in results:
                            if progress_callback is not None:
                                progress_callback.increment_progress(1)
                            new_texts[u_id] = text
                    break
                except psycopg2.errors.DeadlockDetected:
                    pass
            if stopped is not None and stopped.stop_check():
                session.rollback()
                return
            session.commit()
        except Exception:
            session.rollback()
            raise
    return search_query.generate_expression(), old_texts, new_texts


def export_files_function(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
):
    with Session() as session:
        try:
            mappings = []
            settings = AnchorSettings()
            settings.sync()
            output_directory = session.query(Corpus.path).first()[0]
            files = (
                session.query(File)
                .options(
                    subqueryload(File.utterances),
                    subqueryload(File.speakers),
                    joinedload(File.sound_file, innerjoin=True).load_only(SoundFile.duration),
                    joinedload(File.text_file, innerjoin=True).load_only(TextFile.file_type),
                )
                .filter(File.modified == True)  # noqa
            )

            if progress_callback is not None:
                progress_callback.update_total(files.count())
            for f in files:
                if stopped.stop_check():
                    session.rollback()
                    break
                try:
                    f.save(
                        output_directory, overwrite=True, output_format=TextFileType.TEXTGRID.value
                    )
                except Exception:
                    logger.error(f"Error writing {f.name}")
                    raise
                mappings.append({"id": f.id, "modified": False})
                if progress_callback is not None:
                    progress_callback.increment_progress(1)
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


def export_lexicon_function(
    Session,
    dictionary_id: int,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
):
    with Session() as session:
        dictionary_path = (
            session.query(Dictionary.path).filter(Dictionary.id == dictionary_id).scalar()
        )
        words = (
            session.query(Word.word, Pronunciation.pronunciation)
            .join(Pronunciation.word)
            .filter(
                Word.dictionary_id == dictionary_id,
                Pronunciation.pronunciation != "",
                Word.word_type.in_([WordType.speech, WordType.clitic]),
            )
            .order_by(Word.word)
        )

        if progress_callback is not None:
            progress_callback.update_total(words.count())
        with open(dictionary_path, "w", encoding="utf8") as f:
            for w, p in words:
                if stopped.stop_check():
                    break
                f.write(f"{w}\t{p}\n")
                if progress_callback is not None:
                    progress_callback.increment_progress(1)


def speakers_function(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
):
    begin = time.time()
    conn = Session.bind.raw_connection()
    speakers = {}
    try:
        cursor = conn.cursor()
        cursor.execute("select speaker.name, speaker.id from speaker order by speaker.name")
        query = cursor.fetchall()
        for s_name, s_id in query:
            speakers[s_name] = s_id
        cursor.close()
    finally:
        conn.close()
    logger.debug(f"Loading all speaker names took {time.time() - begin:.3f} seconds.")
    return speakers


def dictionaries_function(
    Session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
):
    dictionaries = []
    word_sets = {}
    speaker_mapping = {}
    with Session() as session:
        query = session.query(Dictionary.id, Dictionary.name)
        for dict_id, dict_name in query:
            dictionaries.append([dict_id, dict_name])
            word_sets[dict_id] = {
                x[0]
                for x in session.query(Word.word).filter(
                    Word.dictionary_id == dict_id,
                    Word.word_type.in_([WordType.speech, WordType.clitic]),
                )
            }
            for (s_id,) in session.query(Speaker.id).filter(Speaker.dictionary_id == dict_id):
                speaker_mapping[s_id] = dict_id

    return dictionaries, word_sets, speaker_mapping


def files_function(
    Session: sqlalchemy.orm.scoped_session,
    progress_callback: typing.Optional[ProgressCallback] = None,
    stopped: typing.Optional[Stopped] = None,
):
    begin = time.time()
    conn = Session.bind.raw_connection()
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


class ExportFilesWorker(Worker):
    def __init__(self, session, use_mp=False):
        super().__init__(export_files_function, session, use_mp=use_mp)


class ReplaceAllWorker(Worker):
    def __init__(self, session, search_string, replacement_string, use_mp=False):
        super().__init__(
            replace_function, session, search_string, replacement_string, use_mp=use_mp
        )


class ChangeSpeakerWorker(Worker):
    def __init__(self, session, utterance_ids, new_speaker_id, old_speaker_id, use_mp=False):
        super().__init__(
            change_speaker_function,
            session,
            utterance_ids,
            new_speaker_id,
            old_speaker_id,
            use_mp=use_mp,
        )


class RecalculateSpeakerWorker(Worker):
    def __init__(self, session, speaker_id, use_mp=False):
        super().__init__(recalculate_speaker_function, session, speaker_id, use_mp=use_mp)


class QueryUtterancesWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(query_function, session, use_mp=use_mp, **kwargs)


class QuerySpeakersWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(query_speakers_function, session, use_mp=use_mp, **kwargs)


class ClusterSpeakerUtterancesWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(cluster_speaker_utterances, session, use_mp=use_mp, **kwargs)


class CalculateSpeakerIvectorsWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(calculate_speaker_ivectors, session, use_mp=use_mp, **kwargs)


class SpeakerMdsWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(mds_speaker_utterances, session, use_mp=use_mp, **kwargs)


class SpeakerComparisonWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(speaker_comparison_query, session, use_mp=use_mp, **kwargs)


class DuplicateFilesWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(duplicate_files_query, session, use_mp=use_mp, **kwargs)


class MergeSpeakersWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(merge_speakers_function, session, use_mp=use_mp, **kwargs)


class ClosestSpeakersWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(closest_speaker_function, session, use_mp=use_mp, **kwargs)


class FileUtterancesWorker(Worker):
    def __init__(self, session, file_id, use_mp=False, **kwargs):
        super().__init__(file_utterances_function, session, file_id, use_mp=use_mp, **kwargs)


class QueryOovWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(query_oovs_function, session, use_mp=use_mp, **kwargs)


class QueryDictionaryWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(query_dictionary_function, session, use_mp=use_mp, **kwargs)


class ExportLexiconWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(export_lexicon_function, session, use_mp=use_mp, **kwargs)


class LoadSpeakersWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(speakers_function, session, use_mp=use_mp, **kwargs)


class LoadFilesWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(files_function, session, use_mp=use_mp, **kwargs)


class LoadDictionariesWorker(Worker):
    def __init__(self, session, use_mp=False, **kwargs):
        super().__init__(dictionaries_function, session, use_mp=use_mp, **kwargs)


class FunctionWorker(QtCore.QThread):  # pragma: no cover
    def __init__(self, name, *args):
        super().__init__(*args)
        self.settings = AnchorSettings()
        self.signals = WorkerSignals(name)
        self.lock = Lock()

    def setParams(self, kwargs):
        self.kwargs = kwargs
        self.kwargs["progress_callback"] = self.signals.progress
        self.kwargs["stop_check"] = self.stopCheck
        self.total = None

    def stop(self):
        pass

    def stopCheck(self):
        return False


class AutoWaveformWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Scaling waveform", *args)

    def set_params(self, y, normalized_min, normalized_max, begin, end, channel):
        with self.lock:
            self.y = y
            self.normalized_min = normalized_min
            self.normalized_max = normalized_max
            self.begin = begin
            self.end = end
            self.channel = channel

    def run(self):
        with self.lock:
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
            if self.stopCheck():
                return
            self.signals.result.emit((normalized, self.begin, self.end, self.channel))


class WaveformWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Loading waveform", *args)

    def set_params(self, file_path):
        with self.lock:
            self.file_path = file_path

    def run(self):
        with self.lock:
            y, _ = soundfile.read(self.file_path)
            if self.stopCheck():
                return
            self.signals.result.emit((y, self.file_path))


class SpeakerTierWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Generating speaker tier", *args)

    def set_params(self, Session, file_id):
        with self.lock:
            self.Session = Session
            self.file_id = file_id

    def run(self):
        with self.lock:
            with self.Session() as session:
                utterances = (
                    session.query(Utterance)
                    .options(
                        selectinload(Utterance.phone_intervals).options(
                            joinedload(PhoneInterval.phone, innerjoin=True),
                            joinedload(PhoneInterval.workflow, innerjoin=True),
                        ),
                        selectinload(Utterance.word_intervals).options(
                            joinedload(WordInterval.word, innerjoin=True),
                            joinedload(WordInterval.workflow, innerjoin=True),
                        ),
                        joinedload(Utterance.speaker, innerjoin=True),
                    )
                    .filter(Utterance.file_id == self.file_id)
                    .order_by(Utterance.begin)
                    .all()
                )
            if self.stopCheck():
                return
            self.signals.result.emit((utterances, self.file_id))


class SpectrogramWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Generating spectrogram", *args)

    def set_params(
        self,
        y,
        sample_rate,
        begin,
        end,
        channel,
        dynamic_range,
        n_fft,
        time_steps,
        window_size,
        pre_emph_coeff,
        max_freq,
    ):
        with self.lock:
            self.y = y
            self.sample_rate = sample_rate
            self.begin = begin
            self.end = end
            self.channel = channel
            self.dynamic_range = dynamic_range
            self.n_fft = n_fft
            self.time_steps = time_steps
            self.window_size = window_size
            self.pre_emph_coeff = pre_emph_coeff
            self.max_freq = max_freq

    def run(self):
        with self.lock:
            if self.y.shape[0] == 0:
                return
            max_sr = 2 * self.max_freq
            if self.sample_rate > max_sr:
                self.y = resampy.resample(self.y, self.sample_rate, max_sr)
                self.sample_rate = max_sr
            self.y = librosa.effects.preemphasis(self.y, coef=self.pre_emph_coeff)
            if self.stopCheck():
                return
            begin_samp = int(self.begin * self.sample_rate)
            end_samp = int(self.end * self.sample_rate)
            window_size = round(self.window_size, 6)
            window_size_samp = int(window_size * self.sample_rate)
            duration_samp = end_samp - begin_samp
            if self.time_steps >= duration_samp:
                step_size_samples = 1
            else:
                step_size_samples = int(duration_samp / self.time_steps)
            stft = librosa.amplitude_to_db(
                np.abs(
                    librosa.stft(
                        self.y,
                        n_fft=self.n_fft,
                        win_length=window_size_samp,
                        hop_length=step_size_samples,
                        center=True,
                    )
                ),
                top_db=self.dynamic_range,
            )
            min_db, max_db = np.min(stft), np.max(stft)
            if self.stopCheck():
                return
            self.signals.result.emit((stft, self.channel, self.begin, self.end, min_db, max_db))


class PitchWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Generating pitch track", *args)

    def set_params(
        self,
        y,
        sample_rate,
        begin,
        end,
        channel,
        min_f0,
        max_f0,
        frame_shift,
        frame_length,
        delta_pitch,
        penalty_factor,
        normalized_min,
        normalized_max,
    ):
        with self.lock:
            self.y = y
            self.sample_rate = sample_rate
            self.begin = begin
            self.end = end
            self.channel = channel
            self.min_f0 = min_f0
            self.max_f0 = max_f0
            self.frame_shift = frame_shift
            self.frame_length = frame_length
            self.delta_pitch = delta_pitch
            self.penalty_factor = penalty_factor
            self.normalized_min = normalized_min
            self.normalized_max = normalized_max

    def run(self):
        with self.lock:
            if self.y.shape[0] == 0:
                return
            pitch_proc = subprocess.Popen(
                [
                    thirdparty_binary("compute-and-process-kaldi-pitch-feats"),
                    "--snip-edges=true",
                    f"--min-f0={self.min_f0}",
                    f"--max-f0={self.max_f0}",
                    "--add-delta-pitch=false",
                    "--add-normalized-log-pitch=false",
                    "--add-raw-log-pitch=true",
                    f"--sample-frequency={self.sample_rate}",
                    f"--frame-shift={self.frame_shift}",
                    f"--frame-length={self.frame_length}",
                    f"--delta-pitch={self.delta_pitch}",
                    f"--penalty-factor={self.penalty_factor}",
                    "ark:-",
                    "ark,t:-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            pitch_proc.stdin.write(b"0-0 ")
            bio = BytesIO()
            sf.write(bio, self.y, samplerate=self.sample_rate, format="WAV")

            pitch_proc.stdin.write(bio.getvalue())
            pitch_proc.stdin.flush()
            pitch_proc.stdin.close()
            pitch_track = None
            voiced_track = None
            for _, pitch_track in read_feats(pitch_proc):
                if len(pitch_track.shape) < 2:
                    self.signals.result.emit(
                        (None, None, self.channel, self.begin, self.end, self.min_f0, self.max_f0)
                    )
                    return
                voiced_track = pitch_track[:, 0]
                pitch_track = np.exp(pitch_track[:, 1])
            pitch_proc.wait()
            if self.stopCheck():
                return
            min_nccf = np.min(voiced_track)
            max_nccf = np.max(voiced_track)
            threshold = min_nccf + (max_nccf - min_nccf) * 0.45
            voiced_frames = np.where(
                (voiced_track <= threshold)
                & (pitch_track < self.max_f0)
                & (pitch_track > self.min_f0)
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
            if self.stopCheck():
                return
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

    def stop(self):
        if hasattr(self, "corpus") and self.corpus is not None:
            self.corpus.stopped.stop()

    def set_params(self, corpus_path: str, dictionary_path: str, reset=False):
        self.corpus_path = corpus_path
        self.dictionary_path = dictionary_path
        self.reset = reset

    def run(self):
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
        GLOBAL_CONFIG.current_profile.clean = self.reset
        corpus_name = os.path.basename(self.corpus_path)
        dataset_type = inspect_database(corpus_name)
        try:
            if dataset_type is DatasetType.NONE:
                if self.dictionary_path and os.path.exists(self.dictionary_path):
                    self.corpus = AcousticCorpusWithPronunciations(
                        corpus_directory=self.corpus_path, dictionary_path=self.dictionary_path
                    )
                    self.corpus.initialize_database()
                    self.corpus.dictionary_setup()
                else:
                    self.corpus = AcousticCorpus(corpus_directory=self.corpus_path)
                    self.corpus.initialize_database()
                    self.corpus._load_corpus()
            elif (
                dataset_type is DatasetType.ACOUSTIC_CORPUS_WITH_DICTIONARY
                and self.dictionary_path
                and os.path.exists(self.dictionary_path)
            ):
                self.corpus = AcousticCorpusWithPronunciations(
                    corpus_directory=self.corpus_path, dictionary_path=self.dictionary_path
                )
                self.corpus.inspect_database()
            else:
                self.corpus = AcousticCorpus(corpus_directory=self.corpus_path)
                self.corpus.inspect_database()
            self.corpus._load_corpus()
            if self.dictionary_path and os.path.exists(self.dictionary_path):
                self.corpus.initialize_jobs()

                self.corpus.normalize_text()
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            if self.corpus.stopped.stop_check():
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
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
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
            if self.corpus.stopped.stop_check():
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
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
        try:
            with self.corpus.session() as session:
                session.query(PhoneInterval).filter(
                    PhoneInterval.workflow_id == CorpusWorkflow.id,
                    CorpusWorkflow.workflow_type == WorkflowType.reference,
                ).delete(synchronize_session=False)
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
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
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
                session.execute(
                    sqlalchemy.update(Speaker).values(dictionary_id=corpus._default_dictionary_id)
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
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
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
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
        if not self.model_path:
            return
        try:
            acoustic_model = AcousticModel(self.model_path)
        except Exception:
            if os.path.exists(self.model_path):
                exctype, value = sys.exc_info()[:2]
                self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(acoustic_model)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class ImportLanguageModelWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Importing language model", *args)

    def set_params(self, model_path: str):
        self.model_path = model_path

    def run(self):
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
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
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
        if not self.model_path:
            return
        try:
            generator = Generator(g2p_model_path=self.model_path, num_pronunciations=5)
            generator.setup()
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
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
        if not self.model_path:
            return
        try:
            if str(self.model_path) == "speechbrain":
                model = "speechbrain"
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
        self.corpus: typing.Optional[AcousticCorpusWithPronunciations] = None
        self.acoustic_model: typing.Optional[AcousticModel] = None

    def set_params(
        self, corpus: AcousticCorpusWithPronunciations, acoustic_model: AcousticModel, utterance_id
    ):
        self.corpus = corpus
        self.acoustic_model = acoustic_model
        self.utterance_id = utterance_id

    def run(self):
        self.settings.sync()
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
        try:
            aligner = PretrainedAligner(
                acoustic_model_path=self.acoustic_model.source,
                corpus_directory=self.corpus.corpus_directory,
                dictionary_path=self.corpus.dictionary_model.path,
            )
            aligner.inspect_database()
            aligner.corpus_output_directory = self.corpus.corpus_output_directory
            aligner.dictionary_output_directory = self.corpus.dictionary_output_directory
            aligner.non_silence_phones = self.corpus.non_silence_phones

            aligner.acoustic_model = self.acoustic_model
            with aligner.session() as session:
                utterance = (
                    session.query(Utterance)
                    .options(
                        joinedload(Utterance.file, innerjoin=True).joinedload(
                            File.sound_file, innerjoin=True
                        ),
                        joinedload(Utterance.speaker, innerjoin=True).joinedload(
                            Speaker.dictionary, innerjoin=True
                        ),
                    )
                    .get(self.utterance_id)
                )
                aligner.align_one_utterance(utterance, session)
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(self.utterance_id)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class SegmentUtteranceWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Segmenting utterance", *args)
        self.corpus: typing.Optional[AcousticCorpusWithPronunciations] = None
        self.acoustic_model: typing.Optional[AcousticModel] = None

    def set_params(
        self, corpus: AcousticCorpusWithPronunciations, acoustic_model: AcousticModel, utterance_id
    ):
        self.corpus = corpus
        self.acoustic_model = acoustic_model
        self.utterance_id = utterance_id

    def run(self):
        self.settings.sync()
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
        try:
            segmenter = TranscriptionSegmenter(
                acoustic_model_path=self.acoustic_model.source,
                corpus_directory=self.corpus.corpus_directory,
                dictionary_path=self.corpus.dictionary_model.path,
                speechbrain=True,
            )
            segmenter.inspect_database()
            segmenter.corpus_output_directory = self.corpus.corpus_output_directory
            segmenter.dictionary_output_directory = self.corpus.dictionary_output_directory
            segmenter.non_silence_phones = self.corpus.non_silence_phones

            segmenter.acoustic_model = self.acoustic_model
            segmenter.create_new_current_workflow(WorkflowType.segmentation)
            segmenter.setup_acoustic_model()

            segmenter.write_lexicon_information(write_disambiguation=True)
            with segmenter.session() as session:
                sub_utterances = segment_utterance(
                    session,
                    segmenter.working_directory,
                    self.utterance_id,
                    segmenter.vad_model,
                    segmenter.segmentation_options,
                    segmenter.mfcc_options,
                    segmenter.pitch_options,
                    segmenter.lda_options,
                    segmenter.decode_options,
                )
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(sub_utterances)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class AlignmentWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Aligning", *args)
        self.corpus: typing.Optional[AcousticCorpusWithPronunciations] = None
        self.dictionary: typing.Optional[MultispeakerDictionary] = None
        self.acoustic_model: typing.Optional[AcousticModel] = None

    def set_params(
        self,
        corpus: AcousticCorpusWithPronunciations,
        acoustic_model: AcousticModel,
        parameters=None,
    ):
        self.corpus = corpus
        self.acoustic_model = acoustic_model
        self.parameters = parameters
        if self.parameters is None:
            self.parameters = {}

    def run(self):
        self.settings.sync()
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
        try:
            logger.info("Resetting any previous alignments...")
            with self.corpus.session() as session:
                session.query(PhoneInterval).filter(
                    PhoneInterval.workflow_id == CorpusWorkflow.id,
                    CorpusWorkflow.workflow_type == WorkflowType.alignment,
                ).delete(synchronize_session=False)
                session.query(WordInterval).filter(
                    WordInterval.workflow_id == CorpusWorkflow.id,
                    CorpusWorkflow.workflow_type == WorkflowType.alignment,
                ).delete(synchronize_session=False)
                session.query(CorpusWorkflow).filter(
                    CorpusWorkflow.workflow_type == WorkflowType.alignment
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
            aligner = PretrainedAligner(
                acoustic_model_path=self.acoustic_model.source,
                corpus_directory=self.corpus.corpus_directory,
                dictionary_path=self.corpus.dictionary_model.path,
                **self.parameters,
            )
            aligner.inspect_database()
            aligner.clean_working_directory()
            aligner.corpus_output_directory = self.corpus.corpus_output_directory
            aligner.dictionary_output_directory = self.corpus.dictionary_output_directory
            aligner.acoustic_model = self.acoustic_model
            aligner.align()
            aligner.collect_alignments()
            aligner.analyze_alignments()
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            self.signals.finished.emit()  # Done


class ComputeIvectorWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Computing ivectors", *args)
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
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
        logger = logging.getLogger("anchor")
        try:
            logger.debug("Beginning ivector computation")
            logger.info("Resetting ivectors...")
            with self.corpus.session() as session:
                if self.reset:
                    session.execute(
                        sqlalchemy.update(Corpus).values(
                            ivectors_calculated=False, plda_calculated=False, xvectors_loaded=False
                        )
                    )
                    session.execute(sqlalchemy.update(Utterance).values(ivector=None))
                    session.execute(sqlalchemy.update(Utterance).values(xvector=None))
                    session.execute(sqlalchemy.update(Speaker).values(xvector=None))
                    session.execute(sqlalchemy.update(Speaker).values(ivector=None))
                    session.commit()
            diarizer = SpeakerDiarizer(
                ivector_extractor_path=self.ivector_extractor.source
                if self.ivector_extractor != "speechbrain"
                else self.ivector_extractor,
                corpus_directory=self.corpus.corpus_directory,
                cuda=True,
                **self.parameters,
            )
            diarizer.inspect_database()
            diarizer.corpus_output_directory = self.corpus.corpus_output_directory
            diarizer.dictionary_output_directory = self.corpus.dictionary_output_directory
            diarizer.setup()
            diarizer.cleanup_empty_speakers()
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
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
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
        logger = logging.getLogger("anchor")
        try:
            logger.debug("Beginning clustering")

            self.parameters["cluster_type"] = "mfa"
            self.parameters["distance_threshold"] = self.settings.value(
                self.settings.CLUSTERING_DISTANCE_THRESHOLD
            )
            self.parameters["metric"] = self.settings.value(self.settings.CLUSTERING_METRIC)
            self.parameters["expected_num_speakers"] = self.settings.value(
                self.settings.CLUSTERING_N_CLUSTERS
            )
            diarizer = SpeakerDiarizer(
                ivector_extractor_path=self.ivector_extractor.source
                if self.ivector_extractor != "speechbrain"
                else self.ivector_extractor,
                corpus_directory=self.corpus.corpus_directory,
                cuda=self.settings.value(self.settings.CUDA),
                cluster=True,
                **self.parameters,
            )
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
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
        logger = logging.getLogger("anchor")
        try:
            logger.debug("Beginning speaker classification")
            diarizer = SpeakerDiarizer(
                ivector_extractor_path=self.ivector_extractor.source
                if self.ivector_extractor != "speechbrain"
                else self.ivector_extractor,
                corpus_directory=self.corpus.corpus_directory,  # score_threshold = 0.5,
                cluster=False,
                cuda=self.settings.value(self.settings.CUDA),
                **self.parameters,
            )
            diarizer.inspect_database()
            diarizer.corpus_output_directory = self.corpus.corpus_output_directory
            diarizer.dictionary_output_directory = self.corpus.dictionary_output_directory
            diarizer.classify_speakers()
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
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
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
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
            aligner = PretrainedAligner(
                acoustic_model_path=self.acoustic_model.source,
                corpus_directory=self.corpus.corpus_directory,
                dictionary_path=self.corpus.dictionary_model.path,
            )
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
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
        try:
            with self.corpus.session() as session:
                session.query(PhoneInterval).filter(
                    PhoneInterval.workflow_id == CorpusWorkflow.id
                ).filter(CorpusWorkflow.workflow_type == WorkflowType.transcription).delete(
                    synchronize_session="fetch"
                )
                session.query(WordInterval).filter(
                    WordInterval.workflow_id == CorpusWorkflow.id
                ).filter(CorpusWorkflow.workflow_type == WorkflowType.transcription).delete(
                    synchronize_session="fetch"
                )
                session.query(CorpusWorkflow).filter(
                    CorpusWorkflow.workflow_type == WorkflowType.transcription
                ).delete()
                session.query(Utterance).update({Utterance.transcription_text: None})
                session.commit()
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
            self.signals.finished.emit()  # Done


class FeatureGeneratorWorker(FunctionWorker):  # pragma: no cover
    def __init__(self, *args):
        super().__init__("Validating", *args)
        self.queue = queue.Queue()
        self.corpus: typing.Optional[AcousticCorpusWithPronunciations] = None
        self.acoustic_model: typing.Optional[AcousticModel] = None
        self.ivector_extractor: typing.Optional[IvectorExtractorModel] = None
        self.stopped = Stopped()
        self._db_engine = None

    def set_params(
        self,
        corpus: AcousticCorpusWithPronunciations,
        acoustic_model: AcousticModel = None,
        ivector_extractor: IvectorExtractorModel = None,
    ):
        self.corpus = corpus
        self.db_string = corpus.db_string
        self.acoustic_model = acoustic_model
        self.ivector_extractor = ivector_extractor

    @property
    def db_engine(self):
        return sqlalchemy.create_engine(self.db_string)

    def run(self):
        while True:
            try:
                utterance_id = self.queue.get(timeout=5)
                if self.stopped.stopCheck():
                    continue
            except queue.Empty:
                continue
            if self.stopped.stopCheck():
                break
            with sqlalchemy.orm.Session(self.db_engine) as session:
                utterance = (
                    session.query(Utterance)
                    .options(joinedload(Utterance.file).joinedload(File.sound_file))
                    .get(utterance_id)
                )
                wave = librosa.load(
                    utterance.file.sound_file.sound_file_path,
                    sr=16000,
                    offset=utterance.begin,
                    duration=utterance.duration,
                    mono=False,
                )
                if len(wave.shape) == 2:
                    wave = wave[utterance.channel, :]


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
        os.environ[MFA_PROFILE_VARIABLE] = "anchor"
        GLOBAL_CONFIG.load()
        GLOBAL_CONFIG.profiles["anchor"].clean = False
        GLOBAL_CONFIG.save()
        try:
            with self.corpus.session() as session:
                session.query(PhoneInterval).filter(
                    PhoneInterval.workflow_id == CorpusWorkflow.id
                ).filter(
                    CorpusWorkflow.workflow_type == WorkflowType.per_speaker_transcription
                ).delete(
                    synchronize_session="fetch"
                )
                session.query(WordInterval).filter(
                    WordInterval.workflow_id == CorpusWorkflow.id
                ).filter(
                    CorpusWorkflow.workflow_type == WorkflowType.per_speaker_transcription
                ).delete(
                    synchronize_session="fetch"
                )
                session.query(CorpusWorkflow).filter(
                    CorpusWorkflow.workflow_type == WorkflowType.per_speaker_transcription
                ).delete()
                session.query(Utterance).update({Utterance.transcription_text: None})
                session.commit()
            validator = PretrainedValidator(
                acoustic_model_path=self.acoustic_model.source,
                corpus_directory=self.corpus.corpus_directory,
                dictionary_path=self.corpus.dictionary_model.path,
                test_transcriptions=self.test_transcriptions,
                target_num_ngrams=self.target_num_ngrams,
                first_max_active=750,
            )
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
            self.signals.finished.emit()  # Done
