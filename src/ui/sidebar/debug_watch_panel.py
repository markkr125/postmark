"""Watch expressions panel for the script debugger."""

from __future__ import annotations

from typing import TYPE_CHECKING

from shiboken6 import Shiboken
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.styling.icons import phi

if TYPE_CHECKING:
    from services.scripting.debug import DebugProtocol


class WatchPanel(QWidget):
    """Editable watch-expression list evaluated on each debug pause."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the watch list, add row, and remove controls."""
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 4, 12, 8)
        outer.setSpacing(4)

        title = QLabel("Watch")
        title.setObjectName("sidebarSectionLabel")
        outer.addWidget(title)

        self._list = QListWidget()
        self._list.setObjectName("debugWatchList")
        self._list.setAlternatingRowColors(True)
        outer.addWidget(self._list, 1)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Expression…")
        self._input.setObjectName("sidebarSearch")
        self._input.returnPressed.connect(self._add_expression)
        row.addWidget(self._input, 1)

        add_btn = QPushButton()
        add_btn.setIcon(phi("plus", size=14))
        add_btn.setToolTip("Add watch expression")
        add_btn.setObjectName("iconButton")
        add_btn.setFixedSize(28, 28)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_expression)
        row.addWidget(add_btn)

        rm_btn = QPushButton()
        rm_btn.setIcon(phi("trash", size=14))
        rm_btn.setToolTip("Remove selected watch")
        rm_btn.setObjectName("iconButton")
        rm_btn.setFixedSize(28, 28)
        rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rm_btn.clicked.connect(self._remove_selected)
        row.addWidget(rm_btn)

        outer.addLayout(row)
        self._protocol: DebugProtocol | None = None
        self._expressions: list[str] = []

    def set_protocol(self, protocol: DebugProtocol | None) -> None:
        """Attach the active :class:`DebugProtocol` (or ``None`` when idle)."""
        self._protocol = protocol

    def expressions(self) -> list[str]:
        """Return a copy of the current watch expressions."""
        return list(self._expressions)

    def clear_session(self) -> None:
        """Clear evaluated values but keep expressions."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item is not None:
                expr = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(expr, str):
                    item.setText(f"{expr}  =  —")

    def set_idle(self) -> None:
        """Reset to empty when debugging is not active."""
        self._protocol = None
        if Shiboken.isValid(self._list):
            self.clear_session()

    def refresh(self) -> None:
        """Re-evaluate every watch expression against the paused runtime."""
        protocol = self._protocol
        if protocol is None or protocol.state.value != "paused":
            return
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item is None:
                continue
            expr = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(expr, str) or not expr.strip():
                continue
            value = protocol.evaluate(expr.strip())
            item.setText(f"{expr}  =  {value}")

    def update_pause(self) -> None:
        """Alias for :meth:`refresh` — called when the debugger pauses."""
        self.refresh()

    def _add_expression(self) -> None:
        text = self._input.text().strip()
        if not text or text in self._expressions:
            self._input.clear()
            return
        self._expressions.append(text)
        item = QListWidgetItem(f"{text}  =  …")
        item.setData(Qt.ItemDataRole.UserRole, text)
        self._list.addItem(item)
        self._input.clear()
        self.changed.emit()
        self.refresh()

    def _remove_selected(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        item = self._list.takeItem(row)
        if item is None:
            return
        expr = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(expr, str) and expr in self._expressions:
            self._expressions.remove(expr)
        self.changed.emit()
