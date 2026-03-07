"""Reusable key-value table editor for request parameters and headers.

Provides a ``KeyValueTableWidget`` showing editable rows of key-value
pairs with an enable/disable checkbox, description column, and
inline per-row delete buttons.

Variable references (``{{name}}``) are highlighted with an orange
background so they stand out at a glance.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import (QEvent, QModelIndex, QObject,
                            QPersistentModelIndex, QPoint, QRect, Qt, QTimer,
                            Signal)
from PySide6.QtGui import (QColor, QFontMetrics, QHelpEvent, QMouseEvent,
                           QPainter)
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QHBoxLayout,
                               QHeaderView, QPushButton, QStyledItemDelegate,
                               QStyleOptionViewItem, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

if TYPE_CHECKING:
    from services.environment_service import VariableDetail

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

# Regex for {{variable}} references
_VAR_RE = re.compile(r"\{\{(.+?)\}\}")

# Padding (px) around the highlight box
_HIGHLIGHT_PAD_X = 2
_HIGHLIGHT_PAD_Y = 1
_HIGHLIGHT_RADIUS = 3


class _VariableHighlightDelegate(QStyledItemDelegate):
    """Delegate that highlights ``{{variable}}`` patterns with a coloured background.

    Only columns listed in *highlight_columns* are processed; other
    columns fall through to the default paint implementation.
    """

    def __init__(
        self,
        highlight_columns: set[int],
        parent: QWidget | None = None,
    ) -> None:
        """Initialise with the set of column indices to highlight."""
        super().__init__(parent)
        self._columns = highlight_columns
        self._variable_map: dict[str, VariableDetail] = {}

    def set_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Update the variable resolution map for tooltips."""
        self._variable_map = variables

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint the cell, overlaying variable highlights when present."""
        # For columns we don't care about, defer to default
        if index.column() not in self._columns:
            super().paint(painter, option, index)
            return

        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text or "{{" not in text:
            super().paint(painter, option, index)
            return

        # 1. Let the base class draw selection/focus/background
        # We draw the text ourselves, so clear it temporarily
        self.initStyleOption(option, index)
        option.text = ""
        style = option.widget.style() if option.widget else None
        if style:
            style.drawControl(
                style.ControlElement.CE_ItemViewItem,
                option,
                painter,
                option.widget,
            )

        # 2. Compute text area
        text_rect = option.rect.adjusted(4, 0, -4, 0)  # small left/right margin

        painter.save()
        painter.setClipRect(text_rect)

        fm = QFontMetrics(option.font)
        y_center = text_rect.top() + (text_rect.height() + fm.ascent() - fm.descent()) // 2

        # Resolve highlight colour at paint time so theme changes apply
        from ui.theme import (COLOR_VARIABLE_HIGHLIGHT,
                              COLOR_VARIABLE_UNRESOLVED_HIGHLIGHT,
                              COLOR_VARIABLE_UNRESOLVED_TEXT, COLOR_WARNING)

        hl_bg = QColor(COLOR_VARIABLE_HIGHLIGHT)
        hl_fg = QColor(COLOR_WARNING)
        unresolved_bg = QColor(COLOR_VARIABLE_UNRESOLVED_HIGHLIGHT)
        unresolved_fg = QColor(COLOR_VARIABLE_UNRESOLVED_TEXT)

        # 3. Walk through the text, painting normal and highlighted spans
        x = text_rect.left()
        pos = 0
        full_text: str = text
        for match in _VAR_RE.finditer(full_text):
            # Normal text before the match
            if match.start() > pos:
                normal = full_text[pos : match.start()]
                painter.setPen(option.palette.color(option.palette.ColorRole.Text))
                painter.drawText(x, y_center, normal)
                x += fm.horizontalAdvance(normal)
            # Highlighted variable reference
            var_name = match.group(1)
            resolved = var_name in self._variable_map
            var_text = match.group(0)
            var_w = fm.horizontalAdvance(var_text)
            bg_rect = QRect(
                x - _HIGHLIGHT_PAD_X,
                text_rect.top() + (text_rect.height() - fm.height()) // 2 - _HIGHLIGHT_PAD_Y,
                var_w + 2 * _HIGHLIGHT_PAD_X,
                fm.height() + 2 * _HIGHLIGHT_PAD_Y,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(hl_bg if resolved else unresolved_bg)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.drawRoundedRect(bg_rect, _HIGHLIGHT_RADIUS, _HIGHLIGHT_RADIUS)
            painter.setPen(hl_fg if resolved else unresolved_fg)
            painter.drawText(x, y_center, var_text)
            x += var_w
            pos = match.end()
        # Trailing normal text
        if pos < len(full_text):
            painter.setPen(option.palette.color(option.palette.ColorRole.Text))
            painter.drawText(x, y_center, full_text[pos:])

        painter.restore()

    def helpEvent(
        self,
        event: QHelpEvent,
        view: QAbstractItemView,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """Suppress default tooltip for variable cells."""
        if event.type() == QEvent.Type.ToolTip and index.column() in self._columns:
            text = index.data(Qt.ItemDataRole.DisplayRole)
            if text and "{{" in text:
                return True  # swallow — popup is handled by mouse tracking
        return super().helpEvent(event, view, option, index)

    def var_at_pos(
        self,
        pos: QMouseEvent,
        view: QAbstractItemView,
    ) -> str | None:
        """Return the variable name at pixel *pos*, or ``None``.

        Called by the parent widget's event filter to implement fast
        mouse-tracking-based variable popup display.
        """
        mouse_pos = pos.position().toPoint()
        index = view.indexAt(mouse_pos)
        if not index.isValid() or index.column() not in self._columns:
            return None
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text or "{{" not in text:
            return None

        option = QStyleOptionViewItem()
        self.initStyleOption(option, index)
        option.rect = view.visualRect(index)
        text_rect = option.rect.adjusted(4, 0, -4, 0)
        fm = QFontMetrics(option.font)
        mouse_x = mouse_pos.x()

        x = text_rect.left()
        char_pos = 0
        for match in _VAR_RE.finditer(text):
            if match.start() > char_pos:
                x += fm.horizontalAdvance(text[char_pos : match.start()])
            var_w = fm.horizontalAdvance(match.group(0))
            if x <= mouse_x <= x + var_w:
                return match.group(1)
            x += var_w
            char_pos = match.end()

        return None


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

        # Highlight {{variable}} references in key and value columns
        self._highlight_delegate = _VariableHighlightDelegate(
            {_COL_KEY, _COL_VALUE},
            self._table,
        )
        self._table.setItemDelegate(self._highlight_delegate)

        layout.addWidget(self._table, 1)

        # Hover tracking for fast variable popup display
        self._var_hover_name: str | None = None
        self._var_hover_timer = QTimer(self)
        self._var_hover_timer.setSingleShot(True)
        self._var_hover_timer.timeout.connect(self._show_var_hover_popup)
        self._var_hover_global_pos = QPoint()

        # Start with one ghost row
        self._append_ghost_row()

    # -- Public API ----------------------------------------------------

    def set_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Update the variable resolution map for tooltip display."""
        self._highlight_delegate.set_variable_map(variables)
        self._table.viewport().update()

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
        """Track mouse hover for delete buttons and variable popups."""
        if obj is self._table.viewport():
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
                        from ui.variable_popup import VariablePopup

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
        from ui.variable_popup import VariablePopup

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
