"""Tests for user message actions popup."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPushButton

from ui.sidebar.ai.message_bubble.user_message.actions_popup import AiUserMessageActionsPopup


def test_actions_popup_fork_callback_runs(qapp: QApplication) -> None:
    """Fork row invokes the callback supplied when the popup opens."""
    popup = AiUserMessageActionsPopup.instance()
    anchor = QPushButton()
    anchor.show()
    fired: list[str] = []
    popup.show_for(anchor, on_fork=lambda: fired.append("fork"))
    popup._on_fork()
    assert fired == ["fork"]
