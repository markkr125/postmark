"""Centralised colour and style constants for the UI layer.

All hex colour values used in stylesheets should be defined here so the
design system is explicit and grep-able.
"""

from __future__ import annotations

# -- Semantic palette --------------------------------------------------
COLOR_ACCENT = "#3498db"  # links, active borders, progress bars
COLOR_SUCCESS = "#2ecc71"  # GET badge
COLOR_WARNING = "#e89a0c"  # POST badge (amber — readable on white text)
COLOR_DANGER = "#e74c3c"  # PATCH badge
COLOR_MUTED = "#95a5a6"  # fallback / unknown method badge
COLOR_DELETE = "#e67e22"  # DELETE badge
COLOR_HEAD = "#27ae60"  # HEAD badge
COLOR_OPTIONS = "#9b59b6"  # OPTIONS badge

# -- Neutral palette ---------------------------------------------------
COLOR_WHITE = "#fff"
COLOR_TEXT = "#444"
COLOR_TEXT_MUTED = "#888"
COLOR_BORDER = "#ccc"
COLOR_HOVER_BG = "#c7c7c7"
COLOR_HOVER_TREE_BG = "#e8e8e8"  # tree item hover
COLOR_SELECTED_BG = "#d0e4f7"  # tree item selection

# -- Import dialog -----------------------------------------------------
COLOR_DROP_ZONE_BORDER = "#b0b0b0"  # dashed border for the drag-and-drop area
COLOR_DROP_ZONE_BG = "#fafafa"  # subtle background for the drop zone
COLOR_DROP_ZONE_ACTIVE_BG = "#e8f4fd"  # highlight while dragging over zone
COLOR_IMPORT_SUCCESS = "#27ae60"  # green for success messages
COLOR_IMPORT_ERROR = "#e74c3c"  # red for error messages

# -- Method → colour mapping ------------------------------------------
METHOD_COLORS: dict[str, str] = {
    "GET": COLOR_SUCCESS,
    "POST": COLOR_WARNING,
    "PUT": COLOR_ACCENT,
    "PATCH": COLOR_DANGER,
    "DELETE": COLOR_DELETE,
    "HEAD": COLOR_HEAD,
    "OPTIONS": COLOR_OPTIONS,
}
DEFAULT_METHOD_COLOR = COLOR_MUTED

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
TREE_ROW_HEIGHT = 24  # px — uniform row height for every item


def method_color(method: str) -> str:
    """Return the theme colour for a given HTTP method."""
    return METHOD_COLORS.get(method.upper(), DEFAULT_METHOD_COLOR)


def method_short_label(method: str) -> str:
    """Return a compact badge label for a given HTTP method."""
    return METHOD_SHORT_LABELS.get(method.upper(), method.upper()[:3])
