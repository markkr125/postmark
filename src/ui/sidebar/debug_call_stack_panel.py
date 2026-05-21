"""Call-stack panel for the script debugger."""

from __future__ import annotations

from shiboken6 import Shiboken
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from services.scripting.debug import CallFrame, DebugPauseInfo


class CallStackPanel(QWidget):
    """Lists stack frames for the current pause; emits selection changes."""

    frame_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the call-stack list widget."""
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 4, 12, 4)
        outer.setSpacing(4)

        title = QLabel("Call stack")
        title.setObjectName("sidebarSectionLabel")
        outer.addWidget(title)

        self._list = QListWidget()
        self._list.setObjectName("debugCallStackList")
        self._list.currentRowChanged.connect(self._on_row_changed)
        outer.addWidget(self._list)

        self._updating = False

    def update_pause(self, info: DebugPauseInfo) -> None:
        """Populate frames from a pause event."""
        self._updating = True
        self._list.clear()
        stack = info.get("call_stack") or []
        selected = int(info.get("selected_frame_index", 0))
        if isinstance(stack, list):
            for i, fr in enumerate(stack):
                if not isinstance(fr, dict):
                    continue
                cf = fr  # CallFrame-compatible dict
                label = _format_frame(cf, i)
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, i)
                self._list.addItem(item)
        if self._list.count() > 0:
            row = min(max(0, selected), self._list.count() - 1)
            self._list.setCurrentRow(row)
        self._updating = False

    def clear_session(self) -> None:
        """Clear the list when a session ends."""
        if not Shiboken.isValid(self._list):
            return
        self._updating = True
        self._list.clear()
        self._updating = False

    def set_idle(self) -> None:
        """Reset to empty when debugging is not active."""
        self.clear_session()

    def _on_row_changed(self, row: int) -> None:
        if self._updating or row < 0:
            return
        item = self._list.item(row)
        if item is None:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(idx, int):
            self.frame_selected.emit(idx)


def _format_frame(fr: CallFrame | dict[str, object], index: int) -> str:
    """Return a one-line label for a stack frame."""
    name = fr.get("name", "(anonymous)") if isinstance(fr, dict) else "(anonymous)"
    line_raw = fr.get("line", 0) if isinstance(fr, dict) else 0
    line = int(line_raw) if isinstance(line_raw, int) else 0
    return f"{index}: {name}  @ line {line + 1}"
