"""Footer chrome for user message bubbles (timestamp + config menu)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ui.sidebar.ai.chat_sessions.time_format import format_message_sent_at
from ui.sidebar.ai.message_bubble.user_message.actions_popup import AiUserMessageActionsPopup
from ui.styling.icons import phi
from ui.styling.theme import COLOR_TEXT_MUTED


_CONFIG_BTN_SIZE = 28
_CONFIG_ICON_SIZE = 18


class UserMessageFooterRow(QWidget):
    """Timestamp on the left and a config menu button on the right."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build timestamp label and config button."""
        super().__init__(parent)
        self.setObjectName("aiChatUserMessageFooter")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._timestamp = QLabel()
        self._timestamp.setObjectName("aiChatUserMessageTime")
        self._timestamp.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._timestamp.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._timestamp, 1)

        self._config_btn = QPushButton()
        self._config_btn.setObjectName("aiChatUserMessageConfig")
        self._config_btn.setFlat(True)
        self._config_btn.setIcon(
            phi("arrow-u-up-left", color=COLOR_TEXT_MUTED, size=_CONFIG_ICON_SIZE)
        )
        self._config_btn.setIconSize(QSize(_CONFIG_ICON_SIZE, _CONFIG_ICON_SIZE))
        self._config_btn.setFixedSize(_CONFIG_BTN_SIZE, _CONFIG_BTN_SIZE)
        self._config_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._config_btn.clicked.connect(self._on_config_clicked)
        layout.addWidget(self._config_btn, 0, Qt.AlignmentFlag.AlignRight)

        self._sent_at: datetime | None = None
        self._timestamp.hide()

    def timestamp_label(self) -> QLabel:
        """Return the send-time label widget."""
        return self._timestamp

    def config_button(self) -> QPushButton:
        """Return the config menu button."""
        return self._config_btn

    def set_sent_at(self, sent_at: datetime | None) -> None:
        """Show or hide the timestamp for *sent_at*."""
        self._sent_at = sent_at
        if sent_at is not None:
            self._timestamp.setText(format_message_sent_at(sent_at))
            self._timestamp.show()
        else:
            self._timestamp.clear()
            self._timestamp.hide()

    def sent_at(self) -> datetime | None:
        """Return the current send time, if any."""
        return self._sent_at

    def _on_config_clicked(self) -> None:
        """Toggle the user-message actions flyout anchored to the config button."""
        AiUserMessageActionsPopup.instance().toggle_for(self._config_btn)


__all__ = ["UserMessageFooterRow"]
