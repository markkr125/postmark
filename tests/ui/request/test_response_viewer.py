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


class TestResponseViewerWidget:
    """Tests for the response viewer pane."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Widget can be instantiated without errors."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        assert viewer is not None

    def test_starts_in_empty_state(self, qapp: QApplication, qtbot) -> None:
        """Viewer starts with the empty-state label visible."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        assert not viewer._empty_label.isHidden()
        assert viewer._tabs.isHidden()
        assert viewer._status_bar_widget.isHidden()
        assert viewer._error_label.isHidden()

    def test_show_loading(self, qapp: QApplication, qtbot) -> None:
        """Loading state shows progress bar and hides other elements."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)

        viewer.show_loading()

        assert not viewer._progress_bar.isHidden()
        assert viewer._tabs.isHidden()
        assert viewer._empty_label.isHidden()
        assert viewer._error_label.isHidden()

    def test_show_error(self, qapp: QApplication, qtbot) -> None:
        """Error state shows error label with message."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)

        viewer.show_error("Connection refused")

        assert not viewer._error_label.isHidden()
        assert "Connection refused" in viewer._error_label.text()
        assert viewer._tabs.isHidden()
        assert viewer._empty_label.isHidden()

    def test_load_response_success(self, qapp: QApplication, qtbot) -> None:
        """Loading a successful response shows status, body, and headers."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)

        data = _make_response(
            headers=[
                {"key": "Content-Type", "value": "application/json"},
                {"key": "X-Custom", "value": "test"},
            ],
            body='{"result": "success"}',
            elapsed_ms=142.5,
            size_bytes=21,
        )
        viewer.load_response(data)

        assert not viewer._tabs.isHidden()
        assert not viewer._status_bar_widget.isHidden()
        assert viewer._empty_label.isHidden()
        assert viewer._error_label.isHidden()
        assert "200" in viewer._status_label.text()
        assert "OK" in viewer._status_label.text()
        assert "142" in viewer._time_label.text()
        # Body is pretty-printed by default
        assert '"result": "success"' in viewer._body_edit.toPlainText()
        assert "Content-Type: application/json" in viewer._headers_edit.toPlainText()

    def test_load_response_with_error_key(self, qapp: QApplication, qtbot) -> None:
        """Response dict with error key shows error state."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)

        data = {"error": "Connection refused: localhost:9999", "elapsed_ms": 15.0}
        viewer.load_response(data)

        assert not viewer._error_label.isHidden()
        assert "Connection refused" in viewer._error_label.text()
        assert viewer._tabs.isHidden()

    def test_load_response_404(self, qapp: QApplication, qtbot) -> None:
        """A 404 response is shown normally (not as an error)."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)

        data = _make_response(
            status_code=404,
            status_text="Not Found",
            body="Not Found",
            elapsed_ms=50.0,
            size_bytes=9,
        )
        viewer.load_response(data)

        assert "404" in viewer._status_label.text()
        assert not viewer._tabs.isHidden()

    def test_clear_resets_to_empty(self, qapp: QApplication, qtbot) -> None:
        """Clear resets the viewer to the empty state."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)

        viewer.load_response(_make_response(body="hello", elapsed_ms=10.0, size_bytes=5))
        viewer.clear()

        assert not viewer._empty_label.isHidden()
        assert viewer._tabs.isHidden()
        assert viewer._body_edit.toPlainText() == ""

    def test_size_formatting_bytes(self, qapp: QApplication, qtbot) -> None:
        """Small response shows size in bytes."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)

        viewer.load_response(_make_response(body="hi", elapsed_ms=5.0, size_bytes=100))

        assert "100 B" in viewer._size_label.text()

    def test_size_formatting_kilobytes(self, qapp: QApplication, qtbot) -> None:
        """Larger response shows size in KB."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)

        viewer.load_response(_make_response(body="x" * 2048, elapsed_ms=5.0, size_bytes=2048))

        assert "KB" in viewer._size_label.text()

    def test_cookies_tab_exists(self, qapp: QApplication, qtbot) -> None:
        """Response viewer has a Cookies tab."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)

        tab_titles = [viewer._tabs.tabText(i) for i in range(viewer._tabs.count())]
        assert "Cookies" in tab_titles

    def test_cookies_extracted_from_headers(self, qapp: QApplication, qtbot) -> None:
        """Set-Cookie headers are shown in the Cookies tab."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)

        data = _make_response(
            headers=[
                {"key": "Content-Type", "value": "text/html"},
                {"key": "set-cookie", "value": "sid=abc123; Path=/"},
            ],
            body="",
            elapsed_ms=5.0,
            size_bytes=0,
        )
        viewer.load_response(data)

        assert "sid=abc123" in viewer._cookies_edit.toPlainText()

    def test_format_selector_has_options(self, qapp: QApplication, qtbot) -> None:
        """Format selector contains Pretty, Raw, JSON, XML, HTML."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)

        options = [viewer._format_combo.itemText(i) for i in range(viewer._format_combo.count())]
        assert "Pretty" in options
        assert "Raw" in options
        assert "JSON" in options

    def test_format_pretty_json(self, qapp: QApplication, qtbot) -> None:
        """Pretty format auto-formats valid JSON body."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)

        viewer._format_combo.setCurrentText("Pretty")
        viewer.load_response(_make_response(body='{"a":1,"b":2}', elapsed_ms=5.0, size_bytes=13))

        body = viewer._body_edit.toPlainText()
        # Pretty-printed JSON has newlines
        assert "\n" in body
        assert '"a": 1' in body

    def test_format_raw_shows_unformatted(self, qapp: QApplication, qtbot) -> None:
        """Raw format shows the body as-is."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)

        raw_json = '{"a":1,"b":2}'
        viewer._format_combo.setCurrentText("Raw")
        viewer.load_response(_make_response(body=raw_json, elapsed_ms=5.0, size_bytes=13))

        assert viewer._body_edit.toPlainText() == raw_json


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


class TestResponseViewerBeautify:
    """Tests for the Beautify button."""

    def _make_viewer_with_body(self, qtbot, body: str) -> ResponseViewerWidget:
        """Return a viewer pre-loaded with a Raw-formatted response body."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        viewer._format_combo.setCurrentText("Raw")
        viewer.load_response(_make_response(body=body, elapsed_ms=1.0, size_bytes=len(body)))
        return viewer

    def test_beautify_json(self, qapp: QApplication, qtbot) -> None:
        """Beautify formats compact JSON into indented output."""
        viewer = self._make_viewer_with_body(qtbot, '{"a":1,"b":2}')
        viewer._on_beautify()
        body = viewer._body_edit.toPlainText()
        assert "\n" in body
        assert '"a": 1' in body

    def test_beautify_xml(self, qapp: QApplication, qtbot) -> None:
        """Beautify formats a single-line XML string into indented output."""
        xml_input = "<root><child>val</child></root>"
        viewer = self._make_viewer_with_body(qtbot, xml_input)
        viewer._on_beautify()
        body = viewer._body_edit.toPlainText()
        assert "<root>" in body
        assert "  " in body  # indented

    def test_beautify_plain_text_unchanged(self, qapp: QApplication, qtbot) -> None:
        """Beautify on non-JSON/XML text leaves the body unchanged."""
        plain = "just some text"
        viewer = self._make_viewer_with_body(qtbot, plain)
        viewer._on_beautify()
        assert viewer._body_edit.toPlainText() == plain

    def test_beautify_empty_body_noop(self, qapp: QApplication, qtbot) -> None:
        """Beautify with no body does nothing."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        viewer._on_beautify()
        assert viewer._body_edit.toPlainText() == ""


class TestResponseViewerSaveResponse:
    """Tests for the Save response button and saved responses tab."""

    def test_save_emits_signal(self, qapp: QApplication, qtbot) -> None:
        """Clicking Save emits save_response_requested with current data."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        viewer.load_response(
            _make_response(
                headers=[{"key": "X-Test", "value": "1"}],
                body='{"ok": true}',
                elapsed_ms=5.0,
                size_bytes=12,
            )
        )

        with qtbot.waitSignal(viewer.save_response_requested, timeout=1000) as blocker:
            viewer._on_save_response()

        data = blocker.args[0]
        assert "200" in data["status"]
        assert '{"ok": true}' in data["body"]

    def test_save_no_response_noop(self, qapp: QApplication, qtbot) -> None:
        """Save does nothing when no response is loaded."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        # No signal should be emitted
        emitted = []
        viewer.save_response_requested.connect(lambda d: emitted.append(d))
        viewer._on_save_response()
        assert emitted == []

    def test_load_saved_responses(self, qapp: QApplication, qtbot) -> None:
        """Saved responses populate the Saved tab."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        responses = [
            {"name": "Success", "code": 200, "status": "OK", "body": '{"result": 1}'},
            {"name": "Error", "code": 500, "status": "Server Error", "body": "fail"},
        ]
        viewer.load_saved_responses(responses)
        text = viewer._saved_list.toPlainText()
        assert "Success" in text
        assert "Error" in text
        assert "200" in text
        assert "500" in text

    def test_load_saved_responses_empty(self, qapp: QApplication, qtbot) -> None:
        """Empty list shows placeholder text in Saved tab."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        viewer.load_saved_responses([])
        assert "No saved responses" in viewer._saved_list.toPlainText()

    def test_saved_tab_exists(self, qapp: QApplication, qtbot) -> None:
        """Response viewer has a Saved tab."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        tab_titles = [viewer._tabs.tabText(i) for i in range(viewer._tabs.count())]
        assert "Saved" in tab_titles


class TestResponseViewerPopups:
    """Tests for the click-triggered popup panels."""

    def _loaded_viewer(self, qtbot) -> ResponseViewerWidget:
        """Return a viewer pre-loaded with a full response."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        viewer.load_response(_make_response())
        return viewer

    def test_status_popup_created_on_click(self, qapp: QApplication, qtbot) -> None:
        """Clicking the status label creates and shows the status popup."""
        viewer = self._loaded_viewer(qtbot)
        assert viewer._status_popup is None
        viewer._on_status_clicked()
        assert viewer._status_popup is not None

    def test_timing_popup_created_on_click(self, qapp: QApplication, qtbot) -> None:
        """Clicking the time label creates and shows the timing popup."""
        viewer = self._loaded_viewer(qtbot)
        assert viewer._timing_popup is None
        viewer._on_time_clicked()
        assert viewer._timing_popup is not None

    def test_size_popup_created_on_click(self, qapp: QApplication, qtbot) -> None:
        """Clicking the size label creates and shows the size popup."""
        viewer = self._loaded_viewer(qtbot)
        assert viewer._size_popup is None
        viewer._on_size_clicked()
        assert viewer._size_popup is not None

    def test_network_popup_created_on_click(self, qapp: QApplication, qtbot) -> None:
        """Clicking the network icon creates and shows the network popup."""
        viewer = self._loaded_viewer(qtbot)
        assert viewer._network_popup is None
        viewer._on_network_clicked()
        assert viewer._network_popup is not None

    def test_load_response_stores_timing_data(self, qapp: QApplication, qtbot) -> None:
        """load_response stores timing dict for popup use."""
        viewer = self._loaded_viewer(qtbot)
        assert viewer._timing_data is not None
        assert viewer._timing_data["dns_ms"] == _SAMPLE_TIMING["dns_ms"]

    def test_load_response_stores_network_data(self, qapp: QApplication, qtbot) -> None:
        """load_response stores network dict for popup use."""
        viewer = self._loaded_viewer(qtbot)
        assert viewer._network_data is not None
        assert viewer._network_data["http_version"] == "HTTP/1.1"

    def test_load_response_stores_size_breakdown(self, qapp: QApplication, qtbot) -> None:
        """load_response stores size breakdown dict for popup use."""
        viewer = self._loaded_viewer(qtbot)
        assert "response_headers_size" in viewer._size_data
        assert "request_body_size" in viewer._size_data

    def test_save_button_in_corner_widget(self, qapp: QApplication, qtbot) -> None:
        """Save button is part of the tab corner widget row."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        # The save button's parent chain goes through the status_bar_widget
        assert viewer._save_response_btn.parent() is viewer._status_bar_widget

    def test_network_icon_exists(self, qapp: QApplication, qtbot) -> None:
        """Response viewer has a network globe icon in the status bar."""
        viewer = ResponseViewerWidget()
        qtbot.addWidget(viewer)
        assert viewer._network_icon is not None
        assert viewer._network_icon.parent() is viewer._status_bar_widget


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
