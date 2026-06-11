"""Bottom gradient fade for height-clamped user message text."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

from ui.styling.theme import ThemePalette, current_palette

USER_MESSAGE_FADE_HEIGHT_PX = 28


class UserMessageBottomFade(QWidget):
    """Gradient fade at the bottom of a height-clamped user message label."""

    def __init__(self, parent: QWidget) -> None:
        """Build a mouse-transparent fade strip over the user message label."""
        super().__init__(parent)
        self.setObjectName("aiChatUserMessageFade")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedHeight(USER_MESSAGE_FADE_HEIGHT_PX)

    def _fade_base_color(self, palette: ThemePalette) -> QColor:
        """Return the solid colour the bottom fade should blend into."""
        return QColor(palette["composer_bg"])

    def paintEvent(self, _event: object) -> None:
        """Paint a vertical fade from transparent to the user bubble background."""
        palette = current_palette()
        base = self._fade_base_color(palette)
        gradient = QLinearGradient(0.0, 0.0, 0.0, float(self.height()))
        gradient.setColorAt(0.0, QColor(base.red(), base.green(), base.blue(), 0))
        gradient.setColorAt(1.0, base)
        painter = QPainter(self)
        painter.fillRect(self.rect(), gradient)
