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
    accent_hover: str
    danger_hover: str
    solid_button_fg: str
    muted: str
    delete: str
    head: str
    options: str

    # Functional
    sending: str
    breadcrumb_sep: str
    status_bar_bg: str

    # Import dialog
    drop_zone_border: str
    drop_zone_bg: str
    drop_zone_active_bg: str
    import_success: str
    import_error: str
    import_warn: str

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

    # Variable highlighting
    variable_highlight: str
    variable_unresolved_highlight: str
    variable_unresolved_text: str

    # Code editor
    editor_bracket_match: str
    editor_gutter_bg: str
    editor_gutter_text: str
    editor_error_underline: str
    editor_warning_underline: str
    editor_info_underline: str
    editor_hint_underline: str
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
    editor_warning_gutter_bg: str
    editor_info_gutter_bg: str
    editor_hint_gutter_bg: str
    editor_fold_badge_bg: str
    editor_fold_badge_text: str
    editor_whitespace_dot: str
    editor_breakpoint: str
    editor_breakpoint_conditional: str
    editor_breakpoint_line: str
    editor_breakpoint_unreachable: str
    editor_current_line: str
    editor_debug_line: str
    editor_debug_gutter_arrow: str
    editor_inline_log_text: str

    # Diff viewer
    diff_removed_bg: str
    diff_added_bg: str
    diff_removed_inline: str
    diff_added_inline: str
    diff_removed_gutter: str
    diff_added_gutter: str
    diff_header_bg: str


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
    "accent_hover": "#2980b9",
    "danger_hover": "#c0392b",
    "solid_button_fg": "#ffffff",
    "muted": "#95a5a6",
    "delete": "#e67e22",
    "head": "#27ae60",
    "options": "#9b59b6",
    "sending": "#f39c12",
    "breadcrumb_sep": "#aaaaaa",
    "status_bar_bg": "#ebebeb",
    "drop_zone_border": "#b0b0b0",
    "drop_zone_bg": "#fafafa",
    "drop_zone_active_bg": "#e8f4fd",
    "import_success": "#27ae60",
    "import_error": "#e74c3c",
    "import_warn": "#f39c12",
    "console_bg": "#1e1e1e",
    "console_text": "#d4d4d4",
    "timing_prepare": "#95a5a6",
    "timing_dns": "#3498db",
    "timing_tcp": "#2ecc71",
    "timing_tls": "#9b59b6",
    "timing_ttfb": "#e89a0c",
    "timing_download": "#e67e22",
    "timing_process": "#e74c3c",
    "variable_highlight": "#fff3e0",
    "variable_unresolved_highlight": "#fce4e4",
    "variable_unresolved_text": "#c0392b",
    "editor_bracket_match": "#d4edda",
    "editor_gutter_bg": "#fafafa",
    "editor_gutter_text": "#999999",
    "editor_error_underline": "#e74c3c",
    "editor_warning_underline": "#d9a441",
    "editor_info_underline": "#2980b9",
    "editor_hint_underline": "#8e44ad",
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
    "editor_warning_gutter_bg": "#fff3cd",
    "editor_info_gutter_bg": "#e3f2fd",
    "editor_hint_gutter_bg": "#f4ecf7",
    "editor_fold_badge_bg": "#e0e6ed",
    "editor_fold_badge_text": "#6a737d",
    "editor_whitespace_dot": "#b0b0b0",
    "editor_breakpoint": "#e74c3c",
    "editor_breakpoint_conditional": "#f1c40f",
    "editor_breakpoint_line": "#fae9ec",
    "editor_breakpoint_unreachable": "#b0b0b0",
    "editor_current_line": "#f5f5f5",
    "editor_debug_line": "#ffe89a",
    "editor_debug_gutter_arrow": "#f39c12",
    "editor_inline_log_text": "#7f8c8d",
    "diff_removed_bg": "#fce4e4",
    "diff_added_bg": "#d4edda",
    "diff_removed_inline": "#f5c6c6",
    "diff_added_inline": "#abdbbd",
    "diff_removed_gutter": "#e74c3c",
    "diff_added_gutter": "#2ecc71",
    "diff_header_bg": "#efefef",
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
    "accent_hover": "#3d9fd9",
    "danger_hover": "#ff6b6b",
    "solid_button_fg": "#ffffff",
    "muted": "#808080",
    "delete": "#ce9178",
    "head": "#4ec9b0",
    "options": "#c586c0",
    "sending": "#f39c12",
    "breadcrumb_sep": "#666666",
    "status_bar_bg": "#1a1a1c",
    "drop_zone_border": "#555555",
    "drop_zone_bg": "#252526",
    "drop_zone_active_bg": "#1a3a4a",
    "import_success": "#4ec9b0",
    "import_error": "#f44747",
    "import_warn": "#dcdcaa",
    "console_bg": "#1e1e1e",
    "console_text": "#d4d4d4",
    "timing_prepare": "#808080",
    "timing_dns": "#4fc1ff",
    "timing_tcp": "#4ec9b0",
    "timing_tls": "#c586c0",
    "timing_ttfb": "#dcdcaa",
    "timing_download": "#ce9178",
    "timing_process": "#f44747",
    "variable_highlight": "#3a2a1a",
    "variable_unresolved_highlight": "#4a2020",
    "variable_unresolved_text": "#f44747",
    "editor_bracket_match": "#2a4a3a",
    "editor_gutter_bg": "#252526",
    "editor_gutter_text": "#858585",
    "editor_error_underline": "#f44747",
    "editor_warning_underline": "#dcdcaa",
    "editor_info_underline": "#4fc1ff",
    "editor_hint_underline": "#c586c0",
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
    "editor_warning_gutter_bg": "#3a3520",
    "editor_info_gutter_bg": "#1a3a4a",
    "editor_hint_gutter_bg": "#3a2a45",
    "editor_fold_badge_bg": "#3a3d4a",
    "editor_fold_badge_text": "#a0a0a0",
    "editor_whitespace_dot": "#606060",
    "editor_breakpoint": "#f44747",
    "editor_breakpoint_conditional": "#dcdcaa",
    "editor_breakpoint_line": "#3d2325",
    "editor_breakpoint_unreachable": "#8a8a8a",
    "editor_current_line": "#2a2a2e",
    "editor_debug_line": "#5a4a1e",
    "editor_debug_gutter_arrow": "#f39c12",
    "editor_inline_log_text": "#8b949e",
    "diff_removed_bg": "#4a2020",
    "diff_added_bg": "#1a3a2a",
    "diff_removed_inline": "#6b3030",
    "diff_added_inline": "#2a5a3a",
    "diff_removed_gutter": "#f44747",
    "diff_added_gutter": "#4ec9b0",
    "diff_header_bg": "#2a2d2e",
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
COLOR_ACCENT_HOVER: str = _active["accent_hover"]
COLOR_DANGER_HOVER: str = _active["danger_hover"]
COLOR_SOLID_BUTTON_FG: str = _active["solid_button_fg"]
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
COLOR_STATUS_BAR_BG: str = _active["status_bar_bg"]

COLOR_DROP_ZONE_BORDER: str = _active["drop_zone_border"]
COLOR_DROP_ZONE_BG: str = _active["drop_zone_bg"]
COLOR_DROP_ZONE_ACTIVE_BG: str = _active["drop_zone_active_bg"]
COLOR_IMPORT_SUCCESS: str = _active["import_success"]
COLOR_IMPORT_ERROR: str = _active["import_error"]
COLOR_IMPORT_WARN: str = _active["import_warn"]

COLOR_TIMING_PREPARE: str = _active["timing_prepare"]
COLOR_TIMING_DNS: str = _active["timing_dns"]
COLOR_TIMING_TCP: str = _active["timing_tcp"]
COLOR_TIMING_TLS: str = _active["timing_tls"]
COLOR_TIMING_TTFB: str = _active["timing_ttfb"]
COLOR_TIMING_DOWNLOAD: str = _active["timing_download"]
COLOR_TIMING_PROCESS: str = _active["timing_process"]

COLOR_VARIABLE_HIGHLIGHT: str = _active["variable_highlight"]
COLOR_VARIABLE_UNRESOLVED_HIGHLIGHT: str = _active["variable_unresolved_highlight"]
COLOR_VARIABLE_UNRESOLVED_TEXT: str = _active["variable_unresolved_text"]

COLOR_EDITOR_BRACKET_MATCH: str = _active["editor_bracket_match"]
COLOR_EDITOR_GUTTER_BG: str = _active["editor_gutter_bg"]
COLOR_EDITOR_GUTTER_TEXT: str = _active["editor_gutter_text"]
COLOR_EDITOR_ERROR_UNDERLINE: str = _active["editor_error_underline"]
COLOR_EDITOR_WARNING_UNDERLINE: str = _active["editor_warning_underline"]
COLOR_EDITOR_INFO_UNDERLINE: str = _active["editor_info_underline"]
COLOR_EDITOR_HINT_UNDERLINE: str = _active["editor_hint_underline"]
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
COLOR_EDITOR_WARNING_GUTTER_BG: str = _active["editor_warning_gutter_bg"]
COLOR_EDITOR_INFO_GUTTER_BG: str = _active["editor_info_gutter_bg"]
COLOR_EDITOR_HINT_GUTTER_BG: str = _active["editor_hint_gutter_bg"]
COLOR_EDITOR_FOLD_BADGE_BG: str = _active["editor_fold_badge_bg"]
COLOR_EDITOR_FOLD_BADGE_TEXT: str = _active["editor_fold_badge_text"]
COLOR_EDITOR_WHITESPACE_DOT: str = _active["editor_whitespace_dot"]
COLOR_EDITOR_BREAKPOINT: str = _active["editor_breakpoint"]
COLOR_EDITOR_BREAKPOINT_CONDITIONAL: str = _active["editor_breakpoint_conditional"]
COLOR_EDITOR_BREAKPOINT_LINE: str = _active["editor_breakpoint_line"]
COLOR_EDITOR_BREAKPOINT_UNREACHABLE: str = _active["editor_breakpoint_unreachable"]
COLOR_EDITOR_CURRENT_LINE: str = _active["editor_current_line"]
COLOR_EDITOR_DEBUG_LINE: str = _active["editor_debug_line"]
COLOR_EDITOR_DEBUG_GUTTER_ARROW: str = _active["editor_debug_gutter_arrow"]
COLOR_EDITOR_INLINE_LOG_TEXT: str = _active["editor_inline_log_text"]

COLOR_DIFF_REMOVED_BG: str = _active["diff_removed_bg"]
COLOR_DIFF_ADDED_BG: str = _active["diff_added_bg"]
COLOR_DIFF_REMOVED_INLINE: str = _active["diff_removed_inline"]
COLOR_DIFF_ADDED_INLINE: str = _active["diff_added_inline"]
COLOR_DIFF_REMOVED_GUTTER: str = _active["diff_removed_gutter"]
COLOR_DIFF_ADDED_GUTTER: str = _active["diff_added_gutter"]


def set_active_palette(palette: ThemePalette) -> None:
    """Replace the module-level colour aliases with values from *palette*.

    Called by ``ThemeManager.apply()`` — widget code should **not** call
    this directly.
    """
    global _active
    global COLOR_ACCENT, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER
    global COLOR_ACCENT_HOVER, COLOR_DANGER_HOVER, COLOR_SOLID_BUTTON_FG
    global COLOR_MUTED, COLOR_DELETE, COLOR_HEAD, COLOR_OPTIONS
    global COLOR_WHITE, COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_BORDER
    global COLOR_HOVER_BG, COLOR_HOVER_TREE_BG, COLOR_SELECTED_BG
    global COLOR_SENDING
    global COLOR_CONSOLE_BG, COLOR_CONSOLE_TEXT
    global COLOR_BREADCRUMB_SEP, COLOR_STATUS_BAR_BG
    global COLOR_DROP_ZONE_BORDER, COLOR_DROP_ZONE_BG
    global COLOR_DROP_ZONE_ACTIVE_BG
    global COLOR_IMPORT_SUCCESS, COLOR_IMPORT_ERROR, COLOR_IMPORT_WARN
    global COLOR_TIMING_PREPARE, COLOR_TIMING_DNS, COLOR_TIMING_TCP
    global COLOR_TIMING_TLS, COLOR_TIMING_TTFB, COLOR_TIMING_DOWNLOAD
    global COLOR_TIMING_PROCESS
    global COLOR_VARIABLE_HIGHLIGHT
    global COLOR_VARIABLE_UNRESOLVED_HIGHLIGHT, COLOR_VARIABLE_UNRESOLVED_TEXT
    global COLOR_EDITOR_BRACKET_MATCH, COLOR_EDITOR_GUTTER_BG
    global COLOR_EDITOR_GUTTER_TEXT, COLOR_EDITOR_ERROR_UNDERLINE
    global COLOR_EDITOR_WARNING_UNDERLINE
    global COLOR_EDITOR_INFO_UNDERLINE, COLOR_EDITOR_HINT_UNDERLINE
    global COLOR_EDITOR_FOLD_INDICATOR
    global COLOR_EDITOR_STRING, COLOR_EDITOR_NUMBER, COLOR_EDITOR_KEYWORD
    global COLOR_EDITOR_COMMENT, COLOR_EDITOR_TAG, COLOR_EDITOR_ATTRIBUTE
    global COLOR_EDITOR_PUNCTUATION
    global COLOR_EDITOR_FOLD_HIGHLIGHT, COLOR_EDITOR_INDENT_GUIDE
    global COLOR_EDITOR_ACTIVE_INDENT_GUIDE
    global COLOR_EDITOR_ERROR_GUTTER_BG
    global COLOR_EDITOR_WARNING_GUTTER_BG
    global COLOR_EDITOR_INFO_GUTTER_BG, COLOR_EDITOR_HINT_GUTTER_BG
    global COLOR_EDITOR_FOLD_BADGE_BG, COLOR_EDITOR_FOLD_BADGE_TEXT
    global COLOR_EDITOR_WHITESPACE_DOT
    global COLOR_EDITOR_BREAKPOINT, COLOR_EDITOR_BREAKPOINT_CONDITIONAL
    global COLOR_EDITOR_DEBUG_LINE, COLOR_EDITOR_BREAKPOINT_LINE
    global COLOR_EDITOR_BREAKPOINT_UNREACHABLE
    global COLOR_EDITOR_CURRENT_LINE
    global COLOR_EDITOR_DEBUG_GUTTER_ARROW, COLOR_EDITOR_INLINE_LOG_TEXT
    global COLOR_DIFF_REMOVED_BG, COLOR_DIFF_ADDED_BG
    global COLOR_DIFF_REMOVED_INLINE, COLOR_DIFF_ADDED_INLINE
    global COLOR_DIFF_REMOVED_GUTTER, COLOR_DIFF_ADDED_GUTTER

    _active = palette

    COLOR_ACCENT = palette["accent"]
    COLOR_SUCCESS = palette["success"]
    COLOR_WARNING = palette["warning"]
    COLOR_DANGER = palette["danger"]
    COLOR_ACCENT_HOVER = palette["accent_hover"]
    COLOR_DANGER_HOVER = palette["danger_hover"]
    COLOR_SOLID_BUTTON_FG = palette["solid_button_fg"]
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
    COLOR_STATUS_BAR_BG = palette["status_bar_bg"]

    COLOR_DROP_ZONE_BORDER = palette["drop_zone_border"]
    COLOR_DROP_ZONE_BG = palette["drop_zone_bg"]
    COLOR_DROP_ZONE_ACTIVE_BG = palette["drop_zone_active_bg"]
    COLOR_IMPORT_SUCCESS = palette["import_success"]
    COLOR_IMPORT_ERROR = palette["import_error"]
    COLOR_IMPORT_WARN = palette["import_warn"]

    COLOR_TIMING_PREPARE = palette["timing_prepare"]
    COLOR_TIMING_DNS = palette["timing_dns"]
    COLOR_TIMING_TCP = palette["timing_tcp"]
    COLOR_TIMING_TLS = palette["timing_tls"]
    COLOR_TIMING_TTFB = palette["timing_ttfb"]
    COLOR_TIMING_DOWNLOAD = palette["timing_download"]
    COLOR_TIMING_PROCESS = palette["timing_process"]

    COLOR_VARIABLE_HIGHLIGHT = palette["variable_highlight"]
    COLOR_VARIABLE_UNRESOLVED_HIGHLIGHT = palette["variable_unresolved_highlight"]
    COLOR_VARIABLE_UNRESOLVED_TEXT = palette["variable_unresolved_text"]

    COLOR_EDITOR_BRACKET_MATCH = palette["editor_bracket_match"]
    COLOR_EDITOR_GUTTER_BG = palette["editor_gutter_bg"]
    COLOR_EDITOR_GUTTER_TEXT = palette["editor_gutter_text"]
    COLOR_EDITOR_ERROR_UNDERLINE = palette["editor_error_underline"]
    COLOR_EDITOR_WARNING_UNDERLINE = palette["editor_warning_underline"]
    COLOR_EDITOR_INFO_UNDERLINE = palette["editor_info_underline"]
    COLOR_EDITOR_HINT_UNDERLINE = palette["editor_hint_underline"]
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
    COLOR_EDITOR_WARNING_GUTTER_BG = palette["editor_warning_gutter_bg"]
    COLOR_EDITOR_INFO_GUTTER_BG = palette["editor_info_gutter_bg"]
    COLOR_EDITOR_HINT_GUTTER_BG = palette["editor_hint_gutter_bg"]
    COLOR_EDITOR_FOLD_BADGE_BG = palette["editor_fold_badge_bg"]
    COLOR_EDITOR_FOLD_BADGE_TEXT = palette["editor_fold_badge_text"]
    COLOR_EDITOR_WHITESPACE_DOT = palette["editor_whitespace_dot"]
    COLOR_EDITOR_BREAKPOINT = palette["editor_breakpoint"]
    COLOR_EDITOR_BREAKPOINT_CONDITIONAL = palette["editor_breakpoint_conditional"]
    COLOR_EDITOR_BREAKPOINT_LINE = palette["editor_breakpoint_line"]
    COLOR_EDITOR_BREAKPOINT_UNREACHABLE = palette["editor_breakpoint_unreachable"]
    COLOR_EDITOR_CURRENT_LINE = palette["editor_current_line"]
    COLOR_EDITOR_DEBUG_LINE = palette["editor_debug_line"]
    COLOR_EDITOR_DEBUG_GUTTER_ARROW = palette["editor_debug_gutter_arrow"]
    COLOR_EDITOR_INLINE_LOG_TEXT = palette["editor_inline_log_text"]

    COLOR_DIFF_REMOVED_BG = palette["diff_removed_bg"]
    COLOR_DIFF_ADDED_BG = palette["diff_added_bg"]
    COLOR_DIFF_REMOVED_INLINE = palette["diff_removed_inline"]
    COLOR_DIFF_ADDED_INLINE = palette["diff_added_inline"]
    COLOR_DIFF_REMOVED_GUTTER = palette["diff_removed_gutter"]
    COLOR_DIFF_ADDED_GUTTER = palette["diff_added_gutter"]


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

# Left nav flyout (collections + environments panes): horizontal inset for
# panel bodies only. Applied inside each splitter child so the vertical handle
# between collections and environments stays edge-to-edge in the flyout.
LEFT_NAV_PANEL_MARGIN_H_LEFT_PX = 12
LEFT_NAV_PANEL_MARGIN_H_RIGHT_PX = 8

# Left activity rail: width and icon size as multiples of the primary font
# height (see ``LeftSidebar``). Keep the strip narrow; ``ICON_EM`` nudges the
# glyph up slightly, and ``LEFT_RAIL_BUTTON_EXTRA_HEIGHT_PX`` adds top/bottom
# padding inside each rail row (hit target + air around the icon).
LEFT_RAIL_WIDTH_EM = 2.55
LEFT_RAIL_ICON_EM = 1.48
# Extra vertical space on each button (hit target + room around the icon).
LEFT_RAIL_BUTTON_EXTRA_HEIGHT_PX = 28
# Full-height painted accent (``QToolButton`` QSS ``border-left`` clips to content).
LEFT_RAIL_ACCENT_STRIPE_WIDTH_PX = 3


def method_color(method: str) -> str:
    """Return the theme colour for a given HTTP method."""
    return METHOD_COLORS.get(method.upper(), DEFAULT_METHOD_COLOR)


def method_short_label(method: str) -> str:
    """Return a compact badge label for a given HTTP method."""
    return METHOD_SHORT_LABELS.get(method.upper(), method.upper()[:3])


def status_color(code: int | None) -> str:
    """Return the theme colour for an HTTP status code."""
    if code is None:
        return COLOR_MUTED
    if code < 300:
        return COLOR_SUCCESS
    if code < 400:
        return COLOR_WARNING
    if code < 500:
        return COLOR_DELETE
    return COLOR_DANGER
