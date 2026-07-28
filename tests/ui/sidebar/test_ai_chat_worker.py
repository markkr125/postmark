"""Tests for AiChatWorker."""

from __future__ import annotations

import types

import pytest
from PySide6.QtCore import QObject, QThread, Qt, Slot
from PySide6.QtWidgets import QApplication

from services.ai.ai_config import AiModelEntry
from services.ai.chat.response_text import AssistantParts
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.workers.chat_worker import AiChatWorker


class _ChunkThreadRecorder(QObject):
    """Records which thread receives queued ``chunk_received`` deliveries."""

    def __init__(self) -> None:
        """Initialise an empty delivery-thread log."""
        super().__init__()
        self.threads: list[QThread | None] = []

    @Slot(str, str)
    def record(self, _thinking: str, _content: str) -> None:
        """Append :class:`QThread.currentThread` for each queued chunk."""
        self.threads.append(QThread.currentThread())


def _entry() -> AiModelEntry:
    return {
        "id": "id1",
        "provider": "openai",
        "label": "L",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
    }


def test_set_run_keeps_the_prompt_verbatim(qapp: QApplication) -> None:
    """The turn sends what the user wrote; documents are read from storage instead."""
    session_id = "00000000-0000-4000-8000-0000000000fe"
    worker = AiChatWorker()
    prompt = "Import this\n\nAttached files:\n- spec.pdf -> postmark://uploaded/spec.md"
    worker.set_run(
        session_id=session_id,
        entry=_entry(),
        agent_id="postmark-assistant",
        text=prompt,
    )
    assert worker._text == prompt


def _install_fake_conversation(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    captured: dict[str, object] = {"closed": False}

    class _State:
        def __init__(self) -> None:
            self.events: list[object] = []

    class _Conv:
        def __init__(self, **kw: object) -> None:
            captured["kw"] = kw
            self._kw = kw
            self.state = _State()
            self.state.events = []

        def send_message(self, text: str) -> None:
            captured["sent"] = text

        async def arun(self) -> None:
            token_cbs = self._kw.get("token_callbacks", [])
            if not isinstance(token_cbs, list):
                token_cbs = []
            for cb in token_cbs:
                chunk = types.SimpleNamespace(
                    choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content="Hi"))]
                )
                cb(chunk)

        def close(self) -> None:
            captured["closed"] = True

        def interrupt(self) -> None:
            captured["interrupted"] = True

    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.AiChatSessionService.build_conversation",
        lambda *a, **k: _Conv(**k),
    )
    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.resolve_assistant_parts",
        lambda _conv, _think, _content: AssistantParts("", "Full reply"),
    )
    return captured


def test_worker_flushes_final_tail_before_finish(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any thinking/content missing from stream deltas is flushed before finish."""
    captured: dict[str, object] = {"closed": False}

    class _Conv:
        def __init__(self, **kw: object) -> None:
            captured["kw"] = kw
            self.state = types.SimpleNamespace(events=[])

        def send_message(self, text: str) -> None:
            captured["sent"] = text

        async def arun(self) -> None:
            kw = captured.get("kw")
            token_cbs = kw.get("token_callbacks", []) if isinstance(kw, dict) else []
            if isinstance(token_cbs, list):
                for cb in token_cbs:
                    chunk = types.SimpleNamespace(
                        choices=[
                            types.SimpleNamespace(
                                delta=types.SimpleNamespace(
                                    reasoning_content="Partial",
                                    content=None,
                                )
                            )
                        ]
                    )
                    cb(chunk)

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.AiChatSessionService.build_conversation",
        lambda *a, **k: _Conv(**k),
    )
    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.resolve_assistant_parts",
        lambda _conv, _think, _content: AssistantParts(
            "Partial thinking tail",
            "Full reply",
        ),
    )

    chunks: list[tuple[str, str]] = []
    worker = AiChatWorker()
    worker.set_run(
        session_id="00000000-0000-4000-8000-000000000001",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="Hello",
    )
    worker.chunk_received.connect(lambda thinking, content: chunks.append((thinking, content)))
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.assistant_finished.connect(thread.quit)
    with qtbot.waitSignal(worker.assistant_finished, timeout=5000):
        thread.start()
    thread.wait(5000)

    assert chunks == [("Partial", ""), (" thinking tail", "Full reply")]
    assert captured["closed"] is True


def test_chunk_received_runs_panel_delivery_on_gui_thread(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``deliver_assistant_chunk`` must run on the GUI thread (QueuedConnection)."""
    _install_fake_conversation(monkeypatch)
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    gui_thread = qapp.thread()
    recorder = _ChunkThreadRecorder()

    worker = AiChatWorker()
    worker.set_run(
        session_id="00000000-0000-4000-8000-000000000001",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="Hello",
    )
    queued = Qt.ConnectionType.QueuedConnection
    worker.chunk_received.connect(recorder.record, queued)
    worker.chunk_received.connect(panel.deliver_assistant_chunk, queued)

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.assistant_finished.connect(thread.quit, queued)
    with qtbot.waitSignal(worker.assistant_finished, timeout=5000):
        thread.start()
    thread.wait(5000)
    for _ in range(50):
        qapp.processEvents()
        if recorder.threads:
            break
    qtbot.wait(60)
    qapp.processEvents()

    assert recorder.threads
    assert all(t == gui_thread for t in recorder.threads)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.text() == "Hill reply"


def test_direct_chunk_delivery_is_marshaled_to_gui_thread(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A direct worker callback must not mutate chat widgets off-thread."""
    _install_fake_conversation(monkeypatch)
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()

    worker = AiChatWorker()
    worker.set_run(
        session_id="00000000-0000-4000-8000-000000000001",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="Hello",
    )
    worker.chunk_received.connect(
        panel.deliver_assistant_chunk,
        Qt.ConnectionType.DirectConnection,
    )

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.assistant_finished.connect(thread.quit, Qt.ConnectionType.QueuedConnection)
    with qtbot.waitSignal(worker.assistant_finished, timeout=5000):
        thread.start()
    thread.wait(5000)
    for _ in range(50):
        qapp.processEvents()
    qtbot.wait(60)
    qapp.processEvents()

    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.text() == "Hill reply"


def test_worker_streams_and_finishes(qapp: QApplication, qtbot, monkeypatch) -> None:
    """Worker emits chunks, final text, and closes the conversation."""
    captured = _install_fake_conversation(monkeypatch)
    chunks: list[tuple[str, str]] = []
    finals: list[tuple[str, str]] = []

    worker = AiChatWorker()
    worker.set_run(
        session_id="00000000-0000-4000-8000-000000000001",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="Hello",
    )
    worker.chunk_received.connect(lambda thinking, content: chunks.append((thinking, content)))
    worker.assistant_finished.connect(lambda thinking, content: finals.append((thinking, content)))

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.assistant_finished.connect(thread.quit)
    with qtbot.waitSignal(worker.assistant_finished, timeout=5000):
        thread.start()
    thread.wait(5000)

    assert chunks == [("", "Hi"), ("", "ll reply")]
    assert finals == [("", "Full reply")]
    assert captured["closed"] is True


def test_worker_emits_status_changed(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OpenHands event callbacks emit status_changed for the activity row."""
    captured: dict[str, object] = {}

    class _Conv:
        def __init__(self, **kw: object) -> None:
            captured["kw"] = kw
            self.state = types.SimpleNamespace(events=[])

        def send_message(self, text: str) -> None:
            pass

        async def arun(self) -> None:
            kw = captured.get("kw")
            event_cbs = kw.get("callbacks", []) if isinstance(kw, dict) else []
            if isinstance(event_cbs, list):
                for cb in event_cbs:
                    cb(types.SimpleNamespace(status="planning"))

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.AiChatSessionService.build_conversation",
        lambda *a, **k: _Conv(**k),
    )
    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.resolve_assistant_parts",
        lambda _conv, _think, _content: AssistantParts("", "Full reply"),
    )

    statuses: list[str] = []
    worker = AiChatWorker()
    worker.set_run(
        session_id="00000000-0000-4000-8000-000000000001",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="Hello",
    )
    worker.status_changed.connect(statuses.append)

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.assistant_finished.connect(thread.quit)
    with qtbot.waitSignal(worker.assistant_finished, timeout=5000):
        thread.start()
    thread.wait(5000)

    assert statuses == ["planning"]


def test_worker_closes_before_finish_signal(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Conversation.close() runs before assistant_finished is delivered."""
    order: list[str] = []

    class _Conv:
        def __init__(self, **kw: object) -> None:
            self._kw = kw
            self.state = types.SimpleNamespace(events=[])

        def send_message(self, text: str) -> None:
            pass

        async def arun(self) -> None:
            pass

        def close(self) -> None:
            order.append("close")

    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.AiChatSessionService.build_conversation",
        lambda *a, **k: _Conv(**k),
    )
    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.resolve_assistant_parts",
        lambda _conv, _think, _content: AssistantParts("", "Full reply"),
    )

    worker = AiChatWorker()
    worker.set_run(
        session_id="00000000-0000-4000-8000-000000000001",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="Hello",
    )
    worker.assistant_finished.connect(lambda _thinking, _content: order.append("emit"))

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.assistant_finished.connect(thread.quit)
    with qtbot.waitSignal(worker.assistant_finished, timeout=5000):
        thread.start()
    thread.wait(5000)

    assert order == ["close", "emit"]


def test_worker_cancel_interrupts_conversation() -> None:
    """cancel() forwards to Conversation.interrupt when a run is active."""
    interrupted = False

    class _Conv:
        def interrupt(self) -> None:
            nonlocal interrupted
            interrupted = True

    worker = AiChatWorker()
    worker._conv = _Conv()  # type: ignore[assignment]
    worker.cancel()
    assert interrupted is True
    assert worker._stop_requested is True


def test_worker_stop_emits_failed(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stopping a run emits failed('Stopped') instead of hanging."""
    import asyncio

    class _Conv:
        def __init__(self, **kw: object) -> None:
            self._kw = kw
            self.state = types.SimpleNamespace(events=[])
            self._task: asyncio.Task[None] | None = None

        def send_message(self, text: str) -> None:
            pass

        async def arun(self) -> None:
            self._task = asyncio.current_task()
            try:
                while True:
                    await asyncio.sleep(0.02)
            except asyncio.CancelledError:
                return

        def interrupt(self) -> None:
            task = self._task
            if task is not None and not task.done():
                task.cancel()

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.AiChatSessionService.build_conversation",
        lambda *a, **k: _Conv(**k),
    )

    worker = AiChatWorker()
    worker.set_run(
        session_id="00000000-0000-4000-8000-000000000001",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="Hello",
    )
    errors: list[tuple[str, str, str]] = []
    worker.failed.connect(lambda err, thinking, content: errors.append((err, thinking, content)))

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.failed.connect(thread.quit)
    thread.start()

    with qtbot.waitSignal(worker.failed, timeout=5000):
        qtbot.wait(50)
        worker.cancel()

    thread.wait(5000)
    assert errors and errors[0][0] == "Stopped"


def test_worker_failure_emits_partial_text(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failures include streamed assistant text collected before the error."""
    captured: dict[str, object] = {"closed": False}

    class _Conv:
        def __init__(self, **kw: object) -> None:
            self._kw = kw
            self.state = types.SimpleNamespace(events=[])

        def send_message(self, text: str) -> None:
            pass

        async def arun(self) -> None:
            token_cbs = self._kw.get("token_callbacks", [])
            if isinstance(token_cbs, list):
                for cb in token_cbs:
                    chunk = types.SimpleNamespace(
                        choices=[
                            types.SimpleNamespace(
                                delta=types.SimpleNamespace(
                                    reasoning_content=None,
                                    content="Partial",
                                )
                            )
                        ]
                    )
                    cb(chunk)
            raise RuntimeError("provider boom")

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.AiChatSessionService.build_conversation",
        lambda *a, **k: _Conv(**k),
    )
    worker = AiChatWorker()
    worker.set_run(
        session_id="00000000-0000-4000-8000-000000000001",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="Hello",
    )
    failures: list[tuple[str, str, str]] = []
    worker.failed.connect(lambda err, thinking, content: failures.append((err, thinking, content)))

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.failed.connect(thread.quit)
    with qtbot.waitSignal(worker.failed, timeout=5000):
        thread.start()
    thread.wait(5000)

    assert failures
    assert "boom" in failures[0][0]
    assert failures[0][1] == ""
    assert failures[0][2] == "Partial"
    assert captured["closed"] is True


def test_worker_emits_usage_updated_after_arun(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Successful runs emit SDK usage metrics after ``arun()`` completes."""

    class _Conv:
        def __init__(self, **kw: object) -> None:
            self._kw = kw
            self.state = types.SimpleNamespace(events=[])

        def send_message(self, _text: str) -> None:
            pass

        async def arun(self) -> None:
            return

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.AiChatSessionService.build_conversation",
        lambda *a, **k: _Conv(**k),
    )
    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.resolve_assistant_parts",
        lambda _conv, _think, _content: AssistantParts("", "Full reply"),
    )
    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.metrics_from_conversation",
        lambda _conv, _session_id, **_kw: {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "reasoning_tokens": 2,
        },
    )

    updates: list[object] = []
    worker = AiChatWorker()
    worker.set_run(
        session_id="00000000-0000-4000-8000-000000000001",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="Hello",
    )
    worker.usage_updated.connect(updates.append)

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.assistant_finished.connect(thread.quit)
    with qtbot.waitSignal(worker.assistant_finished, timeout=5000):
        thread.start()
    thread.wait(5000)

    assert updates == [{"prompt_tokens": 10, "completion_tokens": 5, "reasoning_tokens": 2}]


def test_worker_emits_summarizing_status_and_context_compacted(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Condenser events show the mandatory status label and compaction signal."""
    from openhands.sdk.event.condenser import Condensation, CondensationRequest

    captured: dict[str, object] = {}

    class _Conv:
        def __init__(self, **kw: object) -> None:
            captured["kw"] = kw
            self.state = types.SimpleNamespace(events=[])

        def send_message(self, _text: str) -> None:
            pass

        async def arun(self) -> None:
            kw = captured.get("kw")
            event_cbs = kw.get("callbacks", []) if isinstance(kw, dict) else []
            if isinstance(event_cbs, list):
                for cb in event_cbs:
                    cb(CondensationRequest())
                    cb(
                        Condensation(
                            forgotten_event_ids={"a"},
                            summary="summary",
                            summary_offset=1,
                            llm_response_id="resp-1",
                        )
                    )

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.AiChatSessionService.build_conversation",
        lambda *a, **k: _Conv(**k),
    )
    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.resolve_assistant_parts",
        lambda _conv, _think, _content: AssistantParts("", "Full reply"),
    )
    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.metrics_from_conversation",
        lambda _conv, _session_id, **_kw: None,
    )

    statuses: list[str] = []
    compacted: list[bool] = []
    worker = AiChatWorker()
    worker.set_run(
        session_id="00000000-0000-4000-8000-000000000001",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="Hello",
    )
    worker.status_changed.connect(statuses.append)
    worker.context_compacted.connect(lambda: compacted.append(True))

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.assistant_finished.connect(thread.quit)
    with qtbot.waitSignal(worker.assistant_finished, timeout=5000):
        thread.start()
    thread.wait(5000)

    assert "Summarizing earlier messages…" in statuses
    assert compacted == [True]


def test_worker_cancel_before_build_emits_stopped(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stop requested before conversation build emits failed without building."""

    def _fail_build(*_args: object, **_kwargs: object) -> object:
        msg = "build_conversation should not run after pre-build cancel"
        raise AssertionError(msg)

    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.AiChatSessionService.build_conversation",
        _fail_build,
    )
    worker = AiChatWorker()
    worker.set_run(
        session_id="00000000-0000-4000-8000-000000000001",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="Hello",
    )
    worker.cancel()
    failures: list[str] = []
    worker.failed.connect(lambda message, _thinking, _content: failures.append(message))
    worker.run()
    assert failures == ["Stopped"]
