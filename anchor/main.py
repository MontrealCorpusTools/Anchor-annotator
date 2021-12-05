import yaml
import os
import sys
import traceback
from PySide6 import QtGui, QtCore, QtWidgets, QtMultimedia, QtSvg, QtSvgWidgets

from montreal_forced_aligner.config import get_temporary_directory

from montreal_forced_aligner.dictionary import PronunciationDictionary
from montreal_forced_aligner.models import G2PModel, AcousticModel, LanguageModel, IvectorExtractorModel, DictionaryModel

from anchor.widgets import UtteranceListWidget, UtteranceDetailWidget, \
    DetailedMessageBox, DefaultAction, AnchorAction, create_icon, HelpDropDown, \
    MediaPlayer, DictionaryWidget, SpeakerWidget
from anchor.models import CorpusModel, CorpusSelectionModel, CorpusProxy


from anchor.workers import ImportCorpusWorker


class ColorEdit(QtWidgets.QPushButton): # pragma: no cover
    def __init__(self, color, parent=None):
        super(ColorEdit, self).__init__(parent=parent)
        self._color = color
        self.update_icon()
        self.clicked.connect(self.open_dialog)

    def update_icon(self):
        pixmap = QtGui.QPixmap(100, 100)
        pixmap.fill(self._color)
        icon = QtGui.QIcon(pixmap)
        icon.addPixmap(pixmap, QtGui.QIcon.Mode.Disabled)
        self.setIcon(icon)

    @property
    def color(self):
        return self._color.name()

    def open_dialog(self):
        color = QtWidgets.QColorDialog.getColor()
        if color.isValid():
            self._color = color
            self.update_icon()


class FontDialog(QtWidgets.QFontDialog):
    def __init__(self, *args):
        super(FontDialog, self).__init__(*args)


class FontEdit(QtWidgets.QPushButton): # pragma: no cover
    """
    Parameters
    ----------
    font : QtGui.QFont
    """
    def __init__(self, font, parent=None):
        super(FontEdit, self).__init__(parent=parent)
        self.font = font
        self.update_icon()
        self.clicked.connect(self.open_dialog)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

    def update_icon(self):
        self.setFont(self.font)
        self.setText(self.font.key().split(',',maxsplit=1)[0])

    def open_dialog(self):
        font, ok = FontDialog.getFont(self.font)

        if ok:
            self.font = font
            self.update_icon()

class ConfigurationOptions(object):
    def __init__(self, data):
        self.data = {
            'temp_directory': get_temporary_directory(),
            'current_corpus_path': None,
            'current_acoustic_model_path': None,
            'current_dictionary_path': None,
            'current_g2p_model_path': None,
            'current_language_model_path': None,
            'current_ivector_extractor_path': None,
            'autosave': True,
            'autoload': True,
            'is_maximized': False,
            'play_keybind': 'Tab',
            'delete_keybind': 'Delete',
            'save_keybind': '',
            'search_keybind': 'Ctrl+F',
            'split_keybind': 'Ctrl+S',
            'merge_keybind': 'Ctrl+M',
            'zoom_in_keybind': 'Ctrl+I',
            'zoom_out_keybind': 'Ctrl+O',
            'pan_left_keybind': 'Left',
            'pan_right_keybind': 'Right',
            'undo_keybind': 'Ctrl+Z',
            'redo_keybind': 'Shift+Ctrl+Z',

            'font': QtGui.QFont('Noto Sans', 12).toString(),
            'plot_text_width': 400,
            'height': 720,
            'width': 1280,
            'volume': 100,

        }
        for k, v in self.mfa_color_theme.items():
            self.data['style_'+ k] = v
        for k, v in self.mfa_plot_theme.items():
            self.data['plot_'+ k] = v
        self.data.update(data)


    def __getitem__(self, item):
        if 'color' in item:
            return QtGui.QColor(self.data[item])
        return self.data[item]

    def __setitem__(self, key, value):
        self.data[key] = value

    def get(self, key, default):
        if key in self.data:
            return self.data[key]
        return default

    def items(self):
        return self.data.items()

    def update(self, dictionary):
        if isinstance(dictionary, ConfigurationOptions):
            self.data.update(dictionary.data)
        elif dictionary is not None:
            self.data.update(dictionary)

    @property
    def is_mfa(self):
        return self.data.get('theme', 'MFA').lower() == 'mfa'

    @property
    def font_options(self):
        theme = self.data.get('theme', 'MFA')
        base_font = self.data.get('font', QtGui.QFont('Noto Sans', 12).toString())
        if theme.lower() == 'custom':
            base_font = self.data.get('font', QtGui.QFont('Noto Sans', 12).toString())

        font = QtGui.QFont()
        font.fromString(base_font)

        small_font = QtGui.QFont()
        small_font.fromString(base_font)
        small_font.setPointSize(int(0.75 * small_font.pointSize()))

        header_font = QtGui.QFont()
        header_font.fromString(base_font)
        header_font.setBold(True)

        big_font = QtGui.QFont()
        big_font.fromString(base_font)
        big_font.setPointSize(int(1.25 * big_font.pointSize()))

        title_font = QtGui.QFont()
        title_font.fromString(base_font)
        title_font.setPointSize(int(3 * big_font.pointSize()))
        return {'font': font, 'axis_font': small_font,
                'form_font': small_font, 'header_font': header_font,
                'small_font': small_font, 'big_font': big_font, 'title_font': title_font}

    @property
    def mfa_color_palettes(self):
        yellows = {'very_light': '#F2CD49',
                   'light': '#FFD60A',
                   'base': '#FFC300',
                   'dark': '#E3930D',
                   'very_dark': '#7A4E03',
                   }
        blues = {
            'very_light': '#7AB5E6',
            'light': '#0E63B3',
            'base': '#003566',
            'dark': '#001D3D',
            'very_dark': '#000814',
                   }
        reds = {'very_light': '#DC4432',
                   'light': '#C63623',
                   'base': '#B32300',
                   'dark': '#891800',
                   'very_dark': '#620E00',
                   }
        white = '#EDDDD4'
        black = blues['very_dark']
        return yellows, blues, reds, white, black

    @property
    def praat_like_color_theme(self):
        white = '#FFFFFF'
        black = '#000000'
        return {
                'background_color': '#E5E5D8',

                'table_header_color': black,
                'table_header_background_color': '#BFBFBF',
                'table_even_color': white,
                'table_odd_color': white,
                'table_text_color': black,

                'underline_color': '#DC0806',
                'keyword_color': '#FAF205',
                'keyword_text_color': black,
                'selection_color': '#0078D7',
                'selection_text_color': white,
                'text_edit_color': black,
                'error_color': '#DC0806',
                'error_text_color': '#DC0806',
                'error_background_color': white,
                'text_edit_background_color': white,
                'line_edit_color': black,
                'line_edit_background_color': white,

                'main_widget_border_color': 'none',
                'main_widget_background_color': white,

                'menu_background_color': white,
                'menu_text_color': black,

                'checked_background_color': white,
                'checked_color': black,

                'enabled_color': black,
                'enabled_background_color': '#F0F0F0',
                'enabled_border_color': black,

                'active_color': black,
                'active_background_color': '#F0F0F0',
                'active_border_color': black,

                'hover_text_color': black,
                'hover_background_color': '#F0F0F0',
                'hover_border_color': black,

                'disabled_text_color': '#A0A0A0',
                'disabled_background_color': '#F0F0F0',
                'disabled_border_color': black,

                'scroll_bar_background_color': '#F0F0F0',
                'scroll_bar_handle_color': '#F0F0F0',
                'scroll_bar_border_color': black,

        }

    @property
    def praat_like_plot_theme(self):
        white = '#FFFFFF'
        black = '#000000'
        return {
            'background_color': white,
            'play_line_color': '#DC0806',
            'selected_range_color': '#FFD2D2',
            'selected_interval_color': '#FAF205',
            'selected_line_color': '#DC0806',
            'selected_text_color': '#DC0806',
            'break_line_color': '#0000D3',
            'wave_line_color': black,
            'text_color': black,
            'axis_color': black,
            'interval_background_color': white,
        }

    @property
    def mfa_color_theme(self):
        yellows, blues, reds, white, black = self.mfa_color_palettes
        return {
                'background_color': blues['base'],

                'table_header_color': white,
                'table_header_background_color': blues['light'],
                'table_even_color': yellows['very_light'],
                'table_odd_color': blues['very_light'],
                'table_text_color': black,

                'underline_color': reds['very_light'],
                'keyword_color': yellows['light'],
                'keyword_text_color': black,
                'selection_color': blues['light'],
                'error_color': reds['very_light'],
                'error_text_color': yellows['dark'],
                'error_background_color': reds['light'],

                'text_edit_color': white,
                'text_edit_background_color': black,
                'line_edit_color': black,
                'line_edit_background_color': white,

                'main_widget_border_color': blues['light'],
                'main_widget_background_color': black,

                'checked_background_color': black,
                'checked_color': yellows['light'],

                'menu_background_color': yellows['base'],
                'menu_text_color': black,

                'enabled_color': black,
                'enabled_background_color': yellows['base'],
                'enabled_border_color': blues['very_dark'],

                'active_color': yellows['very_light'],
                'active_background_color': blues['dark'],
                'active_border_color': blues['light'],

                'hover_text_color': yellows['light'],
                'hover_background_color': blues['light'],
                'hover_border_color': blues['very_dark'],

                'disabled_text_color': reds['very_light'],
                'disabled_background_color': blues['dark'],
                'disabled_border_color': blues['very_dark'],

                'scroll_bar_background_color': blues['dark'],
                'scroll_bar_handle_color': yellows['light'],
                'scroll_bar_border_color': black,
            }

    @property
    def mfa_plot_theme(self):
        yellows, blues, reds, white, black = self.mfa_color_palettes
        return {
            'background_color': black,
            'play_line_color': reds['very_light'],
            'selected_range_color': blues['very_light'],
            'selected_interval_color': blues['base'],
            'hover_line_color': blues['very_light'],
            'moving_line_color': reds['light'],
            'break_line_color': yellows['light'],
            'wave_line_color': white,
            'text_color': white,
            'selected_text_color': white,
            'axis_color': yellows['light'],
            'interval_background_color': blues['dark'],
        }

    @property
    def style_keys(self):
        return ['style_'+ k for k in self.mfa_color_theme.keys()]

    @property
    def plot_keys(self):
        return ['plot_'+ k for k in self.mfa_plot_theme.keys()]

    @property
    def color_options(self):
        theme = self.data.get('theme', 'MFA')
        if theme == 'custom':
            return {k.replace('style_', ''): v for k,v in self.data.items() if k.startswith('style_')}
        elif theme.lower() == 'mfa':
            return self.mfa_color_theme
        elif theme.lower() == 'praat-like':
            return self.praat_like_color_theme


    @property
    def plot_color_options(self):
        theme = self.data.get('theme', 'MFA')
        if theme == 'custom':
            return {k: v for k,v in self.data.items() if k.startswith('plot_')}
        if theme.lower() == 'mfa':
            return self.mfa_plot_theme
        elif theme.lower() == 'praat-like':
            return self.praat_like_plot_theme
        else:
            return {
            'background_color': 'black',
            'play_line_color': 'red',
            'selected_range_color': 'blue',
            'selected_line_color': 'green',
            'break_line_color': 'white',
            'wave_line_color': 'white',
            'text_color': 'white',
            'interval_background_color': 'darkGray',
            }

class FormLayout(QtWidgets.QVBoxLayout):
    def addRow(self, label, widget):
        row_layout = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(label)
        label.setSizePolicy(QtWidgets.QSizePolicy.Expanding,QtWidgets.QSizePolicy.Expanding)
        row_layout.addWidget(label)
        row_layout.addWidget(widget)
        super(FormLayout, self).addLayout(row_layout)


class OptionsDialog(QtWidgets.QDialog): # pragma: no cover
    def __init__(self, parent=None):
        super(OptionsDialog, self).__init__(parent=parent)
        self.base_config = ConfigurationOptions({})
        self.base_config.update(parent.config)

        self.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setFont(self.base_config.font_options['font'])
        self.tab_widget.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)

        self.appearance_widget = QtWidgets.QWidget()
        self.appearance_widget.setFont(self.base_config.font_options['font'])
        self.appearance_widget.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        self.tab_widget.addTab(self.appearance_widget, 'Appearance')
        appearance_layout = QtWidgets.QVBoxLayout()
        common_appearance_layout = FormLayout()
        common_appearance_widget = QtWidgets.QWidget()

        common_appearance_widget.setLayout(common_appearance_layout)
        appearance_tabs = QtWidgets.QTabWidget()

        self.theme_select = QtWidgets.QComboBox()

        self.theme_select.addItem('MFA')
        self.theme_select.addItem('Praat-like')
        self.theme_select.addItem('Custom')
        self.theme_select.setCurrentText(self.base_config.get('theme','MFA'))
        common_appearance_layout.addRow('Theme', self.theme_select)

        f = QtGui.QFont()
        f.fromString(self.base_config['font'])
        self.font_edit = FontEdit(f)

        common_appearance_layout.addRow('Font', self.font_edit)
        appearance_layout.addWidget(common_appearance_widget)
        self.theme_select.currentTextChanged.connect(self.updateColors)

        style_wrapper = QtWidgets.QHBoxLayout()
        breaks = 2
        break_layouts = []
        for b in range(breaks):
            fl = FormLayout()
            break_layouts.append(fl)
            style_wrapper.addLayout(fl)
        self.color_edits = {}
        num_edits = len(self.base_config.style_keys)
        num_per = num_edits / breaks
        cur = 0
        cur_count =0
        for i, style_name in enumerate(self.base_config.style_keys):
            cur_count += 1
            if cur_count >= num_per and cur < breaks - 1:
                cur += 1
                cur_count = 0
            self.color_edits[style_name] = ColorEdit(QtGui.QColor(self.base_config[style_name]))
            human_readable = ' '.join(style_name.replace('style_', '').replace('_color', '').split('_')).title()
            break_layouts[cur].addRow(human_readable, self.color_edits[style_name])

        plot_appearance_layout = FormLayout()

        self.plot_color_edits = {}
        for style_name in self.base_config.plot_keys:
            self.plot_color_edits[style_name] = ColorEdit(QtGui.QColor(self.base_config[style_name]))
            human_readable = ' '.join(style_name.replace('plot_', '').replace('_color', '').split('_')).title()
            plot_appearance_layout.addRow(human_readable, self.plot_color_edits[style_name])


        if self.theme_select.currentText().lower() != 'custom':
            for k, v in self.color_edits.items():
                v.setEnabled(False)
            for k, v in self.plot_color_edits.items():
                v.setEnabled(False)

        self.plot_text_width_edit = QtWidgets.QSpinBox()
        self.plot_text_width_edit.setMinimum(1)
        self.plot_text_width_edit.setMaximum(1000)
        self.plot_text_width_edit.setValue(self.base_config['plot_text_width'])
        plot_appearance_layout.addRow('Plot text width', self.plot_text_width_edit)
        style_appearance_widget = QtWidgets.QWidget()

        style_appearance_widget.setFont(self.base_config.font_options['font'])
        style_appearance_widget.setLayout(style_wrapper)
        appearance_tabs.addTab(style_appearance_widget, 'General')

        plot_appearance_widget = QtWidgets.QWidget()
        plot_appearance_widget.setLayout(plot_appearance_layout)
        appearance_tabs.addTab(plot_appearance_widget, 'Plot')

        appearance_layout.addWidget(appearance_tabs)
        self.appearance_widget.setLayout(appearance_layout)

        self.key_bind_widget = QtWidgets.QWidget()
        self.key_bind_widget.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        self.tab_widget.addTab(self.key_bind_widget, 'Key shortcuts')

        key_bind_layout = QtWidgets.QFormLayout()

        self.autosave_edit = QtWidgets.QCheckBox()
        self.autosave_edit.setChecked(self.base_config['autosave'])
        self.autosave_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        key_bind_layout.addRow('Autosave on exit', self.autosave_edit)

        self.autoload_edit = QtWidgets.QCheckBox()
        self.autoload_edit.setChecked(self.base_config['autoload'])
        self.autoload_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        key_bind_layout.addRow('Autoload last used corpus', self.autoload_edit)

        self.play_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.play_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['play_keybind']))
        self.play_key_bind_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        key_bind_layout.addRow('Play audio', self.play_key_bind_edit)

        self.zoom_in_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.zoom_in_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['zoom_in_keybind']))
        self.zoom_in_key_bind_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        key_bind_layout.addRow('Zoom in', self.zoom_in_key_bind_edit)

        self.zoom_out_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.zoom_out_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['zoom_out_keybind']))
        self.zoom_out_key_bind_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        key_bind_layout.addRow('Zoom out', self.zoom_out_key_bind_edit)

        self.pan_left_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.pan_left_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['pan_left_keybind']))
        self.pan_left_key_bind_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        key_bind_layout.addRow('Pan left', self.pan_left_key_bind_edit)

        self.pan_right_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.pan_right_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['pan_right_keybind']))
        self.pan_right_key_bind_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        key_bind_layout.addRow('Pan right', self.pan_right_key_bind_edit)

        self.merge_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.merge_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['merge_keybind']))
        self.merge_key_bind_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        key_bind_layout.addRow('Merge utterances', self.merge_key_bind_edit)

        self.split_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.split_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['split_keybind']))
        self.split_key_bind_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        key_bind_layout.addRow('Split utterances', self.split_key_bind_edit)

        self.delete_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.delete_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['delete_keybind']))
        self.delete_key_bind_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        key_bind_layout.addRow('Delete utterance', self.delete_key_bind_edit)

        self.save_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.save_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['save_keybind']))
        self.save_key_bind_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        key_bind_layout.addRow('Save current file', self.save_key_bind_edit)

        self.search_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.search_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['search_keybind']))
        self.search_key_bind_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        key_bind_layout.addRow('Search within the corpus', self.search_key_bind_edit)

        self.key_bind_widget.setLayout(key_bind_layout)

        layout = QtWidgets.QVBoxLayout()

        button_layout = QtWidgets.QHBoxLayout()
        self.save_button = QtWidgets.QPushButton('Save')
        self.save_button.clicked.connect(self.accept)
        self.save_button.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.cancel_button = QtWidgets.QPushButton('Cancel')
        self.cancel_button.clicked.connect(self.reject)
        self.cancel_button.setFocusPolicy(QtCore.Qt.ClickFocus)

        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addWidget(self.tab_widget)
        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.setWindowTitle('Preferences')

    def updateColors(self):
        theme = self.theme_select.currentText()
        for k, v in self.color_edits.items():
            v.setEnabled(theme == 'custom')
        for k, v in self.plot_color_edits.items():
            v.setEnabled(theme == 'custom')

    def generate_config(self):
        out = {
            'autosave': self.autosave_edit.isChecked(),
            'autoload': self.autoload_edit.isChecked(),
            'play_keybind': self.play_key_bind_edit.keySequence().toString(),
            'delete_keybind': self.delete_key_bind_edit.keySequence().toString(),
            'save_keybind': self.save_key_bind_edit.keySequence().toString(),
            'split_keybind': self.split_key_bind_edit.keySequence().toString(),
            'merge_keybind': self.merge_key_bind_edit.keySequence().toString(),
            'zoom_in_keybind': self.zoom_in_key_bind_edit.keySequence().toString(),
            'zoom_out_keybind': self.zoom_out_key_bind_edit.keySequence().toString(),
            'pan_left_keybind': self.pan_left_key_bind_edit.keySequence().toString(),
            'pan_right_keybind': self.pan_right_key_bind_edit.keySequence().toString(),
            'theme': self.theme_select.currentText(),

            'plot_text_width': self.plot_text_width_edit.value(),

            'font': self.font_edit.font.toString(),
        }
        for k, v in self.color_edits.items():
            out[k] = v.color
        for k, v in self.plot_color_edits.items():
            out[k] = v.color

        return out


class Application(QtWidgets.QApplication): # pragma: no cover
    pass
    #def notify(self, receiver, e):
        #if e and e.type() == QtCore.QEvent.KeyPress:
        #    if e.key() == QtCore.Qt.Key_Tab:
        #        return False
    #    return super(Application, self).notify(receiver, e)


class WarningLabel(QtWidgets.QLabel):
    def __init__(self, *args):
        super(WarningLabel, self).__init__( *args)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)

class LoadingScreen(QtWidgets.QWidget):
    def __init__(self, *args):
        super(LoadingScreen, self).__init__( *args)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QtWidgets.QVBoxLayout()
        self.loading_movie = QtGui.QMovie(':loading_screen.gif')
        self.movie_label = QtWidgets.QLabel()
        self.movie_label.setMinimumSize(720,576)

        self.movie_label.setMovie(self.loading_movie)

        self.logo_icon = QtGui.QIcon(':logo_text.svg')

        self.logo_label = QtWidgets.QLabel()
        self.logo_label.setPixmap(self.logo_icon.pixmap(QtCore.QSize(720, 144)))

        self.logo_label.setFixedSize(720, 144)

        self.text_label = QtWidgets.QLabel()
        self.text_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.exit_label = QtWidgets.QLabel('Wrapping things up before exit, please wait a moment...')
        self.exit_label.setVisible(False)
        tool_bar_wrapper = QtWidgets.QVBoxLayout()
        self.tool_bar = QtWidgets.QToolBar()
        self.tool_bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.tool_bar.addWidget(self.text_label)

        tool_bar_wrapper.addWidget(self.tool_bar, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        self.setVisible(False)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.movie_label)
        layout.addWidget(self.logo_label)
        layout.addWidget(self.text_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(tool_bar_wrapper)
        layout.addWidget(self.exit_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)

    def update_config(self, config):
        font_config = config.font_options
        self.text_label.setFont(font_config['big_font'])
        self.exit_label.setFont(font_config['big_font'])

    def setExiting(self):
        self.tool_bar.setVisible(False)
        self.exit_label.setVisible(True)
        self.repaint()

    def setVisible(self, visible: bool) -> None:
        if visible:
            self.loading_movie.start()
        else:
            self.text_label.setText('')
            self.loading_movie.stop()
        super(LoadingScreen, self).setVisible(visible)

    def setCorpusName(self, corpus_name):
        self.text_label.setText(corpus_name)
        self.text_label.setVisible(True)

class TitleScreen(QtWidgets.QWidget):
    def __init__(self, *args):
        super(TitleScreen, self).__init__( *args)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QtWidgets.QVBoxLayout()
        self.logo_widget = QtSvgWidgets.QSvgWidget(':splash_screen.svg')
        self.setMinimumSize(720, 720)
        self.setMaximumSize(720, 720)

        self.setVisible(False)
        #self.loading_label.setWindowFlag()
        layout.addWidget(self.logo_widget)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.setLayout(layout)

    def update_config(self, config):
        font_config = config.font_options

class DockWidget(QtWidgets.QDockWidget):
    def __init__(self, *args, **kwargs):
        super(DockWidget, self).__init__(*args, **kwargs)
        #self.setFeatures(QtWidgets.QDockWidget.AllDockWidgetFeatures)
        self.setContentsMargins(0,0,0,0)

class MainWindow(QtWidgets.QMainWindow):  # pragma: no cover
    configUpdated = QtCore.Signal(object)
    corpusLoaded = QtCore.Signal()
    dictionaryLoaded = QtCore.Signal(object)
    g2pLoaded = QtCore.Signal(object)
    ivectorExtractorLoaded = QtCore.Signal(object)
    acousticModelLoaded = QtCore.Signal(object)
    languageModelLoaded = QtCore.Signal(object)
    newSpeaker = QtCore.Signal(object)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Tab:
            event.ignore()
            return
        super(MainWindow, self).keyPressEvent(event)

    def __init__(self):
        super(MainWindow, self).__init__()
        QtCore.QCoreApplication.setOrganizationName('Montreal Corpus Tools')
        QtCore.QCoreApplication.setApplicationName('Anchor')

        fonts = ['GentiumPlus', 'CharisSIL',
                 'NotoSans-Black', 'NotoSans-Bold', 'NotoSans-BoldItalic', 'NotoSans-Italic', 'NotoSans-Light',
                 'NotoSans-Medium', 'NotoSans-MediumItalic', 'NotoSans-Regular', 'NotoSans-Thin',
                 'NotoSerif-Black', 'NotoSerif-Bold', 'NotoSerif-BoldItalic', 'NotoSerif-Italic', 'NotoSerif-Light',
                 'NotoSerif-Medium', 'NotoSerif-MediumItalic', 'NotoSerif-Regular', 'NotoSerif-Thin'
                 ]
        for font in fonts:
            id = QtGui.QFontDatabase.addApplicationFont(f":fonts/{font}.ttf")
        if not os.path.exists(os.path.join(get_temporary_directory(), 'Anchor')):
            os.makedirs(os.path.join(get_temporary_directory(), 'Anchor'))
        self.config_path = os.path.join(get_temporary_directory(), 'Anchor', 'config.yaml')
        self.history_path = os.path.join(get_temporary_directory(), 'Anchor', 'search_history')
        self.corpus_history_path = os.path.join(get_temporary_directory(), 'Anchor', 'corpus_history')
        self.corpus = None
        self.corpus_model = CorpusModel()
        self.proxy_model = CorpusProxy(self.corpus_model)
        self.proxy_model.setSourceModel(self.corpus_model)
        self.selection_model = CorpusSelectionModel(self.proxy_model)
        self.selection_model.currentChanged.connect(self.change_utterance)
        self.corpus_model.fileSaveable.connect(self.setFileSaveable)
        self.current_corpus_path = None
        self.dictionary = None
        self.acoustic_model = None
        self.g2p_model = None
        self.language_model = None
        self.waiting_on_close = False
        self.media_player = MediaPlayer(self.corpus_model, self.selection_model)
        self.media_player.playbackStateChanged.connect(self.handleAudioState)

        self.status_bar = QtWidgets.QStatusBar()
        self.warning_label = WarningLabel('Warning: This is alpha '
                                              'software, there will be bugs and issues. Please back up any data before '
                                              'using.')
        self.status_label = QtWidgets.QLabel()
        self.status_bar.addPermanentWidget(self.warning_label, 1)
        self.status_bar.addPermanentWidget(self.status_label)
        self.setStatusBar(self.status_bar)

        self.list_widget = UtteranceListWidget(self)
        self.list_dock = DockWidget('Utterances')
        self.list_dock.setWidget(self.list_widget)
        self.detail_widget = UtteranceDetailWidget(self)
        self.media_player.timeChanged.connect(self.detail_widget.plot_widget.update_play_line)
        self.detail_widget.plot_widget.timeRequested.connect(self.media_player.setCurrentTime)
        self.detail_widget.text_widget.installEventFilter(self)
        self.dictionary_widget = DictionaryWidget(self)
        self.dictionary_dock = DockWidget('Dictionary')
        self.dictionary_dock.setWidget(self.dictionary_widget)

        self.speaker_widget = SpeakerWidget(self)
        self.speaker_dock = DockWidget('Speakers')
        self.speaker_dock.setWidget(self.speaker_widget)

        self.speaker_dock.visibilityChanged.connect(self.update_icons)

        self.loading_label = LoadingScreen(self)
        self.title_screen = TitleScreen(self)
        self.configUpdated.connect(self.detail_widget.update_config)
        self.configUpdated.connect(self.list_widget.update_config)
        self.configUpdated.connect(self.dictionary_widget.update_config)
        self.configUpdated.connect(self.speaker_widget.update_config)
        self.configUpdated.connect(self.loading_label.update_config)
        self.configUpdated.connect(self.title_screen.update_config)

        self.setDockOptions(self.DockOption.ForceTabbedDocks | self.DockOption.VerticalTabs)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, self.list_dock)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, self.dictionary_dock)
        self.tabifyDockWidget(self.list_dock, self.dictionary_dock)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, self.speaker_dock)
        self.tabifyDockWidget(self.list_dock, self.speaker_dock)

        self.settings = QtCore.QSettings()
        self.restoreGeometry(self.settings.value("MainWindow/geometry"))
        self.restoreState(self.settings.value("MainWindow/windowState"))

        self.create_actions()
        self.create_menus()
        self.setup_key_binds()
        self.load_config()
        self.load_search_history()
        self.load_corpus_history()
        self.configUpdated.connect(self.save_config)

        self.corpusLoaded.connect(self.detail_widget.update_corpus)
        self.corpusLoaded.connect(self.list_widget.update_corpus)
        self.dictionaryLoaded.connect(self.detail_widget.update_dictionary)

        self.dictionaryLoaded.connect(self.dictionary_widget.update_dictionary)
        self.g2pLoaded.connect(self.dictionary_widget.update_g2p)
        self.detail_widget.lookUpWord.connect(self.open_dictionary)
        self.detail_widget.createWord.connect(self.open_dictionary)
        self.detail_widget.lookUpWord.connect(self.dictionary_widget.look_up_word)
        self.detail_widget.createWord.connect(self.dictionary_widget.create_pronunciation)
        self.dictionary_widget.dictionaryError.connect(self.show_dictionary_error)
        self.dictionary_widget.dictionaryModified.connect(self.enable_dictionary_actions)
        self.newSpeaker.connect(self.change_speaker_act.widget.refresh_speaker_dropdown)
        self.newSpeaker.connect(self.speaker_widget.refresh_speakers)
        self.speaker_widget.speaker_edit.enableAddSpeaker.connect(self.enable_add_speaker)

        self.wrapper = QtWidgets.QWidget()
        self.wrapper.setContentsMargins(0,0,0,0)
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0,0,0,0)

        self.list_widget.setVisible(False)
        self.detail_widget.setVisible(False)
        self.loading_label.setVisible(False)
        self.title_screen.setVisible(True)
        #layout.addWidget(self.list_widget)
        layout.addWidget(self.detail_widget)
        layout.addWidget(self.loading_label)
        layout.addWidget(self.title_screen)

        self.wrapper.setLayout(layout)
        self.setCentralWidget(self.wrapper)
        self.default_directory = get_temporary_directory()

        icon = QtGui.QIcon()
        icon.addFile(':anchor-yellow.svg', mode=QtGui.QIcon.Normal, state=QtGui.QIcon.On)
        self.setWindowTitle("MFA Anchor")
        self.setWindowIcon(icon)
        self.setWindowIconText('Anchor')
        self.loading_corpus = False
        self.loading_dictionary = False
        self.loading_g2p = False
        self.loading_ie = False
        self.loading_am = False
        self.loading_lm = False
        self.saving_dictionary = False
        self.saving_utterance = False

        self.corpus_worker = ImportCorpusWorker()

        #self.corpus_worker.errorEncountered.connect(self.showError)
        self.corpus_worker.dataReady.connect(self.finalize_load_corpus)
        self.corpus_worker.finishedCancelling.connect(self.finish_cancelling)
        if self.config['autoload']:
            self.load_corpus()
        self.load_dictionary()
        self.load_g2p()
        self.load_ivector_extractor()
        self.previous_volume = 100

    def update_icons(self):
        dock_tab_bars = self.findChildren(QtWidgets.QTabBar, "")

        for j in range(len(dock_tab_bars)):
            dock_tab_bar = dock_tab_bars[j]
            if not dock_tab_bar.count():
                continue
            font = self.config.font_options
            dock_tab_bar.setFont(font['font'])
            for i in range(dock_tab_bar.count()):
                if dock_tab_bar.tabText(i) == 'Utterances':
                    dock_tab_bar.setTabIcon(i,create_icon('search'))
                elif dock_tab_bar.tabText(i) == 'Dictionary':
                    dock_tab_bar.setTabIcon(i,create_icon('book'))
                elif dock_tab_bar.tabText(i) == 'Speakers':
                    dock_tab_bar.setTabIcon(i,create_icon('speaker'))

    def handleAudioState(self, state):
        if state == QtMultimedia.QMediaPlayer.StoppedState:
            self.play_act.setChecked(False)

    def update_mute_status(self, is_muted):
        if is_muted:
            self.previous_volume = self.media_player.volume()
            self.change_volume_act.widget.setValue(0)
        else:
            self.change_volume_act.widget.setValue(self.previous_volume)
        self.media_player.setMuted(is_muted)

    def enable_add_speaker(self, b):
        self.add_new_speaker_act.setEnabled(b)

    def enable_dictionary_actions(self):
        self.save_dictionary_act.setEnabled(True)
        self.save_dictionary_act.setText('Save dictionary')
        self.reset_dictionary_act.setEnabled(True)

    def show_dictionary_error(self, message):
        reply = DetailedMessageBox()
        reply.setWindowTitle('Issue saving dictionary')
        self.setStandardButtons(QtWidgets.QMessageBox.Ignore|QtWidgets.QMessageBox.Close)
        reply.setText(message)
        ret = reply.exec_()
        if ret:
            self.dictionary_widget.ignore_errors = True
            self.save_dictionary_act.trigger()

    def eventFilter(self, object, event) -> bool:
        if event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Tab:
            self.play_act.trigger()
            return True
        return False

    def update_file_name(self, file_name):
        self.current_file = file_name
        self.detail_widget.update_file_name(file_name)
        self.set_current_utterance(None, False)
        self.setFileSaveable(False)

    def setFileSaveable(self, enable):
        self.save_current_file_act.setEnabled(enable)

    def restore_deleted_utts(self):
        self.corpus_model.restore_deleted_utts()

    def delete_utterances(self):
        utts = self.selection_model.selectedUtterances()
        self.corpus_model.delete_utterances(utts)

    def split_utterances(self):
        utts = self.selection_model.selectedUtterances()
        self.corpus_model.split_utterances(utts)


    def merge_utterances(self):
        utts = self.selection_model.selectedUtterances()
        self.corpus_model.merge_utterances(utts)

    def change_utterance(self):
        current_utterance = self.selection_model.currentUtterance()
        if current_utterance is None:
            self.change_speaker_act.setEnabled(False)
            self.delete_act.setEnabled(False)
            self.change_speaker_act.widget.setCurrentSpeaker('')
        else:
            self.change_speaker_act.setEnabled(True)
            self.change_speaker_act.widget.setCurrentSpeaker(current_utterance.speaker)
            self.delete_act.setEnabled(True)


    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        if self.loading_corpus:
            self.cancel_load_corpus_act.trigger()
            self.loading_label.setExiting()
            self.repaint()
            while self.loading_corpus:
                self.corpus_worker.wait(500)
                if self.corpus_worker.isFinished():
                    break
        self.config['volume'] = self.change_volume_act.widget.value()

        self.save_config()
        self.save_search_history()

        self.settings.setValue("MainWindow/geometry", self.saveGeometry())
        self.settings.setValue("MainWindow/windowState", self.saveState())
        self.settings.sync()
        if self.config['autosave']:
            print('Saving!')
            self.save_file()
        a0.accept()

    def load_config(self):
        self.config = ConfigurationOptions({})
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf8') as f:
                self.config.update(yaml.load(f, Loader=yaml.SafeLoader))


        os.makedirs(self.config['temp_directory'], exist_ok=True)
        self.refresh_fonts()
        self.refresh_shortcuts()
        self.refresh_style_sheets()
        self.configUpdated.emit(self.config)

    def update_speaker(self):
        old_utterance = self.selection_model.currentUtterance()
        speaker = self.change_speaker_act.widget.current_speaker
        self.corpus_model.update_utterance(old_utterance, speaker=speaker)

    def refresh_fonts(self):
        base_font = self.config.font_options['font']
        small_font = self.config.font_options['small_font']
        self.menuBar().setFont(base_font)
        self.list_dock.setFont(base_font)
        self.speaker_dock.setFont(base_font)
        self.dictionary_dock.setFont(base_font)
        self.corpus_menu.setFont(base_font)
        for a in self.corpus_menu.actions():
            a.setFont(base_font)
        self.dictionary_menu.setFont(base_font)
        for a in self.dictionary_menu.actions():
            a.setFont(base_font)
        self.acoustic_model_menu.setFont(base_font)
        for a in self.acoustic_model_menu.actions():
            a.setFont(base_font)
        self.g2p_model_menu.setFont(base_font)
        for a in self.g2p_model_menu.actions():
            a.setFont(base_font)
        self.status_bar.setFont(base_font)
        self.warning_label.setFont(base_font)

        icon_ratio = 0.03
        icon_height = int(icon_ratio*self.config['height'])
        if icon_height < 24:
            icon_height = 24

        for a in self.actions():
            if isinstance(a, AnchorAction):
                a.widget.setFont(small_font)
                a.widget.setFixedHeight(icon_height+8)

            else:
                a.setFont(small_font)

        icon_height = self.menuBar().fontMetrics().height()
        self.corner_tool_bar.setIconSize(QtCore.QSize(icon_height, icon_height))

    def save_search_history(self):
        with open(self.history_path, 'w', encoding='utf8') as f:
            for query in self.list_widget.search_box.history:
                f.write(f"{query[0]}\t{query[1]}\t{query[2]}\n")

    def save_corpus_history(self):
        with open(self.corpus_history_path, 'w', encoding='utf8') as f:
            for path in self.corpus_history:
                f.write(f"{path}\n")

    def load_search_history(self):
        history = []
        if os.path.exists(self.history_path):
            with open(self.history_path, 'r', encoding='utf8') as f:
                for line in f:
                    line = line.strip().split()
                    if not line:
                        continue
                    line[1] = line[1].lower() != 'false'
                    line[2] = line[2].lower() != 'false'
                    line = tuple(line)
                    if line not in history:
                        history.append(line)
        self.list_widget.load_history(history)

    def load_corpus_history(self):
        self.corpus_history = []
        if os.path.exists(self.corpus_history_path):
            with open(self.corpus_history_path, 'r', encoding='utf8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if line not in self.corpus_history:
                        self.corpus_history.append(line)
        self.refresh_corpus_history()

    def refresh_corpus_history(self):
        self.open_recent_menu.clear()
        if not self.corpus_history or self.corpus_history[0] != self.current_corpus_path:
            self.corpus_history.insert(0, self.current_corpus_path)
        for i, corpus in enumerate(self.corpus_history):
            if corpus == self.current_corpus_path:
                continue
            history_action = QtGui.QAction(parent=self, text=os.path.basename(corpus),
                                               triggered=lambda: self.load_corpus_path(corpus))
            self.open_recent_menu.addAction(history_action)
            if i == 6:
                break
        if len(self.corpus_history) <= 1:
            self.open_recent_menu.setEnabled(False)
        else:
            self.open_recent_menu.setEnabled(True)
        self.corpus_history = self.corpus_history[:6]

    def save_config(self):
        self.refresh_fonts()
        self.refresh_shortcuts()
        self.refresh_style_sheets()
        with open(self.config_path, 'w', encoding='utf8') as f:
            to_output = {}
            for k, v in self.config.items():
                to_output[k] = v
            yaml.dump(to_output, f)

    def open_options(self):
        dialog = OptionsDialog(self)
        if dialog.exec_():
            self.config.update(dialog.generate_config())
            self.refresh_shortcuts()
            self.refresh_style_sheets()
            self.configUpdated.emit(self.config)

    def refresh_style_sheets(self):
        colors = self.config.color_options
        background_color = colors['background_color']

        selection_color = colors['selection_color']
        error_color = colors['error_color']
        error_background_color = colors['error_background_color']

        text_edit_color = colors['text_edit_color']
        text_edit_background_color = colors['text_edit_background_color']
        line_edit_color = colors['line_edit_color']
        line_edit_background_color = colors['line_edit_background_color']

        enabled_color = colors['enabled_color']
        enabled_background_color = colors['enabled_background_color']
        enabled_border_color = colors['enabled_border_color']

        active_color = colors['active_color']
        active_background_color = colors['active_background_color']
        active_border_color = colors['active_border_color']

        hover_text_color = colors['hover_text_color']
        hover_background_color = colors['hover_background_color']
        hover_border_color = colors['hover_border_color']

        disabled_text_color = colors['disabled_text_color']
        disabled_background_color = colors['disabled_background_color']
        disabled_border_color = colors['disabled_border_color']

        table_text_color = colors['table_text_color']
        table_odd_color = colors['table_odd_color']
        table_even_color = colors['table_even_color']
        table_header_background_color = colors['table_header_background_color']

        table_header_color = colors['table_header_color']

        main_widget_border_color = colors['main_widget_border_color']
        main_widget_background_color = colors['main_widget_background_color']
        menu_background_color = colors['menu_background_color']
        menu_text_color = colors['menu_text_color']

        scroll_bar_background_color = colors['scroll_bar_background_color']
        scroll_bar_handle_color = colors['scroll_bar_handle_color']
        scroll_bar_border_color = colors['scroll_bar_border_color']
        border_radius = 5
        text_padding = 5
        border_width = 2
        base_menu_button_width = 16
        menu_button_width = base_menu_button_width + border_width * 2

        sort_indicator_size = 20
        sort_indicator_padding = 15
        scroll_bar_height = 25
        scroll_bar_border_radius = int(scroll_bar_height / 2) -2
        sheet = f'''
        QMainWindow, QDialog{{
            background-color: {background_color};
        }}
        QMenuBar {{
            background-color: {menu_background_color};
            spacing: 2px;
        }}
        QMenuBar::item {{
            padding: 4px 4px;
                        color: {menu_text_color};
                        background-color: {menu_background_color};
        }}
        QMenuBar::item:selected {{
                        color: {hover_text_color};
                        background-color: {hover_background_color};
        }}
        QMenuBar::item:disabled {{
                        color: {disabled_text_color};
                        background-color: {menu_background_color};
                        }}
        ButtonWidget {{
            background-color: {table_header_background_color};
        }}
        QDockWidget {{
            background-color: {active_background_color};
            color: {active_color};
            
            titlebar-close-icon: url(:checked/times.svg);
            titlebar-normal-icon: url(:checked/external-link.svg);
        }}
        QDockWidget::title {{
            text-align: center;
        }}
        
        QMainWindow::separator {{
    background: {background_color};
    width: 10px; /* when vertical */
    height: 10px; /* when horizontal */
}}

QMainWindow::separator:hover {{
    background: {enabled_background_color};
}}
        UtteranceListWidget {{
            background-color: {text_edit_background_color};
        
            border: {border_width}px solid {main_widget_border_color};
            color: {main_widget_border_color};
            padding: 0px;
            padding-top: 20px;
            margin-top: 0ex; /* leave space at the top for the title */
            }}
            
        UtteranceDetailWidget {{
            padding: 0px;
            border: none;
            margin: 0;
        }}
        InformationWidget {{
            background-color: {main_widget_background_color};
            border: {border_width}px solid {main_widget_border_color};
            border-top-right-radius: {border_radius}px;
            border-bottom-right-radius: {border_radius}px;
                    
        }}
        QTabWidget::pane, SearchWidget, DictionaryWidget, SpeakerWidget {{
        
            border-bottom-right-radius: {border_radius}px;
                    
        }}
        
        QGroupBox::title {{
            color: {text_edit_color};
            background-color: transparent;
            subcontrol-origin: margin;
            subcontrol-position: top center; /* position at the top center */
            padding-top: 5px;
        }}
        QLabel {{
                        color: {text_edit_color};
            }}
        QStatusBar {{
            background-color: {text_edit_background_color};
                        color: {text_edit_color};
            }}
        WarningLabel {{
                        color: {error_color};
            }}
        QCheckBox {{
            color: {text_edit_color};
        }}
        QTabWidget::pane, SearchWidget, DictionaryWidget, SpeakerWidget {{ /* The tab widget frame */
            background-color: {main_widget_background_color};
        
        }}
        QTabWidget::pane  {{ /* The tab widget frame */
            border: {border_width}px solid {main_widget_border_color};
            border-top-color: {enabled_color};
            background-color: {main_widget_background_color};
        
        }}
            
            
        QTabBar::tab {{
            color: {menu_text_color};
            background-color: {menu_background_color};
            border-color: {enabled_border_color};
            border: {border_width / 2}px solid {enabled_border_color};
            border-top-color: {main_widget_border_color};
            border-bottom: none;
            
            min-width: 8ex;
            padding: {text_padding}px;
            margin: 0px;
        }}
            
        QTabBar::scroller{{
            width: {2*scroll_bar_height}px;
        }}
        QTabBar QToolButton  {{
            border-radius: 0px;
        }}
        
        QTabBar QToolButton::right-arrow  {{
            image: url(:caret-right.svg);
            height: {scroll_bar_height}px;
            width: {scroll_bar_height}px;
        }}
        QTabBar QToolButton::right-arrow :pressed {{
            image: url(:checked/caret-right.svg);
        }}
        QTabBar QToolButton::right-arrow :disabled {{
            image: url(:disabled/caret-right.svg);
        }}
        
        QTabBar QToolButton::left-arrow  {{
            image: url(:caret-left.svg);
            height: {scroll_bar_height}px;
            width: {scroll_bar_height}px;
        }}
        QTabBar QToolButton::left-arrow:pressed {{
            image: url(:checked/caret-left.svg);
        }}
        QTabBar QToolButton::left-arrow:disabled {{
            image: url(:disabled/caret-left.svg);
        }}
        
        QTabBar::tab-bar {{
            color: {menu_text_color};
            background-color: {menu_background_color};
            border: {border_width}px solid {main_widget_border_color};
        }}
            
        QTabBar::tab:hover {{
            color: {hover_text_color};
            background-color: {hover_background_color};
            border-color: {hover_border_color};
            border-bottom-color:  {active_border_color};
        }}
        QTabBar::tab:selected {{
            color: {active_color};
            background-color: {active_background_color};
            margin-left: -{border_width}px;
            margin-right: -{border_width}px;
            border-color: {active_border_color};
            border-bottom-color:  {active_border_color};
        }}
        QTabBar::tab:first {{
            border-left-width: {border_width}px;
            margin-left: 0px;
        }}
        QTabBar::tab:last {{
            border-right-width: {border_width}px;
            margin-right: 0px;
        }}
        QToolBar {{
            spacing: 3px; 
        }}
            
        QToolBar::separator {{
            margin-left: 5px;
            margin-right: 5px;
            width: 3px;
            height: 3px;
            background: {selection_color};
        }}
            
        
            
        QPushButton, QToolButton {{
            background-color: {enabled_background_color};
            color: {enabled_color};
            padding: {text_padding}px;
            border-width: {border_width}px; 
            border-style: solid; 
            border-color: {enabled_border_color};
            border-radius: {border_radius}px;
        }}
        QToolButton[popupMode="1"] {{ /* only for MenuButtonPopup */
            padding-right: {menu_button_width}px; /* make way for the popup button */
        }}
        QToolButton::menu-button {{
            border: {border_width}px solid {enabled_border_color};
            border-top-right-radius: {border_radius}px;
            border-bottom-right-radius: {border_radius}px;
            
            width: {base_menu_button_width}px;
        }}
        QMenuBar QToolButton{{
            padding: 0px;
        }}
        QLineEdit QToolButton {{
                        background-color: {text_edit_background_color};
                        color: {text_edit_color};
                        border: none;
        }}
        QToolButton#clear_search_field, QToolButton#clear_new_speaker_field, 
        QToolButton#regex_search_field, QToolButton#word_search_field {{
                        background-color: none;
                        border: none;
                        padding: {border_width}px;
        }}
        QMenu {{
                margin: 2px;
                background-color: {menu_background_color};
                color: {menu_text_color};
        }}
        QMenu::item {{
                padding: 2px 25px 2px 20px;
                border: {border_width /2}px solid transparent;
                background-color: {menu_background_color};
                color: {menu_text_color};
        }}
        QMenu::item:disabled {{
                border: none;
                background-color: {disabled_background_color};
                color: {disabled_text_color};
        }}
        QMenu::item:!disabled:selected {{
            border-color: {enabled_color};
            background-color: {selection_color};
        }}
        QComboBox {{
            color: {enabled_color};
            background-color: {enabled_background_color};
            selection-background-color: none;
        }}
        QComboBox QAbstractItemView {{
            color: {enabled_color};
            background-color: {enabled_background_color};
            selection-background-color: {hover_background_color};
        }}
        QToolButton:checked  {{
            color: {active_color};
            background-color: {active_background_color};
            border-color: {active_border_color};
        }}
        QPushButton:disabled, QToolButton:disabled {{
            color: {disabled_text_color};
            background-color: {disabled_background_color};
            border-color: {disabled_border_color};
        }}
        
        QToolButton#cancel_load:disabled {{
            color: {disabled_text_color};
            background-color: {disabled_background_color};
            border-color: {disabled_border_color};
        }}
        QPushButton:hover, QToolButton:hover, QToolButton:focus, QToolButton:pressed, ToolButton:hover {{
            color: {hover_text_color};
            background-color: {hover_background_color};
            border-color: {hover_border_color};
        }}
        
        QToolButton#cancel_load:focus:hover {{
            color: {hover_text_color};
            background-color: {hover_background_color};
            border-color: {hover_border_color};
        }}
        QTextEdit {{
            color: {text_edit_color};
            background-color: {text_edit_background_color};
            border: {border_width}px solid {main_widget_border_color};
            selection-background-color: {selection_color};
        }}
        QGraphicsView {{
            border: {border_width}px solid {main_widget_border_color};
        }}
         QLineEdit {{
            color: {line_edit_color};
            background-color: {line_edit_background_color};
            selection-background-color: {selection_color};
        }}
        QSlider::handle:horizontal {{
            height: 10px;
            background: {enabled_background_color};
            border: {border_width/2}px solid {enabled_border_color};
            margin: 0 -2px; /* expand outside the groove */
        }}
        QSlider::handle:horizontal:hover {{
            height: 10px;
            background: {hover_background_color};
            border-color: {hover_border_color};
            margin: 0 -2px; /* expand outside the groove */
        }}
        QTableWidget, QTableView {{
            alternate-background-color: {table_even_color}; 
            selection-background-color: {selection_color};
            selection-color: {text_edit_color};
            background-color: {table_odd_color};
            color: {table_text_color};
            border: 4px solid {enabled_color};
        }}
        QScrollArea {{
            border: 4px solid {enabled_color};
        }}
        QHeaderView::up-arrow {{
            subcontrol-origin: padding; 
            subcontrol-position: center right;
            image: url(:hover/sort-up.svg);
            height: {sort_indicator_size}px;
            width: {sort_indicator_size}px;
        }}
        QHeaderView::down-arrow {{
            image: url(:hover/sort-down.svg);
            subcontrol-origin: padding; 
            subcontrol-position: center right;
            height: {sort_indicator_size}px;
            width: {sort_indicator_size}px;
        }}
        QTableView QTableCornerButton::section {{
            background-color: {enabled_background_color};
        }}
        QHeaderView {{
            background-color: {table_odd_color};
        }}
        QHeaderView::section {{
            color: {table_header_color};
            background-color: {table_header_background_color};
            padding-left: {text_padding}px;
        }}
        QHeaderView::section:horizontal {{
            padding-right: {sort_indicator_padding}px;
        }}
        '''

        scroll_bar_style = f'''
        QScrollBar {{
            color: {scroll_bar_handle_color};
            background: {scroll_bar_background_color};
            border: {border_width}px solid {scroll_bar_border_color};
        }}
        QScrollBar#time_scroll_bar {{
            color: {scroll_bar_handle_color};
            background: {scroll_bar_background_color};
            border: {border_width}px solid {scroll_bar_border_color};
            margin-left: 0px;
            margin-right: 0px;
        }}
        QScrollBar:horizontal {{
            height: {scroll_bar_height}px;
            border: 2px solid {scroll_bar_border_color};
            border-radius: {scroll_bar_border_radius+2}px;
            margin-left: {scroll_bar_height}px;
            margin-right: {scroll_bar_height}px;
        }}
        QScrollBar:vertical {{
            width: {scroll_bar_height}px;
            border: 2px solid {scroll_bar_border_color};
            border-radius: {scroll_bar_border_radius+2}px;
            margin-top: {scroll_bar_height}px;
            margin-bottom: {scroll_bar_height}px;
        }}
        
        QScrollBar:left-arrow:horizontal {{
            image: url(:caret-left.svg);
            height: {scroll_bar_height}px;
            width: {scroll_bar_height}px;
        }}
        QScrollBar:left-arrow:horizontal:pressed {{
            image: url(:checked/caret-left.svg);
        }}
        
        QScrollBar:right-arrow:horizontal {{
            image: url(:caret-right.svg);
            height: {scroll_bar_height}px;
            width: {scroll_bar_height}px;
        }}
        QScrollBar:right-arrow:horizontal:pressed {{
            image: url(:checked/caret-right.svg);
        }}
        
        QScrollBar:up-arrow:vertical {{
            image: url(:caret-up.svg);
            height: {scroll_bar_height}px;
            width: {scroll_bar_height}px;
        }}
        QScrollBar:up-arrow:vertical:pressed {{
            image: url(:checked/caret-up.svg);
        }}
        
        QScrollBar:down-arrow:vertical {{
            image: url(:caret-down.svg);
            height: {scroll_bar_height}px;
            width: {scroll_bar_height}px;
        }}
        QScrollBar:down-arrow:vertical:pressed {{
            image: url(:checked/caret-down.svg);
        }}
        
        QScrollBar::handle:horizontal {{
            background: {scroll_bar_handle_color};
            min-width: {scroll_bar_height}px;
            border: 2px solid {scroll_bar_border_color};
            border-radius: {scroll_bar_border_radius}px;
        }}
        
        QScrollBar::handle:vertical {{
            background: {scroll_bar_handle_color};
            min-height: {scroll_bar_height}px;
            border: 2px solid {scroll_bar_border_color};
            border-radius: {scroll_bar_border_radius}px;
        }}
        
        QToolButton#pan_left_button, QToolButton#pan_right_button {{
            
            color: none;
            background-color: none;
            border: none;
            margin: 0px;
            padding: 0px;
        }}
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: none;
            height: {scroll_bar_height}px;
            width: {scroll_bar_height}px;
            padding: 0px;
            margin: 0px;
        }}
        
        QScrollBar::add-line:horizontal {{
            background: none;
            subcontrol-position: right;
            subcontrol-origin: margin;
            width: {scroll_bar_height}px;
        }}
        
        QScrollBar::sub-line:horizontal {{
            background: none;
            subcontrol-position: left;
            subcontrol-origin: margin;
            width: {scroll_bar_height}px;
        }}
        
        QScrollBar::add-line:vertical {{
            background: none;
            subcontrol-position: bottom;
            subcontrol-origin: margin;
            height: {scroll_bar_height}px;
        }}
        
        QScrollBar::sub-line:vertical {{
            background: none;
            subcontrol-position: top;
            subcontrol-origin: margin;
            height: {scroll_bar_height}px;
        }}
        
        QScrollBar#time_scroll_bar::add-line:horizontal {{
            background: none;
            subcontrol-position: none;
            subcontrol-origin: none;
            width: 0px;
        }}
        
        QScrollBar#time_scroll_bar::sub-line:horizontal {{
            background: none;
            subcontrol-position: none;
            subcontrol-origin: none;
            width: 0px;
        }}
        '''
        if 'praat' not in self.config['theme'].lower():
            sheet += scroll_bar_style
        else:
            sheet += f'''
        QToolButton#pan_left_button, QToolButton#pan_right_button {{
            width: 0;
            height: 0;
            color: none;
            background-color: none;
            border: none;
            margin: 0px;
            padding: 0px;
        }}'''

        self.setStyleSheet(sheet)

    def create_actions(self):
        self.change_temp_dir_act = QtGui.QAction(
            parent=self, text="Change temporary directory",
            statusTip="Change temporary directory", triggered=self.change_temp_dir)

        self.options_act = DefaultAction('cog',
            parent=self, text="Preferences...",
            statusTip="Edit preferences", triggered=self.open_options)

        self.load_corpus_act = DefaultAction('folder-open',
            parent=self, text="Load a corpus",
            statusTip="Load a corpus", triggered=self.change_corpus)

        self.cancel_load_corpus_act = DefaultAction('clear',
            parent=self, text="Cancel loading current corpus",
            statusTip="Cancel loading current corpus", triggered=self.cancel_corpus_load)

        self.loading_label.tool_bar.addAction(self.cancel_load_corpus_act)
        w = self.loading_label.tool_bar.widgetForAction(self.cancel_load_corpus_act)
        w.setObjectName('cancel_load')

        self.close_corpus_act = QtGui.QAction(
            parent=self, text="Close current corpus",
            statusTip="Load current corpus", triggered=self.close_corpus)

        self.load_acoustic_model_act = QtGui.QAction(
            parent=self, text="Load an acoustic model",
            statusTip="Load an acoustic model", triggered=self.change_acoustic_model)

        self.load_dictionary_act = QtGui.QAction(
            parent=self, text="Load a dictionary",
            statusTip="Load a dictionary", triggered=self.change_dictionary)

        self.load_g2p_act = QtGui.QAction(
            parent=self, text="Load a G2P model",
            statusTip="Load a G2P model", triggered=self.change_g2p)

        self.load_lm_act = QtGui.QAction(
            parent=self, text="Load a language model",
            statusTip="Load a language model", triggered=self.change_lm)

        self.load_ivector_extractor_act = QtGui.QAction(
            parent=self, text="Load an ivector extractor",
            statusTip="Load an ivector extractor", triggered=self.change_ivector_extractor)

        self.undo_act = self.corpus_model.undo_stack.createUndoAction(self, 'Undo')

        self.redo_act = self.corpus_model.undo_stack.createRedoAction(self, 'Redo')

        self.addAction(self.change_temp_dir_act)
        self.addAction(self.options_act)
        self.addAction(self.load_corpus_act)
        self.addAction(self.close_corpus_act)
        self.addAction(self.cancel_load_corpus_act)
        self.addAction(self.load_acoustic_model_act)
        self.addAction(self.load_dictionary_act)
        self.addAction(self.load_g2p_act)
        self.addAction(self.load_lm_act)
        self.addAction(self.load_ivector_extractor_act)

    def set_application_state(self, state):
        if state == 'loading':
            self.list_widget.setVisible(False)
            self.list_dock.setVisible(False)
            self.dictionary_dock.setVisible(False)
            self.dictionary_widget.setVisible(False)
            self.speaker_dock.setVisible(False)
            self.speaker_widget.setVisible(False)

            self.detail_widget.setVisible(False)
            self.title_screen.setVisible(False)
            self.loading_label.setVisible(True)

            self.change_temp_dir_act.setEnabled(False)
            self.options_act.setEnabled(True)
            self.cancel_load_corpus_act.setEnabled(True)
            self.load_corpus_act.setEnabled(False)
            self.open_recent_menu.setEnabled(False)
            self.close_corpus_act.setEnabled(False)
            self.load_acoustic_model_act.setEnabled(False)
            self.load_dictionary_act.setEnabled(False)
            self.load_g2p_act.setEnabled(False)
            self.load_lm_act.setEnabled(False)
            self.load_ivector_extractor_act.setEnabled(False)
        elif state == 'loaded':
            self.loading_label.setVisible(False)

            self.list_widget.setVisible(True)
            self.dictionary_widget.setVisible(True)
            self.speaker_widget.setVisible(True)
            self.list_dock.setVisible(True)
            self.dictionary_dock.setVisible(True)
            self.speaker_dock.setVisible(True)


            self.detail_widget.setVisible(True)
            self.title_screen.setVisible(False)

            self.change_temp_dir_act.setEnabled(True)
            self.options_act.setEnabled(True)
            self.cancel_load_corpus_act.setEnabled(False)
            self.load_corpus_act.setEnabled(True)
            self.open_recent_menu.setEnabled(True)
            self.close_corpus_act.setEnabled(True)
            self.load_acoustic_model_act.setEnabled(True)
            self.load_dictionary_act.setEnabled(True)
            self.load_g2p_act.setEnabled(True)
            self.load_lm_act.setEnabled(True)
            self.load_ivector_extractor_act.setEnabled(True)
            self.update_icons()
        elif state == 'unloaded':
            self.loading_label.setVisible(False)
            self.list_widget.setVisible(False)
            self.list_dock.setVisible(False)
            self.dictionary_dock.setVisible(False)
            self.dictionary_widget.setVisible(False)
            self.speaker_dock.setVisible(False)
            self.speaker_widget.setVisible(False)
            self.detail_widget.setVisible(False)
            self.title_screen.setVisible(True)

            self.change_temp_dir_act.setEnabled(True)
            self.options_act.setEnabled(True)
            self.cancel_load_corpus_act.setEnabled(False)
            self.load_corpus_act.setEnabled(True)
            self.open_recent_menu.setEnabled(True)
            self.close_corpus_act.setEnabled(False)
            self.load_acoustic_model_act.setEnabled(True)
            self.load_dictionary_act.setEnabled(True)
            self.load_g2p_act.setEnabled(True)
            self.load_lm_act.setEnabled(True)
            self.load_ivector_extractor_act.setEnabled(True)

    def play_audio(self):
        if self.media_player.state() in [QtMultimedia.QMediaPlayer.StoppedState,
                                          QtMultimedia.QMediaPlayer.PausedState]:
            self.media_player.play()
        elif self.media_player.state() == QtMultimedia.QMediaPlayer.PlayingState:
            self.media_player.pause()

    def setup_key_binds(self):

        self.play_act = DefaultAction('play', checkable=True,
            parent=self, text="Play audio",
            statusTip="Play current loaded file", triggered=self.play_audio)


        self.zoom_in_act = DefaultAction('search-plus',
            parent=self, text="Zoom in",
            statusTip="Zoom in", triggered=self.selection_model.zoom_in)

        self.zoom_out_act = DefaultAction('search-minus',
            parent=self, text="Zoom out",
            statusTip="Zoom out", triggered=self.selection_model.zoom_out)

        self.pan_left_act = DefaultAction('caret-left', buttonless=True,
            parent=self, text="Pan left",
            statusTip="Pan left", triggered=self.detail_widget.pan_left)

        self.pan_right_act = DefaultAction('caret-right', buttonless=True,
            parent=self, text="Pan right",
            statusTip="Pan right", triggered=self.detail_widget.pan_right)

        self.merge_act = DefaultAction('compress',
            parent=self, text="Merge utterances",
            statusTip="Merge utterances", triggered=self.merge_utterances)

        self.split_act = DefaultAction('expand',
            parent=self, text="Split utterances",
            statusTip="Split utterances", triggered=self.split_utterances)

        self.search_act = DefaultAction('search',
            parent=self, text="Search corpus",
            statusTip="Search corpus", triggered=self.open_search)

        self.delete_act = DefaultAction(icon_name='trash',
            parent=self, text="Delete utterances",
            statusTip="Delete utterances", triggered=self.delete_utterances)

        self.save_act = DefaultAction('save',
            parent=self, text="Save file",
            statusTip="Save a current file", triggered=self.save_file)

        self.show_all_speakers_act = DefaultAction('users', checkable=True,
            parent=self, text="Show all speakers",
            statusTip="Show all speakers", triggered=self.detail_widget.plot_widget.update_show_speakers)

        self.mute_act = DefaultAction('volume-up', checkable=True,
            parent=self, text="Mute",
            statusTip="Mute", triggered=self.update_mute_status)

        self.change_volume_act = AnchorAction('volume',
            parent=self, text="Adjust volume",
            statusTip="Adjust volume")
        self.change_volume_act.widget.valueChanged.connect(self.media_player.set_volume)

        self.change_speaker_act = AnchorAction('speaker',
            parent=self, text="Change utterance speaker",
            statusTip="Change utterance speaker", triggered=self.update_speaker)

        self.save_current_file_act = DefaultAction('save',
            parent=self, text="Save file",
            statusTip="Save file", triggered=self.save_file)
        self.save_current_file_act.setDisabled(True)

        self.revert_changes_act = DefaultAction('undo',
            parent=self, text="Undo changes",
            statusTip="Undo changes", triggered=self.restore_deleted_utts)
        self.revert_changes_act.setDisabled(True)
        self.corpus_model.undoAvailable.connect(self.revert_changes_act.setEnabled)

        self.add_new_speaker_act = DefaultAction('user-plus',
            parent=self, text="Add new speaker",
            statusTip="Add new speaker", triggered=self.add_new_speaker)
        self.add_new_speaker_act.setEnabled(False)

        self.save_dictionary_act = DefaultAction('book-save',
            parent=self, text="Save dictionary",
            statusTip="Save dictionary", triggered=self.save_dictionary)
        self.save_dictionary_act.setEnabled(False)

        self.reset_dictionary_act = DefaultAction('book-undo',
            parent=self, text="Revert changes",
            statusTip="Revert changes", triggered=self.load_dictionary)
        self.reset_dictionary_act.setEnabled(False)

        self.change_speaker_act.setEnabled(False)
        self.addAction(self.play_act)
        self.addAction(self.zoom_in_act)
        self.addAction(self.zoom_out_act)
        self.addAction(self.pan_left_act)
        self.addAction(self.pan_right_act)
        self.addAction(self.merge_act)
        self.addAction(self.split_act)
        self.addAction(self.delete_act)
        self.addAction(self.save_act)
        self.addAction(self.show_all_speakers_act)
        self.addAction(self.mute_act)
        self.addAction(self.change_volume_act)
        self.addAction(self.change_speaker_act)
        self.addAction(self.add_new_speaker_act)
        self.addAction(self.save_current_file_act)
        self.addAction(self.save_dictionary_act)
        self.addAction(self.reset_dictionary_act)
        self.addAction(self.search_act)
        self.speaker_widget.tool_bar.addAction(self.add_new_speaker_act)
        self.speaker_widget.speaker_edit.returnPressed.connect(self.add_new_speaker_act.trigger)

        self.list_widget.tool_bar.addAction(self.save_current_file_act)
        self.list_widget.tool_bar.addSeparator()
        self.list_widget.tool_bar.addAction(self.revert_changes_act)

        self.detail_widget.tool_bar.addAction(self.play_act)
        self.detail_widget.tool_bar.addSeparator()
        self.detail_widget.tool_bar.addAction(self.mute_act)
        self.detail_widget.tool_bar.addWidget(self.change_volume_act.widget)
        self.detail_widget.tool_bar.addSeparator()
        self.detail_widget.tool_bar.addAction(self.show_all_speakers_act)
        self.detail_widget.tool_bar.addWidget(self.change_speaker_act.widget)
        self.detail_widget.tool_bar.addSeparator()
        self.detail_widget.tool_bar.addAction(self.zoom_in_act)
        self.detail_widget.tool_bar.addAction(self.zoom_out_act)

        self.detail_widget.pan_left_button.setDefaultAction(self.pan_left_act)
        self.detail_widget.pan_right_button.setDefaultAction(self.pan_right_act)

        self.detail_widget.tool_bar.addSeparator()
        self.detail_widget.tool_bar.addAction(self.merge_act)
        self.detail_widget.tool_bar.addAction(self.split_act)

        self.detail_widget.tool_bar.addAction(self.delete_act)
        w = self.detail_widget.tool_bar.widgetForAction(self.delete_act)
        w.setObjectName('delete_utterance')

        self.dictionary_widget.tool_bar.addAction(self.save_dictionary_act)
        self.dictionary_widget.tool_bar.addSeparator()
        self.dictionary_widget.tool_bar.addAction(self.reset_dictionary_act)

    def report_bug(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl('https://github.com/MontrealCorpusTools/Anchor-annotator/issues'))

    def open_help(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl('https://anchor-annotator.readthedocs.io/en/latest/'))

    def add_new_speaker(self):
        new_speaker = self.speaker_widget.speaker_edit.text()
        if new_speaker in self.corpus.speak_utt_mapping:
            return
        if not new_speaker:
            return
        self.corpus.speak_utt_mapping[new_speaker] = []
        self.newSpeaker.emit(self.corpus.speakers)
        self.speaker_widget.speaker_edit.clear()



    def open_search(self):

        dock_tab_bars = self.findChildren(QtWidgets.QTabBar, "")

        for j in range(len(dock_tab_bars)):
            dock_tab_bar = dock_tab_bars[j]
            if not dock_tab_bar.count():
                continue
            for i in range(dock_tab_bar.count()):
                if dock_tab_bar.tabText(i) == 'Utterances':
                    dock_tab_bar.setCurrentIndex(i)
                    break
            else:
                self.list_dock.toggleViewAction().trigger()
            self.list_widget.search_widget.search_box.setFocus()

    def open_dictionary(self):

        dock_tab_bars = self.findChildren(QtWidgets.QTabBar, "")

        for j in range(len(dock_tab_bars)):
            dock_tab_bar = dock_tab_bars[j]
            if not dock_tab_bar.count():
                continue
            for i in range(dock_tab_bar.count()):
                if dock_tab_bar.tabText(i) == 'Dictionary':
                    dock_tab_bar.setCurrentIndex(i)
                    break
            else:
                self.dictionary_dock.toggleViewAction().trigger()

    def refresh_shortcuts(self):
        self.play_act.setShortcut(QtGui.QKeySequence(self.config['play_keybind']))
        self.zoom_in_act.setShortcut(QtGui.QKeySequence(self.config['zoom_in_keybind']))
        self.zoom_out_act.setShortcut(QtGui.QKeySequence(self.config['zoom_out_keybind']))
        self.pan_left_act.setShortcut(QtGui.QKeySequence(self.config['pan_left_keybind']))
        self.pan_right_act.setShortcut(QtGui.QKeySequence(self.config['pan_right_keybind']))
        self.merge_act.setShortcut(QtGui.QKeySequence(self.config['merge_keybind']))
        self.split_act.setShortcut(QtGui.QKeySequence(self.config['split_keybind']))
        self.delete_act.setShortcut(QtGui.QKeySequence(self.config['delete_keybind']))
        self.save_act.setShortcut(QtGui.QKeySequence(self.config['save_keybind']))
        self.search_act.setShortcut(QtGui.QKeySequence(self.config['search_keybind']))
        self.undo_act.setShortcut(QtGui.QKeySequence(self.config['undo_keybind']))
        self.redo_act.setShortcut(QtGui.QKeySequence(self.config['redo_keybind']))
        self.change_volume_act.widget.setValue(self.config['volume'])

        for a in self.actions():
            if isinstance(a, (DefaultAction, AnchorAction)):
                a.update_icons(self.config.is_mfa)

    def create_menus(self):
        self.corpus_menu = self.menuBar().addMenu("Corpus")
        self.corpus_menu.addAction(self.load_corpus_act)
        self.open_recent_menu = self.corpus_menu.addMenu("Load recent corpus")

        self.corpus_menu.addAction(self.close_corpus_act)

        self.file_menu = self.menuBar().addMenu("Edit")
        self.file_menu.addAction(self.undo_act)
        self.file_menu.addAction(self.redo_act)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.change_temp_dir_act)
        self.file_menu.addAction(self.options_act)
        self.dictionary_menu = self.menuBar().addMenu("Dictionary")
        self.dictionary_menu.addAction(self.load_dictionary_act)
        downloaded_dictionaries_models = self.dictionary_menu.addMenu("Downloaded dictionary")
        for lang in DictionaryModel.get_available_models():
            lang_action = QtGui.QAction(parent=self, text=lang)
            lang_action.triggered.connect(lambda: self.change_dictionary(lang))
            downloaded_dictionaries_models.addAction(lang_action)
        self.acoustic_model_menu = self.menuBar().addMenu("Acoustic model")
        self.acoustic_model_menu.addAction(self.load_acoustic_model_act)
        downloaded_acoustic_models = self.acoustic_model_menu.addMenu("MFA acoustic model")
        for lang in AcousticModel.get_available_models():
            lang_action = QtGui.QAction(parent=self, text=lang)
            lang_action.triggered.connect(lambda: self.change_acoustic_model(lang))
            downloaded_acoustic_models.addAction(lang_action)

        self.g2p_model_menu = self.menuBar().addMenu("G2P model")
        self.g2p_model_menu.addAction(self.load_g2p_act)
        downloaded_g2p_models = self.g2p_model_menu.addMenu("MFA G2P model")
        for lang in G2PModel.get_available_models():
            lang_action = QtGui.QAction(parent=self, text=lang)
            lang_action.triggered.connect(lambda: self.change_g2p(lang))
            downloaded_g2p_models.addAction(lang_action)

        self.windows_menu = self.menuBar().addMenu('Window')
        self.windows_menu.addAction(self.list_dock.toggleViewAction())
        self.windows_menu.addAction(self.dictionary_dock.toggleViewAction())
        self.windows_menu.addAction(self.speaker_dock.toggleViewAction())

        self.help_act = DefaultAction('help',
            parent=self, text="Help",
            statusTip="Help")

        self.open_help_act = DefaultAction('help',
            parent=self, text="Open documentation",
            statusTip="Open documentation", triggered=self.open_help)
        self.report_bug_act = DefaultAction('bug',
            parent=self, text="Report a bug",
            statusTip="Report a bug", triggered=self.report_bug)

        self.corner_tool_bar = QtWidgets.QToolBar()
        self.help_widget = HelpDropDown()
        self.help_widget.setDefaultAction(self.help_act)

        self.help_widget.addAction(self.open_help_act)
        self.corner_tool_bar.addWidget(self.help_widget)

        self.corner_tool_bar.addAction(self.report_bug_act)
        self.menuBar().setCornerWidget(self.corner_tool_bar, QtCore.Qt.Corner.TopRightCorner)
        #self.language_model_menu = self.menuBar().addMenu("Language model")
        #self.language_model_menu.addAction(self.load_lm_act)
        #downloaded_language_models = self.language_model_menu.addMenu("MFA language model")
        #for lang in get_available_lm_languages():
        #    lang_action = QtGui.QAction(
        #        parent=self, text=lang,
        #        statusTip=lang, triggered=lambda: self.change_lm(lang))
        #    downloaded_language_models.addAction(lang_action)

        #self.ivector_menu = self.menuBar().addMenu("Speaker classification")
        #self.ivector_menu.addAction(self.load_ivector_extractor_act)
        #downloaded_ie_models = self.ivector_menu.addMenu("MFA ivector extractor")
        #for lang in get_available_ivector_languages():
        #    lang_action = QtGui.QAction(
        #        parent=self, text=lang,
        #        statusTip=lang, triggered=lambda: self.change_ivector_extractor(lang))
        #    downloaded_ie_models.addAction(lang_action)


    def change_temp_dir(self):
        self.configUpdated.emit(self.config)

    def change_corpus(self):
        default_dir = self.default_directory
        if self.config['current_corpus_path']:
            default_dir = os.path.dirname(self.config['current_corpus_path'])
        corpus_directory = QtWidgets.QFileDialog.getExistingDirectory(caption='Select a corpus directory',
                                                                      directory=default_dir)
        if not corpus_directory or not os.path.exists(corpus_directory):
            return
        self.default_directory = os.path.dirname(corpus_directory)
        self.config['current_corpus_path'] = corpus_directory
        self.load_corpus()
        self.configUpdated.emit(self.config)
        self.deleted_utts = []

    def close_corpus(self):
        self.title_screen.setVisible(True)
        self.list_widget.setVisible(False)
        self.detail_widget.setVisible(False)
        self.loading_label.setVisible(False)
        self.corpus = None
        self.current_corpus_path = None
        self.config['current_corpus_path'] = ''
        self.corpusLoaded.emit(None)
        self.configUpdated.emit(self.config)

    def load_corpus(self):
        self.loading_corpus = True
        directory = self.config['current_corpus_path']
        if directory is None or not os.path.exists(directory):
            self.title_screen.setVisible(True)
            self.list_widget.setVisible(False)
            self.detail_widget.setVisible(False)
            self.loading_label.setVisible(False)
            return
        self.load_corpus_path(directory)

    def load_corpus_path(self, directory):
        self.current_corpus_path = directory
        self.set_application_state('loading')

        self.loading_label.setCorpusName(f'Loading {directory}...')
        self.corpus_worker.setParams(directory, self.config['temp_directory'])
        self.corpus_worker.start()


    def cancel_corpus_load(self):
        self.cancel_load_corpus_act.setEnabled(False)
        self.loading_label.text_label.setText("Cancelling...")
        self.corpus_worker.stop()

    def finish_cancelling(self):
        self.loading_corpus = False
        self.corpus = None
        self.corpus_model.setCorpus(None)
        self.current_corpus_path = None

        self.set_application_state('unloaded')
        self.corpusLoaded.emit()
        self.set_current_utterance(None, False)

    def finalize_load_corpus(self, corpus):
        self.corpus = corpus
        self.corpus_model.setCorpus(corpus)

        self.loading_corpus = False
        self.corpusLoaded.emit()
        self.change_speaker_act.widget.refresh_speaker_dropdown(self.corpus.speakers)
        self.set_application_state('loaded')

    def change_acoustic_model(self, lang=None):
        if not isinstance(lang, str):
            am_path, _ = QtWidgets.QFileDialog.getOpenFileName(caption='Select an acoustic model',
                                                               directory=self.default_directory,
                                                               filter="Model files (*.zip)")
        else:
            am_path = AcousticModel.get_pretrained_path(lang)
        if not am_path or not os.path.exists(am_path):
            return
        self.default_directory = os.path.dirname(am_path)
        self.config['current_acoustic_model_path'] = am_path
        self.load_acoustic_model()
        self.configUpdated.emit(self.config)

    def load_acoustic_model(self):
        self.loading_am = True
        am_path = self.config['current_acoustic_model_path']
        if am_path is None or not os.path.exists(am_path):
            return
        am_name, _ = os.path.splitext(os.path.basename(am_path))
        self.acoustic_model = AcousticModel(am_path, root_directory=self.config['temp_directory'])
        self.acousticModelLoaded.emit(self.acoustic_model)
        self.loading_am = False

    def change_ivector_extractor(self, lang=None):
        if not isinstance(lang, str):
            ie_path, _ = QtWidgets.QFileDialog.getOpenFileName(caption='Select a ivector extractor model',
                                                               directory=self.default_directory,
                                                               filter="Model files (*.zip)")
        else:
            ie_path = IvectorExtractorModel.get_pretrained_path(lang)
        if not ie_path or not os.path.exists(ie_path):
            return
        self.default_directory = os.path.dirname(ie_path)
        self.config['current_ivector_extractor_path'] = ie_path
        self.load_ivector_extractor()
        self.configUpdated.emit(self.config)

    def load_ivector_extractor(self):
        self.loading_ie = True
        ie_path = self.config['current_ivector_extractor_path']
        if ie_path is None or not os.path.exists(ie_path):
            return
        ie_name, _ = os.path.splitext(os.path.basename(ie_path))
        self.ie_model = IvectorExtractorModel(ie_path, root_directory=self.config['temp_directory'])
        self.ivectorExtractorLoaded.emit(self.ie_model)
        self.loading_ie = False

    def change_dictionary(self, lang=None):
        if not isinstance(lang, str):
            lang = None
        if lang is None:
            dictionary_path, _ = QtWidgets.QFileDialog.getOpenFileName(caption='Select a dictionary',
                                                                       directory=self.default_directory,
                                                                       filter="Dictionary files (*.dict *.txt)")
        else:
            dictionary_path = DictionaryModel.get_pretrained_path(lang)
        if not dictionary_path or not os.path.exists(dictionary_path):
            return
        self.default_directory = os.path.dirname(dictionary_path)
        self.config['current_dictionary_path'] = dictionary_path
        self.load_dictionary()
        self.configUpdated.emit(self.config)

    def load_dictionary(self):
        self.loading_dictionary = True
        dictionary_path = self.config['current_dictionary_path']
        if dictionary_path is None or not os.path.exists(dictionary_path):
            return

        dictionary_name, _ = os.path.splitext(os.path.basename(dictionary_path))
        dictionary_temp_dir = os.path.join(self.config['temp_directory'], dictionary_name)
        self.dictionary = PronunciationDictionary(dictionary_path, dictionary_temp_dir)
        self.dictionaryLoaded.emit(self.dictionary)
        self.corpus_model.setDictionary(self.dictionary)
        self.loading_dictionary = False
        self.save_dictionary_act.setEnabled(False)
        self.reset_dictionary_act.setEnabled(False)

    def save_file(self):
        if not self.corpus_model.corpus:
            return
        if self.saving_utterance:
            return
        self.saving_utterance = True

        self.status_label.setText('Saving {}...'.format(self.corpus_model.file_name))
        try:
            self.corpus_model.corpus.save_text_file(self.corpus_model.file_name)
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print(traceback.format_exception(exc_type, exc_value, exc_traceback))
            reply = DetailedMessageBox()
            reply.setDetailedText('\n'.join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            ret = reply.exec_()
        self.saving_utterance = False
        self.save_current_file_act.setEnabled(False)
        self.status_label.setText('Saved {}!'.format(self.corpus_model.file_name))

    def save_dictionary(self):
        if self.saving_dictionary:
            return
        words = self.dictionary_widget.create_dictionary_for_save()
        if not words:
            self.save_dictionary_act.setText('Issue encountered')
            return
        self.dictionary.words = words
        self.saving_dictionary = True
        with open(self.config['current_dictionary_path'], 'w', encoding='utf8') as f:
            for word, prons in sorted(self.dictionary.words.items()):
                for p in prons:
                    pronunciation = ' '.join(p['pronunciation'])
                    f.write('{} {}\n'.format(word, pronunciation))
        self.saving_dictionary = False
        self.dictionaryLoaded.emit(self.dictionary)
        self.save_dictionary_act.setEnabled(False)
        self.reset_dictionary_act.setEnabled(False)
        self.save_dictionary_act.setText('Dictionary saved!')

    def load_g2p(self):
        self.loading_g2p = True
        g2p_path = self.config['current_g2p_model_path']
        if g2p_path is None or not os.path.exists(g2p_path):
            return
        g2p_name, _ = os.path.splitext(os.path.basename(g2p_path))
        self.g2p_model = G2PModel(g2p_path, root_directory=self.config['temp_directory'])
        self.g2pLoaded.emit(self.g2p_model)
        self.loading_g2p = False

    def change_g2p(self, lang=None):
        if not isinstance(lang, str):
            g2p_path, _ = QtWidgets.QFileDialog.getOpenFileName(caption='Select a g2p model',
                                                                directory=self.default_directory,
                                                                filter="Model files (*.zip)")
        else:
            g2p_path = G2PModel.get_pretrained_path(lang)
        if not g2p_path or not os.path.exists(g2p_path):
            return
        self.default_directory = os.path.dirname(g2p_path)
        self.config['current_g2p_model_path'] = g2p_path
        self.load_g2p()
        self.configUpdated.emit(self.config)

    def load_lm(self):
        pass

    def change_lm(self, lang=None):
        if not isinstance(lang, str):
            lm_path, _ = QtWidgets.QFileDialog.getOpenFileName(caption='Select a language model',
                                                               directory=self.default_directory,
                                                               filter="Model files (*.zip)")
        else:
            lm_path = LanguageModel.get_pretrained_path(lang)
        if not lm_path or not os.path.exists(lm_path):
            return
        self.default_directory = os.path.dirname(lm_path)
        self.config['current_language_model_path'] = lm_path
        self.load_lm()
        self.configUpdated.emit(self.config)
