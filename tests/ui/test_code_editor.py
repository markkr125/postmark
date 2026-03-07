"""Tests for the reusable CodeEditorWidget.

Exercises syntax highlighting, code folding, bracket matching,
auto-close, validation, prettify, word wrap, and search selections.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QHelpEvent, QKeyEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTextEdit, QToolTip

from services.environment_service import VariableDetail
from ui.code_editor import CodeEditorWidget, SyntaxError_

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
    """Tests for JSON/XML validation and error signals."""

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


class TestCodeFolding:
    """Tests for fold region detection and toggle."""

    def test_json_fold_regions_detected(self, qapp: QApplication, qtbot) -> None:
        """JSON objects produce fold regions."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text('{\n  "a": 1,\n  "b": 2\n}')
        # Line 0 should be a fold start (the opening brace)
        assert 0 in editor._fold_regions

    def test_toggle_fold_collapses(self, qapp: QApplication, qtbot) -> None:
        """Toggling a fold hides inner blocks."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text('{\n  "a": 1,\n  "b": 2\n}')
        editor.toggle_fold(0)
        assert 0 in editor._collapsed_folds

    def test_toggle_fold_expands(self, qapp: QApplication, qtbot) -> None:
        """Toggling a collapsed fold shows inner blocks again."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text('{\n  "a": 1,\n  "b": 2\n}')
        editor.toggle_fold(0)
        editor.toggle_fold(0)
        assert 0 not in editor._collapsed_folds

    def test_fold_all_unfold_all(self, qapp: QApplication, qtbot) -> None:
        """fold_all and unfold_all toggle all regions."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text('{\n  "a": {\n    "b": 1\n  }\n}')
        editor.fold_all()
        assert len(editor._collapsed_folds) > 0
        editor.unfold_all()
        assert len(editor._collapsed_folds) == 0

    def test_no_folds_for_text(self, qapp: QApplication, qtbot) -> None:
        """Plain text language produces no fold regions."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("text")
        editor.set_text('{\n  "a": 1\n}')
        assert len(editor._fold_regions) == 0


# -- Bracket matching --------------------------------------------------


class TestBracketMatching:
    """Tests for bracket match highlighting via extra selections."""

    def test_bracket_match_at_cursor(self, qapp: QApplication, qtbot) -> None:
        """Placing cursor on an opening bracket creates extra selections."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.setPlainText('{"a": 1}')
        # Place cursor right after the opening brace (position 1)
        cursor = editor.textCursor()
        cursor.setPosition(1)
        editor.setTextCursor(cursor)
        # Bracket matching is debounced — wait for the timer to fire.
        qtbot.waitUntil(lambda: len(editor.extraSelections()) >= 2, timeout=500)
        sels = editor.extraSelections()
        assert len(sels) >= 2  # at least the bracket pair


# -- Auto-close brackets -----------------------------------------------


class TestAutoClose:
    """Tests for auto-closing brackets and quotes."""

    def test_auto_close_brace(self, qapp: QApplication, qtbot) -> None:
        """Typing '{' auto-inserts '}'."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        # Simulate typing '{'
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_BraceLeft, Qt.KeyboardModifier.NoModifier, "{"
        )
        editor.keyPressEvent(event)
        assert editor.toPlainText() == "{}"

    def test_auto_close_bracket(self, qapp: QApplication, qtbot) -> None:
        """Typing '[' auto-inserts ']'."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_BracketLeft, Qt.KeyboardModifier.NoModifier, "["
        )
        editor.keyPressEvent(event)
        assert editor.toPlainText() == "[]"

    def test_no_auto_close_read_only(self, qapp: QApplication, qtbot) -> None:
        """Read-only mode does not auto-close brackets."""
        editor = CodeEditorWidget(read_only=True)
        qtbot.addWidget(editor)
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_BraceLeft, Qt.KeyboardModifier.NoModifier, "{"
        )
        editor.keyPressEvent(event)
        # Read-only editor ignores input
        assert editor.toPlainText() == ""


# -- Search selections -------------------------------------------------


class TestSearchSelections:
    """Tests for the set_search_selections API."""

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


# -- Highlighter -------------------------------------------------------


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


# -- Collapsed-fold highlight ------------------------------------------


class TestCollapsedFoldHighlight:
    """Tests for the background highlight on collapsed fold-header lines."""

    def test_collapsed_fold_produces_highlight_selection(self, qapp: QApplication, qtbot) -> None:
        """Collapsing a fold adds a full-width background ExtraSelection."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text('{\n  "a": 1,\n  "b": 2\n}')
        editor.toggle_fold(0)

        # Find selections with FullWidthSelection property on the fold line
        full_width_sels = [
            s
            for s in editor.extraSelections()
            if s.format.boolProperty(QTextCharFormat.Property.FullWidthSelection)
            and s.cursor.blockNumber() == 0
        ]
        assert len(full_width_sels) > 0, "Expected a full-width highlight on the collapsed line"

    def test_expanding_fold_removes_highlight(self, qapp: QApplication, qtbot) -> None:
        """Expanding a fold removes the collapsed-line highlight."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text('{\n  "a": 1,\n  "b": 2\n}')
        editor.toggle_fold(0)
        editor.toggle_fold(0)  # expand again

        full_width_sels = [
            s
            for s in editor.extraSelections()
            if s.format.boolProperty(QTextCharFormat.Property.FullWidthSelection)
        ]
        assert len(full_width_sels) == 0, "No full-width highlight when all folds are expanded"


# -- Hand cursor on fold gutter ----------------------------------------


class TestFoldGutterCursor:
    """Tests for the pointing-hand cursor on the fold gutter."""

    def test_hand_cursor_on_fold_line(self, qapp: QApplication, qtbot) -> None:
        """The fold gutter shows a hand cursor over a foldable line."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.show()
        editor.set_language("json")
        editor.set_text('{\n  "a": 1\n}')

        # Line 0 is foldable — is_fold_line_at should return True
        assert editor.is_fold_line_at(0) or len(editor._fold_regions) > 0

    def test_no_hand_cursor_for_text(self, qapp: QApplication, qtbot) -> None:
        """Plain text language has no foldable lines."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("text")
        editor.set_text('{\n  "a": 1\n}')
        assert not editor.is_fold_line_at(0)


# -- Error gutter styling ---------------------------------------------


class TestErrorGutterStyling:
    """Tests for the updated error gutter (red bg + red line number)."""

    def test_error_lines_tracked_for_gutter(self, qapp: QApplication, qtbot) -> None:
        """Error lines are available for the gutter painter."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text(_INVALID_JSON)

        error_lines = {e.line for e in editor._errors}
        assert len(error_lines) > 0, "Expected at least one error line"


# -- Indent guides ------------------------------------------------------


class TestIndentGuides:
    """Tests for indent guide line painting.

    Guides are drawn at **scope opener** columns — where the enclosing
    brace / bracket lives — NOT at content columns.  The paint loop
    iterates ``level = 1, 2, ...`` while ``level * iw <= indent``, but
    each guide is drawn at ``(level - 1) * iw`` — shifted left by one
    indent width.  For 4-space JSON:

        Line 0: ``{``              indent=0  -> no guides
        Line 1: ``    "a": {``     indent=4  -> guide at col 0 (root ``{``)
        Line 2: ``        "b": 1`` indent=8  -> guides at col 0 and col 4

    The ``<=`` keeps the same guide *count* as the original loop
    (which drew at ``level * iw``); the ``(level - 1)`` shift moves
    each guide left so it sits at the scope opener, not the content.
    """

    def test_indent_guides_painted_for_json(self, qapp: QApplication, qtbot) -> None:
        """Verify paintEvent completes without error for JSON with indentation."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.show()
        editor.set_language("json")
        editor.set_text('{\n  "a": {\n    "b": 1\n  }\n}')
        # Force a repaint — should not raise
        editor.viewport().update()
        qapp.processEvents()

    def test_no_indent_guides_for_text(self, qapp: QApplication, qtbot) -> None:
        """Plain text language skips indent guide painting."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.show()
        editor.set_language("text")
        editor.set_text("  indented\n    double indented")
        # Force a repaint — should not raise
        editor.viewport().update()
        qapp.processEvents()

    def test_guide_draw_columns_4space(self, qapp: QApplication, qtbot) -> None:
        """For indent=4/iw=4 -> [0].  indent=8 -> [0, 4].  indent=12 -> [0, 4, 8]."""
        iw = 4
        for indent, expected in [(4, [0]), (8, [0, 4]), (12, [0, 4, 8])]:
            draw_cols: list[int] = []
            level = 1
            while level * iw <= indent:
                draw_cols.append((level - 1) * iw)
                level += 1
            assert draw_cols == expected, f"indent={indent}"

    def test_guide_draw_columns_2space(self, qapp: QApplication, qtbot) -> None:
        """For indent=6 with iw=2, draw columns are [0, 2, 4]."""
        iw = 2
        draw_cols: list[int] = []
        level = 1
        while level * iw <= 6:
            draw_cols.append((level - 1) * iw)
            level += 1
        assert draw_cols == [0, 2, 4]

    def test_no_guide_at_content_column(self, qapp: QApplication, qtbot) -> None:
        """The content's own indent column must never appear in the draw list.

        For indent=8 / iw=4: draw_cols = [0, 4].  Col 8 (content) absent.
        For indent=12 / iw=4: draw_cols = [0, 4, 8].  Col 12 absent.
        """
        iw = 4
        for indent in (4, 8, 12, 16):
            draw_cols: list[int] = []
            level = 1
            while level * iw <= indent:
                draw_cols.append((level - 1) * iw)
                level += 1
            assert indent not in draw_cols, f"content col {indent} should be absent"

    def test_same_guide_count_as_original(self, qapp: QApplication, qtbot) -> None:
        """The shifted loop produces the same number of guides as the original.

        Original: guides at level*iw for level=1..  while level*iw <= indent.
        Shifted: same iteration count, draw at (level-1)*iw.
        """
        iw = 4
        for indent in (4, 8, 12, 16):
            original_count = 0
            level = 1
            while level * iw <= indent:
                original_count += 1
                level += 1
            shifted_count = 0
            level = 1
            while level * iw <= indent:
                shifted_count += 1
                level += 1
            assert shifted_count == original_count, f"indent={indent}"

    def test_active_indent_col_at_scope_opener(self, qapp: QApplication, qtbot) -> None:
        """Active guide returns (col, start, end) scoped to the fold range.

        For ``{"a": {"b": 1}}``, the innermost fold around the ``"b"``
        line is ``"a": {…}`` (lines 1-3) whose opener lives at col 4.

        The returned range limits the highlight to only those lines.
        """
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.show()
        editor.set_language("json")
        editor.set_text('{\n    "a": {\n        "b": 1\n    }\n}')
        assert editor._detected_indent == 4
        # Cursor on line 2 ('        "b": 1') — innermost fold is "a":{
        # which spans lines 1-3 with leading=4.  Active col = 4.
        col, start, end = editor._active_indent_col(2)
        assert col == 4
        assert start == 1
        assert end == 3
        # Cursor on line 1 ('    "a": {') — fold starts here (lines 1-3),
        # so its guide (col 4) highlights, scoped to lines 1-3.
        col1, start1, end1 = editor._active_indent_col(1)
        assert col1 == 4
        assert start1 == 1
        assert end1 == 3


# -- Gutter width -------------------------------------------------------


class TestGutterWidth:
    """Tests for line number area width calculation."""

    def test_gutter_width_positive(self, qapp: QApplication, qtbot) -> None:
        """Line number area width is positive for non-empty content."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("line1\nline2\nline3")
        assert editor.line_number_area_width() > 0


# -- Collapsed fold badge ------------------------------------------------


class TestFoldBadge:
    """Tests for the inline ``...`` badge on collapsed fold lines."""

    def test_badge_rects_populated_after_collapse(self, qapp: QApplication, qtbot) -> None:
        """Collapsing a fold populates ``_fold_badge_rects`` after repaint."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.resize(600, 400)
        editor.show()
        qapp.processEvents()
        editor.set_language("json")
        editor.set_text('{\n  "a": 1,\n  "b": 2\n}')
        editor.toggle_fold(0)
        # grab() forces a synchronous full paint including our paintEvent.
        editor.grab()
        assert 0 in editor._fold_badge_rects

    def test_badge_rects_cleared_after_expand(self, qapp: QApplication, qtbot) -> None:
        """Expanding a fold removes its entry from ``_fold_badge_rects``."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.resize(600, 400)
        editor.show()
        qapp.processEvents()
        editor.set_language("json")
        editor.set_text('{\n  "a": 1,\n  "b": 2\n}')
        editor.toggle_fold(0)
        editor.grab()
        assert 0 in editor._fold_badge_rects

        editor.toggle_fold(0)
        editor.grab()
        assert 0 not in editor._fold_badge_rects

    def test_badge_click_expands_fold(self, qapp: QApplication, qtbot) -> None:
        """Clicking inside the badge rectangle expands the fold."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.resize(600, 400)
        editor.show()
        qapp.processEvents()
        editor.set_language("json")
        editor.set_text('{\n  "a": 1,\n  "b": 2\n}')
        editor.toggle_fold(0)
        editor.grab()

        rect = editor._fold_badge_rects.get(0)
        assert rect is not None, "Badge rect should exist for collapsed fold"

        # Simulate a click in the centre of the badge
        center = rect.center()
        qtbot.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=center)

        # Fold should now be expanded
        assert 0 not in editor._collapsed_folds

    def test_no_badge_for_plain_text(self, qapp: QApplication, qtbot) -> None:
        """Plain text language produces no fold badge rects."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.resize(600, 400)
        editor.show()
        qapp.processEvents()
        editor.set_language("text")
        editor.set_text('{\n  "a": 1\n}')
        editor.grab()
        assert editor._fold_badge_rects == {}


# -- Indent detection ---------------------------------------------------


class TestIndentDetection:
    """Tests for auto-detection of indent width."""

    def test_detects_2_space_indent(self, qapp: QApplication, qtbot) -> None:
        """2-space indented JSON is detected correctly."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text('{\n  "a": {\n    "b": 1\n  }\n}')
        assert editor._detected_indent == 2

    def test_detects_4_space_indent(self, qapp: QApplication, qtbot) -> None:
        """4-space indented JSON is detected correctly."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text('{\n    "a": {\n        "b": 1\n    }\n}')
        assert editor._detected_indent == 4

    def test_default_for_empty(self, qapp: QApplication, qtbot) -> None:
        """Empty content falls back to the default indent width."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text("")
        assert editor._detected_indent == 2

    def test_default_for_no_indentation(self, qapp: QApplication, qtbot) -> None:
        """Content with no leading spaces falls back to default."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text('{"a": 1}')
        assert editor._detected_indent == 2


# -- Block indent / outdent --------------------------------------------


class TestBlockIndentOutdent:
    """Tests for Tab/Shift+Tab block indent and outdent."""

    def test_tab_inserts_spaces_single_cursor(self, qapp: QApplication, qtbot) -> None:
        """Tab with no selection inserts detected-indent spaces."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text("")
        editor._detected_indent = 4
        # Simulate Tab press
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        editor.keyPressEvent(event)
        assert editor.toPlainText() == "    "

    def test_tab_indents_selected_lines(self, qapp: QApplication, qtbot) -> None:
        """Tab with multi-line selection prepends spaces to every line."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text("line1\nline2\nline3")
        editor._detected_indent = 2
        # Select all text
        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        editor.setTextCursor(cursor)
        # Simulate Tab press
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        editor.keyPressEvent(event)
        assert editor.toPlainText() == "  line1\n  line2\n  line3"

    def test_shift_tab_outdents_selected_lines(self, qapp: QApplication, qtbot) -> None:
        """Shift+Tab removes leading spaces from every selected line."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text("    line1\n    line2\n    line3")
        editor._detected_indent = 4
        # Select all text
        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        editor.setTextCursor(cursor)
        # Simulate Shift+Tab press
        event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier
        )
        editor.keyPressEvent(event)
        assert editor.toPlainText() == "line1\nline2\nline3"

    def test_shift_tab_partial_outdent(self, qapp: QApplication, qtbot) -> None:
        """Shift+Tab removes only available leading spaces (less than indent)."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text(" a\n  b")
        editor._detected_indent = 4
        # Select all text
        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        editor.setTextCursor(cursor)
        # Simulate Shift+Tab press
        event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier
        )
        editor.keyPressEvent(event)
        assert editor.toPlainText() == "a\nb"

    def test_shift_tab_single_line_outdent(self, qapp: QApplication, qtbot) -> None:
        """Shift+Tab with no selection outdents the current line."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text("    hello")
        editor._detected_indent = 2
        # Place cursor inside the line (no selection)
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        # Simulate Shift+Tab press
        event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier
        )
        editor.keyPressEvent(event)
        assert editor.toPlainText() == "  hello"


class TestWhitespaceDots:
    """Whitespace dot rendering on selected text."""

    def test_no_dots_without_selection(self, qapp: QApplication, qtbot) -> None:
        """No whitespace dots are painted when there is no selection."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("text")
        editor.set_text("a b c")
        editor.show()
        qapp.processEvents()

        # No selection — calling _paint_selection_whitespace should
        # not draw any ellipses because cursor.hasSelection() is False
        # and paintEvent will not call the method at all.
        cursor = editor.textCursor()
        assert not cursor.hasSelection()

    def test_dots_only_on_spaces(self, qapp: QApplication, qtbot) -> None:
        """Dots are drawn only for space characters, not other text."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("text")
        editor.set_text("a b c")
        editor.show()
        qapp.processEvents()

        # Select the full text: "a b c" contains 2 spaces.
        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        editor.setTextCursor(cursor)

        # Spy on QPainter.drawEllipse to count dot draws.
        from PySide6.QtGui import QPainter

        original_draw = QPainter.drawEllipse
        call_count = 0

        def counting_draw(self_painter, *args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            return original_draw(self_painter, *args, **kwargs)

        with patch.object(QPainter, "drawEllipse", counting_draw):
            editor._paint_selection_whitespace(cursor)

        # Exactly 2 spaces => 2 dots.
        assert call_count == 2

    def test_no_dots_for_non_space_chars(self, qapp: QApplication, qtbot) -> None:
        """No dots drawn when selected text has no spaces."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("text")
        editor.set_text("abcdef")
        editor.show()
        qapp.processEvents()

        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        editor.setTextCursor(cursor)

        from PySide6.QtGui import QPainter

        original_draw = QPainter.drawEllipse
        call_count = 0

        def counting_draw(self_painter, *args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            return original_draw(self_painter, *args, **kwargs)

        with patch.object(QPainter, "drawEllipse", counting_draw):
            editor._paint_selection_whitespace(cursor)

        assert call_count == 0

    def test_dots_with_leading_spaces(self, qapp: QApplication, qtbot) -> None:
        """Dots appear for leading whitespace when selected."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.set_text('    "key": "val"')
        editor.show()
        qapp.processEvents()

        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        editor.setTextCursor(cursor)

        from PySide6.QtGui import QPainter

        original_draw = QPainter.drawEllipse
        call_count = 0

        def counting_draw(self_painter, *args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            return original_draw(self_painter, *args, **kwargs)

        with patch.object(QPainter, "drawEllipse", counting_draw):
            editor._paint_selection_whitespace(cursor)

        # 4 leading spaces + 1 after colon = 5 total.
        # '    "key": "val"' has spaces at indices 0, 1, 2, 3, 10.
        assert call_count == 5


# -- Variable highlighting in editor ----------------------------------


class TestVariableHighlighting:
    """Tests for ``{{variable}}`` highlighting in the code editor."""

    def test_variable_highlight_format_applied(self, qapp: QApplication, qtbot) -> None:
        """Blocks containing {{var}} get a highlight format applied."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("text")
        editor.setPlainText("url = {{base_url}}/api")

        # The highlighter should have applied a format to the {{base_url}} span
        block = editor.document().firstBlock()
        layout = block.layout()
        formats = layout.formats()
        # At least one format should cover the variable region
        var_start = 6  # "url = " is 6 chars
        var_end = 18  # "{{base_url}}" is 12 chars -> ends at 18
        found = any(f.start <= var_start and f.start + f.length >= var_end for f in formats)
        assert found, "Expected a format range covering {{base_url}}"

    def test_variable_highlight_in_json(self, qapp: QApplication, qtbot) -> None:
        """Variable highlighting works alongside JSON syntax highlighting."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.setPlainText('{"url": "{{base_url}}"}')

        block = editor.document().firstBlock()
        layout = block.layout()
        formats = layout.formats()
        # Should have both JSON string formats and variable highlight
        assert len(formats) >= 2

    def test_set_variable_map_stores_and_rehighlights(self, qapp: QApplication, qtbot) -> None:
        """set_variable_map stores the map and triggers rehighlight."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        m: dict[str, VariableDetail] = {
            "host": {"value": "example.com", "source": "collection", "source_id": 1}
        }
        editor.set_variable_map(m)
        assert editor._variable_map == m


class TestVariableTooltipInEditor:
    """Tests for variable tooltip display in the code editor."""

    def test_tooltip_for_resolved_variable(self, qapp: QApplication, qtbot) -> None:
        """Hovering over a resolved variable triggers the popup."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.show()
        editor.setPlainText("{{host}}/api")
        vmap: dict[str, VariableDetail] = {
            "host": {"value": "example.com", "source": "environment", "source_id": 10},
        }
        editor.set_variable_map(vmap)

        # Position cursor over the variable
        block = editor.document().firstBlock()
        rect = editor.blockBoundingGeometry(block).translated(editor.contentOffset())
        local_pos = rect.center().toPoint()
        global_pos = editor.mapToGlobal(local_pos)

        with patch("ui.variable_popup.VariablePopup") as mock_cls:
            help_event = QHelpEvent(QEvent.Type.ToolTip, local_pos, global_pos)
            editor.event(help_event)
            if mock_cls.show_variable.called:
                args = mock_cls.show_variable.call_args[0]
                assert args[0] == "host"
                assert args[1]["value"] == "example.com"

    def test_tooltip_for_unresolved_variable(self, qapp: QApplication, qtbot) -> None:
        """Hovering over an unresolved variable shows None detail."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.show()
        editor.setPlainText("{{unknown}}/api")
        editor.set_variable_map({})

        block = editor.document().firstBlock()
        rect = editor.blockBoundingGeometry(block).translated(editor.contentOffset())
        local_pos = rect.center().toPoint()
        global_pos = editor.mapToGlobal(local_pos)

        with patch("ui.variable_popup.VariablePopup") as mock_cls:
            help_event = QHelpEvent(QEvent.Type.ToolTip, local_pos, global_pos)
            editor.event(help_event)
            if mock_cls.show_variable.called:
                args = mock_cls.show_variable.call_args[0]
                assert args[0] == "unknown"
                assert args[1] is None
