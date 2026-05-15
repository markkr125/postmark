"""Reusable key-value table editor for request parameters and headers.

Provides a ``KeyValueTableWidget`` showing editable rows of key-value
pairs with an enable/disable checkbox, description column, and
inline per-row delete buttons.  Key and Value columns are user-resizable;
Description grows with the table width (remaining space after Key/Value).

Variable references (``{{name}}``) are highlighted with an orange
background so they stand out at a glance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from services.environment_service import VariableDetail

from shiboken6 import Shiboken

from ui.styling.icons import phi
from ui.widgets.key_value_bulk import BULK_PLACEHOLDER, parse_bulk_text, serialize_for_bulk
from ui.widgets.key_value_table_delegate import _VariableHighlightDelegate

# Column indices
_COL_ENABLED = 0
_COL_KEY = 1
_COL_VALUE = 2
_COL_DESCRIPTION = 3
_COL_DELETE = 4

_COLUMN_COUNT = 5

# Width (px) for the narrow delete-button column (body rows)
_DELETE_COL_WIDTH = 28
# Extra width when the delete header hosts the Bulk link control
_BULK_HEADER_BTN_PADDING = 10

# Default Key / Value column widths (Description is stretch; larger defaults
# leave less horizontal space for Description until the user resizes).
_DEFAULT_KEY_COL_WIDTH = 220
_DEFAULT_VALUE_COL_WIDTH = 520

# Height (px) of the bulk-mode strip above the text editor (table-header feel)
_BULK_PAGE_HEADER_HEIGHT = 32

_PAGE_TABLE = 0
_PAGE_BULK = 1


class KeyValueTableWidget(QWidget):
    """Editable key-value table with enable checkboxes and inline delete.

    A ghost row is always present at the bottom.  When the user types
    into the ghost row a new ghost is appended automatically.  Each
    non-ghost row shows a small delete button on hover.

    Optional *settings_profile* persists Key/Value column widths under a
    shared QSettings JSON key (``ui/kv_col_widths``) so each usage context
    (for example ``params`` vs ``headers``) keeps its own remembered sizes.

    Signals:
        data_changed(): Emitted when any cell value or checkbox changes.
    """

    data_changed = Signal()

    def __init__(
        self,
        *,
        placeholder_key: str = "Key",
        placeholder_value: str = "Value",
        settings_profile: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the key-value table with one ghost row."""
        super().__init__(parent)
        self._placeholder_key = placeholder_key
        self._placeholder_value = placeholder_value
        self._settings_profile = settings_profile
        self._updating = False
        # Row index currently hovered (-1 = none)
        self._hovered_row: int = -1

        layout = QVBoxLayout(self)
        # 1px breathing room below the QTabBar baseline (Params / Headers / …).
        layout.setContentsMargins(0, 1, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)

        # -- Table page (grid; bulk control is overlaid on the header) ------
        table_page = QWidget()
        table_page_layout = QVBoxLayout(table_page)
        table_page_layout.setContentsMargins(0, 0, 0, 0)
        table_page_layout.setSpacing(0)

        self._table = QTableWidget(0, _COLUMN_COUNT)
        self._table.setObjectName("keyValueTable")
        # Native frame + global QSS border both draw an edge — keep QSS only.
        self._table.setFrameShape(QFrame.Shape.NoFrame)
        self._table.setHorizontalHeaderLabels(["", "Key", "Value", "Description", ""])
        self._horizontal_header = self._table.horizontalHeader()
        header = self._horizontal_header
        # Checkbox + trash stay fixed; Key/Value are user-resizable; Description
        # stretches so extra table width still lands in the notes column.
        header.setMinimumSectionSize(48)
        header.setSectionResizeMode(_COL_ENABLED, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(_COL_KEY, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_VALUE, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_DESCRIPTION, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_DELETE, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_ENABLED, 30)
        self._table.setColumnWidth(_COL_KEY, _DEFAULT_KEY_COL_WIDTH)
        self._table.setColumnWidth(_COL_VALUE, _DEFAULT_VALUE_COL_WIDTH)

        self._bulk_enter_btn = QPushButton("Bulk")
        self._bulk_enter_btn.setObjectName("keyValueBulkEnter")
        self._bulk_enter_btn.setIcon(phi("list-dashes"))
        self._bulk_enter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bulk_enter_btn.clicked.connect(self._on_bulk_enter_clicked)
        delete_header_w = max(
            _DELETE_COL_WIDTH,
            self._bulk_enter_btn.sizeHint().width() + _BULK_HEADER_BTN_PADDING,
        )
        self._table.setColumnWidth(_COL_DELETE, delete_header_w)

        if settings_profile is not None:
            from ui.widgets.key_value_column_widths import load_column_widths

            key_w, val_w = load_column_widths(
                settings_profile,
                _DEFAULT_KEY_COL_WIDTH,
                _DEFAULT_VALUE_COL_WIDTH,
            )
            header.blockSignals(True)
            self._table.setColumnWidth(_COL_KEY, key_w)
            self._table.setColumnWidth(_COL_VALUE, val_w)
            header.blockSignals(False)

        header.sectionResized.connect(self._on_header_section_resized)
        header.geometriesChanged.connect(self._position_bulk_header_button)
        header.installEventFilter(self)
        self._bulk_header_position_timer = QTimer(self)
        self._bulk_header_position_timer.setSingleShot(True)
        self._bulk_header_position_timer.timeout.connect(self._position_bulk_header_button)
        self._persist_width_timer = QTimer(self)
        self._persist_width_timer.setSingleShot(True)
        self._persist_width_timer.setInterval(250)
        self._persist_width_timer.timeout.connect(self._persist_column_widths)

        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setMouseTracking(True)
        self._table.cellChanged.connect(self._on_cell_changed)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._table.viewport().installEventFilter(self)

        # Highlight {{variable}} references in key and value columns
        self._highlight_delegate = _VariableHighlightDelegate(
            {_COL_KEY, _COL_VALUE},
            self._table,
        )
        self._table.setItemDelegate(self._highlight_delegate)

        self._bulk_enter_btn.setParent(header)
        self._bulk_enter_btn.show()

        table_page_layout.addWidget(self._table, 1)

        bulk_page = QWidget()
        bulk_layout = QVBoxLayout(bulk_page)
        bulk_layout.setContentsMargins(0, 0, 0, 0)
        bulk_layout.setSpacing(0)

        self._bulk_page_header = QFrame()
        self._bulk_page_header.setObjectName("keyValueBulkPageHeader")
        self._bulk_page_header.setFixedHeight(_BULK_PAGE_HEADER_HEIGHT)
        bulk_header_inner = QHBoxLayout(self._bulk_page_header)
        bulk_header_inner.setContentsMargins(8, 0, 8, 0)
        bulk_header_inner.setSpacing(8)
        bulk_header_inner.addStretch()
        self._bulk_back_btn = QPushButton("Key-value edit")
        self._bulk_back_btn.setObjectName("flatAccentButton")
        self._bulk_back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bulk_back_btn.clicked.connect(self._on_bulk_back_clicked)
        bulk_header_inner.addWidget(self._bulk_back_btn)
        bulk_layout.addWidget(self._bulk_page_header)

        self._bulk_text = QTextEdit()
        self._bulk_text.setObjectName("keyValueBulkEdit")
        self._bulk_text.setPlaceholderText(BULK_PLACEHOLDER)
        self._bulk_text.setAcceptRichText(False)
        bulk_layout.addWidget(self._bulk_text, 1)

        self._stack.addWidget(table_page)
        self._stack.addWidget(bulk_page)

        # Hover tracking for fast variable popup display
        self._var_hover_name: str | None = None
        self._var_hover_timer = QTimer(self)
        self._var_hover_timer.setSingleShot(True)
        self._var_hover_timer.timeout.connect(self._show_var_hover_popup)
        self._var_hover_global_pos = QPoint()

        # Start with one ghost row
        self._append_ghost_row()
        self._bulk_header_position_timer.start(0)

    def showEvent(self, event: QShowEvent) -> None:
        """Re-align the header bulk control after the widget is shown."""
        super().showEvent(event)
        if Shiboken.isValid(self):
            self._position_bulk_header_button()

    def _position_bulk_header_button(self) -> None:
        """Place the *Bulk* link on the right edge of the delete-column header."""
        if not Shiboken.isValid(self):
            return
        header = self._horizontal_header
        btn = self._bulk_enter_btn
        if not Shiboken.isValid(header) or not Shiboken.isValid(btn):
            return
        if btn.parent() is not header or header.width() <= 0:
            return
        x = header.sectionPosition(_COL_DELETE)
        w = header.sectionSize(_COL_DELETE)
        hint = btn.sizeHint()
        margin_h = 3
        margin_v = max(0, (header.height() - hint.height()) // 2)
        btn_w = min(hint.width(), max(24, w - 2 * margin_h))
        btn_h = min(hint.height(), max(16, header.height() - 2))
        btn.resize(btn_w, btn_h)
        btn.move(x + w - btn_w - margin_h, margin_v)
        btn.raise_()

    def _on_bulk_enter_clicked(self) -> None:
        """Show the Postman-style bulk text editor."""
        self._bulk_text.setPlainText(serialize_for_bulk(self.get_data()))
        self._stack.setCurrentIndex(_PAGE_BULK)
        self._bulk_text.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_bulk_back_clicked(self) -> None:
        """Apply bulk text to the table and return to the grid."""
        rows = parse_bulk_text(self._bulk_text.toPlainText())
        self.set_data(rows)
        self.data_changed.emit()

    def _on_header_section_resized(self, logical_index: int, _old: int, _new: int) -> None:
        """Debounce persisting Key/Value widths after a header drag."""
        self._position_bulk_header_button()
        if self._settings_profile is None:
            return
        if logical_index not in (_COL_KEY, _COL_VALUE):
            return
        self._persist_width_timer.start()

    def _persist_column_widths(self) -> None:
        """Write current Key/Value section sizes to QSettings."""
        if self._settings_profile is None:
            return
        from ui.widgets.key_value_column_widths import save_column_widths

        h = self._horizontal_header
        save_column_widths(
            self._settings_profile,
            h.sectionSize(_COL_KEY),
            h.sectionSize(_COL_VALUE),
        )

    # -- Public API ----------------------------------------------------

    def set_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Update the variable resolution map for tooltip display."""
        self._highlight_delegate.set_variable_map(variables)
        self._table.viewport().update()

    def add_empty_row(self) -> None:
        """Append a new empty row before the ghost row."""
        was_bulk = self._stack.currentIndex() == _PAGE_BULK
        if was_bulk:
            rows = parse_bulk_text(self._bulk_text.toPlainText())
            self.set_data(rows)
        ghost = self._table.rowCount() - 1
        if ghost < 0:
            ghost = 0
        self._insert_row(ghost, "", "", "", enabled=True)
        if was_bulk:
            self.data_changed.emit()

    def set_data(self, rows: list[dict]) -> None:
        """Populate the table from a list of row dicts.

        Each dict should have ``key``, ``value``, and optionally
        ``description`` and ``enabled``.
        """
        self._updating = True
        try:
            self._stack.setCurrentIndex(_PAGE_TABLE)
            self._table.setRowCount(0)
            for row in rows:
                self._insert_row(
                    self._table.rowCount(),
                    row.get("key", ""),
                    row.get("value", ""),
                    row.get("description", ""),
                    enabled=row.get("enabled", True),
                )
            # Always end with a ghost row
            self._append_ghost_row()
        finally:
            self._updating = False
        self._position_bulk_header_button()

    def get_data(self) -> list[dict]:
        """Return the table data as a list of row dicts.

        Only includes rows that have a non-empty key.
        When bulk-edit mode is active, rows are parsed from the bulk text.
        """
        if self._stack.currentIndex() == _PAGE_BULK:
            return parse_bulk_text(self._bulk_text.toPlainText())
        rows: list[dict] = []
        for r in range(self._table.rowCount()):
            key = self._cell_text(r, _COL_KEY)
            if not key:
                continue
            value = self._cell_text(r, _COL_VALUE)
            desc = self._cell_text(r, _COL_DESCRIPTION)
            enabled = self._is_row_enabled(r)
            row: dict = {"key": key, "value": value, "enabled": enabled}
            if desc:
                row["description"] = desc
            rows.append(row)
        return rows

    def to_text(self) -> str:
        """Serialize enabled rows to ``key=value`` or ``key: value`` text.

        Uses ``key: value`` for headers-style, ``key=value`` for params.
        This method uses ``: `` as the separator.
        """
        lines: list[str] = []
        for row in self.get_data():
            if row.get("enabled", True):
                lines.append(f"{row['key']}: {row['value']}")
        return "\n".join(lines)

    def from_text(self, text: str) -> None:
        """Parse ``key: value`` or ``key=value`` lines into the table."""
        rows: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if ": " in line:
                key, _, value = line.partition(": ")
            elif "=" in line:
                key, _, value = line.partition("=")
            else:
                key, value = line, ""
            rows.append({"key": key.strip(), "value": value.strip(), "enabled": True})
        self.set_data(rows)

    def row_count(self) -> int:
        """Return the number of rows (including the ghost row).

        In bulk-edit mode this is derived from the bulk text (one trailing
        ghost is approximated as ``len(rows) + 1``).
        """
        if self._stack.currentIndex() == _PAGE_BULK:
            n = len(parse_bulk_text(self._bulk_text.toPlainText()))
            return max(1, n + 1)
        return self._table.rowCount()

    # -- Ghost-row helpers ---------------------------------------------

    def _is_ghost_row(self, row: int) -> bool:
        """Return True if the row is the trailing ghost row."""
        return row == self._table.rowCount() - 1

    def _append_ghost_row(self) -> None:
        """Add a ghost row at the end of the table."""
        self._insert_row(self._table.rowCount(), "", "", "", enabled=True, ghost=True)

    def _promote_ghost(self, row: int) -> None:
        """Turn the ghost row into a real row and add a new ghost below."""
        self._update_delete_button_visibility()
        self._append_ghost_row()

    # -- Delete button -------------------------------------------------

    def _make_delete_button(self) -> QPushButton:
        """Create a small inline delete button for a row."""
        btn = QPushButton()
        btn.setIcon(phi("trash"))
        btn.setObjectName("rowDeleteButton")
        btn.setFixedSize(_DELETE_COL_WIDTH, 22)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.hide()
        btn.clicked.connect(self._on_delete_clicked)
        return btn

    def _on_delete_clicked(self) -> None:
        """Remove the row that owns the clicked delete button."""
        btn = self.sender()
        if btn is None:
            return
        for r in range(self._table.rowCount()):
            if self._table.cellWidget(r, _COL_DELETE) is btn:
                # Never delete the ghost row
                if self._is_ghost_row(r):
                    return
                self._table.removeRow(r)
                self._hovered_row = -1
                self._update_delete_button_visibility()
                self.data_changed.emit()
                return

    def _update_delete_button_visibility(self) -> None:
        """Show the delete button only on the hovered non-ghost row."""
        selected_rows = {idx.row() for idx in self._table.selectionModel().selectedRows()}
        for r in range(self._table.rowCount()):
            btn = self._table.cellWidget(r, _COL_DELETE)
            if isinstance(btn, QPushButton):
                show = r == self._hovered_row and not self._is_ghost_row(r)
                btn.setVisible(show)
                # Use white icon on selected rows so it stays visible
                # against the highlight background.
                if r in selected_rows:
                    btn.setIcon(phi("trash", color="#ffffff"))
                else:
                    btn.setIcon(phi("trash"))

    def _on_selection_changed(self) -> None:
        """Refresh delete-button icons when the selected row changes."""
        self._update_delete_button_visibility()

    # -- Event filter for hover tracking -------------------------------

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Track mouse hover for delete buttons and variable popups."""
        if obj is self._horizontal_header and event.type() == QEvent.Type.Resize:
            self._position_bulk_header_button()
        elif obj is self._table.viewport():
            if event.type() == QEvent.Type.MouseMove:
                mouse_event = cast(QMouseEvent, event)
                pos = mouse_event.position().toPoint()
                row = self._table.rowAt(pos.y())
                if row != self._hovered_row:
                    self._hovered_row = row
                    self._update_delete_button_visibility()

                # Variable hover tracking
                var_name = self._highlight_delegate.var_at_pos(mouse_event, self._table)
                if var_name:
                    if var_name != self._var_hover_name:
                        self._var_hover_name = var_name
                        self._var_hover_global_pos = mouse_event.globalPosition().toPoint()
                        from ui.widgets.variable_popup import VariablePopup

                        self._var_hover_timer.start(VariablePopup.hover_delay_ms())
                else:
                    if self._var_hover_name is not None:
                        self._var_hover_name = None
                        self._var_hover_timer.stop()

            elif event.type() == QEvent.Type.Leave:
                self._hovered_row = -1
                self._update_delete_button_visibility()
                self._var_hover_name = None
                self._var_hover_timer.stop()
        return super().eventFilter(obj, event)

    def _show_var_hover_popup(self) -> None:
        """Show the variable popup for the currently hovered variable."""
        if self._var_hover_name is None:
            return
        from ui.widgets.variable_popup import VariablePopup

        detail = self._highlight_delegate._variable_map.get(self._var_hover_name)
        VariablePopup.show_variable(
            self._var_hover_name,
            detail,
            self._var_hover_global_pos,
            self._table,
        )

    # -- Internal helpers ----------------------------------------------

    def _insert_row(
        self,
        row: int,
        key: str,
        value: str,
        description: str,
        *,
        enabled: bool = True,
        ghost: bool = False,
    ) -> None:
        """Insert a row at the given position."""
        self._table.blockSignals(True)
        try:
            self._table.insertRow(row)

            # Enabled checkbox
            cb = QCheckBox()
            cb.setChecked(enabled)
            cb.stateChanged.connect(self._on_checkbox_changed)
            container = QWidget()
            container.setObjectName("keyValueCheckCell")
            cb_layout = QHBoxLayout(container)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.addWidget(cb)
            self._table.setCellWidget(row, _COL_ENABLED, container)

            key_item = QTableWidgetItem(key)
            self._table.setItem(row, _COL_KEY, key_item)

            value_item = QTableWidgetItem(value)
            self._table.setItem(row, _COL_VALUE, value_item)

            desc_item = QTableWidgetItem(description)
            self._table.setItem(row, _COL_DESCRIPTION, desc_item)

            # Delete button (hidden by default; shown on hover)
            delete_btn = self._make_delete_button()
            self._table.setCellWidget(row, _COL_DELETE, delete_btn)
        finally:
            self._table.blockSignals(False)

    def _cell_text(self, row: int, col: int) -> str:
        """Return the text of a cell, or empty string."""
        item = self._table.item(row, col)
        return item.text().strip() if item else ""

    def _is_row_enabled(self, row: int) -> bool:
        """Return whether the checkbox for a row is checked."""
        container = self._table.cellWidget(row, _COL_ENABLED)
        if container is None:
            return True
        cb = container.findChild(QCheckBox)
        if cb is None:
            return True
        return cb.isChecked()

    def _on_cell_changed(self, row: int, _col: int) -> None:
        """Forward cell edits and auto-promote ghost rows."""
        if self._updating:
            return
        # If the user typed into the ghost row, promote it
        if self._is_ghost_row(row) and self._cell_text(row, _COL_KEY):
            self._promote_ghost(row)
        self.data_changed.emit()

    def _on_checkbox_changed(self) -> None:
        """Forward checkbox toggles as data_changed signal."""
        if not self._updating:
            self.data_changed.emit()
