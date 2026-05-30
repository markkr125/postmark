"""Brand icons for JavaScript, TypeScript, and Python (tree, tabs, dialogs).

Logos are from `data/images/languages/`. See that folder README for sources.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ui.request.request_editor.scripts.script_language import normalise_script_code
from ui.styling.icons import _device_pixel_ratio, phi

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_LANG_DIR = _PROJECT_ROOT / "data" / "images" / "languages"

_LANGUAGE_FILES: dict[str, str] = {
    "javascript": "javascript.svg",
    "typescript": "typescript.svg",
    "python": "python.svg",
}

# Legacy tree ``method`` badge labels before ``ROLE_LANGUAGE`` was introduced.
_BADGE_TO_LANGUAGE: dict[str, str] = {
    "JS": "javascript",
    "TS": "typescript",
    "PY": "python",
}

# Phosphor fallbacks when an SVG is missing (distinct shapes per language).
_PHOSPHOR_FALLBACK: dict[str, tuple[str, str]] = {
    "javascript": ("brackets-curly", "#E8D44A"),
    "typescript": ("brackets-angle", "#3178C6"),
    "python": ("terminal-window", "#3B82F6"),
}

_pixmap_cache: dict[tuple[str, int], QPixmap] = {}


def clear_language_icon_cache() -> None:
    """Drop cached pixmaps (e.g. after a theme change)."""
    _pixmap_cache.clear()


def resolve_script_language(
    language: str | None = None,
    *,
    method_badge: str | None = None,
) -> str:
    """Resolve a script language code from explicit language or a legacy badge label."""
    if language:
        return normalise_script_code(language)
    if method_badge:
        key = method_badge.strip().upper()
        if key in _BADGE_TO_LANGUAGE:
            return _BADGE_TO_LANGUAGE[key]
        return normalise_script_code(method_badge)
    return "javascript"


def language_icon_pixmap(language: str, *, size: int = 36) -> QPixmap:
    """Return a cached brand pixmap for *language* (javascript | typescript | python)."""
    code = normalise_script_code(language)
    if code not in _LANGUAGE_FILES:
        code = "javascript"
    cache_key = (code, size)
    if cache_key in _pixmap_cache:
        return _pixmap_cache[cache_key]

    pixmap = _render_brand_pixmap(code, size=size)
    _pixmap_cache[cache_key] = pixmap
    return pixmap


def _render_brand_pixmap(code: str, *, size: int) -> QPixmap:
    """Render a language logo with padding; fall back to Phosphor on failure."""
    dpr = _device_pixel_ratio()
    px_size = max(1, int(size * dpr))
    pixmap = QPixmap(px_size, px_size)
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)

    path = _LANG_DIR / _LANGUAGE_FILES[code]
    if path.is_file():
        renderer = QSvgRenderer(str(path))
        if renderer.isValid():
            inset = max(1, size // 7)
            target = QRect(inset, inset, size - (2 * inset), size - (2 * inset))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            renderer.render(painter, target)
            painter.end()
            return pixmap
        logger.warning("Invalid SVG for language icon: %s", path)
    else:
        logger.warning("Language icon not found: %s", path)

    glyph_name, color = _PHOSPHOR_FALLBACK.get(code, _PHOSPHOR_FALLBACK["javascript"])
    icon = phi(glyph_name, color=color, size=size)
    fallback = icon.pixmap(size, size)
    if not fallback.isNull():
        return fallback
    return pixmap
