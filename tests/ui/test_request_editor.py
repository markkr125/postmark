"""Tests for the RequestEditorWidget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.request_editor import RequestEditorWidget


class TestRequestEditorWidget:
    """Tests for the request editor pane."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Widget can be instantiated without errors."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        assert editor is not None

    def test_starts_in_empty_state(self, qapp: QApplication, qtbot) -> None:
        """Editor starts with the empty-state label visible."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        # Widget is not shown, so use isHidden() which checks local state
        assert not editor._empty_label.isHidden()
        assert editor._tabs.isHidden()

    def test_load_request_shows_content(self, qapp: QApplication, qtbot) -> None:
        """Loading a request hides the empty state and shows content."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "Get Users",
                "method": "GET",
                "url": "https://api.example.com/users",
                "body": "",
                "request_parameters": "page=1",
                "headers": "Accept: application/json",
            }
        )

        assert editor._empty_label.isHidden()
        assert not editor._tabs.isHidden()
        assert editor._title_label.text() == "Get Users"
        assert editor._url_input.text() == "https://api.example.com/users"
        assert editor._method_combo.currentText() == "GET"
        assert editor._params_edit.toPlainText() == "page=1"
        assert editor._headers_edit.toPlainText() == "Accept: application/json"

    def test_clear_request_restores_empty_state(self, qapp: QApplication, qtbot) -> None:
        """Clearing resets to the empty state."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor.clear_request()

        assert not editor._empty_label.isHidden()
        assert editor._tabs.isHidden()
        assert editor._url_input.text() == ""

    def test_load_request_with_scripts_dict(self, qapp: QApplication, qtbot) -> None:
        """Scripts dict is displayed as formatted JSON."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "X",
                "method": "GET",
                "url": "http://x",
                "scripts": {"pre": "console.log('hi')"},
            }
        )

        text = editor._scripts_edit.toPlainText()
        assert "console.log" in text
