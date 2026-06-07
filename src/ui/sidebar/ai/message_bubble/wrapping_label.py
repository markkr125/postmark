"""Word-wrapped QLabel used in chat message rows."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


class _WrappingLabel(QLabel):
    """Word-wrapped label that reports height-for-width to the layout."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        """Configure wrap, expansion, and selectable text."""
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def hasHeightForWidth(self) -> bool:
        """Allow the layout to size this label from the available width."""
        return True

    def heightForWidth(self, width: int) -> int:
        """Return wrapped text height for *width*."""
        if width <= 0:
            return self.sizeHint().height()
        margins = self.contentsMargins()
        text_width = max(1, width - margins.left() - margins.right())
        rect = self.fontMetrics().boundingRect(
            0,
            0,
            text_width,
            0,
            Qt.TextFlag.TextWordWrap,
            self.text(),
        )
        return rect.height() + margins.top() + margins.bottom() + 2

    def setText(self, text: str) -> None:
        """Replace text and invalidate cached height."""
        super().setText(text)
        self.updateGeometry()
