"""Tests for NewLocalScriptItemPopup."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.collections.new_item_popup import _Tile
from ui.collections.new_local_script_popup import NewLocalScriptItemPopup, _LanguageTile


class TestNewLocalScriptItemPopup:
    """Language and folder tile signals."""

    def test_typescript_tile_emits_language(self, qapp: QApplication, qtbot) -> None:
        """Clicking the TypeScript tile emits the normalized language code."""
        popup = NewLocalScriptItemPopup()
        qtbot.addWidget(popup)

        ts_tile = next(t for t in popup.findChildren(_LanguageTile) if t.language == "typescript")
        with qtbot.waitSignal(popup.new_script_clicked, timeout=1000) as blocker:
            qtbot.mouseClick(ts_tile, Qt.MouseButton.LeftButton)

        assert blocker.args == ["typescript", "esm"]

    def test_commonjs_tile_emits_language_and_format(self, qapp: QApplication, qtbot) -> None:
        """CommonJS tile emits javascript + commonjs."""
        popup = NewLocalScriptItemPopup()
        qtbot.addWidget(popup)

        cjs_tile = next(
            t
            for t in popup.findChildren(_LanguageTile)
            if t.language == "javascript" and t.module_format == "commonjs"
        )
        with qtbot.waitSignal(popup.new_script_clicked, timeout=1000) as blocker:
            qtbot.mouseClick(cjs_tile, Qt.MouseButton.LeftButton)

        assert blocker.args == ["javascript", "commonjs"]

    def test_folder_tile_emits_signal(self, qapp: QApplication, qtbot) -> None:
        """Clicking Folder emits ``new_folder_clicked``."""
        popup = NewLocalScriptItemPopup()
        qtbot.addWidget(popup)

        folder_tile = popup.findChild(_Tile)
        assert folder_tile is not None

        with qtbot.waitSignal(popup.new_folder_clicked, timeout=1000):
            qtbot.mouseClick(folder_tile, Qt.MouseButton.LeftButton)
