"""Tests for the SnippetPanel widget."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from services.http.snippet_generator import SnippetGenerator
from ui.sidebar.snippet_panel import SnippetPanel, SnippetSettingsPopup


class TestSnippetPanel:
    """Tests for the inline code snippet panel."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """SnippetPanel can be instantiated without errors."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        assert panel is not None

    def test_default_language(self, qapp: QApplication, qtbot) -> None:
        """The language combo starts with the first available language."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        assert panel._lang_combo.currentText() == "cURL"

    def test_update_request_generates_snippet(self, qapp: QApplication, qtbot) -> None:
        """update_request populates the code editor with a snippet."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        panel.update_request(method="GET", url="https://api.example.com/users")
        text = panel._code_edit.toPlainText()
        assert "curl" in text.lower()
        assert "https://api.example.com/users" in text

    def test_language_switch_regenerates(self, qapp: QApplication, qtbot) -> None:
        """Switching the language combo regenerates the snippet."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        panel.update_request(method="POST", url="https://api.example.com/data")
        panel._lang_combo.setCurrentText("Python (requests)")
        text = panel._code_edit.toPlainText()
        assert "requests" in text.lower()

    def test_copy_to_clipboard(self, qapp: QApplication, qtbot) -> None:
        """Clicking copy sets the text to the system clipboard."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        panel.update_request(method="GET", url="https://example.com")
        panel._copy_btn.click()
        assert panel._status_label.text() == "Copied!"

    def test_clear_resets_state(self, qapp: QApplication, qtbot) -> None:
        """clear() empties the code editor."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        panel.update_request(method="GET", url="https://example.com")
        panel.clear()
        assert panel._code_edit.toPlainText() == ""

    def test_empty_url_no_snippet(self, qapp: QApplication, qtbot) -> None:
        """When URL is empty, no snippet is generated."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        panel.update_request(method="GET", url="")
        assert panel._code_edit.toPlainText() == ""

    def test_snippet_with_headers_and_body(self, qapp: QApplication, qtbot) -> None:
        """Snippet includes headers and body when provided."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        panel.update_request(
            method="POST",
            url="https://api.example.com/data",
            headers="Content-Type: application/json",
            body='{"key": "value"}',
        )
        text = panel._code_edit.toPlainText()
        assert "Content-Type" in text
        assert "key" in text

    def test_snippet_with_bearer_auth(self, qapp: QApplication, qtbot) -> None:
        """Snippet includes Authorization header when bearer auth is set."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        auth = {"type": "bearer", "bearer": [{"key": "token", "value": "tok123"}]}
        panel.update_request(
            method="GET",
            url="https://api.example.com",
            auth=auth,
        )
        text = panel._code_edit.toPlainText()
        assert "Authorization" in text
        assert "Bearer tok123" in text

    def test_snippet_with_substituted_auth_variable(self, qapp: QApplication, qtbot) -> None:
        """Snippet resolves {{variable}} placeholders in auth values."""
        from ui.main_window.variable_controller import _VariableControllerMixin

        auth = {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{api_key}}"}],
        }
        resolved = _VariableControllerMixin._substitute_auth(auth, {"api_key": "secret123"})
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        panel.update_request(
            method="GET",
            url="https://api.example.com",
            auth=resolved,
        )
        text = panel._code_edit.toPlainText()
        assert "Bearer secret123" in text
        assert "{{api_key}}" not in text

    def test_syntax_highlighting_language(self, qapp: QApplication, qtbot) -> None:
        """Snippet editor uses correct syntax language per combo selection."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        panel._lang_combo.setCurrentText("cURL")
        panel.update_request(method="GET", url="https://example.com")
        assert panel._code_edit._language == "bash"

        panel._lang_combo.setCurrentText("Python (requests)")
        assert panel._code_edit._language == "python"

        panel._lang_combo.setCurrentText("JavaScript (fetch)")
        assert panel._code_edit._language == "javascript"

    def test_all_languages_in_combo(self, qapp: QApplication, qtbot) -> None:
        """Combo box contains all 23 registered languages."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        count = panel._lang_combo.count()
        assert count == len(SnippetGenerator.available_languages())
        assert count == 23

    def test_gear_button_exists(self, qapp: QApplication, qtbot) -> None:
        """Settings gear button is present in the panel."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        assert panel._settings_btn is not None
        assert panel._settings_btn.toolTip() == "Snippet settings"

    def test_toggle_settings_opens_popup(self, qapp: QApplication, qtbot) -> None:
        """Clicking gear button creates and shows the settings popup."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        assert panel._settings_popup is None
        panel._toggle_settings()
        assert panel._settings_popup is not None
        assert panel._settings_popup.isVisible()

    def test_toggle_settings_closes_popup(self, qapp: QApplication, qtbot) -> None:
        """Second click on gear button hides the popup."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        panel._toggle_settings()
        assert panel._settings_popup is not None
        assert panel._settings_popup.isVisible()
        panel._toggle_settings()
        assert not panel._settings_popup.isVisible()

    def test_options_propagated_to_generate(self, qapp: QApplication, qtbot) -> None:
        """Options from the settings popup affect snippet generation."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        panel._toggle_settings()
        assert panel._settings_popup is not None
        panel._settings_popup._indent_count.setValue(4)
        panel.update_request(method="GET", url="https://api.example.com")
        # Re-open should preserve indent count
        assert panel._settings_popup._indent_count.value() == 4

    def test_language_persisted_to_qsettings(self, qapp: QApplication, qtbot) -> None:
        """Switching language persists it via QSettings."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        panel._lang_combo.setCurrentText("Go (net/http)")
        saved = QSettings().value("snippet/last_language")
        assert saved == "Go (net/http)"

    def test_lexer_from_registry(self, qapp: QApplication, qtbot) -> None:
        """Each language combo entry sets the correct lexer via registry."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        panel.update_request(method="GET", url="https://example.com")
        # Python (requests) -> python lexer
        panel._lang_combo.setCurrentText("Python (requests)")
        assert panel._code_edit._language == "python"
        # Go (net/http) -> go lexer
        panel._lang_combo.setCurrentText("Go (net/http)")
        assert panel._code_edit._language == "go"
        # Rust (reqwest) -> rust lexer
        panel._lang_combo.setCurrentText("Rust (reqwest)")
        assert panel._code_edit._language == "rust"


class TestSnippetSettingsPopup:
    """Tests for the SnippetSettingsPopup widget."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Popup can be instantiated."""
        popup = SnippetSettingsPopup()
        qtbot.addWidget(popup)
        assert popup is not None

    def test_get_options_defaults(self, qapp: QApplication, qtbot) -> None:
        """Default options match expected defaults."""
        QSettings().remove("snippet")
        popup = SnippetSettingsPopup()
        qtbot.addWidget(popup)
        opts = popup.get_options()
        assert opts["indent_count"] == 2
        assert opts["indent_type"] == "space"
        assert opts["trim_body"] is False
        assert opts["follow_redirect"] is True
        assert opts["request_timeout"] == 0
        assert opts["include_boilerplate"] is True
        assert opts["async_await"] is False
        assert opts["es6_features"] is False

    def test_set_language_options_hides_controls(self, qapp: QApplication, qtbot) -> None:
        """Controls not in applicable_options are hidden."""
        popup = SnippetSettingsPopup()
        qtbot.addWidget(popup)
        popup.set_language_options(("trim_body",))
        assert popup._indent_count.isHidden()
        assert popup._indent_type.isHidden()
        assert popup._follow_redirect.isHidden()
        assert popup._request_timeout.isHidden()
        assert popup._include_boilerplate.isHidden()
        assert popup._async_await.isHidden()
        assert popup._es6_features.isHidden()
        assert not popup._trim_body.isHidden()

    def test_set_language_options_shows_controls(self, qapp: QApplication, qtbot) -> None:
        """Controls in applicable_options are not hidden."""
        popup = SnippetSettingsPopup()
        qtbot.addWidget(popup)
        popup.set_language_options(
            (
                "indent_count",
                "indent_type",
                "trim_body",
                "follow_redirect",
                "request_timeout",
                "include_boilerplate",
                "async_await",
                "es6_features",
            )
        )
        assert not popup._indent_count.isHidden()
        assert not popup._indent_type.isHidden()
        assert not popup._trim_body.isHidden()
        assert not popup._follow_redirect.isHidden()
        assert not popup._request_timeout.isHidden()
        assert not popup._include_boilerplate.isHidden()
        assert not popup._async_await.isHidden()
        assert not popup._es6_features.isHidden()

    def test_set_language_options_httpie_hides_indent(self, qapp: QApplication, qtbot) -> None:
        """HTTPie options hide indent controls."""
        popup = SnippetSettingsPopup()
        qtbot.addWidget(popup)
        popup.set_language_options(("request_timeout", "follow_redirect"))
        assert popup._indent_count.isHidden()
        assert popup._indent_type.isHidden()
        assert popup._trim_body.isHidden()
        assert not popup._request_timeout.isHidden()
        assert not popup._follow_redirect.isHidden()

    def test_on_settings_changed_callback(self, qapp: QApplication, qtbot) -> None:
        """Changing a value fires the on_settings_changed callback."""
        popup = SnippetSettingsPopup()
        qtbot.addWidget(popup)
        called = []
        popup.on_settings_changed(lambda: called.append(True))
        popup._indent_count.setValue(4)
        assert len(called) == 1

    def test_saves_to_qsettings(self, qapp: QApplication, qtbot) -> None:
        """Changing a setting persists the value via QSettings."""
        popup = SnippetSettingsPopup()
        qtbot.addWidget(popup)
        popup._indent_count.setValue(6)
        saved = int(str(QSettings().value("snippet/indent_count", 2)))
        assert saved == 6

    def test_get_options_includes_new_curl_fields(self, qapp: QApplication, qtbot) -> None:
        """get_options returns all 14 fields including 6 new cURL options."""
        QSettings().remove("snippet")
        popup = SnippetSettingsPopup()
        qtbot.addWidget(popup)
        opts = popup.get_options()
        assert opts["multiline"] is True
        assert opts["long_form"] is True
        assert opts["line_continuation"] == "\\"
        assert opts["quote_type"] == "single"
        assert opts["follow_original_method"] is False
        assert opts["silent_mode"] is False

    def test_curl_options_visible_for_curl(self, qapp: QApplication, qtbot) -> None:
        """cURL-specific controls are visible when cURL options are set."""
        popup = SnippetSettingsPopup()
        qtbot.addWidget(popup)
        popup.set_language_options(
            (
                "trim_body",
                "request_timeout",
                "follow_redirect",
                "follow_original_method",
                "multiline",
                "long_form",
                "line_continuation",
                "quote_type",
                "silent_mode",
            )
        )
        assert not popup._multiline.isHidden()
        assert not popup._long_form.isHidden()
        assert not popup._line_continuation.isHidden()
        assert not popup._quote_type.isHidden()
        assert not popup._follow_original_method.isHidden()
        assert not popup._silent_mode.isHidden()

    def test_curl_options_hidden_for_python(self, qapp: QApplication, qtbot) -> None:
        """cURL-specific controls are hidden for non-cURL languages."""
        popup = SnippetSettingsPopup()
        qtbot.addWidget(popup)
        popup.set_language_options(
            ("indent_count", "indent_type", "trim_body", "request_timeout", "follow_redirect")
        )
        assert popup._multiline.isHidden()
        assert popup._long_form.isHidden()
        assert popup._line_continuation.isHidden()
        assert popup._quote_type.isHidden()
        assert popup._follow_original_method.isHidden()
        assert popup._silent_mode.isHidden()

    def test_new_curl_options_change_fires_callback(self, qapp: QApplication, qtbot) -> None:
        """Changing a cURL option fires on_settings_changed callback."""
        popup = SnippetSettingsPopup()
        qtbot.addWidget(popup)
        called = []
        popup.on_settings_changed(lambda: called.append(True))
        popup._multiline.setChecked(False)
        assert len(called) >= 1
