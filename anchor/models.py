from __future__ import annotations
from typing import Optional, Any, Union

from montreal_forced_aligner.corpus.classes import File, Speaker, Utterance, UtteranceCollection, SpeakerCollection, FileCollection
from montreal_forced_aligner.corpus import AcousticCorpus

from PySide6 import QtGui, QtCore, QtWidgets, QtMultimedia, QtSvg


class TableModel(QtCore.QAbstractTableModel):
    def __init__(self, header_data):
        super(TableModel, self).__init__()
        self._header_data = header_data
        self._data = []

    def update_data(self, data=None):
        self.layoutAboutToBeChanged.emit()
        self._data = data
        self.layoutChanged.emit()

    def headerData(self, index: int, orientation: QtCore.Qt.Orientation, role: Optional[QtCore.Qt.ItemDataRole]=None):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if orientation == QtCore.Qt.Orientation.Horizontal:
                return self._header_data[index]
            else:
                return index + 1


    def data(self, index, role=None):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._data[index.row()][index.column()]

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self._header_data)

class CorpusSelectionModel(QtCore.QItemSelectionModel):
    viewChanged = QtCore.Signal(object, object)
    selectionAudioChanged = QtCore.Signal(object, object)
    def __init__(self, *args, **kwargs):
        super(CorpusSelectionModel, self).__init__(*args, **kwargs)
        self.min_time = 0
        self.max_time = 10

        self.selectionChanged.connect(self.update_selection_times)

    def visible_utts(self) -> UtteranceCollection:
        m = self.model().sourceModel()
        file_utts = UtteranceCollection()
        if not m.current_file:
            return file_utts
        if m.current_file.num_utterances > 1:
            for u in sorted(m.current_file.utterances, key=lambda x: x.begin):
                print(u.begin, u.end, self.max_time, self.min_time)
                if u.begin >= self.max_time:
                    break
                if u.end <= self.min_time:
                    continue
                file_utts.add_utterance(u)
        else:
            file_utts.update(m.current_file.utterances)
        return file_utts

    def currentUtterance(self):
        index = self.currentIndex()
        print(index)
        if not index:
            return
        m = self.model()
        utt = m.data(m.index(index.row(), 1), QtCore.Qt.ItemDataRole.DisplayRole)
        print(utt)
        return m.sourceModel().current_file.utterances[utt]

    def selectedUtterances(self):
        utts = []
        m = self.model()
        for index in self.selectedRows(1):
            utts.append(m.sourceModel().current_file.utterances[m.data(index, QtCore.Qt.ItemDataRole.DisplayRole)])
        print(utts)
        return utts

    def currentText(self):
        index = self.currentIndex()
        if not index:
            return
        m = self.model()

        text = m.data(m.index(index.row(), m.sourceModel().text_column), QtCore.Qt.ItemDataRole.DisplayRole)
        return text

    def zoom_in(self):
        shift = round((self.max_time - self.min_time) * 0.25, 3)
        cur_duration = self.max_time - self.min_time
        if cur_duration < 2:
            return
        if cur_duration - 2 * shift < 1:
            shift = (cur_duration - 1) / 2
        self.min_time += shift
        self.max_time -= shift
        self.viewChanged.emit(self.min_time, self.max_time)

    def zoom_out(self):
        duration = self.model().sourceModel().currentDuration()
        shift = round((self.max_time - self.min_time) * 0.25, 3)
        cur_duration = self.max_time - self.min_time
        if cur_duration + 2 * shift > 20:
            shift = (20 - cur_duration) / 2
        self.min_time -= shift
        self.max_time += shift
        if self.max_time > duration:
            self.max_time = duration
        if self.min_time < 0:
            self.min_time = 0
        self.viewChanged.emit(self.min_time, self.max_time)

    def update_from_slider(self, value):
        if not self.max_time:
            return
        cur_window = self.max_time - self.min_time
        self.min_time = value
        self.max_time = value + cur_window
        self.viewChanged.emit(self.min_time, self.max_time)

    def update_selection_times(self):
        m = self.model()
        begin = None
        end = None
        for index in self.selectedRows(1):
            b = m.data(m.index(index.row(), 3), QtCore.Qt.ItemDataRole.DisplayRole)
            e =  m.data(m.index(index.row(), 4), QtCore.Qt.ItemDataRole.DisplayRole)
            if begin is None or b < begin:
                begin = b
            if end is None or e > end:
                end = e
        if begin is not None and end is not None:
            self.selectionAudioChanged.emit(begin, end)

    def checkSelected(self, utterance: Utterance):
        m = self.model()
        for index in self.selectedRows(1):
            utt = m.data(index, QtCore.Qt.ItemDataRole.DisplayRole)
            if utterance.name == utt:
                return True
        return False


    def focusUtterance(self, index):
        print('FOCUSING UTTERANCE')
        m = self.model()
        if m.sourceModel().current_file:
            begin = m.data(m.index(index.row(), 3), QtCore.Qt.ItemDataRole.DisplayRole)
            end = m.data(m.index(index.row(), 4), QtCore.Qt.ItemDataRole.DisplayRole)
            padding = 1
            self.min_time = begin - padding
            self.max_time = end + padding
            self.viewChanged.emit(self.min_time, self.max_time)
            self.selectionAudioChanged.emit(begin, end)


class DeleteUtteranceCommand(QtGui.QUndoCommand):
    def __init__(self, deleted_utterances: list[Utterance], corpus_model: CorpusModel):
        super().__init__()
        self.corpus_model = corpus_model
        self.deleted_utterances = deleted_utterances
        self.setText(QtCore.QCoreApplication.translate('DeleteUtteranceCommand', 'Delete utterances'))

    def redo(self) -> None:
        for utt in self.deleted_utterances:
            self.corpus_model.corpus.delete_utterance(utt)
        self.corpus_model.update_data()
        self.corpus_model.fileSaveable.emit(True)

    def undo(self) -> None:
        for utt in self.deleted_utterances:
            self.corpus_model.corpus.add_utterance(utt)
        self.corpus_model.update_data()
        self.corpus_model.fileSaveable.emit(True)


class SplitUtteranceCommand(QtGui.QUndoCommand):
    def __init__(self, split_utterances: list[tuple[Utterance, Utterance, Utterance]], corpus_model: CorpusModel):
        super().__init__()
        self.corpus_model = corpus_model
        self.split_utterances = split_utterances
        self.setText(QtCore.QCoreApplication.translate('SplitUtteranceCommand', 'Split utterances'))

    def redo(self) -> None:
        for old_utt, first_utt, second_utt in self.split_utterances:
            self.corpus_model.corpus.delete_utterance(old_utt)
            self.corpus_model.corpus.add_utterance(first_utt)
            self.corpus_model.corpus.add_utterance(second_utt)
        self.corpus_model.update_data()
        self.corpus_model.fileSaveable.emit(True)

    def undo(self) -> None:
        for old_utt, first_utt, second_utt in self.split_utterances:
            self.corpus_model.corpus.add_utterance(old_utt)
            self.corpus_model.corpus.delete_utterance(first_utt)
            self.corpus_model.corpus.delete_utterance(second_utt)
        self.corpus_model.update_data()
        self.corpus_model.fileSaveable.emit(True)


class MergeUtteranceCommand(QtGui.QUndoCommand):
    def __init__(self, unmerged_utterances: list[Utterance], merged_utterance: Utterance, corpus_model: CorpusModel):
        super().__init__()
        self.corpus_model = corpus_model
        self.unmerged_utterances = unmerged_utterances
        self.merged_utterance = merged_utterance
        self.setText(QtCore.QCoreApplication.translate('MergeUtteranceCommand', 'Merge utterances'))

    def redo(self) -> None:
        for old_utt in self.unmerged_utterances:
            self.corpus_model.corpus.delete_utterance(old_utt)
        self.corpus_model.corpus.add_utterance(self.merged_utterance)
        self.corpus_model.update_data()
        self.corpus_model.fileSaveable.emit(True)

    def undo(self) -> None:
        for old_utt in self.unmerged_utterances:
            self.corpus_model.corpus.add_utterance(old_utt)
        self.corpus_model.corpus.delete_utterance(self.merged_utterance)
        self.corpus_model.update_data()
        self.corpus_model.fileSaveable.emit(True)


class CreateUtteranceCommand(QtGui.QUndoCommand):
    def __init__(self, new_utterance: Utterance, corpus_model: CorpusModel):
        super().__init__()
        self.corpus_model = corpus_model
        self.new_utterance = new_utterance
        self.setText(QtCore.QCoreApplication.translate('CreateUtteranceCommand', 'Create utterance'))

    def redo(self) -> None:

        self.corpus_model.corpus.add_utterance(self.new_utterance)
        self.corpus_model.update_data()
        self.corpus_model.fileSaveable.emit(True)

    def undo(self) -> None:
        self.corpus_model.corpus.delete_utterance(self.new_utterance)
        self.corpus_model.update_data()
        self.corpus_model.fileSaveable.emit(True)

class UpdateUtteranceCommand(QtGui.QUndoCommand):
    def __init__(self, old_utterance: Utterance, new_utterance: Utterance, corpus_model: CorpusModel):
        super().__init__()
        self.corpus_model = corpus_model
        self.old_utterance = old_utterance
        self.new_utterance = new_utterance
        self.setText(QtCore.QCoreApplication.translate('UpdateUtteranceCommand', 'Update utterance data'))

    def redo(self) -> None:
        self.corpus_model.corpus.delete_utterance(self.old_utterance)
        self.corpus_model.corpus.add_utterance(self.new_utterance)
        print('UPDATINGG')
        print(self.new_utterance)
        print(self.new_utterance.speaker)
        print(self.new_utterance.text)
        print(self.old_utterance.text)
        print(self.old_utterance)
        self.corpus_model.update_data()
        self.corpus_model.fileSaveable.emit(True)

    def undo(self) -> None:
        print("UNDOING")
        print(repr(self.new_utterance))
        print(repr(self.old_utterance))
        print(self.new_utterance.text)
        print(self.old_utterance.text)
        self.corpus_model.corpus.delete_utterance(self.new_utterance)
        self.corpus_model.corpus.add_utterance(self.old_utterance)
        self.corpus_model.update_data()
        self.corpus_model.fileSaveable.emit(True)


class CorpusModel(TableModel):
    fileChanged = QtCore.Signal(object)
    fileSaveable = QtCore.Signal(object)
    undoAvailable = QtCore.Signal(object)

    def __init__(self):
        super(CorpusModel, self).__init__(['', 'Utterance', 'Speaker', 'Begin', 'End', 'Text'])
        self.oov_column = 0
        self.utterance_column = 1
        self.speaker_column = 2
        self.begin_column = 3
        self.end_column = 4
        self.text_column = 5
        self._data = {}
        self.corpus: Optional[AcousticCorpus] = None
        self._dictionary = None
        self.current_file: Optional[File] = None
        self.current_utterance: Optional[Utterance] = None
        self.files = FileCollection()
        self._changed = False
        self.undo_stack = QtGui.QUndoStack()
        self.reversed_indices = {}

    def setDictionary(self, dictionary):
        self._dictionary = dictionary

    def updateUtteranceText(self, utterance: Union[str, Utterance], text: str):
        if isinstance(utterance, str):
            utterance = self.corpus.utterances[utterance]
        utterance.text = text
        index = self.reversed_indices[utterance]
        self._data[utterance][self.text_column] = text
        index = self.index(index, self.text_column)
        self.dataChanged.emit(index, index)

    def updateCurrentFile(self, file_name = None):
        if file_name:
            self.current_file = self.files[file_name]
        if len(self.current_file.utterances) > 1:
            self.long_file = False
        else:
            self.long_file = True

        self.current_file.load_wav_data()
        self.fileChanged.emit(self.current_file)

    def create_utterance(self, speaker:Optional[Speaker], begin:float, end:float):
        channel = 0
        if self.current_file.num_channels > 1:
            ind = self.current_file.speaker_ordering.index(speaker)
            if ind >= len(self.current_file.speaker_ordering) / 2:
                channel = 1
        if speaker is None:
            if not self.current_file.speaker_ordering:
                speaker = Speaker('speech')
                self.current_file.speaker_ordering.append(speaker)

        begin = round(begin, 4)
        end = round(end, 4)
        text = ''
        new_utt = Utterance(speaker=speaker, file=self.current_file, begin=begin, end=end, channel=channel, text=text)
        self.undo_stack.push(CreateUtteranceCommand(new_utt, self))

    def update_utterance(self, utterance: Union[str, Utterance],
                         begin: Optional[float]=None,
                         end: Optional[float]=None,
                         speaker: Optional[Union[str, Speaker]]=None, text: Optional[str]=None):

        if isinstance(utterance, str):
            utterance = self.corpus.utterances[utterance]
        new_utt = Utterance(file=utterance.file, speaker=utterance.speaker, text=utterance.text,
                            begin=utterance.begin, end=utterance.end, channel=utterance.channel)
        if begin is not None:
            new_utt.begin = begin
        if end is not None:
            new_utt.end = end
        if speaker is not None:
            if isinstance(speaker, str):
                speaker = self.corpus.speakers[speaker]
            new_utt.speaker = speaker
        print("HELLO!?!", new_utt.speaker)
        if text is not None:
            new_utt.text = text
        self.undo_stack.push(UpdateUtteranceCommand(utterance, new_utt, self))

    def delete_utterances(self, utterances: list[Utterance]):
        self.undo_stack.push(DeleteUtteranceCommand(utterances, self))

    def split_utterances(self, utterances: list[Utterance]):
        splitting_utterances = []
        for utt in utterances:
            duration = utt.duration
            beg = utt.begin
            end = utt.end
            if beg is None:
                beg = 0
                end = utt.file.duration
            first_text = ''
            second_text = ''
            if utt.text:
                t = utt.text.split()
                mid_ind = int(len(t)/2)
                first_text = t[:mid_ind]
                second_text = t[mid_ind:]
            split_time = beg + (duration / 2)
            first_utt = Utterance(speaker=utt.speaker, file=utt.file,begin=beg, end = split_time, channel=utt.channel,
                                  text=first_text
                                  )
            second_utt = Utterance(speaker=utt.speaker, file=utt.file, begin=split_time, end =end, channel=utt.channel,
                                   text=second_text)
            splitting_utterances.append((utt, first_utt, second_utt))
        self.undo_stack.push(SplitUtteranceCommand(splitting_utterances, self))


    def merge_utterances(self, utterances: list[Utterance]):
        min_begin = 1000000000
        max_end = 0
        text = ''
        speaker = None
        channel = None
        for old_utt in sorted(utterances, key=lambda x: x.begin):
            if speaker is None:
                speaker = old_utt.speaker
            if channel is None:
                channel = old_utt.channel
            if old_utt.begin < min_begin:
                min_begin = old_utt.begin
            if old_utt.end > max_end:
                max_end = old_utt.end
            utt_text = old_utt.text
            if utt_text == 'speech' and text.strip() == 'speech':
                continue
            text += utt_text + ' '
        text = text[:-1]
        new_utt = Utterance(speaker=speaker, file=self.current_file, begin=min_begin, end=max_end, channel=channel, text=text)
        self.undo_stack.push(MergeUtteranceCommand(utterances, new_utt, self))

    def indexForUtterance(self, utterance):
        return self.createIndex(self.reversed_indices[utterance], 1)


    def fileNames(self):
        return self.files

    def setCorpus(self, corpus):
        self.corpus = corpus

        if corpus is not None:
            self.files = self.corpus.files
            self.current_file = next(iter(self.files))
        else:
            self.files = FileCollection()
            self.current_file = None
        self.update_data()
        self._changed = False
        if self.current_file:
            self.updateCurrentFile()

    def headerData(self, index, orientation, role):
        if index != 0 and role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._header_data[index]

    def data(self, index, role):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._data[self._indices[index.row()]][index.column()]
        elif role == QtCore.Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            if self._data[self._indices[index.row()]][index.column()]:
                return QtCore.Qt.CheckState.Checked
            else:
                return QtCore.Qt.CheckState.Unchecked

    def update_data(self):
        print("UPDATING DATA")
        print(self.sender())
        self.layoutAboutToBeChanged.emit()
        self._data = {}
        self._indices = []
        self.reversed_indices = {}
        if self.current_file:
            self._header_data = ['OOV', 'Utterance', 'Speaker', 'Begin', 'End', 'Text']
            self.oov_column = 0
            self.utterance_column = 1
            self.speaker_column = 2
            self.begin_column = 3
            self.end_column = 4
            self.text_column = 5
            print("hello!!", len(self.current_file.utterances))
            for i, u in enumerate(sorted(self.current_file.utterances, key=lambda x: x.begin)):
                t = u.text
                oov_found = False
                if self._dictionary is not None:
                    words = t.split(' ')
                    for w in words:
                        if not w:
                            continue
                        if not self._dictionary.check_word(w):
                            oov_found = True
                            break
                self._indices.append(u)
                self.reversed_indices[u] = i
                self._data[u] = [oov_found, u.name, u.speaker.name, u.begin,
                                 u.end, t]
        else:
            self._header_data = ['OOV', 'Utterance', 'Speaker', 'Text']
            self.oov_column = 0
            self.utterance_column = 1
            self.speaker_column = 2
            self.text_column = 3
            for i, u in enumerate(sorted(self.corpus.utterances)):
                oov_found = False
                t = u.text
                if self._dictionary is not None:
                    words = t.split(' ')
                    for w in words:
                        if not self._dictionary.check_word(w):
                            oov_found = True
                            break
                self._indices.append(u)
                self.reversed_indices[u] = i
                self._data[u] = [oov_found, u.name, u.speaker.name, t]

        self.layoutChanged.emit()


class CorpusProxy(QtCore.QSortFilterProxyModel):
    def __init__(self, *args):
        super(CorpusProxy, self).__init__(*args)
        self.setDynamicSortFilter(True)
        self.sourceModelChanged.connect(self.updateFilterKey)

    def updateFilterKey(self):
        self.setFilterKeyColumn(self.sourceModel().columnCount() - 1)

    def headerData(self, section, orientation, role):
        # if display role of vertical headers
        if orientation == QtCore.Qt.Orientation.Vertical and role == QtCore.Qt.ItemDataRole.DisplayRole:
            # return the actual row number
            return section + 1
        # for other cases, rely on the base implementation
        return super(CorpusProxy, self).headerData(section, orientation, role)
