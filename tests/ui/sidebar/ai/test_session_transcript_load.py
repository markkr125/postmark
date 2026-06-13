"""Tests for async session transcript loading."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from services.ai.chat.session_service import AiChatMessageDict, AiChatSessionLoadDict
from tests.ui.sidebar.ai.conftest import load_transcript_sync
from ui.main_window.ai_chat_controller import _AiChatControllerMixin
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble


def _session_row(session_id: str, title: str) -> dict[str, Any]:
    """Build a minimal session dict for controller tests."""
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


def _long_messages(count: int) -> list[AiChatMessageDict]:
    """Build alternating turns with fenced code for load stress tests."""
    messages: list[AiChatMessageDict] = []
    for index in range(count):
        role = "user" if index % 2 == 0 else "assistant"
        body = (
            f"{role} line {index}\n```python\nprint('block')\n```\n" * 2
            if role == "assistant"
            else f"Question {index}?"
        )
        messages.append(
            {
                "id": index,
                "session_id": "s1",
                "role": role,
                "content": body,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
    return messages


class _Host(_AiChatControllerMixin):
    """Minimal controller host for session-load tests."""

    def __init__(self, panel: AiChatPanel) -> None:
        """Wire a panel as the right-sidebar chat surface."""
        self._right_sidebar = cast(Any, SimpleNamespace(ai_chat_panel=panel))
        self._active_ai_session_id = None
        self._session_load_generation = 0
        from PySide6.QtWidgets import QWidget as _QWidget

        parent = _QWidget()
        from ui.sidebar.ai.workers.session_load_worker import AiChatSessionLoader

        self._session_loader = AiChatSessionLoader(parent)


def test_lazy_markdown_defers_until_viewport_render(qapp: QApplication, qtbot) -> None:
    """Off-screen assistant rows defer Pygments until scrolled into view."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 120)
    messages = _long_messages(20)
    panel.prepare_transcript_load(lazy_markdown=True)
    panel.load_transcript_async(messages, generation=1, lazy_markdown=True)
    panel.flush_transcript_load()
    bodies = [
        bubble._markdown_body
        for bubble in panel.findChildren(ChatMessageBubble)
        if bubble.role == "assistant" and bubble._markdown_body is not None
    ]
    assert len(bodies) >= 4
    panel._scroll.verticalScrollBar().setValue(0)
    qapp.processEvents()
    panel._render_visible_lazy_markdown()
    assert any(body.is_render_deferred() for body in bodies)
    panel._scroll.verticalScrollBar().setValue(panel._scroll.verticalScrollBar().maximum())
    qapp.processEvents()
    panel._render_visible_lazy_markdown()
    assert any(not body.is_render_deferred() for body in bodies)


def test_activate_skips_reload_for_current_session(qapp: QApplication, qtbot) -> None:
    """Selecting the already-active session does not restart transcript load."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _Host(panel)
    host._active_ai_session_id = "sess-a"
    with patch.object(panel, "prepare_transcript_load") as prepare:
        host._activate_chat_session("sess-a")
    prepare.assert_not_called()


def test_session_load_finished_applies_chrome_before_transcript(qapp: QApplication, qtbot) -> None:
    """Worker completion updates title before incremental transcript build."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _Host(panel)
    payload = AiChatSessionLoadDict(
        session=cast(Any, _session_row("sess-b", "Rust HTTP")),
        messages=[
            {
                "id": 1,
                "session_id": "sess-b",
                "role": "user",
                "content": "hi",
                "created_at": "2026-01-01T00:00:00+00:00",
            },
        ],
    )
    host._session_load_generation = 1
    with patch.object(host, "_apply_session_chrome") as chrome:
        host._on_session_load_finished(1, payload)
    chrome.assert_called_once()
    assert host._active_ai_session_id == "sess-b"
    panel.flush_transcript_load()
    assert len(panel.findChildren(ChatMessageBubble)) == 1


def test_stale_session_load_generation_is_ignored(qapp: QApplication, qtbot) -> None:
    """Out-of-date worker results do not replace a newer session selection."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _Host(panel)
    host._session_load_generation = 2
    payload = AiChatSessionLoadDict(
        session=cast(Any, _session_row("old", "Old")),
        messages=[],
    )
    host._on_session_load_finished(1, payload)
    assert host._active_ai_session_id is None


def test_incremental_load_chunked_build_completes(qapp: QApplication, qtbot) -> None:
    """Chunked transcript load finishes with all rows present."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    messages = _long_messages(12)
    load_transcript_sync(panel, messages, qtbot)
    assert len(panel.findChildren(ChatMessageBubble)) == 12


def test_load_transcript_pins_scroll_to_bottom(qapp: QApplication, qtbot) -> None:
    """Session transcript load keeps the viewport at the newest messages."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 240)
    messages = _long_messages(24)
    panel.prepare_transcript_load(lazy_markdown=True)
    panel.load_transcript_async(messages, generation=1, lazy_markdown=True)
    panel.flush_transcript_load()
    qtbot.wait(10)
    bar = panel._scroll.verticalScrollBar()
    assert bar.maximum() > 0
    assert panel._is_pinned_to_bottom()


def test_transcript_loading_overlay_until_layout_finishes(qapp: QApplication, qtbot) -> None:
    """The line loading overlay stays visible until the transcript fully settles."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    messages = _long_messages(8)
    panel.prepare_transcript_load(lazy_markdown=True)
    assert panel._transcript_loading.is_loading_visible()
    panel.load_transcript_async(messages, generation=1, lazy_markdown=True)
    panel.flush_transcript_load()
    qtbot.wait(10)
    assert not panel._transcript_loading.is_loading_visible()
    assert len(panel.findChildren(ChatMessageBubble)) == 8


def test_hidden_panel_defers_bottom_scroll_until_shown(qapp: QApplication, qtbot) -> None:
    """Startup-style restore pins the bottom once the transcript viewport is visible."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    messages = _long_messages(16)
    panel.prepare_transcript_load(lazy_markdown=True)
    panel.load_transcript_async(messages, generation=1, lazy_markdown=True)
    panel.flush_transcript_load()
    assert panel._pending_transcript_bottom_scroll
    panel.show()
    panel.resize(360, 240)
    qtbot.waitExposed(panel)
    qapp.processEvents()
    panel._finish_transcript_bottom_scroll()
    qapp.processEvents()
    bar = panel._scroll.verticalScrollBar()
    assert panel._is_pinned_to_bottom(), f"val={bar.value()} max={bar.maximum()}"
    assert not panel._pending_transcript_bottom_scroll
