"""End-to-end controller tests for registry-backed chat streaming."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import cast

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from services.ai.chat.session_service import AiChatSessionDict
from ui.main_window.ai_chat_controller import _AiChatControllerMixin
from ui.sidebar import RightSidebar
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble

_FINAL_TEXT = "Hello world"
_CHUNK_PARTS = ("Hel", "lo ", "wor", "ld")


class _StagedStreamingWorker(QObject):
    """Fake worker that streams staged chunks while ``run()`` is still blocking."""

    chunk_received = Signal(str, str)
    assistant_finished = Signal(str, str)
    failed = Signal(str, str, str)
    status_changed = Signal(str)
    usage_updated = Signal(object)
    context_compacted = Signal()

    def set_run(self, **kwargs: object) -> None:
        self._kwargs = kwargs

    def cancel(self) -> None:
        return

    def run(self) -> None:
        for part in _CHUNK_PARTS:
            self.chunk_received.emit("", part)
            time.sleep(0.08)
        self.assistant_finished.emit("", _FINAL_TEXT)


class _ControllerQObjectHost(QObject, _AiChatControllerMixin):
    """QObject-backed host used to exercise real controller wiring."""

    _ai_assistant_finish_requested = Signal(str, int, str, str)
    _ai_chat_fail_requested = Signal(str, int, str, str, str)
    _ai_title_ready_requested = Signal(str)

    def __init__(self, sidebar: RightSidebar) -> None:
        """Initialise the real controller wiring against *sidebar*."""
        super().__init__()
        self._right_sidebar = sidebar
        self._init_ai_chat_controller()

    def _cleanup_ai_chat_threads(self) -> None:
        """Stop all registry workers (test teardown helper)."""
        self._chat_run_registry.cancel_all()


def _session_row(session_id: str, title: str = "Title") -> AiChatSessionDict:
    """Build a minimal session dict for streaming tests."""
    return AiChatSessionDict(
        id=session_id,
        title=title,
        model_id="m1",
        mode="agent",
        agent_id="postmark-assistant",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        last_preview=None,
        archived=False,
    )


def _enable_models(panel) -> None:
    """Install one enabled model on the chat panel."""
    panel.set_models(
        [
            {
                "id": "m1",
                "provider": "openai",
                "label": "GPT-4o",
                "model": "openai/gpt-4o",
                "base_url": "",
                "api_version": "",
                "auth_kind": "none",
                "auth_ref": "",
                "context": 128_000,
                "enabled": True,
            }
        ]
    )


@pytest.fixture(autouse=True)
def _patch_streaming_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route all controller sends through the staged streaming worker."""
    monkeypatch.setattr(
        "services.ai.chat.run_registry.AiChatWorker",
        _StagedStreamingWorker,
    )


@pytest.fixture(autouse=True)
def _shutdown_ai_sidebar_workers(qtbot, qapp) -> Iterator[None]:
    """Stop context-usage loader threads left by controller integration tests."""
    yield
    for widget in qapp.topLevelWidgets():
        panel = getattr(widget, "ai_chat_panel", None)
        if panel is not None and hasattr(panel, "_shutdown_context_usage_worker"):
            panel._shutdown_context_usage_worker()
    qtbot.wait(200)
    qapp.processEvents()


def _wire_session_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_a: str,
    session_b: str,
) -> None:
    """Patch session service helpers for parallel chat sessions."""
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.record_user_message",
        lambda session_id, text, **kwargs: {
            "id": 1 if session_id == session_a else 2,
            "session_id": session_id,
            "role": "user",
            "content": text,
        },
    )
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.get_session",
        lambda session_id: _session_row(session_id),
    )
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.new_session",
        lambda entry, mode, first_message="": _session_row(
            session_b,
            first_message or "New",
        ),
    )


def _assistant_bubble(panel: AiChatPanel) -> ChatMessageBubble:
    """Return the newest assistant bubble in the transcript."""
    bubbles = panel.findChildren(ChatMessageBubble)
    assert bubbles
    return cast(ChatMessageBubble, bubbles[-1])


def test_message_submitted_streams_incrementally_same_session(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_on_ai_message_submitted`` must stream text before the worker exits."""
    session_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    _wire_session_mocks(monkeypatch, session_a=session_id, session_b="unused-bbbb")
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
    _enable_models(panel)
    host._active_ai_session_id = session_id

    host._on_ai_message_submitted("hi")
    handle = host._chat_run_registry.run_for(session_id)
    assert handle is not None

    def _partial_text_while_running() -> bool:
        if not handle.thread.isRunning():
            return False
        bubble = _assistant_bubble(panel)
        return 0 < len(bubble.text()) < len(_FINAL_TEXT)

    qtbot.waitUntil(_partial_text_while_running, timeout=3000)
    bubble = _assistant_bubble(panel)
    assert not bubble.is_activity_visible()
    host._cleanup_ai_chat_threads()
    qtbot.wait(300)
    qapp.processEvents()


def test_message_submitted_final_text_after_finish(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After the worker finishes, the assistant bubble shows the full reply."""
    session_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    _wire_session_mocks(monkeypatch, session_a=session_id, session_b="unused-bbbb")
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
    _enable_models(panel)
    host._active_ai_session_id = session_id

    host._on_ai_message_submitted("hi")
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 0, timeout=5000)
    qtbot.wait(100)
    qapp.processEvents()

    bubble = _assistant_bubble(panel)
    assert bubble.text() == _FINAL_TEXT
    assert panel._open_stream_generation == 0
    host._cleanup_ai_chat_threads()


def test_concurrent_run_visible_session_still_streams(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The visible session must stream while another session runs in background."""
    session_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    session_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    _wire_session_mocks(monkeypatch, session_a=session_a, session_b=session_b)
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
    _enable_models(panel)

    host._active_ai_session_id = session_a
    host._on_ai_message_submitted("first")
    qtbot.waitUntil(lambda: host._chat_run_registry.is_running(session_a), timeout=3000)

    host._on_ai_new_chat()
    host._on_ai_message_submitted("second")
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 2, timeout=3000)

    handle_b = host._chat_run_registry.run_for(session_b)
    assert handle_b is not None

    def _session_b_streams() -> bool:
        if not handle_b.thread.isRunning():
            return False
        return 0 < len(_assistant_bubble(panel).text()) < len(_FINAL_TEXT)

    qtbot.waitUntil(_session_b_streams, timeout=3000)
    assert host._chat_run_registry.is_running(session_a)
    host._cleanup_ai_chat_threads()
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 0, timeout=5000)


def test_switch_back_to_running_session_replays_buffer_then_streams(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returning to a running session replays buffered text from the registry."""
    session_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    session_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    _wire_session_mocks(monkeypatch, session_a=session_a, session_b=session_b)
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
    _enable_models(panel)

    host._active_ai_session_id = session_a
    host._on_ai_message_submitted("first")
    qtbot.waitUntil(lambda: host._chat_run_registry.is_running(session_a), timeout=3000)

    host._on_ai_new_chat()
    host._on_ai_message_submitted("second")
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 2, timeout=3000)

    handle_a = host._chat_run_registry.run_for(session_a)
    assert handle_a is not None
    qtbot.waitUntil(
        lambda: len(handle_a.content_buffer) >= len(_FINAL_TEXT),
        timeout=3000,
    )

    host._active_ai_session_id = session_a
    host._reattach_session_run_if_needed(session_a)
    qtbot.wait(80)
    qapp.processEvents()

    bubble = _assistant_bubble(panel)
    assert bubble.text() == handle_a.content_buffer
    host._cleanup_ai_chat_threads()
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 0, timeout=5000)
