"""Centralised colour and style constants for the UI layer.

All hex colour values used in stylesheets should be defined here so the
design system is explicit and grep-able.
"""

from __future__ import annotations

# -- Semantic palette --------------------------------------------------
COLOR_ACCENT = "#3498db"  # links, active borders, progress bars
COLOR_SUCCESS = "#2ecc71"  # GET badge
COLOR_WARNING = "#f1c40f"  # POST badge
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


def method_color(method: str) -> str:
    """Return the theme colour for a given HTTP method."""
    return METHOD_COLORS.get(method.upper(), DEFAULT_METHOD_COLOR)
