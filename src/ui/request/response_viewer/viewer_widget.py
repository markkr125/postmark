"""Response viewer widget showing HTTP response status, body, and headers.

Displays the result of an HTTP request sent from the request editor.
Supports three visual states: empty (no request sent), loading
(request in progress), and populated (response received or error).

Status, timing, and size labels are clickable and open floating
popup panels with breakdown details (matching Postman's UX).
"""

from __future__ import annotations

import contextlib

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QSizePolicy,
                               QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from ui.request.popups.network_popup import NetworkPopup
from ui.request.popups.size_popup import SizePopup
from ui.request.popups.status_popup import StatusPopup
from ui.request.popups.timing_popup import TimingPopup
from ui.request.response_viewer.search_filter import _SearchFilterMixin
from ui.styling.icons import phi
from ui.styling.theme import (COLOR_DANGER, COLOR_DELETE, COLOR_IMPORT_ERROR,
                              COLOR_SUCCESS, COLOR_WARNING, COLOR_WHITE)
from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.info_popup import ClickableLabel, InfoPopup

# -- Status code colour thresholds ------------------------------------
_STATUS_2XX = COLOR_SUCCESS  # green
_STATUS_3XX = COLOR_WARNING  # amber
_STATUS_4XX = COLOR_DELETE  # orange
_STATUS_5XX = COLOR_DANGER  # red

# Progress bar height (matches import dialog convention)
_PROGRESS_HEIGHT = 4


def _status_color(code: int) -> str:
    """Return the theme colour for an HTTP status code."""
    if code < 300:
        return _STATUS_2XX
    if code < 400:
        return _STATUS_3XX
    if code < 500:
        return _STATUS_4XX
    return _STATUS_5XX


def _format_size(size_bytes: int) -> str:
    """Format byte count into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


class ResponseViewerWidget(_SearchFilterMixin, QWidget):
    """Display HTTP response data with status bar and tabbed body/headers.

    Call :meth:`load_response` to populate from an ``HttpResponseDict``,
    :meth:`show_loading` to display a progress indicator, or
    :meth:`show_error` for error states.
    """

    save_response_requested = Signal(dict)
    save_availability_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the response viewer layout."""
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(6)

        # -- Response label -------------------------------------------
        self._response_label = QLabel("Response")
        self._response_label.setObjectName("panelTitle")
        root.addWidget(self._response_label)

        # -- Status bar row (shown as tab corner widget) -----------------
        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        status_row.setContentsMargins(0, 0, 0, 0)

        self._status_label = ClickableLabel()
        self._status_label.setStyleSheet("font-weight: bold; padding: 2px 8px; border-radius: 3px;")
        self._status_label.clicked.connect(self._on_status_clicked)
        status_row.addWidget(self._status_label)

        self._time_label = ClickableLabel()
        self._time_label.setObjectName("mutedLabel")
        self._time_label.clicked.connect(self._on_time_clicked)
        status_row.addWidget(self._time_label)

        self._size_label = ClickableLabel()
        self._size_label.setObjectName("mutedLabel")
        self._size_label.clicked.connect(self._on_size_clicked)
        status_row.addWidget(self._size_label)

        self._network_icon = ClickableLabel()
        self._network_icon.setPixmap(phi("globe-simple").pixmap(16, 16))
        self._network_icon.setToolTip("Network information")
        self._network_icon.clicked.connect(self._on_network_clicked)
        status_row.addWidget(self._network_icon)

        self._save_response_btn = QPushButton(" Save Response")
        self._save_response_btn.setIcon(phi("floppy-disk"))
        self._save_response_btn.setToolTip("Save this response as a named example")
        self._save_response_btn.setObjectName("flatMutedButton")
        self._save_response_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_response_btn.clicked.connect(self._on_save_response)
        self._save_response_btn.setEnabled(False)
        status_row.addWidget(self._save_response_btn)

        self._status_bar_widget = QWidget()
        self._status_bar_widget.setLayout(status_row)

        # -- Popup instances (created lazily on first click) -----------
        self._status_popup: StatusPopup | None = None
        self._timing_popup: TimingPopup | None = None
        self._size_popup: SizePopup | None = None
        self._network_popup: NetworkPopup | None = None

        # Breakdown data stored from load_response for popup use
        self._timing_data: dict | None = None
        self._size_data: dict = {}
        self._network_data: dict | None = None
        self._last_status_code: int = 0
        self._last_status_text: str = ""
        self._last_status_color: str = ""
        self._last_elapsed_ms: float = 0.0
        self._last_live_response: dict | None = None

        # -- Progress bar (loading state) -----------------------------
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate
        self._progress_bar.setFixedHeight(_PROGRESS_HEIGHT)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        root.addWidget(self._progress_bar)

        # -- Tabbed area: Body, Headers -------------------------------
        self._tabs = QTabWidget()
        self._tabs.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)
        self._tabs.setCornerWidget(self._status_bar_widget, Qt.Corner.TopRightCorner)

        # Body tab with format selector
        body_tab = QWidget()
        body_layout = QVBoxLayout(body_tab)
        body_layout.setContentsMargins(0, 6, 0, 0)

        self._format_combo = QComboBox()
        self._format_combo.addItems(["Pretty", "Raw", "JSON", "XML", "HTML"])
        self._format_combo.setFixedWidth(90)
        self._format_combo.currentTextChanged.connect(self._on_format_changed)

        format_row = QHBoxLayout()
        format_row.addWidget(self._format_combo)

        self._beautify_btn = QPushButton("Beautify")
        self._beautify_btn.setIcon(phi("magic-wand", color=COLOR_WHITE))
        self._beautify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._beautify_btn.setToolTip("Format and beautify the response body")
        self._beautify_btn.setObjectName("smallPrimaryButton")
        self._beautify_btn.clicked.connect(self._on_beautify)
        format_row.addWidget(self._beautify_btn)

        format_row.addStretch()

        # -- Toolbar buttons (right side of format row) ----------------
        self._wrap_btn = QPushButton()
        self._wrap_btn.setIcon(phi("text-align-left"))
        self._wrap_btn.setToolTip("Toggle word wrap")
        self._wrap_btn.setObjectName("iconButton")
        self._wrap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wrap_btn.setCheckable(True)
        self._wrap_btn.setChecked(True)
        self._wrap_btn.setFixedSize(28, 28)
        self._wrap_btn.clicked.connect(self._on_wrap_toggle)
        format_row.addWidget(self._wrap_btn)

        self._filter_btn = QPushButton()
        self._filter_btn.setIcon(phi("funnel"))
        self._filter_btn.setToolTip("Filter response (JSONPath / XPath)")
        self._filter_btn.setObjectName("iconButton")
        self._filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_btn.setCheckable(True)
        self._filter_btn.setFixedSize(28, 28)
        self._filter_btn.clicked.connect(self._toggle_filter)
        format_row.addWidget(self._filter_btn)

        self._search_btn = QPushButton()
        self._search_btn.setIcon(phi("magnifying-glass"))
        find_hint = QKeySequence(QKeySequence.StandardKey.Find).toString(
            QKeySequence.SequenceFormat.NativeText,
        )
        self._search_btn.setToolTip(f"Search in response ({find_hint})")
        self._search_btn.setObjectName("iconButton")
        self._search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._search_btn.setCheckable(True)
        self._search_btn.setFixedSize(28, 28)
        self._search_btn.clicked.connect(self._toggle_search)
        format_row.addWidget(self._search_btn)

        self._copy_btn = QPushButton()
        self._copy_btn.setIcon(phi("clipboard"))
        self._copy_btn.setToolTip("Copy response body")
        self._copy_btn.setObjectName("iconButton")
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.setFixedSize(28, 28)
        self._copy_btn.clicked.connect(self._on_copy_body)
        format_row.addWidget(self._copy_btn)

        body_layout.addLayout(format_row)

        # Delegate filter / search bar construction to the mixin
        self._build_filter_bar(body_layout)
        self._build_search_bar(body_layout)

        self._body_edit = CodeEditorWidget(read_only=True)
        self._body_edit.setPlaceholderText("Response body")
        body_layout.addWidget(self._body_edit, 1)

        self._tabs.addTab(body_tab, "Body")

        # Headers tab
        self._headers_edit = QTextEdit()
        self._headers_edit.setReadOnly(True)
        self._headers_edit.setPlaceholderText("Response headers")
        self._headers_edit.setObjectName("monoEdit")
        self._tabs.addTab(self._headers_edit, "Headers")

        # Cookies tab (placeholder)
        self._cookies_edit = QTextEdit()
        self._cookies_edit.setReadOnly(True)
        self._cookies_edit.setPlaceholderText("Response cookies")
        self._cookies_edit.setObjectName("monoEdit")
        self._tabs.addTab(self._cookies_edit, "Cookies")

        root.addWidget(self._tabs, 1)

        # -- Empty state label ----------------------------------------
        self._empty_label = QLabel("Send a request to see the response.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("emptyStateLabel")
        self._empty_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._empty_label)

        # -- Error state label ----------------------------------------
        self._error_label = QLabel()
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet(
            f"color: {COLOR_IMPORT_ERROR}; font-size: 13px; padding: 20px;"
        )
        self._error_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._error_label.hide()
        root.addWidget(self._error_label)

        # Start in empty state
        self._raw_body: str = ""  # stored raw body for format switching
        self._filtered_body: str = ""  # body after filter applied
        self._set_state("empty")

    # -- State management ---------------------------------------------

    def _set_state(self, state: str) -> None:
        """Switch between ``empty``, ``loading``, ``error``, and ``response`` states."""
        self._response_label.setVisible(state in ("response", "loading"))
        self._status_bar_widget.setVisible(state == "response")
        self._progress_bar.setVisible(state == "loading")
        self._tabs.setVisible(state == "response")
        self._empty_label.setVisible(state == "empty")
        self._error_label.setVisible(state == "error")

    # -- Public API ---------------------------------------------------

    def show_loading(self) -> None:
        """Display the indeterminate progress bar (request in flight)."""
        self._set_state("loading")

    def show_error(self, message: str) -> None:
        """Display an error message (e.g. connection refused)."""
        self._error_label.setText(f"Could not send request\n\n{message}")
        self._set_save_enabled(False)
        self._set_state("error")

    def load_response(self, data: dict) -> None:
        """Populate the viewer from an ``HttpResponseDict``.

        If the dict contains an ``error`` key, the error state is shown
        instead of the response tabs.  New breakdown fields (``timing``,
        ``network``, size keys) are stored for popup display.
        """
        if "error" in data:
            elapsed = data.get("elapsed_ms")
            suffix = f"\n\nElapsed: {elapsed:.0f} ms" if elapsed else ""
            self.show_error(f"{data['error']}{suffix}")
            return

        self._last_live_response = dict(data)
        self._set_save_enabled(True)

        self._render_response_data(data)

    def has_live_response(self) -> bool:
        """Return whether a live response is currently available for saving."""
        return self._last_live_response is not None

    def get_save_response_data(self) -> dict | None:
        """Return the current live response payload suitable for saving."""
        if not self.has_live_response() or self._last_live_response is None:
            return None
        preview_language = self._detect_preview_language(self._last_live_response)
        return {
            "status": self._last_live_response.get("status_text"),
            "code": self._last_live_response.get("status_code"),
            "body": self._last_live_response.get("body"),
            "headers": self._last_live_response.get("headers"),
            "preview_language": preview_language,
        }

    def _render_response_data(self, data: dict) -> None:
        """Render response data into the viewer widgets."""
        self._set_state("response")

        # Status code
        code = data.get("status_code", 0)
        text = data.get("status_text", "")
        color = _status_color(code)
        self._status_label.setText(f"{code} {text}")
        self._status_label.setStyleSheet(
            f"font-weight: bold; padding: 2px 8px; border-radius: 3px;"
            f" color: {COLOR_WHITE}; background: {color};"
        )

        # Store for popup use
        self._last_status_code = code
        self._last_status_text = text
        self._last_status_color = color

        # Timing
        elapsed = data.get("elapsed_ms", 0)
        self._time_label.setText(f"{elapsed:.0f} ms")
        self._last_elapsed_ms = elapsed
        self._timing_data = data.get("timing")

        # Size
        size = data.get("size_bytes", 0)
        self._size_label.setText(_format_size(size))
        self._size_data = {
            "response_headers_size": data.get("response_headers_size", 0),
            "size_bytes": size,
            "response_uncompressed_size": data.get("response_uncompressed_size"),
            "request_headers_size": data.get("request_headers_size", 0),
            "request_body_size": data.get("request_body_size", 0),
        }

        # Network
        self._network_data = data.get("network")

        # Body — store raw and apply current format
        self._raw_body = data.get("body", "")
        self._apply_body_format()

        # Headers
        headers = data.get("headers", [])
        header_lines = [f"{h.get('key', '')}: {h.get('value', '')}" for h in headers]
        self._headers_edit.setPlainText("\n".join(header_lines))

        # Cookies — extract Set-Cookie headers
        cookie_lines = [
            h.get("value", "") for h in headers if h.get("key", "").lower() == "set-cookie"
        ]
        self._cookies_edit.setPlainText("\n".join(cookie_lines) if cookie_lines else "No cookies")

    def clear(self) -> None:
        """Reset to the empty state."""
        self._set_save_enabled(False)
        self._set_state("empty")
        self._status_label.setText("")
        self._time_label.setText("")
        self._size_label.setText("")
        self._body_edit.clear()
        self._headers_edit.clear()
        self._cookies_edit.clear()
        self._error_label.setText("")
        self._last_live_response = None
        self._raw_body = ""
        self._filtered_body = ""
        self._is_filtered = False
        self._filter_expression = ""
        self._filter_bar.hide()
        self._filter_btn.setChecked(False)
        self._filter_input.clear()
        self._filter_error_label.hide()
        self._filter_clear_btn.hide()
        self._filter_apply_btn.show()
        self._wrap_btn.setChecked(True)
        self._body_edit.set_word_wrap(True)

    # -- Format switching ---------------------------------------------

    def _on_format_changed(self, _text: str) -> None:
        """Re-render the response body when the format selector changes."""
        self._apply_body_format()

    def _apply_body_format(self) -> None:
        """Render ``_raw_body`` according to the current format selection.

        When a filter is active the filter expression is re-evaluated
        against the (possibly reformatted) body so the filtered view
        stays consistent across format switches.
        """
        fmt = self._format_combo.currentText()
        body = self._raw_body

        if fmt == "Pretty" or fmt == "JSON":
            body = self._try_pretty_json(body)
            self._body_edit.set_language("json")
        elif fmt == "XML":
            self._body_edit.set_language("xml")
        elif fmt == "HTML":
            self._body_edit.set_language("html")
        else:
            self._body_edit.set_language("text")

        # Re-apply active filter if one exists
        if self._is_filtered and self._filter_expression:
            self._run_filter(self._filter_expression, body)
            return

        self._body_edit.set_text(body)

        # Update filter placeholder based on detected language
        self._update_filter_placeholder()

    @staticmethod
    def _try_pretty_json(text: str) -> str:
        """Attempt to pretty-print JSON; return original text on failure."""
        import json

        try:
            parsed = json.loads(text)
            return json.dumps(parsed, indent=4, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            return text

    # -- Beautify / Save -----------------------------------------------

    def _on_beautify(self) -> None:
        """Format the response body using pretty-printing."""
        body = self._raw_body
        if not body:
            return
        pretty = self._try_pretty_json(body)
        if pretty != body:
            self._body_edit.set_text(pretty)
            return
        # Try XML beautification
        pretty = self._try_pretty_xml(body)
        if pretty != body:
            self._body_edit.set_text(pretty)

    @staticmethod
    def _try_pretty_xml(text: str) -> str:
        """Attempt to pretty-print XML; return original text on failure."""
        try:
            import xml.dom.minidom

            dom = xml.dom.minidom.parseString(text)
            return dom.toprettyxml(indent="    ")
        except Exception:
            return text

    def _on_save_response(self) -> None:
        """Emit the save_response_requested signal with current response data."""
        data = self.get_save_response_data()
        if data is None:
            return
        self.save_response_requested.emit(data)

    def _set_save_enabled(self, enabled: bool) -> None:
        """Update Save Response button enabled state and notify listeners."""
        self._save_response_btn.setEnabled(enabled)
        self.save_availability_changed.emit(enabled)

    @staticmethod
    def _detect_preview_language(data: dict) -> str | None:
        """Guess the preview language from the response headers."""
        headers = data.get("headers") or []
        content_type = ""
        for header in headers:
            key = str(header.get("key", "")).lower()
            if key == "content-type":
                content_type = str(header.get("value", "")).lower()
                break
        if "json" in content_type:
            return "json"
        if "xml" in content_type:
            return "xml"
        if "html" in content_type:
            return "html"
        # Fallback: sniff body content
        body = str(data.get("body") or "").strip()
        if body and body[0] in ("{", "["):
            import json

            try:
                json.loads(body)
                return "json"
            except (json.JSONDecodeError, ValueError):
                pass
        lower = body[:100].lower()
        if lower.startswith("<?xml"):
            return "xml"
        if lower.startswith("<!doctype html") or lower.startswith("<html"):
            return "html"
        if content_type:
            return "text"
        return None

    # -- Popup handlers ------------------------------------------------

    def _close_other_popups(self, keep: InfoPopup | None) -> None:
        """Close every open popup except *keep*."""
        for popup in (
            self._status_popup,
            self._timing_popup,
            self._size_popup,
            self._network_popup,
        ):
            if popup is not None and popup is not keep and popup.isVisible():
                popup.close()

    def _on_status_clicked(self) -> None:
        """Open or refresh the status description popup."""
        if self._status_popup is None:
            self._status_popup = StatusPopup(self)
        self._close_other_popups(self._status_popup)
        self._status_popup.update_status(
            self._last_status_code,
            self._last_status_text,
            self._last_status_color,
        )
        self._status_popup.show_below(self._status_label)

    def _on_time_clicked(self) -> None:
        """Open or refresh the timing breakdown popup."""
        if self._timing_popup is None:
            self._timing_popup = TimingPopup(self)
        self._close_other_popups(self._timing_popup)
        if self._timing_data is not None:
            self._timing_popup.update_timing(self._timing_data, self._last_elapsed_ms)
        self._timing_popup.show_below(self._time_label)

    def _on_size_clicked(self) -> None:
        """Open or refresh the size breakdown popup."""
        if self._size_popup is None:
            self._size_popup = SizePopup(self)
        self._close_other_popups(self._size_popup)
        self._size_popup.update_sizes(self._size_data)
        self._size_popup.show_below(self._size_label)

    def _on_network_clicked(self) -> None:
        """Open or refresh the network info popup."""
        if self._network_popup is None:
            self._network_popup = NetworkPopup(self)
        self._close_other_popups(self._network_popup)
        self._network_popup.update_network(self._network_data)
        self._network_popup.show_below(self._network_icon)

    # -- Toolbar handlers ----------------------------------------------

    def _on_wrap_toggle(self) -> None:
        """Toggle word wrap on the response body editor."""
        self._body_edit.set_word_wrap(self._wrap_btn.isChecked())

    def _on_copy_body(self) -> None:
        """Copy the current response body text to the system clipboard."""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._body_edit.toPlainText())
        # Brief visual feedback — swap icon to a check mark for 1.5 s
        self._copy_btn.setIcon(phi("check"))
        btn = self._copy_btn

        def _restore_icon() -> None:
            with contextlib.suppress(RuntimeError):
                btn.setIcon(phi("clipboard"))

        QTimer.singleShot(1500, _restore_icon)
