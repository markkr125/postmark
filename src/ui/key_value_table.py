"""Reusable key-value table editor for request parameters and headers.

Provides a ``KeyValueTableWidget`` showing editable rows of key-value
pairs with an enable/disable checkbox, description column, and
inline per-row delete buttons.
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.icons import phi

# Column indices
_COL_ENABLED = 0
_COL_KEY = 1
_COL_VALUE = 2
_COL_DESCRIPTION = 3
_COL_DELETE = 4

_COLUMN_COUNT = 5

# Width (px) for the narrow delete-button column
_DELETE_COL_WIDTH = 28


class KeyValueTableWidget(QWidget):
    """Editable key-value table with enable checkboxes and inline delete.

    A ghost row is always present at the bottom.  When the user types
    into the ghost row a new ghost is appended automatically.  Each
    non-ghost row shows a small delete button on hover.

    Signals:
        data_changed(): Emitted when any cell value or checkbox changes.
    """

    data_changed = Signal()

    def __init__(
        self,
        *,
        placeholder_key: str = "Key",
        placeholder_value: str = "Value",
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the key-value table with one ghost row."""
        super().__init__(parent)
        self._placeholder_key = placeholder_key
        self._placeholder_value = placeholder_value
        self._updating = False
        # Row index currently hovered (-1 = none)
        self._hovered_row: int = -1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = QTableWidget(0, _COLUMN_COUNT)
        self._table.setHorizontalHeaderLabels(["", "Key", "Value", "Description", ""])
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_KEY, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_VALUE, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_DESCRIPTION, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_ENABLED, QHeaderView.ResizeMode.Fixed
        )
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_DELETE, QHeaderView.ResizeMode.Fixed
        )
        self._table.setColumnWidth(_COL_ENABLED, 30)
        self._table.setColumnWidth(_COL_DELETE, _DELETE_COL_WIDTH)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setMouseTracking(True)
        self._table.cellChanged.connect(self._on_cell_changed)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._table.viewport().installEventFilter(self)
        layout.addWidget(self._table, 1)

        # Start with one ghost row
        self._append_ghost_row()

    # -- Public API ----------------------------------------------------

    def add_empty_row(self) -> None:
        """Append a new empty row before the ghost row."""
        ghost = self._table.rowCount() - 1
        if ghost < 0:
            ghost = 0
        self._insert_row(ghost, "", "", "", enabled=True)

    def set_data(self, rows: list[dict]) -> None:
        """Populate the table from a list of row dicts.

        Each dict should have ``key``, ``value``, and optionally
        ``description`` and ``enabled``.
        """
        self._updating = True
        try:
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

    def get_data(self) -> list[dict]:
        """Return the table data as a list of row dicts.

        Only includes rows that have a non-empty key.
        """
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
        """Return the number of rows (including the ghost row)."""
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
        """Track mouse hover over the table viewport to show delete buttons."""
        if obj is self._table.viewport():
            if event.type() == QEvent.Type.MouseMove:
                mouse_event = cast(QMouseEvent, event)
                pos = mouse_event.position().toPoint()
                row = self._table.rowAt(pos.y())
                if row != self._hovered_row:
                    self._hovered_row = row
                    self._update_delete_button_visibility()
            elif event.type() == QEvent.Type.Leave:
                self._hovered_row = -1
                self._update_delete_button_visibility()
        return super().eventFilter(obj, event)

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
