"""Placeholder shown until a heavy editor subtree is materialised on first tab visit."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class LazyEditorPlaceholder(QWidget):
    """Compact busy state with indeterminate progress and caption text."""

    def __init__(
        self, message: str = "Loading editor\u2026", parent: QWidget | None = None
    ) -> None:
        """Create a centred placeholder suitable for body/scripts deferred load."""
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)
        lay.addStretch()
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setFixedHeight(4)
        self._bar.setTextVisible(False)
        lay.addWidget(self._bar)
        self._label = QLabel(message)
        self._label.setObjectName("mutedLabel")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        lay.addWidget(self._label)
        lay.addStretch()
