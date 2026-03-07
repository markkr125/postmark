"""Phosphor icon provider — lightweight font-glyph icon rendering.

Loads the bundled Phosphor TTF font once and renders glyph-based ``QIcon``
objects on demand.  Icons are cached by (name, color_hex, size) tuple so
each unique variant is created only once, keeping memory usage flat.

Usage::

    from ui.styling.icons import phi

    action.setIcon(phi("arrow-left"))
    button.setIcon(phi("trash", color="#e74c3c", size=16))
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QPainter,
                           QPixmap)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths — resolve relative to the project root (two levels above src/ui/styling/)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_FONT_PATH = _PROJECT_ROOT / "data" / "fonts" / "phosphor.ttf"
_CHARMAP_PATH = _PROJECT_ROOT / "data" / "fonts" / "phosphor-charmap.json"

# ---------------------------------------------------------------------------
# Module-level state (populated by ``load_font``)
# ---------------------------------------------------------------------------
_charmap: dict[str, str] = {}
_font_family: str = ""
_font_loaded: bool = False
_icon_cache: dict[tuple[str, str, int], QIcon] = {}

# Default icon size used when none is specified.
_DEFAULT_SIZE = 16


def load_font() -> None:
    """Load the Phosphor TTF font and charmap into module state.

    Safe to call multiple times — subsequent calls are no-ops.
    Must be called **after** ``QApplication`` is created.
    """
    global _charmap, _font_family, _font_loaded

    if _font_loaded:
        return

    if not _FONT_PATH.exists():
        logger.warning("Phosphor font not found at %s", _FONT_PATH)
        _font_loaded = True
        return

    font_id = QFontDatabase.addApplicationFont(str(_FONT_PATH))
    if font_id < 0:
        logger.warning("Failed to load Phosphor font from %s", _FONT_PATH)
        _font_loaded = True
        return

    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        logger.warning("Phosphor font registered but no families found")
        _font_loaded = True
        return

    _font_family = families[0]

    if _CHARMAP_PATH.exists():
        with open(_CHARMAP_PATH, encoding="utf-8") as fh:
            raw = json.load(fh)
        # Values are hex strings like "0xf03b" — convert to single chars
        for name, code in raw.items():
            _charmap[name] = chr(int(code, 16))
    else:
        logger.warning("Phosphor charmap not found at %s", _CHARMAP_PATH)

    _font_loaded = True
    logger.debug(
        "Phosphor font loaded: family=%r, glyphs=%d",
        _font_family,
        len(_charmap),
    )


def phi(name: str, *, color: str = "", size: int = _DEFAULT_SIZE) -> QIcon:
    """Return a cached ``QIcon`` for the given Phosphor icon *name*.

    Parameters
    ----------
    name:
        Phosphor icon name (e.g. ``"arrow-left"``, ``"trash"``).
    color:
        Hex colour string (e.g. ``"#cccccc"``).  Defaults to the
        current theme's ``COLOR_TEXT_MUTED`` if empty.
    size:
        Pixel size of the rendered icon (default 16).

    Returns a null ``QIcon`` when the font or the glyph is unavailable.
    """
    if not _font_loaded:
        load_font()

    if not color:
        # Import here to avoid circular import at module load time
        from ui.styling.theme import COLOR_TEXT_MUTED

        color = COLOR_TEXT_MUTED

    cache_key = (name, color, size)
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    glyph = _charmap.get(name, "")
    if not glyph or not _font_family:
        icon = QIcon()
        _icon_cache[cache_key] = icon
        return icon

    icon = _render_glyph_icon(glyph, color, size)
    _icon_cache[cache_key] = icon
    return icon


def clear_cache() -> None:
    """Drop all cached icons.

    Call after a theme change so colours are re-rendered on next access.
    """
    _icon_cache.clear()


def glyph_char(name: str) -> str:
    """Return the raw Unicode character for a Phosphor glyph *name*.

    Returns an empty string if the font is not loaded or the glyph is
    unknown.  Useful for painting glyphs directly with a ``QPainter``
    that already has the Phosphor font set.
    """
    if not _font_loaded:
        load_font()
    return _charmap.get(name, "")


def font_family() -> str:
    """Return the Phosphor font family name.

    Returns an empty string if the font is not loaded.
    """
    if not _font_loaded:
        load_font()
    return _font_family


# ---------------------------------------------------------------------------
# Internal rendering
# ---------------------------------------------------------------------------


def _render_glyph_icon(glyph: str, color: str, size: int) -> QIcon:
    """Render a single Phosphor glyph into a ``QIcon``."""
    dpr = _device_pixel_ratio()
    px_size = int(size * dpr)

    pixmap = QPixmap(px_size, px_size)
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    font = QFont(_font_family)
    font.setPixelSize(size)
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(
        QRect(0, 0, size, size),
        Qt.AlignmentFlag.AlignCenter,
        glyph,
    )
    painter.end()

    icon = QIcon(pixmap)
    return icon


def _device_pixel_ratio() -> float:
    """Return the primary screen's device-pixel ratio, defaulting to 1."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if isinstance(app, QApplication):
        screen = app.primaryScreen()
        if screen is not None:
            return float(screen.devicePixelRatio())
    return 1.0
    return 1.0
    return 1.0
    return 1.0
