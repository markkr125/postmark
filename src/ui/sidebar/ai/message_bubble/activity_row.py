"""Streaming activity spinner row for assistant message bubbles."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from ui.widgets.busy_spinner import BrailleSpinner


class AssistantActivityRow(QWidget):
    """Spinner + status label shown while waiting for the first stream token."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build a muted activity row hidden until streaming starts."""
        super().__init__(parent)
        self.setObjectName("aiChatActivityRow")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 8)
        row.setSpacing(6)

        self._spinner = BrailleSpinner(self, object_name="aiChatActivitySpinner")
        row.addWidget(self._spinner, 0)

        self._label = QLabel()
        self._label.setObjectName("aiChatActivityLabel")
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        row.addWidget(self._label, 1)

        self._research_btn = QPushButton("Research")
        self._research_btn.setObjectName("aiChatResearchChip")
        self._research_btn.setFlat(True)
        self._research_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._research_btn.hide()
        row.addWidget(self._research_btn, 0, Qt.AlignmentFlag.AlignRight)

        self._click_to_toggle = False
        self._research_btn.clicked.connect(self.clicked.emit)

        self.hide()

    def message(self) -> str:
        """Return the current status caption."""
        return self._label.text()

    def set_research_chip_visible(self, visible: bool) -> None:
        """Show or hide the inline Research chip on the activity row."""
        self._research_btn.setVisible(visible)

    def set_click_to_toggle(self, enabled: bool) -> None:
        """When True, clicking the row emits ``clicked`` (research flyout toggle)."""
        self._click_to_toggle = enabled
        cursor = Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Toggle research flyout when the row is clickable."""
        if (
            self._click_to_toggle
            and self.isVisible()
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def show_activity(self, message: str) -> None:
        """Show the row, start the spinner, and set *message*."""
        self._label.setText(message)
        self._spinner.start()
        self.show()

    def set_message(self, message: str) -> None:
        """Update the status caption without changing visibility."""
        self._label.setText(message)

    def hide_activity(self) -> None:
        """Stop the spinner and hide the row."""
        self._spinner.stop()
        self.hide()

    def is_activity_visible(self) -> bool:
        """Return whether the activity row is in the shown state (not hidden)."""
        return not self.isHidden()


_AssistantActivityRow = AssistantActivityRow
