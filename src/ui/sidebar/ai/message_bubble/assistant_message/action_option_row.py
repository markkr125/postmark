"""Shared hover-highlight row for chat message action flyouts."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.styling.theme import COLOR_HOVER_BG


class ActionOptionRow(QWidget):
    """One clickable action row with hover highlight and hand cursor."""

    clicked = Signal()

    def __init__(
        self,
        label_text: str,
        *,
        row_object_name: str,
        label_object_name: str,
        parent: QWidget | None = None,
    ) -> None:
        """Build a labeled action row."""
        super().__init__(parent)
        self.setObjectName(row_object_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hovered = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        label = QLabel(label_text)
        label.setObjectName(label_object_name)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(label)

    def enterEvent(self, event) -> None:
        """Track hover for gentle highlight."""
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Clear hover highlight."""
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Emit ``clicked`` for primary-button releases inside the row."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        """Paint hover wash when the pointer is over the row."""
        if self._hovered:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            wash = QColor(COLOR_HOVER_BG)
            wash.setAlpha(96)
            painter.setBrush(wash)
            painter.drawRoundedRect(self.rect().adjusted(2, 1, -2, -1), 4, 4)
            painter.end()
        super().paintEvent(event)


__all__ = ["ActionOptionRow"]
