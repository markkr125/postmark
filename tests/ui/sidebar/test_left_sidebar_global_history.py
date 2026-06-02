"""Tests for the left-rail History flyout button."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QSplitter

from ui.sidebar.history.panel import HistoryPanel
from ui.sidebar.left_sidebar import LeftSidebar


class TestLeftSidebarGlobalHistory:
    """Left sidebar third rail button for workspace history."""

    def test_history_panel_registered(self, qapp: QApplication, qtbot) -> None:
        """set_history_panel reveals the History rail button."""
        splitter = QSplitter()
        qtbot.addWidget(splitter)
        left = LeftSidebar()
        panel = HistoryPanel()
        panel.set_global_mode()
        left.set_history_panel(panel)
        left.install_in_splitter(splitter)
        assert not left._history_btn.isHidden()
        left.open_panel("history")
        assert left.active_panel == "history"
        assert left.session_panel_key() == "history"
