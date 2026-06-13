"""Tests for AI chat controller finalize paths on the GUI thread."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QLabel

from ui.main_window.ai_chat_controller import _AiChatControllerMixin
from ui.sidebar import RightSidebar
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent


def _flush_stream_chunks(qtbot) -> None:
    """Wait for the coalesced chunk delivery timer (~50ms)."""
    qtbot.wait(60)


class _ChatControllerHost(_AiChatControllerMixin):
    """Minimal host exposing controller methods for panel integration tests."""

    def __init__(
        self,
        panel: AiChatPanel,
        session_id: str = "sess-1",
        *,
        sidebar: RightSidebar | None = None,
    ) -> None:
        """Wire a panel as the right-sidebar chat surface."""
        if sidebar is None:
            self._right_sidebar = cast(
                RightSidebar,
                SimpleNamespace(ai_chat_panel=panel),
            )
        else:
            self._right_sidebar = sidebar
        self._active_ai_session_id = session_id


def _session_row(session_id: str, title: str) -> dict[str, Any]:
    """Build a minimal session dict for controller title tests."""
    return {
        "id": session_id,
        "title": title,
        "model_id": "gpt-test",
        "mode": "agent",
        "agent_id": "postmark-assistant",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "last_preview": None,
        "archived": False,
    }


def test_sync_ai_session_title_uses_active_session(qapp: QApplication, qtbot) -> None:
    """Controller sync reads the active session title into flyout chrome."""
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ChatControllerHost(AiChatPanel(), session_id="sess-1", sidebar=sidebar)
    with patch(
        "ui.main_window.ai_chat_controller.AiChatSessionService.get_session",
        return_value=_session_row("sess-1", "Go HTTP client"),
    ):
        host._sync_ai_session_title()
    title = sidebar._flyout.findChild(QLabel, "aiChatSessionTitle")
    assert title is not None
    assert title.toolTip() == "Go HTTP client"


def test_on_ai_title_ready_updates_flyout_title(qapp: QApplication, qtbot) -> None:
    """Generated titles refresh the flyout subtitle for the active session."""
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ChatControllerHost(AiChatPanel(), session_id="sess-1", sidebar=sidebar)
    with (
        patch(
            "ui.main_window.ai_chat_controller.AiChatSessionService.rename_session",
        ) as rename,
        patch(
            "ui.main_window.ai_chat_controller.AiChatSessionService.get_session",
            return_value=_session_row("sess-1", "Generated title"),
        ),
    ):
        host._on_ai_title_ready("sess-1", "Generated title")
    rename.assert_called_once_with("sess-1", "Generated title")
    title = sidebar._flyout.findChild(QLabel, "aiChatSessionTitle")
    assert title is not None
    assert title.toolTip() == "Generated title"


def test_controller_stop_finalizes_streaming_rich_html(qapp: QApplication, qtbot) -> None:
    """User stop marshals through the controller and exits streaming with rich HTML."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _ChatControllerHost(panel)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "**Partial**")
    _flush_stream_chunks(qtbot)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.is_content_streaming()
    host._on_ai_chat_failed("sess-1", "stopped", "", "")
    assert not bubble.is_content_streaming()
    body = bubble.findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    html = body.toHtml().lower()
    assert "font-weight:600" in html or "font-weight:700" in html
    assert "stopped" in bubble.text().lower()


def test_controller_failure_finalizes_streaming_rich_html(qapp: QApplication, qtbot) -> None:
    """Provider failure preserves streamed text and renders rich markdown."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _ChatControllerHost(panel)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("trace", "")
    panel.append_assistant_chunk("", "**Hi**")
    _flush_stream_chunks(qtbot)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.is_content_streaming()
    host._on_ai_chat_failed("sess-1", "boom", "", "")
    assert not bubble.is_content_streaming()
    assert bubble.thinking_text() == "trace"
    body = bubble.findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    html = body.toHtml().lower()
    assert "font-weight:600" in html or "font-weight:700" in html
    assert "boom" in bubble.text().lower()
