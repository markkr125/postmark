"""Streaming delivery tests for :class:`ChatRunRegistry`."""

from __future__ import annotations

import asyncio
import inspect
import time
import types
from collections.abc import Iterator
from itertools import pairwise

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from services.ai.ai_config import AiModelEntry
from services.ai.chat.response_text import AssistantParts
from services.ai.chat.run_registry import AiChatRunContext, ChatRunHandle, ChatRunRegistry
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.workers.chat_worker import AiChatWorker

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


class _StatusStreamingWorker(_StagedStreamingWorker):
    """Emit activity status mid-run before streaming chunks."""

    def run(self) -> None:
        time.sleep(0.04)
        self.status_changed.emit("Planning")
        super().run()


def _entry() -> AiModelEntry:
    return AiModelEntry(
        id="m1",
        provider="openai",
        label="GPT",
        model="openai/gpt-4o",
        base_url="",
        api_version="",
        auth_kind="none",
        auth_ref="",
        context=128_000,
        enabled=True,
    )


def _start_registry_run(
    registry: ChatRunRegistry,
    *,
    session_id: str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
) -> ChatRunHandle:
    """Start one staged streaming run and return its handle."""
    run_generation = registry.next_run_generation()
    handle = registry.start_run(
        session_id=session_id,
        run_generation=run_generation,
        user_message_id=1,
        user_text="hi",
        model_id="m1",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="hi",
        composer=None,
    )
    assert handle is not None
    return handle


def _connect_panel_for_session(
    registry: ChatRunRegistry,
    panel: AiChatPanel,
    session_id: str,
) -> None:
    """Mirror controller routing for one visible session."""

    def _on_chunk(
        routed_session_id: str,
        _run_generation: int,
        thinking: str,
        content: str,
    ) -> None:
        if routed_session_id == session_id:
            panel.deliver_assistant_chunk(thinking, content)

    def _on_status(
        routed_session_id: str,
        _run_generation: int,
        status: str,
    ) -> None:
        if routed_session_id == session_id:
            panel.deliver_activity_status(status)

    queued = Qt.ConnectionType.QueuedConnection
    registry.chunk_received.connect(_on_chunk, queued)
    registry.status_changed.connect(_on_status, queued)


@pytest.fixture(autouse=True)
def _patch_streaming_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use staged workers for every registry streaming test."""
    monkeypatch.setattr(
        "services.ai.chat.run_registry.AiChatWorker",
        _StagedStreamingWorker,
    )


@pytest.fixture
def registry_panel(qapp: QApplication, qtbot) -> Iterator[tuple[ChatRunRegistry, AiChatPanel]]:
    """Registry plus panel wired for one session."""
    registry = ChatRunRegistry()
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    session_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    _connect_panel_for_session(registry, panel, session_id)
    yield registry, panel
    if registry.count_running():
        registry.cancel_all()
        qtbot.wait(500)
    qapp.processEvents()


def test_start_run_does_not_connect_worker_signals_with_lambda() -> None:
    """Worker→GUI cross-thread signals must use @Slot bridges, not lambdas."""
    source = inspect.getsource(ChatRunRegistry.start_run)
    assert "lambda" not in source, (
        "ChatRunRegistry.start_run must not use lambda connections for worker "
        "signals — QueuedConnection defers delivery until run() returns"
    )


def test_registry_chunk_bridge_delivers_before_run_returns(
    qapp: QApplication,
    qtbot,
    registry_panel: tuple[ChatRunRegistry, AiChatPanel],
) -> None:
    """``chunk_received`` must fire while the worker thread is still running."""
    registry, _panel = registry_panel
    chunk_calls: list[tuple[str, str]] = []
    registry.chunk_received.connect(
        lambda _sid, _gen, thinking, content: chunk_calls.append((thinking, content))
    )
    handle = _start_registry_run(registry)
    delivered_while_running = False

    def _poll() -> bool:
        nonlocal delivered_while_running
        if chunk_calls and handle.thread.isRunning():
            delivered_while_running = True
            return True
        return bool(chunk_calls) and not handle.thread.isRunning()

    qtbot.waitUntil(_poll, timeout=3000)
    assert delivered_while_running, f"chunks batched until thread exit: {chunk_calls}"
    qtbot.waitUntil(lambda: registry.count_running() == 0, timeout=3000)


def test_registry_chunk_bridge_updates_panel_incrementally(
    qapp: QApplication,
    qtbot,
    registry_panel: tuple[ChatRunRegistry, AiChatPanel],
) -> None:
    """Panel text must grow before the worker finishes."""
    registry, panel = registry_panel
    panel.begin_assistant_stream()
    _start_registry_run(registry)

    def _partial_text_visible() -> bool:
        length = len(panel.streaming_assistant_text())
        return 0 < length < len(_FINAL_TEXT)

    qtbot.waitUntil(_partial_text_visible, timeout=3000)
    qtbot.waitUntil(lambda: registry.count_running() == 0, timeout=3000)
    qtbot.wait(80)
    qapp.processEvents()
    assert panel.streaming_assistant_text() == _FINAL_TEXT


def test_registry_chunk_bridge_monotonic_growth(
    qapp: QApplication,
    qtbot,
    registry_panel: tuple[ChatRunRegistry, AiChatPanel],
) -> None:
    """Bubble text length must increase at least twice before completion."""
    registry, panel = registry_panel
    panel.begin_assistant_stream()
    _start_registry_run(registry)
    samples: list[int] = []
    for _ in range(12):
        qtbot.wait(50)
        samples.append(len(panel.streaming_assistant_text()))
    qtbot.waitUntil(lambda: registry.count_running() == 0, timeout=3000)
    increases = sum(1 for prev, cur in pairwise(samples) if cur > prev)
    assert increases >= 2, f"expected monotonic growth, got lengths {samples}"
    assert samples[-1] == len(_FINAL_TEXT)


def test_registry_status_bridge_delivers_before_run_returns(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    registry_panel: tuple[ChatRunRegistry, AiChatPanel],
) -> None:
    """Activity status must reach the panel before the turn finishes."""
    monkeypatch.setattr(
        "services.ai.chat.run_registry.AiChatWorker",
        _StatusStreamingWorker,
    )
    registry, panel = registry_panel
    panel.begin_assistant_stream()
    handle = _start_registry_run(registry)
    saw_status_while_running = False

    def _poll() -> bool:
        nonlocal saw_status_while_running
        bubble = panel.findChildren(ChatMessageBubble)[-1]
        if bubble.activity_message() == "Planning…" and handle.thread.isRunning():
            saw_status_while_running = True
            return True
        return not handle.thread.isRunning()

    qtbot.waitUntil(_poll, timeout=3000)
    assert saw_status_while_running
    qtbot.waitUntil(lambda: registry.count_running() == 0, timeout=3000)


def test_registry_buffers_chunks_while_background_session(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Background session chunks buffer in the handle for later reattach."""
    monkeypatch.setattr(
        "services.ai.chat.run_registry.AiChatWorker",
        _StagedStreamingWorker,
    )
    session_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    session_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    registry = ChatRunRegistry()
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    _connect_panel_for_session(registry, panel, session_a)

    handle_b = _start_registry_run(registry, session_id=session_b)
    qtbot.waitUntil(
        lambda: len(handle_b.content_buffer) >= len(_FINAL_TEXT),
        timeout=3000,
    )
    assert len(panel.streaming_assistant_text()) == 0

    panel.begin_assistant_stream()
    panel.resume_assistant_stream(
        handle_b.thinking_buffer,
        handle_b.content_buffer,
        status=handle_b.status_text,
    )
    assert panel.streaming_assistant_text() == handle_b.content_buffer
    registry.cancel_all()
    qtbot.waitUntil(lambda: registry.count_running() == 0, timeout=3000)


def test_background_reattach_preserves_thought_tool_thought_order(
    qapp: QApplication,
    qtbot,
) -> None:
    """Registry timeline retains interrupt boundaries while a session is hidden."""
    session_id = "background-timeline"
    registry = ChatRunRegistry()
    context = AiChatRunContext(session_id, 1, "inspect", 1, "model")
    handle = ChatRunHandle(
        context=context,
        thread=None,  # type: ignore[arg-type]
        worker=None,  # type: ignore[arg-type]
        thread_generation=1,
        bridge=None,  # type: ignore[arg-type]
    )
    registry._handles[session_id] = handle
    registry._on_chunk(session_id, 1, "Plan query.", "")
    registry._on_tool_activity_updated(
        session_id,
        1,
        [
            {
                "id": "query-1",
                "tool_name": "postmark_workspace_query",
                "title": "Query workspace",
                "detail": "overview",
                "status": "completed",
            }
        ],
    )
    registry._on_chunk(session_id, 1, "Inspect result.", "")

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resume_assistant_stream(
        handle.thinking_buffer,
        handle.content_buffer,
        tool_activity_records=handle.tool_activity_records,
        thinking_phases=handle.thinking_phases,
        activity_timeline=handle.activity_timeline,
    )
    bubble = panel._streaming_bubble
    assert bubble is not None
    first_thought, second_thought = bubble._thought_sections
    tool_group = bubble._tool_activity_groups[0]
    outer = bubble._assistant_outer
    assert outer is not None
    assert first_thought.text() == "Plan query."
    assert second_thought.text() == "Inspect result."
    assert outer.indexOf(first_thought) < outer.indexOf(tool_group)
    assert outer.indexOf(tool_group) < outer.indexOf(second_thought)
    registry._handles.pop(session_id, None)


def _install_staged_token_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake OpenHands conversation that streams tokens in multiple async steps."""

    class _Conv:
        def __init__(self, **kw: object) -> None:
            self._kw = kw

        def send_message(self, text: str) -> None:
            return

        async def arun(self) -> None:
            token_cbs = self._kw.get("token_callbacks", [])
            if not isinstance(token_cbs, list):
                token_cbs = []
            for part in _CHUNK_PARTS:
                for cb in token_cbs:
                    chunk = types.SimpleNamespace(
                        choices=[
                            types.SimpleNamespace(
                                delta=types.SimpleNamespace(content=part),
                            )
                        ]
                    )
                    cb(chunk)
                await asyncio.sleep(0.08)

        def close(self) -> None:
            return

    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.AiChatSessionService.build_conversation",
        lambda *args, **kwargs: _Conv(**kwargs),
    )
    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.resolve_assistant_parts",
        lambda _conv, _think, _content: AssistantParts("", _FINAL_TEXT),
    )


def test_worker_streams_through_registry_to_panel(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    registry_panel: tuple[ChatRunRegistry, AiChatPanel],
) -> None:
    """Real ``AiChatWorker`` must stream through ``start_run`` before finishing."""
    _install_staged_token_conversation(monkeypatch)
    monkeypatch.setattr("services.ai.chat.run_registry.AiChatWorker", AiChatWorker)
    registry, panel = registry_panel
    panel.begin_assistant_stream()
    handle = _start_registry_run(registry)

    def _partial_text_while_running() -> bool:
        if not handle.thread.isRunning():
            return False
        return 0 < len(panel.streaming_assistant_text()) < len(_FINAL_TEXT)

    qtbot.waitUntil(_partial_text_while_running, timeout=5000)
    qtbot.waitUntil(lambda: registry.count_running() == 0, timeout=5000)
    qtbot.wait(80)
    qapp.processEvents()
    assert panel.streaming_assistant_text() == _FINAL_TEXT
