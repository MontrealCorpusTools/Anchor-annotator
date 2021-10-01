import yaml
import os
import sys
import traceback
import re
from PyQt5 import QtGui, QtCore, QtWidgets, QtSvg

from montreal_forced_aligner.config import TEMP_DIR

from montreal_forced_aligner.dictionary import Dictionary
from montreal_forced_aligner.models import G2PModel, AcousticModel, LanguageModel, IvectorExtractor
from montreal_forced_aligner.utils import get_available_g2p_languages, get_pretrained_g2p_path, \
    get_available_acoustic_languages, get_pretrained_acoustic_path, \
    get_available_dict_languages, get_dictionary_path, \
    get_available_ivector_languages, get_pretrained_ivector_path, \
    get_available_lm_languages, get_pretrained_language_model_path

from montreal_forced_aligner.helper import setup_logger

from .widgets import UtteranceListWidget, UtteranceDetailWidget, InformationWidget, \
    DetailedMessageBox, DefaultAction, AnchorAction, create_icon, HorizontalSpacer

from .workers import ImportCorpusWorker


class ColorEdit(QtWidgets.QPushButton): # pragma: no cover
    def __init__(self, color, parent=None):
        super(ColorEdit, self).__init__(parent=parent)
        self._color = color
        self.updateIcon()
        self.clicked.connect(self.openDialog)

    def updateIcon(self):
        pixmap = QtGui.QPixmap(100, 100)
        pixmap.fill(self._color)
        icon = QtGui.QIcon(pixmap)
        icon.addPixmap(pixmap, QtGui.QIcon.Disabled)
        self.setIcon(icon)

    @property
    def color(self):
        return self._color.name()

    def openDialog(self):
        color = QtWidgets.QColorDialog.getColor()
        if color.isValid():
            self._color = color
            self.updateIcon()


class FontDialog(QtWidgets.QFontDialog):
    def __init__(self, *args):
        super(FontDialog, self).__init__(*args)
        print(dir(self))


class FontEdit(QtWidgets.QPushButton): # pragma: no cover
    """
    Parameters
    ----------
    font : QtGui.QFont
    """
    def __init__(self, font, parent=None):
        super(FontEdit, self).__init__(parent=parent)
        print(font)
        self.font = font
        self.updateIcon()
        self.clicked.connect(self.openDialog)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

    def updateIcon(self):
        self.setFont(self.font)
        self.setText(self.font.key().split(',',maxsplit=1)[0])

    def openDialog(self):
        font, ok = FontDialog.getFont(self.font)

        if ok:
            self.font = font
            self.updateIcon()

class ConfigurationOptions(object):
    def __init__(self, data):
        self.data = {
            'temp_directory': TEMP_DIR,
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
        yellows = {'very_very_light': '#EFCE2B',
                   'very_light': '#FFE819',
                   'light': '#F9D213',
                   'base': '#F2BC0C',
                   'dark': '#BD9105',
                   'very_dark': '#A07A00',
                   }
        blues = {
            'very_very_light': '#49A4F7',
            'very_light': '#1265B2',
            'light': '#0A4B89',
            'base': '#053561',
            'dark': '#01192F',
            'very_dark': '#000C17',
                   }
        reds = {'very_light': '#FF4619',
                   'light': '#D43610',
                   'base': '#AA2809',
                   'dark': '#761A03',
                   'very_dark': '#5C1200',
                   }
        return yellows, blues, reds

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
        yellows, blues, reds = self.mfa_color_palettes
        white = '#EDDDD4'
        black = blues['very_dark']
        return {
                'background_color': blues['base'],

                'table_header_color': white,
                'table_header_background_color': blues['light'],
                'table_even_color': yellows['very_very_light'],
                'table_odd_color': blues['very_very_light'],
                'table_text_color': black,

                'underline_color': reds['very_light'],
                'keyword_color': yellows['light'],
                'keyword_text_color': black,
                'selection_color': blues['very_light'],
                'text_edit_color': white,
                'error_color': reds['very_light'],
                'error_text_color': yellows['dark'],
                'error_background_color': reds['light'],
                'text_edit_background_color': black,

                'main_widget_border_color': blues['very_very_light'],
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
                'active_border_color': blues['very_very_light'],

                'hover_text_color': yellows['very_light'],
                'hover_background_color': blues['very_very_light'],
                'hover_border_color': blues['base'],

                'disabled_text_color': reds['very_light'],
                'disabled_background_color': blues['dark'],
                'disabled_border_color': blues['very_dark'],

                'scroll_bar_background_color': blues['dark'],
                'scroll_bar_handle_color': yellows['light'],
                'scroll_bar_border_color': black,
            }

    @property
    def mfa_plot_theme(self):
        yellows, blues, reds = self.mfa_color_palettes
        white = '#EDDDD4'
        black = blues['very_dark']
        return {
            'background_color': black,
            'play_line_color': reds['very_light'],
            'selected_range_color': blues['very_light'],
            'selected_interval_color': blues['base'],
            'selected_line_color': yellows['light'],
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
        self.key_bind_widget.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.tab_widget.addTab(self.key_bind_widget, 'Key shortcuts')

        key_bind_layout = QtWidgets.QFormLayout()

        self.autosave_edit = QtWidgets.QCheckBox()
        self.autosave_edit.setChecked(self.base_config['autosave'])
        self.autosave_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        key_bind_layout.addRow('Autosave on exit', self.autosave_edit)

        self.autoload_edit = QtWidgets.QCheckBox()
        self.autoload_edit.setChecked(self.base_config['autoload'])
        self.autoload_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        key_bind_layout.addRow('Autoload last used corpus', self.autoload_edit)

        self.play_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.play_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['play_keybind']))
        self.play_key_bind_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        key_bind_layout.addRow('Play audio', self.play_key_bind_edit)

        self.zoom_in_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.zoom_in_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['zoom_in_keybind']))
        self.zoom_in_key_bind_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        key_bind_layout.addRow('Zoom in', self.zoom_in_key_bind_edit)

        self.zoom_out_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.zoom_out_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['zoom_out_keybind']))
        self.zoom_out_key_bind_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        key_bind_layout.addRow('Zoom out', self.zoom_out_key_bind_edit)

        self.pan_left_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.pan_left_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['pan_left_keybind']))
        self.pan_left_key_bind_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        key_bind_layout.addRow('Pan left', self.pan_left_key_bind_edit)

        self.pan_right_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.pan_right_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['pan_right_keybind']))
        self.pan_right_key_bind_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        key_bind_layout.addRow('Pan right', self.pan_right_key_bind_edit)

        self.merge_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.merge_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['merge_keybind']))
        self.merge_key_bind_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        key_bind_layout.addRow('Merge utterances', self.merge_key_bind_edit)

        self.split_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.split_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['split_keybind']))
        self.split_key_bind_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        key_bind_layout.addRow('Split utterances', self.split_key_bind_edit)

        self.delete_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.delete_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['delete_keybind']))
        self.delete_key_bind_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        key_bind_layout.addRow('Delete utterance', self.delete_key_bind_edit)

        self.save_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.save_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['save_keybind']))
        self.save_key_bind_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        key_bind_layout.addRow('Save current file', self.save_key_bind_edit)

        self.search_key_bind_edit = QtWidgets.QKeySequenceEdit()
        self.search_key_bind_edit.setKeySequence(QtGui.QKeySequence(self.base_config['search_keybind']))
        self.search_key_bind_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
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
    def notify(self, receiver, e):
        #if e and e.type() == QtCore.QEvent.KeyPress:
        #    if e.key() == QtCore.Qt.Key_Tab:
        #        return False
        return super(Application, self).notify(receiver, e)


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
        self.logo_widget = QtSvg.QSvgWidget(':splash_screen.svg')
        self.setMinimumSize(720, 720)
        self.setMaximumSize(720, 720)

        self.setVisible(False)
        #self.loading_label.setWindowFlag()
        layout.addWidget(self.logo_widget)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.setLayout(layout)

    def update_config(self, config):
        font_config = config.font_options


class MainWindow(QtWidgets.QMainWindow):  # pragma: no cover
    configUpdated = QtCore.pyqtSignal(object)
    corpusLoaded = QtCore.pyqtSignal(object)
    dictionaryLoaded = QtCore.pyqtSignal(object)
    g2pLoaded = QtCore.pyqtSignal(object)
    ivectorExtractorLoaded = QtCore.pyqtSignal(object)
    acousticModelLoaded = QtCore.pyqtSignal(object)
    languageModelLoaded = QtCore.pyqtSignal(object)
    saveCompleted = QtCore.pyqtSignal(object)
    newSpeaker = QtCore.pyqtSignal(object)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Tab:
            event.ignore()
            return
        super(MainWindow, self).keyPressEvent(event)

    def __init__(self):
        super(MainWindow, self).__init__()
        fonts = ['GentiumPlus', 'CharisSIL',
                 'NotoSans-Black', 'NotoSans-Bold', 'NotoSans-BoldItalic', 'NotoSans-Italic', 'NotoSans-Light',
                 'NotoSans-Medium', 'NotoSans-MediumItalic', 'NotoSans-Regular', 'NotoSans-Thin',
                 'NotoSerif-Black', 'NotoSerif-Bold', 'NotoSerif-BoldItalic', 'NotoSerif-Italic', 'NotoSerif-Light',
                 'NotoSerif-Medium', 'NotoSerif-MediumItalic', 'NotoSerif-Regular', 'NotoSerif-Thin'
                 ]
        for font in fonts:
            id = QtGui.QFontDatabase.addApplicationFont(f":fonts/{font}.ttf")
        self.config_path = os.path.join(TEMP_DIR, 'config.yaml')
        self.history_path = os.path.join(TEMP_DIR, 'search_history')
        self.corpus_history_path = os.path.join(TEMP_DIR, 'corpus_history')
        self.corpus = None
        self.current_corpus_path = None
        self.dictionary = None
        self.acoustic_model = None
        self.g2p_model = None
        self.language_model = None
        self.waiting_on_close = False

        self.list_widget = UtteranceListWidget(self)
        self.detail_widget = UtteranceDetailWidget(self)
        self.detail_widget.text_widget.installEventFilter(self)
        self.information_widget = InformationWidget(self)
        self.loading_label = LoadingScreen(self)
        self.title_screen = TitleScreen(self)
        self.status_bar = QtWidgets.QStatusBar()
        self.configUpdated.connect(self.detail_widget.update_config)
        self.configUpdated.connect(self.list_widget.update_config)
        self.configUpdated.connect(self.information_widget.update_config)
        self.configUpdated.connect(self.loading_label.update_config)
        self.configUpdated.connect(self.title_screen.update_config)
        self.resize_timer = QtCore.QTimer(self)
        self.resize_timer.timeout.connect(self.doneResizing)
        self.create_actions()
        self.create_menus()
        self.setup_key_binds()
        self.load_config()
        self.load_search_history()
        self.load_corpus_history()
        if self.config['is_maximized']:
            self.setWindowState(QtCore.Qt.WindowState.WindowMaximized)
        else:
            self.resize(self.config['width'], self.config['height'])
        self.configUpdated.connect(self.save_config)
        self.current_utterance = None

        self.corpusLoaded.connect(self.detail_widget.update_corpus)
        self.corpusLoaded.connect(self.list_widget.update_corpus)
        self.dictionaryLoaded.connect(self.detail_widget.update_dictionary)
        self.list_widget.utteranceChanged.connect(self.set_current_utterance)
        self.list_widget.updateView.connect(self.detail_widget.update_plot)
        self.list_widget.utteranceMerged.connect(self.detail_widget.refresh_view)
        self.list_widget.utteranceDeleted.connect(self.detail_widget.refresh_view)
        self.list_widget.utteranceDeleted.connect(self.setFileSaveable)
        self.list_widget.fileChanged.connect(self.update_file_name)
        self.detail_widget.selectUtterance.connect(self.set_current_utterance)
        self.information_widget.search_widget.showUtterance.connect(self.set_current_utterance)
        self.detail_widget.refreshCorpus.connect(self.list_widget.refresh_corpus)
        self.detail_widget.createUtterance.connect(self.list_widget.create_utterance)
        self.detail_widget.utteranceUpdated.connect(self.list_widget.update_utterance_text)
        self.detail_widget.utteranceChanged.connect(self.setFileSaveable)
        self.detail_widget.refreshCorpus.connect(self.setFileSaveable)
        self.detail_widget.audioPlaying.connect(self.updateAudioState)
        self.corpusLoaded.connect(self.information_widget.speaker_widget.update_corpus)
        self.corpusLoaded.connect(self.information_widget.search_widget.update_corpus)
        self.dictionaryLoaded.connect(self.list_widget.update_dictionary)
        self.dictionaryLoaded.connect(self.information_widget.dictionary_widget.update_dictionary)
        self.g2pLoaded.connect(self.information_widget.dictionary_widget.update_g2p)
        self.detail_widget.lookUpWord.connect(self.information_widget.dictionary_widget.look_up_word)
        self.detail_widget.createWord.connect(self.information_widget.dictionary_widget.create_pronunciation)
        self.saveCompleted.connect(self.setFileSaveable)
        self.information_widget.dictionary_widget.dictionaryError.connect(self.show_dictionary_error)
        self.information_widget.dictionary_widget.dictionaryModified.connect(self.enable_dictionary_actions)
        self.newSpeaker.connect(self.change_speaker_act.widget.refresh_speaker_dropdown)
        self.newSpeaker.connect(self.information_widget.speaker_widget.refresh_speakers)
        self.information_widget.speaker_widget.speaker_edit.enableAddSpeaker.connect(self.enable_add_speaker)
        self.information_widget.search_widget.searchNew.connect(self.detail_widget.set_search_term)
        self.warning_label = WarningLabel('Warning: This is alpha '
                                              'software, there will be bugs and issues. Please back up any data before '
                                              'using.')
        self.status_label = QtWidgets.QLabel()
        self.status_bar.addPermanentWidget(self.warning_label, 1)
        self.status_bar.addPermanentWidget(self.status_label)
        self.setStatusBar(self.status_bar)
        self.wrapper = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout()

        self.list_widget.setVisible(False)
        self.detail_widget.setVisible(False)
        self.information_widget.setVisible(False)
        self.loading_label.setVisible(False)
        self.title_screen.setVisible(True)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.detail_widget)
        layout.addWidget(self.information_widget)
        layout.addWidget(self.loading_label)
        layout.addWidget(self.title_screen)

        self.wrapper.setLayout(layout)
        self.setCentralWidget(self.wrapper)
        self.default_directory = TEMP_DIR
        self.logger = setup_logger('anchor', self.default_directory, 'debug')

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

        self.corpus_worker = ImportCorpusWorker(logger=self.logger)

        #self.corpus_worker.errorEncountered.connect(self.showError)
        self.corpus_worker.dataReady.connect(self.finalize_load_corpus)
        self.corpus_worker.finishedCancelling.connect(self.finish_cancelling)
        if self.config['autoload']:
            self.load_corpus()
        self.load_dictionary()
        self.load_g2p()
        self.load_ivector_extractor()

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
            self.information_widget.dictionary_widget.ignore_errors = True
            self.save_dictionary_act.trigger()

    def eventFilter(self, object, event) -> bool:
        if event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Tab:
            self.play_act.trigger()
            return True
        return False

    def update_file_name(self, file_name):
        self.current_file = file_name
        self.list_widget.update_file_name(file_name)
        self.detail_widget.update_file_name(file_name)
        self.information_widget.search_widget.update_file_name(file_name)
        self.set_current_utterance(None, False)
        self.setFileSaveable(False)

    def updateAudioState(self, playing):
        self.play_act.setChecked(playing)

    def setFileSaveable(self, enable):
        self.save_current_file_act.setEnabled(enable)

    def set_current_utterance(self, utterance, zoom):
        self.current_utterance = utterance
        if self.sender() != self.list_widget:
            self.list_widget.select_utterance(utterance, zoom)
        if self.sender() != self.detail_widget:
            self.detail_widget.update_utterance(utterance, zoom)
        if self.current_utterance is None:
            self.change_speaker_act.setEnabled(False)
            self.delete_act.setEnabled(False)
            self.change_speaker_act.widget.setCurrentSpeaker('')
        else:
            self.change_speaker_act.setEnabled(True)
            self.delete_act.setEnabled(True)
            self.change_speaker_act.widget.setCurrentSpeaker(self.corpus.utt_speak_mapping[self.current_utterance])


    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        if self.loading_corpus:
            self.cancel_load_corpus_act.trigger()
            self.loading_label.setExiting()
            self.repaint()
            while self.loading_corpus:
                self.corpus_worker.wait(500)
                if self.corpus_worker.isFinished():
                    break
        print('CLOSE EVENT')
        self.config['height'] = self.height()
        self.config['width'] = self.width()
        print('SAVING MAXIMIZED', self.isMaximized())
        self.config['is_maximized'] = self.isMaximized()
        self.config['volume'] = self.change_volume_act.widget.value()
        self.save_config()
        self.save_search_history()
        if self.config['autosave']:
            print('Saving!')
            self.save_file(self.list_widget.current_file)
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
        old_utterance = self.detail_widget.utterance
        speaker = self.change_speaker_act.widget.current_speaker
        print(old_utterance, speaker)
        if old_utterance is None:
            return
        if old_utterance not in self.corpus.utt_speak_mapping:
            return
        old_speaker = self.corpus.utt_speak_mapping[old_utterance]

        if old_speaker == speaker:
            return
        if not speaker:
            return
        new_utt = old_utterance.replace(old_speaker, speaker)
        file = self.corpus.utt_file_mapping[old_utterance]
        text = self.corpus.text_mapping[old_utterance]
        seg = self.corpus.segments[old_utterance]
        self.corpus.add_utterance(new_utt, speaker, file, text, seg=seg)
        self.corpus.delete_utterance(old_utterance)

        self.list_widget.refresh_corpus(new_utt)
        self.information_widget.speaker_widget.refresh_speakers()
        self.detail_widget.refresh_utterances()
        self.setFileSaveable(True)

    def refresh_fonts(self):
        base_font = self.config.font_options['font']
        big_font = self.config.font_options['big_font']
        self.menuBar().setFont(base_font)
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

        icon_ratio = 0.03
        icon_height = int(icon_ratio*self.config['height'])
        if icon_height < 24:
            icon_height = 24

        for a in self.actions():
            if isinstance(a, AnchorAction):
                a.widget.setFont(base_font)
                a.widget.setFixedHeight(icon_height+8)

            else:
                a.setFont(base_font)

    def doneResizing(self):
        self.resize_timer.stop()
        print('DONE RESIZING', self.size())
        self.config['height'] = self.height()
        self.config['width'] = self.width()
        self.configUpdated.emit(self.config)

    def resizeEvent(self, a0: QtGui.QResizeEvent) -> None:
        if self.corpus is not None:
            self.resize_timer.stop()
        super(MainWindow, self).resizeEvent(a0)
        if self.corpus is not None:
            self.resize_timer.start(100)

    def save_search_history(self):
        with open(self.history_path, 'w', encoding='utf8') as f:
            for query in self.information_widget.search_widget.history:
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
        self.information_widget.search_widget.load_history(history)

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
            history_action = QtWidgets.QAction(parent=self, text=os.path.basename(corpus),
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
        }}
        QMenuBar::item {{
                        color: {menu_text_color};
                        background-color: {menu_background_color};
        }}
        QMenuBar::item:disabled {{
                        color: {disabled_text_color};
                        background-color: {menu_background_color};
                        }}
        ButtonWidget {{
            background-color: {table_header_background_color};
        }}
        
        UtteranceListWidget {{
            background-color: {text_edit_background_color};
            color: {main_widget_border_color};
            border: {border_width}px solid {main_widget_border_color};
            padding: 0px;
            padding-top: 20px;
            border-radius: {border_radius}px;
            margin-top: 0ex; /* leave space at the top for the title */
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
            border-bottom-left-radius: {border_radius}px;
            border-bottom-right-radius: {border_radius}px;
            background-color: {main_widget_background_color};
        
        }}
        QTabWidget {{
            background-color: {main_widget_background_color};
            border-radius: {border_radius}px;
            border: {border_width}px solid {main_widget_border_color};
            border-radius: {border_radius}px;
                    
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
            
        
        QTabBar::tab-bar {{
            color: {menu_text_color};
            background-color: {menu_background_color};
            border: {border_width}px solid {main_widget_border_color};
            border-radius: {border_radius}px;
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
            border-left-width: {border_width}px;
            border-right-width: {border_width}px;
            margin-left: -{border_width}px;
            margin-right: -{border_width}px;
            border-color: {active_border_color};
            border-bottom-color:  {active_border_color};
        }}
        QTabBar::tab:first {{
            border-top-left-radius: {border_radius}px;
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
        QPushButton:hover, QToolButton:hover, QToolButton:focus, ToolButton:hover {{
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
            color: {text_edit_color};
            background-color: {text_edit_background_color};
            selection-background-color: {selection_color};
        }}
        QSlider::handle:horizontal {{
            height: 10px;
            background: {enabled_color};
            margin: 0 -4px; /* expand outside the groove */
        }}
        QSlider::handle:horizontal:hover {{
            height: 10px;
            background: {hover_text_color};
            margin: 0 -4px; /* expand outside the groove */
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
        self.change_temp_dir_act = QtWidgets.QAction(
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

        self.close_corpus_act = QtWidgets.QAction(
            parent=self, text="Close current corpus",
            statusTip="Load current corpus", triggered=self.close_corpus)

        self.load_acoustic_model_act = QtWidgets.QAction(
            parent=self, text="Load an acoustic model",
            statusTip="Load an acoustic model", triggered=self.change_acoustic_model)

        self.load_dictionary_act = QtWidgets.QAction(
            parent=self, text="Load a dictionary",
            statusTip="Load a dictionary", triggered=self.change_dictionary)

        self.load_g2p_act = QtWidgets.QAction(
            parent=self, text="Load a G2P model",
            statusTip="Load a G2P model", triggered=self.change_g2p)

        self.load_lm_act = QtWidgets.QAction(
            parent=self, text="Load a language model",
            statusTip="Load a language model", triggered=self.change_lm)

        self.load_ivector_extractor_act = QtWidgets.QAction(
            parent=self, text="Load an ivector extractor",
            statusTip="Load an ivector extractor", triggered=self.change_ivector_extractor)

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
            self.detail_widget.setVisible(False)
            self.information_widget.setVisible(False)
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
            self.detail_widget.setVisible(True)
            self.information_widget.setVisible(True)
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

        elif state == 'unloaded':
            self.loading_label.setVisible(False)
            self.list_widget.setVisible(False)
            self.detail_widget.setVisible(False)
            self.information_widget.setVisible(False)
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

    def setup_key_binds(self):

        self.play_act = DefaultAction('play', checkable=True,
            parent=self, text="Play audio",
            statusTip="Play current loaded file", triggered=self.detail_widget.play_audio)


        self.zoom_in_act = DefaultAction('search-plus',
            parent=self, text="Zoom in",
            statusTip="Zoom in", triggered=self.detail_widget.zoom_in)

        self.zoom_out_act = DefaultAction('search-minus',
            parent=self, text="Zoom out",
            statusTip="Zoom out", triggered=self.detail_widget.zoom_out)

        self.pan_left_act = DefaultAction('caret-left', buttonless=True,
            parent=self, text="Pan left",
            statusTip="Pan left", triggered=self.detail_widget.pan_left)

        self.pan_right_act = DefaultAction('caret-right', buttonless=True,
            parent=self, text="Pan right",
            statusTip="Pan right", triggered=self.detail_widget.pan_right)

        self.merge_act = DefaultAction('compress',
            parent=self, text="Merge utterances",
            statusTip="Merge utterances", triggered=self.list_widget.merge_utterances)

        self.split_act = DefaultAction('expand',
            parent=self, text="Split utterances",
            statusTip="Split utterances", triggered=self.list_widget.split_utterances)

        self.search_act = DefaultAction('search',
            parent=self, text="Search corpus",
            statusTip="Search corpus", triggered=self.open_search)

        self.delete_act = DefaultAction(icon_name='trash',
            parent=self, text="Delete utterances",
            statusTip="Delete utterances", triggered=self.list_widget.delete_utterances)

        self.save_act = DefaultAction('save',
            parent=self, text="Save file",
            statusTip="Save a current file", triggered=self.save_file)

        self.show_all_speakers_act = DefaultAction('users', checkable=True,
            parent=self, text="Show all speakers",
            statusTip="Show all speakers", triggered=self.detail_widget.update_show_speakers)

        self.mute_act = DefaultAction('volume-up', checkable=True,
            parent=self, text="Mute",
            statusTip="Mute", triggered=self.detail_widget.update_mute_status)

        self.change_volume_act = AnchorAction('volume',
            parent=self, text="Adjust volume",
            statusTip="Adjust volume")
        self.change_volume_act.widget.valueChanged.connect(self.detail_widget.m_audioOutput.setVolume)

        self.change_speaker_act = AnchorAction('speaker',
            parent=self, text="Change utterance speaker",
            statusTip="Change utterance speaker", triggered=self.update_speaker)

        self.save_current_file_act = DefaultAction('save',
            parent=self, text="Save current file",
            statusTip="Save current file", triggered=self.save_file)
        self.save_current_file_act.setDisabled(True)

        self.revert_changes_act = DefaultAction('undo',
            parent=self, text="Undo unsaved changes",
            statusTip="Undo unsaved changes", triggered=self.list_widget.restore_deleted_utts)
        self.revert_changes_act.setDisabled(True)

        self.add_new_speaker_act = DefaultAction('user-plus',
            parent=self, text="Add new speaker",
            statusTip="Add new speaker", triggered=self.add_new_speaker)
        self.add_new_speaker_act.setEnabled(False)

        self.save_dictionary_act = DefaultAction('book-save',
            parent=self, text="Save dictionary",
            statusTip="Save dictionary", triggered=self.save_dictionary)
        self.save_dictionary_act.setEnabled(False)

        self.reset_dictionary_act = DefaultAction('book-undo',
            parent=self, text="Revert dictionary",
            statusTip="Revert dictionary", triggered=self.load_dictionary)
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

        self.information_widget.speaker_widget.tool_bar.addAction(self.add_new_speaker_act)
        self.information_widget.speaker_widget.speaker_edit.returnPressed.connect(self.add_new_speaker_act.trigger)

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

        self.information_widget.dictionary_widget.tool_bar.addAction(self.save_dictionary_act)
        self.information_widget.dictionary_widget.tool_bar.addSeparator()
        self.information_widget.dictionary_widget.tool_bar.addAction(self.reset_dictionary_act)

    def add_new_speaker(self):
        new_speaker = self.information_widget.speaker_widget.speaker_edit.text()
        if new_speaker in self.corpus.speak_utt_mapping:
            return
        if not new_speaker:
            return
        self.corpus.speak_utt_mapping[new_speaker] = []
        self.newSpeaker.emit(self.corpus.speakers)
        self.information_widget.speaker_widget.speaker_edit.clear()

    def open_search(self):
        self.information_widget.tabs.setCurrentWidget(self.information_widget.search_widget)
        self.information_widget.search_widget.search_field.setFocus()

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
        self.file_menu.addAction(self.change_temp_dir_act)
        self.file_menu.addAction(self.options_act)
        self.dictionary_menu = self.menuBar().addMenu("Dictionary")
        self.dictionary_menu.addAction(self.load_dictionary_act)
        downloaded_dictionaries_models = self.dictionary_menu.addMenu("Downloaded dictionary")
        for lang in get_available_dict_languages():
            lang_action = QtWidgets.QAction(
                parent=self, text=lang,
                statusTip=lang, triggered=lambda: self.change_dictionary(lang))
            downloaded_dictionaries_models.addAction(lang_action)
        self.acoustic_model_menu = self.menuBar().addMenu("Acoustic model")
        self.acoustic_model_menu.addAction(self.load_acoustic_model_act)
        downloaded_acoustic_models = self.acoustic_model_menu.addMenu("MFA acoustic model")
        for lang in get_available_acoustic_languages():
            lang_action = QtWidgets.QAction(
                parent=self, text=lang,
                statusTip=lang, triggered=lambda: self.change_acoustic_model(lang))
            downloaded_acoustic_models.addAction(lang_action)

        self.g2p_model_menu = self.menuBar().addMenu("G2P model")
        self.g2p_model_menu.addAction(self.load_g2p_act)
        downloaded_g2p_models = self.g2p_model_menu.addMenu("MFA G2P model")
        for lang in get_available_g2p_languages():
            lang_action = QtWidgets.QAction(
                parent=self, text=lang,
                statusTip=lang, triggered=lambda: self.change_g2p(lang))
            downloaded_g2p_models.addAction(lang_action)

        #self.language_model_menu = self.menuBar().addMenu("Language model")
        #self.language_model_menu.addAction(self.load_lm_act)
        #downloaded_language_models = self.language_model_menu.addMenu("MFA language model")
        #for lang in get_available_lm_languages():
        #    lang_action = QtWidgets.QAction(
        #        parent=self, text=lang,
        #        statusTip=lang, triggered=lambda: self.change_lm(lang))
        #    downloaded_language_models.addAction(lang_action)

        #self.ivector_menu = self.menuBar().addMenu("Speaker classification")
        #self.ivector_menu.addAction(self.load_ivector_extractor_act)
        #downloaded_ie_models = self.ivector_menu.addMenu("MFA ivector extractor")
        #for lang in get_available_ivector_languages():
        #    lang_action = QtWidgets.QAction(
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
        print(corpus_directory)
        self.default_directory = os.path.dirname(corpus_directory)
        self.config['current_corpus_path'] = corpus_directory
        self.load_corpus()
        self.configUpdated.emit(self.config)

    def close_corpus(self):
        self.title_screen.setVisible(True)
        self.list_widget.setVisible(False)
        self.detail_widget.setVisible(False)
        self.information_widget.setVisible(False)
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
            self.information_widget.setVisible(False)
            self.loading_label.setVisible(False)
            return
        self.load_corpus_path(directory)

    def load_corpus_path(self, directory):
        self.current_corpus_path = directory
        self.set_application_state('loading')

        self.corpusLoaded.emit(None)
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
        self.current_corpus_path = None

        self.set_application_state('unloaded')

        self.corpusLoaded.emit(self.corpus)
        self.set_current_utterance(None, False)

    def finalize_load_corpus(self, corpus):
        self.corpus = corpus
        self.loading_corpus = False
        self.corpusLoaded.emit(self.corpus)
        self.change_speaker_act.widget.refresh_speaker_dropdown(self.corpus.speakers)
        self.set_current_utterance(None, False)
        self.set_application_state('loaded')

    def change_acoustic_model(self, lang=None):
        if not isinstance(lang, str):
            am_path, _ = QtWidgets.QFileDialog.getOpenFileName(caption='Select an acoustic model',
                                                               directory=self.default_directory,
                                                               filter="Model files (*.zip)")
        else:
            am_path = get_pretrained_acoustic_path(lang)
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
            ie_path = get_pretrained_ivector_path(lang)
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
        self.ie_model = IvectorExtractor(ie_path, root_directory=self.config['temp_directory'])
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
            dictionary_path = get_dictionary_path(lang)
        if not dictionary_path or not os.path.exists(dictionary_path):
            return
        self.default_directory = os.path.dirname(dictionary_path)
        self.config['current_dictionary_path'] = dictionary_path
        self.load_dictionary()
        self.configUpdated.emit(self.config)

    def load_dictionary(self):
        self.loading_dictionary = True
        dictionary_path = self.config['current_dictionary_path']
        print(dictionary_path)
        if dictionary_path is None or not os.path.exists(dictionary_path):
            return

        dictionary_name, _ = os.path.splitext(os.path.basename(dictionary_path))
        dictionary_temp_dir = os.path.join(self.config['temp_directory'], dictionary_name)
        self.dictionary = Dictionary(dictionary_path, dictionary_temp_dir)
        self.dictionaryLoaded.emit(self.dictionary)
        self.loading_dictionary = False
        self.save_dictionary_act.setEnabled(False)
        self.reset_dictionary_act.setEnabled(False)

    def save_file(self, file_name):
        if not file_name:
            return
        if not self.corpus:
            return
        if self.saving_utterance:
            return
        self.saving_utterance = True

        self.status_label.setText('Saving {}...'.format(file_name))
        try:
            self.corpus.save_text_file(file_name)
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print(traceback.format_exception(exc_type, exc_value, exc_traceback))
            reply = DetailedMessageBox()
            reply.setDetailedText('\n'.join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            ret = reply.exec_()
        self.saving_utterance = False
        #self.corpusLoaded.emit(self.corpus)
        self.saveCompleted.emit(False)
        self.status_label.setText('Saved {}!'.format(file_name))

    def save_dictionary(self):
        if self.saving_dictionary:
            return
        words = self.information_widget.dictionary_widget.create_dictionary_for_save()
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
            g2p_path = get_pretrained_g2p_path(lang)
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
            lm_path = get_pretrained_language_model_path(lang)
        if not lm_path or not os.path.exists(lm_path):
            return
        self.default_directory = os.path.dirname(lm_path)
        self.config['current_language_model_path'] = lm_path
        self.load_lm()
        self.configUpdated.emit(self.config)
