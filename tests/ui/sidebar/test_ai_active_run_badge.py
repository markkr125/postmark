"""Tests for active-run chrome in the AI sidebar header."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel

from ui.sidebar import RightSidebar


def test_active_run_badge_shows_count(qapp: QApplication, qtbot) -> None:
    """Header badge reflects the number of concurrent chat runs."""
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    badge = sidebar._flyout.findChild(QLabel, "aiChatActiveRunsBadge")
    assert badge is not None
    assert badge.isHidden()
    sidebar.set_ai_active_run_count(2)
    assert not badge.isHidden()
    assert badge.text() == "2 active"
    assert "2 chats running" in badge.toolTip()
    sidebar.set_ai_active_run_count(0)
    assert badge.isHidden()
