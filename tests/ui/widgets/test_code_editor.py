"""Tests for the reusable CodeEditorWidget.

Exercises syntax highlighting, code folding, bracket matching,
auto-close, validation, prettify, word wrap, and search selections.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QFocusEvent, QHelpEvent, QKeyEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTextEdit, QToolTip, QTreeWidget

from ui.widgets.code_editor import CodeEditorWidget, SyntaxError_
from ui.widgets.code_editor.editor_keyboard import _is_parameter_hint_shortcut
from ui.widgets.debug_value_tree import debug_tree_cell_text

# -- Helpers -----------------------------------------------------------

_SAMPLE_JSON = '{"name": "Alice", "age": 30}'
_PRETTY_JSON = json.dumps(json.loads(_SAMPLE_JSON), indent=4, ensure_ascii=False)
_SAMPLE_XML = "<root><child>text</child></root>"
_INVALID_JSON = '{"name": "Alice", "age": }'
_INVALID_XML = "<root><child>text</root>"


# -- Parameter hint (Ctrl+P) ------------------------------------------


class TestParameterHintShortcut:
    """Ctrl+P must match even when Qt adds non-chord modifier bits."""

    def test_group_switch_bit_still_matches(self, qapp: QApplication) -> None:
        """Regression: equality to ``ControlModifier`` alone dropped the shortcut."""
        m = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.GroupSwitchModifier
        ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_P, m, "")
        assert _is_parameter_hint_shortcut(ev) is True

    def test_shift_control_p_rejected(self, qapp: QApplication) -> None:
        m = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_P, m, "")
        assert _is_parameter_hint_shortcut(ev) is False

    def test_ctrl_p_shows_popup_inside_call(self, qapp: QApplication, qtbot) -> None:
        """``keyPressEvent`` with Ctrl+P surfaces a signature when the cursor is in a call."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("javascript")
        editor.setPlainText("pm.variables.set(")
        editor.moveCursor(QTextCursor.MoveOperation.End)
        ev = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier, ""
        )
        editor.keyPressEvent(ev)
        assert editor._parameter_hint_popup.isVisible()

    def test_ctrl_p_read_only_editor_still_shows_hint(self, qapp: QApplication, qtbot) -> None:
        """Hints are useful when viewing code in a read-only ``CodeEditorWidget``."""
        editor = CodeEditorWidget(read_only=True)
        qtbot.addWidget(editor)
        editor.set_language("javascript")
        editor.setPlainText("pm.variables.set(")
        editor.moveCursor(QTextCursor.MoveOperation.End)
        ev = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier, ""
        )
        editor.keyPressEvent(ev)
        assert editor._parameter_hint_popup.isVisible()

    def test_focus_out_active_window_reason_keeps_hint(self, qapp: QApplication, qtbot) -> None:
        """Showing a Tool popup raises ActiveWindowFocusReason; hint must survive it."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("javascript")
        editor.setPlainText("pm.variables.set(")
        editor.moveCursor(QTextCursor.MoveOperation.End)
        editor.trigger_parameter_hint()
        assert editor._parameter_hint_popup.isVisible()

        ev = QFocusEvent(QFocusEvent.Type.FocusOut, Qt.FocusReason.ActiveWindowFocusReason)
        editor.focusOutEvent(ev)
        assert editor._parameter_hint_popup.isVisible()

    def test_focus_out_popup_reason_keeps_hint(self, qapp: QApplication, qtbot) -> None:
        """PopupFocusReason fires when child popups open; hint must survive it."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("javascript")
        editor.setPlainText("pm.variables.set(")
        editor.moveCursor(QTextCursor.MoveOperation.End)
        editor.trigger_parameter_hint()
        assert editor._parameter_hint_popup.isVisible()

        ev = QFocusEvent(QFocusEvent.Type.FocusOut, Qt.FocusReason.PopupFocusReason)
        editor.focusOutEvent(ev)
        assert editor._parameter_hint_popup.isVisible()

    def test_paren_keystroke_multiline_shows_hint(self, qapp: QApplication, qtbot) -> None:
        """Typing ``(`` after a known method on a later line still resolves the call."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("javascript")
        editor.setPlainText("// header\n// padding\npm.variables.set")
        editor.moveCursor(QTextCursor.MoveOperation.End)
        ev = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_ParenLeft, Qt.KeyboardModifier.NoModifier, "("
        )
        editor.keyPressEvent(ev)
        assert editor._parameter_hint_popup.isVisible()
        assert "key: string" in editor._parameter_hint_popup._label.text()

    def test_focus_out_mouse_reason_dismisses_hint(self, qapp: QApplication, qtbot) -> None:
        """User clicking outside the editor genuinely loses focus; hint should hide."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("javascript")
        editor.setPlainText("pm.variables.set(")
        editor.moveCursor(QTextCursor.MoveOperation.End)
        editor.trigger_parameter_hint()
        assert editor._parameter_hint_popup.isVisible()

        ev = QFocusEvent(QFocusEvent.Type.FocusOut, Qt.FocusReason.MouseFocusReason)
        editor.focusOutEvent(ev)
        assert not editor._parameter_hint_popup.isVisible()


class TestLocalRequireCompletionPopup:
    """``pm.require('local:…')`` opens the shared completion popup."""

    def test_typing_local_prefix_shows_paths(self, qapp: QApplication, qtbot) -> None:
        """After ``local:`` the completion popup lists DB-backed virtual paths."""
        from database.models.local_scripts.local_script_repository import (
            create_folder,
            create_script,
        )

        from ui.widgets.code_editor import popup_registry

        root = create_folder("auth")
        create_script(root.id, "helper", language="javascript")

        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("javascript")
        editor.setPlainText("pm.require('local:")
        cur = editor.textCursor()
        cur.setPosition(len(editor.toPlainText()))
        editor.setTextCursor(cur)
        editor._maybe_trigger_local_path_completion()
        popup = popup_registry.completion_popup()
        qtbot.waitUntil(popup.is_active, timeout=2000)
        labels = [popup._list.item(i).text() for i in range(popup._list.count())]
        assert "auth/helper.js" in labels


class TestSymbolDocFeatures:
    """Ctrl+hover, Ctrl+click, and Ctrl+Q symbol-doc surfaces."""

    def test_ident_at_pos_resolves_dot_path(self, qapp: QApplication, qtbot) -> None:
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("javascript")
        editor.setPlainText("pm.variables.set('k', 1);")
        cur = editor.textCursor()
        cur.setPosition(15)  # inside 'set'
        rect = editor.cursorRect(cur)
        hit = editor._ident_at_pos(rect.center())
        assert hit is not None
        assert hit[0] == "pm.variables.set"

    def test_resolve_symbol_pm_api(self, qapp: QApplication) -> None:
        from ui.widgets.code_editor.completion.engine import CompletionEngine

        eng = CompletionEngine("javascript")
        sym = eng.resolve_symbol("pm.variables.set", "")
        assert sym is not None
        assert sym.kind == "method"
        assert "key" in (sym.signature or "")
        assert sym.origin == "pm API"

    def test_find_definition_pos_user_var(self, qapp: QApplication) -> None:
        from ui.widgets.code_editor.completion.engine import CompletionEngine

        eng = CompletionEngine("javascript")
        src = "// hi\nconst foo = 1;\n"
        pos = eng.find_definition_pos("foo", src)
        assert pos is not None
        assert src[pos:].startswith("const foo")

    def test_ctrl_q_shows_symbol_popup(self, qapp: QApplication, qtbot) -> None:
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("javascript")
        editor.setPlainText("pm.variables.set('k', 1);")
        cur = editor.textCursor()
        cur.setPosition(15)
        editor.setTextCursor(cur)
        ev = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Q,
            Qt.KeyboardModifier.ControlModifier,
            "",
        )
        editor.keyPressEvent(ev)
        assert editor._symbol_doc_popup.isVisible()


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

    def test_prettify_python(self, qapp: QApplication, qtbot) -> None:
        """Format Document uses Ruff for Python (jedi LSP has no formatter)."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("python")
        editor.setPlainText('x={"a":1}')
        assert editor.format_document() is True
        assert editor.toPlainText() != 'x={"a":1}'

    def test_format_selection_json(self, qapp: QApplication, qtbot) -> None:
        """Format Selection replaces the selected JSON with pretty-printed text."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.setPlainText('{"a":1,"b":[2,3]}')
        editor.selectAll()
        assert editor.format_selection() is True
        assert '"a": 1' in editor.toPlainText()

    def test_format_menu_after_undo_redo(self, qapp: QApplication, qtbot) -> None:
        """Format actions appear immediately after Undo/Redo in the context menu."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("x = 1")
        menu = editor.createStandardContextMenu()
        editor._add_format_menu_actions(menu)
        actions = menu.actions()
        undo_idx = next(i for i, a in enumerate(actions) if "Undo" in a.text())
        redo_idx = next(i for i, a in enumerate(actions) if "Redo" in a.text())
        fmt_idx = next(i for i, a in enumerate(actions) if "Format Document" in a.text())
        cut_idx = next(i for i, a in enumerate(actions) if "Ctrl+X" in a.text())
        assert undo_idx < fmt_idx
        assert redo_idx < fmt_idx
        assert fmt_idx < cut_idx
        assert actions[cut_idx - 1].isSeparator()

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
        from esprima_test_util import (  # type: ignore[import-not-found]
            deno_and_esprima_available,
        )

        if not deno_and_esprima_available():
            pytest.skip("Deno + Esprima required for JavaScript editor validation")

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

    def test_inline_log_annotations_store_and_clear(self, qapp: QApplication, qtbot) -> None:
        """Inline console decorations can be set and cleared."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_inline_log_annotations({0: "hello", 2: "world"})
        assert editor._inline_log_annotations == {0: "hello", 2: "world"}
        editor.clear_inline_log_annotations()
        assert editor._inline_log_annotations == {}


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

    def test_debug_line_adds_full_width_selection(self, qapp: QApplication, qtbot) -> None:
        """Paused debug line (0-based) gets a full-width extra selection."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("zero\none\ntwo")
        editor.set_debug_line(1)  # line "one"
        sels = editor.extraSelections()
        fw = [s for s in sels if s.format.boolProperty(QTextCharFormat.Property.FullWidthSelection)]
        on_one = [s for s in fw if s.cursor.block().blockNumber() == 1]
        assert len(on_one) == 1
        assert on_one[0].format.background().color().isValid()

    def test_breakpoint_line_adds_full_width_tint(self, qapp: QApplication, qtbot) -> None:
        """A breakpoint on a line adds a full-width extra selection in breakpoint-line colour."""
        from PySide6.QtGui import QColor

        from ui.styling.theme import COLOR_EDITOR_BREAKPOINT_LINE, COLOR_EDITOR_DEBUG_LINE

        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("a\nb\nc")
        editor.toggle_breakpoint(1)
        sels = editor.extraSelections()
        fw = [s for s in sels if s.format.boolProperty(QTextCharFormat.Property.FullWidthSelection)]
        on_b = [s for s in fw if s.cursor.block().blockNumber() == 1]
        assert len(on_b) == 1
        assert on_b[0].format.background().color() == QColor(COLOR_EDITOR_BREAKPOINT_LINE)
        # Debug execution line adds a second full-width selection on the same line
        editor.set_debug_line(1)
        sels2 = editor.extraSelections()
        fw2 = [
            s for s in sels2 if s.format.boolProperty(QTextCharFormat.Property.FullWidthSelection)
        ]
        on_b_dbg = [s for s in fw2 if s.cursor.block().blockNumber() == 1]
        assert len(on_b_dbg) >= 1
        line_hex = {s.format.background().color().name(QColor.NameFormat.HexArgb) for s in on_b_dbg}
        assert QColor(COLOR_EDITOR_DEBUG_LINE).name(QColor.NameFormat.HexArgb) in line_hex
        assert QColor(COLOR_EDITOR_BREAKPOINT_LINE).name(QColor.NameFormat.HexArgb) in line_hex

    def test_breakpoints_changed_fires_on_toggle(self, qapp: QApplication, qtbot) -> None:
        """Gutter breakpoint toggles emit ``breakpoints_changed`` for live debug sync."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("a\nb")
        n = 0

        def _bump() -> None:
            nonlocal n
            n += 1

        editor.breakpoints_changed.connect(_bump)
        editor.toggle_breakpoint(0)
        assert n == 1
        editor.toggle_breakpoint(0)
        assert n == 2

    def test_hiding_breakpoint_gutter_clears_hover_line(self, qapp: QApplication, qtbot) -> None:
        """Turning off the breakpoint column clears the hover preview line."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_breakpoint_gutter_visible(True)
        editor._set_breakpoint_hover_line(0)
        editor.set_breakpoint_gutter_visible(False)
        assert editor._breakpoint_hover_line is None

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


class TestBreakpointGutterUx:
    """Wide gutter clicks, ``pm.test`` column vs breakpoint column, and fold + breakpoint."""

    def test_breakpoint_add_preview_active_respects_breakpoint_and_debug_line(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Tooltip / hollow-ring logic skips lines that already have a BP or are the debug line."""
        editor = CodeEditorWidget(read_only=False)
        qtbot.addWidget(editor)
        editor.set_breakpoint_gutter_visible(True)
        editor.setPlainText("a\nb")
        editor._set_breakpoint_hover_line(0)
        assert editor._breakpoint_add_preview_active()
        editor.toggle_breakpoint(0)
        assert not editor._breakpoint_add_preview_active()
        editor.toggle_breakpoint(0)
        assert editor._breakpoint_add_preview_active()
        editor.set_debug_line(0)
        assert not editor._breakpoint_add_preview_active()

    def test_line_has_pm_test_at_gutter_y(self, qapp: QApplication, qtbot) -> None:
        """``pm.test`` rows are detected by *y* for the full test-gutter column."""
        editor = CodeEditorWidget(read_only=False)
        qtbot.addWidget(editor)
        editor.resize(520, 240)
        editor.set_language("javascript")
        editor.set_test_gutter_enabled(True)
        editor.setPlainText('pm.test("n", function () {});')
        editor.set_pm_tests([{"line": 1, "name": "n"}])
        qtbot.waitExposed(editor)
        block = editor.document().firstBlock()
        top = float(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
        bottom = top + float(editor.blockBoundingRect(block).height())
        y = (top + bottom) / 2.0
        assert editor._line_has_pm_test_at_gutter_y(y)
        assert not editor._line_has_pm_test_at_gutter_y(y + 9999.0)

    def test_test_gutter_right_edge_opens_test_not_breakpoint(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Clicks on the right edge of a ``pm.test`` row still invoke the test gutter, not BP."""
        editor = CodeEditorWidget(read_only=False)
        qtbot.addWidget(editor)
        editor.resize(520, 240)
        editor.set_language("javascript")
        editor.set_test_gutter_enabled(True)
        editor.set_breakpoint_gutter_visible(True)
        editor.setPlainText('pm.test("n", function () {});')
        editor.set_pm_tests([{"line": 1, "name": "n"}])
        qtbot.waitExposed(editor)
        block = editor.document().firstBlock()
        top = float(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
        bottom = top + float(editor.blockBoundingRect(block).height())
        y = (top + bottom) / 2.0
        tw = editor.test_gutter_width()
        tg = editor._test_gutter_area
        with patch.object(editor, "_show_test_menu") as mock_show:
            qtbot.mouseClick(tg, Qt.MouseButton.LeftButton, pos=QPoint(int(tw) - 1, int(y)))
        mock_show.assert_called_once()
        assert 0 not in editor.breakpoints

    def test_line_number_left_click_toggles_breakpoint(self, qapp: QApplication, qtbot) -> None:
        """Clicking the line-number column toggles a breakpoint for that row."""
        editor = CodeEditorWidget(read_only=False)
        qtbot.addWidget(editor)
        editor.resize(520, 240)
        editor.setPlainText("alpha\nbeta")
        editor.set_breakpoint_gutter_visible(True)
        qtbot.waitExposed(editor)
        ln = editor._line_number_area
        block = editor.document().firstBlock()
        top = int(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
        bottom = int(top + editor.blockBoundingRect(block).height())
        y = (top + bottom) // 2
        assert 0 not in editor.breakpoints
        qtbot.mouseClick(ln, Qt.MouseButton.LeftButton, pos=QPoint(max(1, ln.width() // 2), y))
        assert 0 in editor.breakpoints
        qtbot.mouseClick(ln, Qt.MouseButton.LeftButton, pos=QPoint(max(1, ln.width() // 2), y))
        assert 0 not in editor.breakpoints

    def test_fold_gutter_on_non_fold_line_toggles_breakpoint(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Fold gutter clicks on lines without a fold mark toggle the breakpoint instead."""
        editor = CodeEditorWidget(read_only=False)
        qtbot.addWidget(editor)
        editor.resize(520, 240)
        editor.set_language("text")
        editor.setPlainText("x\ny")
        editor.set_breakpoint_gutter_visible(True)
        qtbot.waitExposed(editor)
        assert 0 not in editor._fold_regions
        fg = editor._fold_gutter_area
        block = editor.document().firstBlock()
        top = int(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
        bottom = int(top + editor.blockBoundingRect(block).height())
        y = (top + bottom) // 2
        assert 0 not in editor.breakpoints
        qtbot.mouseClick(fg, Qt.MouseButton.LeftButton, pos=QPoint(fg.width() // 2, y))
        assert 0 in editor.breakpoints


class TestDebugHoverInspect:
    """Paused-debug hover: ``pm`` from *root_values* and expandable dict popup."""

    def test_var_at_cursor_resolves_pm_from_root_values_only(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """When the flat map omits ``pm``, hover still resolves from *root_values*."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("pm.response")
        editor.set_debug_locals(
            {"response": {"code": 201}},
            root_values={"pm": {"response": {"code": 201}}},
        )
        cursor = editor.textCursor()
        cursor.setPosition(0)
        editor.setTextCursor(cursor)
        pos = editor.cursorRect(cursor).center()
        assert editor._var_at_cursor(pos) == "pm"

    def test_debug_hover_dict_uses_expandable_tree(self, qapp: QApplication, qtbot) -> None:
        """Dict snapshots open the tree page with top-level keys."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor._var_hover_global_pos = QPoint(320, 240)
        editor._show_debug_value_popup("pm", {"status": "ok", "n": 1})
        qtbot.waitUntil(lambda: editor._debug_popup.isVisible(), timeout=2000)
        tree = editor._debug_popup.findChild(QTreeWidget, "debugHoverValueTree")
        assert tree is not None
        assert tree.isVisible()
        assert tree.topLevelItemCount() == 2

    def test_debug_hover_pm_resolves_snapshot_when_locals_are_object_string(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """CDP ``Object`` description in flat locals is replaced by structured *root_values*."""
        from PySide6.QtWidgets import QTreeWidget

        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_debug_locals(
            {"pm": "Object", "response.code": 201},
            root_values={"pm": {"response.code": 201, "response.status": "Created"}},
        )
        editor._var_hover_name = "pm"
        editor._var_hover_global_pos = QPoint(320, 240)
        editor._show_var_hover_popup()
        qtbot.waitUntil(lambda: editor._debug_popup.isVisible(), timeout=2000)
        tree = editor._debug_popup.findChild(QTreeWidget, "debugHoverValueTree")
        assert tree is not None and tree.isVisible()
        assert tree.topLevelItemCount() == 2

    def test_debug_hover_pm_prefers_nonempty_cdp_dict_over_snapshot(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """When CDP materialised ``pm`` as a non-empty dict, use it over the evaluate snapshot."""
        from PySide6.QtWidgets import QTreeWidget

        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_debug_locals(
            {"pm": {"response": {"code": 500}}},
            root_values={"pm": {"response.code": 201}},
        )
        editor._var_hover_name = "pm"
        editor._var_hover_global_pos = QPoint(320, 240)
        editor._show_var_hover_popup()
        qtbot.waitUntil(lambda: editor._debug_popup.isVisible(), timeout=2000)
        tree = editor._debug_popup.findChild(QTreeWidget, "debugHoverValueTree")
        assert tree is not None
        names: set[str] = set()
        for i in range(tree.topLevelItemCount()):
            it = tree.topLevelItem(i)
            assert it is not None
            names.add(debug_tree_cell_text(it, 0))
        assert "response" in names
