"""Tests for send-history integration on the right sidebar rail."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.sidebar.history.panel import HistoryPanel
from ui.sidebar.sidebar_widget import RightSidebar


class TestRightSidebarRequestHistory:
    """Send history as the fourth right-rail flyout button."""

    def test_history_panel_on_sidebar(self, qapp: QApplication, qtbot) -> None:
        """RightSidebar exposes the request history panel."""
        panel = HistoryPanel()
        sidebar = RightSidebar(request_history_panel=panel)
        qtbot.addWidget(sidebar)
        assert sidebar.request_history_panel is panel

    def test_history_button_hidden_until_request_tab(self, qapp: QApplication, qtbot) -> None:
        """History rail button is hidden until show_request_panels."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        assert sidebar._history_btn.isHidden()

        sidebar.show_request_panels({}, method="GET", url="http://x")
        assert not sidebar._history_btn.isHidden()

        sidebar.show_folder_panels({})
        assert sidebar._history_btn.isHidden()

    def test_set_request_history_context_draft_disables_button(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Draft context disables the history button and shows save-first state."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_request_panels({}, method="GET", url="http://x")
        sidebar.set_request_history_context(
            request_id=None,
            request_name="Draft",
            is_persisted_request=False,
        )
        assert not sidebar._history_btn.isEnabled()
        assert "Save the request first" in sidebar.request_history_panel._state_label.text()

    def test_open_request_history_panel(self, qapp: QApplication, qtbot) -> None:
        """open_panel('request_history') selects the send-history flyout."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_request_panels({}, method="GET", url="http://x")
        sidebar.set_request_history_context(
            request_id=1,
            request_name="Req",
            is_persisted_request=True,
        )
        sidebar.open_panel("request_history")
        assert sidebar.active_panel == "request_history"
        assert sidebar._history_btn.isChecked()
        assert sidebar.request_history_panel.isVisible()
