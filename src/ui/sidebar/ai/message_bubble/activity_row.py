"""Streaming activity spinner row for assistant message bubbles."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from ui.widgets.busy_spinner import BrailleSpinner


class AssistantActivityRow(QWidget):
    """Spinner + status label shown while waiting for the first stream token."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build a muted activity row hidden until streaming starts."""
        super().__init__(parent)
        self.setObjectName("aiChatActivityRow")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

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

        self.hide()

    def message(self) -> str:
        """Return the current status caption."""
        return self._label.text()

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
