from __future__ import annotations

import os
import subprocess
import sys
import traceback

import sqlalchemy
from _kalpy.ivector import Plda
from kalpy.utils import read_kaldi_object
from montreal_forced_aligner import config
from montreal_forced_aligner.command_line.utils import check_databases
from montreal_forced_aligner.config import MfaConfiguration, get_temporary_directory
from montreal_forced_aligner.corpus import AcousticCorpus
from montreal_forced_aligner.data import WorkflowType
from montreal_forced_aligner.db import CorpusWorkflow
from montreal_forced_aligner.diarization.speaker_diarizer import FOUND_SPEECHBRAIN
from montreal_forced_aligner.exceptions import DatabaseError
from montreal_forced_aligner.g2p.generator import PyniniValidator
from montreal_forced_aligner.models import (
    AcousticModel,
    IvectorExtractorModel,
    LanguageModel,
    ModelManager,
)
from montreal_forced_aligner.utils import DatasetType, inspect_database
from PySide6 import QtCore, QtGui, QtMultimedia, QtWidgets

import anchor.db
from anchor import workers
from anchor.models import (
    CorpusModel,
    CorpusSelectionModel,
    DiarizationModel,
    DictionaryTableModel,
    OovModel,
    SpeakerModel,
)
from anchor.settings import AnchorSettings
from anchor.ui_error_dialog import Ui_ErrorDialog
from anchor.ui_main_window import Ui_MainWindow
from anchor.ui_preferences import Ui_PreferencesDialog
from anchor.widgets import MediaPlayer, ProgressWidget


class MainWindow(QtWidgets.QMainWindow):
    configUpdated = QtCore.Signal(object)
    g2pLoaded = QtCore.Signal(object)
    ivectorExtractorLoaded = QtCore.Signal(object)
    acousticModelLoaded = QtCore.Signal(object)
    languageModelLoaded = QtCore.Signal(object)
    newSpeaker = QtCore.Signal(object)

    def __init__(self, debug):
        super().__init__()
        QtCore.QCoreApplication.setOrganizationName("Montreal Corpus Tools")
        QtCore.QCoreApplication.setApplicationName("Anchor")
        self.workers = []

        fonts = [
            "GentiumPlus",
            "CharisSIL",
            "NotoSans-Black",
            "NotoSans-Bold",
            "NotoSans-BoldItalic",
            "NotoSans-Italic",
            "NotoSans-Light",
            "NotoSans-Medium",
            "NotoSans-MediumItalic",
            "NotoSans-Regular",
            "NotoSans-Thin",
            "NotoSerif-Black",
            "NotoSerif-Bold",
            "NotoSerif-BoldItalic",
            "NotoSerif-Italic",
            "NotoSerif-Light",
            "NotoSerif-Medium",
            "NotoSerif-MediumItalic",
            "NotoSerif-Regular",
            "NotoSerif-Thin",
        ]
        for font in fonts:
            QtGui.QFontDatabase.addApplicationFont(f":fonts/{font}.ttf")
        if not os.path.exists(os.path.join(get_temporary_directory(), "Anchor")):
            os.makedirs(os.path.join(get_temporary_directory(), "Anchor"))
        self._db_engine = None
        self.initialize_database()

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.corpus = None
        self.debug = debug
        self.status_indicator = ProgressWidget()
        self.status_indicator.setFixedWidth(self.ui.statusbar.height())
        self.ui.statusbar.addPermanentWidget(self.status_indicator, 0)
        self.settings = AnchorSettings()
        self.sync_models()
        if self.settings.contains(AnchorSettings.GEOMETRY):
            self.restoreGeometry(self.settings.value(AnchorSettings.GEOMETRY))
            self.restoreState(self.settings.value(AnchorSettings.WINDOW_STATE))
        self.tabifyDockWidget(self.ui.utteranceDockWidget, self.ui.dictionaryDockWidget)
        self.tabifyDockWidget(self.ui.utteranceDockWidget, self.ui.oovDockWidget)
        self.tabifyDockWidget(self.ui.utteranceDockWidget, self.ui.alignmentDockWidget)
        self.tabifyDockWidget(self.ui.utteranceDockWidget, self.ui.transcriptionDockWidget)
        self.tabifyDockWidget(self.ui.utteranceDockWidget, self.ui.acousticModelDockWidget)
        self.tabifyDockWidget(self.ui.utteranceDockWidget, self.ui.languageModelDockWidget)
        self.tabifyDockWidget(self.ui.utteranceDockWidget, self.ui.speakerDockWidget)
        self.tabifyDockWidget(self.ui.utteranceDockWidget, self.ui.diarizationDockWidget)
        self.media_player = MediaPlayer(self)
        self.media_player.playbackStateChanged.connect(self.handleAudioState)
        self.media_player.audioReady.connect(self.file_loaded)
        self.media_player.timeChanged.connect(
            self.ui.utteranceDetailWidget.plot_widget.audio_plot.update_play_line
        )
        if self.settings.contains(AnchorSettings.VOLUME):
            self.media_player.set_volume(self.settings.value(AnchorSettings.VOLUME))
        self.ui.loadingScreen.setVisible(False)
        self.ui.titleScreen.setVisible(True)

        self.thread_pool = QtCore.QThreadPool()

        self.single_runners = {
            "Calculating OOVs": None,
            "Comparing speakers": None,
            "Counting utterance results": None,
            "Counting speaker results": None,
            "Counting diarization results": None,
            "Diarizing utterances": None,
            "Recalculating speaker ivectors": None,
            "Finding duplicates": None,
            "Querying utterances": None,
            "Querying speakers": None,
            "Querying dictionary": None,
            "Querying OOVs": None,
            "Counting OOV results": None,
            "Clustering speaker utterances": None,
            "Generating speaker MDS": None,
            "Loading speaker ivectors": None,
            "Merging speakers": None,
        }
        self.sequential_runners = {
            "Exporting files": [],
            # "Changing speakers": [],
        }
        self.quick_runners = {
            "Generating waveform",
            "Generating scaled waveform",
            "Generating spectrogram",
            "Generating pitch track",
            "Creating speaker tiers",
        }
        self.current_query_worker = None
        self.current_count_worker = None
        self.current_speaker_comparison_worker = None
        self.current_speaker_merge_worker = None

        self.download_worker = workers.DownloadWorker(self)
        self.download_worker.signals.error.connect(self.handle_error)
        self.download_worker.signals.result.connect(self.finalize_download)
        self.workers.append(self.download_worker)

        self.dictionary_worker = workers.ImportDictionaryWorker(self)
        self.dictionary_worker.signals.error.connect(self.handle_error)
        self.dictionary_worker.signals.result.connect(self.finalize_load_dictionary)
        self.workers.append(self.dictionary_worker)

        self.oov_worker = workers.OovCountWorker(self)
        self.oov_worker.signals.error.connect(self.handle_error)
        self.oov_worker.signals.result.connect(self.finalize_oov_count)
        self.workers.append(self.oov_worker)

        self.acoustic_model_worker = workers.ImportAcousticModelWorker(self)
        self.acoustic_model_worker.signals.error.connect(self.handle_error)
        self.acoustic_model_worker.signals.result.connect(self.finalize_load_acoustic_model)
        self.workers.append(self.acoustic_model_worker)

        self.language_model_worker = workers.ImportLanguageModelWorker(self)
        self.language_model_worker.signals.error.connect(self.handle_error)
        self.language_model_worker.signals.result.connect(self.finalize_load_language_model)
        self.workers.append(self.language_model_worker)

        self.g2p_model_worker = workers.ImportG2PModelWorker(self)
        self.g2p_model_worker.signals.error.connect(self.handle_error)
        self.g2p_model_worker.signals.result.connect(self.finalize_load_g2p_model)
        self.workers.append(self.g2p_model_worker)

        self.ivector_extractor_worker = workers.ImportIvectorExtractorWorker(self)
        self.ivector_extractor_worker.signals.error.connect(self.handle_error)
        self.ivector_extractor_worker.signals.result.connect(self.finalize_load_ivector_extractor)
        self.workers.append(self.ivector_extractor_worker)

        self.transcription_worker = workers.TranscriptionWorker(self)
        self.transcription_worker.signals.error.connect(self.handle_error)
        self.transcription_worker.signals.finished.connect(self.finalize_adding_intervals)
        self.workers.append(self.transcription_worker)

        self.validation_worker = workers.ValidationWorker(self)
        self.validation_worker.signals.error.connect(self.handle_error)
        self.validation_worker.signals.finished.connect(self.finalize_adding_intervals)
        self.workers.append(self.validation_worker)

        self.alignment_worker = workers.AlignmentWorker(self)
        self.alignment_worker.signals.error.connect(self.handle_error)
        self.alignment_worker.signals.finished.connect(self.finalize_adding_intervals)
        self.workers.append(self.alignment_worker)

        self.compute_ivectors_worker = workers.ComputeIvectorWorker(self)
        self.compute_ivectors_worker.signals.error.connect(self.handle_error)
        self.compute_ivectors_worker.signals.finished.connect(self.finalize_adding_ivectors)
        self.workers.append(self.compute_ivectors_worker)

        self.compute_plda_worker = workers.ComputePldaWorker(self)
        self.compute_plda_worker.signals.error.connect(self.handle_error)
        self.compute_plda_worker.signals.result.connect(self.finalize_computing_plda)
        self.workers.append(self.compute_plda_worker)

        self.cluster_utterances_worker = workers.ClusterUtterancesWorker(self)
        self.cluster_utterances_worker.signals.error.connect(self.handle_error)
        self.cluster_utterances_worker.signals.finished.connect(
            self.finalize_clustering_utterances
        )
        self.workers.append(self.cluster_utterances_worker)

        self.classify_speakers_worker = workers.ClassifySpeakersWorker(self)
        self.classify_speakers_worker.signals.error.connect(self.handle_error)
        self.classify_speakers_worker.signals.finished.connect(self.finalize_clustering_utterances)
        self.workers.append(self.classify_speakers_worker)

        self.alignment_utterance_worker = workers.AlignUtteranceWorker(self)
        self.alignment_utterance_worker.signals.error.connect(self.handle_error)
        self.alignment_utterance_worker.signals.result.connect(self.finalize_utterance_alignment)
        self.workers.append(self.alignment_utterance_worker)

        self.segment_utterance_worker = workers.SegmentUtteranceWorker(self)
        self.segment_utterance_worker.signals.error.connect(self.handle_error)
        self.segment_utterance_worker.signals.result.connect(self.finalize_segmentation)
        self.workers.append(self.segment_utterance_worker)

        self.alignment_evaluation_worker = workers.AlignmentEvaluationWorker(self)
        self.alignment_evaluation_worker.signals.error.connect(self.handle_error)
        self.alignment_evaluation_worker.signals.finished.connect(self.finalize_adding_intervals)
        self.workers.append(self.alignment_evaluation_worker)

        self.corpus_worker = workers.ImportCorpusWorker(self)
        self.corpus_worker.signals.result.connect(self.finalize_load_corpus)
        self.corpus_worker.signals.error.connect(self.handle_error)
        self.workers.append(self.corpus_worker)

        self.load_reference_worker = workers.LoadReferenceWorker(self)
        self.load_reference_worker.signals.error.connect(self.handle_error)
        self.load_reference_worker.signals.finished.connect(self.finalize_adding_intervals)
        self.workers.append(self.load_reference_worker)

        self.undo_group = QtGui.QUndoGroup(self)
        self.corpus_undo_stack = QtGui.QUndoStack(self)
        self.dictionary_undo_stack = QtGui.QUndoStack(self)

        self.set_up_models()
        if self.settings.value(AnchorSettings.AUTOLOAD):
            self.load_corpus()
        else:
            self.set_application_state("unloaded")
        self.load_ivector_extractor()
        # self.load_dictionary()
        self.load_acoustic_model()
        self.load_language_model()
        self.load_g2p()
        self.create_actions()
        self.refresh_settings()
        self.refresh_shortcuts()
        self.refresh_style_sheets()
        self.refresh_fonts()

    def finalize_download(self):
        self.refresh_model_actions()

    @property
    def db_string(self):
        return f"postgresql+psycopg2://@/anchor?host={config.database_socket()}"

    @property
    def db_engine(self) -> sqlalchemy.engine.Engine:
        """Database engine"""
        if self._db_engine is None:
            self._db_engine = sqlalchemy.create_engine(self.db_string)
        return self._db_engine

    def initialize_database(self):
        try:
            check_databases(db_name="anchor")
            return
        except Exception:
            try:
                subprocess.check_call(
                    [
                        "createdb",
                        f"--host={config.database_socket()}",
                        "anchor",
                    ],
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                )
            except Exception:
                raise DatabaseError(
                    f"There was an error connecting to the {config.CURRENT_PROFILE_NAME} MFA database server. "
                    "Please ensure the server is initialized (mfa server init) or running (mfa server start)"
                )

            from anchor.db import AnchorSqlBase

            AnchorSqlBase.metadata.create_all(self.db_engine)

    def sync_models(self):
        self.model_manager = ModelManager(token=self.settings.value(AnchorSettings.GITHUB_TOKEN))
        try:
            self.model_manager.refresh_remote()
        except Exception:
            return
        with sqlalchemy.orm.Session(self.db_engine) as session:
            for model_type, db_class in anchor.db.MODEL_TYPES.items():
                if model_type not in self.model_manager.local_models:
                    continue
                current_models = {x.name: x for x in session.query(db_class)}
                for m in self.model_manager.local_models[model_type]:
                    if m not in current_models:
                        current_models[m] = db_class(name=m, path=m, available_locally=True)
                        session.add(current_models[m])
                    else:
                        current_models[m].available_locally = True
                for m in self.model_manager.remote_models[model_type]:
                    if m not in current_models:
                        current_models[m] = db_class(name=m, path=m, available_locally=False)
                        session.add(current_models[m])
                session.flush()
            session.commit()

    def file_loaded(self, ready):
        if ready:
            self.ui.playAct.setEnabled(ready)
        else:
            self.ui.playAct.setEnabled(False)
            self.ui.playAct.setChecked(False)

    def corpus_changed(self, clean):
        if clean:
            self.ui.revertChangesAct.setEnabled(False)
            self.ui.saveChangesAct.setEnabled(False)
        else:
            self.ui.revertChangesAct.setEnabled(True)
            self.ui.saveChangesAct.setEnabled(True)

    def handle_changes_synced(self, changed: bool):
        self.ui.revertChangesAct.setEnabled(False)
        self.undo_group.setActiveStack(self.corpus_undo_stack)
        self.corpus_undo_stack.setClean()
        self.ui.saveChangesAct.setEnabled(False)

    def execute_runnable(self, function, finished_function, extra_args=None):
        if self.corpus_model.corpus is None:
            return
        delayed_start = False
        if function == "Replacing query":
            worker = workers.ReplaceAllWorker(self.corpus_model.session, *extra_args)
            worker.signals.result.connect(finished_function)
        elif function == "Changing speakers":
            worker = workers.ChangeSpeakerWorker(self.corpus_model.session, *extra_args)
            worker.signals.result.connect(finished_function)
        elif function == "Recalculating speaker ivectors":
            worker = workers.RecalculateSpeakerWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Loading speakers":
            worker = workers.LoadSpeakersWorker(self.corpus_model.session, *extra_args)
            worker.signals.result.connect(finished_function)
        elif function == "Loading files":
            worker = workers.LoadFilesWorker(self.corpus_model.session, *extra_args)
            worker.signals.result.connect(finished_function)
        elif function == "Loading dictionaries":
            worker = workers.LoadDictionariesWorker(self.corpus_model.session, *extra_args)
            worker.signals.result.connect(finished_function)
        elif function == "Rebuilding lexicon FSTs":
            worker = workers.LexiconFstBuildWorker(self.corpus_model, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Calculating OOVs":
            self.calculate_oovs()
            return
        elif function == "Finding duplicates":
            self.set_application_state("loading")
            worker = workers.DuplicateFilesWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Counting utterance results":
            worker = workers.QueryUtterancesWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Diarizing utterances":
            worker = workers.SpeakerDiarizationWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Counting diarization results":
            worker = workers.SpeakerDiarizationWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Merging speakers":
            self.set_application_state("loading")
            worker = workers.MergeSpeakersWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.finished.connect(finished_function)
        elif function == "Reassigning utterances":
            worker = workers.MismatchedUtterancesWorker(self.corpus_model.session, **extra_args[0])
            self.set_application_state("loading")
            worker.signals.finished.connect(finished_function)
        elif function == "Reassigning utterances for speaker":
            worker = workers.BulkUpdateSpeakerUtterancesWorker(
                self.corpus_model.session, **extra_args[0]
            )
            worker.signals.finished.connect(finished_function)
        elif function == "Querying utterances":
            worker = workers.QueryUtterancesWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Querying speakers":
            worker = workers.QuerySpeakersWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Counting speaker results":
            worker = workers.QuerySpeakersWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Creating speaker tiers":
            worker = workers.FileUtterancesWorker(self.corpus_model.session, *extra_args)
            worker.signals.result.connect(finished_function)
        elif function == "Counting dictionary results":
            worker = workers.QueryDictionaryWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Querying dictionary":
            worker = workers.QueryDictionaryWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Querying OOVs":
            worker = workers.QueryOovWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Counting OOV results":
            worker = workers.QueryOovWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Clustering speaker utterances":
            worker = workers.ClusterSpeakerUtterancesWorker(
                self.corpus_model.session, **extra_args[0]
            )
            worker.signals.result.connect(finished_function)
        elif function == "Loading speaker ivectors":
            worker = workers.CalculateSpeakerIvectorsWorker(
                self.corpus_model.session, **extra_args[0]
            )
            worker.signals.result.connect(finished_function)
        elif function == "Generating speaker MDS":
            worker = workers.SpeakerMdsWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Exporting dictionary":
            self.set_application_state("loading")
            self.ui.loadingScreen.setCorpusName("Saving dictionary changes...")
            worker = workers.ExportLexiconWorker(self.corpus_model.session, **extra_args[0])
            worker.signals.result.connect(finished_function)
        elif function == "Exporting files":
            worker = workers.ExportFilesWorker(self.corpus_model.session, *extra_args)
            self.set_application_state("loading", worker)
            self.ui.loadingScreen.setCorpusName("Saving changes...")
            worker.signals.result.connect(finished_function)
        else:
            if extra_args is None:
                extra_args = []
            worker = workers.Worker(function, *extra_args)
            worker.signals.result.connect(finished_function)
        if function in self.single_runners:
            if self.single_runners[function] is not None:
                self.single_runners[function].cancel()
            self.single_runners[function] = worker
        if function in self.sequential_runners:
            delayed_start = len(self.sequential_runners[function]) > 0
            if delayed_start:
                self.sequential_runners[function][-1].signals.finished.connect(
                    lambda: self.thread_pool.start(worker)
                )
            self.sequential_runners[function].append(worker)
            worker.signals.finished.connect(self.update_sequential_runners)

        worker.signals.error.connect(self.handle_error)
        # Execute
        if not delayed_start:
            self.thread_pool.start(worker)
        if function not in self.quick_runners:
            if isinstance(function, str):
                worker.name = function
            self.status_indicator.add_worker(worker)

    def update_sequential_runners(self):
        sender = self.sender()
        for k, v in self.sequential_runners.items():
            self.sequential_runners[k] = [x for x in v if x.signals != sender]

    def set_up_models(self):
        self.dictionary_model = DictionaryTableModel(self)
        self.oov_model = OovModel(self)
        self.corpus_model = CorpusModel(self)
        self.speaker_model = SpeakerModel(self)
        self.diarization_model = DiarizationModel(self)

        self.corpus_model.databaseSynced.connect(self.handle_changes_synced)
        self.corpus_model.runFunction.connect(self.execute_runnable)
        self.diarization_model.runFunction.connect(self.execute_runnable)
        self.corpus_model.lockCorpus.connect(self.anchor_lock_corpus)
        self.corpus_model.statusUpdate.connect(self.update_status_message)
        self.corpus_model.unlockCorpus.connect(self.anchor_unlock_corpus)
        self.corpus_model.corpusLoaded.connect(self.fully_loaded)
        self.corpus_model.filesSaved.connect(self.save_completed)
        self.corpus_model.requestFileView.connect(self.open_search_file)
        self.speaker_model.runFunction.connect(self.execute_runnable)
        self.dictionary_model.runFunction.connect(self.execute_runnable)
        self.oov_model.runFunction.connect(self.execute_runnable)
        self.dictionary_model.set_corpus_model(self.corpus_model)
        self.corpus_model.set_dictionary_model(self.dictionary_model)
        self.speaker_model.set_corpus_model(self.corpus_model)
        self.diarization_model.set_corpus_model(self.corpus_model)
        self.oov_model.set_corpus_model(self.corpus_model)
        self.selection_model = CorpusSelectionModel(self.corpus_model)
        self.ui.utteranceListWidget.set_models(
            self.corpus_model, self.selection_model, self.speaker_model
        )
        self.ui.utteranceDetailWidget.set_models(
            self.corpus_model, self.selection_model, self.dictionary_model
        )
        self.ui.speakerWidget.set_models(
            self.corpus_model, self.selection_model, self.speaker_model
        )
        self.ui.transcriptionWidget.set_models(self.corpus_model, self.dictionary_model)
        self.ui.alignmentWidget.set_models(self.corpus_model)
        self.ui.acousticModelWidget.set_models(self.corpus_model)
        self.ui.languageModelWidget.set_models(self.corpus_model)
        self.ui.dictionaryWidget.set_models(self.dictionary_model)
        self.ui.diarizationWidget.set_models(self.diarization_model, self.selection_model)
        self.ui.oovWidget.set_models(self.oov_model)
        self.selection_model.selectionChanged.connect(self.change_utterance)
        self.selection_model.fileChanged.connect(self.change_file)
        self.selection_model.fileAboutToChange.connect(self.check_media_stop)
        self.media_player.set_corpus_models(self.corpus_model, self.selection_model)
        self.corpus_model.addCommand.connect(self.update_corpus_stack)

        self.g2p_model = None
        self.acoustic_model = None
        self.language_model = None
        self.ivector_extractor = None

    def check_media_stop(self):
        if self.ui.playAct.isChecked():
            self.ui.playAct.setChecked(False)
            self.media_player.stop()

    def update_status_message(self, message: str):
        self.ui.statusbar.showMessage(message)

    def anchor_lock_corpus(self):
        self.ui.lockEditAct.setChecked(True)
        self.ui.lockEditAct.setEnabled(False)

    def anchor_unlock_corpus(self):
        self.ui.lockEditAct.setChecked(False)
        self.ui.lockEditAct.setEnabled(True)

    def update_corpus_stack(self, command):
        self.undo_group.setActiveStack(self.corpus_undo_stack)
        self.corpus_undo_stack.push(command)

    def update_dictionary_stack(self, command):
        self.undo_group.setActiveStack(self.dictionary_undo_stack)
        self.dictionary_undo_stack.push(command)

    def delete_utterances(self):
        utts = self.selection_model.selectedUtterances()
        self.corpus_model.delete_utterances(utts)

    def split_utterances(self):
        utts = self.selection_model.selectedUtterances()
        self.corpus_model.split_utterances(utts)

    def merge_utterances(self):
        utts = self.selection_model.selectedUtterances()
        self.corpus_model.merge_utterances(utts)

    def check_actions(self):
        self.ui.lockEditAct.setEnabled(True)
        self.ui.transcribeCorpusAct.setEnabled(True)
        self.ui.alignCorpusAct.setEnabled(True)
        self.ui.loadReferenceAlignmentsAct.setEnabled(True)
        self.ui.closeLanguageModelAct.setEnabled(True)
        self.ui.closeDictionaryAct.setEnabled(True)
        self.ui.evaluateAlignmentsAct.setEnabled(True)
        self.ui.closeAcousticModelAct.setEnabled(True)
        self.ui.closeG2PAct.setEnabled(True)
        self.ui.saveDictionaryAct.setEnabled(True)
        self.ui.closeIvectorExtractorAct.setEnabled(True)
        if self.corpus_model.language_model is None:
            self.ui.closeLanguageModelAct.setEnabled(False)
        if self.corpus_model.g2p_model is None:
            self.ui.closeG2PAct.setEnabled(False)
        if self.corpus_model.acoustic_model is None:
            self.ui.alignCorpusAct.setEnabled(False)
            self.ui.transcribeCorpusAct.setEnabled(False)
            self.ui.loadReferenceAlignmentsAct.setEnabled(False)
            self.ui.evaluateAlignmentsAct.setEnabled(False)
            self.ui.closeAcousticModelAct.setEnabled(False)
        if self.corpus_model.corpus is None:
            self.ui.alignCorpusAct.setEnabled(False)
            self.ui.transcribeCorpusAct.setEnabled(False)
            self.ui.loadReferenceAlignmentsAct.setEnabled(False)
            self.ui.evaluateAlignmentsAct.setEnabled(False)
            self.ui.find_duplicates_action.setEnabled(False)
            self.ui.cluster_utterances_action.setEnabled(False)
            self.ui.classify_speakers_action.setEnabled(False)
        else:
            if (
                not self.corpus_model.corpus.has_alignments()
                or not self.corpus_model.corpus.has_alignments(WorkflowType.reference)
            ):
                self.ui.evaluateAlignmentsAct.setEnabled(False)
            # if self.corpus_model.corpus.alignment_done:
            #    self.ui.alignCorpusAct.setEnabled(False)
            if self.corpus_model.corpus.transcription_done:
                self.ui.transcribeCorpusAct.setEnabled(False)
            self.ui.find_duplicates_action.setEnabled(self.corpus_model.corpus.has_any_ivectors())
            self.ui.cluster_utterances_action.setEnabled(
                self.corpus_model.corpus.has_any_ivectors()
            )
            self.ui.classify_speakers_action.setEnabled(
                self.corpus_model.corpus.has_any_ivectors()
            )

        if self.corpus_model.corpus is None or inspect_database(
            self.corpus_model.corpus.data_source_identifier
        ) not in {
            DatasetType.ACOUSTIC_CORPUS_WITH_DICTIONARY,
            DatasetType.TEXT_CORPUS_WITH_DICTIONARY,
        }:
            self.ui.alignCorpusAct.setEnabled(False)
            self.ui.transcribeCorpusAct.setEnabled(False)
            self.ui.evaluateAlignmentsAct.setEnabled(False)
            self.ui.closeDictionaryAct.setEnabled(False)
            # self.ui.saveDictionaryAct.setEnabled(False)

    def change_file(self):
        self.ui.playAct.setChecked(False)
        if self.selection_model.current_file is None:
            self.ui.playAct.setEnabled(False)
            self.ui.panLeftAct.setEnabled(False)
            self.ui.panRightAct.setEnabled(False)
            self.ui.zoomInAct.setEnabled(False)
            self.ui.zoomToSelectionAct.setEnabled(False)
            self.ui.zoomOutAct.setEnabled(False)
        else:
            self.ui.playAct.setEnabled(True)
            self.ui.panLeftAct.setEnabled(True)
            self.ui.panRightAct.setEnabled(True)
            self.ui.zoomInAct.setEnabled(True)
            self.ui.zoomToSelectionAct.setEnabled(True)
            self.ui.zoomOutAct.setEnabled(True)
        if hasattr(self, "channel_select"):
            with QtCore.QSignalBlocker(self.channel_select):
                self.channel_select.clear()
                self.channel_select.addItem("Channel 0", userData=0)
                self.channel_select.setEnabled(False)
                if (
                    self.selection_model.current_file is not None
                    and self.selection_model.current_file.num_channels > 1
                ):
                    self.channel_select.addItem("Channel 1", userData=1)
                    self.channel_select.setEnabled(True)

    def change_utterance(self):
        selection = self.selection_model.selectedUtterances()
        self.ui.deleteUtterancesAct.setEnabled(False)
        self.ui.splitUtterancesAct.setEnabled(False)
        self.ui.alignUtteranceAct.setEnabled(False)
        self.ui.segmentUtteranceAct.setEnabled(False)
        if not selection:
            return

        self.ui.splitUtterancesAct.setEnabled(True)
        if len(selection) == 1:
            self.ui.mergeUtterancesAct.setEnabled(False)
            if self.corpus_model.acoustic_model is not None and self.corpus_model.has_dictionary:
                self.ui.alignUtteranceAct.setEnabled(True)
                self.ui.segmentUtteranceAct.setEnabled(True)
        else:
            self.ui.mergeUtterancesAct.setEnabled(True)
        self.ui.deleteUtterancesAct.setEnabled(True)

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        for worker in self.workers:
            worker.stopped.set()
        self.ui.utteranceDetailWidget.plot_widget.clean_up_for_close()
        self.settings.setValue(
            AnchorSettings.UTTERANCES_VISIBLE, self.ui.utteranceDockWidget.isVisible()
        )
        self.settings.setValue(
            AnchorSettings.DICTIONARY_VISIBLE, self.ui.dictionaryDockWidget.isVisible()
        )
        self.settings.setValue(
            AnchorSettings.DICTIONARY_VISIBLE, self.ui.oovDockWidget.isVisible()
        )
        self.settings.setValue(
            AnchorSettings.SPEAKERS_VISIBLE, self.ui.speakerDockWidget.isVisible()
        )
        self.settings.setValue(
            AnchorSettings.LM_VISIBLE, self.ui.languageModelDockWidget.isVisible()
        )
        self.settings.setValue(
            AnchorSettings.AM_VISIBLE, self.ui.acousticModelDockWidget.isVisible()
        )
        self.settings.setValue(
            AnchorSettings.TRANSCRIPTION_VISIBLE, self.ui.transcriptionDockWidget.isVisible()
        )
        self.settings.setValue(
            AnchorSettings.ALIGNMENT_VISIBLE, self.ui.alignmentDockWidget.isVisible()
        )
        self.settings.setValue(
            AnchorSettings.DIARIZATION_VISIBLE, self.ui.diarizationDockWidget.isVisible()
        )
        self.set_application_state("loading")
        self.ui.loadingScreen.setExiting()
        self.close_timer = QtCore.QTimer()
        self.close_timer.timeout.connect(lambda: self._actual_close(a0))
        self.close_timer.start(1000)

    def _actual_close(self, a0):
        for worker in self.workers:
            if not worker.finished():
                return
        if self.thread_pool.activeThreadCount() > 0:
            return
        self.settings.setValue(AnchorSettings.GEOMETRY, self.saveGeometry())
        self.settings.setValue(AnchorSettings.WINDOW_STATE, self.saveState())

        self.settings.sync()
        if self.corpus_model.session is not None:
            self.corpus_model.session = None
            self.corpus_model.corpus.cleanup_connections()
            sqlalchemy.orm.close_all_sessions()
        a0.accept()

    def create_actions(self):
        w = QtWidgets.QWidget(self)
        w.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding
        )
        self.ui.toolBar.insertWidget(self.ui.toolBar.actions()[0], w)
        self.ui.toolBar.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding
        )
        self.ui.toolBar.addWidget(w)
        self.ui.toolBar.setAttribute(QtCore.Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        self.ui.lockEditAct.setEnabled(True)
        self.ui.lockEditAct.setChecked(bool(self.settings.value(AnchorSettings.LOCKED, False)))
        self.ui.lockEditAct.toggled.connect(self.corpus_model.lock_edits)
        self.ui.loadCorpusAct.triggered.connect(self.change_corpus)
        self.ui.reloadCorpusAct.triggered.connect(self.reload_corpus)
        self.ui.closeCurrentCorpusAct.triggered.connect(self.close_corpus)
        self.ui.cancelCorpusLoadAct.triggered.connect(self.cancel_corpus_load)
        self.ui.changeTemporaryDirectoryAct.triggered.connect(self.change_temp_dir)
        self.ui.openPreferencesAct.triggered.connect(self.open_options)
        self.ui.loadAcousticModelAct.triggered.connect(self.change_acoustic_model)
        self.ui.loadLanguageModelAct.triggered.connect(self.change_language_model)
        self.ui.loadIvectorExtractorAct.triggered.connect(self.change_ivector_extractor)
        self.ui.loadDictionaryAct.triggered.connect(self.change_dictionary)
        self.ui.saveDictionaryAct.triggered.connect(self.save_dictionary)
        self.ui.loadG2PModelAct.triggered.connect(self.change_g2p)
        self.ui.loadReferenceAlignmentsAct.triggered.connect(self.load_reference_alignments)
        self.ui.loadingScreen.tool_bar.addAction(self.ui.cancelCorpusLoadAct)
        self.ui.utteranceDetailWidget.pan_left_button.setDefaultAction(self.ui.panLeftAct)
        self.ui.utteranceDetailWidget.pan_right_button.setDefaultAction(self.ui.panRightAct)
        self.ui.playAct.triggered.connect(self.play_audio)
        self.media_player.playbackStateChanged.connect(self.update_play_act)
        self.ui.find_duplicates_action.triggered.connect(self.find_duplicates)
        self.ui.cluster_utterances_action.triggered.connect(self.begin_cluster_utterances)
        self.ui.classify_speakers_action.triggered.connect(self.begin_classify_speakers)
        self.selection_model.selectionAudioChanged.connect(self.enable_zoom)
        self.ui.zoomInAct.triggered.connect(self.selection_model.zoom_in)
        self.ui.zoomToSelectionAct.triggered.connect(self.selection_model.zoom_to_selection)
        self.ui.zoomOutAct.triggered.connect(self.selection_model.zoom_out)
        self.ui.panLeftAct.triggered.connect(self.ui.utteranceDetailWidget.pan_left)
        self.ui.panRightAct.triggered.connect(self.ui.utteranceDetailWidget.pan_right)
        self.ui.mergeUtterancesAct.triggered.connect(self.merge_utterances)
        self.ui.splitUtterancesAct.triggered.connect(self.split_utterances)
        self.ui.searchAct.triggered.connect(self.open_search)
        self.ui.dictionaryWidget.table.searchRequested.connect(self.open_search)
        self.ui.oovWidget.table.searchRequested.connect(self.open_search)
        self.ui.diarizationWidget.table.utteranceSearchRequested.connect(self.open_search_file)
        self.ui.diarizationWidget.table.speakerSearchRequested.connect(self.open_search_speaker)
        self.ui.speakerWidget.table.searchRequested.connect(self.open_search_speaker)
        self.ui.oovWidget.table.g2pRequested.connect(self.dictionary_model.add_word)
        self.dictionary_model.requestLookup.connect(self.open_dictionary)
        self.ui.deleteUtterancesAct.triggered.connect(self.delete_utterances)
        self.ui.lockEditAct.toggled.connect(self.toggle_lock)
        self.ui.exportFilesAct.setEnabled(True)
        self.ui.exportFilesAct.triggered.connect(self.export_files)
        self.ui.showAllSpeakersAct.triggered.connect(
            self.ui.utteranceDetailWidget.plot_widget.update_show_speakers
        )
        self.ui.muteAct.triggered.connect(self.update_mute_status)
        self.volume_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal, self)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximumWidth(100)
        self.volume_slider.setValue(self.media_player.volume())
        self.volume_slider.valueChanged.connect(self.ui.changeVolumeAct.trigger)
        self.channel_select = QtWidgets.QComboBox(self)
        self.channel_select.addItem("Channel 0")
        self.ui.toolBar.addWidget(self.volume_slider)
        self.ui.toolBar.addWidget(self.channel_select)
        self.channel_select.currentIndexChanged.connect(self.selection_model.set_current_channel)
        self.ui.changeVolumeAct.triggered.connect(self.media_player.set_volume)
        self.ui.addSpeakerAct.triggered.connect(self.add_new_speaker)
        self.ui.speakerWidget.tool_bar.addAction(self.ui.addSpeakerAct)
        self.ui.transcribeCorpusAct.triggered.connect(self.begin_transcription)
        self.ui.transcriptionWidget.button.setDefaultAction(self.ui.transcribeCorpusAct)
        self.ui.utteranceListWidget.oov_button.setDefaultAction(self.ui.oovsOnlyAct)
        self.ui.alignmentWidget.button.setDefaultAction(self.ui.alignCorpusAct)

        self.ui.alignCorpusAct.triggered.connect(self.begin_alignment)
        self.ui.diarizationWidget.refresh_ivectors_action.triggered.connect(
            self.begin_refresh_ivectors
        )
        self.ui.diarizationWidget.calculate_plda_action.triggered.connect(
            self.begin_calculate_plda
        )
        self.ui.diarizationWidget.reset_ivectors_action.triggered.connect(
            self.begin_reset_ivectors
        )
        self.ui.alignUtteranceAct.triggered.connect(self.begin_utterance_alignment)
        self.ui.segmentUtteranceAct.triggered.connect(self.begin_utterance_segmentation)
        self.ui.evaluateAlignmentsAct.triggered.connect(self.begin_alignment_evaluation)
        self.ui.selectMappingFileAct.triggered.connect(self.change_custom_mapping)

        self.undo_act = self.undo_group.createUndoAction(self, "Undo")
        self.undo_act.setIcon(QtGui.QIcon(":undo.svg"))
        self.redo_act = self.undo_group.createRedoAction(self, "Redo")
        self.redo_act.setIcon(QtGui.QIcon(":redo.svg"))
        self.ui.menuEdit.addAction(self.undo_act)
        self.ui.menuEdit.addAction(self.redo_act)
        self.undo_group.setActiveStack(self.corpus_undo_stack)
        self.corpus_model.undoRequested.connect(self.undo_act.trigger)
        self.corpus_model.redoRequested.connect(self.redo_act.trigger)
        self.corpus_model.playRequested.connect(self.ui.playAct.trigger)
        self.corpus_undo_stack.cleanChanged.connect(self.corpus_changed)
        self.ui.lockEditAct.toggled.connect(self.undo_act.setDisabled)
        self.ui.lockEditAct.toggled.connect(self.redo_act.setDisabled)
        self.ui.menuWindow.addAction(self.ui.utteranceDockWidget.toggleViewAction())
        self.ui.menuWindow.addAction(self.ui.dictionaryDockWidget.toggleViewAction())
        self.ui.menuWindow.addAction(self.ui.oovDockWidget.toggleViewAction())
        self.ui.menuWindow.addAction(self.ui.speakerDockWidget.toggleViewAction())
        self.ui.menuWindow.addAction(self.ui.acousticModelDockWidget.toggleViewAction())
        self.ui.menuWindow.addAction(self.ui.languageModelDockWidget.toggleViewAction())
        self.ui.menuWindow.addAction(self.ui.alignmentDockWidget.toggleViewAction())
        self.ui.menuWindow.addAction(self.ui.transcriptionDockWidget.toggleViewAction())
        self.ui.menuWindow.addAction(self.ui.diarizationDockWidget.toggleViewAction())

        self.merge_all_action = QtGui.QAction(self)
        self.merge_all_action.setObjectName("merge_all_action")
        self.merge_all_action.setText(
            QtCore.QCoreApplication.translate("MainWindow", "Merge close speakers", None)
        )
        self.merge_all_action.triggered.connect(self.merge_all)

        self.mismatched_utterances_action = QtGui.QAction(self)
        self.mismatched_utterances_action.setObjectName("mismatched_utterances_action")
        self.mismatched_utterances_action.setText(
            QtCore.QCoreApplication.translate("MainWindow", "Reassign mismatched utterances", None)
        )
        self.mismatched_utterances_action.triggered.connect(self.reassign_mismatched_utterances)
        self.ui.menuExperimental.addAction(self.merge_all_action)
        self.ui.menuExperimental.addAction(self.mismatched_utterances_action)
        self.ui.getHelpAct.triggered.connect(self.open_help)
        self.ui.reportBugAct.triggered.connect(self.report_bug)

        self.acoustic_action_group = QtGui.QActionGroup(self)
        self.acoustic_action_group.setExclusive(True)

        self.g2p_action_group = QtGui.QActionGroup(self)
        self.g2p_action_group.setExclusive(True)

        self.dictionary_action_group = QtGui.QActionGroup(self)
        self.dictionary_action_group.setExclusive(True)

        self.language_model_action_group = QtGui.QActionGroup(self)
        self.language_model_action_group.setExclusive(True)

        self.ivector_action_group = QtGui.QActionGroup(self)
        self.ivector_action_group.setExclusive(True)

        self.ui.ivectorExtractorMenu.setEnabled(False)
        self.ui.closeIvectorExtractorAct.setEnabled(False)
        self.refresh_corpus_history()
        self.refresh_model_actions()

    def merge_all(self):
        if not self.corpus_model.corpus.has_any_ivectors():
            return
        kwargs = {
            "threshold": 0.2,
            "metric": "cosine",
        }
        if self.corpus_model.plda is not None:
            kwargs["metric"] = "plda"
            kwargs["plda"] = self.corpus_model.plda
            kwargs["speaker_plda"] = self.corpus_model.speaker_plda
            kwargs["threshold"] = 45
        self.execute_runnable("Merging speakers", self.finish_merging, [kwargs])

    def finish_recalculate(self, result):
        if result is not None:
            self.corpus_model.speaker_plda = result

    def finish_merging(self, result=None):
        if result is not None:
            self.update_status_message(f"Merged {result} speakers.")
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

        self.set_application_state("loaded")

    def reassign_mismatched_utterances(self):
        if not self.corpus_model.corpus.has_any_ivectors():
            return
        kwargs = {
            "threshold": 0.3,
        }
        if False and self.corpus_model.plda is not None:
            kwargs["metric"] = "plda"
            kwargs["plda"] = self.corpus_model.plda
            kwargs["speaker_plda"] = self.corpus_model.speaker_plda
            kwargs["threshold"] = 50
        self.execute_runnable(
            "Reassigning utterances", self.finish_mismatched_utterances, [kwargs]
        )

    def finish_mismatched_utterances(self, result=None):
        if result is not None:
            self.update_status_message(f"Updated {result} utterances.")
        self.execute_runnable(
            "Recalculating speaker ivectors",
            self.finish_recalculate,
            [
                {
                    "plda": self.corpus_model.plda,
                    "speaker_plda": self.corpus_model.speaker_plda,
                }
            ],
        )

        self.set_application_state("loaded")

    def update_play_act(self, state):
        if state == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
            self.ui.playAct.setChecked(True)
        else:
            self.ui.playAct.setChecked(False)

    def find_duplicates(self):
        if not self.corpus_model.corpus.has_any_ivectors():
            return
        self.execute_runnable(
            "Finding duplicates",
            self.finish_finding_duplicates,
            [
                {
                    "threshold": 0.05,
                    "working_directory": os.path.join(
                        self.corpus_model.corpus.output_directory, "speaker_diarization"
                    ),
                }
            ],
        )

    def finish_finding_duplicates(self, results):
        self.set_application_state("loaded")
        if not results:
            return
        duplicate_count, duplicate_path = results
        self.update_status_message(
            f"Found {duplicate_count} duplicate files, see {duplicate_path}."
        )

    def refresh_model_actions(self):
        self.ui.menuDownload_acoustic_model.clear()
        self.ui.menuDownload_G2P_model.clear()
        self.ui.menuDownload_language_model.clear()
        self.ui.menuDownload_dictionary.clear()
        self.ui.menuDownload_ivector_extractor.clear()
        with sqlalchemy.orm.Session(self.db_engine) as session:
            for (m,) in (
                session.query(anchor.db.AcousticModel.name)
                .filter_by(available_locally=False)
                .order_by(anchor.db.AcousticModel.name)
            ):
                a = QtGui.QAction(m, parent=self)
                a.triggered.connect(self.download_acoustic_model)
                self.ui.menuDownload_acoustic_model.addAction(a)
            for (m,) in (
                session.query(anchor.db.LanguageModel.name)
                .filter_by(available_locally=False)
                .order_by(anchor.db.LanguageModel.name)
            ):
                a = QtGui.QAction(m, parent=self)
                a.triggered.connect(self.download_language_model)
                self.ui.menuDownload_language_model.addAction(a)
            for (m,) in (
                session.query(anchor.db.G2PModel.name)
                .filter_by(available_locally=False)
                .order_by(anchor.db.G2PModel.name)
            ):
                a = QtGui.QAction(m, parent=self)
                a.triggered.connect(self.download_g2p_model)
                self.ui.menuDownload_G2P_model.addAction(a)
            for (m,) in (
                session.query(anchor.db.Dictionary.name)
                .filter_by(available_locally=False)
                .order_by(anchor.db.Dictionary.name)
            ):
                a = QtGui.QAction(m, parent=self)
                a.triggered.connect(self.download_dictionary)
                self.ui.menuDownload_dictionary.addAction(a)
            for (m,) in (
                session.query(anchor.db.IvectorExtractor.name)
                .filter_by(available_locally=False)
                .order_by(anchor.db.IvectorExtractor.name)
            ):
                a = QtGui.QAction(m, parent=self)
                a.triggered.connect(self.download_ivector_extractor)
                self.ui.menuDownload_ivector_extractor.addAction(a)

            current_corpus = (
                session.query(anchor.db.AnchorCorpus)
                .options(
                    sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.acoustic_model),
                    sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.language_model),
                    sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.dictionary),
                    sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.ivector_extractor),
                    sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.g2p_model),
                    sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.sad_model),
                )
                .filter(anchor.db.AnchorCorpus.current == True)  # noqa
                .first()
            )
            for m in session.query(anchor.db.AcousticModel).filter_by(available_locally=True):
                a = QtGui.QAction(f"{m.path} [{m.name}]", parent=self)
                a.setData(m.id)
                a.setCheckable(True)
                if (
                    current_corpus is not None
                    and current_corpus.acoustic_model is not None
                    and current_corpus.acoustic_model == m
                ):
                    a.setChecked(True)
                a.triggered.connect(self.change_acoustic_model)
                self.acoustic_action_group.addAction(a)
                self.ui.acousticModelMenu.addAction(a)

            for m in session.query(anchor.db.Dictionary).filter_by(available_locally=True):
                a = QtGui.QAction(text=f"{m.path} [{m.name}]", parent=self)
                a.setData(m.id)
                if (
                    current_corpus is not None
                    and current_corpus.dictionary is not None
                    and current_corpus.dictionary == m
                ):
                    a.setChecked(True)
                a.triggered.connect(self.change_dictionary)
                self.dictionary_action_group.addAction(a)
                self.ui.mfaDictionaryMenu.addAction(a)

            for m in session.query(anchor.db.LanguageModel).filter_by(available_locally=True):
                a = QtGui.QAction(text=f"{m.path} [{m.name}]", parent=self)
                a.setData(m.id)
                if (
                    current_corpus is not None
                    and current_corpus.language_model is not None
                    and current_corpus.language_model == m
                ):
                    a.setChecked(True)
                a.triggered.connect(self.change_language_model)
                self.ui.languageModelMenu.addAction(a)
                self.language_model_action_group.addAction(a)

            for m in session.query(anchor.db.G2PModel).filter_by(available_locally=True):
                a = QtGui.QAction(text=f"{m.path} [{m.name}]", parent=self)
                a.setData(m.id)
                if (
                    current_corpus is not None
                    and current_corpus.g2p_model is not None
                    and current_corpus.g2p_model == m
                ):
                    a.setChecked(True)
                a.triggered.connect(self.change_g2p)
                self.ui.g2pMenu.addAction(a)
                self.g2p_action_group.addAction(a)

            if FOUND_SPEECHBRAIN:
                m = (
                    session.query(anchor.db.IvectorExtractor)
                    .filter(anchor.db.IvectorExtractor.path == "speechbrain")
                    .first()
                )
                if m is None:
                    session.add(
                        anchor.db.IvectorExtractor(
                            name="speechbrain", path="speechbrain", available_locally=True
                        )
                    )
                    session.flush()
                    session.commit()
                a = QtGui.QAction(text="speechbrain", parent=self)
                a.setData(m.id)
                a.triggered.connect(self.change_ivector_extractor)
                self.ui.ivectorExtractorMenu.addAction(a)
                self.ivector_action_group.addAction(a)

            for m in session.query(anchor.db.IvectorExtractor).filter(
                anchor.db.IvectorExtractor.available_locally == True,  # noqa
                anchor.db.IvectorExtractor.name != "speechbrain",
            ):
                a = QtGui.QAction(text=f"{m.path} [{m.name}]", parent=self)
                a.setData(m.id)
                if (
                    current_corpus is not None
                    and current_corpus.ivector_extractor is not None
                    and current_corpus.ivector_extractor == m
                ):
                    a.setChecked(True)
                a.triggered.connect(self.change_ivector_extractor)
                self.ui.ivectorExtractorMenu.addAction(a)
                self.ivector_action_group.addAction(a)

    def toggle_lock(self, locked):
        self.settings.setValue(AnchorSettings.LOCKED, locked)

    def handleAudioState(self, state):
        if state == QtMultimedia.QMediaPlayer.PlaybackState.StoppedState:
            self.ui.playAct.setChecked(False)

    def update_mute_status(self, is_muted):
        if is_muted:
            self.previous_volume = self.media_player.volume()
            self.change_volume_act.widget.setValue(0)
        else:
            self.change_volume_act.widget.setValue(self.previous_volume)
        self.media_player.setMuted(is_muted)

    def change_corpus(self):
        corpus_name = self.sender().text()
        with sqlalchemy.orm.Session(self.db_engine) as session:
            session.query(anchor.db.AnchorCorpus).update({anchor.db.AnchorCorpus.current: False})
            session.flush()
            m = (
                session.query(anchor.db.AnchorCorpus)
                .filter(anchor.db.AnchorCorpus.name == corpus_name)
                .first()
            )
            if m is None:
                corpus_directory = QtWidgets.QFileDialog.getExistingDirectory(
                    parent=self,
                    caption="Select a corpus directory",
                    dir=self.settings.value(AnchorSettings.DEFAULT_CORPUS_DIRECTORY),
                )
                if not corpus_directory or not os.path.exists(corpus_directory):
                    return
                corpus_name = os.path.basename(corpus_directory)
                self.settings.setValue(
                    AnchorSettings.DEFAULT_CORPUS_DIRECTORY, os.path.dirname(corpus_directory)
                )
                m = (
                    session.query(anchor.db.AnchorCorpus)
                    .filter(anchor.db.AnchorCorpus.name == corpus_name)
                    .first()
                )
                if m is None:
                    m = anchor.db.AnchorCorpus(
                        name=corpus_name, path=corpus_directory, current=True
                    )
                    session.add(m)
            m.current = True
            session.commit()
        self.refresh_corpus_history()
        self.load_corpus()
        self.deleted_utts = []

    def load_reference_alignments(self):
        reference_directory = QtWidgets.QFileDialog.getExistingDirectory(
            parent=self,
            caption="Select a reference directory",
            dir=self.settings.value(AnchorSettings.DEFAULT_CORPUS_DIRECTORY),
        )
        if not reference_directory or not os.path.exists(reference_directory):
            return
        with sqlalchemy.orm.Session(self.db_engine) as session:
            c = session.query(anchor.db.AnchorCorpus).filter_by(current=True).first()
            c.reference_directory = reference_directory
            session.commit()
        self.load_reference_worker.set_params(self.corpus_model.corpus, reference_directory)
        self.load_reference_worker.start()

    def close_corpus(self):
        self.set_application_state("unloaded")
        self.selection_model.clearSelection()
        if self.corpus_model.corpus is not None:
            self.corpus_model.session.close()
        self.corpus_model.setCorpus(None)
        self.settings.setValue(AnchorSettings.CURRENT_CORPUS, "")

    def load_corpus(self):
        self.selection_model.clearSelection()
        self.corpus_model.setCorpus(None)
        with sqlalchemy.orm.Session(self.db_engine) as session:
            c = (
                session.query(anchor.db.AnchorCorpus)
                .options(sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.dictionary))
                .filter_by(current=True)
                .first()
            )
            if c is None:
                self.set_application_state("unloaded")
                return
            self.set_application_state("loading")
            self.ui.loadingScreen.setCorpusName(f"Loading {c.path}...")
            dictionary_path = None
            if c.dictionary is not None:
                dictionary_path = c.dictionary.path
        self.corpus_worker.set_params(c.path, dictionary_path)
        self.corpus_worker.start()

    def reload_corpus(self):
        self.selection_model.clearSelection()
        with sqlalchemy.orm.Session(self.db_engine) as session:
            c = session.query(anchor.db.AnchorCorpus).filter_by(current=True).first()
            corpus_path = c.path
            dictionary_path = None
            if c.dictionary is not None:
                dictionary_path = c.dictionary.path

        self.corpus_worker.set_params(corpus_path, dictionary_path, reset=True)
        self.set_application_state("loading")
        self.ui.loadingScreen.setCorpusName(f"Reloading {c.path}...")
        self.corpus_worker.start()

    def cancel_corpus_load(self):
        self.ui.cancelCorpusLoadAct.setEnabled(False)
        self.ui.loadingScreen.text_label.setText("Cancelling...")
        self.corpus_worker.stop()

    def save_completed(self):
        self.set_application_state("loaded")
        self.check_actions()

    def fully_loaded(self):
        if self.corpus is not None:
            self.set_application_state("loaded")
        else:
            self.set_application_state("unloaded")
        self.check_actions()
        with self.corpus_model.corpus.session() as session:
            workflows = session.query(CorpusWorkflow).order_by(CorpusWorkflow.time_stamp).all()
            for w in workflows:
                if w.workflow_type is WorkflowType.alignment:
                    self.corpus_model.has_alignments = True
                elif w.workflow_type is WorkflowType.reference:
                    self.corpus_model.has_reference_alignments = True
                elif w.workflow_type is WorkflowType.transcription:
                    self.corpus_model.has_transcribed_alignments = True
                elif w.workflow_type is WorkflowType.per_speaker_transcription:
                    self.corpus_model.has_per_speaker_transcribed_alignments = True

    def finalize_load_corpus(self, corpus: AcousticCorpus):
        if corpus is None:
            self.set_application_state("unloaded")
        self.corpus = corpus
        self.corpus_model.setCorpus(corpus)
        if corpus is not None:
            plda_path = self.corpus_model.corpus.output_directory.joinpath(
                "speaker_diarization"
            ).joinpath("plda")
            if plda_path.exists():
                self.corpus_model.plda = read_kaldi_object(Plda, plda_path)
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
            with sqlalchemy.orm.Session(self.db_engine) as session:
                c = session.query(anchor.db.AnchorCorpus).filter_by(current=True).first()
                if c.custom_mapping_path:
                    self.dictionary_model.set_custom_mapping(c.custom_mapping_path)

    def finalize_reload_corpus(self):
        self.set_application_state("loaded")
        self.check_actions()

    def finalize_load_dictionary(self, corpus):
        self.set_application_state("loaded")
        self.corpus_model.setCorpus(corpus)
        self.corpus_model.dictionaryChanged.emit()
        self.check_actions()
        self.ui.loadDictionaryAct.setEnabled(True)

    def finalize_oov_count(self, corpus):
        self.set_application_state("loaded")
        self.corpus_model.setCorpus(corpus)
        self.corpus_model.dictionaryChanged.emit()
        self.dictionary_model.finish_refresh_word_counts()
        self.check_actions()
        self.ui.loadDictionaryAct.setEnabled(True)

    def finalize_load_acoustic_model(self, model: AcousticModel):
        self.acoustic_model = model
        self.corpus_model.set_acoustic_model(model)
        self.check_actions()
        self.ui.acousticModelMenu.setEnabled(True)

    def finalize_load_language_model(self, model: LanguageModel):
        self.language_model = model
        self.corpus_model.set_language_model(model)
        self.check_actions()
        self.ui.languageModelMenu.setEnabled(True)

    def finalize_load_g2p_model(self, generator: PyniniValidator):
        self.dictionary_model.set_g2p_generator(generator)
        self.corpus_model.g2p_model = generator.g2p_model
        self.check_actions()
        self.ui.g2pMenu.setEnabled(True)

    def finalize_load_ivector_extractor(self, model: IvectorExtractorModel):
        self.ivector_extractor = model
        self.corpus_model.set_ivector_extractor(model)
        self.check_actions()
        self.ui.ivectorExtractorMenu.setEnabled(True)

    def begin_alignment(self):
        self.enableMfaActions(False)
        self.alignment_worker.set_params(
            self.corpus_model.corpus, self.acoustic_model, self.ui.alignmentWidget.parameters()
        )
        self.alignment_worker.start()
        self.set_application_state("loading")
        self.ui.loadingScreen.setCorpusName("Performing alignment...")

    def begin_refresh_ivectors(self):
        self.enableMfaActions(False)
        self.compute_ivectors_worker.set_params(self.corpus_model, reset=False)
        self.compute_ivectors_worker.start()
        self.set_application_state("loading")
        self.ui.loadingScreen.setCorpusName("Calculating ivectors...")

    def begin_calculate_plda(self):
        self.enableMfaActions(False)
        self.compute_plda_worker.set_params(
            self.corpus_model.corpus, self.ivector_extractor, reset=False
        )
        self.compute_plda_worker.start()
        self.set_application_state("loading")
        self.ui.loadingScreen.setCorpusName("Calculating PLDA...")

    def begin_reset_ivectors(self):
        self.enableMfaActions(False)
        self.compute_ivectors_worker.set_params(self.corpus_model, reset=True)
        self.compute_ivectors_worker.start()
        self.set_application_state("loading")
        self.ui.loadingScreen.setCorpusName("Calculating ivectors...")

    def begin_cluster_utterances(self):
        self.enableMfaActions(False)
        self.cluster_utterances_worker.set_params(self.corpus_model.corpus, self.ivector_extractor)
        self.cluster_utterances_worker.start()
        self.set_application_state("loading")
        self.ui.loadingScreen.setCorpusName("Clustering speakers...")

    def begin_classify_speakers(self):
        self.enableMfaActions(False)
        self.classify_speakers_worker.set_params(self.corpus_model.corpus, self.ivector_extractor)
        self.classify_speakers_worker.start()
        self.set_application_state("loading")
        self.ui.loadingScreen.setCorpusName("Clustering speakers...")

    def begin_utterance_alignment(self):
        self.enableMfaActions(False)
        utterance = self.selection_model.currentUtterance()
        self.alignment_utterance_worker.set_params(
            self.corpus_model.corpus, self.acoustic_model, utterance.id
        )
        self.alignment_utterance_worker.start()
        self.set_application_state("loading")
        self.ui.loadingScreen.setCorpusName("Performing alignment...")

    def begin_utterance_segmentation(self):
        utterance = self.selection_model.currentUtterance()
        self.segment_utterance_worker.set_params(self.corpus_model, utterance.id)
        self.segment_utterance_worker.start()

    def begin_alignment_evaluation(self):
        self.enableMfaActions(False)
        with sqlalchemy.orm.Session(self.db_engine) as session:
            c = session.query(anchor.db.AnchorCorpus).filter_by(current=True).first()
            self.alignment_evaluation_worker.set_params(
                self.corpus_model.corpus, self.acoustic_model, c.custom_mapping_path
            )
        self.alignment_evaluation_worker.start()
        self.set_application_state("loading")
        self.ui.loadingScreen.setCorpusName("Performing alignment evaluation...")

    def begin_transcription(self):
        self.enableMfaActions(False)
        if self.corpus_model.language_model is not None:
            self.transcription_worker.set_params(
                self.corpus_model.corpus, self.acoustic_model, self.language_model
            )
            self.transcription_worker.start()
        else:
            self.validation_worker.set_params(
                self.corpus_model.corpus,
                self.acoustic_model,
                self.ui.transcriptionWidget.frequent_words_edit.value(),
                test_transcriptions=True,
            )
            self.validation_worker.start()
        self.set_application_state("loading")
        self.ui.loadingScreen.setCorpusName("Performing transcription...")

    def enableMfaActions(self, enabled):
        self.ui.alignCorpusAct.setEnabled(enabled)
        self.ui.transcribeCorpusAct.setEnabled(enabled)
        self.ui.evaluateAlignmentsAct.setEnabled(enabled)

    def finalize_adding_ivectors(self, speaker_space=None):
        self.speaker_model.speaker_space = speaker_space
        self.corpus_model.corpus.inspect_database()
        selection = self.selection_model.selection()
        self.selection_model.clearSelection()
        self.selection_model.select(
            selection,
            QtCore.QItemSelectionModel.SelectionFlag.SelectCurrent
            | QtCore.QItemSelectionModel.SelectionFlag.Rows,
        )
        self.corpus_model.update_data()
        self.check_actions()
        self.ui.diarizationWidget.refresh()
        self.set_application_state("loaded")

    def finalize_computing_plda(self, result=None):
        if result is None:
            self.corpus_model.plda = result
        else:
            self.corpus_model.plda = result[0]
            self.corpus_model.speaker_plda = result[1]
        self.corpus_model.corpus.inspect_database()
        selection = self.selection_model.selection()
        self.selection_model.clearSelection()
        self.selection_model.select(
            selection,
            QtCore.QItemSelectionModel.SelectionFlag.SelectCurrent
            | QtCore.QItemSelectionModel.SelectionFlag.Rows,
        )
        self.corpus_model.update_data()
        self.check_actions()
        self.ui.diarizationWidget.refresh()
        self.set_application_state("loaded")

    def finalize_clustering_utterances(self):
        self.corpus_model.corpus.inspect_database()
        self.corpus_model.corpus._num_speakers = None
        self.corpus_model.refresh_speakers()

        selection = self.selection_model.selection()
        self.selection_model.clearSelection()
        self.selection_model.select(
            selection,
            QtCore.QItemSelectionModel.SelectionFlag.SelectCurrent
            | QtCore.QItemSelectionModel.SelectionFlag.Rows,
        )
        self.corpus_model.update_data()
        self.check_actions()
        self.set_application_state("loaded")

    def finalize_adding_intervals(self):
        self.corpus_model.corpus.inspect_database()
        self.corpus_model.corpusLoaded.emit()
        selection = self.selection_model.selection()
        self.selection_model.clearSelection()
        self.selection_model.select(
            selection,
            QtCore.QItemSelectionModel.SelectionFlag.SelectCurrent
            | QtCore.QItemSelectionModel.SelectionFlag.Rows,
        )
        self.corpus_model.update_data()
        self.check_actions()
        self.set_application_state("loaded")

    def finalize_utterance_alignment(self, utterance_id: int):
        self.corpus_model.session.expire_all()
        self.corpus_model.update_data()
        self.check_actions()
        self.set_application_state("loaded")

    def finalize_segmentation(self, data):
        original_utterance_id, split_data = data
        self.corpus_model.split_vad_utterance(original_utterance_id, split_data)
        self.corpus_model.update_data()

    def finalize_saving(self):
        self.check_actions()

    def set_application_state(self, state, worker=None):
        self.selection_model.clearSelection()
        if state == "loading":
            self.ui.loadingScreen.set_worker(worker)
            self.ui.utteranceDockWidget.setVisible(False)
            self.ui.dictionaryDockWidget.setVisible(False)
            self.ui.oovDockWidget.setVisible(False)
            self.ui.speakerDockWidget.setVisible(False)
            self.ui.acousticModelDockWidget.setVisible(False)
            self.ui.transcriptionDockWidget.setVisible(False)
            self.ui.alignmentDockWidget.setVisible(False)
            self.ui.languageModelDockWidget.setVisible(False)
            self.ui.diarizationDockWidget.setVisible(False)
            self.ui.toolBar.setVisible(False)

            self.ui.utteranceDetailWidget.setVisible(False)
            self.ui.titleScreen.setVisible(False)
            self.ui.loadingScreen.setVisible(True)

            self.ui.changeTemporaryDirectoryAct.setEnabled(False)
            self.ui.openPreferencesAct.setEnabled(True)
            self.ui.cancelCorpusLoadAct.setEnabled(True)
            self.ui.loadCorpusAct.setEnabled(False)
            self.ui.loadRecentCorpusMenu.setEnabled(False)
            self.ui.closeCurrentCorpusAct.setEnabled(False)
            self.ui.acousticModelMenu.setEnabled(False)
            self.ui.languageModelMenu.setEnabled(False)
            self.ui.ivectorExtractorMenu.setEnabled(False)
            self.ui.g2pMenu.setEnabled(False)
            self.ui.loadAcousticModelAct.setEnabled(False)
            self.ui.loadDictionaryAct.setEnabled(False)
            self.ui.loadG2PModelAct.setEnabled(False)
            self.ui.loadLanguageModelAct.setEnabled(False)
            self.ui.loadIvectorExtractorAct.setEnabled(False)
        elif state == "loaded":
            self.ui.loadingScreen.set_worker(None)
            self.ui.loadingScreen.setVisible(False)
            self.ui.titleScreen.setVisible(False)

            self.ui.utteranceDockWidget.setVisible(
                self.settings.value(AnchorSettings.UTTERANCES_VISIBLE)
            )
            self.ui.dictionaryDockWidget.setVisible(
                self.settings.value(AnchorSettings.DICTIONARY_VISIBLE)
            )
            self.ui.oovDockWidget.setVisible(self.settings.value(AnchorSettings.OOV_VISIBLE))
            self.ui.speakerDockWidget.setVisible(
                self.settings.value(AnchorSettings.SPEAKERS_VISIBLE)
            )
            self.ui.languageModelDockWidget.setVisible(
                self.settings.value(AnchorSettings.LM_VISIBLE)
            )
            self.ui.acousticModelDockWidget.setVisible(
                self.settings.value(AnchorSettings.AM_VISIBLE)
            )
            self.ui.transcriptionDockWidget.setVisible(
                self.settings.value(AnchorSettings.TRANSCRIPTION_VISIBLE)
            )
            self.ui.alignmentDockWidget.setVisible(
                self.settings.value(AnchorSettings.ALIGNMENT_VISIBLE)
            )
            self.ui.diarizationDockWidget.setVisible(
                self.settings.value(AnchorSettings.DIARIZATION_VISIBLE)
            )
            self.ui.toolBar.setVisible(True)

            self.ui.utteranceDetailWidget.setVisible(True)

            self.ui.changeTemporaryDirectoryAct.setEnabled(True)
            self.ui.openPreferencesAct.setEnabled(True)
            self.ui.cancelCorpusLoadAct.setEnabled(False)
            self.ui.loadCorpusAct.setEnabled(True)
            self.ui.loadRecentCorpusMenu.setEnabled(True)
            self.ui.closeCurrentCorpusAct.setEnabled(True)
            self.ui.loadAcousticModelAct.setEnabled(True)
            self.ui.loadDictionaryAct.setEnabled(True)
            self.ui.loadDictionaryAct.setEnabled(True)
            self.ui.loadG2PModelAct.setEnabled(True)
            self.ui.loadLanguageModelAct.setEnabled(True)
            self.ui.loadIvectorExtractorAct.setEnabled(True)
            self.ui.acousticModelMenu.setEnabled(True)
            self.ui.languageModelMenu.setEnabled(True)
            self.ui.ivectorExtractorMenu.setEnabled(True)
            self.ui.g2pMenu.setEnabled(True)
        elif state == "unloaded":
            self.ui.loadingScreen.setVisible(False)
            self.ui.titleScreen.setVisible(True)
            self.ui.toolBar.setVisible(False)

            self.ui.utteranceDockWidget.setVisible(False)
            self.ui.dictionaryDockWidget.setVisible(False)
            self.ui.oovDockWidget.setVisible(False)
            self.ui.acousticModelDockWidget.setVisible(False)
            self.ui.transcriptionDockWidget.setVisible(False)
            self.ui.alignmentDockWidget.setVisible(False)
            self.ui.languageModelDockWidget.setVisible(False)
            self.ui.speakerDockWidget.setVisible(False)
            self.ui.utteranceDetailWidget.setVisible(False)
            self.ui.diarizationDockWidget.setVisible(False)

            self.ui.changeTemporaryDirectoryAct.setEnabled(True)
            self.ui.openPreferencesAct.setEnabled(True)
            self.ui.cancelCorpusLoadAct.setEnabled(False)
            self.ui.loadCorpusAct.setEnabled(True)
            self.ui.loadRecentCorpusMenu.setEnabled(True)
            self.ui.closeCurrentCorpusAct.setEnabled(False)
            self.ui.loadAcousticModelAct.setEnabled(True)
            self.ui.loadDictionaryAct.setEnabled(True)
            self.ui.loadG2PModelAct.setEnabled(True)
            self.ui.loadLanguageModelAct.setEnabled(True)
            self.ui.loadIvectorExtractorAct.setEnabled(True)
            self.ui.acousticModelMenu.setEnabled(True)
            self.ui.languageModelMenu.setEnabled(True)
            self.ui.ivectorExtractorMenu.setEnabled(True)
            self.ui.g2pMenu.setEnabled(True)
            self.ui.loadingScreen.set_worker(None)

    def enable_zoom(self):
        if (
            self.selection_model.selected_min_time is None
            or self.selection_model.selected_max_time is None
            or not self.selection_model.hasSelection()
        ):
            self.ui.zoomToSelectionAct.setEnabled(False)
        else:
            self.ui.zoomToSelectionAct.setEnabled(True)

    def play_audio(self):
        if self.media_player.playbackState() in [
            QtMultimedia.QMediaPlayer.PlaybackState.StoppedState,
            QtMultimedia.QMediaPlayer.PlaybackState.PausedState,
        ]:
            self.media_player.play()
        elif (
            self.media_player.playbackState()
            == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState
        ):
            self.media_player.pause()

    def report_bug(self):
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl("https://github.com/MontrealCorpusTools/Anchor-annotator/issues")
        )

    def open_help(self):
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl("https://anchor-annotator.readthedocs.io/en/latest/")
        )

    def add_new_speaker(self):
        new_speaker = self.ui.speakerWidget.newSpeakerEdit.text()
        if new_speaker in self.corpus.speak_utt_mapping:
            return
        if not new_speaker:
            return
        self.newSpeaker.emit(self.corpus.speakers)
        self.ui.speakerWidget.newSpeakerEdit.clear()

    def open_search(self, search_term=None):
        dock_tab_bars = self.findChildren(QtWidgets.QTabBar, "")

        for j in range(len(dock_tab_bars)):
            dock_tab_bar = dock_tab_bars[j]
            if not dock_tab_bar.count():
                continue
            for i in range(dock_tab_bar.count()):
                if dock_tab_bar.tabText(i) == "Utterances":
                    dock_tab_bar.setCurrentIndex(i)
                    break
            else:
                self.ui.utteranceDockWidget.toggleViewAction().trigger()
            self.ui.utteranceListWidget.search_box.setFocus()
            if search_term is not None:
                self.ui.utteranceListWidget.search_box.setQuery(search_term)

    def open_search_speaker(self, search_term=None, show=False):
        if search_term is not None:
            self.ui.utteranceListWidget.speaker_dropdown.line_edit.setText(search_term)
            self.ui.utteranceListWidget.file_dropdown.line_edit.setText("")
            self.ui.utteranceListWidget.search_box.setText("")
            if self.corpus_model.corpus.has_any_ivectors():
                self.ui.utteranceListWidget.table_widget.horizontalHeader().setSortIndicator(
                    self.corpus_model.ivector_distance_column, QtCore.Qt.SortOrder.AscendingOrder
                )
            self.ui.utteranceListWidget.search()
            if show:
                dock_tab_bars = self.findChildren(QtWidgets.QTabBar, "")

                for j in range(len(dock_tab_bars)):
                    dock_tab_bar = dock_tab_bars[j]
                    if not dock_tab_bar.count():
                        continue
                    for i in range(dock_tab_bar.count()):
                        if dock_tab_bar.tabText(i) == "Utterances":
                            dock_tab_bar.setCurrentIndex(i)
                            break
                    else:
                        self.ui.utteranceDockWidget.toggleViewAction().trigger()

    def open_search_file(self, search_term=None, utterance_id=None, show=False):
        if search_term is not None:
            self.ui.utteranceListWidget.file_dropdown.line_edit.setText(search_term)
            self.ui.utteranceListWidget.speaker_dropdown.line_edit.setText("")
            self.ui.utteranceListWidget.search_box.setText("")
            self.ui.utteranceListWidget.table_widget.horizontalHeader().setSortIndicator(
                self.corpus_model.begin_column, QtCore.Qt.SortOrder.AscendingOrder
            )
            self.ui.utteranceListWidget.requested_utterance_id = utterance_id
            self.ui.utteranceListWidget.search()
            if show:
                dock_tab_bars = self.findChildren(QtWidgets.QTabBar, "")

                for j in range(len(dock_tab_bars)):
                    dock_tab_bar = dock_tab_bars[j]
                    if not dock_tab_bar.count():
                        continue
                    for i in range(dock_tab_bar.count()):
                        if dock_tab_bar.tabText(i) == "Utterances":
                            dock_tab_bar.setCurrentIndex(i)
                            break
                    else:
                        self.ui.utteranceDockWidget.toggleViewAction().trigger()

    def refresh_shortcuts(self):
        self.ui.playAct.setShortcut(self.settings.value(AnchorSettings.PLAY_KEYBIND))
        self.ui.zoomInAct.setShortcut(self.settings.value(AnchorSettings.ZOOM_IN_KEYBIND))
        self.ui.zoomOutAct.setShortcut(self.settings.value(AnchorSettings.ZOOM_OUT_KEYBIND))
        self.ui.zoomToSelectionAct.setShortcut(
            self.settings.value(AnchorSettings.ZOOM_TO_SELECTION_KEYBIND)
        )
        self.ui.panLeftAct.setShortcut(self.settings.value(AnchorSettings.PAN_LEFT_KEYBIND))
        self.ui.panRightAct.setShortcut(self.settings.value(AnchorSettings.PAN_RIGHT_KEYBIND))
        self.ui.mergeUtterancesAct.setShortcut(self.settings.value(AnchorSettings.MERGE_KEYBIND))
        self.ui.splitUtterancesAct.setShortcut(self.settings.value(AnchorSettings.SPLIT_KEYBIND))
        self.ui.deleteUtterancesAct.setShortcut(self.settings.value(AnchorSettings.DELETE_KEYBIND))
        self.ui.saveChangesAct.setShortcut(self.settings.value(AnchorSettings.SAVE_KEYBIND))
        self.ui.searchAct.setShortcut(self.settings.value(AnchorSettings.SEARCH_KEYBIND))
        self.undo_act.setShortcut(self.settings.value(AnchorSettings.UNDO_KEYBIND))
        self.redo_act.setShortcut(self.settings.value(AnchorSettings.REDO_KEYBIND))
        # self.ui.changeVolumeAct.widget.setValue(self.config['volume'])

    def open_dictionary(self):
        dock_tab_bars = self.findChildren(QtWidgets.QTabBar, "")

        for j in range(len(dock_tab_bars)):
            dock_tab_bar = dock_tab_bars[j]
            if not dock_tab_bar.count():
                continue
            for i in range(dock_tab_bar.count()):
                if dock_tab_bar.tabText(i) == "Dictionary":
                    dock_tab_bar.setCurrentIndex(i)
                    break
            else:
                self.ui.dictionaryDockWidget.toggleViewAction().trigger()

    def change_temp_dir(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            parent=self, caption="Select a temporary directory", dir=self.settings.temp_directory
        )
        if not directory or not os.path.exists(directory):
            return
        config = MfaConfiguration()
        config.profiles["anchor"].temporary_directory = directory
        config.save()

    def open_options(self):
        dialog = OptionsDialog(self)
        if dialog.exec_():
            self.settings.sync()
            self.refresh_settings()

    def refresh_style_sheets(self):
        self.setStyleSheet(self.settings.style_sheet)

    def refresh_corpus_history(self):
        self.ui.loadRecentCorpusMenu.clear()
        with sqlalchemy.orm.Session(self.db_engine) as session:
            corpora = session.query(anchor.db.AnchorCorpus).filter_by(current=False)
            for c in corpora:
                a = QtGui.QAction(c.name, parent=self)
                a.triggered.connect(self.change_corpus)
                self.ui.loadRecentCorpusMenu.addAction(a)

    def refresh_settings(self):
        self.refresh_fonts()
        self.refresh_shortcuts()
        self.refresh_style_sheets()
        self.corpus_model.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))
        self.dictionary_model.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))
        self.speaker_model.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))
        self.diarization_model.set_limit(self.settings.value(self.settings.RESULTS_PER_PAGE))
        self.ui.utteranceListWidget.refresh_settings()
        self.ui.dictionaryWidget.refresh_settings()
        self.ui.speakerWidget.refresh_settings()
        self.ui.loadingScreen.refresh_settings()
        self.media_player.refresh_settings()

    def refresh_fonts(self):
        base_font = self.settings.font
        self.menuBar().setFont(base_font)
        self.ui.utteranceDockWidget.setFont(base_font)
        self.ui.speakerDockWidget.setFont(base_font)
        self.ui.dictionaryDockWidget.setFont(base_font)
        self.ui.oovDockWidget.setFont(base_font)
        self.ui.diarizationDockWidget.setFont(base_font)

    def download_language_model(self):
        self.download_worker.set_params(
            self.db_string, "language_model", self.sender().text(), self.model_manager
        )
        self.download_worker.start()

    def download_g2p_model(self):
        self.download_worker.set_params(
            self.db_string, "g2p", self.sender().text(), self.model_manager
        )
        self.download_worker.start()

    def download_acoustic_model(self):
        self.download_worker.set_params(
            self.db_string, "acoustic", self.sender().text(), self.model_manager
        )
        self.download_worker.start()

    def download_dictionary(self):
        self.download_worker.set_params(
            self.db_string, "dictionary", self.sender().text(), self.model_manager
        )
        self.download_worker.start()

    def download_ivector_extractor(self):
        self.download_worker.set_params(
            self.db_string, "ivector", self.sender().text(), self.model_manager
        )
        self.download_worker.start()

    def load_acoustic_model(self):
        with sqlalchemy.orm.Session(self.db_engine) as session:
            c = (
                session.query(anchor.db.AnchorCorpus)
                .options(sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.acoustic_model))
                .filter_by(current=True)
                .first()
            )
            if c is None or c.acoustic_model is None:
                return
            self.acoustic_model_worker.set_params(c.acoustic_model.path)
        self.acoustic_model_worker.start()

    def change_acoustic_model(self):
        m_id = self.sender().data()
        if m_id:
            with sqlalchemy.orm.Session(self.db_engine) as session:
                m = session.get(anchor.db.AcousticModel, m_id)
                am_path = m.path

                session.query(anchor.db.AnchorCorpus).filter_by(current=True).update(
                    {anchor.db.AnchorCorpus.acoustic_model_id: m_id}
                )
                session.commit()
        else:
            am_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                parent=self,
                caption="Select an acoustic model",
                dir=self.settings.value(AnchorSettings.DEFAULT_ACOUSTIC_DIRECTORY),
                filter="Model files (*.zip)",
            )
            self.settings.setValue(
                AnchorSettings.DEFAULT_ACOUSTIC_DIRECTORY, os.path.dirname(am_path)
            )
            if not am_path or not os.path.exists(am_path):
                return
            with sqlalchemy.orm.Session(self.db_engine) as session:
                c = (
                    session.query(anchor.db.AnchorCorpus)
                    .options(sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.acoustic_model))
                    .filter_by(current=True)
                    .first()
                )
                m = session.query(anchor.db.AcousticModel).filter_by(path=am_path).first()
                if not m:
                    m_name = os.path.splitext(os.path.basename(am_path))[0]
                    m = anchor.db.AcousticModel(name=m_name, path=am_path, available_locally=True)
                    session.add(m)
                c.acoustic_model = m
                session.commit()

        self.acoustic_model_worker.set_params(am_path)
        self.acoustic_model_worker.start()

    def change_custom_mapping(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            parent=self,
            caption="Select a mapping file",
            dir=self.settings.value(AnchorSettings.DEFAULT_DIRECTORY),
            filter="Configuration files (*.yaml)",
        )

        if not path or not os.path.exists(path):
            return
        with sqlalchemy.orm.Session(self.db_engine) as session:
            c = (
                session.query(anchor.db.AnchorCorpus)
                .options(sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.dictionary))
                .filter_by(current=True)
                .first()
            )
            c.custom_mapping_path = path
        self.settings.setValue(AnchorSettings.DEFAULT_DIRECTORY, os.path.dirname(path))
        self.settings.sync()
        self.dictionary_model.set_custom_mapping(path)

    def change_dictionary(self):
        m_id = self.sender().data()
        if m_id:
            with sqlalchemy.orm.Session(self.db_engine) as session:
                m = session.get(anchor.db.Dictionary, m_id)
                dictionary_path = m.path

                session.query(anchor.db.AnchorCorpus).filter_by(current=True).update(
                    {anchor.db.AnchorCorpus.dictionary_id: m_id}
                )
                session.commit()
        else:
            dictionary_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                parent=self,
                caption="Select a dictionary",
                dir=self.settings.value(AnchorSettings.DEFAULT_DICTIONARY_DIRECTORY),
                filter="Dictionary files (*.dict *.txt *.yaml)",
            )
            if not dictionary_path or not os.path.exists(dictionary_path):
                return
            self.settings.setValue(
                AnchorSettings.DEFAULT_DICTIONARY_DIRECTORY, os.path.dirname(dictionary_path)
            )
            with sqlalchemy.orm.Session(self.db_engine) as session:
                c = (
                    session.query(anchor.db.AnchorCorpus)
                    .options(sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.dictionary))
                    .filter_by(current=True)
                    .first()
                )
                d = session.query(anchor.db.Dictionary).filter_by(path=dictionary_path).first()
                if not d:
                    d_name = os.path.splitext(os.path.basename(dictionary_path))[0]
                    d = anchor.db.Dictionary(
                        name=d_name, path=dictionary_path, available_locally=True
                    )
                    session.add(d)
                c.dictionary = d
                session.commit()
        self.set_application_state("loading")
        self.ui.loadingScreen.setCorpusName(f"Loading {dictionary_path}...")
        self.dictionary_worker.set_params(self.corpus_model.corpus, dictionary_path)
        self.dictionary_worker.start()

    def calculate_oovs(self):
        self.set_application_state("loading")
        self.ui.loadingScreen.setCorpusName("Calculating OOV counts...")
        self.oov_worker.set_params(self.corpus_model.corpus)
        self.oov_worker.start()

    def change_language_model(self):
        m_id = self.sender().data()
        if m_id:
            with sqlalchemy.orm.Session(self.db_engine) as session:
                m = session.get(anchor.db.LanguageModel, m_id)
                path = m.path

                session.query(anchor.db.AnchorCorpus).filter_by(current=True).update(
                    {anchor.db.AnchorCorpus.language_model_id: m_id}
                )
                session.commit()
        else:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                parent=self,
                caption="Select a language model",
                dir=self.settings.value(AnchorSettings.DEFAULT_LM_DIRECTORY),
                filter="Model files (*.zip)",
            )
            if not path or not os.path.exists(path):
                return
            self.settings.setValue(AnchorSettings.DEFAULT_LM_DIRECTORY, os.path.dirname(path))
            with sqlalchemy.orm.Session(self.db_engine) as session:
                c = (
                    session.query(anchor.db.AnchorCorpus)
                    .options(sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.language_model))
                    .filter_by(current=True)
                    .first()
                )
                m = session.query(anchor.db.LanguageModel).filter_by(path=path).first()
                if not m:
                    m_name = os.path.splitext(os.path.basename(path))[0]
                    m = anchor.db.LanguageModel(name=m_name, path=path, available_locally=True)
                    session.add(m)
                c.language_model = m
                session.commit()
        self.language_model_worker.set_params(path)
        self.language_model_worker.start()

    def load_language_model(self):
        with sqlalchemy.orm.Session(self.db_engine) as session:
            c = (
                session.query(anchor.db.AnchorCorpus)
                .options(sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.language_model))
                .filter_by(current=True)
                .first()
            )
            if c is None or c.language_model is None:
                return
            self.language_model_worker.set_params(c.language_model.path)
        self.language_model_worker.start()
        self.settings.setValue(
            AnchorSettings.DEFAULT_LM_DIRECTORY, os.path.dirname(c.language_model.path)
        )

    def load_g2p(self):
        with sqlalchemy.orm.Session(self.db_engine) as session:
            c = (
                session.query(anchor.db.AnchorCorpus)
                .options(sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.g2p_model))
                .filter_by(current=True)
                .first()
            )
            if c is None or c.g2p_model is None:
                return
            self.g2p_model_worker.set_params(c.g2p_model.path)
            print(c.g2p_model.path)
        self.g2p_model_worker.start()
        self.settings.setValue(
            AnchorSettings.DEFAULT_G2P_DIRECTORY, os.path.dirname(c.g2p_model.path)
        )

    def change_g2p(self):
        m_id = self.sender().data()
        if m_id:
            with sqlalchemy.orm.Session(self.db_engine) as session:
                m = session.get(anchor.db.G2PModel, m_id)
                g2p_path = m.path

                session.query(anchor.db.AnchorCorpus).filter_by(current=True).update(
                    {anchor.db.AnchorCorpus.g2p_model_id: m_id}
                )
                session.commit()
        else:
            g2p_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                parent=self,
                caption="Select a g2p model",
                dir=self.settings.value(AnchorSettings.DEFAULT_G2P_DIRECTORY),
                filter="Model files (*.zip)",
            )
            if not g2p_path or not os.path.exists(g2p_path):
                return
            self.settings.setValue(AnchorSettings.DEFAULT_G2P_DIRECTORY, os.path.dirname(g2p_path))
            with sqlalchemy.orm.Session(self.db_engine) as session:
                c = (
                    session.query(anchor.db.AnchorCorpus)
                    .options(sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.g2p_model))
                    .filter_by(current=True)
                    .first()
                )
                m = session.query(anchor.db.G2PModel).filter_by(path=g2p_path).first()
                if not m:
                    m_name = os.path.splitext(os.path.basename(g2p_path))[0]
                    m = anchor.db.G2PModel(name=m_name, path=g2p_path, available_locally=True)
                    session.add(m)
                c.g2p_model = m
                session.commit()
        self.g2p_model_worker.set_params(g2p_path)
        self.g2p_model_worker.start()

    def change_ivector_extractor(self):
        m_id = self.sender().data()
        if m_id:
            with sqlalchemy.orm.Session(self.db_engine) as session:
                m = session.get(anchor.db.IvectorExtractor, m_id)
                ie_path = m.path

                session.query(anchor.db.AnchorCorpus).filter_by(current=True).update(
                    {anchor.db.AnchorCorpus.ivector_extractor_id: m_id}
                )
                session.commit()
        else:
            ie_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                caption="Select a ivector extractor model",
                dir=self.settings.value(self.settings.DEFAULT_IVECTOR_DIRECTORY),
                filter="Ivector extractors (*.ivector *.zip)",
                parent=self,
            )

            if not ie_path or not os.path.exists(ie_path):
                return
            self.settings.setValue(
                AnchorSettings.DEFAULT_IVECTOR_DIRECTORY, os.path.dirname(ie_path)
            )
            with sqlalchemy.orm.Session(self.db_engine) as session:
                c = (
                    session.query(anchor.db.AnchorCorpus)
                    .options(sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.ivector_extractor))
                    .filter_by(current=True)
                    .first()
                )
                m = session.query(anchor.db.IvectorExtractor).filter_by(path=ie_path).first()
                if not m:
                    m_name = os.path.splitext(os.path.basename(ie_path))[0]
                    m = anchor.db.IvectorExtractor(
                        name=m_name, path=ie_path, available_locally=True
                    )
                    session.add(m)
                c.ivector_extractor = m
                session.commit()
        self.ivector_extractor_worker.set_params(ie_path)
        self.ivector_extractor_worker.start()

    def load_ivector_extractor(self):
        with sqlalchemy.orm.Session(self.db_engine) as session:
            c = (
                session.query(anchor.db.AnchorCorpus)
                .options(sqlalchemy.orm.joinedload(anchor.db.AnchorCorpus.ivector_extractor))
                .filter_by(current=True)
                .first()
            )
            if c is None or c.ivector_extractor is None:
                return
            self.ivector_extractor_worker.set_params(c.ivector_extractor.path)
        self.ivector_extractor_worker.start()
        self.settings.setValue(
            AnchorSettings.DEFAULT_IVECTOR_DIRECTORY, os.path.dirname(c.ivector_extractor.path)
        )

    def export_files(self):
        if not self.corpus_model.corpus:
            return
        try:
            self.corpus_model.export_changes()
        except Exception:
            exctype, value = sys.exc_info()[:2]
            self.handle_error((exctype, value, traceback.format_exc()))

    def handle_error(self, trace_args):
        exctype, value, trace = trace_args
        reply = DetailedMessageBox(detailed_message=trace)
        reply.reportBug.connect(self.ui.reportBugAct.trigger)
        _ = reply.exec_()
        self.check_actions()
        if self.corpus_model.corpus is not None:
            self.set_application_state("loaded")

    def save_dictionary(self):
        self.ui.saveDictionaryAct.setEnabled(False)
        self.execute_runnable(
            "Exporting dictionary",
            self.save_completed,
            [{"dictionary_id": self.dictionary_model.current_dictionary_id}],
        )


class FormLayout(QtWidgets.QVBoxLayout):
    def addRow(self, label, widget):
        row_layout = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(label)
        label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding
        )
        row_layout.addWidget(label)
        row_layout.addWidget(widget)
        super(FormLayout, self).addLayout(row_layout)


class DetailedMessageBox(QtWidgets.QDialog):  # pragma: no cover
    reportBug = QtCore.Signal()

    def __init__(self, detailed_message, *args, **kwargs):
        super(DetailedMessageBox, self).__init__(*args, **kwargs)
        self.ui = Ui_ErrorDialog()
        self.ui.setupUi(self)
        self.settings = AnchorSettings()
        self.ui.detailed_message.setText(detailed_message)
        self.setStyleSheet(self.settings.style_sheet)
        self.ui.buttonBox.report_bug_button.clicked.connect(self.reportBug.emit)
        self.ui.buttonBox.rejected.connect(self.reject)
        self.ui.label.setFont(self.settings.font)
        self.ui.label_2.setFont(self.settings.font)
        self.ui.detailed_message.setFont(self.settings.font)


class OptionsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(OptionsDialog, self).__init__(parent=parent)
        self.ui = Ui_PreferencesDialog()
        self.ui.setupUi(self)
        self.settings = AnchorSettings()

        self.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)

        self.ui.primaryBaseEdit.set_color(self.settings.value(self.settings.PRIMARY_BASE_COLOR))
        self.ui.primaryLightEdit.set_color(self.settings.value(self.settings.PRIMARY_LIGHT_COLOR))
        self.ui.primaryDarkEdit.set_color(self.settings.value(self.settings.PRIMARY_DARK_COLOR))
        self.ui.primaryVeryLightEdit.set_color(
            self.settings.value(self.settings.PRIMARY_VERY_LIGHT_COLOR)
        )
        self.ui.primaryVeryDarkEdit.set_color(
            self.settings.value(self.settings.PRIMARY_VERY_DARK_COLOR)
        )

        self.ui.accentBaseEdit.set_color(self.settings.value(self.settings.ACCENT_BASE_COLOR))
        self.ui.accentLightEdit.set_color(self.settings.value(self.settings.ACCENT_LIGHT_COLOR))
        self.ui.accentDarkEdit.set_color(self.settings.value(self.settings.ACCENT_DARK_COLOR))
        self.ui.accentVeryLightEdit.set_color(
            self.settings.value(self.settings.ACCENT_VERY_LIGHT_COLOR)
        )
        self.ui.accentVeryDarkEdit.set_color(
            self.settings.value(self.settings.ACCENT_VERY_DARK_COLOR)
        )

        self.ui.mainTextColorEdit.set_color(self.settings.value(self.settings.MAIN_TEXT_COLOR))
        self.ui.selectedTextColorEdit.set_color(
            self.settings.value(self.settings.SELECTED_TEXT_COLOR)
        )
        self.ui.errorColorEdit.set_color(self.settings.value(self.settings.ERROR_COLOR))

        self.ui.fontEdit.set_font(self.settings.font)

        self.ui.playAudioShortcutEdit.setKeySequence(
            self.settings.value(self.settings.PLAY_KEYBIND)
        )
        self.ui.zoomInShortcutEdit.setKeySequence(
            self.settings.value(self.settings.ZOOM_IN_KEYBIND)
        )
        self.ui.zoomToSelectionShortcutEdit.setKeySequence(
            self.settings.value(self.settings.ZOOM_TO_SELECTION_KEYBIND)
        )
        self.ui.zoomOutShortcutEdit.setKeySequence(
            self.settings.value(self.settings.ZOOM_OUT_KEYBIND)
        )
        self.ui.panLeftShortcutEdit.setKeySequence(
            self.settings.value(self.settings.PAN_LEFT_KEYBIND)
        )
        self.ui.panRightShortcutEdit.setKeySequence(
            self.settings.value(self.settings.PAN_RIGHT_KEYBIND)
        )
        self.ui.mergeShortcutEdit.setKeySequence(self.settings.value(self.settings.MERGE_KEYBIND))
        self.ui.splitShortcutEdit.setKeySequence(self.settings.value(self.settings.SPLIT_KEYBIND))
        self.ui.deleteShortcutEdit.setKeySequence(
            self.settings.value(self.settings.DELETE_KEYBIND)
        )
        self.ui.saveShortcutEdit.setKeySequence(self.settings.value(self.settings.SAVE_KEYBIND))
        self.ui.searchShortcutEdit.setKeySequence(
            self.settings.value(self.settings.SEARCH_KEYBIND)
        )
        self.ui.undoShortcutEdit.setKeySequence(self.settings.value(self.settings.UNDO_KEYBIND))
        self.ui.redoShortcutEdit.setKeySequence(self.settings.value(self.settings.REDO_KEYBIND))

        self.ui.autosaveOnExitCheckBox.setChecked(self.settings.value(self.settings.AUTOSAVE))
        self.ui.cudaCheckBox.setChecked(self.settings.value(self.settings.CUDA))
        self.ui.autoloadLastUsedCorpusCheckBox.setChecked(
            self.settings.value(self.settings.AUTOLOAD)
        )

        self.ui.audioDeviceEdit.clear()
        for o in QtMultimedia.QMediaDevices.audioOutputs():
            self.ui.audioDeviceEdit.addItem(o.description(), userData=o.id())
        self.ui.numJobsEdit.setValue(config.NUM_JOBS)
        try:
            self.ui.useMpCheckBox.setChecked(bool(config.USE_MP))
        except TypeError:
            self.ui.useMpCheckBox.setChecked(True)
        self.setWindowTitle("Preferences")

    def accept(self) -> None:
        config.NUM_JOBS = self.ui.numJobsEdit.value()
        config.USE_MP = self.ui.useMpCheckBox.isChecked()
        config.GLOBAL_CONFIG.current_profile.num_jobs = config.NUM_JOBS
        config.GLOBAL_CONFIG.current_profile.use_mp = config.USE_MP
        config.GLOBAL_CONFIG.save()
        self.settings.setValue(self.settings.PRIMARY_BASE_COLOR, self.ui.primaryBaseEdit.color)
        self.settings.setValue(self.settings.PRIMARY_LIGHT_COLOR, self.ui.primaryLightEdit.color)
        self.settings.setValue(self.settings.PRIMARY_DARK_COLOR, self.ui.primaryDarkEdit.color)
        self.settings.setValue(
            self.settings.PRIMARY_VERY_LIGHT_COLOR, self.ui.primaryVeryLightEdit.color
        )
        self.settings.setValue(
            self.settings.PRIMARY_VERY_DARK_COLOR, self.ui.primaryVeryDarkEdit.color
        )

        self.settings.setValue(self.settings.ACCENT_BASE_COLOR, self.ui.accentBaseEdit.color)
        self.settings.setValue(self.settings.ACCENT_LIGHT_COLOR, self.ui.accentLightEdit.color)
        self.settings.setValue(self.settings.ACCENT_DARK_COLOR, self.ui.accentDarkEdit.color)
        self.settings.setValue(
            self.settings.ACCENT_VERY_LIGHT_COLOR, self.ui.accentVeryLightEdit.color
        )
        self.settings.setValue(
            self.settings.ACCENT_VERY_DARK_COLOR, self.ui.accentVeryDarkEdit.color
        )

        self.settings.setValue(self.settings.MAIN_TEXT_COLOR, self.ui.mainTextColorEdit.color)
        self.settings.setValue(
            self.settings.SELECTED_TEXT_COLOR, self.ui.selectedTextColorEdit.color
        )
        self.settings.setValue(self.settings.ERROR_COLOR, self.ui.errorColorEdit.color)

        self.settings.setValue(self.settings.FONT, self.ui.fontEdit.font.toString())

        self.settings.setValue(
            self.settings.PLAY_KEYBIND, self.ui.playAudioShortcutEdit.keySequence().toString()
        )
        self.settings.setValue(
            self.settings.ZOOM_IN_KEYBIND, self.ui.zoomInShortcutEdit.keySequence().toString()
        )
        self.settings.setValue(
            self.settings.ZOOM_OUT_KEYBIND, self.ui.zoomOutShortcutEdit.keySequence().toString()
        )
        self.settings.setValue(
            self.settings.ZOOM_TO_SELECTION_KEYBIND,
            self.ui.zoomToSelectionShortcutEdit.keySequence().toString(),
        )
        self.settings.setValue(
            self.settings.PAN_LEFT_KEYBIND, self.ui.panLeftShortcutEdit.keySequence().toString()
        )
        self.settings.setValue(
            self.settings.PAN_RIGHT_KEYBIND, self.ui.panRightShortcutEdit.keySequence().toString()
        )
        self.settings.setValue(
            self.settings.MERGE_KEYBIND, self.ui.mergeShortcutEdit.keySequence().toString()
        )
        self.settings.setValue(
            self.settings.SPLIT_KEYBIND, self.ui.splitShortcutEdit.keySequence().toString()
        )
        self.settings.setValue(
            self.settings.DELETE_KEYBIND, self.ui.deleteShortcutEdit.keySequence().toString()
        )
        self.settings.setValue(
            self.settings.SAVE_KEYBIND, self.ui.saveShortcutEdit.keySequence().toString()
        )
        self.settings.setValue(
            self.settings.SEARCH_KEYBIND, self.ui.searchShortcutEdit.keySequence().toString()
        )
        self.settings.setValue(
            self.settings.UNDO_KEYBIND, self.ui.undoShortcutEdit.keySequence().toString()
        )
        self.settings.setValue(
            self.settings.REDO_KEYBIND, self.ui.redoShortcutEdit.keySequence().toString()
        )

        self.settings.setValue(
            self.settings.AUTOLOAD, self.ui.autoloadLastUsedCorpusCheckBox.isChecked()
        )
        self.settings.setValue(self.settings.CUDA, self.ui.cudaCheckBox.isChecked())
        self.settings.setValue(self.settings.AUTOSAVE, self.ui.autosaveOnExitCheckBox.isChecked())
        self.settings.setValue(self.settings.AUDIO_DEVICE, self.ui.audioDeviceEdit.currentData())
        self.settings.sync()
        super(OptionsDialog, self).accept()


class Application(QtWidgets.QApplication):
    pass
