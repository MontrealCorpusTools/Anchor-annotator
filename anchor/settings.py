import pathlib
from typing import Any, Optional

from montreal_forced_aligner.config import get_temporary_directory
from PySide6 import QtCore, QtGui


class AnchorSettings(QtCore.QSettings):
    DEFAULT_DIRECTORY = "anchor/default_directory"
    DEFAULT_CORPUS_DIRECTORY = "anchor/default_corpus_directory"
    DEFAULT_DICTIONARY_DIRECTORY = "anchor/default_dictionary_directory"
    DEFAULT_G2P_DIRECTORY = "anchor/default_g2p_directory"
    DEFAULT_ACOUSTIC_DIRECTORY = "anchor/default_acoustic_directory"
    DEFAULT_LM_DIRECTORY = "anchor/default_lm_directory"
    DEFAULT_IVECTOR_DIRECTORY = "anchor/default_ivector_directory"
    DEFAULT_SAD_DIRECTORY = "anchor/default_sad_directory"
    CORPORA = "anchor/corpora"
    CURRENT_CORPUS = "anchor/current_corpus"

    CORPUS_PATH = "path"
    DICTIONARY_PATH = "dictionary_path"
    ACOUSTIC_MODEL_PATH = "acoustic_model_path"
    G2P_MODEL_PATH = "g2p_model_path"
    LANGUAGE_MODEL_PATH = "language_model_path"
    IE_MODEL_PATH = "ie_model_path"
    PHONE_MAPPING_PATH = "phone_mapping_path"
    REFERENCE_ALIGNMENT_PATH = "reference_alignment_path"

    AUTOSAVE = "anchor/autosave"
    AUTOLOAD = "anchor/autoload"

    VOLUME = "anchor/audio/volume"
    AUDIO_DEVICE = "anchor/audio/device"

    GEOMETRY = "anchor/MainWindow/geometry"
    WINDOW_STATE = "anchor/MainWindow/windowState"

    UTTERANCES_VISIBLE = "anchor/MainWindow/utterancesVisible"
    DICTIONARY_VISIBLE = "anchor/MainWindow/dictionaryVisible"
    OOV_VISIBLE = "anchor/MainWindow/oovVisible"
    SPEAKERS_VISIBLE = "anchor/MainWindow/speakersVisible"
    LM_VISIBLE = "anchor/MainWindow/languageModelVisible"
    AM_VISIBLE = "anchor/MainWindow/acousticModelVisible"
    TRANSCRIPTION_VISIBLE = "anchor/MainWindow/transcriptionVisible"
    ALIGNMENT_VISIBLE = "anchor/MainWindow/alignmentVisible"
    DIARIZATION_VISIBLE = "anchor/MainWindow/diarizationVisible"

    FONT = "anchor/theme/font"
    MAIN_TEXT_COLOR = "anchor/theme/text_color"
    SELECTED_TEXT_COLOR = "anchor/theme/selected_text_color"
    ERROR_COLOR = "anchor/theme/error_color"
    PRIMARY_BASE_COLOR = "anchor/theme/primary_color/base"
    PRIMARY_LIGHT_COLOR = "anchor/theme/primary_color/light"
    PRIMARY_DARK_COLOR = "anchor/theme/primary_color/dark"
    PRIMARY_VERY_LIGHT_COLOR = "anchor/theme/primary_color/very_light"
    PRIMARY_VERY_DARK_COLOR = "anchor/theme/primary_color/very_dark"
    ACCENT_BASE_COLOR = "anchor/theme/accent_color/base"
    ACCENT_LIGHT_COLOR = "anchor/theme/accent_color/light"
    ACCENT_DARK_COLOR = "anchor/theme/accent_color/dark"
    ACCENT_VERY_LIGHT_COLOR = "anchor/theme/accent_color/very_light"
    ACCENT_VERY_DARK_COLOR = "anchor/theme/accent_color/very_dark"

    PLAY_KEYBIND = "anchor/keybinds/play"
    DELETE_KEYBIND = "anchor/keybinds/delete"
    SAVE_KEYBIND = "anchor/keybinds/save"
    SEARCH_KEYBIND = "anchor/keybinds/search"
    SPLIT_KEYBIND = "anchor/keybinds/split"
    MERGE_KEYBIND = "anchor/keybinds/merge"
    ZOOM_IN_KEYBIND = "anchor/keybinds/zoom_in"
    ZOOM_OUT_KEYBIND = "anchor/keybinds/zoom_out"
    ZOOM_TO_SELECTION_KEYBIND = "anchor/keybinds/zoom_to_selection"
    PAN_LEFT_KEYBIND = "anchor/keybinds/pan_left"
    PAN_RIGHT_KEYBIND = "anchor/keybinds/pan_right"
    UNDO_KEYBIND = "anchor/keybinds/undo"
    REDO_KEYBIND = "anchor/keybinds/redo"
    LOCKED = "anchor/locked"
    CUDA = "anchor/cuda"
    GITHUB_TOKEN = "anchor/github_token"
    TIME_DIRECTION = "anchor/time_direction"
    RTL = "Right-to-left"
    LTR = "Left-to-right"

    RESULTS_PER_PAGE = "anchor/results_per_page"
    SPEC_DYNAMIC_RANGE = "anchor/spectrogram/dynamic_range"
    SPEC_N_FFT = "anchor/spectrogram/n_fft"
    SPEC_N_TIME_STEPS = "anchor/spectrogram/time_steps"
    SPEC_WINDOW_SIZE = "anchor/spectrogram/window_size"
    SPEC_PREEMPH = "anchor/spectrogram/preemphasis"
    SPEC_MAX_FREQ = "anchor/spectrogram/max_frequency"

    CLUSTERING_PERPLEXITY = "anchor/clustering/perplexity"
    CLUSTERING_DISTANCE_THRESHOLD = "anchor/clustering/distance_threshold"
    CLUSTERING_METRIC = "anchor/clustering/metric"

    PITCH_MIN_F0 = "anchor/pitch/min_f0"
    PITCH_MAX_F0 = "anchor/pitch/max_f0"
    PITCH_FRAME_SHIFT = "anchor/pitch/frame_shift"
    PITCH_FRAME_LENGTH = "anchor/pitch/frame_length"
    PITCH_DELTA_PITCH = "anchor/pitch/delta_pitch"
    PITCH_PENALTY_FACTOR = "anchor/pitch/penalty_factor"

    TIER_NORMALIZED_VISIBLE = "anchor/tier/normalized_visible"
    TIER_TRANSCRIPTION_VISIBLE = "anchor/tier/transcription_visible"
    TIER_ALIGNED_WORDS_VISIBLE = "anchor/tier/aligned_words_visible"
    TIER_ALIGNED_PHONES_VISIBLE = "anchor/tier/aligned_phones_visible"
    TIER_REFERENCE_PHONES_VISIBLE = "anchor/tier/reference_phones_visible"
    TIER_TRANSCRIBED_WORDS_VISIBLE = "anchor/tier/transcribed_words_visible"
    TIER_TRANSCRIBED_PHONES_VISIBLE = "anchor/tier/transcribed_phones_visible"

    def __init__(self, *args):
        super(AnchorSettings, self).__init__(
            QtCore.QSettings.Format.NativeFormat,
            QtCore.QSettings.Scope.UserScope,
            "Montreal Corpus Tools",
            "Anchor",
        )
        self.mfa_theme = {
            AnchorSettings.MAIN_TEXT_COLOR: "#EDDDD4",
            AnchorSettings.SELECTED_TEXT_COLOR: "#EDDDD4",
            AnchorSettings.ERROR_COLOR: "#C63623",
            AnchorSettings.PRIMARY_BASE_COLOR: "#003566",
            AnchorSettings.PRIMARY_LIGHT_COLOR: "#0E63B3",
            AnchorSettings.PRIMARY_DARK_COLOR: "#001D3D",
            AnchorSettings.PRIMARY_VERY_LIGHT_COLOR: "#7AB5E6",
            AnchorSettings.PRIMARY_VERY_DARK_COLOR: "#000814",
            AnchorSettings.ACCENT_BASE_COLOR: "#FFC300",
            AnchorSettings.ACCENT_LIGHT_COLOR: "#FFD60A",
            AnchorSettings.ACCENT_DARK_COLOR: "#E3930D",
            AnchorSettings.ACCENT_VERY_LIGHT_COLOR: "#F2CD49",
            AnchorSettings.ACCENT_VERY_DARK_COLOR: "#7A4E03",
        }

        self.praat_theme = {
            AnchorSettings.MAIN_TEXT_COLOR: "#000000",
            AnchorSettings.SELECTED_TEXT_COLOR: "#FFFFFF",
            AnchorSettings.ERROR_COLOR: "#DC0806",
            AnchorSettings.PRIMARY_BASE_COLOR: "#FFFFFF",
            AnchorSettings.PRIMARY_LIGHT_COLOR: "#0078D7",
            AnchorSettings.PRIMARY_DARK_COLOR: "#A0A0A0",
            AnchorSettings.PRIMARY_VERY_LIGHT_COLOR: "#F0F0F0",
            AnchorSettings.PRIMARY_VERY_DARK_COLOR: "#FFFFFF",
            AnchorSettings.ACCENT_BASE_COLOR: "#000000",
            AnchorSettings.ACCENT_LIGHT_COLOR: "#FAF205",
            AnchorSettings.ACCENT_DARK_COLOR: "#000000",
            AnchorSettings.ACCENT_VERY_LIGHT_COLOR: "#000000",
            AnchorSettings.ACCENT_VERY_DARK_COLOR: "#000000",
        }

        self.default_values = {
            AnchorSettings.CORPORA: [],
            AnchorSettings.CURRENT_CORPUS: "",
            AnchorSettings.DEFAULT_DIRECTORY: str(get_temporary_directory()),
            AnchorSettings.AUTOSAVE: False,
            AnchorSettings.AUTOLOAD: False,
            AnchorSettings.VOLUME: 100,
            AnchorSettings.AUDIO_DEVICE: None,
            AnchorSettings.GEOMETRY: None,
            AnchorSettings.WINDOW_STATE: None,
            AnchorSettings.FONT: QtGui.QFont("Noto Sans", 12).toString(),
            AnchorSettings.PLAY_KEYBIND: "Tab",
            AnchorSettings.DELETE_KEYBIND: "Delete",
            AnchorSettings.SAVE_KEYBIND: "Ctrl+S",
            AnchorSettings.SEARCH_KEYBIND: "Ctrl+F",
            AnchorSettings.SPLIT_KEYBIND: "Ctrl+D",
            AnchorSettings.MERGE_KEYBIND: "Ctrl+M",
            AnchorSettings.ZOOM_IN_KEYBIND: "Ctrl+I",
            AnchorSettings.ZOOM_OUT_KEYBIND: "Ctrl+O",
            AnchorSettings.ZOOM_TO_SELECTION_KEYBIND: "Ctrl+N",
            AnchorSettings.PAN_LEFT_KEYBIND: "LeftArrow",
            AnchorSettings.PAN_RIGHT_KEYBIND: "RightArrow",
            AnchorSettings.UNDO_KEYBIND: "Ctrl+Z",
            AnchorSettings.REDO_KEYBIND: "Ctrl+Shift+Z",
            AnchorSettings.RESULTS_PER_PAGE: 100,
            AnchorSettings.SPEC_DYNAMIC_RANGE: 50,
            AnchorSettings.SPEC_N_FFT: 256,
            AnchorSettings.SPEC_N_TIME_STEPS: 1000,
            AnchorSettings.SPEC_MAX_FREQ: 5000,
            AnchorSettings.SPEC_WINDOW_SIZE: 0.005,
            AnchorSettings.SPEC_PREEMPH: 0.97,
            AnchorSettings.CUDA: True,
            AnchorSettings.TIME_DIRECTION: AnchorSettings.LTR,
            AnchorSettings.CLUSTERING_PERPLEXITY: 30.0,
            AnchorSettings.CLUSTERING_DISTANCE_THRESHOLD: 0.0,
            AnchorSettings.CLUSTERING_METRIC: "cosine",
            AnchorSettings.PITCH_MIN_F0: 50,
            AnchorSettings.PITCH_MAX_F0: 600,
            AnchorSettings.PITCH_FRAME_SHIFT: 10,
            AnchorSettings.PITCH_FRAME_LENGTH: 25,
            AnchorSettings.PITCH_PENALTY_FACTOR: 0.1,
            AnchorSettings.PITCH_DELTA_PITCH: 0.005,
            AnchorSettings.LOCKED: True,
            AnchorSettings.UTTERANCES_VISIBLE: True,
            AnchorSettings.DICTIONARY_VISIBLE: False,
            AnchorSettings.OOV_VISIBLE: False,
            AnchorSettings.SPEAKERS_VISIBLE: False,
            AnchorSettings.LM_VISIBLE: False,
            AnchorSettings.AM_VISIBLE: False,
            AnchorSettings.TRANSCRIPTION_VISIBLE: False,
            AnchorSettings.ALIGNMENT_VISIBLE: False,
            AnchorSettings.DIARIZATION_VISIBLE: False,
            AnchorSettings.TIER_NORMALIZED_VISIBLE: False,
            AnchorSettings.TIER_ALIGNED_WORDS_VISIBLE: True,
            AnchorSettings.TIER_ALIGNED_PHONES_VISIBLE: True,
            AnchorSettings.TIER_REFERENCE_PHONES_VISIBLE: True,
            AnchorSettings.TIER_TRANSCRIPTION_VISIBLE: True,
            AnchorSettings.TIER_TRANSCRIBED_WORDS_VISIBLE: True,
            AnchorSettings.TIER_TRANSCRIBED_PHONES_VISIBLE: True,
        }
        self.default_values.update(self.mfa_theme)
        self.border_radius = 5
        self.text_padding = 2
        self.border_width = 2
        self.base_menu_button_width = 16
        self.menu_button_width = self.base_menu_button_width + self.border_width * 2

        self.sort_indicator_size = 20
        self.sort_indicator_padding = 15
        self.scroll_bar_height = 25
        self.icon_size = 25
        self.scroll_bar_border_radius = int(self.scroll_bar_height / 2) - 2
        self.tier_visibility_mapping = {
            "Normalized text": AnchorSettings.TIER_NORMALIZED_VISIBLE,
            "Words": AnchorSettings.TIER_ALIGNED_WORDS_VISIBLE,
            "Phones": AnchorSettings.TIER_ALIGNED_PHONES_VISIBLE,
            "Reference": AnchorSettings.TIER_REFERENCE_PHONES_VISIBLE,
            "Transcription": AnchorSettings.TIER_TRANSCRIPTION_VISIBLE,
            "Transcribed words": AnchorSettings.TIER_TRANSCRIBED_WORDS_VISIBLE,
            "Transcribed phones": AnchorSettings.TIER_TRANSCRIBED_PHONES_VISIBLE,
        }

    @property
    def right_to_left(self) -> bool:
        return self.value(AnchorSettings.TIME_DIRECTION) == AnchorSettings.RTL

    @property
    def visible_tiers(self):
        return {
            "Normalized text": self.value(AnchorSettings.TIER_NORMALIZED_VISIBLE),
            "Words": self.value(AnchorSettings.TIER_ALIGNED_WORDS_VISIBLE),
            "Phones": self.value(AnchorSettings.TIER_ALIGNED_PHONES_VISIBLE),
            "Reference": self.value(AnchorSettings.TIER_REFERENCE_PHONES_VISIBLE),
            "Transcription": self.value(AnchorSettings.TIER_TRANSCRIPTION_VISIBLE),
            "Transcribed words": self.value(AnchorSettings.TIER_TRANSCRIBED_WORDS_VISIBLE),
            "Transcribed phones": self.value(AnchorSettings.TIER_TRANSCRIBED_PHONES_VISIBLE),
        }

    def value(self, arg__1: str, defaultValue: Optional[Any] = ..., t: object = ...) -> Any:
        if arg__1 == AnchorSettings.FONT:
            value = QtGui.QFont()
            value.fromString(
                super(AnchorSettings, self).value(arg__1, self.default_values[arg__1])
            )
        elif "color" in arg__1:
            value = QtGui.QColor(
                super(AnchorSettings, self).value(arg__1, self.default_values[arg__1])
            )
        elif "keybind" in arg__1:
            value = QtGui.QKeySequence(
                super(AnchorSettings, self).value(arg__1, self.default_values[arg__1])
            )
        elif "auto" in arg__1:
            value = super(AnchorSettings, self).value(arg__1, self.default_values[arg__1], bool)
        elif arg__1 in {
            AnchorSettings.GEOMETRY,
            AnchorSettings.WINDOW_STATE,
            AnchorSettings.AUDIO_DEVICE,
        }:
            value = super(AnchorSettings, self).value(arg__1, self.default_values[arg__1])
        else:
            value = super(AnchorSettings, self).value(
                arg__1,
                self.default_values.get(arg__1, ""),
                type=type(self.default_values.get(arg__1, "")),
            )
            if isinstance(value, float):
                value = round(value, 6)

        return value

    @property
    def temp_directory(self) -> pathlib.Path:
        return get_temporary_directory()

    @property
    def font(self) -> QtGui.QFont:
        font = self.value(AnchorSettings.FONT)
        return font

    @property
    def big_font(self) -> QtGui.QFont:
        font = self.value(AnchorSettings.FONT)
        font.setPointSize(int(1.25 * font.pointSize()))
        return font

    @property
    def small_font(self) -> QtGui.QFont:
        font = self.value(AnchorSettings.FONT)
        font.setPointSize(int(0.75 * font.pointSize()))
        return font

    @property
    def title_font(self) -> QtGui.QFont:
        font = self.value(AnchorSettings.FONT)
        font.setPointSize(int(3 * font.pointSize()))
        return font

    def set_mfa_theme(self):
        for k, v in self.mfa_theme.items():
            self.setValue(k, v)

    def set_praat_theme(self):
        for k, v in self.praat_theme.items():
            self.setValue(k, v)

    @property
    def plot_theme(self):
        return {
            "background_color": self.value(AnchorSettings.PRIMARY_VERY_DARK_COLOR),
            "play_line_color": self.value(AnchorSettings.ERROR_COLOR),
            "selected_range_color": self.value(AnchorSettings.PRIMARY_VERY_LIGHT_COLOR),
            "selected_interval_color": self.value(AnchorSettings.PRIMARY_BASE_COLOR),
            "hover_line_color": self.value(AnchorSettings.PRIMARY_VERY_LIGHT_COLOR),
            "moving_line_color": self.value(AnchorSettings.ERROR_COLOR),
            "break_line_color": self.value(AnchorSettings.ACCENT_LIGHT_COLOR),
            "wave_line_color": self.value(AnchorSettings.MAIN_TEXT_COLOR),
            "text_color": self.value(AnchorSettings.MAIN_TEXT_COLOR),
            "selected_text_color": self.value(AnchorSettings.MAIN_TEXT_COLOR),
            "axis_color": self.value(AnchorSettings.ACCENT_LIGHT_COLOR),
            "interval_background_color": self.value(AnchorSettings.PRIMARY_DARK_COLOR),
        }

    @property
    def error_color(self) -> QtGui.QColor:
        return self.value(AnchorSettings.ERROR_COLOR)

    @property
    def selected_text_color(self) -> QtGui.QColor:
        return self.value(AnchorSettings.SELECTED_TEXT_COLOR)

    @property
    def text_color(self) -> QtGui.QColor:
        return self.value(AnchorSettings.MAIN_TEXT_COLOR)

    @property
    def primary_base_color(self) -> QtGui.QColor:
        return self.value(AnchorSettings.PRIMARY_BASE_COLOR)

    @property
    def primary_light_color(self) -> QtGui.QColor:
        return self.value(AnchorSettings.PRIMARY_LIGHT_COLOR)

    @property
    def primary_dark_color(self) -> QtGui.QColor:
        return self.value(AnchorSettings.PRIMARY_DARK_COLOR)

    @property
    def primary_very_light_color(self) -> QtGui.QColor:
        return self.value(AnchorSettings.PRIMARY_VERY_LIGHT_COLOR)

    @property
    def primary_very_dark_color(self) -> QtGui.QColor:
        return self.value(AnchorSettings.PRIMARY_VERY_DARK_COLOR)

    @property
    def accent_base_color(self) -> QtGui.QColor:
        return self.value(AnchorSettings.ACCENT_BASE_COLOR)

    @property
    def accent_light_color(self) -> QtGui.QColor:
        return self.value(AnchorSettings.ACCENT_LIGHT_COLOR)

    @property
    def accent_dark_color(self) -> QtGui.QColor:
        return self.value(AnchorSettings.ACCENT_DARK_COLOR)

    @property
    def accent_very_light_color(self) -> QtGui.QColor:
        return self.value(AnchorSettings.ACCENT_VERY_LIGHT_COLOR)

    @property
    def accent_very_dark_color(self) -> QtGui.QColor:
        return self.value(AnchorSettings.ACCENT_VERY_DARK_COLOR)

    @property
    def keyboard_style_sheet(self) -> str:
        border_color = self.accent_base_color.name()
        background_color = self.primary_light_color.name()

        enabled_color = self.primary_very_dark_color.name()
        enabled_background_color = self.accent_base_color.name()
        enabled_border_color = self.primary_very_dark_color.name()
        scroll_bar_style = self.scroll_bar_style_sheet
        return f"""
        QWidget{{
            background-color: {background_color};
        }}
        QMenu{{
            border-width: {self.border_width}px;
            border-style: solid;
            border-color: {border_color};
            border-radius: {self.border_radius}px;
        }}
        QScrollArea {{
            border: none;
        }}
        QPushButton {{
            background-color: {enabled_background_color};
            color: {enabled_color};
            padding: {self.text_padding}px;
            border-width: {self.border_width}px;
            border-style: solid;
            border-color: {enabled_border_color};
            border-radius: {self.border_radius}px;
        }}
        {scroll_bar_style}
        """

    @property
    def search_box_style_sheet(self) -> str:
        line_edit_color = self.primary_very_dark_color.name()
        line_edit_background_color = self.accent_base_color.name()
        error_color = self.error_color.name()
        return f"""
        QWidget{{
            background-color: {line_edit_background_color};
        }}
         QLineEdit[error="true"] {{
            color: {error_color};
            font-weight: bold;
        }}
        QMenu {{ menu-scrollable: 1; }}
        QLineEdit QToolButton {{
                        background-color: {line_edit_background_color};
                        color: {line_edit_color};
                        margin: {self.border_width}px;
        }}
        QToolButton#clear_search_field, QToolButton#clear_field, QToolButton#clear_new_speaker_field,
        QToolButton#regex_search_field, QToolButton#word_search_field {{
                        background-color: none;
                        border: none;
                        padding: {self.border_width}px;
        }}
    """

    @property
    def combo_box_style_sheet(self) -> str:
        enabled_color = self.primary_very_dark_color.name()
        enabled_background_color = self.accent_base_color.name()

        hover_background_color = self.primary_very_light_color.name()
        return f"""
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
        """

    @property
    def interval_style_sheet(self):
        text_edit_color = self.text_color.name()

        scroll_bar_background_color = self.primary_dark_color.name()
        scroll_bar_handle_color = self.accent_light_color.name()
        scroll_bar_border_color = self.primary_dark_color.name()
        border_color = self.primary_light_color.name()
        scroll_bar_height = 10
        scroll_bar_border_radius = int(scroll_bar_height / 2) - 2

        return f"""
        QTextEdit {{
            background-color: rgba(0, 0, 0, 0%);
            color: {text_edit_color};
            border: 5px inset {border_color};
        }}
        QScrollBar {{
            color: {scroll_bar_handle_color};
            background: {scroll_bar_background_color};
            border: {self.border_width}px solid {scroll_bar_border_color};
        }}
        QScrollBar:vertical {{
            width: {scroll_bar_height}px;
            border: 2px solid {scroll_bar_border_color};
            border-radius: {scroll_bar_border_radius + 2}px;
            margin-top: {scroll_bar_height}px;
            margin-bottom: {scroll_bar_height}px;
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
        QScrollBar::handle:vertical {{
            background: {scroll_bar_handle_color};
            min-height: {scroll_bar_height}px;
            border: 2px solid {scroll_bar_border_color};
            border-radius: {scroll_bar_border_radius}px;
        }}
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: none;
            height: {scroll_bar_height}px;
            width: {scroll_bar_height}px;
            padding: 0px;
            margin: 0px;
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
        }}"""

    @property
    def style_sheet(self):
        background_color = self.primary_base_color.name()

        selection_color = self.primary_light_color.name()
        error_color = self.error_color.name()

        text_edit_color = self.text_color.name()
        text_edit_background_color = self.primary_very_dark_color.name()

        enabled_color = self.primary_very_dark_color.name()
        enabled_background_color = self.accent_base_color.name()
        enabled_border_color = self.primary_very_dark_color.name()

        active_color = self.accent_light_color.name()
        active_background_color = self.primary_dark_color.name()
        active_border_color = self.primary_dark_color.name()

        hover_text_color = self.accent_very_light_color.name()
        hover_background_color = self.primary_very_light_color.name()
        hover_border_color = self.accent_very_light_color.name()

        disabled_text_color = self.primary_dark_color.name()
        disabled_background_color = self.accent_very_dark_color.name()
        disabled_border_color = self.primary_very_dark_color.name()

        table_text_color = self.primary_very_dark_color.name()
        table_odd_color = self.primary_very_light_color.name()
        table_even_color = self.accent_very_light_color.name()
        table_header_background_color = self.primary_light_color.name()

        table_header_color = self.text_color.name()

        main_widget_border_color = self.primary_very_light_color.name()
        main_widget_background_color = self.primary_very_dark_color.name()
        menu_background_color = self.accent_base_color.name()
        menu_text_color = self.primary_very_dark_color.name()
        line_edit_color = self.primary_very_dark_color.name()
        line_edit_background_color = self.accent_base_color.name()

        sheet = f"""
        QWidget{{
            background-color: {background_color};
        }}
        QProgressBar {{
            border: {self.border_width}px solid {enabled_border_color};
            color: {text_edit_color};
            background-color: {text_edit_background_color};
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: {background_color};
        }}
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
            color: {menu_text_color};
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
        #utteranceListWidget, #dictionaryWidget, #speakerWidget {{
            background-color: {text_edit_background_color};

            border: {self.border_width}px solid {main_widget_border_color};
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
            border: {self.border_width}px solid {main_widget_border_color};
            border-top-right-radius: {self.border_radius}px;
            border-bottom-right-radius: {self.border_radius}px;
        }}
        QTabWidget::pane, SearchWidget, DictionaryWidget, SpeakerWidget {{
            border-bottom-right-radius: {self.border_radius}px;
        }}
        QCheckBox::indicator{{
            width: {int(self.scroll_bar_height/2)}px;
            height: {int(self.scroll_bar_height/2)}px;
        }}
        QLineEdit, QSpinBox, QCheckBox::indicator, #pronunciation_field {{
            color: {line_edit_color};
            background-color: {line_edit_background_color};
            selection-background-color: {selection_color};
            border: {self.border_width}px solid {enabled_border_color};
        }}
        QCheckBox::indicator:checked {{
            image: url(:check.svg);
        }}
        QTextEdit{{
            color: {text_edit_color};
            background-color: {text_edit_background_color};
            selection-background-color: {selection_color};
            border: {self.border_width}px solid {enabled_border_color};
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
            border: {self.border_width}px solid {main_widget_border_color};
            border-top-color: {enabled_color};
            background-color: {main_widget_background_color};

        }}
        QTabBar::tab {{
            color: {menu_text_color};
            background-color: {menu_background_color};
            border-color: {enabled_border_color};
            border: {self.border_width / 2}px solid {enabled_border_color};
            border-top-color: {main_widget_border_color};
            border-bottom: none;

            min-width: 8ex;
            padding: {self.text_padding}px;
            margin: 0px;
        }}
        QTabBar::scroller{{
            width: {2 * self.scroll_bar_height}px;
        }}
        QTabBar QToolButton  {{
            border-radius: 0px;
        }}
        QTabBar QToolButton::right-arrow  {{
            image: url(:caret-right.svg);
            height: {self.scroll_bar_height}px;
            width: {self.scroll_bar_height}px;
        }}
        QTabBar QToolButton::right-arrow :pressed {{
            image: url(:checked/caret-right.svg);
        }}
        QTabBar QToolButton::right-arrow :disabled {{
            image: url(:disabled/caret-right.svg);
        }}
        QTabBar QToolButton::left-arrow  {{
            image: url(:caret-left.svg);
            height: {self.scroll_bar_height}px;
            width: {self.scroll_bar_height}px;
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
            border: {self.border_width}px solid {main_widget_border_color};
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
            margin-left: -{self.border_width}px;
            margin-right: -{self.border_width}px;
            border-color: {active_border_color};
            border-bottom-color:  {active_border_color};
        }}
        QTabBar::tab:first {{
            border-left-width: {self.border_width}px;
            margin-left: 0px;
        }}
        QTabBar::tab:last {{
            border-right-width: {self.border_width}px;
            margin-right: 0px;
        }}
        QToolBar {{
            spacing: 3px;
        }}
        #toolBar {{
            background: rgb(0, 8, 20);
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
            padding: {self.text_padding}px;
            border-width: {self.border_width}px;
            border-style: solid;
            border-color: {enabled_border_color};
            border-radius: {self.border_radius}px;
        }}
        QToolButton[popupMode="1"] {{ /* only for MenuButtonPopup */
            padding-right: {self.menu_button_width}px; /* make way for the popup button */
        }}
        QToolButton::menu-button {{
            border: {self.border_width}px solid {enabled_border_color};
            border-top-right-radius: {self.border_radius}px;
            border-bottom-right-radius: {self.border_radius}px;

            width: {self.base_menu_button_width}px;
        }}
        QMenuBar QToolButton{{
            padding: 0px;
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
        QGraphicsView {{
            border: {self.border_width}px solid {main_widget_border_color};
        }}
        QSlider::handle:horizontal {{
            height: 10px;
            background: {enabled_background_color};
            border: {self.border_width / 2}px solid {enabled_border_color};
            margin: 0 -2px; /* expand outside the groove */
        }}
        QSlider::handle:horizontal:hover {{
            height: 10px;
            background: {hover_background_color};
            border-color: {hover_border_color};
            margin: 0 -2px; /* expand outside the groove */
        }}
        QTableWidget, QTableView, QTreeView, QTreeWidget {{
            alternate-background-color: {table_even_color};
            selection-background-color: {selection_color};
            selection-color: {text_edit_color};
            background-color: {table_odd_color};
            color: {table_text_color};
            border: 4px solid {enabled_color};
        }}
       QTreeView QLabel, QTreeWidget QLabel{{
            color: {table_text_color};
        }}
        QTreeView::branch:has-children:closed{{
            alternate-background-color: {table_even_color};
            selection-background-color: {selection_color};
            border-image: none;
            image: url(:chevron-right.svg);
        }}
        QTreeView::branch:has-children:!closed{{
            alternate-background-color: {table_even_color};
            selection-background-color: {selection_color};
            border-image: none;
            image: url(:chevron-down.svg);
        }}
        QScrollArea {{
            border: 4px solid {enabled_color};
            background: {background_color};
        }}
        QHeaderView::up-arrow {{
            subcontrol-origin: padding;
            subcontrol-position: center right;
            image: url(:hover/sort-up.svg);
            height: {self.sort_indicator_size}px;
            width: {self.sort_indicator_size}px;
        }}
        QHeaderView::down-arrow {{
            image: url(:hover/sort-down.svg);
            subcontrol-origin: padding;
            subcontrol-position: center right;
            height: {self.sort_indicator_size}px;
            width: {self.sort_indicator_size}px;
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
            padding-left: {self.text_padding+3}px;
        }}
        QHeaderView::section:horizontal {{
            padding-right: {self.sort_indicator_padding}px;
        }}
        """

        sheet += self.scroll_bar_style_sheet
        sheet += self.menu_style_sheet
        sheet += self.tool_tip_style_sheet
        return sheet

    @property
    def tool_tip_style_sheet(self):
        background_color = self.accent_base_color.name()
        text_color = self.primary_very_dark_color.name()
        return f"""
        QToolTip {{
            background-color: {background_color};
            color: {text_color};
        }}
        """

    @property
    def menu_style_sheet(self):
        menu_background_color = self.accent_base_color.name()
        menu_text_color = self.primary_very_dark_color.name()
        disabled_text_color = self.primary_dark_color.name()
        disabled_background_color = self.accent_very_dark_color.name()
        enabled_color = self.primary_very_dark_color.name()
        selection_color = self.primary_light_color.name()
        return f"""
        QMenu {{
                border: 1px solid {enabled_color};
                background-color: {menu_background_color};
                color: {menu_text_color};
                menu-scrollable: 1;
        }}
        QMenu::item {{
                padding: 2px 25px 2px 20px;
                border: {self.border_width / 2}px solid transparent;
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
        }}"""

    @property
    def completer_style_sheet(self):
        menu_background_color = self.accent_base_color.name()
        menu_text_color = self.primary_very_dark_color.name()
        disabled_text_color = self.primary_dark_color.name()
        disabled_background_color = self.accent_very_dark_color.name()
        enabled_color = self.primary_very_dark_color.name()
        selection_color = self.primary_light_color.name()
        scroll_bar_background_color = self.primary_dark_color.name()
        scroll_bar_handle_color = self.accent_light_color.name()
        scroll_bar_border_color = self.primary_dark_color.name()
        scroll_bar_height = int(self.scroll_bar_height / 2)
        scroll_bar_border_radius = int(scroll_bar_height / 2) - 2
        return f"""
        QListView {{
                margin: 2px;
                background-color: {menu_background_color};
                color: {menu_text_color};
                menu-scrollable: 1;
        }}
        QMenu::item {{
                padding: 2px 25px 2px 20px;
                border: {self.border_width / 2}px solid transparent;
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
        QScrollBar {{
            color: {scroll_bar_handle_color};
            background: {scroll_bar_background_color};
            border: {self.border_width}px solid {scroll_bar_border_color};
        }}
        QScrollBar:vertical {{
            width: {scroll_bar_height}px;
            border: 2px solid {scroll_bar_border_color};
            border-radius: {scroll_bar_border_radius + 2}px;
            margin-top: {scroll_bar_height}px;
            margin-bottom: {scroll_bar_height}px;
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

        QScrollBar::handle:vertical {{
            background: {scroll_bar_handle_color};
            min-height: {scroll_bar_height}px;
            border: 2px solid {scroll_bar_border_color};
            border-radius: {scroll_bar_border_radius}px;
        }}
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: none;
            height: {scroll_bar_height}px;
            width: {scroll_bar_height}px;
            padding: 0px;
            margin: 0px;
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
        }}"""

    @property
    def scroll_bar_style_sheet(self):
        scroll_bar_background_color = self.primary_dark_color.name()
        scroll_bar_handle_color = self.accent_light_color.name()
        scroll_bar_border_color = self.primary_dark_color.name()

        return f"""
        QScrollBar {{
            color: {scroll_bar_handle_color};
            background: {scroll_bar_background_color};
            border: {self.border_width}px solid {scroll_bar_border_color};
        }}
        QScrollBar#time_scroll_bar {{
            color: {scroll_bar_handle_color};
            background: {scroll_bar_background_color};
            border: {self.border_width}px solid {scroll_bar_border_color};
            margin-left: 0px;
            margin-right: 0px;
        }}
        QScrollBar:horizontal {{
            height: {self.scroll_bar_height}px;
            border: 2px solid {scroll_bar_border_color};
            border-radius: {self.scroll_bar_border_radius + 2}px;
            margin-left: {self.scroll_bar_height}px;
            margin-right: {self.scroll_bar_height}px;
        }}
        QScrollBar:vertical {{
            width: {self.scroll_bar_height}px;
            border: 2px solid {scroll_bar_border_color};
            border-radius: {self.scroll_bar_border_radius + 2}px;
            margin-top: {self.scroll_bar_height}px;
            margin-bottom: {self.scroll_bar_height}px;
        }}

        QScrollBar:left-arrow:horizontal {{
            image: url(:caret-left.svg);
            height: {self.scroll_bar_height}px;
            width: {self.scroll_bar_height}px;
        }}
        QScrollBar:left-arrow:horizontal:pressed {{
            image: url(:checked/caret-left.svg);
        }}

        QScrollBar:right-arrow:horizontal {{
            image: url(:caret-right.svg);
            height: {self.scroll_bar_height}px;
            width: {self.scroll_bar_height}px;
        }}
        QScrollBar:right-arrow:horizontal:pressed {{
            image: url(:checked/caret-right.svg);
        }}

        QScrollBar:up-arrow:vertical {{
            image: url(:caret-up.svg);
            height: {self.scroll_bar_height}px;
            width: {self.scroll_bar_height}px;
        }}
        QScrollBar:up-arrow:vertical:pressed {{
            image: url(:checked/caret-up.svg);
        }}

        QScrollBar:down-arrow:vertical {{
            image: url(:caret-down.svg);
            height: {self.scroll_bar_height}px;
            width: {self.scroll_bar_height}px;
        }}
        QScrollBar:down-arrow:vertical:pressed {{
            image: url(:checked/caret-down.svg);
        }}

        QScrollBar::handle:horizontal {{
            background: {scroll_bar_handle_color};
            min-width: {self.scroll_bar_height}px;
            border: 2px solid {scroll_bar_border_color};
            border-radius: {self.scroll_bar_border_radius}px;
        }}

        QScrollBar::handle:vertical {{
            background: {scroll_bar_handle_color};
            min-height: {self.scroll_bar_height}px;
            border: 2px solid {scroll_bar_border_color};
            border-radius: {self.scroll_bar_border_radius}px;
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
            height: {self.scroll_bar_height}px;
            width: {self.scroll_bar_height}px;
            padding: 0px;
            margin: 0px;
        }}

        QScrollBar::add-line:horizontal {{
            background: none;
            subcontrol-position: right;
            subcontrol-origin: margin;
            width: {self.scroll_bar_height}px;
        }}

        QScrollBar::sub-line:horizontal {{
            background: none;
            subcontrol-position: left;
            subcontrol-origin: margin;
            width: {self.scroll_bar_height}px;
        }}

        QScrollBar::add-line:vertical {{
            background: none;
            subcontrol-position: bottom;
            subcontrol-origin: margin;
            height: {self.scroll_bar_height}px;
        }}

        QScrollBar::sub-line:vertical {{
            background: none;
            subcontrol-position: top;
            subcontrol-origin: margin;
            height: {self.scroll_bar_height}px;
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
        """
