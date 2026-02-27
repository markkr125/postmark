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
