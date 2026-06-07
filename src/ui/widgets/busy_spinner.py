"""Shared braille spinner used for inline busy indicators."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QWidget

# Braille spinner frames — same pattern CLIs use; renders crisply at any font size.
_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_FRAME_INTERVAL_MS = 90


class BrailleSpinner(QLabel):
    """Tiny rotating spinner that animates while visible."""

    def __init__(
        self, parent: QWidget | None = None, *, object_name: str = "busyChipSpinner"
    ) -> None:
        """Build a spinner with optional ``objectName`` for QSS."""
        super().__init__(parent)
        self.setObjectName(object_name)
        self._frame = 0
        self.setText(_SPINNER_FRAMES[0])
        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % len(_SPINNER_FRAMES)
        self.setText(_SPINNER_FRAMES[self._frame])

    def start(self) -> None:
        """Reset to the first frame and begin animation."""
        self._frame = 0
        self.setText(_SPINNER_FRAMES[0])
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        """Stop the animation timer."""
        self._timer.stop()

    def frame_index(self) -> int:
        """Return the current animation frame index (for tests)."""
        return self._frame
