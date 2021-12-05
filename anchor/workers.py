import os
import time
from PySide6 import QtCore

from montreal_forced_aligner.corpus.acoustic_corpus import AcousticCorpus

class FunctionWorker(QtCore.QThread):  # pragma: no cover
    updateProgress = QtCore.Signal(object)
    updateMaximum = QtCore.Signal(object)
    updateProgressText = QtCore.Signal(str)
    errorEncountered = QtCore.Signal(object)
    finishedCancelling = QtCore.Signal()
    actionCompleted= QtCore.Signal(object)

    dataReady = QtCore.Signal(object)

    def __init__(self):
        super(FunctionWorker, self).__init__()
        self.stopped = False
        self.finished = True

    def setParams(self, kwargs):
        self.kwargs = kwargs
        self.kwargs['call_back'] = self.emitProgress
        self.kwargs['stop_check'] = self.stopCheck
        self.stopped = False
        self.total = None

    def stop(self):
        self.stopped = True

    def stopCheck(self):
        return self.stopped

    def emitProgress(self, *args):
        if isinstance(args[0],str):
            self.updateProgressText.emit(args[0])
        elif isinstance(args[0],dict):
            self.updateProgressText.emit(args[0]['status'])
        else:
            progress = args[0]
            if len(args) > 1:
                self.updateMaximum.emit(args[1])
            self.updateProgress.emit(progress)


class ImportCorpusWorker(FunctionWorker):  # pragma: no cover
    def __init__(self):
        super(FunctionWorker, self).__init__()
        self.directory = None
        self.corpus_name = None
        self.corpus_temp_dir = None
        self.stopped = False
        self.finished = True

    def setParams(self, directory, temp_directory):
        self.corpus_name = os.path.basename(directory)
        self.directory = directory
        self.corpus_temp_dir = os.path.join(temp_directory, self.corpus_name)
        self.corpus = AcousticCorpus(corpus_directory=self.directory, temporary_directory=self.corpus_temp_dir)
        self.corpus.utterances_time_sorted = True

    def stop(self):
        self.stopped = True

        self.corpus.stopped.stop()
        print("WHOA", self.corpus.stopped.stop_check())

    def run(self):
        time.sleep(0.1)
        if not self.directory:
            return
        self.corpus._load_corpus()
        #if not corpus.loaded_from_temp:
        #    corpus.initialize_corpus(None)
        if self.stopCheck():
            self.finishedCancelling.emit()
        else:
            self.dataReady.emit(self.corpus)
