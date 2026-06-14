"""In-transcript row shown while an older history page is loading."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from ui.widgets.busy_spinner import BrailleSpinner

_DEFAULT_MESSAGE = "Fetching older messages\u2026"


class TranscriptOlderLoadingRow(QWidget):
    """Spinner + caption inserted at the top of the transcript during older paging."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build a muted top-row indicator hidden until an older page fetch starts."""
        super().__init__(parent)
        self.setObjectName("aiChatOlderLoadingRow")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 12)
        row.setSpacing(6)

        self._spinner = BrailleSpinner(self, object_name="aiChatActivitySpinner")
        row.addWidget(self._spinner, 0)

        self._label = QLabel(_DEFAULT_MESSAGE)
        self._label.setObjectName("aiChatTranscriptLoadingLabel")
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        row.addWidget(self._label, 1)

        self.hide()

    def show_loading(self, message: str = _DEFAULT_MESSAGE) -> None:
        """Show the row, start the spinner, and set *message*."""
        self._label.setText(message)
        self._spinner.start()
        self.show()

    def hide_loading(self) -> None:
        """Stop the spinner and hide the row."""
        self._spinner.stop()
        self.hide()

    def is_loading_visible(self) -> bool:
        """Return whether the older-page indicator is currently shown."""
        return not self.isHidden()
