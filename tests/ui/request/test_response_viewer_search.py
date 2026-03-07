"""Tests for the ResponseViewerWidget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.request.response_viewer import ResponseViewerWidget

# -- Sample data used across tests ------------------------------------

_SAMPLE_TIMING: dict = {
    "dns_ms": 1.5,
    "tcp_ms": 3.0,
    "tls_ms": 0.0,
    "ttfb_ms": 50.0,
    "download_ms": 5.0,
    "process_ms": 83.0,
}

_SAMPLE_NETWORK: dict = {
    "http_version": "HTTP/1.1",
    "remote_address": "93.184.216.34:80",
    "local_address": "192.168.1.10:54321",
    "tls_protocol": None,
    "cipher_name": None,
    "certificate_cn": None,
    "issuer_cn": None,
    "valid_until": None,
}


def _make_response(
    *,
    status_code: int = 200,
    status_text: str = "OK",
    headers: list[dict[str, str]] | None = None,
    body: str = '{"result": "success"}',
    elapsed_ms: float = 142.5,
    size_bytes: int | None = None,
) -> dict:
    """Build a minimal response dict with all required fields."""
    if headers is None:
        headers = []
    if size_bytes is None:
        size_bytes = len(body.encode("utf-8"))
    return {
        "status_code": status_code,
        "status_text": status_text,
        "headers": headers,
        "body": body,
        "elapsed_ms": elapsed_ms,
        "size_bytes": size_bytes,
        "timing": _SAMPLE_TIMING,
        "request_headers_size": 0,
        "request_body_size": 0,
        "response_headers_size": 0,
        "network": _SAMPLE_NETWORK,
    }


class TestResponseViewerSearch:
    """Tests for the body search feature."""

    def _make_viewer_with_body(self, qtbot, body: str) -> ResponseViewerWidget:
        """Return a viewer pre-loaded with a response body."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        viewer.load_response(_make_response(body=body, elapsed_ms=1.0, size_bytes=len(body)))
        return viewer

    def test_search_bar_hidden_by_default(self, qapp, qtbot) -> None:
        """The search bar starts hidden."""
        viewer = self._make_viewer_with_body(qtbot, "hello")
        assert viewer._search_bar.isHidden()

    def test_toggle_search_shows_bar(self, qapp, qtbot) -> None:
        """Calling toggle_search shows the search bar."""
        viewer = self._make_viewer_with_body(qtbot, "hello")
        viewer._toggle_search()
        assert not viewer._search_bar.isHidden()

    def test_close_search_hides_bar(self, qapp, qtbot) -> None:
        """Closing the search bar hides it."""
        viewer = self._make_viewer_with_body(qtbot, "hello")
        viewer._toggle_search()
        viewer._close_search()
        assert viewer._search_bar.isHidden()

    def test_search_finds_matches(self, qapp, qtbot) -> None:
        """Searching for a word finds all occurrences."""
        viewer = self._make_viewer_with_body(qtbot, "foo bar foo baz foo")
        viewer._toggle_search()
        viewer._search_input.setText("foo")
        assert len(viewer._search_matches) == 3
        assert viewer._search_count_label.text() == "1 of 3"

    def test_search_no_results(self, qapp, qtbot) -> None:
        """Searching for missing text shows 'No results'."""
        viewer = self._make_viewer_with_body(qtbot, "hello world")
        viewer._toggle_search()
        viewer._search_input.setText("zzz")
        assert len(viewer._search_matches) == 0
        assert viewer._search_count_label.text() == "No results"

    def test_search_next_wraps_around(self, qapp, qtbot) -> None:
        """Pressing next wraps from the last match to the first."""
        viewer = self._make_viewer_with_body(qtbot, "a b a c a")
        viewer._toggle_search()
        viewer._search_input.setText("a")
        assert viewer._search_index == 0
        viewer._search_next()
        assert viewer._search_index == 1
        viewer._search_next()
        assert viewer._search_index == 2
        viewer._search_next()
        assert viewer._search_index == 0  # wrapped

    def test_search_prev_wraps_around(self, qapp, qtbot) -> None:
        """Pressing prev wraps from the first match to the last."""
        viewer = self._make_viewer_with_body(qtbot, "x y x z x")
        viewer._toggle_search()
        viewer._search_input.setText("x")
        assert viewer._search_index == 0
        viewer._search_prev()
        assert viewer._search_index == 2  # wrapped to last


class TestResponseViewerToolbar:
    """Tests for the body toolbar buttons (wrap, filter, search, copy)."""

    def _make_viewer_with_body(self, qtbot, body: str) -> ResponseViewerWidget:
        """Return a viewer pre-loaded with a response body."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        viewer.load_response(_make_response(body=body, elapsed_ms=1.0, size_bytes=len(body)))
        return viewer

    def test_wrap_button_exists(self, qapp: QApplication, qtbot) -> None:
        """Wrap toggle button is present on the viewer."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        assert viewer._wrap_btn is not None
        assert viewer._wrap_btn.isCheckable()
        assert viewer._wrap_btn.isChecked()

    def test_wrap_toggle_disables_word_wrap(self, qapp: QApplication, qtbot) -> None:
        """Un-checking the wrap button disables word wrap on the editor."""
        viewer = self._make_viewer_with_body(qtbot, "hello world")
        viewer._wrap_btn.setChecked(False)
        viewer._on_wrap_toggle()
        assert not viewer._body_edit.is_word_wrap()

    def test_wrap_toggle_enables_word_wrap(self, qapp: QApplication, qtbot) -> None:
        """Re-checking the wrap button re-enables word wrap."""
        viewer = self._make_viewer_with_body(qtbot, "hello world")
        viewer._wrap_btn.setChecked(False)
        viewer._on_wrap_toggle()
        viewer._wrap_btn.setChecked(True)
        viewer._on_wrap_toggle()
        assert viewer._body_edit.is_word_wrap()

    def test_copy_button_copies_body(self, qapp: QApplication, qtbot) -> None:
        """Copy button places the response body on the clipboard."""
        viewer = self._make_viewer_with_body(qtbot, '{"key": "value"}')
        viewer._on_copy_body()
        clipboard = QApplication.clipboard()
        assert clipboard is not None
        assert "key" in clipboard.text()

    def test_copy_empty_body_no_crash(self, qapp: QApplication, qtbot) -> None:
        """Copy on an empty body does not crash."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        viewer._on_copy_body()  # should not raise

    def test_search_button_toggles_bar(self, qapp: QApplication, qtbot) -> None:
        """Clicking the search button shows/hides the search bar."""
        viewer = self._make_viewer_with_body(qtbot, "hello")
        assert viewer._search_bar.isHidden()
        viewer._toggle_search()
        assert not viewer._search_bar.isHidden()
        assert viewer._search_btn.isChecked()
        viewer._toggle_search()
        assert viewer._search_bar.isHidden()
        assert not viewer._search_btn.isChecked()

    def test_search_button_syncs_with_close(self, qapp: QApplication, qtbot) -> None:
        """Closing search via _close_search unchecks the search button."""
        viewer = self._make_viewer_with_body(qtbot, "hello")
        viewer._toggle_search()
        assert viewer._search_btn.isChecked()
        viewer._close_search()
        assert not viewer._search_btn.isChecked()

    def test_search_button_syncs_with_shortcut(self, qapp: QApplication, qtbot) -> None:
        """The Find shortcut updates the search button checked state."""
        viewer = self._make_viewer_with_body(qtbot, "hello")
        # Simulate the shortcut activating (calls _toggle_search)
        viewer._find_shortcut.activated.emit()
        assert not viewer._search_bar.isHidden()
        assert viewer._search_btn.isChecked()
        # Activate again to close
        viewer._find_shortcut.activated.emit()
        assert viewer._search_bar.isHidden()
        assert not viewer._search_btn.isChecked()

    def test_find_shortcut_uses_standard_key(self, qapp: QApplication, qtbot) -> None:
        """Find shortcut uses QKeySequence.StandardKey.Find (OS-agnostic)."""
        from PySide6.QtGui import QKeySequence

        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        expected = QKeySequence(QKeySequence.StandardKey.Find)
        assert viewer._find_shortcut.key() == expected

    def test_filter_button_toggles_bar(self, qapp: QApplication, qtbot) -> None:
        """Clicking the filter button shows/hides the filter bar."""
        viewer = self._make_viewer_with_body(qtbot, '{"a": 1}')
        assert viewer._filter_bar.isHidden()
        viewer._toggle_filter()
        assert not viewer._filter_bar.isHidden()
        assert viewer._filter_btn.isChecked()
        viewer._toggle_filter()
        assert viewer._filter_bar.isHidden()
        assert not viewer._filter_btn.isChecked()

    def test_filter_bar_hidden_by_default(self, qapp: QApplication, qtbot) -> None:
        """Filter bar starts hidden."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        assert viewer._filter_bar.isHidden()

    def test_clear_resets_toolbar_state(self, qapp: QApplication, qtbot) -> None:
        """Clear resets wrap, filter, and related state."""
        viewer = self._make_viewer_with_body(qtbot, '{"x": 1}')
        viewer._wrap_btn.setChecked(False)
        viewer._on_wrap_toggle()
        viewer._toggle_filter()
        viewer.clear()
        assert viewer._wrap_btn.isChecked()
        assert viewer._filter_bar.isHidden()
        assert not viewer._filter_btn.isChecked()
        assert not viewer._is_filtered


class TestResponseViewerFilter:
    """Tests for the JSONPath / XPath filter feature."""

    def _make_viewer_with_body(
        self, qtbot, body: str, *, fmt: str = "Pretty"
    ) -> ResponseViewerWidget:
        """Return a viewer pre-loaded with a response body."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        viewer._format_combo.setCurrentText(fmt)
        viewer.load_response(_make_response(body=body, elapsed_ms=1.0, size_bytes=len(body)))
        return viewer

    def test_filter_jsonpath_basic(self, qapp: QApplication, qtbot) -> None:
        """JSONPath filter extracts a single value from a JSON body."""
        viewer = self._make_viewer_with_body(qtbot, '{"result": "success"}')
        viewer._toggle_filter()
        viewer._filter_input.setText("$.result")
        viewer._apply_filter()
        assert viewer._is_filtered
        assert "success" in viewer._body_edit.toPlainText()

    def test_filter_jsonpath_array(self, qapp: QApplication, qtbot) -> None:
        """JSONPath filter on an array body returns matching elements."""
        body = '{"items": [1, 2, 3]}'
        viewer = self._make_viewer_with_body(qtbot, body)
        viewer._toggle_filter()
        viewer._filter_input.setText("$.items[*]")
        viewer._apply_filter()
        assert viewer._is_filtered
        text = viewer._body_edit.toPlainText()
        assert "1" in text
        assert "3" in text

    def test_filter_jsonpath_no_match(self, qapp: QApplication, qtbot) -> None:
        """JSONPath with no matches shows 'No matches' in the error label."""
        viewer = self._make_viewer_with_body(qtbot, '{"a": 1}')
        viewer._toggle_filter()
        viewer._filter_input.setText("$.nonexistent")
        viewer._apply_filter()
        assert not viewer._is_filtered
        assert not viewer._filter_error_label.isHidden()
        assert "No matches" in viewer._filter_error_label.text()

    def test_filter_jsonpath_invalid_expression(self, qapp: QApplication, qtbot) -> None:
        """Invalid JSONPath expression shows an error, does not crash."""
        viewer = self._make_viewer_with_body(qtbot, '{"a": 1}')
        viewer._toggle_filter()
        viewer._filter_input.setText("$[[[invalid")
        viewer._apply_filter()
        assert not viewer._is_filtered
        assert not viewer._filter_error_label.isHidden()

    def test_filter_jsonpath_on_non_json_shows_error(self, qapp: QApplication, qtbot) -> None:
        """Applying JSONPath filter to plain text shows an error."""
        viewer = self._make_viewer_with_body(qtbot, "just plain text", fmt="Raw")
        viewer._toggle_filter()
        viewer._filter_input.setText("$.something")
        viewer._apply_filter()
        assert not viewer._is_filtered
        assert not viewer._filter_error_label.isHidden()

    def test_filter_xpath_basic(self, qapp: QApplication, qtbot) -> None:
        """XPath filter extracts matching elements from XML body."""
        xml_body = "<root><child>hello</child><child>world</child></root>"
        viewer = self._make_viewer_with_body(qtbot, xml_body, fmt="XML")
        viewer._toggle_filter()
        viewer._filter_input.setText("//child")
        viewer._apply_filter()
        assert viewer._is_filtered
        text = viewer._body_edit.toPlainText()
        assert "hello" in text
        assert "world" in text

    def test_filter_xpath_no_match(self, qapp: QApplication, qtbot) -> None:
        """XPath with no matches shows 'No matches' error."""
        xml_body = "<root><child>v</child></root>"
        viewer = self._make_viewer_with_body(qtbot, xml_body, fmt="XML")
        viewer._toggle_filter()
        viewer._filter_input.setText("//nonexistent")
        viewer._apply_filter()
        assert not viewer._is_filtered
        assert "No matches" in viewer._filter_error_label.text()

    def test_filter_xpath_invalid(self, qapp: QApplication, qtbot) -> None:
        """Invalid XPath expression shows an error, does not crash."""
        xml_body = "<root><child>v</child></root>"
        viewer = self._make_viewer_with_body(qtbot, xml_body, fmt="XML")
        viewer._toggle_filter()
        viewer._filter_input.setText("[[[bad xpath")
        viewer._apply_filter()
        assert not viewer._is_filtered
        assert not viewer._filter_error_label.isHidden()

    def test_filter_clear_restores_body(self, qapp: QApplication, qtbot) -> None:
        """Clearing a filter restores the original response body."""
        body = '{"a": 1, "b": 2}'
        viewer = self._make_viewer_with_body(qtbot, body)
        viewer._toggle_filter()
        viewer._filter_input.setText("$.a")
        viewer._apply_filter()
        assert viewer._is_filtered
        viewer._clear_filter()
        assert not viewer._is_filtered
        # Body should contain both keys again (pretty-printed)
        text = viewer._body_edit.toPlainText()
        assert '"a"' in text
        assert '"b"' in text

    def test_filter_persists_across_format_change(self, qapp: QApplication, qtbot) -> None:
        """Switching format while filtered re-applies the filter."""
        body = '{"a": 1, "b": 2}'
        viewer = self._make_viewer_with_body(qtbot, body)
        viewer._toggle_filter()
        viewer._filter_input.setText("$.a")
        viewer._apply_filter()
        assert viewer._is_filtered
        # Switch to Raw — filter should still be applied
        viewer._format_combo.setCurrentText("Raw")
        assert viewer._is_filtered
        # The body should still show the filtered value
        assert "1" in viewer._body_edit.toPlainText()

    def test_filter_apply_btn_hidden_after_filter(self, qapp: QApplication, qtbot) -> None:
        """Apply button hides and Clear button appears after filtering."""
        viewer = self._make_viewer_with_body(qtbot, '{"x": 42}')
        viewer._toggle_filter()
        viewer._filter_input.setText("$.x")
        viewer._apply_filter()
        assert viewer._filter_apply_btn.isHidden()
        assert not viewer._filter_clear_btn.isHidden()

    def test_filter_clear_shows_apply_btn(self, qapp: QApplication, qtbot) -> None:
        """Clearing a filter restores the Apply button."""
        viewer = self._make_viewer_with_body(qtbot, '{"x": 42}')
        viewer._toggle_filter()
        viewer._filter_input.setText("$.x")
        viewer._apply_filter()
        viewer._clear_filter()
        assert not viewer._filter_apply_btn.isHidden()
        assert viewer._filter_clear_btn.isHidden()

    def test_filter_empty_expression_noop(self, qapp: QApplication, qtbot) -> None:
        """Pressing Apply with an empty filter expression does nothing."""
        viewer = self._make_viewer_with_body(qtbot, '{"a": 1}')
        viewer._toggle_filter()
        viewer._filter_input.setText("")
        viewer._apply_filter()
        assert not viewer._is_filtered

    def test_filter_placeholder_json(self, qapp: QApplication, qtbot) -> None:
        """Filter placeholder mentions JSONPath for JSON content."""
        viewer = self._make_viewer_with_body(qtbot, '{"a": 1}')
        viewer._toggle_filter()
        assert "JSONPath" in viewer._filter_input.placeholderText()

    def test_filter_placeholder_xml(self, qapp: QApplication, qtbot) -> None:
        """Filter placeholder mentions XPath for XML content."""
        xml_body = "<root><child>v</child></root>"
        viewer = self._make_viewer_with_body(qtbot, xml_body, fmt="XML")
        viewer._toggle_filter()
        assert "XPath" in viewer._filter_input.placeholderText()
