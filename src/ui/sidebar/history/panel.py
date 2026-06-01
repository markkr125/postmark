"""Send-history panel — per-request list/detail flyout (read-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QFrame,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.request_history_service import RequestHistoryService
from ui.sidebar.history.delegate import (
    ROLE_HISTORY_IS_DATE_GROUP,
    HistoryEntryDelegate,
)
from ui.sidebar.history.helpers import (
    build_row_name,
    extract_history_request_headers,
    find_history_tree_item,
    first_history_entry_id,
    format_executed_at,
    populate_history_tree_widget,
)
from ui.sidebar.history.panel_detail_tabs import _HistoryPanelDetailTabsMixin
from ui.sidebar.history.search_filter import _PanelSearchFilterMixin
from ui.sidebar.saved_responses.helpers import (
    detect_body_language,
    extract_snapshot_body,
    extract_snapshot_method,
    extract_snapshot_url,
    format_body_size,
    format_code_text,
    format_headers,
)
from ui.styling.icons import phi
from ui.styling.theme import COLOR_WHITE, method_color, status_color
from ui.widgets.code_editor import CodeEditorWidget

if TYPE_CHECKING:
    from services.request_history_service import RequestHistoryEntryDict


class HistoryPanel(_HistoryPanelDetailTabsMixin, _PanelSearchFilterMixin, QWidget):
    """Read-only list/detail panel for HTTP send history on a request tab."""

    refresh_requested = Signal()
    replay_requested = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the panel UI and start in the no-request state."""
        super().__init__(parent)
        self.setObjectName("requestHistoryPanel")

        self._request_id: int | None = None
        self._request_name: str = ""
        self._is_persisted_request: bool = False
        self._items: list[RequestHistoryEntryDict] = []
        self._items_by_id: dict[int, RequestHistoryEntryDict] = {}
        self._current_entry_id: int | None = None
        self._body_raw_text: str = ""
        self._body_language: str = "text"
        self._snapshot_raw_data: Any = None
        self._req_body_raw_text: str = ""
        self._req_body_language: str = "text"
        self._body_view_mode: str = "Pretty"
        self._req_body_view_mode: str = "Pretty"

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 8)
        root.setSpacing(6)

        self._refresh_btn = self._make_icon_btn(
            "arrow-clockwise",
            "Refresh history",
            "iconButton",
            self.refresh_requested.emit,
        )

        self._state_label = QLabel()
        self._state_label.setObjectName("emptyStateLabel")
        self._state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state_label.setWordWrap(True)
        root.addWidget(self._state_label, 1)

        self._history_search_input = QLineEdit()
        self._history_search_input.setObjectName("requestHistorySearch")
        self._history_search_input.setPlaceholderText("Search URL or status (e.g. 200, 400)")
        self._history_search_input.setClearButtonEnabled(True)
        self._history_search_input.textChanged.connect(self._on_history_search_changed)
        self._history_search_input.hide()
        root.addWidget(self._history_search_input)

        self._content_splitter = QSplitter(Qt.Orientation.Vertical)
        self._content_splitter.setChildrenCollapsible(False)
        self._content_splitter.hide()
        root.addWidget(self._content_splitter, 1)

        self._list_stack = QStackedWidget()
        self._list_stack.setObjectName("requestHistoryList")

        no_match_page = QFrame()
        no_match_page.setObjectName("requestHistoryListEmpty")
        no_match_layout = QVBoxLayout(no_match_page)
        no_match_layout.setContentsMargins(8, 8, 8, 8)
        self._list_empty_label = QLabel()
        self._list_empty_label.setObjectName("emptyStateLabel")
        self._list_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_empty_label.setWordWrap(True)
        no_match_layout.addStretch(1)
        no_match_layout.addWidget(self._list_empty_label)
        no_match_layout.addStretch(1)
        self._list_stack.addWidget(no_match_page)

        self._tree_widget = QTreeWidget()
        self._tree_widget.setObjectName("requestHistoryTree")
        self._tree_widget.setHeaderHidden(True)
        self._tree_widget.setRootIsDecorated(True)
        self._tree_widget.setIndentation(16)
        self._tree_widget.setAnimated(False)
        self._tree_widget.setExpandsOnDoubleClick(False)
        self._tree_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tree_widget.itemClicked.connect(self._on_tree_item_clicked)
        self._tree_widget.currentItemChanged.connect(self._on_selection_changed)
        self._tree_widget.setItemDelegate(HistoryEntryDelegate(self._tree_widget))
        self._tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree_widget.customContextMenuRequested.connect(self._on_tree_context_menu)
        self._list_stack.addWidget(self._tree_widget)
        self._list_stack.setCurrentWidget(self._tree_widget)

        self._content_splitter.addWidget(self._list_stack)

        detail_host = QWidget()
        detail_layout = QVBoxLayout(detail_host)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(6)

        detail_header = QHBoxLayout()
        detail_header.setContentsMargins(0, 0, 0, 0)
        detail_header.setSpacing(6)

        self._status_badge = QLabel()
        self._status_badge.setObjectName("savedResponseStatusBadge")
        self._status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_badge.setFixedHeight(22)
        self._status_badge.setMinimumWidth(42)
        detail_header.addWidget(self._status_badge)

        summary_col = QVBoxLayout()
        summary_col.setContentsMargins(0, 0, 0, 0)
        summary_col.setSpacing(0)

        self._detail_name = QLabel("Select a send")
        self._detail_name.setObjectName("sectionLabel")
        summary_col.addWidget(self._detail_name)

        self._detail_meta = QLabel("")
        self._detail_meta.setObjectName("mutedLabel")
        summary_col.addWidget(self._detail_meta)

        detail_header.addLayout(summary_col, 1)

        self._replay_btn = self._make_replay_btn()
        detail_header.addWidget(self._replay_btn)

        detail_layout.addLayout(detail_header)

        request_info_row = QHBoxLayout()
        request_info_row.setContentsMargins(0, 0, 0, 0)
        request_info_row.setSpacing(6)

        self._request_method_badge = QLabel()
        self._request_method_badge.setObjectName("savedResponseMethodBadge")
        self._request_method_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._request_method_badge.setFixedHeight(20)
        self._request_method_badge.setFixedWidth(50)
        request_info_row.addWidget(self._request_method_badge)

        self._request_url_label = QLabel()
        self._request_url_label.setObjectName("mutedLabel")
        self._request_url_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        request_info_row.addWidget(self._request_url_label, 1)

        self._request_info_widget = QWidget()
        request_info_layout = QVBoxLayout(self._request_info_widget)
        request_info_layout.setContentsMargins(0, 0, 0, 0)
        request_info_layout.addLayout(request_info_row)
        self._request_info_widget.hide()
        detail_layout.addWidget(self._request_info_widget)

        self._detail_tabs = QTabWidget()
        self._detail_tabs.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)
        detail_layout.addWidget(self._detail_tabs, 1)

        self._build_body_tab()
        self._build_headers_tab()
        self._build_request_headers_tab()
        self._build_request_body_tab()

        self._content_splitter.addWidget(detail_host)
        self._content_splitter.setSizes([180, 280])

        self.clear()

    def refresh_button(self) -> QPushButton:
        """Return the refresh control (reparented to the flyout title bar)."""
        return self._refresh_btn

    def _on_tree_context_menu(self, pos: QPoint) -> None:
        """Show replay/delete actions for send rows under the cursor."""
        item = self._tree_widget.itemAt(pos)
        if item is None or item.data(0, ROLE_HISTORY_IS_DATE_GROUP):
            return
        entry_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(entry_id, int):
            return

        menu = QMenu(self)
        replay_action = QAction("Replay this request", self)
        replay_action.triggered.connect(lambda: self.replay_requested.emit(entry_id))
        delete_action = QAction("Delete item", self)
        delete_action.triggered.connect(lambda: self.delete_requested.emit(entry_id))
        menu.addAction(replay_action)
        menu.addAction(delete_action)
        menu.exec(self._tree_widget.viewport().mapToGlobal(pos))

    def _on_replay_clicked(self) -> None:
        """Emit :attr:`replay_requested` for the selected history row."""
        if self._current_entry_id is not None:
            self.replay_requested.emit(self._current_entry_id)

    def set_request_context(
        self,
        request_id: int | None,
        request_name: str | None,
        *,
        is_persisted_request: bool,
    ) -> None:
        """Set the active request context shown in the panel header."""
        if request_id != self._request_id:
            self._current_entry_id = None
        self._request_id = request_id
        self._request_name = request_name or ""
        self._is_persisted_request = is_persisted_request

    def _show_full_panel_empty_state(self, message: str) -> None:
        """Hide browse chrome and show a centred empty message (no search box)."""
        self._state_label.setText(message)
        self._state_label.show()
        self._history_search_input.hide()
        self._content_splitter.hide()
        self._set_detail_enabled(False)

    def _show_browse_layout(self) -> None:
        """Show search, list, and detail (hide full-panel empty message)."""
        self._state_label.hide()
        self._history_search_input.show()
        self._content_splitter.show()

    def show_request_required_state(self, message: str) -> None:
        """Show a contextual empty state when history is unavailable."""
        self._show_full_panel_empty_state(message)
        self._refresh_btn.setEnabled(False)

    def show_empty_history_state(self) -> None:
        """Show the empty state for a persisted request with no sends yet."""
        self._show_full_panel_empty_state(
            "No history for this request yet.\n\nSend the request to record an entry here."
        )
        self._refresh_btn.setEnabled(self._request_id is not None)

    def refresh(self, search: str = "") -> None:
        """Reload send history for the current persisted request."""
        if not self._is_persisted_request or self._request_id is None:
            return
        term = search if search else self._history_search_input.text().strip()
        items = RequestHistoryService.list_for_request(self._request_id, search=term)
        self._apply_items(items)

    def _on_history_search_changed(self, text: str) -> None:
        """Filter the list when the search box changes."""
        if not self._is_persisted_request or self._request_id is None:
            return
        self.refresh(search=text.strip())

    def _apply_items(self, items: list[RequestHistoryEntryDict]) -> None:
        """Populate the list from metadata rows."""
        self._items = items
        self._items_by_id = {int(item["id"]): item for item in items if "id" in item}
        self._refresh_btn.setEnabled(self._request_id is not None)
        self._history_search_input.setEnabled(True)

        if not items:
            self._current_entry_id = None
            self._tree_widget.clear()
            term = self._history_search_input.text().strip()
            if term:
                self._show_browse_layout()
                self._list_empty_label.setText(f'No history matches "{term}".')
                self._list_stack.setCurrentIndex(0)
                self._set_detail_enabled(False)
            else:
                self.show_empty_history_state()
            return

        populate_history_tree_widget(self._tree_widget, items)

        self._show_browse_layout()
        self._list_stack.setCurrentWidget(self._tree_widget)
        first_id = first_history_entry_id(self._tree_widget)
        target_id = self._current_entry_id if self._current_entry_id in self._items_by_id else None
        self._select_entry(target_id or first_id)

    def clear(self) -> None:
        """Reset the panel to its no-request state."""
        self._request_id = None
        self._request_name = ""
        self._is_persisted_request = False
        self._items = []
        self._items_by_id = {}
        self._current_entry_id = None
        self._tree_widget.clear()
        self._history_search_input.clear()
        self._history_search_input.setEnabled(False)
        self._body_raw_text = ""
        self._body_language = "text"
        self._snapshot_raw_data = None
        self._req_body_raw_text = ""
        self._req_body_language = "text"
        self._body_view_mode = "Pretty"
        self._req_body_view_mode = "Pretty"
        self._set_combo_text(self._body_view_combo, self._body_view_mode)
        self._set_combo_text(self._req_body_view_combo, self._req_body_view_mode)
        self._body_edit.set_language("text")
        self._body_edit.set_text("")
        self._body_edit.hide()
        self._body_empty_label.show()
        self._headers_edit.set_language("text")
        self._headers_edit.set_text("")
        self._headers_edit.hide()
        self._headers_empty_label.show()
        self._req_headers_edit.set_language("text")
        self._req_headers_edit.set_text("")
        self._req_headers_edit.hide()
        self._req_headers_empty_label.show()
        self._req_body_edit.set_language("text")
        self._req_body_edit.set_text("")
        self._req_body_edit.hide()
        self._req_body_empty_label.show()
        self._request_info_widget.hide()
        self._status_badge.setText("")
        self._status_badge.setStyleSheet("")
        self._detail_name.setText("Select a send")
        self._detail_meta.setText("")
        self._reset_search_filter()
        self.show_request_required_state(
            "Open a saved request to browse history for this request."
        )

    def _restore_tree_selection_to_current_entry(self) -> bool:
        """Re-select the active send row after a date-group row receives focus."""
        if self._current_entry_id is None:
            return False
        leaf = find_history_tree_item(self._tree_widget, self._current_entry_id)
        if leaf is None:
            return False
        self._tree_widget.blockSignals(True)
        self._tree_widget.setCurrentItem(leaf)
        self._tree_widget.blockSignals(False)
        return True

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Toggle date groups on single click without changing the active send."""
        if not item.data(0, ROLE_HISTORY_IS_DATE_GROUP):
            return
        item.setExpanded(not item.isExpanded())
        self._restore_tree_selection_to_current_entry()

    def focus_entry(self, entry_id: int) -> bool:
        """Select *entry_id* in the tree, expand its date group, and load detail."""
        if not self._is_persisted_request or self._request_id is None:
            return False
        if entry_id not in self._items_by_id:
            self.refresh()
        item = find_history_tree_item(self._tree_widget, entry_id)
        if item is None:
            return False
        parent = item.parent()
        if parent is not None:
            parent.setExpanded(True)
        self._tree_widget.scrollToItem(
            item,
            QAbstractItemView.ScrollHint.EnsureVisible,
        )
        self._select_entry(entry_id)
        return True

    def _select_entry(self, entry_id: int | None) -> None:
        """Select a tree row and load detail for *entry_id*."""
        if entry_id is None:
            self._set_detail_enabled(False)
            return
        item = find_history_tree_item(self._tree_widget, entry_id)
        if item is not None:
            self._tree_widget.setCurrentItem(item)
            self._load_detail(entry_id)
            return
        first_id = first_history_entry_id(self._tree_widget)
        if first_id is not None:
            self._select_entry(first_id)
            return
        self._set_detail_enabled(False)

    def _on_selection_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        """Update the detail pane when the tree selection changes."""
        if current is not None and current.data(0, ROLE_HISTORY_IS_DATE_GROUP):
            self._restore_tree_selection_to_current_entry()
            return
        if current is None:
            if self._restore_tree_selection_to_current_entry():
                return
            self._set_detail_enabled(False)
            return
        entry_id = current.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(entry_id, int):
            self._set_detail_enabled(False)
            return
        self._current_entry_id = entry_id
        self._load_detail(entry_id)

    def _load_detail(self, entry_id: int) -> None:
        """Fetch full entry payloads and render the detail pane."""
        entry = RequestHistoryService.get_entry(entry_id)
        if entry is None:
            self._set_detail_enabled(False)
            return
        detail = RequestHistoryService.entry_to_detail_snapshot(entry)
        self._populate_detail(entry, detail)

    def _populate_detail(
        self,
        entry: RequestHistoryEntryDict,
        detail: dict[str, Any],
    ) -> None:
        """Render one send-history entry in the detail pane."""
        code = detail.get("status_code", 0)
        badge_text = str(code) if code else "\u2014"
        colour = status_color(code if code else 0)
        self._status_badge.setText(badge_text)
        self._status_badge.setStyleSheet(
            f"background: {colour}; color: #ffffff; "
            f"padding: 2px 8px; border-radius: 3px; "
            f"font-weight: bold; font-size: 11px;"
        )

        self._detail_name.setText(build_row_name(entry))
        meta_parts: list[str] = []
        executed = entry.get("executed_at")
        if isinstance(executed, str) and executed:
            meta_parts.append(format_executed_at(executed))
        elapsed = entry.get("elapsed_ms")
        if elapsed is not None:
            meta_parts.append(f"{float(elapsed):.0f} ms")
        size = entry.get("response_size_bytes")
        if size:
            meta_parts.append(format_body_size(int(size)))
        label = entry.get("source_label")
        if label:
            meta_parts.append(str(label))
        if detail.get("body_truncated"):
            meta_parts.append("truncated")
        if detail.get("error"):
            meta_parts.append(str(detail["error"]))
        self._detail_meta.setText(" \u00b7 ".join(meta_parts))

        self._reset_search_filter()
        body_text = str(detail.get("body") or "")
        self._body_raw_text = body_text
        self._body_language = detect_body_language(body_text) or "text"
        self._set_combo_text(self._body_view_combo, self._body_view_mode)
        self._refresh_body_view()

        headers_text = format_headers(detail.get("headers"))
        if headers_text:
            self._headers_empty_label.hide()
            self._headers_edit.show()
            self._headers_edit.set_language("text")
            self._headers_edit.set_text(headers_text)
        else:
            self._headers_edit.hide()
            self._headers_empty_label.show()

        snapshot = detail.get("original_request")
        self._snapshot_raw_data = snapshot
        req_method = extract_snapshot_method(snapshot if isinstance(snapshot, dict) else None)
        req_url = extract_snapshot_url(snapshot if isinstance(snapshot, dict) else None)
        if req_method or req_url:
            self._request_method_badge.setText(req_method)
            method_colour = method_color(req_method)
            self._request_method_badge.setStyleSheet(
                f"background: {method_colour}; color: #ffffff; "
                f"padding: 1px 6px; border-radius: 3px; "
                f"font-weight: bold; font-size: 10px;"
            )
            self._request_url_label.setText(req_url)
            self._request_url_label.setToolTip(req_url)
            self._request_info_widget.show()
        else:
            self._request_info_widget.hide()

        req_headers_text = extract_history_request_headers(
            snapshot if isinstance(snapshot, dict) else None
        )
        if req_headers_text:
            self._req_headers_empty_label.hide()
            self._req_headers_edit.show()
            self._req_headers_edit.set_language("text")
            self._req_headers_edit.set_text(req_headers_text)
        else:
            self._req_headers_edit.hide()
            self._req_headers_empty_label.show()

        req_body, req_body_lang = extract_snapshot_body(
            snapshot if isinstance(snapshot, dict) else None
        )
        self._req_body_raw_text = req_body
        self._req_body_language = req_body_lang
        self._set_combo_text(self._req_body_view_combo, self._req_body_view_mode)
        self._refresh_request_body_view()

        self._set_detail_enabled(True)
        self._update_replay_button_enabled()

    def _update_replay_button_enabled(self) -> None:
        """Enable replay when the selected row has a URL to send."""
        btn = getattr(self, "_replay_btn", None)
        if btn is None:
            return
        entry = (
            self._items_by_id.get(self._current_entry_id)
            if self._current_entry_id is not None
            else None
        )
        if entry is None:
            btn.setEnabled(False)
            return
        btn.setEnabled(RequestHistoryService.can_replay_entry(entry))

    def _set_detail_enabled(self, enabled: bool) -> None:
        """Enable or disable detail tabs."""
        self._detail_tabs.setEnabled(enabled)
        if not enabled:
            replay = getattr(self, "_replay_btn", None)
            if replay is not None:
                replay.setEnabled(False)

    def _make_replay_btn(self) -> QPushButton:
        """White replay icon in the detail header."""
        btn = QPushButton()
        btn.setIcon(phi("arrow-clockwise", color=COLOR_WHITE, size=16))
        btn.setObjectName("requestHistoryReplayButton")
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Replay this request (updates response only)")
        btn.setEnabled(False)
        btn.clicked.connect(self._on_replay_clicked)
        return btn

    def _make_copy_btn(self, slot: object) -> QPushButton:
        """Create a clipboard copy icon button connected to *slot*."""
        return self._make_icon_btn("clipboard", "Copy to clipboard", "iconButton", slot)

    @staticmethod
    def _make_icon_btn(
        icon_name: str,
        tooltip: str,
        obj_name: str,
        slot: object = None,
    ) -> QPushButton:
        """Create a 28x28 icon button with optional click slot."""
        btn = QPushButton()
        btn.setIcon(phi(icon_name))
        btn.setObjectName(obj_name)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)
        if slot is not None:
            btn.clicked.connect(slot)
        return btn

    @staticmethod
    def _make_empty_label(text: str) -> QLabel:
        """Create a centred empty-state label for a detail tab."""
        label = QLabel(text)
        label.setObjectName("emptyStateLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _copy_editor(self, editor: CodeEditorWidget) -> None:
        """Copy the given editor's text to the system clipboard."""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(editor.toPlainText())

    def _refresh_body_view(self, _mode: str | None = None) -> None:
        """Render the response body using the selected view mode."""
        self._body_view_mode = self._body_view_combo.currentText()
        if not self._body_raw_text:
            self._body_edit.hide()
            self._body_empty_label.show()
            return

        self._body_empty_label.hide()
        self._body_edit.show()
        language = self._body_language or "text"
        body_text = self._body_raw_text
        if self._body_view_mode == "Pretty":
            body_text = format_code_text(body_text, language, pretty=True)
        self._body_edit.set_language(language)

        if self._is_filtered and self._filter_expression:
            self._run_filter(self._filter_expression, body_text)
            return

        self._body_edit.set_text(body_text)

    def _refresh_request_body_view(self, _mode: str | None = None) -> None:
        """Render the request snapshot body using the selected view mode."""
        self._req_body_view_mode = self._req_body_view_combo.currentText()
        if not self._req_body_raw_text:
            self._req_body_edit.hide()
            self._req_body_empty_label.show()
            return

        self._req_body_empty_label.hide()
        self._req_body_edit.show()
        language = self._req_body_language or "text"
        body_text = self._req_body_raw_text
        if self._req_body_view_mode == "Pretty":
            body_text = format_code_text(body_text, language, pretty=True)
        self._req_body_edit.set_language(language)
        self._req_body_edit.set_text(body_text)

    @staticmethod
    def _set_combo_text(combo: QComboBox, text: str) -> None:
        """Set combo text without triggering a redundant re-render."""
        combo.blockSignals(True)
        combo.setCurrentText(text)
        combo.blockSignals(False)
