"""Centralised colour and style constants for the UI layer.

All hex colour values used in stylesheets should be defined here so the
design system is explicit and grep-able.  The module exposes two palettes
(``LIGHT_PALETTE`` and ``DARK_PALETTE``) and a set of *mutable* module-level
colour aliases (``COLOR_TEXT``, ``COLOR_BORDER``, etc.) that
``ThemeManager.apply()`` updates at runtime.

Widget code should import and use the module-level aliases; they always
reflect the currently active palette.
"""

from __future__ import annotations

from typing import TypedDict


# -- Palette schema ----------------------------------------------------
class ThemePalette(TypedDict):
    """Colour slots consumed by the global stylesheet and widget code."""

    # Neutral
    bg: str
    bg_alt: str
    text: str
    text_muted: str
    border: str
    hover_bg: str
    hover_tree_bg: str
    selected_bg: str
    input_bg: str

    # Semantic
    accent: str
    success: str
    warning: str
    danger: str
    muted: str
    delete: str
    head: str
    options: str

    # Functional
    sending: str
    breadcrumb_sep: str

    # Import dialog
    drop_zone_border: str
    drop_zone_bg: str
    drop_zone_active_bg: str
    import_success: str
    import_error: str

    # Console
    console_bg: str
    console_text: str

    # Timing breakdown
    timing_prepare: str
    timing_dns: str
    timing_tcp: str
    timing_tls: str
    timing_ttfb: str
    timing_download: str
    timing_process: str

    # Code editor
    editor_bracket_match: str
    editor_gutter_bg: str
    editor_gutter_text: str
    editor_error_underline: str
    editor_fold_indicator: str
    editor_string: str
    editor_number: str
    editor_keyword: str
    editor_comment: str
    editor_tag: str
    editor_attribute: str
    editor_punctuation: str
    editor_fold_highlight: str
    editor_indent_guide: str
    editor_active_indent_guide: str
    editor_error_gutter_bg: str
    editor_fold_badge_bg: str
    editor_fold_badge_text: str
    editor_whitespace_dot: str


# -- Light palette -----------------------------------------------------
LIGHT_PALETTE: ThemePalette = {
    "bg": "#ffffff",
    "bg_alt": "#fafafa",
    "text": "#444444",
    "text_muted": "#888888",
    "border": "#cccccc",
    "hover_bg": "#c7c7c7",
    "hover_tree_bg": "#e8e8e8",
    "selected_bg": "#d0e4f7",
    "input_bg": "#ffffff",
    "accent": "#3498db",
    "success": "#2ecc71",
    "warning": "#e89a0c",
    "danger": "#e74c3c",
    "muted": "#95a5a6",
    "delete": "#e67e22",
    "head": "#27ae60",
    "options": "#9b59b6",
    "sending": "#f39c12",
    "breadcrumb_sep": "#aaaaaa",
    "drop_zone_border": "#b0b0b0",
    "drop_zone_bg": "#fafafa",
    "drop_zone_active_bg": "#e8f4fd",
    "import_success": "#27ae60",
    "import_error": "#e74c3c",
    "console_bg": "#1e1e1e",
    "console_text": "#d4d4d4",
    "timing_prepare": "#95a5a6",
    "timing_dns": "#3498db",
    "timing_tcp": "#2ecc71",
    "timing_tls": "#9b59b6",
    "timing_ttfb": "#e89a0c",
    "timing_download": "#e67e22",
    "timing_process": "#e74c3c",
    "editor_bracket_match": "#d4edda",
    "editor_gutter_bg": "#fafafa",
    "editor_gutter_text": "#999999",
    "editor_error_underline": "#e74c3c",
    "editor_fold_indicator": "#555555",
    "editor_string": "#22863a",
    "editor_number": "#005cc5",
    "editor_keyword": "#d73a49",
    "editor_comment": "#6a737d",
    "editor_tag": "#22863a",
    "editor_attribute": "#6f42c1",
    "editor_punctuation": "#586069",
    "editor_fold_highlight": "#f0f4ff",
    "editor_indent_guide": "#e0e0e0",
    "editor_active_indent_guide": "#b0b0b0",
    "editor_error_gutter_bg": "#fce4e4",
    "editor_fold_badge_bg": "#e0e6ed",
    "editor_fold_badge_text": "#6a737d",
    "editor_whitespace_dot": "#b0b0b0",
}

# -- Dark palette ------------------------------------------------------
DARK_PALETTE: ThemePalette = {
    "bg": "#1e1e1e",
    "bg_alt": "#252526",
    "text": "#d4d4d4",
    "text_muted": "#808080",
    "border": "#3c3c3c",
    "hover_bg": "#2a2d2e",
    "hover_tree_bg": "#2a2d2e",
    "selected_bg": "#094771",
    "input_bg": "#2d2d2d",
    "accent": "#4fc1ff",
    "success": "#4ec9b0",
    "warning": "#dcdcaa",
    "danger": "#f44747",
    "muted": "#808080",
    "delete": "#ce9178",
    "head": "#4ec9b0",
    "options": "#c586c0",
    "sending": "#f39c12",
    "breadcrumb_sep": "#666666",
    "drop_zone_border": "#555555",
    "drop_zone_bg": "#252526",
    "drop_zone_active_bg": "#1a3a4a",
    "import_success": "#4ec9b0",
    "import_error": "#f44747",
    "console_bg": "#1e1e1e",
    "console_text": "#d4d4d4",
    "timing_prepare": "#808080",
    "timing_dns": "#4fc1ff",
    "timing_tcp": "#4ec9b0",
    "timing_tls": "#c586c0",
    "timing_ttfb": "#dcdcaa",
    "timing_download": "#ce9178",
    "timing_process": "#f44747",
    "editor_bracket_match": "#2a4a3a",
    "editor_gutter_bg": "#252526",
    "editor_gutter_text": "#858585",
    "editor_error_underline": "#f44747",
    "editor_fold_indicator": "#c0c0c0",
    "editor_string": "#ce9178",
    "editor_number": "#b5cea8",
    "editor_keyword": "#569cd6",
    "editor_comment": "#6a9955",
    "editor_tag": "#569cd6",
    "editor_attribute": "#9cdcfe",
    "editor_punctuation": "#808080",
    "editor_fold_highlight": "#2a2d3a",
    "editor_indent_guide": "#333333",
    "editor_active_indent_guide": "#606060",
    "editor_error_gutter_bg": "#4a2020",
    "editor_fold_badge_bg": "#3a3d4a",
    "editor_fold_badge_text": "#a0a0a0",
    "editor_whitespace_dot": "#606060",
}


# -- Active palette reference -----------------------------------------
# ThemeManager.apply() replaces this with LIGHT_PALETTE or DARK_PALETTE.
_active: ThemePalette = dict(LIGHT_PALETTE)  # type: ignore[assignment]

# -- Mutable module-level colour aliases -------------------------------
# These are updated by ``set_active_palette()`` so widgets that import
# them at *call time* (inside functions/methods) always see the current
# palette.  Widgets that capture a colour at *import time* (module scope)
# will keep the value from when the module was first loaded; that is fine
# for the initial render and ``ThemeManager.theme_changed`` handles the
# rest by triggering a global stylesheet refresh.

COLOR_ACCENT: str = _active["accent"]
COLOR_SUCCESS: str = _active["success"]
COLOR_WARNING: str = _active["warning"]
COLOR_DANGER: str = _active["danger"]
COLOR_MUTED: str = _active["muted"]
COLOR_DELETE: str = _active["delete"]
COLOR_HEAD: str = _active["head"]
COLOR_OPTIONS: str = _active["options"]

COLOR_WHITE: str = _active["bg"]
COLOR_TEXT: str = _active["text"]
COLOR_TEXT_MUTED: str = _active["text_muted"]
COLOR_BORDER: str = _active["border"]
COLOR_HOVER_BG: str = _active["hover_bg"]
COLOR_HOVER_TREE_BG: str = _active["hover_tree_bg"]
COLOR_SELECTED_BG: str = _active["selected_bg"]

COLOR_SENDING: str = _active["sending"]

COLOR_CONSOLE_BG: str = _active["console_bg"]
COLOR_CONSOLE_TEXT: str = _active["console_text"]

COLOR_BREADCRUMB_SEP: str = _active["breadcrumb_sep"]

COLOR_DROP_ZONE_BORDER: str = _active["drop_zone_border"]
COLOR_DROP_ZONE_BG: str = _active["drop_zone_bg"]
COLOR_DROP_ZONE_ACTIVE_BG: str = _active["drop_zone_active_bg"]
COLOR_IMPORT_SUCCESS: str = _active["import_success"]
COLOR_IMPORT_ERROR: str = _active["import_error"]

COLOR_TIMING_PREPARE: str = _active["timing_prepare"]
COLOR_TIMING_DNS: str = _active["timing_dns"]
COLOR_TIMING_TCP: str = _active["timing_tcp"]
COLOR_TIMING_TLS: str = _active["timing_tls"]
COLOR_TIMING_TTFB: str = _active["timing_ttfb"]
COLOR_TIMING_DOWNLOAD: str = _active["timing_download"]
COLOR_TIMING_PROCESS: str = _active["timing_process"]

COLOR_EDITOR_BRACKET_MATCH: str = _active["editor_bracket_match"]
COLOR_EDITOR_GUTTER_BG: str = _active["editor_gutter_bg"]
COLOR_EDITOR_GUTTER_TEXT: str = _active["editor_gutter_text"]
COLOR_EDITOR_ERROR_UNDERLINE: str = _active["editor_error_underline"]
COLOR_EDITOR_FOLD_INDICATOR: str = _active["editor_fold_indicator"]
COLOR_EDITOR_STRING: str = _active["editor_string"]
COLOR_EDITOR_NUMBER: str = _active["editor_number"]
COLOR_EDITOR_KEYWORD: str = _active["editor_keyword"]
COLOR_EDITOR_COMMENT: str = _active["editor_comment"]
COLOR_EDITOR_TAG: str = _active["editor_tag"]
COLOR_EDITOR_ATTRIBUTE: str = _active["editor_attribute"]
COLOR_EDITOR_PUNCTUATION: str = _active["editor_punctuation"]
COLOR_EDITOR_FOLD_HIGHLIGHT: str = _active["editor_fold_highlight"]
COLOR_EDITOR_INDENT_GUIDE: str = _active["editor_indent_guide"]
COLOR_EDITOR_ACTIVE_INDENT_GUIDE: str = _active["editor_active_indent_guide"]
COLOR_EDITOR_ERROR_GUTTER_BG: str = _active["editor_error_gutter_bg"]
COLOR_EDITOR_FOLD_BADGE_BG: str = _active["editor_fold_badge_bg"]
COLOR_EDITOR_FOLD_BADGE_TEXT: str = _active["editor_fold_badge_text"]
COLOR_EDITOR_WHITESPACE_DOT: str = _active["editor_whitespace_dot"]


def set_active_palette(palette: ThemePalette) -> None:
    """Replace the module-level colour aliases with values from *palette*.

    Called by ``ThemeManager.apply()`` — widget code should **not** call
    this directly.
    """
    global _active
    global COLOR_ACCENT, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER
    global COLOR_MUTED, COLOR_DELETE, COLOR_HEAD, COLOR_OPTIONS
    global COLOR_WHITE, COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_BORDER
    global COLOR_HOVER_BG, COLOR_HOVER_TREE_BG, COLOR_SELECTED_BG
    global COLOR_SENDING
    global COLOR_CONSOLE_BG, COLOR_CONSOLE_TEXT
    global COLOR_BREADCRUMB_SEP
    global COLOR_DROP_ZONE_BORDER, COLOR_DROP_ZONE_BG
    global COLOR_DROP_ZONE_ACTIVE_BG
    global COLOR_IMPORT_SUCCESS, COLOR_IMPORT_ERROR
    global COLOR_TIMING_PREPARE, COLOR_TIMING_DNS, COLOR_TIMING_TCP
    global COLOR_TIMING_TLS, COLOR_TIMING_TTFB, COLOR_TIMING_DOWNLOAD
    global COLOR_TIMING_PROCESS
    global COLOR_EDITOR_BRACKET_MATCH, COLOR_EDITOR_GUTTER_BG
    global COLOR_EDITOR_GUTTER_TEXT, COLOR_EDITOR_ERROR_UNDERLINE
    global COLOR_EDITOR_FOLD_INDICATOR
    global COLOR_EDITOR_STRING, COLOR_EDITOR_NUMBER, COLOR_EDITOR_KEYWORD
    global COLOR_EDITOR_COMMENT, COLOR_EDITOR_TAG, COLOR_EDITOR_ATTRIBUTE
    global COLOR_EDITOR_PUNCTUATION
    global COLOR_EDITOR_FOLD_HIGHLIGHT, COLOR_EDITOR_INDENT_GUIDE
    global COLOR_EDITOR_ACTIVE_INDENT_GUIDE
    global COLOR_EDITOR_ERROR_GUTTER_BG
    global COLOR_EDITOR_FOLD_BADGE_BG, COLOR_EDITOR_FOLD_BADGE_TEXT
    global COLOR_EDITOR_WHITESPACE_DOT

    _active = palette

    COLOR_ACCENT = palette["accent"]
    COLOR_SUCCESS = palette["success"]
    COLOR_WARNING = palette["warning"]
    COLOR_DANGER = palette["danger"]
    COLOR_MUTED = palette["muted"]
    COLOR_DELETE = palette["delete"]
    COLOR_HEAD = palette["head"]
    COLOR_OPTIONS = palette["options"]

    COLOR_WHITE = palette["bg"]
    COLOR_TEXT = palette["text"]
    COLOR_TEXT_MUTED = palette["text_muted"]
    COLOR_BORDER = palette["border"]
    COLOR_HOVER_BG = palette["hover_bg"]
    COLOR_HOVER_TREE_BG = palette["hover_tree_bg"]
    COLOR_SELECTED_BG = palette["selected_bg"]

    COLOR_SENDING = palette["sending"]

    COLOR_CONSOLE_BG = palette["console_bg"]
    COLOR_CONSOLE_TEXT = palette["console_text"]

    COLOR_BREADCRUMB_SEP = palette["breadcrumb_sep"]

    COLOR_DROP_ZONE_BORDER = palette["drop_zone_border"]
    COLOR_DROP_ZONE_BG = palette["drop_zone_bg"]
    COLOR_DROP_ZONE_ACTIVE_BG = palette["drop_zone_active_bg"]
    COLOR_IMPORT_SUCCESS = palette["import_success"]
    COLOR_IMPORT_ERROR = palette["import_error"]

    COLOR_TIMING_PREPARE = palette["timing_prepare"]
    COLOR_TIMING_DNS = palette["timing_dns"]
    COLOR_TIMING_TCP = palette["timing_tcp"]
    COLOR_TIMING_TLS = palette["timing_tls"]
    COLOR_TIMING_TTFB = palette["timing_ttfb"]
    COLOR_TIMING_DOWNLOAD = palette["timing_download"]
    COLOR_TIMING_PROCESS = palette["timing_process"]

    COLOR_EDITOR_BRACKET_MATCH = palette["editor_bracket_match"]
    COLOR_EDITOR_GUTTER_BG = palette["editor_gutter_bg"]
    COLOR_EDITOR_GUTTER_TEXT = palette["editor_gutter_text"]
    COLOR_EDITOR_ERROR_UNDERLINE = palette["editor_error_underline"]
    COLOR_EDITOR_FOLD_INDICATOR = palette["editor_fold_indicator"]
    COLOR_EDITOR_STRING = palette["editor_string"]
    COLOR_EDITOR_NUMBER = palette["editor_number"]
    COLOR_EDITOR_KEYWORD = palette["editor_keyword"]
    COLOR_EDITOR_COMMENT = palette["editor_comment"]
    COLOR_EDITOR_TAG = palette["editor_tag"]
    COLOR_EDITOR_ATTRIBUTE = palette["editor_attribute"]
    COLOR_EDITOR_PUNCTUATION = palette["editor_punctuation"]
    COLOR_EDITOR_FOLD_HIGHLIGHT = palette["editor_fold_highlight"]
    COLOR_EDITOR_INDENT_GUIDE = palette["editor_indent_guide"]
    COLOR_EDITOR_ACTIVE_INDENT_GUIDE = palette["editor_active_indent_guide"]
    COLOR_EDITOR_ERROR_GUTTER_BG = palette["editor_error_gutter_bg"]
    COLOR_EDITOR_FOLD_BADGE_BG = palette["editor_fold_badge_bg"]
    COLOR_EDITOR_FOLD_BADGE_TEXT = palette["editor_fold_badge_text"]
    COLOR_EDITOR_WHITESPACE_DOT = palette["editor_whitespace_dot"]


def current_palette() -> ThemePalette:
    """Return the currently active palette dict."""
    return _active


# -- Method → colour mapping ------------------------------------------
METHOD_COLORS: dict[str, str] = {
    "GET": LIGHT_PALETTE["success"],
    "POST": LIGHT_PALETTE["warning"],
    "PUT": LIGHT_PALETTE["accent"],
    "PATCH": LIGHT_PALETTE["danger"],
    "DELETE": LIGHT_PALETTE["delete"],
    "HEAD": LIGHT_PALETTE["head"],
    "OPTIONS": LIGHT_PALETTE["options"],
}
DEFAULT_METHOD_COLOR = LIGHT_PALETTE["muted"]

# Short labels that fit a fixed-width badge (max 3 chars).
METHOD_SHORT_LABELS: dict[str, str] = {
    "GET": "GET",
    "POST": "POST",
    "PUT": "PUT",
    "PATCH": "PAT",
    "DELETE": "DEL",
    "HEAD": "HED",
    "OPTIONS": "OPT",
}

# -- Badge geometry (pixels) -------------------------------------------
BADGE_FONT_SIZE = 9  # px — small but legible
BADGE_MIN_WIDTH = 32  # px — keeps all labels the same width
BADGE_HEIGHT = 16  # px — consistent vertical size
BADGE_BORDER_RADIUS = 3  # px
TREE_ROW_HEIGHT = 28  # px — uniform row height for every item


def method_color(method: str) -> str:
    """Return the theme colour for a given HTTP method."""
    return METHOD_COLORS.get(method.upper(), DEFAULT_METHOD_COLOR)


def method_short_label(method: str) -> str:
    """Return a compact badge label for a given HTTP method."""
    return METHOD_SHORT_LABELS.get(method.upper(), method.upper()[:3])
