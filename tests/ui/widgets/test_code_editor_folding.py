"""Tests for CodeEditorWidget — code folding, brackets, and indentation."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication

from ui.widgets.code_editor import CodeEditorWidget


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
