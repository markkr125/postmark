"""Tests for the SearchReplaceBar widget."""

from __future__ import annotations

from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.search_replace_bar import SearchReplaceBar


class TestSearchReplaceBarConstruction:
    """Tests for basic construction and initial state."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Widget can be instantiated without errors."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        assert bar is not None

    def test_starts_hidden(self, qapp: QApplication, qtbot) -> None:
        """Bar is hidden by default."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        assert bar.isHidden()

    def test_replace_row_starts_hidden(self, qapp: QApplication, qtbot) -> None:
        """Replace row is hidden by default."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        assert bar._replace_row.isHidden()


class TestSearchReplaceBarToggle:
    """Tests for showing and hiding the search bar."""

    def test_toggle_search_shows_bar(self, qapp: QApplication, qtbot) -> None:
        """Calling toggle_search shows the bar."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        bar.toggle_search()
        assert not bar.isHidden()

    def test_toggle_search_hides_bar(self, qapp: QApplication, qtbot) -> None:
        """Calling toggle_search a second time hides the bar."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        bar.toggle_search()
        bar.toggle_search()
        assert bar.isHidden()

    def test_toggle_replace_shows_replace_row(self, qapp: QApplication, qtbot) -> None:
        """Calling toggle_replace reveals the replace row."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        bar.toggle_replace()
        assert not bar._replace_row.isHidden()

    def test_close_search_resets_state(self, qapp: QApplication, qtbot) -> None:
        """Closing the bar clears inputs and match state."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        bar.toggle_search()
        bar._search_input.setText("test")
        bar.close_search()
        assert bar.isHidden()
        assert bar._search_input.text() == ""
        assert bar._matches == []


class TestSearchReplaceBarSearch:
    """Tests for the search functionality."""

    def test_search_finds_matches(self, qapp: QApplication, qtbot) -> None:
        """Typing in the search input finds matches in the editor."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("hello world hello")
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        bar.toggle_search()
        bar._search_input.setText("hello")
        assert len(bar._matches) == 2
        assert "2" in bar._count_label.text()

    def test_search_no_results(self, qapp: QApplication, qtbot) -> None:
        """Search with no matches shows 'No results'."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("hello world")
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        bar.toggle_search()
        bar._search_input.setText("xyz")
        assert len(bar._matches) == 0
        assert "No results" in bar._count_label.text()

    def test_search_next_wraps(self, qapp: QApplication, qtbot) -> None:
        """Pressing next wraps around to the first match."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("aa bb aa")
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        bar.toggle_search()
        bar._search_input.setText("aa")
        assert bar._match_index == 0
        bar._search_next()
        assert bar._match_index == 1
        bar._search_next()
        assert bar._match_index == 0  # wrapped

    def test_search_prev_wraps(self, qapp: QApplication, qtbot) -> None:
        """Pressing prev wraps around to the last match."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("aa bb aa")
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        bar.toggle_search()
        bar._search_input.setText("aa")
        bar._search_prev()
        assert bar._match_index == 1  # wrapped to last

    def test_search_highlights_selections(self, qapp: QApplication, qtbot) -> None:
        """Search sets search selections on the editor."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("foo bar foo")
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        bar.toggle_search()
        bar._search_input.setText("foo")
        assert len(editor._search_selections) == 2


class TestSearchReplaceBarReplace:
    """Tests for the replace functionality."""

    def test_replace_one(self, qapp: QApplication, qtbot) -> None:
        """Replace-one replaces the current match."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("aa bb aa")
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        bar.toggle_replace()
        bar._search_input.setText("aa")
        bar._replace_input.setText("cc")
        bar._replace_one()
        assert editor.toPlainText() == "cc bb aa"

    def test_replace_all(self, qapp: QApplication, qtbot) -> None:
        """Replace-all replaces every match."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("aa bb aa")
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        bar.toggle_replace()
        bar._search_input.setText("aa")
        bar._replace_input.setText("cc")
        bar._replace_all()
        assert editor.toPlainText() == "cc bb cc"

    def test_replace_with_empty(self, qapp: QApplication, qtbot) -> None:
        """Replacing with empty string removes the match."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("hello world")
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        bar.toggle_replace()
        bar._search_input.setText("hello ")
        bar._replace_input.setText("")
        bar._replace_one()
        assert editor.toPlainText() == "world"


class TestSearchReplaceBarGoToLine:
    """Tests for the go-to-line feature."""

    @patch("ui.widgets.search_replace_bar.QInputDialog.getInt")
    def test_goto_line(self, mock_dialog, qapp: QApplication, qtbot) -> None:
        """Go-to-line navigates to the specified line."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("line1\nline2\nline3\nline4")
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        mock_dialog.return_value = (3, True)
        bar.goto_line()
        assert editor.textCursor().blockNumber() == 2  # 0-based

    @patch("ui.widgets.search_replace_bar.QInputDialog.getInt")
    def test_goto_line_cancelled(self, mock_dialog, qapp: QApplication, qtbot) -> None:
        """Cancelling go-to-line does not move the cursor."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("line1\nline2\nline3")
        bar = SearchReplaceBar(editor)
        qtbot.addWidget(bar)
        mock_dialog.return_value = (2, False)
        bar.goto_line()
        assert editor.textCursor().blockNumber() == 0  # unchanged
