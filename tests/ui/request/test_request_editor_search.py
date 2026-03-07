"""Tests for RequestEditorWidget — body search and replace."""

from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from ui.request.request_editor import RequestEditorWidget


class TestRequestEditorBodySearch:
    """Tests for the body search bar (Ctrl+F / Cmd+F)."""

    def _make_editor_with_raw_body(
        self, qtbot, body: str, *, fmt: str = "JSON"
    ) -> RequestEditorWidget:
        """Return an editor pre-loaded with a raw body."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "Test",
                "method": "POST",
                "url": "http://example.com",
                "body_mode": "raw",
                "body": body,
            }
        )
        return editor

    def test_search_bar_hidden_by_default(self, qapp: QApplication, qtbot) -> None:
        """Body search bar starts hidden."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        assert editor._body_search_bar.isHidden()

    def test_toggle_shows_and_hides_bar(self, qapp: QApplication, qtbot) -> None:
        """Toggling the body search opens and closes the bar."""
        editor = self._make_editor_with_raw_body(qtbot, '{"a": 1}')
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        assert not editor._body_search_bar.isHidden()
        editor._toggle_body_search()
        assert editor._body_search_bar.isHidden()

    def test_search_finds_matches(self, qapp: QApplication, qtbot) -> None:
        """Typing in the search input highlights matches."""
        editor = self._make_editor_with_raw_body(qtbot, '{"hello": "world", "hello2": 1}')
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("hello")
        assert len(editor._body_search_matches) == 2
        assert "1 of 2" in editor._body_search_count_label.text()

    def test_search_no_results(self, qapp: QApplication, qtbot) -> None:
        """Searching for nonexistent text shows 'No results'."""
        editor = self._make_editor_with_raw_body(qtbot, '{"a": 1}')
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("zzz_not_found")
        assert len(editor._body_search_matches) == 0
        assert "No results" in editor._body_search_count_label.text()

    def test_search_next_wraps_around(self, qapp: QApplication, qtbot) -> None:
        """Next match wraps from the last back to the first."""
        editor = self._make_editor_with_raw_body(qtbot, "aaa")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("a")
        assert len(editor._body_search_matches) == 3
        assert editor._body_search_index == 0
        editor._body_search_next()
        assert editor._body_search_index == 1
        editor._body_search_next()
        assert editor._body_search_index == 2
        editor._body_search_next()
        assert editor._body_search_index == 0

    def test_search_prev_wraps_around(self, qapp: QApplication, qtbot) -> None:
        """Previous match wraps from the first back to the last."""
        editor = self._make_editor_with_raw_body(qtbot, "aaa")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("a")
        assert editor._body_search_index == 0
        editor._body_search_prev()
        assert editor._body_search_index == 2

    def test_close_clears_highlights(self, qapp: QApplication, qtbot) -> None:
        """Closing the search bar clears highlights and resets state."""
        editor = self._make_editor_with_raw_body(qtbot, '{"a": 1}')
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("a")
        assert len(editor._body_search_matches) > 0
        editor._close_body_search()
        assert editor._body_search_bar.isHidden()
        assert editor._body_search_matches == []
        assert editor._body_search_index == -1

    def test_clear_request_closes_search(self, qapp: QApplication, qtbot) -> None:
        """Clearing the request closes the body search bar."""
        editor = self._make_editor_with_raw_body(qtbot, '{"a": 1}')
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        assert not editor._body_search_bar.isHidden()
        editor.clear_request()
        assert editor._body_search_bar.isHidden()

    def test_find_shortcut_uses_standard_key(self, qapp: QApplication, qtbot) -> None:
        """The find shortcut uses the platform-native Find key sequence."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        expected = QKeySequence(QKeySequence.StandardKey.Find)
        assert editor._body_find_shortcut.key() == expected

    def test_toggle_does_nothing_on_none_mode(self, qapp: QApplication, qtbot) -> None:
        """Toggling body search when body mode is 'none' does nothing."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request({"name": "T", "method": "GET", "url": "http://x", "body": ""})
        editor._toggle_body_search()
        assert editor._body_search_bar.isHidden()


class TestRequestEditorReplace:
    """Tests for the find-and-replace feature in the request body."""

    def _make_editor_with_raw_body(
        self, qtbot, body: str, *, fmt: str = "JSON"
    ) -> RequestEditorWidget:
        """Return an editor pre-loaded with a raw body."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "Test",
                "method": "POST",
                "url": "http://example.com",
                "body_mode": "raw",
                "body": body,
            }
        )
        return editor

    def test_replace_row_hidden_by_default(self, qapp: QApplication, qtbot) -> None:
        """Replace row starts hidden even when search bar is open."""
        editor = self._make_editor_with_raw_body(qtbot, "abc")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        assert not editor._body_search_bar.isHidden()
        assert editor._replace_row.isHidden()

    def test_toggle_replace_shows_row(self, qapp: QApplication, qtbot) -> None:
        """Clicking the chevron toggles the replace row visibility."""
        editor = self._make_editor_with_raw_body(qtbot, "abc")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._toggle_replace_row()
        assert not editor._replace_row.isHidden()
        assert editor._replace_toggle_btn.isChecked()
        editor._toggle_replace_row()
        assert editor._replace_row.isHidden()
        assert not editor._replace_toggle_btn.isChecked()

    def test_ctrl_r_opens_replace(self, qapp: QApplication, qtbot) -> None:
        """The replace shortcut is Ctrl+R."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        expected = QKeySequence("Ctrl+R")
        assert editor._body_replace_shortcut.key() == expected

    def test_toggle_body_replace_shows_both_rows(self, qapp: QApplication, qtbot) -> None:
        """_toggle_body_replace opens the search bar with the replace row."""
        editor = self._make_editor_with_raw_body(qtbot, "abc")
        editor._body_code_editor.setFocus()
        editor._toggle_body_replace()
        assert not editor._body_search_bar.isHidden()
        assert not editor._replace_row.isHidden()

    def test_replace_one_replaces_current_match(self, qapp: QApplication, qtbot) -> None:
        """Replace-one replaces the current match and re-searches."""
        editor = self._make_editor_with_raw_body(qtbot, "aXbXc", fmt="Text")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("X")
        assert len(editor._body_search_matches) == 2
        editor._replace_input.setText("Y")
        editor._replace_one()
        text = editor._body_code_editor.toPlainText()
        assert text == "aYbXc"
        # One match left after first replacement
        assert len(editor._body_search_matches) == 1

    def test_replace_all_replaces_every_match(self, qapp: QApplication, qtbot) -> None:
        """Replace-all replaces every occurrence at once."""
        editor = self._make_editor_with_raw_body(qtbot, "aXbXcX", fmt="Text")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("X")
        assert len(editor._body_search_matches) == 3
        editor._replace_input.setText("Z")
        editor._replace_all()
        text = editor._body_code_editor.toPlainText()
        assert text == "aZbZcZ"
        assert len(editor._body_search_matches) == 0

    def test_replace_all_with_empty_string(self, qapp: QApplication, qtbot) -> None:
        """Replace-all with empty replacement removes all matches."""
        editor = self._make_editor_with_raw_body(qtbot, "aXbXc", fmt="Text")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("X")
        editor._replace_input.setText("")
        editor._replace_all()
        assert editor._body_code_editor.toPlainText() == "abc"

    def test_replace_one_no_matches_is_noop(self, qapp: QApplication, qtbot) -> None:
        """Replace-one with no matches does nothing."""
        editor = self._make_editor_with_raw_body(qtbot, "abc", fmt="Text")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("ZZZ")
        assert len(editor._body_search_matches) == 0
        editor._replace_input.setText("Y")
        editor._replace_one()
        assert editor._body_code_editor.toPlainText() == "abc"

    def test_close_resets_replace_row(self, qapp: QApplication, qtbot) -> None:
        """Closing the search bar hides and clears the replace row."""
        editor = self._make_editor_with_raw_body(qtbot, "abc", fmt="Text")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._toggle_replace_row()
        editor._replace_input.setText("xyz")
        assert not editor._replace_row.isHidden()
        editor._close_body_search()
        assert editor._replace_row.isHidden()
        assert editor._replace_input.text() == ""
        assert not editor._replace_toggle_btn.isChecked()
