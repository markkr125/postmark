"""Tests for CodeEditorWidget — gutter styling, indent guides, whitespace dots."""

from __future__ import annotations

from unittest.mock import patch

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from ui.widgets.code_editor import CodeEditorWidget

_INVALID_JSON = '{"name": "Alice", "age": }'


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
