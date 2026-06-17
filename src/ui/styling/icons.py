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
import re
from pathlib import Path

from PySide6.QtCore import QDir, QRect, QStandardPaths, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

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
_qss_image_cache: dict[tuple[str, str, int], str] = {}
_qss_icons_dir: Path | None = None
_qss_search_path_registered = False
_QSS_ICON_SCHEME = "postmark-qss"
_COLOR_SLUG_RE = re.compile(r"[^0-9a-fA-F]+")

# Default icon size used when none is specified.
_DEFAULT_SIZE = 16
# Solid stop square inside 28x28 ``smallPrimaryButton`` (composer + user footer).
CHAT_STOP_ICON_SIZE = 12


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


def _qss_icon_filename(name: str, color: str, size: int) -> str:
    """Return a stable on-disk filename for a QSS arrow PNG."""
    color_slug = _COLOR_SLUG_RE.sub("", color.removeprefix("#").lower()) or "default"
    safe_name = name.replace("/", "-")
    return f"{safe_name}_{size}_{color_slug}.png"


def _ensure_qss_icons_dir() -> Path | None:
    """Return the writable cache directory for QSS arrow PNGs."""
    global _qss_icons_dir, _qss_search_path_registered

    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        return None

    if _qss_icons_dir is None:
        cache_root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        if not cache_root:
            return None
        _qss_icons_dir = Path(cache_root) / "postmark" / "qss_icons"
        _qss_icons_dir.mkdir(parents=True, exist_ok=True)

    if not _qss_search_path_registered:
        QDir.addSearchPath(_QSS_ICON_SCHEME, str(_qss_icons_dir))
        _qss_search_path_registered = True

    return _qss_icons_dir


def phi_qss_image_url(name: str, *, color: str, size: int = 8) -> str:
    """Return a Qt-stylesheet ``image`` URL for a Phosphor glyph PNG on disk.

    QAbstractSpinBox arrows cannot use CSS border triangles in QSS (Qt draws
    them as lines). QSS also does not support ``data:`` image URLs (QTBUG-51081),
    so glyphs are rendered to PNG files under the app cache directory and
    referenced via ``url(postmark-qss:…png)``.
    """
    if not color:
        from ui.styling.theme import COLOR_TEXT_MUTED

        color = COLOR_TEXT_MUTED

    cache_key = (name, color, size)
    if cache_key in _qss_image_cache:
        return _qss_image_cache[cache_key]

    icon_dir = _ensure_qss_icons_dir()
    if icon_dir is None:
        _qss_image_cache[cache_key] = "none"
        return "none"

    filename = _qss_icon_filename(name, color, size)
    path = icon_dir / filename
    if not path.exists():
        pixmap = phi(name, color=color, size=size).pixmap(size, size)
        if pixmap.isNull():
            _qss_image_cache[cache_key] = "none"
            return "none"
        if not pixmap.save(str(path), "PNG"):
            _qss_image_cache[cache_key] = "none"
            return "none"

    url = f"url({_QSS_ICON_SCHEME}:{filename})"
    _qss_image_cache[cache_key] = url
    return url


def square_filled_icon(*, color: str, size: int = _DEFAULT_SIZE) -> QIcon:
    """Return a cached solid-square ``QIcon`` (media-style stop affordance).

    Unlike the Phosphor ``stop`` outline glyph, the square fills nearly the
    full *size* box with only a 1px inset so it reads as a full stop block.
    """
    cache_key = ("square-filled", color, size)
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    dpr = _device_pixel_ratio()
    px_size = int(size * dpr)
    inset = 1

    pixmap = QPixmap(px_size, px_size)
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.fillRect(inset, inset, size - inset * 2, size - inset * 2, QColor(color))
    painter.end()

    icon = QIcon(pixmap)
    _icon_cache[cache_key] = icon
    return icon


def chat_stop_icon(*, size: int = CHAT_STOP_ICON_SIZE) -> QIcon:
    """Return the shared white filled-square stop icon for chat run controls."""
    from ui.styling.theme import COLOR_SOLID_BUTTON_FG

    return square_filled_icon(color=COLOR_SOLID_BUTTON_FG, size=size)


def phi_menu(name: str, *, size: int = _DEFAULT_SIZE) -> QIcon:
    """Return a menu action icon that turns white when the row is highlighted."""
    from ui.styling.theme import COLOR_SOLID_BUTTON_FG, COLOR_TEXT

    icon = QIcon()
    normal = phi(name, color=COLOR_TEXT, size=size).pixmap(size, size)
    highlighted = phi(name, color=COLOR_SOLID_BUTTON_FG, size=size).pixmap(size, size)
    icon.addPixmap(normal, QIcon.Mode.Normal, QIcon.State.Off)
    for mode in (QIcon.Mode.Active, QIcon.Mode.Selected):
        icon.addPixmap(highlighted, mode, QIcon.State.Off)
    return icon


def clear_cache() -> None:
    """Drop all cached icons.

    Call after a theme change so colours are re-rendered on next access.
    """
    _icon_cache.clear()
    _qss_image_cache.clear()
    from ui.styling.language_icons import clear_language_icon_cache

    clear_language_icon_cache()


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
