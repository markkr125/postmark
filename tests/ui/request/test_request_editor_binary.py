"""Tests for RequestEditorWidget — binary/file-upload body mode."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.request.request_editor import RequestEditorWidget


class TestRequestEditorBinary:
    """Tests for the binary file upload body mode."""

    def test_binary_mode_shows_file_picker(self, qapp: QApplication, qtbot) -> None:
        """Selecting binary mode activates the file picker stack page."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor._body_mode_buttons["binary"].setChecked(True)

        assert editor._body_stack.currentIndex() == 3

    def test_binary_button_exists(self, qapp: QApplication, qtbot) -> None:
        """The binary file select button is present."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert hasattr(editor, "_binary_file_btn")
        assert editor._binary_file_btn.text() == "Select File"

    def test_binary_label_default(self, qapp: QApplication, qtbot) -> None:
        """The binary file label starts with 'No file selected.'."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert editor._binary_file_label.text() == "No file selected."

    def test_load_request_binary_body(self, qapp: QApplication, qtbot) -> None:
        """Loading a binary request shows the file path in the label."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "Upload",
                "method": "POST",
                "url": "http://upload",
                "body_mode": "binary",
                "body": "/path/to/file.png",
            }
        )

        assert editor._body_mode_buttons["binary"].isChecked()
        assert editor._binary_file_label.text() == "/path/to/file.png"

    def test_load_request_binary_empty_body(self, qapp: QApplication, qtbot) -> None:
        """Loading a binary request with empty body shows default label."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "Upload",
                "method": "POST",
                "url": "http://upload",
                "body_mode": "binary",
                "body": "",
            }
        )

        assert editor._binary_file_label.text() == "No file selected."

    def test_get_request_data_binary_with_file(self, qapp: QApplication, qtbot) -> None:
        """get_request_data returns the file path for binary mode."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "Upload",
                "method": "POST",
                "url": "http://upload",
                "body_mode": "binary",
                "body": "/path/to/data.bin",
            }
        )

        data = editor.get_request_data()
        assert data["body_mode"] == "binary"
        assert data["body"] == "/path/to/data.bin"

    def test_get_request_data_binary_no_file(self, qapp: QApplication, qtbot) -> None:
        """get_request_data returns empty body when no file is selected."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor._body_mode_buttons["binary"].setChecked(True)

        data = editor.get_request_data()
        assert data["body_mode"] == "binary"
        assert data["body"] == ""

    def test_clear_resets_binary_label(self, qapp: QApplication, qtbot) -> None:
        """clear_request resets the binary file label."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "Upload",
                "method": "POST",
                "url": "http://upload",
                "body_mode": "binary",
                "body": "/path/to/file.png",
            }
        )
        editor.clear_request()

        assert editor._binary_file_label.text() == "No file selected."

    def test_binary_dirty_on_file_select(self, qapp: QApplication, qtbot) -> None:
        """Programmatically setting the file label marks dirty."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "Upload",
                "method": "POST",
                "url": "http://upload",
                "body_mode": "binary",
                "body": "",
            }
        )
        assert not editor.is_dirty

        # Simulate what _on_select_binary_file does
        editor._binary_file_label.setText("/new/file.bin")
        editor._on_field_changed()
        assert editor.is_dirty

    def test_binary_roundtrip(self, qapp: QApplication, qtbot) -> None:
        """Binary file path survives a load -> get_request_data roundtrip."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        path = "/home/user/documents/payload.json"
        editor.load_request(
            {
                "name": "Upload",
                "method": "POST",
                "url": "http://upload",
                "body_mode": "binary",
                "body": path,
            }
        )

        data = editor.get_request_data()
        assert data["body_mode"] == "binary"
        assert data["body"] == path

    def test_binary_mode_radio_in_group(self, qapp: QApplication, qtbot) -> None:
        """The binary radio button is in the body mode group."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert "binary" in editor._body_mode_buttons
        btn = editor._body_mode_buttons["binary"]
        assert editor._body_mode_group.id(btn) != -1

    def test_switching_from_binary_to_raw(self, qapp: QApplication, qtbot) -> None:
        """Switching from binary to raw changes the stack page."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "X",
                "method": "POST",
                "url": "http://x",
                "body_mode": "binary",
                "body": "/file.bin",
            }
        )
        assert editor._body_stack.currentIndex() == 3

        editor._body_mode_buttons["raw"].setChecked(True)
        assert editor._body_stack.currentIndex() == 1
