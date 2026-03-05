"""Response viewer pane showing HTTP response status, body, and headers.

Displays the result of an HTTP request sent from the request editor.
Supports three visual states: empty (no request sent), loading
(request in progress), and populated (response received or error).

Status, timing, and size labels are clickable and open floating
popup panels with breakdown details (matching Postman's UX).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QShortcut, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.code_editor import CodeEditorWidget
from ui.icons import phi
from ui.info_popup import ClickableLabel, InfoPopup
from ui.request.popups.network_popup import NetworkPopup
from ui.request.popups.size_popup import SizePopup
from ui.request.popups.status_popup import StatusPopup
from ui.request.popups.timing_popup import TimingPopup
from ui.theme import (
    COLOR_DANGER,
    COLOR_DELETE,
    COLOR_IMPORT_ERROR,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_WHITE,
)

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


class ResponseViewerWidget(QWidget):
    """Display HTTP response data with status bar and tabbed body/headers.

    Call :meth:`load_response` to populate from an ``HttpResponseDict``,
    :meth:`show_loading` to display a progress indicator, or
    :meth:`show_error` for error states.
    """

    save_response_requested = Signal(dict)

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
        self._save_response_btn.clicked.connect(self._on_save_response)
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

        # -- Progress bar (loading state) -----------------------------
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate
        self._progress_bar.setFixedHeight(_PROGRESS_HEIGHT)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        root.addWidget(self._progress_bar)

        # -- Tabbed area: Body, Headers -------------------------------
        self._tabs = QTabWidget()
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
        self._beautify_btn.setIcon(phi("magic-wand"))
        self._beautify_btn.setFixedWidth(70)
        self._beautify_btn.setToolTip("Format and beautify the response body")
        self._beautify_btn.setObjectName("smallPrimaryButton")
        self._beautify_btn.clicked.connect(self._on_beautify)
        format_row.addWidget(self._beautify_btn)

        format_row.addStretch()
        body_layout.addLayout(format_row)

        self._body_edit = CodeEditorWidget(read_only=True)
        self._body_edit.setPlaceholderText("Response body")
        body_layout.addWidget(self._body_edit, 1)

        # Search bar for body (toggle with Ctrl+F)
        self._search_bar = QWidget()
        search_layout = QHBoxLayout(self._search_bar)
        search_layout.setContentsMargins(0, 4, 0, 0)
        search_layout.setSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Find in response\u2026")
        self._search_input.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self._search_input, 1)

        self._search_count_label = QLabel("")
        self._search_count_label.setObjectName("mutedLabel")
        search_layout.addWidget(self._search_count_label)

        prev_btn = QPushButton()
        prev_btn.setIcon(phi("caret-up"))
        prev_btn.setFixedWidth(24)
        prev_btn.setToolTip("Previous match")
        prev_btn.clicked.connect(self._search_prev)
        search_layout.addWidget(prev_btn)

        next_btn = QPushButton()
        next_btn.setIcon(phi("caret-down"))
        next_btn.setFixedWidth(24)
        next_btn.setToolTip("Next match")
        next_btn.clicked.connect(self._search_next)
        search_layout.addWidget(next_btn)

        close_btn = QPushButton()
        close_btn.setIcon(phi("x"))
        close_btn.setFixedWidth(24)
        close_btn.setToolTip("Close search")
        close_btn.clicked.connect(self._close_search)
        search_layout.addWidget(close_btn)

        self._search_bar.hide()
        body_layout.addWidget(self._search_bar)

        # Ctrl+F shortcut to toggle search
        self._find_shortcut = QShortcut("Ctrl+F", self)
        self._find_shortcut.activated.connect(self._toggle_search)

        self._search_matches: list[int] = []
        self._search_index: int = -1

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

        # Saved responses tab
        self._saved_list = QTextEdit()
        self._saved_list.setReadOnly(True)
        self._saved_list.setPlaceholderText("No saved responses")
        self._saved_list.setObjectName("monoEdit")
        self._tabs.addTab(self._saved_list, "Saved")

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
        self._set_state("empty")
        self._status_label.setText("")
        self._time_label.setText("")
        self._size_label.setText("")
        self._body_edit.clear()
        self._headers_edit.clear()
        self._cookies_edit.clear()
        self._error_label.setText("")
        self._raw_body = ""

    # -- Format switching ---------------------------------------------

    def _on_format_changed(self, _text: str) -> None:
        """Re-render the response body when the format selector changes."""
        self._apply_body_format()

    def _apply_body_format(self) -> None:
        """Render ``_raw_body`` according to the current format selection."""
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

        self._body_edit.set_text(body)

    @staticmethod
    def _try_pretty_json(text: str) -> str:
        """Attempt to pretty-print JSON; return original text on failure."""
        import json

        try:
            parsed = json.loads(text)
            return json.dumps(parsed, indent=4, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            return text

    # -- Body search ---------------------------------------------------

    def _toggle_search(self) -> None:
        """Show or hide the body search bar."""
        if self._search_bar.isVisible():
            self._close_search()
        else:
            self._search_bar.show()
            self._search_input.setFocus()
            self._search_input.selectAll()

    def _close_search(self) -> None:
        """Hide the search bar and clear highlights."""
        self._search_bar.hide()
        self._search_input.clear()
        self._clear_highlights()

    def _on_search_text_changed(self, text: str) -> None:
        """Highlight all occurrences of *text* in the body."""
        self._clear_highlights()
        self._search_matches = []
        self._search_index = -1

        if not text:
            self._search_count_label.setText("")
            return

        # Find all matches
        body_text = self._body_edit.toPlainText()
        start = 0
        while True:
            idx = body_text.find(text, start)
            if idx == -1:
                break
            self._search_matches.append(idx)
            start = idx + 1

        if not self._search_matches:
            self._search_count_label.setText("No results")
            return

        # Highlight all matches via extra selections
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(COLOR_WARNING))
        selections: list[QTextEdit.ExtraSelection] = []
        for pos in self._search_matches:
            sel = QTextEdit.ExtraSelection()
            cur = QTextCursor(self._body_edit.document())
            cur.setPosition(pos)
            cur.setPosition(pos + len(text), QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = cur
            sel.format = fmt
            selections.append(sel)
        self._body_edit.set_search_selections(selections)

        # Move to first match
        self._search_index = 0
        self._goto_match()

    def _search_next(self) -> None:
        """Move to the next search match."""
        if not self._search_matches:
            return
        self._search_index = (self._search_index + 1) % len(self._search_matches)
        self._goto_match()

    def _search_prev(self) -> None:
        """Move to the previous search match."""
        if not self._search_matches:
            return
        self._search_index = (self._search_index - 1) % len(self._search_matches)
        self._goto_match()

    def _goto_match(self) -> None:
        """Scroll to the current search match and update the counter."""
        if self._search_index < 0 or self._search_index >= len(self._search_matches):
            return
        pos = self._search_matches[self._search_index]
        text = self._search_input.text()
        cursor = self._body_edit.textCursor()
        cursor.setPosition(pos)
        cursor.setPosition(pos + len(text), QTextCursor.MoveMode.KeepAnchor)
        self._body_edit.setTextCursor(cursor)
        self._body_edit.ensureCursorVisible()
        total = len(self._search_matches)
        self._search_count_label.setText(f"{self._search_index + 1} of {total}")

    def _clear_highlights(self) -> None:
        """Remove all search highlight formatting from the body."""
        self._body_edit.set_search_selections([])

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
        if not self._raw_body and not self._status_label.text():
            return
        data = {
            "status": self._status_label.text(),
            "body": self._raw_body,
            "headers": self._headers_edit.toPlainText(),
        }
        self.save_response_requested.emit(data)

    def load_saved_responses(self, responses: list[dict]) -> None:
        """Populate the Saved tab with a list of saved response dicts."""
        if not responses:
            self._saved_list.setPlainText("No saved responses")
            return
        lines = []
        for resp in responses:
            name = resp.get("name", "Untitled")
            code = resp.get("code", "")
            status = resp.get("status", "")
            lines.append(f"--- {name} ({code} {status}) ---")
            body = resp.get("body", "")
            if body:
                lines.append(body[:500])
            lines.append("")
        self._saved_list.setPlainText("\n".join(lines))

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
