"""Footer chrome for user message bubbles (timestamp + config menu)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ui.sidebar.ai.chat_sessions.time_format import format_message_sent_at
from ui.sidebar.ai.message_bubble.user_message.actions_popup import AiUserMessageActionsPopup
from ui.styling.icons import CHAT_STOP_ICON_SIZE, chat_stop_icon, phi
from ui.styling.theme import COLOR_TEXT_MUTED

UserMessageFooterMode = Literal["actions", "stop"]

_CONFIG_BTN_SIZE = 28
_CONFIG_ICON_SIZE = 18
# QSS padding on QWidget/QPushButton does not affect layout geometry — only
# QLayout contents margins do. Keep a real bottom inset under the solid stop
# control so it is not flush with the user-bubble border.
_FOOTER_PAD_TOP = 2
_FOOTER_PAD_BOTTOM = 4


class UserMessageFooterRow(QWidget):
    """Timestamp on the left and a config or stop button on the right."""

    stop_requested = Signal()
    fork_requested = Signal()
    edit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build timestamp label and footer action button."""
        super().__init__(parent)
        self.setObjectName("aiChatUserMessageFooter")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, _FOOTER_PAD_TOP, 0, _FOOTER_PAD_BOTTOM)
        layout.setSpacing(4)

        self._timestamp = QLabel()
        self._timestamp.setObjectName("aiChatUserMessageTime")
        self._timestamp.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._timestamp.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._timestamp, 1)

        self._action_btn = QPushButton()
        self._action_btn.setObjectName("aiChatUserMessageConfig")
        self._action_btn.setFlat(True)
        self._action_btn.setIconSize(QSize(_CONFIG_ICON_SIZE, _CONFIG_ICON_SIZE))
        self._action_btn.setFixedSize(_CONFIG_BTN_SIZE, _CONFIG_BTN_SIZE)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.clicked.connect(self._on_action_clicked)
        layout.addWidget(self._action_btn, 0, Qt.AlignmentFlag.AlignRight)

        # The transcript row's fixed-height clamp can squeeze this row below its
        # hint (the wrapped prompt label reports a stale, inflated minimum), and
        # the fixed-size action button would then be clipped at the bottom. Pin
        # the row height (button + layout pads) so any squeeze lands on the label.
        self.setFixedHeight(_CONFIG_BTN_SIZE + _FOOTER_PAD_TOP + _FOOTER_PAD_BOTTOM)

        self._sent_at: datetime | None = None
        self._footer_mode: UserMessageFooterMode = "actions"
        self._fork_enabled = False
        self._edit_enabled = False
        self._timestamp.hide()
        self._apply_footer_mode("actions")

    def set_fork_enabled(self, enabled: bool) -> None:
        """Enable or disable the fork action for this footer."""
        self._fork_enabled = enabled

    def set_edit_enabled(self, enabled: bool) -> None:
        """Enable or disable the edit action for this footer."""
        self._edit_enabled = enabled

    def timestamp_label(self) -> QLabel:
        """Return the send-time label widget."""
        return self._timestamp

    def config_button(self) -> QPushButton:
        """Return the footer action button (config or stop)."""
        return self._action_btn

    def footer_mode(self) -> UserMessageFooterMode:
        """Return the current footer action mode."""
        return self._footer_mode

    def set_footer_mode(self, mode: UserMessageFooterMode) -> None:
        """Switch between message-actions and turn-scoped stop affordances."""
        if self._footer_mode == mode:
            return
        if mode == "stop":
            AiUserMessageActionsPopup.instance().hide_popup()
        self._apply_footer_mode(mode)

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

    def _apply_footer_mode(self, mode: UserMessageFooterMode) -> None:
        """Update icon, tooltip, and QSS property for *mode*."""
        self._footer_mode = mode
        self._action_btn.setProperty("footerMode", mode)
        if mode == "stop":
            self._action_btn.setObjectName("smallPrimaryButton")
            # Same icon-only box-model gotcha as the composer send/stop button.
            self._action_btn.setProperty("iconOnly", True)
            self._action_btn.setFlat(False)
            self._action_btn.setIconSize(QSize(CHAT_STOP_ICON_SIZE, CHAT_STOP_ICON_SIZE))
            self._action_btn.setIcon(chat_stop_icon())
            self._action_btn.setToolTip("Stop")
        else:
            self._action_btn.setObjectName("aiChatUserMessageConfig")
            self._action_btn.setProperty("iconOnly", False)
            self._action_btn.setFlat(True)
            self._action_btn.setIconSize(QSize(_CONFIG_ICON_SIZE, _CONFIG_ICON_SIZE))
            self._action_btn.setIcon(
                phi("arrow-u-up-left", color=COLOR_TEXT_MUTED, size=_CONFIG_ICON_SIZE)
            )
            self._action_btn.setToolTip("Message actions")
        # Re-pin size after polish: stylesheet padding can inflate sizeHint, and
        # with setFixedSize the accent fill still paints edge-to-edge of the rect.
        self._action_btn.setFixedSize(_CONFIG_BTN_SIZE, _CONFIG_BTN_SIZE)
        style = self._action_btn.style()
        style.unpolish(self._action_btn)
        style.polish(self._action_btn)

    def _on_action_clicked(self) -> None:
        """Open actions or request stop depending on footer mode."""
        if self._footer_mode == "stop":
            self.stop_requested.emit()
            return
        AiUserMessageActionsPopup.instance().toggle_for(
            self._action_btn,
            fork_enabled=self._fork_enabled,
            edit_enabled=self._edit_enabled,
            on_fork=self.fork_requested.emit,
            on_edit=self.edit_requested.emit,
        )


__all__ = ["UserMessageFooterMode", "UserMessageFooterRow"]
