"""Enter-key open filter for global history tree rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QTreeWidget

from ui.sidebar.history.delegate import ROLE_HISTORY_IS_DATE_GROUP

if TYPE_CHECKING:
    from ui.sidebar.history.panel import HistoryPanel


class _HistoryTreeOpenFilter(QObject):
    """Emit open requests when Enter is pressed on a send row in the history tree."""

    def __init__(self, panel: HistoryPanel, tree: QTreeWidget) -> None:
        super().__init__(tree)
        self._panel = panel
        self._tree = tree

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Handle Return/Enter on a focused send row."""
        if watched is not self._tree or event.type() != QEvent.Type.KeyPress:
            return False
        if not isinstance(event, QKeyEvent):
            return False
        key = event.key()
        if key not in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return False
        item = self._tree.currentItem()
        if item is None or item.data(0, ROLE_HISTORY_IS_DATE_GROUP):
            return False
        entry_id = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(entry_id, int):
            self._panel._emit_entry_open(entry_id)
            return True
        return False
