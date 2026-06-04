"""Chat message bubble widget for the AI assistant panel."""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

ChatRole = Literal["user", "assistant"]


class ChatMessageBubble(QFrame):
    """One chat message rendered as a word-wrapped bubble.

    ``role`` selects the ``objectName`` (and therefore QSS styling):
    ``aiChatMessageUser`` or ``aiChatMessageAssistant``.
    """

    def __init__(self, role: ChatRole, text: str, parent: QWidget | None = None) -> None:
        """Build a bubble for *role* showing *text*."""
        super().__init__(parent)
        self._role: ChatRole = role
        self.setObjectName("aiChatMessageUser" if role == "user" else "aiChatMessageAssistant")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(0)

        self._label = QLabel(text)
        self._label.setObjectName("aiChatMessageText")
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._label)

    @property
    def role(self) -> ChatRole:
        """Return the message role."""
        return self._role

    def text(self) -> str:
        """Return the message text."""
        return self._label.text()
