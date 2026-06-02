"""Send-history panel — per-request list/detail flyout (read-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
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
from ui.sidebar.history.detail import HistoryDetailLoader
from ui.sidebar.history.date_filter.mixin import _HistoryDateFilterMixin
from ui.sidebar.history.global_mode import _HistoryPanelGlobalMixin, _HistoryTreeOpenFilter
from ui.sidebar.history.search_filter import _PanelSearchFilterMixin
from ui.sidebar.saved_responses.helpers import (
    detect_body_language,
    extract_snapshot_body,
    extract_snapshot_method,
    extract_snapshot_url,
    format_body_size,
    format_headers,
)
from ui.styling.icons import phi
from ui.styling.theme import COLOR_WHITE, method_color, status_color
from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.text_format_async import AsyncTextFormatRunner, skip_inline_text_for_async_pretty

if TYPE_CHECKING:
    from services.request_history_service import RequestHistoryEntryDict


class HistoryPanel(  # type: ignore[misc]
    _HistoryPanelGlobalMixin,
    _HistoryDateFilterMixin,
    _HistoryPanelDetailTabsMixin,
    _PanelSearchFilterMixin,
    QWidget,
):
    """Read-only list/detail panel for HTTP send history (per-request or global)."""

    refresh_requested = Signal()
    replay_requested = Signal(int)
    delete_requested = Signal(int)
    entry_open_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the panel UI and start in the no-request state."""
        super().__init__(parent)
        self.setObjectName("requestHistoryPanel")

        self._request_id: int | None = None  # type: ignore[assignment]
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
        self._init_global_mode_state()
        self._body_format_generation = 0
        self._req_body_format_generation = 0
        self._body_format_runner = AsyncTextFormatRunner(self)
        self._body_format_runner.formatted.connect(self._on_async_response_body_formatted)
        self._req_body_format_runner = AsyncTextFormatRunner(self)
        self._req_body_format_runner.formatted.connect(self._on_async_request_body_formatted)
        self._detail_load_generation = 0
        self._pending_detail_generation = 0
        self._pending_detail_entry: RequestHistoryEntryDict | None = None
        self._pending_detail_snapshot: dict[str, Any] | None = None
        self._detail_apply_timer = QTimer(self)
        self._detail_apply_timer.setSingleShot(True)
        self._detail_apply_timer.timeout.connect(self._apply_pending_detail_load)
        self._detail_loader = HistoryDetailLoader(self)
        self._detail_loader.finished.connect(self._on_detail_load_finished)

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
        self._init_date_filter_state()
        self._search_row.hide()
        root.addWidget(self._search_row)

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

        self._detail_host = QWidget()
        detail_host = self._detail_host
        detail_layout = QVBoxLayout(detail_host)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(6)

        self._detail_header_row = QHBoxLayout()
        detail_header = self._detail_header_row
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
        self._open_btn = self._build_open_button()
        detail_header.addWidget(self._replay_btn)
        detail_header.addWidget(self._open_btn)

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

        self._detail_loading_bar = QProgressBar()
        self._detail_loading_bar.setObjectName("requestHistoryDetailLoading")
        self._detail_loading_bar.setRange(0, 0)
        self._detail_loading_bar.setFixedHeight(4)
        self._detail_loading_bar.setTextVisible(False)
        self._detail_loading_bar.hide()
        detail_layout.addWidget(self._detail_loading_bar)

        self._detail_tabs = QTabWidget()
        self._detail_tabs.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)
        detail_layout.addWidget(self._detail_tabs, 1)

        self._build_body_tab()
        self._build_headers_tab()
        self._build_request_headers_tab()
        self._build_request_body_tab()

        self._content_splitter.addWidget(detail_host)
        self._content_splitter.setSizes([180, 280])

        self._tree_open_filter = _HistoryTreeOpenFilter(self, self._tree_widget)
        self._tree_widget.installEventFilter(self._tree_open_filter)

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
        if self._is_global_mode():
            for action in self._global_context_menu_actions(entry_id):
                menu.addAction(action)
        else:
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
        self._search_row.hide()
        self._content_splitter.hide()
        self._set_detail_enabled(False)

    def _set_browse_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable search + date filter (browse chrome only)."""
        self._history_search_input.setEnabled(enabled)
        self._date_filter_btn.setEnabled(enabled)

    def _show_browse_layout(self) -> None:
        """Show search and list; detail pane only in per-request mode."""
        self._state_label.hide()
        self._history_search_input.show()
        self._search_row.show()
        self._content_splitter.show()
        self._set_browse_controls_enabled(True)
        if self._is_global_mode():
            self._apply_global_list_only_layout(True)
        else:
            self._apply_global_list_only_layout(False)

    def show_request_required_state(self, message: str) -> None:
        """Show a contextual empty state when history is unavailable."""
        self._show_full_panel_empty_state(message)
        self._refresh_btn.setEnabled(False)
        self._set_browse_controls_enabled(False)

    def show_empty_history_state(self) -> None:
        """Show the empty state when there are no sends for the current scope."""
        if self._is_global_mode():
            self._show_full_panel_empty_state(self._global_empty_message())
            self._refresh_btn.setEnabled(True)
            return
        self._show_full_panel_empty_state(
            "No history for this request yet.\n\nSend the request to record an entry here."
        )
        self._refresh_btn.setEnabled(self._request_id is not None)

    def refresh(self, search: str = "", *, load_detail: bool = True) -> None:
        """Reload send history for the current scope (request or global)."""
        term = search if search else self._history_search_input.text().strip()
        date_kw = self._date_filter_kwargs()
        if self._is_global_mode():
            items = RequestHistoryService.list_for_sidebar(search=term, **date_kw)
            self._apply_items(items, load_detail=load_detail)
            return
        if not self._is_persisted_request or self._request_id is None:
            return
        items = RequestHistoryService.list_for_request(self._request_id, search=term, **date_kw)
        self._apply_items(items, load_detail=load_detail)

    def _on_history_search_changed(self, text: str) -> None:
        """Filter the list when the search box changes."""
        if self._is_global_mode():
            self.refresh(search=text.strip())
            return
        if not self._is_persisted_request or self._request_id is None:
            return
        self.refresh(search=text.strip())

    def _apply_items(
        self,
        items: list[RequestHistoryEntryDict],
        *,
        load_detail: bool = True,
    ) -> None:
        """Populate the list from metadata rows."""
        self._items = items
        self._items_by_id = {int(item["id"]): item for item in items if "id" in item}
        if self._is_global_mode():
            self._refresh_btn.setEnabled(True)
        else:
            self._refresh_btn.setEnabled(self._request_id is not None)

        if not items:
            self._current_entry_id = None
            self._tree_widget.clear()
            term = self._history_search_input.text().strip()
            if term:
                self._show_browse_layout()
                self._list_empty_label.setText(f'No history matches "{term}".')
                self._list_stack.setCurrentIndex(0)
                self._set_detail_enabled(False)
            elif self._date_filter_active():
                self._show_browse_layout()
                self._list_empty_label.setText(f"No sends in {self._date_filter_summary()}.")
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
        entry_id = target_id or first_id
        self._select_entry(entry_id, load_detail=False)
        if load_detail and entry_id is not None and not self._is_global_mode():
            self._schedule_detail_load(entry_id)

    def clear(self) -> None:
        """Reset the panel to its no-request state."""
        self._detail_apply_timer.stop()
        self._pending_detail_entry = None
        self._pending_detail_snapshot = None
        self._detail_loader.cancel()
        self._detail_load_generation += 1
        self._body_format_runner.cancel()
        self._req_body_format_runner.cancel()
        self._body_format_generation += 1
        self._req_body_format_generation += 1
        self._request_id = None
        self._request_name = ""
        self._is_persisted_request = False
        self._items = []
        self._items_by_id = {}
        self._current_entry_id = None
        self._tree_widget.clear()
        self._history_search_input.clear()
        self._set_browse_controls_enabled(False)
        self._reset_date_filter()
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
        if self._is_global_mode():
            self._show_full_panel_empty_state(self._global_empty_message())
            self._refresh_btn.setEnabled(True)
            return
        self.show_request_required_state("Open a saved request to browse history for this request.")

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
        """Global: open send on click. Request mode: expand date groups only."""
        if item.data(0, ROLE_HISTORY_IS_DATE_GROUP):
            item.setExpanded(not item.isExpanded())
            self._restore_tree_selection_to_current_entry()
            return
        if self._is_global_mode():
            entry_id = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(entry_id, int):
                self._emit_entry_open(entry_id)

    def focus_entry(self, entry_id: int, *, load_detail: bool = True) -> bool:
        """Select *entry_id* in the tree; optionally load the read-only detail pane."""
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
        self._select_entry(entry_id, load_detail=load_detail)
        return True

    def _select_entry(self, entry_id: int | None, *, load_detail: bool = True) -> None:
        """Select a tree row and optionally load detail for *entry_id*."""
        if entry_id is None:
            self._set_detail_enabled(False)
            return
        item = find_history_tree_item(self._tree_widget, entry_id)
        if item is not None:
            self._tree_widget.blockSignals(True)
            try:
                self._tree_widget.setCurrentItem(item)
            finally:
                self._tree_widget.blockSignals(False)
            self._current_entry_id = entry_id
            if load_detail and not self._is_global_mode():
                self._load_detail(entry_id)
            elif not load_detail:
                self._update_replay_button_enabled()
            return
        first_id = first_history_entry_id(self._tree_widget)
        if first_id is not None:
            self._select_entry(first_id, load_detail=load_detail)
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
        if self._is_global_mode():
            self._update_replay_button_enabled()
            return
        self._schedule_detail_load(entry_id)

    def schedule_detail_load(self, entry_id: int) -> None:
        """Select a row and load its detail pane after the UI has settled (e.g. global open)."""
        if not self.focus_entry(entry_id, load_detail=False):
            return
        self._schedule_detail_load(entry_id)

    def _schedule_detail_load(self, entry_id: int) -> None:
        """Show loading chrome and fetch full payloads on a worker thread."""
        if self._is_global_mode():
            return
        self._detail_apply_timer.stop()
        self._detail_loader.cancel()
        self._detail_load_generation += 1
        generation = self._detail_load_generation
        self._current_entry_id = entry_id
        self._show_detail_loading(entry_id)
        self._detail_loader.load(entry_id, generation)

    def _show_detail_loading(self, entry_id: int) -> None:
        """Show indeterminate progress while detail payloads load."""
        row = self._items_by_id.get(entry_id)
        if row is not None:
            self._detail_name.setText(build_row_name(row))
            self._detail_meta.setText("Loading response…")
        else:
            self._detail_name.setText("Loading…")
            self._detail_meta.setText("")
        self._status_badge.setText("")
        self._status_badge.setStyleSheet("")
        self._request_info_widget.hide()
        self._detail_loading_bar.show()
        self._detail_tabs.hide()
        self._detail_tabs.setEnabled(False)
        self._update_replay_button_enabled()

    def _hide_detail_loading(self) -> None:
        """Restore detail tabs after loading completes or fails."""
        self._detail_loading_bar.hide()
        self._detail_tabs.show()

    def _on_detail_load_finished(self, generation: int, payload: object) -> None:
        """Apply async detail load result when still the active job."""
        if generation != self._detail_load_generation:
            return
        self._hide_detail_loading()
        if not isinstance(payload, dict):
            self._set_detail_enabled(False)
            return
        entry = payload.get("entry")
        detail = payload.get("detail")
        if not isinstance(entry, dict) or not isinstance(detail, dict):
            self._set_detail_enabled(False)
            return
        self._pending_detail_generation = generation
        self._pending_detail_entry = cast("RequestHistoryEntryDict", entry)
        self._pending_detail_snapshot = detail
        self._detail_apply_timer.start(0)

    def _apply_pending_detail_load(self) -> None:
        """Apply a deferred detail payload when the event loop has settled."""
        if self._pending_detail_generation != self._detail_load_generation:
            return
        entry = self._pending_detail_entry
        detail = self._pending_detail_snapshot
        if entry is None or detail is None:
            return
        self._populate_detail(entry, detail)

    def _load_detail(self, entry_id: int) -> None:
        """Fetch full entry payloads and render the detail pane (sync; tests only)."""
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
        """Enable replay/open when the selected row has a URL to send."""
        entry = (
            self._items_by_id.get(self._current_entry_id)
            if self._current_entry_id is not None
            else None
        )
        can_open = entry is not None and RequestHistoryService.can_replay_entry(entry)
        replay = getattr(self, "_replay_btn", None)
        if replay is not None and not self._is_global_mode():
            replay.setEnabled(can_open)

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
            self._body_format_runner.cancel()
            self._body_format_generation += 1
            self._body_edit.hide()
            self._body_empty_label.show()
            return

        self._body_empty_label.hide()
        self._body_edit.show()
        language = self._body_language or "text"
        body_text = self._body_raw_text
        self._body_edit.set_language(language)
        self._body_format_runner.cancel()
        self._body_format_generation += 1
        generation = self._body_format_generation

        if self._is_filtered and self._filter_expression:
            self._run_filter(self._filter_expression, body_text)
            if self._body_view_mode == "Pretty":
                self._body_format_runner.format_async(
                    generation,
                    body_text,
                    language,
                    pretty=True,
                )
            return

        if not skip_inline_text_for_async_pretty(
            body_text, pretty=self._body_view_mode == "Pretty"
        ):
            self._body_edit.set_text(body_text)
        if self._body_view_mode == "Pretty":
            self._body_format_runner.format_async(
                generation,
                body_text,
                language,
                pretty=True,
            )

    def _refresh_request_body_view(self, _mode: str | None = None) -> None:
        """Render the request snapshot body using the selected view mode."""
        self._req_body_view_mode = self._req_body_view_combo.currentText()
        if not self._req_body_raw_text:
            self._req_body_format_runner.cancel()
            self._req_body_format_generation += 1
            self._req_body_edit.hide()
            self._req_body_empty_label.show()
            return

        self._req_body_empty_label.hide()
        self._req_body_edit.show()
        language = self._req_body_language or "text"
        body_text = self._req_body_raw_text
        self._req_body_edit.set_language(language)
        self._req_body_format_runner.cancel()
        self._req_body_format_generation += 1
        generation = self._req_body_format_generation
        if not skip_inline_text_for_async_pretty(
            body_text, pretty=self._req_body_view_mode == "Pretty"
        ):
            self._req_body_edit.set_text(body_text)
        if self._req_body_view_mode == "Pretty":
            self._req_body_format_runner.format_async(
                generation,
                body_text,
                language,
                pretty=True,
            )

    def _on_async_response_body_formatted(self, generation: int, text: str) -> None:
        """Apply async pretty-print for the response body tab."""
        if generation != self._body_format_generation:
            return
        if self._is_filtered and self._filter_expression:
            self._run_filter(self._filter_expression, text)
            return
        self._body_edit.set_text(text)

    def _on_async_request_body_formatted(self, generation: int, text: str) -> None:
        """Apply async pretty-print for the request snapshot body tab."""
        if generation != self._req_body_format_generation:
            return
        self._req_body_edit.set_text(text)

    @staticmethod
    def _set_combo_text(combo: QComboBox, text: str) -> None:
        """Set combo text without triggering a redundant re-render."""
        combo.blockSignals(True)
        combo.setCurrentText(text)
        combo.blockSignals(False)
