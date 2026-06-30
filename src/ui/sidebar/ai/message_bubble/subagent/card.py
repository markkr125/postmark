"""Compact subagent summary row in the assistant transcript."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QEnterEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.ai.chat.subagent_events import (
    SubagentRunRecord,
    SubagentStatus,
    subagent_type_display,
)
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

_CARD_MARGIN_LEFT = 10
_CARD_MARGIN_TOP = 4
_CARD_MARGIN_RIGHT = 10
_CARD_MARGIN_BOTTOM = 10
_TITLE_ICON_SIZE_PX = 16
# Extra pull-up after cap-height alignment with the cpu icon (optical tweak).
_TITLE_OPTICAL_NUDGE_PX = 2


class SubagentTaskCard(QFrame):
    """Summary row for one subagent run; click opens the detail window."""

    clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build a hidden card until a record is applied."""
        super().__init__(parent)
        self.setObjectName("aiChatSubagentCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            _CARD_MARGIN_LEFT,
            _CARD_MARGIN_TOP,
            _CARD_MARGIN_RIGHT,
            _CARD_MARGIN_BOTTOM,
        )
        root.setSpacing(4)

        header = QWidget(self)
        header.setObjectName("aiChatSubagentHeader")
        self._header = header
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        self._title_icon = QLabel(header)
        self._title_icon.setObjectName("aiChatSubagentTitleIcon")
        self._title_icon.setPixmap(phi("cpu", size=14).pixmap(14, 14))
        self._title_icon.setFixedSize(_TITLE_ICON_SIZE_PX, _TITLE_ICON_SIZE_PX)
        self._title_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(self._title_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        self._label = _WrappingLabel("", header)
        self._label.setObjectName("aiChatSubagentLabel")
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self._label, 1, Qt.AlignmentFlag.AlignVCenter)

        self._type_chip = QLabel(header)
        self._type_chip.setObjectName("aiChatSubagentTypeChip")
        self._type_chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        header_row.addWidget(self._type_chip, 0, Qt.AlignmentFlag.AlignVCenter)

        self._open_icon = QLabel(header)
        self._open_icon.setObjectName("aiChatSubagentOpenIcon")
        self._open_icon.setPixmap(phi("arrow-up-right", size=12).pixmap(12, 12))
        self._open_icon.setFixedSize(12, 12)
        self._open_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(self._open_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        self._sync_title_label_nudge()
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

        self._record_id = ""
        self._status: SubagentStatus = "warming"
        self._card_hovered = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self._set_children_mouse_transparent()
        self.hide()

    def _set_children_mouse_transparent(self) -> None:
        """Route clicks and hover through to the card frame."""
        for child in self.findChildren(QWidget):
            if child is self:
                continue
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def enterEvent(self, event: QEnterEvent) -> None:
        """Highlight the card border when the pointer enters."""
        self._set_card_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """Clear hover highlight when the pointer leaves the card."""
        self._set_card_hovered(False)
        super().leaveEvent(event)

    def _set_card_hovered(self, hovered: bool) -> None:
        """Toggle the dynamic ``cardHovered`` property for QSS."""
        if self._status == "warming":
            hovered = False
        if self._card_hovered == hovered:
            return
        self._card_hovered = hovered
        self.setProperty("cardHovered", hovered)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

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

        if self._status in ("warming", "running"):
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

        if self._status == "warming":
            self._set_card_hovered(False)

        self._sync_title_label_nudge()
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
        open_w = self._open_icon.width() or 12
        return max(1, inner - 16 - 8 - chip_w - 8 - open_w - 8)

    def _title_label_margin_top(self) -> int:
        """Return a negative top margin so the title cap height centers on the icon."""
        fm = self._label.fontMetrics()
        line_h = fm.height()
        centered = (_TITLE_ICON_SIZE_PX - line_h) // 2
        return centered - _TITLE_OPTICAL_NUDGE_PX

    def _sync_title_label_nudge(self) -> None:
        """Pull the title up for optical alignment with the cpu icon."""
        margin_top = self._title_label_margin_top()
        if margin_top == 0:
            self._label.setContentsMargins(0, 0, 0, 0)
            return
        self._label.setContentsMargins(0, margin_top, 0, 0)

    def _sync_header_geometry(self) -> None:
        """Size the header row to fit the wrapped title label."""
        text_width = self._header_text_width()
        if text_width <= 0:
            return
        label_height = self._label.heightForWidth(text_width)
        if label_height <= 0:
            label_height = self._label.fontMetrics().height()
        self._header.setMinimumHeight(max(_TITLE_ICON_SIZE_PX, label_height))
        self.updateGeometry()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Open the detail window when any part of the card is clicked."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._status != "warming"
            and self._record_id
        ):
            self.clicked.emit(self._record_id)
            event.accept()
            return
        super().mouseReleaseEvent(event)


__all__ = ["SubagentTaskCard"]
