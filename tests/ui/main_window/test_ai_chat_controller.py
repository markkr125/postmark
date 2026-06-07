"""Tests for AI chat controller finalize paths on the GUI thread."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from PySide6.QtWidgets import QApplication, QTextBrowser

from ui.main_window.ai_chat_controller import _AiChatControllerMixin
from ui.sidebar import RightSidebar
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble


def _flush_stream_chunks(qtbot) -> None:
    """Wait for the coalesced chunk delivery timer (~50ms)."""
    qtbot.wait(60)


class _ChatControllerHost(_AiChatControllerMixin):
    """Minimal host exposing controller methods for panel integration tests."""

    def __init__(self, panel: AiChatPanel, session_id: str = "sess-1") -> None:
        """Wire a panel as the right-sidebar chat surface."""
        self._right_sidebar = cast(
            RightSidebar,
            SimpleNamespace(ai_chat_panel=panel),
        )
        self._active_ai_session_id = session_id


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
    browser = bubble.findChild(QTextBrowser, "aiChatAssistantText")
    assert browser is not None
    html = browser.toHtml().lower()
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
    browser = bubble.findChild(QTextBrowser, "aiChatAssistantText")
    assert browser is not None
    html = browser.toHtml().lower()
    assert "font-weight:600" in html or "font-weight:700" in html
    assert "boom" in bubble.text().lower()
