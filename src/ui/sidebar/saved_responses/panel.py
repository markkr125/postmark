"""Saved responses panel — list/detail flyout for browsing saved examples."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal, SignalInstance
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.sidebar.saved_responses.delegate import (
    ROLE_RESPONSE_CODE,
    ROLE_RESPONSE_META,
    ROLE_RESPONSE_NAME,
    SavedResponseDelegate,
)
from ui.sidebar.saved_responses.helpers import (
    build_row_meta,
    detect_body_language,
    extract_snapshot_body,
    extract_snapshot_headers,
    extract_snapshot_method,
    extract_snapshot_url,
    format_body_size,
    format_code_text,
    format_headers,
)
from ui.sidebar.saved_responses.search_filter import _PanelSearchFilterMixin
from ui.styling.icons import phi
from ui.styling.theme import method_color, status_color
from ui.widgets.code_editor import CodeEditorWidget

if TYPE_CHECKING:
    from services.collection_service import SavedResponseDict


class SavedResponsesPanel(_PanelSearchFilterMixin, QWidget):
    """List/detail sidebar panel for saved request responses."""

    save_current_requested = Signal()
    refresh_requested = Signal()
    rename_requested = Signal(int)
    duplicate_requested = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the panel UI and start in the no-request state."""
        super().__init__(parent)

        self._request_id: int | None = None
        self._request_name: str = ""
        self._items: list[SavedResponseDict] = []
        self._items_by_id: dict[int, SavedResponseDict] = {}
        self._current_response_id: int | None = None
        self._body_raw_text: str = ""
        self._body_language: str = "text"
        self._snapshot_raw_data: Any = None
        self._req_body_raw_text: str = ""
        self._req_body_language: str = "text"
        self._body_view_mode: str = "Pretty"
        self._snapshot_view_mode: str = "Pretty"
        self._req_body_view_mode: str = "Pretty"

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 8)
        root.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)

        self._subtitle_label = QLabel("")
        self._subtitle_label.setObjectName("mutedLabel")
        header_row.addWidget(self._subtitle_label, 1)

        self._refresh_btn = self._make_icon_btn(
            "arrow-clockwise",
            "Refresh saved responses",
            "iconButton",
        )
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        header_row.addWidget(self._refresh_btn)

        self._save_current_btn = QPushButton("Save Current")
        self._save_current_btn.setObjectName("smallPrimaryButton")
        self._save_current_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_current_btn.clicked.connect(self.save_current_requested.emit)
        header_row.addWidget(self._save_current_btn)

        root.addLayout(header_row)

        self._state_label = QLabel()
        self._state_label.setObjectName("emptyStateLabel")
        self._state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state_label.setWordWrap(True)
        root.addWidget(self._state_label, 1)

        self._content_splitter = QSplitter(Qt.Orientation.Vertical)
        self._content_splitter.setChildrenCollapsible(False)
        root.addWidget(self._content_splitter, 1)

        self._list_widget = QListWidget()
        self._list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self._list_widget.setItemDelegate(SavedResponseDelegate(self._list_widget))
        self._content_splitter.addWidget(self._list_widget)

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

        self._detail_name = QLabel("Select a saved response")
        self._detail_name.setObjectName("sectionLabel")
        summary_col.addWidget(self._detail_name)

        self._detail_meta = QLabel("")
        self._detail_meta.setObjectName("mutedLabel")
        summary_col.addWidget(self._detail_meta)

        detail_header.addLayout(summary_col, 1)

        self._rename_btn = self._make_icon_btn("pencil-simple", "Rename", "iconButton")
        self._rename_btn.clicked.connect(lambda: self._emit_signal(self.rename_requested))
        detail_header.addWidget(self._rename_btn)

        self._duplicate_btn = self._make_icon_btn("copy", "Duplicate", "iconButton")
        self._duplicate_btn.clicked.connect(lambda: self._emit_signal(self.duplicate_requested))
        detail_header.addWidget(self._duplicate_btn)

        self._delete_btn = self._make_icon_btn("trash", "Delete", "iconDangerButton")
        self._delete_btn.clicked.connect(lambda: self._emit_signal(self.delete_requested))
        detail_header.addWidget(self._delete_btn)

        detail_layout.addLayout(detail_header)

        # -- Request info row (method badge + URL) -------------------------
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

    # -- Tab construction helpers --------------------------------------

    def _build_headers_tab(self) -> None:
        """Construct the Headers tab."""
        editor, empty, _ = self._build_readonly_tab("Headers", "No response headers")
        self._headers_edit = editor
        self._headers_empty_label = empty

    def _build_request_headers_tab(self) -> None:
        """Construct the Request Headers tab."""
        editor, empty, _ = self._build_readonly_tab("Request Headers", "No request headers")
        self._req_headers_edit = editor
        self._req_headers_empty_label = empty

    def _build_request_body_tab(self) -> None:
        """Construct the Request Body tab with Pretty/Raw combo."""
        editor, empty, combo = self._build_readonly_tab(
            "Request Body",
            "No request body",
            view_combo=True,
        )
        self._req_body_edit = editor
        self._req_body_empty_label = empty
        assert combo is not None
        self._req_body_view_combo = combo
        self._req_body_view_combo.currentTextChanged.connect(self._refresh_request_body_view)

    def _build_readonly_tab(
        self,
        title: str,
        empty_text: str,
        *,
        view_combo: bool = False,
    ) -> tuple[CodeEditorWidget, QLabel, QComboBox | None]:
        """Build a read-only tab with optional Pretty/Raw combo."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(6)
        combo: QComboBox | None = None
        if view_combo:
            combo = QComboBox()
            combo.addItems(["Pretty", "Raw"])
            combo.setFixedWidth(90)
            toolbar.addWidget(combo)
        toolbar.addStretch()
        editor = CodeEditorWidget(read_only=True)
        copy_btn = self._make_copy_btn(lambda e=editor: self._copy_editor(e))
        toolbar.addWidget(copy_btn)
        layout.addLayout(toolbar)
        empty_label = self._make_empty_label(empty_text)
        layout.addWidget(empty_label, 1)
        layout.addWidget(editor, 1)
        self._detail_tabs.addTab(tab, title)
        return editor, empty_label, combo

    # -- Public API ----------------------------------------------------

    def set_request_context(self, request_id: int | None, request_name: str | None) -> None:
        """Set the active request context shown in the panel header."""
        if request_id != self._request_id:
            self._current_response_id = None
        self._request_id = request_id
        self._request_name = request_name or ""
        self._subtitle_label.setText(self._request_name)

    def set_live_response_available(self, available: bool) -> None:
        """Enable or disable the Save Current action."""
        self._save_current_btn.setEnabled(available and self._request_id is not None)

    def show_request_required_state(self, message: str) -> None:
        """Show a contextual empty state when saved responses are unavailable."""
        self._state_label.setText(message)
        self._state_label.show()
        self._content_splitter.hide()
        self._set_detail_enabled(False)
        self._save_current_btn.setEnabled(False)
        self._refresh_btn.setEnabled(False)

    def show_empty_examples_state(self) -> None:
        """Show the empty state for a persisted request with no examples."""
        self._state_label.setText(
            "No saved responses for this request.\n\n"
            "Save the next live response to keep an example here."
        )
        self._state_label.show()
        self._content_splitter.hide()
        self._set_detail_enabled(False)
        self._refresh_btn.setEnabled(self._request_id is not None)

    def set_saved_responses(self, items: list[SavedResponseDict]) -> None:
        """Populate the list and detail pane with saved response items."""
        self._items = items
        self._items_by_id = {item["id"]: item for item in items}
        self._refresh_btn.setEnabled(self._request_id is not None)
        self._list_widget.clear()

        if not items:
            self._current_response_id = None
            self.show_empty_examples_state()
            return

        for item in items:
            row = QListWidgetItem()
            row.setData(Qt.ItemDataRole.UserRole, item["id"])
            row.setData(ROLE_RESPONSE_CODE, item["code"])
            row.setData(ROLE_RESPONSE_NAME, item["name"])
            row.setData(ROLE_RESPONSE_META, build_row_meta(item))
            row.setToolTip(item["name"])
            self._list_widget.addItem(row)

        self._state_label.hide()
        self._content_splitter.show()
        self._select_response(self._current_response_id or items[0]["id"])

    def select_response(self, response_id: int) -> None:
        """Select a saved response by ID if it exists in the current list."""
        self._select_response(response_id)

    def clear(self) -> None:
        """Reset the panel to its no-request state."""
        self._request_id = None
        self._request_name = ""
        self._subtitle_label.setText("")
        self._items = []
        self._items_by_id = {}
        self._current_response_id = None
        self._list_widget.clear()
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
        self._detail_name.setText("Select a saved response")
        self._detail_meta.setText("")
        self._reset_search_filter()
        self.show_request_required_state("Open a saved request to browse its saved responses.")

    # -- Private helpers -----------------------------------------------

    def _select_response(self, response_id: int | None) -> None:
        """Select the matching item in the list and populate the detail pane."""
        if response_id is None:
            self._set_detail_enabled(False)
            return
        for index in range(self._list_widget.count()):
            item = self._list_widget.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == response_id:
                self._list_widget.setCurrentRow(index)
                self._populate_detail(self._items_by_id[response_id])
                return
        # Requested ID not in list — fall back to first item
        if self._list_widget.count() > 0:
            first = self._list_widget.item(0)
            first_id = first.data(Qt.ItemDataRole.UserRole)
            self._list_widget.setCurrentRow(0)
            if isinstance(first_id, int) and first_id in self._items_by_id:
                self._populate_detail(self._items_by_id[first_id])
                return
        self._set_detail_enabled(False)

    def _on_selection_changed(self) -> None:
        """Update the detail pane when the list selection changes."""
        item = self._list_widget.currentItem()
        if item is None:
            self._current_response_id = None
            self._set_detail_enabled(False)
            return
        response_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(response_id, int):
            self._set_detail_enabled(False)
            return
        self._current_response_id = response_id
        detail = self._items_by_id.get(response_id)
        if detail is not None:
            self._populate_detail(detail)

    def _populate_detail(self, item: SavedResponseDict) -> None:
        """Render the selected saved response in the detail pane."""
        code = item["code"]
        status = item["status"] or ""

        # 1. Status badge
        badge_text = str(code) if code is not None else "\u2014"
        colour = status_color(code)
        self._status_badge.setText(badge_text)
        self._status_badge.setStyleSheet(
            f"background: {colour}; color: #ffffff; "
            f"padding: 2px 8px; border-radius: 3px; "
            f"font-weight: bold; font-size: 11px;"
        )

        # 2. Name and enriched metadata
        self._detail_name.setText(item["name"])
        meta_parts: list[str] = []
        if status:
            meta_parts.append(status)
        if item["created_at"]:
            meta_parts.append(item["created_at"])
        if item["preview_language"]:
            meta_parts.append(item["preview_language"].upper())
        if item["body_size"]:
            meta_parts.append(format_body_size(item["body_size"]))
        self._detail_meta.setText(" \u00b7 ".join(meta_parts))

        # 3. Body tab — reset search/filter, then render
        self._reset_search_filter()
        self._body_raw_text = item["body"] or ""
        self._body_language = (
            item["preview_language"] or detect_body_language(item["body"] or "") or "text"
        )
        self._set_combo_text(self._body_view_combo, self._body_view_mode)
        self._refresh_body_view()

        # 4. Headers tab
        headers_text = format_headers(item["headers"])
        if headers_text:
            self._headers_empty_label.hide()
            self._headers_edit.show()
            self._headers_edit.set_language("text")
            self._headers_edit.set_text(headers_text)
        else:
            self._headers_edit.hide()
            self._headers_empty_label.show()

        # 5. Request info row (method + URL)
        snapshot = item["original_request"]
        self._snapshot_raw_data = snapshot
        req_method = extract_snapshot_method(snapshot)
        req_url = extract_snapshot_url(snapshot)
        if req_method or req_url:
            self._request_method_badge.setText(req_method)
            colour = method_color(req_method)
            self._request_method_badge.setStyleSheet(
                f"background: {colour}; color: #ffffff; "
                f"padding: 1px 6px; border-radius: 3px; "
                f"font-weight: bold; font-size: 10px;"
            )
            self._request_url_label.setText(req_url)
            self._request_url_label.setToolTip(req_url)
            self._request_info_widget.show()
        else:
            self._request_info_widget.hide()

        # 6. Request Headers tab
        req_headers_text = extract_snapshot_headers(snapshot)
        if req_headers_text:
            self._req_headers_empty_label.hide()
            self._req_headers_edit.show()
            self._req_headers_edit.set_language("text")
            self._req_headers_edit.set_text(req_headers_text)
        else:
            self._req_headers_edit.hide()
            self._req_headers_empty_label.show()

        # 7. Request Body tab
        req_body, req_body_lang = extract_snapshot_body(snapshot)
        self._req_body_raw_text = req_body
        self._req_body_language = req_body_lang
        self._set_combo_text(self._req_body_view_combo, self._req_body_view_mode)
        self._refresh_request_body_view()

        self._set_detail_enabled(True)

    def _set_detail_enabled(self, enabled: bool) -> None:
        """Enable or disable detail actions and tabs."""
        self._detail_tabs.setEnabled(enabled)
        self._rename_btn.setEnabled(enabled)
        self._duplicate_btn.setEnabled(enabled)
        self._delete_btn.setEnabled(enabled)

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

    def _emit_signal(self, signal: SignalInstance) -> None:
        """Emit *signal* with the current response id, if one is selected."""
        if self._current_response_id is not None:
            signal.emit(self._current_response_id)

    def _copy_editor(self, editor: CodeEditorWidget) -> None:
        """Copy the given editor's text to the system clipboard."""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(editor.toPlainText())

    def _refresh_body_view(self, _mode: str | None = None) -> None:
        """Render the saved response body using the selected view mode."""
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

        # Re-apply active filter if one exists
        if self._is_filtered and self._filter_expression:
            self._run_filter(self._filter_expression, body_text)
            return

        self._body_edit.set_text(body_text)

    def _refresh_request_body_view(self, _mode: str | None = None) -> None:
        """Render the saved request body using the selected view mode."""
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
