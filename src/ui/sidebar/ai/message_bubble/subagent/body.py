"""Expandable activity body for a Cursor-style subagent card."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from services.ai.chat.subagent_events import SubagentActivityStep
from ui.styling.icons import phi


class SubagentCardBody(QWidget):
    """Vertical list of step summaries and optional monospace output blocks."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an empty step list hidden until steps are applied."""
        super().__init__(parent)
        self.setObjectName("aiChatSubagentCardBody")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 0, 8, 8)
        self._layout.setSpacing(6)
        self.hide()

    def set_steps(self, steps: list[SubagentActivityStep]) -> None:
        """Replace all step rows from *steps*."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        if not steps:
            self.hide()
            return
        for step in steps:
            self._layout.addWidget(_SubagentStepRow(step, self))
        self.show()

    def has_steps(self) -> bool:
        """Return whether any steps are shown."""
        return self._layout.count() > 0


class _SubagentStepRow(QWidget):
    """One summary line plus an optional dark output block."""

    def __init__(self, step: SubagentActivityStep, parent: QWidget | None = None) -> None:
        """Render *step* as a Cursor-style activity row."""
        super().__init__(parent)
        self.setObjectName("aiChatSubagentStep")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        icon = QLabel()
        icon.setObjectName("aiChatSubagentStepIcon")
        icon_name = step.get("icon") or "circle"
        icon.setPixmap(phi(icon_name, size=12).pixmap(12, 12))
        icon.setFixedSize(14, 14)
        row_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        summary = QLabel(step["summary"])
        summary.setObjectName("aiChatSubagentStepSummary")
        summary.setWordWrap(True)
        row_layout.addWidget(summary, 1)
        layout.addWidget(row)

        detail = step.get("detail", "")
        if detail:
            block = QLabel(detail)
            block.setObjectName("aiChatSubagentOutputBlock")
            block.setWordWrap(True)
            block.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(block)


__all__ = ["SubagentCardBody"]
