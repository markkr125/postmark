"""Compact main-agent tool activity row in the assistant transcript."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.ai.chat.tool_activity_events import ToolActivityRecord, ToolActivityStatus
from ui.sidebar.ai.message_bubble.wrapping_label import _WrappingLabel
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
    "postmark_workspace_mutate": "pencil-simple",
    "postmark_workspace_execute": "paper-plane-right",
}


class ToolActivityCard(QFrame):
    """Summary row for one main-agent tool call."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build a hidden card until a record is applied."""
        super().__init__(parent)
        self.setObjectName("aiChatToolActivityCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 4, 10, 8)
        root.setSpacing(4)

        header = QWidget(self)
        header.setObjectName("aiChatToolActivityHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        self._title_icon = QLabel(header)
        self._title_icon.setObjectName("aiChatToolActivityTitleIcon")
        self._title_icon.setFixedSize(16, 16)
        self._title_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(self._title_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        self._title = _WrappingLabel("", header)
        self._title.setObjectName("aiChatToolActivityTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self._title, 1, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(header)

        detail_row = QWidget(self)
        detail_row.setObjectName("aiChatToolActivityDetailRow")
        detail_layout = QHBoxLayout(detail_row)
        detail_layout.setContentsMargins(22, 0, 0, 0)
        detail_layout.setSpacing(6)

        self._spinner = BrailleSpinner(detail_row, object_name="aiChatToolActivitySpinner")
        detail_layout.addWidget(self._spinner, 0)

        self._status_icon = QLabel(detail_row)
        self._status_icon.setObjectName("aiChatToolActivityStatusIcon")
        self._status_icon.hide()
        detail_layout.addWidget(self._status_icon, 0)

        self._detail = _WrappingLabel("", detail_row)
        self._detail.setObjectName("aiChatToolActivityDetail")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        detail_layout.addWidget(self._detail, 1)
        root.addWidget(detail_row)

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
        """Update the card from *record*."""
        self._record_id = record["id"]
        self._status = record["status"]
        tool_name = str(record.get("tool_name") or "")
        icon_name = _TOOL_ICONS.get(tool_name, "wrench")
        self._title_icon.setPixmap(phi(icon_name, size=14).pixmap(14, 14))
        self._title.setText(record["title"])
        detail_text = record.get("detail") or ""
        status_label = _STATUS_LABELS.get(self._status, self._status.title())
        if self._status == "running":
            self._spinner.start()
            self._spinner.show()
            self._status_icon.hide()
            self._detail.setText(detail_text or status_label)
        else:
            self._spinner.stop()
            self._spinner.hide()
            self._status_icon.show()
            if self._status == "completed":
                icon = "check-circle"
                color = COLOR_SUCCESS
            elif self._status == "rejected":
                icon = "x-circle"
                color = COLOR_DANGER
            else:
                icon = "warning-circle"
                color = COLOR_DANGER
            self._status_icon.setPixmap(phi(icon, color=color, size=14).pixmap(14, 14))
            suffix = f" — {status_label}" if detail_text else status_label
            self._detail.setText(detail_text + suffix if detail_text else status_label)
        self.show()


__all__ = ["ToolActivityCard"]
