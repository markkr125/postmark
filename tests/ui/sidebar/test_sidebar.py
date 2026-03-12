"""Tests for the RightSidebar widget (icon rail + flyout panel)."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QApplication

from ui.sidebar.saved_responses.panel import SavedResponsesPanel
from ui.sidebar.sidebar_widget import RightSidebar
from ui.sidebar.snippet_panel import SnippetPanel
from ui.sidebar.variables_panel import VariablesPanel


class TestRightSidebar:
    """Tests for the Postman-style icon-rail + flyout panel sidebar."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """RightSidebar can be instantiated without errors."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        assert sidebar.objectName() == "sidebarRail"

    def test_panels_exist(self, qapp: QApplication, qtbot) -> None:
        """Sidebar exposes variables, snippet, and saved-responses panels."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        assert isinstance(sidebar.variables_panel, VariablesPanel)
        assert isinstance(sidebar.snippet_panel, SnippetPanel)
        assert isinstance(sidebar.saved_responses_panel, SavedResponsesPanel)

    def test_rail_buttons_exist(self, qapp: QApplication, qtbot) -> None:
        """Sidebar has rail buttons for variables, snippet, and saved responses."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        assert sidebar._var_btn is not None
        assert sidebar._snippet_btn is not None
        assert sidebar._saved_btn is not None

    def test_buttons_start_disabled(self, qapp: QApplication, qtbot) -> None:
        """Rail buttons are disabled until a tab context is set."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        assert not sidebar._var_btn.isEnabled()
        assert sidebar._snippet_btn.isHidden()
        assert sidebar._saved_btn.isHidden()

    def test_panel_starts_closed(self, qapp: QApplication, qtbot) -> None:
        """No panel is open on construction."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        assert sidebar.active_panel is None
        assert not sidebar.panel_open

    def test_open_panel_variables(self, qapp: QApplication, qtbot) -> None:
        """open_panel('variables') opens the variables panel."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_request_panels({}, method="GET", url="")
        sidebar.open_panel("variables")
        assert sidebar.active_panel == "variables"
        assert sidebar.panel_open
        assert sidebar._var_btn.isChecked()
        assert not sidebar._snippet_btn.isChecked()

    def test_open_panel_snippet(self, qapp: QApplication, qtbot) -> None:
        """open_panel('snippet') opens the snippet panel."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_request_panels({}, method="GET", url="")
        sidebar.open_panel("snippet")
        assert sidebar.active_panel == "snippet"
        assert sidebar.panel_open
        assert not sidebar._var_btn.isChecked()
        assert sidebar._snippet_btn.isChecked()

    def test_open_panel_saved_responses(self, qapp: QApplication, qtbot) -> None:
        """open_panel('saved_responses') opens the saved responses panel."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_request_panels({}, method="GET", url="")
        sidebar.set_saved_response_context(
            request_id=1,
            request_name="Search",
            items=[],
            can_save_current=False,
            is_persisted_request=True,
        )
        sidebar.open_panel("saved_responses")
        assert sidebar.active_panel == "saved_responses"
        assert sidebar._saved_btn.isChecked()

    def test_toggle_panel_closes_active(self, qapp: QApplication, qtbot) -> None:
        """Clicking the active panel's icon closes the panel."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_request_panels({}, method="GET", url="")
        sidebar.open_panel("variables")
        assert sidebar.active_panel == "variables"

        sidebar._toggle_panel("variables")
        assert sidebar.active_panel is None
        assert not sidebar.panel_open

    def test_toggle_panel_switches(self, qapp: QApplication, qtbot) -> None:
        """Clicking a different icon switches the active panel."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_request_panels({}, method="GET", url="")
        sidebar.open_panel("variables")

        sidebar._toggle_panel("snippet")
        assert sidebar.active_panel == "snippet"
        assert sidebar._snippet_btn.isChecked()
        assert not sidebar._var_btn.isChecked()

    def test_show_request_panels_enables_both(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """show_request_panels enables all request-scoped rail icons."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        variables: dict[str, Any] = {
            "key1": {"value": "val1", "source": "environment", "source_id": 1},
        }
        sidebar.show_request_panels(
            variables,
            method="GET",
            url="https://example.com",
        )
        assert sidebar._var_btn.isEnabled()
        assert not sidebar._snippet_btn.isHidden()
        assert sidebar._snippet_btn.isEnabled()
        assert not sidebar._saved_btn.isHidden()
        assert sidebar._saved_btn.isEnabled()

    def test_show_folder_panels_disables_snippet(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """show_folder_panels enables variables but disables snippet."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        variables: dict[str, Any] = {
            "key1": {"value": "val1", "source": "collection", "source_id": 5},
        }
        sidebar.show_folder_panels(variables)
        assert sidebar._var_btn.isEnabled()
        assert sidebar._snippet_btn.isHidden()
        assert sidebar._saved_btn.isHidden()

    def test_show_folder_closes_snippet_panel(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Switching to a folder closes the snippet panel if it was open."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_request_panels({}, method="GET", url="")
        sidebar.open_panel("snippet")
        assert sidebar.active_panel == "snippet"

        sidebar.show_folder_panels({})
        assert sidebar.active_panel is None

    def test_clear_disables_all(self, qapp: QApplication, qtbot) -> None:
        """clear() disables all icons and closes the panel."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_request_panels({}, method="GET", url="")
        sidebar.open_panel("variables")
        sidebar.clear()
        assert not sidebar._var_btn.isEnabled()
        assert sidebar._snippet_btn.isHidden()
        assert sidebar._saved_btn.isHidden()
        assert sidebar.active_panel is None

    def test_close_button_closes_panel(self, qapp: QApplication, qtbot) -> None:
        """Clicking the close button hides the active panel."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_request_panels({}, method="GET", url="")
        sidebar.open_panel("variables")
        assert sidebar.panel_open

        sidebar._close_btn.click()
        assert not sidebar.panel_open
        assert sidebar.active_panel is None

    def test_open_unavailable_panel_ignored(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Opening a panel not in available_panels is a no-op."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_folder_panels({})
        sidebar.open_panel("snippet")
        assert sidebar.active_panel is None
