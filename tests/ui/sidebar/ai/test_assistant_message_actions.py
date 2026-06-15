"""Tests for assistant message actions popup."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPushButton

from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.assistant_message.actions_popup import (
    AiAssistantMessageActionsPopup,
)


def test_copy_action_puts_markdown_on_clipboard(qapp: QApplication) -> None:
    """Copy message writes the assistant markdown body to the clipboard."""
    bubble = ChatMessageBubble("assistant", "Line one\n\nLine two")
    copied: list[str] = []

    def _capture() -> None:
        copied.append(bubble.full_markdown_for_copy())

    bubble.copy_requested.connect(_capture)
    bubble.copy_requested.emit()
    assert copied == ["Line one\n\nLine two"]


def test_actions_popup_fork_callback_runs(qapp: QApplication) -> None:
    """Fork row invokes the callback supplied when the popup opens."""
    popup = AiAssistantMessageActionsPopup.instance()
    anchor = QPushButton()
    anchor.show()
    fired: list[str] = []
    popup.show_for(anchor, on_fork=lambda: fired.append("fork"))
    popup._on_fork()
    assert fired == ["fork"]
