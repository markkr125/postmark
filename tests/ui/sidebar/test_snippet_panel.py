"""Tests for the SnippetPanel widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.sidebar.snippet_panel import SnippetPanel


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

    def test_syntax_highlighting_language(self, qapp: QApplication, qtbot) -> None:
        """Snippet editor uses correct syntax language per combo selection."""
        panel = SnippetPanel()
        qtbot.addWidget(panel)
        panel.update_request(method="GET", url="https://example.com")
        assert panel._code_edit._language == "bash"

        panel._lang_combo.setCurrentText("Python (requests)")
        assert panel._code_edit._language == "python"

        panel._lang_combo.setCurrentText("JavaScript (fetch)")
        assert panel._code_edit._language == "javascript"
