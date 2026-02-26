"""Reusable key-value table editor for request parameters and headers.

Provides a ``KeyValueTableWidget`` showing editable rows of key-value
pairs with an enable/disable checkbox and description column.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.theme import COLOR_ACCENT, COLOR_BORDER, COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_WHITE

# Column indices
_COL_ENABLED = 0
_COL_KEY = 1
_COL_VALUE = 2
_COL_DESCRIPTION = 3

_COLUMN_COUNT = 4


class KeyValueTableWidget(QWidget):
    """Editable key-value table with enable checkboxes.

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
        """Initialise the key-value table with default empty row."""
        super().__init__(parent)
        self._placeholder_key = placeholder_key
        self._placeholder_value = placeholder_value
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._table = QTableWidget(0, _COLUMN_COUNT)
        self._table.setHorizontalHeaderLabels(["", "Key", "Value", "Description"])
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
        self._table.setColumnWidth(_COL_ENABLED, 30)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setStyleSheet(
            f"""
            QTableWidget {{
                background: {COLOR_WHITE};
                border: 1px solid {COLOR_BORDER};
                gridline-color: {COLOR_BORDER};
                color: {COLOR_TEXT};
            }}
            QHeaderView::section {{
                background: {COLOR_WHITE};
                border: none;
                border-bottom: 1px solid {COLOR_BORDER};
                padding: 4px;
                font-size: 11px;
                color: {COLOR_TEXT_MUTED};
            }}
            """
        )
        self._table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self._table, 1)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        add_btn = QPushButton("+ Add")
        add_btn.setStyleSheet(
            f"padding: 3px 10px; font-size: 11px; color: {COLOR_ACCENT};"
            " border: none; background: transparent;"
        )
        add_btn.clicked.connect(self.add_empty_row)
        btn_row.addWidget(add_btn)

        self._remove_btn = QPushButton("- Remove")
        self._remove_btn.setStyleSheet(
            f"padding: 3px 10px; font-size: 11px; color: {COLOR_TEXT_MUTED};"
            " border: none; background: transparent;"
        )
        self._remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(self._remove_btn)

        # Bulk actions
        self._bulk_label = QLabel("")
        self._bulk_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
        btn_row.addWidget(self._bulk_label)
        btn_row.addStretch()

        layout.addLayout(btn_row)

        # Start with one empty row
        self.add_empty_row()

    # -- Public API ----------------------------------------------------

    def add_empty_row(self) -> None:
        """Append a new empty row at the bottom of the table."""
        self._insert_row(self._table.rowCount(), "", "", "", enabled=True)

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
            # Always have at least one empty row
            if self._table.rowCount() == 0:
                self.add_empty_row()
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
        """Return the number of rows (including empty ones)."""
        return self._table.rowCount()

    # -- Internal helpers ----------------------------------------------

    def _insert_row(
        self,
        row: int,
        key: str,
        value: str,
        description: str,
        *,
        enabled: bool = True,
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

    def _remove_selected(self) -> None:
        """Remove the currently selected rows."""
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()}, reverse=True)
        for row in rows:
            self._table.removeRow(row)
        if self._table.rowCount() == 0:
            self.add_empty_row()
        self.data_changed.emit()

    def _on_cell_changed(self, _row: int, _col: int) -> None:
        """Forward cell edits as data_changed signal."""
        if not self._updating:
            self.data_changed.emit()

    def _on_checkbox_changed(self) -> None:
        """Forward checkbox toggles as data_changed signal."""
        if not self._updating:
            self.data_changed.emit()
