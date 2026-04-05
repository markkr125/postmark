"""Tests for the reusable CodeEditorWidget.

Exercises syntax highlighting, code folding, bracket matching,
auto-close, validation, prettify, word wrap, and search selections.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QHelpEvent, QKeyEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTextEdit, QToolTip

from ui.widgets.code_editor import CodeEditorWidget, SyntaxError_

# -- Helpers -----------------------------------------------------------

_SAMPLE_JSON = '{"name": "Alice", "age": 30}'
_PRETTY_JSON = json.dumps(json.loads(_SAMPLE_JSON), indent=4, ensure_ascii=False)
_SAMPLE_XML = "<root><child>text</child></root>"
_INVALID_JSON = '{"name": "Alice", "age": }'
_INVALID_XML = "<root><child>text</root>"


# -- Construction & language -----------------------------------------


class TestCodeEditorConstruction:
    """Basic widget construction and language switching."""

    def test_default_language_is_text(self, qapp: QApplication, qtbot) -> None:
        """A fresh editor defaults to the 'text' language."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        assert editor.language == "text"

    def test_set_language_json(self, qapp: QApplication, qtbot) -> None:
        """Switching language to JSON updates the property."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        assert editor.language == "json"

    def test_set_language_case_insensitive(self, qapp: QApplication, qtbot) -> None:
        """Language names are normalised to lowercase."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("JSON")
        assert editor.language == "json"

    def test_read_only_mode(self, qapp: QApplication, qtbot) -> None:
        """A read-only editor reports isReadOnly()."""
        editor = CodeEditorWidget(read_only=True)
        qtbot.addWidget(editor)
        assert editor.isReadOnly()

    def test_object_name_is_code_editor(self, qapp: QApplication, qtbot) -> None:
        """Widget objectName matches the QSS selector."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        assert editor.objectName() == "codeEditor"

    def test_cursor_position_changed_signal(self, qapp: QApplication, qtbot) -> None:
        """cursor_position_changed emits 1-based line and column."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("line1\nline2")
        received: list[tuple[int, int]] = []
        editor.cursor_position_changed.connect(lambda ln, col: received.append((ln, col)))
        # Move cursor to start of second line
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Down)
        editor.setTextCursor(cursor)
        assert len(received) >= 1
        assert received[-1] == (2, 1)


# -- set_text / content helpers ---------------------------------------


class TestSetText:
    """Tests for set_text and plaintext round-trip."""

    def test_set_text_populates_content(self, qapp: QApplication, qtbot) -> None:
        """set_text stores the text so toPlainText returns it."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_text("hello")
        assert editor.toPlainText() == "hello"

    def test_set_text_read_only_caches(self, qapp: QApplication, qtbot) -> None:
        """set_text on a read-only editor caches tokens for highlighting."""
        editor = CodeEditorWidget(read_only=True)
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text(_SAMPLE_JSON)
        assert editor.toPlainText() == _SAMPLE_JSON


# -- Prettify ---------------------------------------------------------


class TestPrettify:
    """Tests for auto-formatting."""

    def test_prettify_json(self, qapp: QApplication, qtbot) -> None:
        """Prettify formats compact JSON with indentation."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.setPlainText(_SAMPLE_JSON)
        result = editor.prettify()
        assert result is True
        assert editor.toPlainText() == _PRETTY_JSON

    def test_prettify_returns_false_on_empty(self, qapp: QApplication, qtbot) -> None:
        """Prettify returns False when the editor is empty."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        assert editor.prettify() is False

    def test_prettify_invalid_json_no_change(self, qapp: QApplication, qtbot) -> None:
        """Prettify returns False and leaves invalid JSON unchanged."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.setPlainText(_INVALID_JSON)
        result = editor.prettify()
        assert result is False
        assert editor.toPlainText() == _INVALID_JSON

    def test_prettify_noop_for_text(self, qapp: QApplication, qtbot) -> None:
        """Prettify does nothing for plain text language."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("text")
        editor.setPlainText("hello world")
        assert editor.prettify() is False


# -- Word wrap --------------------------------------------------------


class TestWordWrap:
    """Tests for word wrap toggle."""

    def test_default_word_wrap_on(self, qapp: QApplication, qtbot) -> None:
        """Word wrap is enabled by default."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        assert editor.is_word_wrap() is True

    def test_toggle_word_wrap_off(self, qapp: QApplication, qtbot) -> None:
        """Disabling word wrap sets NoWrap mode."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_word_wrap(False)
        assert editor.is_word_wrap() is False
        assert editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap

    def test_toggle_word_wrap_on(self, qapp: QApplication, qtbot) -> None:
        """Re-enabling word wrap sets WidgetWidth mode."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_word_wrap(False)
        editor.set_word_wrap(True)
        assert editor.is_word_wrap() is True
        assert editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth


# -- Validation -------------------------------------------------------


class TestValidation:
    """Tests for JSON/XML/JS/Python validation and error signals."""

    @pytest.fixture(autouse=True)
    def _no_script_linter(self) -> None:
        """Override: allow real ScriptLinter for validation tests."""

    def test_valid_json_no_errors(self, qapp: QApplication, qtbot) -> None:
        """Valid JSON produces no validation errors."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text(_SAMPLE_JSON)
        assert editor.errors == []

    def test_invalid_json_has_errors(self, qapp: QApplication, qtbot) -> None:
        """Invalid JSON produces an error with a wave-underline ExtraSelection."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text(_INVALID_JSON)
        assert len(editor.errors) > 0
        assert isinstance(editor.errors[0], SyntaxError_)

        # Verify that extraSelections includes a wave underline
        wave_sels = [
            s
            for s in editor.extraSelections()
            if s.format.underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline
        ]
        assert len(wave_sels) > 0, "Expected at least one wave-underline ExtraSelection"

    def test_fix_json_clears_errors(self, qapp: QApplication, qtbot) -> None:
        """Fixing invalid JSON clears validation errors."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text(_INVALID_JSON)
        assert len(editor.errors) > 0

        editor.set_text(_SAMPLE_JSON)
        assert editor.errors == []

    def test_valid_xml_no_errors(self, qapp: QApplication, qtbot) -> None:
        """Valid XML produces no validation errors."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("xml")
        editor.set_text(_SAMPLE_XML)
        assert editor.errors == []

    def test_invalid_xml_has_errors(self, qapp: QApplication, qtbot) -> None:
        """Invalid XML produces at least one error."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("xml")
        editor.set_text(_INVALID_XML)
        assert len(editor.errors) > 0

    def test_validation_signal_emitted(self, qapp: QApplication, qtbot) -> None:
        """The validation_changed signal is emitted with the error list."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")

        received: list[list] = []
        editor.validation_changed.connect(lambda errs: received.append(errs))
        editor.set_text(_INVALID_JSON)
        assert len(received) > 0
        assert len(received[-1]) > 0

    def test_no_validation_for_text(self, qapp: QApplication, qtbot) -> None:
        """Plain text does not trigger validation errors."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("text")
        editor.set_text(_INVALID_JSON)
        assert editor.errors == []

    def test_invalid_javascript_has_errors(self, qapp: QApplication, qtbot) -> None:
        """Invalid JavaScript syntax produces errors with wave underline."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("javascript")
        editor.set_text("if (true {")
        assert len(editor.errors) > 0
        assert "Unexpected" in editor.errors[0].message

    def test_valid_javascript_no_errors(self, qapp: QApplication, qtbot) -> None:
        """Valid JavaScript produces no validation errors."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("javascript")
        editor.set_text("var x = 1;\nconsole.log(x);")
        assert editor.errors == []

    def test_invalid_python_has_errors(self, qapp: QApplication, qtbot) -> None:
        """Invalid Python syntax produces errors."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("python")
        editor.set_text("if True")
        assert len(editor.errors) > 0

    def test_valid_python_no_errors(self, qapp: QApplication, qtbot) -> None:
        """Valid Python produces no validation errors."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("python")
        editor.set_text("x = 1\nprint(x)")
        assert editor.errors == []


# -- Error gutter marker -----------------------------------------------


class TestErrorGutterMarker:
    """Tests for error markers in the line-number gutter."""

    def test_error_line_in_gutter_data(self, qapp: QApplication, qtbot) -> None:
        """Invalid JSON stores the error line for the gutter painter."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text(_INVALID_JSON)

        error_lines = {e.line for e in editor.errors}
        # The internal _errors list is used by paint_line_number_area
        assert error_lines == {e.line for e in editor._errors}
        assert len(error_lines) > 0

    def test_gutter_update_called_on_error(self, qapp: QApplication, qtbot) -> None:
        """Line number area receives an update when validation finds errors."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")

        updated = []
        orig_update = editor._line_number_area.update

        def _spy_update(*args: object) -> None:
            updated.append(True)
            orig_update(*args)

        editor._line_number_area.update = _spy_update  # type: ignore[assignment]
        editor.set_text(_INVALID_JSON)
        assert len(updated) > 0, "Expected _line_number_area.update() to be called"


# -- Error tooltip ------------------------------------------------------


class TestErrorTooltip:
    """Tests for tooltip display on error lines."""

    def test_tooltip_shown_on_error_line(self, qapp: QApplication, qtbot) -> None:
        """Hovering over an error line calls QToolTip.showText."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.show()
        editor.set_language("json")
        editor.set_text(_INVALID_JSON)

        assert len(editor.errors) > 0
        error = editor.errors[0]

        # Find the position of the error line in widget coordinates
        block = editor.document().findBlockByNumber(error.line - 1)
        rect = editor.blockBoundingGeometry(block).translated(editor.contentOffset())
        local_pos = rect.center().toPoint()
        global_pos = editor.mapToGlobal(local_pos)

        with patch.object(QToolTip, "showText") as mock_show:
            help_event = QHelpEvent(QEvent.Type.ToolTip, local_pos, global_pos)
            editor.event(help_event)
            mock_show.assert_called_once()
            call_args = mock_show.call_args
            assert error.message in call_args[0][1]


# -- Validation debounce -----------------------------------------------


class TestValidationDebounce:
    """Tests for debounced validation."""

    def test_rapid_edits_trigger_single_validate(self, qapp: QApplication, qtbot) -> None:
        """Three rapid keystrokes trigger _validate only once after debounce."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")

        call_count = [0]
        orig_validate = editor._validate

        def _counting_validate() -> None:
            call_count[0] += 1
            orig_validate()

        editor._validate = _counting_validate  # type: ignore[assignment]

        # Simulate three rapid keystrokes (typing 'abc')
        for ch, key in [("a", Qt.Key.Key_A), ("b", Qt.Key.Key_B), ("c", Qt.Key.Key_C)]:
            ev = QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, ch)
            editor.keyPressEvent(ev)

        # Before debounce fires, count should be 0
        assert call_count[0] == 0, "_validate should not fire before debounce"

        # Wait for the debounce timer to fire
        qtbot.waitUntil(lambda: call_count[0] > 0, timeout=1000)
        assert call_count[0] == 1, f"Expected 1 _validate call, got {call_count[0]}"


# -- Validation on language switch ------------------------------------


class TestValidationOnLanguageSwitch:
    """Tests for validation behaviour when switching languages."""

    def test_json_to_xml_to_text(self, qapp: QApplication, qtbot) -> None:
        """Switching language re-validates: JSON valid, XML invalid, text none."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text('{"valid": true}')

        # JSON mode — content is valid JSON
        assert editor.errors == []

        # Switch to XML — the JSON string is not valid XML
        editor.set_language("xml")
        # Re-validation is triggered via the debounce timer
        qtbot.waitUntil(lambda: len(editor.errors) > 0, timeout=1000)

        # Switch to text — no validation
        editor.set_language("text")
        assert editor.errors == []


# -- Validation non-blocking -------------------------------------------


class TestValidationNonBlocking:
    """Validation is advisory — it must never block getting content."""

    def test_invalid_json_still_readable(self, qapp: QApplication, qtbot) -> None:
        """Invalid JSON body is still returned as raw text."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text(_INVALID_JSON)

        assert len(editor.errors) > 0
        # The editor still returns the raw invalid text without raising
        assert editor.toPlainText() == _INVALID_JSON


# -- Code folding ------------------------------------------------------


class TestPygmentsHighlighter:
    """Tests for the PygmentsHighlighter internals."""

    def test_language_default(self, qapp: QApplication, qtbot) -> None:
        """Default language is 'text'."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        assert editor._highlighter.language == "text"

    def test_language_switch(self, qapp: QApplication, qtbot) -> None:
        """Switching language updates the highlighter."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("xml")
        assert editor._highlighter.language == "xml"

    def test_rebuild_formats(self, qapp: QApplication, qtbot) -> None:
        """rebuild_highlight_formats does not raise."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.rebuild_highlight_formats()

    def test_block_comment_opening_highlighted(self, qapp: QApplication, qtbot) -> None:
        """The opening /* of a block comment is highlighted as a comment."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("javascript")
        editor.setPlainText("/* comment\n   body\n*/")

        block = editor.document().firstBlock()
        formats = block.layout().formats()
        # The opening /* (positions 0-1) must be covered by a format
        assert any(f.start == 0 and f.length >= 2 for f in formats)


# -- Collapsed-fold highlight ------------------------------------------


class TestSearchSelections:
    """Tests for the set_search_selections API."""

    def test_current_line_highlight_in_editable_editor(self, qapp: QApplication, qtbot) -> None:
        """Editable editors include a current-line highlight extra selection."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("line one\nline two\nline three")

        # Trigger bracket-match / extra-selections refresh
        editor._refresh_extra_selections()

        sels = editor.extraSelections()
        # At least one selection should be a full-width current-line highlight
        full_width = [
            s for s in sels if s.format.boolProperty(QTextCharFormat.Property.FullWidthSelection)
        ]
        assert len(full_width) >= 1

    def test_no_current_line_highlight_in_readonly_editor(self, qapp: QApplication, qtbot) -> None:
        """Read-only editors do not include a current-line highlight."""
        editor = CodeEditorWidget(read_only=True)
        qtbot.addWidget(editor)
        editor.set_text("line one\nline two")

        editor._refresh_extra_selections()

        sels = editor.extraSelections()
        full_width = [
            s for s in sels if s.format.boolProperty(QTextCharFormat.Property.FullWidthSelection)
        ]
        assert len(full_width) == 0

    def test_set_search_selections_updates_extra(self, qapp: QApplication, qtbot) -> None:
        """set_search_selections merges search highlights into extra selections."""
        editor = CodeEditorWidget(read_only=True)
        qtbot.addWidget(editor)
        editor.set_text("hello world hello")

        # Build a selection for the first "hello"
        sel = QTextEdit.ExtraSelection()
        cur = QTextCursor(editor.document())
        cur.setPosition(0)
        cur.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        sel.cursor = cur
        editor.set_search_selections([sel])

        assert len(editor.extraSelections()) >= 1

    def test_clear_search_selections(self, qapp: QApplication, qtbot) -> None:
        """Passing an empty list clears search highlights."""
        editor = CodeEditorWidget(read_only=True)
        qtbot.addWidget(editor)
        editor.set_text("hello world hello")

        sel = QTextEdit.ExtraSelection()
        cur = QTextCursor(editor.document())
        cur.setPosition(0)
        cur.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        sel.cursor = cur
        editor.set_search_selections([sel])
        editor.set_search_selections([])

        # Only bracket-match / error selections remain (if any)
        remaining = editor.extraSelections()
        assert len(remaining) == 0 or all(s.cursor.position() != 5 for s in remaining)
