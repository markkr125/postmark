"""Compact inline tool-activity row in the assistant transcript.

Established IDEs converged on rendering each agent tool call as a single dense
line — a status icon, the tool icon, the name, a small muted detail, and the
duration — rather than a full-width bordered box. A run of calls reads as a
glanceable list instead of a wall of chrome; detail stays in the tooltip.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.ai.chat.tool_activity_events import ToolActivityRecord, ToolActivityStatus
from ui.styling.icons import phi
from ui.styling.theme import COLOR_DANGER, COLOR_SUCCESS
from ui.widgets.busy_spinner import BrailleSpinner

_STATUS_LABELS: dict[ToolActivityStatus, str] = {
    "pending_confirm": "Waiting",
    "running": "Running",
    "completed": "Completed",
    "error": "Failed",
    "rejected": "Rejected",
    "suppressed": "Done",
}

_TOOL_ICONS: dict[str, str] = {
    "postmark_workspace_query": "magnifying-glass",
    "postmark_datetime": "clock",
    "postmark_import": "download-simple",
    "postmark_workspace_import": "download-simple",
    "postmark_document_import": "file-text",
    "postmark_collection_draft": "folder-plus",
    "postmark_workspace_mutate": "pencil-simple",
    "postmark_workspace_execute": "paper-plane-right",
}

_TERMINAL_STATUSES = frozenset({"completed", "error", "rejected", "suppressed"})


def _format_duration(seconds: float | None) -> str:
    """Return a short inline duration such as ``1.2s``, or empty when unknown."""
    if seconds is None or seconds < 0:
        return ""
    return f"{seconds:.1f}s" if seconds < 60 else f"{seconds / 60:.1f}m"


def _ellipsize(text: str, label: QLabel) -> str:
    """Return *text* elided to one line of the chat's content width for the tooltip-free row."""
    # The row's fixed-height detail keeps the card to a single line; eliding to a
    # generous width keeps it readable while the tooltip carries the full string.
    width = max(200, label.width() or 400)
    return label.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, width)


class ToolActivityCard(QWidget):
    """One-line summary row for a single main-agent tool call."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build a hidden row until a record is applied."""
        super().__init__(parent)
        self.setObjectName("aiChatToolActivityCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(0, 1, 0, 1)
        row.setSpacing(8)
        root.addLayout(row)

        # Status indicator slot — a running spinner or a terminal check/cross.
        self._status_slot = QWidget(self)
        self._status_slot.setObjectName("aiChatToolActivityStatusSlot")
        self._status_slot.setFixedSize(14, 14)
        slot = QVBoxLayout(self._status_slot)
        slot.setContentsMargins(0, 0, 0, 0)
        slot.setSpacing(0)
        self._spinner = BrailleSpinner(self._status_slot)
        slot.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignCenter)
        self._status_icon = QLabel(self._status_slot)
        self._status_icon.setObjectName("aiChatToolActivityStatusIcon")
        self._status_icon.setFixedSize(14, 14)
        self._status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_icon.hide()
        slot.addWidget(self._status_icon, 0, Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._status_slot, 0, Qt.AlignmentFlag.AlignVCenter)

        self._title_icon = QLabel(self)
        self._title_icon.setObjectName("aiChatToolActivityTitleIcon")
        self._title_icon.setFixedSize(14, 14)
        self._title_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._title_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        self._title = QLabel(self)
        self._title.setObjectName("aiChatToolActivityTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._title.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        row.addWidget(self._title, 0, Qt.AlignmentFlag.AlignVCenter)

        self._detail = QLabel(self)
        self._detail.setObjectName("aiChatToolActivityDetail")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._detail.setFixedHeight(self._detail.fontMetrics().lineSpacing() + 2)
        row.addWidget(self._detail, 1, Qt.AlignmentFlag.AlignVCenter)

        self._duration = QLabel(self)
        self._duration.setObjectName("aiChatToolActivityDuration")
        self._duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._duration.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        row.addWidget(self._duration, 0, Qt.AlignmentFlag.AlignVCenter)

        self._record_id = ""
        self._status: ToolActivityStatus = "running"
        self.hide()

    def record_id(self) -> str:
        """Return the bound tool activity record id."""
        return self._record_id

    def status(self) -> ToolActivityStatus:
        """Return the current visual status."""
        return self._status

    def apply_record(self, record: ToolActivityRecord) -> None:
        """Update the row from *record*."""
        self._record_id = record["id"]
        self._status = record["status"]
        tool_name = str(record.get("tool_name") or "")
        icon_name = _TOOL_ICONS.get(tool_name, "wrench")
        failed = self._status in {"error", "rejected"}
        icon_color = COLOR_DANGER if failed else ""
        self._title_icon.setPixmap(phi(icon_name, color=icon_color, size=12).pixmap(12, 12))
        self._title.setText(record["title"])
        self._title.setProperty("failed", "true" if failed else "false")
        self._title.style().unpolish(self._title)
        self._title.style().polish(self._title)

        detail_text = (record.get("detail") or "").strip()
        self._detail.setToolTip(detail_text)
        display = _ellipsize(detail_text, self._detail)
        if self._status == "running":
            self._spinner.start()
            self._spinner.show()
            self._status_icon.hide()
        else:
            self._spinner.stop()
            self._spinner.hide()
            self._status_icon.show()
            icon = "check-circle" if self._status == "completed" else "x-circle"
            color = COLOR_SUCCESS if self._status == "completed" else COLOR_DANGER
            self._status_icon.setPixmap(phi(icon, color=color, size=12).pixmap(12, 12))
        self._detail.setText(display)
        self._detail.setVisible(bool(detail_text))

        started = record.get("started_at")
        completed = record.get("completed_at")
        elapsed = None if started is None or completed is None else completed - started
        self._duration.setText(_format_duration(elapsed))
        self.show()


__all__ = ["ToolActivityCard"]
