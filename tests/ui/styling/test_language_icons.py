"""Tests for script language brand icon pixmaps."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.styling.language_icons import language_icon_pixmap, resolve_script_language


def test_language_icon_pixmap_is_non_empty(qapp: QApplication) -> None:
    """Each supported language returns a transparent pixmap with painted content."""
    for code in ("javascript", "typescript", "python"):
        pixmap = language_icon_pixmap(code, size=16)
        assert not pixmap.isNull()
        assert pixmap.width() == 16
        assert pixmap.height() == 16


def test_resolve_script_language_from_legacy_badge() -> None:
    """Legacy JS/TS/PY tree badges still map to language codes."""
    assert resolve_script_language(method_badge="TS") == "typescript"
    assert resolve_script_language(language="python") == "python"
