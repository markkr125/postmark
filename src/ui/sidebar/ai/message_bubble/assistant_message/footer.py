"""Model/cost row below completed assistant messages (rule is painted on the body)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ui.sidebar.ai.message_bubble.assistant_message.actions_popup import (
    AiAssistantMessageActionsPopup,
)
from ui.styling.icons import phi
from ui.styling.theme import COLOR_TEXT_MUTED

_MENU_BTN_SIZE = 20
_MENU_ICON_SIZE = 15


class AssistantMessageFooterRow(QWidget):
    """Model/cost label and actions menu for a completed assistant turn."""

    fork_requested = Signal()
    copy_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build a metadata row shown when the assistant turn is complete."""
        super().__init__(parent)
        self.setObjectName("aiChatAssistantMessageFooter")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self._usage_label = QLabel()
        self._usage_label.setObjectName("aiChatAssistantUsageLabel")
        self._usage_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._usage_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._usage_label, 1)

        self._menu_btn = QPushButton()
        self._menu_btn.setObjectName("aiChatAssistantMessageMenu")
        self._menu_btn.setFlat(True)
        self._menu_btn.setIconSize(QSize(_MENU_ICON_SIZE, _MENU_ICON_SIZE))
        self._menu_btn.setFixedSize(_MENU_BTN_SIZE, _MENU_BTN_SIZE)
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_btn.setIcon(phi("dots-three", color=COLOR_TEXT_MUTED, size=_MENU_ICON_SIZE))
        self._menu_btn.setToolTip("Message actions")
        self._menu_btn.clicked.connect(self._on_menu_clicked)
        row.addWidget(self._menu_btn, 0, Qt.AlignmentFlag.AlignRight)

        self._fork_enabled = True
        self.hide()

    def set_fork_enabled(self, enabled: bool) -> None:
        """Enable or disable the fork action for this footer."""
        self._fork_enabled = enabled

    def set_usage_text(self, text: str) -> None:
        """Set the left-side model and cost label."""
        self._usage_label.setText(text)

    def menu_button(self) -> QPushButton:
        """Return the three-dot menu button."""
        return self._menu_btn

    def _on_menu_clicked(self) -> None:
        """Toggle the assistant actions flyout."""
        AiAssistantMessageActionsPopup.instance().toggle_for(
            self._menu_btn,
            fork_enabled=self._fork_enabled,
            on_fork=self.fork_requested.emit,
            on_copy=self.copy_requested.emit,
        )


__all__ = ["AssistantMessageFooterRow"]
