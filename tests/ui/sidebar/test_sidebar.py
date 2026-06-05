"""Tests for the RightSidebar widget (icon rail + flyout panel)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from services.ai.ai_config import AiConfig
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.model_picker_edit import reasoning_levels_for_entry
from ui.sidebar.ai.model_picker_popup import AiModelPickerPopup
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
        assert "No models configured" in panel._model_button_label()

    def test_ai_composer_grows_with_lines(self, qapp: QApplication, qtbot) -> None:
        """Composer input height increases as more lines are added."""
        from ui.sidebar.ai.chat_panel import AiChatPanel

        panel = AiChatPanel()
        qtbot.addWidget(panel)
        panel.resize(320, 600)
        panel.show()
        qapp.processEvents()
        initial_h = panel._input.height()
        panel._input.setPlainText("\n".join("line" for _ in range(8)))
        qapp.processEvents()
        assert panel._input.height() > initial_h

    def test_ai_composer_caps_at_max_lines(self, qapp: QApplication, qtbot) -> None:
        """Composer stops growing at 15 lines and enables vertical scrolling."""
        from ui.sidebar.ai.chat_panel import (
            _COMPOSER_MAX_LINES,
            AiChatPanel,
        )

        panel = AiChatPanel()
        qtbot.addWidget(panel)
        panel.resize(320, 600)
        panel.show()
        qapp.processEvents()
        panel._input.setPlainText("\n".join("line" for _ in range(40)))
        qapp.processEvents()
        line_height = panel._input.fontMetrics().lineSpacing()
        chrome = panel._input._vertical_chrome()
        expected_max = _COMPOSER_MAX_LINES * line_height + chrome
        assert abs(panel._input.height() - expected_max) <= 2
        assert panel._input.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded

    def test_ai_composer_shrinks_back(self, qapp: QApplication, qtbot) -> None:
        """Clearing text collapses the composer back to the minimum height."""
        from ui.sidebar.ai.chat_panel import (
            _COMPOSER_MIN_LINES,
            AiChatPanel,
        )

        panel = AiChatPanel()
        qtbot.addWidget(panel)
        panel.resize(320, 600)
        panel.show()
        qapp.processEvents()
        panel._input.setPlainText("\n".join("line" for _ in range(20)))
        qapp.processEvents()
        panel._input.setPlainText("")
        qapp.processEvents()
        line_height = panel._input.fontMetrics().lineSpacing()
        chrome = panel._input._vertical_chrome()
        expected_min = _COMPOSER_MIN_LINES * line_height + chrome
        assert abs(panel._input.height() - expected_min) <= 2
        assert panel._input.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    def test_reasoning_levels_excludes_boolean_thinking(self) -> None:
        """Boolean thinking (off/on) is not shown as reasoning on the row."""
        assert reasoning_levels_for_entry(
            {"reasoning_efforts": ["low", "medium", "high"]}  # type: ignore[typeddict-item]
        ) == ("low", "medium", "high")
        assert (
            reasoning_levels_for_entry(
                {"reasoning_efforts": ["off", "on"]}  # type: ignore[typeddict-item]
            )
            == ()
        )

    def test_ollama_thinking_row_hides_effort_tag(self, qapp: QApplication, qtbot) -> None:
        """Ollama thinking models (not gpt-oss) do not show On/Off on the row."""
        panel = AiChatPanel()
        qtbot.addWidget(panel)
        entry: dict[str, object] = {
            "id": "m1",
            "provider": "ollama",
            "label": "qwen3",
            "model": "ollama/qwen3",
            "base_url": "",
            "api_version": "",
            "auth_kind": "none",
            "auth_ref": "",
            "context": 262144,
            "default_context": 32768,
            "thinking": True,
            "thinking_enabled": "on",
            "enabled": True,
        }
        panel.set_models([entry])  # type: ignore[list-item]
        panel._open_model_picker()
        popup = AiModelPickerPopup.instance()
        qtbot.addWidget(popup)
        row = popup._row_widgets["m1"]
        assert not row._effort_lbl.isVisible()
        assert row._edit_btn.isVisible()

    def test_ai_model_picker_shows_context_and_effort_tags(self, qapp: QApplication, qtbot) -> None:
        """Reasoning rows show context and effort tags in the picker."""
        panel = AiChatPanel()
        qtbot.addWidget(panel)
        entries: list[dict[str, object]] = [
            {
                "id": "m1",
                "provider": "openai",
                "label": "gpt-4o",
                "model": "openai/gpt-4o",
                "base_url": "",
                "api_version": "",
                "auth_kind": "none",
                "auth_ref": "",
                "context": 128000,
                "reasoning": True,
                "reasoning_efforts": ["low", "medium", "high"],
                "reasoning_default": "medium",
                "reasoning_effort": "high",
                "enabled": True,
            },
        ]
        panel.set_models(entries)  # type: ignore[arg-type]
        panel._open_model_picker()
        popup = AiModelPickerPopup.instance()
        qtbot.addWidget(popup)
        assert popup._list.count() == 2  # provider header + model row
        row = popup._row_widgets["m1"]
        assert row._effort_lbl.isVisible()
        assert row._effort_lbl.text() == "High"
        assert row._edit_btn.isVisible()

    def test_ai_model_picker_effort_edit_persists(self, qapp: QApplication, qtbot) -> None:
        """Choosing an effort persists via AiConfig and updates the button label."""
        from unittest.mock import patch

        panel = AiChatPanel()
        qtbot.addWidget(panel)
        entry: dict[str, object] = {
            "id": "m1",
            "provider": "openai",
            "label": "gpt-4o",
            "model": "openai/gpt-4o",
            "base_url": "",
            "api_version": "",
            "auth_kind": "none",
            "auth_ref": "",
            "context": 128000,
            "reasoning": True,
            "reasoning_efforts": ["low", "medium", "high"],
            "reasoning_default": "medium",
            "reasoning_effort": "medium",
            "enabled": True,
        }
        panel.set_models([entry])  # type: ignore[list-item]
        with patch.object(AiConfig, "set_model_reasoning_effort") as mock_set:
            with patch(
                "ui.sidebar.ai.model_picker_edit.AiModelPickerEditPanel.show_for",
                side_effect=lambda *_a, **k: k["on_reasoning"]("m1", "high"),
            ):
                panel._open_model_picker()
                popup = AiModelPickerPopup.instance()
                qtbot.addWidget(popup)
                popup._open_edit_menu("m1")
            mock_set.assert_called_once_with("m1", "high")
        assert panel.current_reasoning_effort() == "high"
        assert "High" in panel._model_button_label()
        assert popup._row_widgets["m1"]._effort_lbl.text() == "High"

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
        assert "llama3" in panel._model_button_label()

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
        assert "gpt-4o" in panel._model_button_label()
        assert not popup.isVisible()

    def test_ai_model_picker_toggles_on_model_button(self, qapp: QApplication, qtbot) -> None:
        """Clicking the model button again while open closes the picker."""
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
        assert popup.isVisible()
        panel._open_model_picker()
        assert not popup.isVisible()

    def test_ai_model_picker_manage_gear_emits(self, qapp: QApplication, qtbot) -> None:
        """The manage-models gear bubbles up manage_models_requested."""
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
        with qtbot.waitSignal(panel.mode_changed, timeout=1000):
            panel.set_mode("plan")
        assert panel.current_mode() == "plan"

    def test_ai_context_usage_tooltip(self, qapp: QApplication, qtbot) -> None:
        """Context button tooltip shows a dash for unknown total, percent otherwise."""
        panel = AiChatPanel()
        qtbot.addWidget(panel)
        panel.set_context_usage(0, 0)
        assert "—" in panel._context_btn.toolTip()
        panel.set_context_usage(64000, 128000)
        assert "50%" in panel._context_btn.toolTip()

    def test_ai_context_button_emits(self, qapp: QApplication, qtbot) -> None:
        """Context icon button emits context_requested for future wiring."""
        panel = AiChatPanel()
        qtbot.addWidget(panel)
        with qtbot.waitSignal(panel.context_requested, timeout=1000):
            panel._context_btn.click()

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
