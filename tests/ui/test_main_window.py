"""Smoke tests for the top-level MainWindow."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.collections.collection_widget import CollectionWidget
from ui.main_window import MainWindow


class TestMainWindow:
    """Smoke tests for the top-level application window."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """MainWindow can be instantiated without errors."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert window.windowTitle() == "Postmark"

    def test_has_collection_widget(self, qapp: QApplication, qtbot) -> None:
        """MainWindow contains a CollectionWidget."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert isinstance(window.collection_widget, CollectionWidget)

    def test_menu_bar_exists(self, qapp: QApplication, qtbot) -> None:
        """MainWindow has a menu bar with File and Collection menus."""
        window = MainWindow()
        qtbot.addWidget(window)

        menubar = window.menuBar()
        menu_titles = [a.text() for a in menubar.actions()]
        assert "&File" in menu_titles
        assert "&Collection" in menu_titles
