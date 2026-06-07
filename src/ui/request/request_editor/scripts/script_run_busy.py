"""Small busy chip with a rotating spinner shown in the editor's status bar."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ui.widgets.busy_spinner import BrailleSpinner


class ScriptRunBusyOverlay(QWidget):
    """Inline status chip: rotating spinner + short caption.

    The historical name is kept so existing call sites compile unchanged;
    today this is a small chip embedded in the editor's status bar, not an
    overlay over the code.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the chip; hidden until :meth:`show_busy` is called."""
        super().__init__(parent)
        self.setObjectName("scriptRunBusyChip")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self._spinner = BrailleSpinner(self)
        row.addWidget(self._spinner)
        self._label = QLabel("Running script…")
        self._label.setObjectName("mutedLabel")
        self._label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        row.addWidget(self._label)
        self.hide()

    def set_message(self, message: str) -> None:
        """Update the caption shown next to the spinner."""
        self._label.setText(message)

    def show_busy(self, message: str = "Running script…") -> None:
        """Show the chip and start the spinner animation."""
        self.set_message(message)
        self._spinner.start()
        self.show()

    def hide_busy(self) -> None:
        """Hide the chip and stop the spinner timer."""
        self._spinner.stop()
        self.hide()

    # Compatibility shim: callers used to call this on the old overlay class
    # when the editor was resized. As a status-bar widget we no longer need it.
    def _sync_geometry(self) -> None:
        return
