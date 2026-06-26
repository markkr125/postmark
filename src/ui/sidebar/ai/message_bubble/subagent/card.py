"""Cursor-style collapsible subagent card in the assistant transcript."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.ai.chat.subagent_events import (
    SubagentRunRecord,
    SubagentStatus,
    subagent_type_display,
)
from services.ai.chat.subagent_transcript import steps_for_subagent_record
from ui.sidebar.ai.message_bubble.subagent.body import SubagentCardBody
from ui.sidebar.ai.message_bubble.wrapping_label import _WrappingLabel
from ui.styling.icons import phi
from ui.styling.theme import COLOR_DANGER, COLOR_SUCCESS
from ui.widgets.busy_spinner import BrailleSpinner

_STATUS_LABELS: dict[SubagentStatus, str] = {
    "warming": "Starting",
    "running": "Running",
    "completed": "Completed",
    "error": "Failed",
}


class SubagentTaskCard(QFrame):
    """Collapsible block showing one subagent run (Cursor-style task card)."""

    clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build a hidden card until a record is applied."""
        super().__init__(parent)
        self.setObjectName("aiChatSubagentCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 4)
        root.setSpacing(4)

        header = QPushButton(self)
        header.setObjectName("aiChatSubagentHeader")
        header.setFlat(True)
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        header.clicked.connect(self._toggle_expanded)
        self._header = header
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        self._title_icon = QLabel(header)
        self._title_icon.setObjectName("aiChatSubagentTitleIcon")
        self._title_icon.setPixmap(phi("cpu", size=14).pixmap(14, 14))
        self._title_icon.setFixedSize(16, 16)
        header_row.addWidget(self._title_icon, 0, Qt.AlignmentFlag.AlignTop)

        self._label = _WrappingLabel("", header)
        self._label.setObjectName("aiChatSubagentLabel")
        header_row.addWidget(self._label, 1)

        self._type_chip = QLabel(header)
        self._type_chip.setObjectName("aiChatSubagentTypeChip")
        self._type_chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        header_row.addWidget(self._type_chip, 0, Qt.AlignmentFlag.AlignTop)

        self._chevron = QLabel(header)
        self._chevron.setObjectName("aiChatSubagentChevron")
        self._chevron.setPixmap(phi("caret-down", size=12).pixmap(12, 12))
        self._chevron.setFixedSize(12, 12)
        header_row.addWidget(self._chevron, 0, Qt.AlignmentFlag.AlignTop)
        root.addWidget(header)

        status_row = QWidget(self)
        status_row.setObjectName("aiChatSubagentStatusRow")
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(22, 0, 0, 0)
        status_layout.setSpacing(6)

        self._spinner = BrailleSpinner(status_row, object_name="aiChatSubagentSpinner")
        status_layout.addWidget(self._spinner, 0)

        self._status_icon = QLabel(status_row)
        self._status_icon.setObjectName("aiChatSubagentStatusIcon")
        self._status_icon.hide()
        status_layout.addWidget(self._status_icon, 0)

        self._status_label = QLabel(status_row)
        self._status_label.setObjectName("aiChatSubagentStatusLabel")
        status_layout.addWidget(self._status_label, 1)
        root.addWidget(status_row)

        self._body = SubagentCardBody(self)
        root.addWidget(self._body)

        self._record_id = ""
        self._status: SubagentStatus = "warming"
        self._expanded = True
        self.hide()

    def record_id(self) -> str:
        """Return the bound subagent record id."""
        return self._record_id

    def status(self) -> SubagentStatus:
        """Return the current visual status."""
        return self._status

    def apply_record(self, record: SubagentRunRecord) -> None:
        """Update the card from *record*."""
        self._record_id = record["id"]
        self._status = record["status"]
        self._label.setText(record["label"])
        self._type_chip.setText(subagent_type_display(record["subagent_type"]))
        self._status_label.setText(_STATUS_LABELS.get(self._status, self._status.title()))

        steps = record.get("steps")
        if not steps:
            steps = steps_for_subagent_record(record)
        self._body.set_steps(steps)

        if self._status in ("warming", "running"):
            self._expanded = True
            self._spinner.start()
            self._spinner.show()
            self._status_icon.hide()
            self.setCursor(
                Qt.CursorShape.ArrowCursor
                if self._status == "warming"
                else Qt.CursorShape.PointingHandCursor
            )
        else:
            self._spinner.stop()
            self._spinner.hide()
            self._status_icon.show()
            icon_name = "check-circle" if self._status == "completed" else "warning-circle"
            color = COLOR_SUCCESS if self._status == "completed" else COLOR_DANGER
            self._status_icon.setPixmap(phi(icon_name, color=color, size=14).pixmap(14, 14))
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._sync_expanded()
        self._sync_header_geometry()
        self.show()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Reflow wrapped title text when the card width changes."""
        super().resizeEvent(event)
        self._sync_header_geometry()

    def _header_text_width(self) -> int:
        """Return the inner width available for the title label."""
        width = self.width()
        if width <= 0:
            return 0
        layout = self.layout()
        outer = 0
        if layout is not None:
            margins = layout.contentsMargins()
            outer = margins.left() + margins.right()
        inner = max(1, width - outer - 20)
        chip_w = self._type_chip.sizeHint().width() if self._type_chip.isVisible() else 0
        chevron_w = self._chevron.width() or 12
        # icon + gaps between header columns
        return max(1, inner - 16 - 8 - chip_w - 8 - chevron_w - 8)

    def _sync_header_geometry(self) -> None:
        """Size the header button to fit the wrapped title label."""
        text_width = self._header_text_width()
        if text_width <= 0:
            return
        label_height = self._label.heightForWidth(text_width)
        if label_height <= 0:
            label_height = self._label.fontMetrics().height()
        self._header.setMinimumHeight(max(20, label_height))
        self.updateGeometry()

    def _sync_expanded(self) -> None:
        """Apply expand/collapse state to body and chevron."""
        self._body.setVisible(self._expanded and self._body.has_steps())
        chevron = "caret-down" if self._expanded else "caret-right"
        self._chevron.setPixmap(phi(chevron, size=12).pixmap(12, 12))

    def _toggle_expanded(self) -> None:
        """Toggle body visibility from the header button."""
        if self._status == "warming":
            return
        self._expanded = not self._expanded
        self._sync_expanded()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Open drill-in when clicking outside the header toggle."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._status not in ("warming",)
            and event.position().y() > 40
        ):
            self.clicked.emit(self._record_id)
            event.accept()
            return
        super().mouseReleaseEvent(event)


__all__ = ["SubagentTaskCard"]
