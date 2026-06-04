"""Tests for the RightSidebar widget (icon rail + flyout panel)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.sidebar.ai import AiChatPanel
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
        """Sidebar exposes AI chat, variables, snippet, and saved-responses panels."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        assert isinstance(sidebar.ai_chat_panel, AiChatPanel)
        assert isinstance(sidebar.variables_panel, VariablesPanel)
        assert isinstance(sidebar.snippet_panel, SnippetPanel)
        assert isinstance(sidebar.saved_responses_panel, SavedResponsesPanel)

    def test_rail_buttons_exist(self, qapp: QApplication, qtbot) -> None:
        """Sidebar has rail buttons for AI, variables, snippet, saved responses, and history."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        assert sidebar._ai_btn is not None
        assert sidebar._var_btn is not None
        assert sidebar._snippet_btn is not None
        assert sidebar._saved_btn is not None
        assert sidebar._history_btn is not None

    def test_buttons_start_disabled(self, qapp: QApplication, qtbot) -> None:
        """Request-scoped rail buttons are disabled until a tab context is set; AI stays enabled."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        assert sidebar._ai_btn.isEnabled()
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

    def test_orphan_history_tab_shows_rail_tooltips(self, qapp: QApplication, qtbot) -> None:
        """Disabled saved/history rail icons explain deleted-request history tabs."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_request_panels({}, method="GET", url="http://example.com")
        sidebar.set_saved_response_context(
            request_id=None,
            request_name="Gone",
            items=[],
            can_save_current=False,
            is_persisted_request=False,
            from_deleted_request_history=True,
        )
        sidebar.set_request_history_context(
            request_id=None,
            request_name="Gone",
            is_persisted_request=False,
            from_deleted_request_history=True,
        )
        assert not sidebar._saved_btn.isEnabled()
        assert "deleted" in sidebar._saved_btn.toolTip().lower()
        assert not sidebar._history_btn.isEnabled()
        assert "deleted" in sidebar._history_btn.toolTip().lower()

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
        """clear() disables request-scoped rail buttons, keeps AI enabled, closes the flyout."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_request_panels({}, method="GET", url="")
        sidebar.open_panel("variables")
        sidebar.clear()
        assert not sidebar._var_btn.isEnabled()
        assert sidebar._snippet_btn.isHidden()
        assert sidebar._saved_btn.isHidden()
        assert sidebar.active_panel is None
        assert sidebar._ai_btn.isEnabled()  # AI is a global assistant; never disabled by clear()

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

    def test_ai_panel_exists_and_button_enabled(self, qapp: QApplication, qtbot) -> None:
        """The AI panel exists and its rail button is always enabled."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        assert isinstance(sidebar.ai_chat_panel, AiChatPanel)
        assert sidebar._ai_btn.isEnabled()

    def test_open_ai_panel(self, qapp: QApplication, qtbot) -> None:
        """open_panel('ai') activates the AI panel and checks its button."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.clear()
        sidebar.open_panel("ai")
        assert sidebar.active_panel == "ai"
        assert sidebar._ai_btn.isChecked()

    def test_ai_settings_button_visible_only_on_ai_panel(self, qapp: QApplication, qtbot) -> None:
        """Gear button in the flyout title bar is shown only for the AI panel."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.show_request_panels({}, method="GET", url="")
        sidebar.open_panel("ai")
        assert sidebar._flyout._ai_settings_btn.isVisible()
        sidebar.open_panel("variables")
        assert not sidebar._flyout._ai_settings_btn.isVisible()

    def test_toggle_ai_panel_closes_active(self, qapp: QApplication, qtbot) -> None:
        """Toggling the AI rail button closes the panel when it is already open."""
        sidebar = RightSidebar()
        qtbot.addWidget(sidebar)
        sidebar.clear()
        sidebar._toggle_panel("ai")
        assert sidebar.active_panel == "ai"
        sidebar._toggle_panel("ai")
        assert sidebar.active_panel is None

    def test_ai_send_appends_user_bubble(self, qapp: QApplication, qtbot) -> None:
        """Sending text adds a user bubble and clears the input."""
        from ui.sidebar.ai.message_bubble import ChatMessageBubble

        panel = AiChatPanel()
        qtbot.addWidget(panel)
        entry: dict[str, Any] = {
            "id": "m1",
            "provider": "ollama",
            "label": "llama3",
            "model": "ollama/llama3:latest",
            "base_url": "",
            "api_version": "",
            "auth_kind": "none",
            "auth_ref": "",
            "enabled": True,
        }
        panel.set_models([entry])  # type: ignore[list-item]
        assert panel._send_btn.isEnabled()
        panel._input.setPlainText("hello")
        with qtbot.waitSignal(panel.message_submitted, timeout=1000):
            panel._on_send()
        assert panel._input.toPlainText() == ""
        bubbles = panel._messages.findChildren(ChatMessageBubble)
        assert len(bubbles) == 1
        assert bubbles[0].role == "user"

    def test_ai_send_disabled_without_models(self, qapp: QApplication, qtbot) -> None:
        """With no enabled models, Send and the model button are disabled."""
        panel = AiChatPanel()
        qtbot.addWidget(panel)
        panel.set_models([])
        assert not panel._send_btn.isEnabled()
        assert not panel._model_btn.isEnabled()
        assert panel.current_model_id() is None
        assert panel._model_btn.text() == "No models configured"

    def test_ai_set_models_selects_first_and_labels_button(self, qapp: QApplication, qtbot) -> None:
        """set_models selects the first enabled model and labels the button."""
        panel = AiChatPanel()
        qtbot.addWidget(panel)
        entries: list[dict[str, Any]] = [
            {
                "id": "m1",
                "provider": "ollama",
                "label": "llama3",
                "model": "ollama/llama3:latest",
                "base_url": "",
                "api_version": "",
                "auth_kind": "none",
                "auth_ref": "",
                "enabled": True,
            },
            {
                "id": "m2",
                "provider": "openai",
                "label": "gpt-4o",
                "model": "openai/gpt-4o",
                "base_url": "",
                "api_version": "",
                "auth_kind": "token",
                "auth_ref": "",
                "enabled": True,
            },
        ]
        panel.set_models(entries)  # type: ignore[arg-type]
        assert panel.current_model_id() == "m1"
        assert panel._model_btn.text() == "llama3"

    def test_ai_model_picker_groups_by_provider(self, qapp: QApplication, qtbot) -> None:
        """Models under the same provider share one bold header row."""
        from ui.sidebar.ai.model_picker_popup import AiModelPickerPopup

        panel = AiChatPanel()
        qtbot.addWidget(panel)
        entries: list[dict[str, Any]] = [
            {
                "id": "m1",
                "provider": "ollama",
                "provider_display_name": "Ollama (local)",
                "label": "qwen2",
                "model": "ollama/qwen2",
                "base_url": "",
                "api_version": "",
                "auth_kind": "none",
                "auth_ref": "",
                "enabled": True,
            },
            {
                "id": "m2",
                "provider": "ollama",
                "provider_display_name": "Ollama (local)",
                "label": "qwen2-coder",
                "model": "ollama/qwen2-coder",
                "base_url": "",
                "api_version": "",
                "auth_kind": "none",
                "auth_ref": "",
                "enabled": True,
            },
        ]
        panel.set_models(entries)  # type: ignore[arg-type]
        panel._open_model_picker()
        popup = AiModelPickerPopup.instance()
        qtbot.addWidget(popup)
        assert popup._list.count() == 3
        header = popup._list.item(0)
        assert header is not None
        assert header.text() == "Ollama (local)"
        assert header.flags() == Qt.ItemFlag.NoItemFlags
        assert header.font().bold()

    def test_ai_model_picker_filters_and_picks(self, qapp: QApplication, qtbot) -> None:
        """The picker filters by search text and updates the current model on pick."""
        from ui.sidebar.ai.model_picker_popup import AiModelPickerPopup

        panel = AiChatPanel()
        qtbot.addWidget(panel)
        entries: list[dict[str, Any]] = [
            {
                "id": "m1",
                "provider": "ollama",
                "label": "llama3",
                "model": "ollama/llama3:latest",
                "base_url": "",
                "api_version": "",
                "auth_kind": "none",
                "auth_ref": "",
                "enabled": True,
            },
            {
                "id": "m2",
                "provider": "openai",
                "provider_display_name": "OpenAI",
                "label": "gpt-4o",
                "model": "openai/gpt-4o",
                "base_url": "",
                "api_version": "",
                "auth_kind": "token",
                "auth_ref": "",
                "enabled": True,
            },
        ]
        panel.set_models(entries)  # type: ignore[arg-type]
        panel._open_model_picker()
        popup = AiModelPickerPopup.instance()
        qtbot.addWidget(popup)
        assert popup._list.count() == 4  # ollama header + model, OpenAI header + model
        popup._search.setText("gpt")
        assert popup._list.count() == 2  # OpenAI header + gpt-4o
        with qtbot.waitSignal(popup.model_picked, timeout=1000):
            popup._pick("m2")
        assert panel.current_model_id() == "m2"
        assert panel._model_btn.text() == "gpt-4o"
        assert not popup.isVisible()

    def test_ai_model_picker_manage_link_emits(self, qapp: QApplication, qtbot) -> None:
        """The Manage models link bubbles up manage_models_requested."""
        from ui.sidebar.ai.model_picker_popup import AiModelPickerPopup

        panel = AiChatPanel()
        qtbot.addWidget(panel)
        entry: dict[str, Any] = {
            "id": "m1",
            "provider": "ollama",
            "label": "llama3",
            "model": "ollama/llama3:latest",
            "base_url": "",
            "api_version": "",
            "auth_kind": "none",
            "auth_ref": "",
            "enabled": True,
        }
        panel.set_models([entry])  # type: ignore[list-item]
        panel._open_model_picker()
        popup = AiModelPickerPopup.instance()
        qtbot.addWidget(popup)
        with qtbot.waitSignal(panel.manage_models_requested, timeout=1000):
            popup._handle_manage()
        assert not popup.isVisible()

    def test_ai_default_mode_is_agent(self, qapp: QApplication, qtbot) -> None:
        """The agent-mode select defaults to Agent and exposes the value."""
        panel = AiChatPanel()
        qtbot.addWidget(panel)
        assert panel.current_mode() == "agent"

    def test_ai_mode_change_emits(self, qapp: QApplication, qtbot) -> None:
        """Changing the mode select emits mode_changed with the new value."""
        panel = AiChatPanel()
        qtbot.addWidget(panel)
        idx = panel._mode_combo.findData("plan")
        with qtbot.waitSignal(panel.mode_changed, timeout=1000):
            panel._mode_combo.setCurrentIndex(idx)
        assert panel.current_mode() == "plan"

    def test_ai_context_usage_label(self, qapp: QApplication, qtbot) -> None:
        """Context indicator shows a dash for unknown total, percent otherwise."""
        panel = AiChatPanel()
        qtbot.addWidget(panel)
        panel.set_context_usage(0, 0)
        assert "—" in panel._context_label.text()
        panel.set_context_usage(64000, 128000)
        assert "50%" in panel._context_label.text()

    def test_ai_attachments_add_and_remove(self, qapp: QApplication, qtbot) -> None:
        """Adding a chip tracks the path and shows the row; removing clears it."""
        from PySide6.QtWidgets import QPushButton

        panel = AiChatPanel()
        qtbot.addWidget(panel)
        panel._attachments.append("/tmp/a.txt")
        panel._add_attachment_chip("/tmp/a.txt")
        panel._attachments_row.setVisible(True)
        assert panel.attachments() == ["/tmp/a.txt"]
        chip = panel._attachments_row.findChildren(QPushButton)[0]
        with qtbot.waitSignal(panel.attachments_changed, timeout=1000):
            panel._remove_attachment("/tmp/a.txt", chip)
        assert panel.attachments() == []

    def test_ai_ctrl_enter_submits(self, qapp: QApplication, qtbot) -> None:
        """Ctrl+Enter on the composer emits message_submitted when Send is enabled."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtWidgets import QApplication

        panel = AiChatPanel()
        qtbot.addWidget(panel)
        entry: dict[str, Any] = {
            "id": "m1",
            "provider": "ollama",
            "label": "llama3",
            "model": "ollama/llama3:latest",
            "base_url": "",
            "api_version": "",
            "auth_kind": "none",
            "auth_ref": "",
            "enabled": True,
        }
        panel.set_models([entry])  # type: ignore[list-item]
        panel._input.setPlainText("hi")
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.ControlModifier,
        )
        with qtbot.waitSignal(panel.message_submitted, timeout=1000):
            QApplication.sendEvent(panel._input, event)
        assert panel._input.toPlainText() == ""
