"""Clickable agent-execute result card in the assistant transcript."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QEnterEvent, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.ai.chat.execute_events import ExecuteRunRecord, ExecuteStatus
from ui.styling.icons import phi
from ui.styling.theme import COLOR_DANGER, COLOR_SUCCESS

_OP_LABELS: dict[str, str] = {
    "send_request": "Send",
    "send_draft": "Send draft",
    "replay_history": "Replay",
    "run_scripts": "Run scripts",
    "run_local_script": "Run local script",
    "run_collection": "Run collection",
    "run_iterations": "Run iterations",
    "unknown": "Execute",
}


class ExecuteResultCard(QFrame):
    """Summary row for one agent send/script run; click opens the stored response."""

    clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build a hidden card until a record is applied."""
        super().__init__(parent)
        self.setObjectName("aiChatExecuteCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 8)
        root.setSpacing(2)

        header = QWidget(self)
        header.setObjectName("aiChatExecuteHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        self._title_icon = QLabel(header)
        self._title_icon.setObjectName("aiChatExecuteTitleIcon")
        self._title_icon.setPixmap(phi("paper-plane-right", size=14).pixmap(14, 14))
        self._title_icon.setFixedSize(16, 16)
        header_row.addWidget(self._title_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        self._label = QLabel(header)
        self._label.setObjectName("aiChatExecuteLabel")
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self._label, 1)

        self._op_chip = QLabel(header)
        self._op_chip.setObjectName("aiChatExecuteOpChip")
        header_row.addWidget(self._op_chip, 0, Qt.AlignmentFlag.AlignVCenter)

        self._open_icon = QLabel(header)
        self._open_icon.setObjectName("aiChatExecuteOpenIcon")
        self._open_icon.setPixmap(phi("arrow-up-right", size=12).pixmap(12, 12))
        self._open_icon.setFixedSize(12, 12)
        header_row.addWidget(self._open_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(header)

        meta = QWidget(self)
        meta.setObjectName("aiChatExecuteMetaRow")
        meta_row = QHBoxLayout(meta)
        meta_row.setContentsMargins(22, 0, 0, 0)
        meta_row.setSpacing(6)

        self._status_icon = QLabel(meta)
        self._status_icon.setObjectName("aiChatExecuteStatusIcon")
        meta_row.addWidget(self._status_icon, 0)

        self._status_label = QLabel(meta)
        self._status_label.setObjectName("aiChatExecuteStatusLabel")
        meta_row.addWidget(self._status_label, 1)
        root.addWidget(meta)

        self._record_id = ""
        self._history_entry_id: int | None = None
        self._request_id: int | None = None
        self._local_script_id: int | None = None
        self._status: ExecuteStatus = "completed"
        self._card_hovered = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self._set_children_mouse_transparent()
        self.hide()

    def record_id(self) -> str:
        """Return the bound execute record id."""
        return self._record_id

    def history_entry_id(self) -> int | None:
        """Return the history entry id for Response viewer open, if any."""
        return self._history_entry_id

    def request_id(self) -> int | None:
        """Return the request id fallback when no history entry exists."""
        return self._request_id

    def apply_record(self, record: ExecuteRunRecord) -> None:
        """Update the card from *record*."""
        self._record_id = record["id"]
        self._history_entry_id = record.get("history_entry_id")
        self._request_id = record.get("request_id")
        self._local_script_id = record.get("local_script_id")
        self._status = record["status"]
        self._label.setText(record["label"])
        self._op_chip.setText(_OP_LABELS.get(record["operation"], "Execute"))

        status_code = record.get("status_code")
        url = str(record.get("url") or "").strip()
        if self._status == "error":
            caption = "Failed"
            color = COLOR_DANGER
            icon_name = "warning-circle"
        elif isinstance(status_code, int):
            caption = f"{status_code}"
            if url:
                caption = f"{status_code} · {url}"
            color = COLOR_SUCCESS if 200 <= status_code < 400 else COLOR_DANGER
            icon_name = "check-circle" if 200 <= status_code < 400 else "warning-circle"
        else:
            caption = "Completed"
            if url:
                caption = url
            color = COLOR_SUCCESS
            icon_name = "check-circle"
        self._status_label.setText(caption)
        self._status_icon.setPixmap(phi(icon_name, color=color, size=14).pixmap(14, 14))

        clickable = (
            self._history_entry_id is not None
            or self._request_id is not None
            or self._local_script_id is not None
            or record.get("collection_id") is not None
        )
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor
        )
        self.show()

    def enterEvent(self, event: QEnterEvent) -> None:
        """Highlight the card border on hover."""
        self._set_card_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """Clear hover highlight."""
        self._set_card_hovered(False)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Emit *clicked* for left-clicks when a target exists."""
        if event.button() == Qt.MouseButton.LeftButton and (
            self._history_entry_id is not None
            or self._request_id is not None
            or self._local_script_id is not None
        ):
            self.clicked.emit(self._record_id)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _set_card_hovered(self, hovered: bool) -> None:
        if self._card_hovered == hovered:
            return
        self._card_hovered = hovered
        self.setProperty("cardHovered", hovered)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def _set_children_mouse_transparent(self) -> None:
        for child in self.findChildren(QWidget):
            if child is self:
                continue
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)


__all__ = ["ExecuteResultCard"]
