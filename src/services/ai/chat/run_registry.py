"""Registry of concurrent AI chat worker runs (at most one per session)."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from services.ai.ai_config import AiModelEntry
from services.ai.chat.response_text import merge_stream_text
from services.ai.chat.session_service import ComposerRunContext
from services.ai.chat.chat_run_limits import (
    DEFAULT_MAX_CONCURRENT_CHAT_RUNS,
    max_concurrent_chat_runs,
)
from ui.sidebar.ai.workers.chat_worker import AiChatWorker

MAX_CONCURRENT_CHAT_RUNS = DEFAULT_MAX_CONCURRENT_CHAT_RUNS


@dataclass
class ResearchTurnState:
    """Research progress + findings for one assistant turn."""

    progress_lines: list[str] = field(default_factory=list)
    findings_text: str = ""
    is_active: bool = False


@dataclass
class AiChatRunContext:
    """Snapshot of one in-flight user send for stop/finalize handling."""

    session_id: str
    user_message_id: int
    user_text: str
    run_generation: int
    model_id: str


@dataclass
class ChatRunHandle:
    """One background chat turn bound to a session id."""

    context: AiChatRunContext
    thread: QThread
    worker: AiChatWorker
    thread_generation: int
    bridge: _WorkerSignalBridge
    thinking_buffer: str = ""
    content_buffer: str = ""
    pending_sdk_metrics: object | None = None
    status_text: str = ""
    send_mode: str = "agent"
    research_state: ResearchTurnState | None = None


class _WorkerSignalBridge(QObject):
    """Queued worker→registry signal adapter with proper ``@Slot`` handlers."""

    def __init__(
        self,
        registry: ChatRunRegistry,
        *,
        session_id: str,
        run_generation: int,
        thread: QThread,
        worker: AiChatWorker,
        thread_generation: int,
        parent: QObject | None = None,
    ) -> None:
        """Bind one worker thread to *registry* fan-out signals."""
        super().__init__(parent)
        self._registry = registry
        self._session_id = session_id
        self._run_generation = run_generation
        self._thread = thread
        self._worker = worker
        self._thread_generation = thread_generation

    @Slot(str, str)
    def on_chunk(self, thinking: str, content: str) -> None:
        """Forward streaming text from the worker thread."""
        self._registry._on_chunk(
            self._session_id,
            self._run_generation,
            thinking,
            content,
        )

    @Slot(str)
    def on_status(self, status: str) -> None:
        """Forward SDK activity status from the worker thread."""
        self._registry._on_status(self._session_id, self._run_generation, status)

    @Slot(str)
    def on_research(self, payload: str) -> None:
        """Forward research UI updates from the worker thread."""
        self._registry._on_research(self._session_id, self._run_generation, payload)

    @Slot(object)
    def on_usage(self, metrics: object) -> None:
        """Forward SDK usage metrics from the worker thread."""
        self._registry._on_usage(self._session_id, self._run_generation, metrics)

    @Slot()
    def on_compacted(self) -> None:
        """Forward context compaction from the worker thread."""
        self._registry.context_compacted.emit(self._session_id, self._run_generation)

    @Slot(str, str)
    def on_finished(self, thinking: str, content: str) -> None:
        """Forward successful turn completion from the worker thread."""
        self._registry.assistant_finished.emit(
            self._session_id,
            self._run_generation,
            thinking,
            content,
        )

    @Slot(str, str, str)
    def on_failed(self, message: str, thinking: str, content: str) -> None:
        """Forward worker failure from the worker thread."""
        self._registry.failed.emit(
            self._session_id,
            self._run_generation,
            message,
            thinking,
            content,
        )

    @Slot()
    def on_thread_finished(self) -> None:
        """Release registry state after the worker thread exits."""
        self._registry._release(
            self._session_id,
            self._thread,
            self._worker,
            self._thread_generation,
        )


class ChatRunRegistry(QObject):
    """Own concurrent ``AiChatWorker`` + ``QThread`` pairs keyed by session id."""

    running_sessions_changed = Signal()
    chunk_received = Signal(str, int, str, str)
    status_changed = Signal(str, int, str)
    research_updated = Signal(str, int, str)
    usage_updated = Signal(str, int, object)
    context_compacted = Signal(str, int)
    assistant_finished = Signal(str, int, str, str)
    failed = Signal(str, int, str, str, str)
    run_finished = Signal(str, int)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialise an empty run registry."""
        super().__init__(parent)
        self._handles: dict[str, ChatRunHandle] = {}
        self._chat_run_generation = 0
        self._thread_generation = 0

    def count_running(self) -> int:
        """Return the number of in-flight session runs."""
        return len(self._handles)

    def running_session_ids(self) -> frozenset[str]:
        """Return session ids with active workers."""
        return frozenset(self._handles)

    def is_running(self, session_id: str | None) -> bool:
        """Return whether *session_id* has an active worker."""
        if not session_id:
            return False
        return session_id in self._handles

    def run_for(self, session_id: str) -> ChatRunHandle | None:
        """Return the active handle for *session_id*, if any."""
        return self._handles.get(session_id)

    def at_capacity(self) -> bool:
        """Return whether the advisory concurrent-run threshold is reached."""
        return len(self._handles) >= max_concurrent_chat_runs()

    def next_run_generation(self) -> int:
        """Allocate the next monotonic run generation id."""
        self._chat_run_generation += 1
        return self._chat_run_generation

    def start_run(
        self,
        *,
        session_id: str,
        run_generation: int,
        user_message_id: int,
        user_text: str,
        model_id: str,
        entry: AiModelEntry,
        agent_id: str,
        text: str,
        composer: ComposerRunContext | None,
    ) -> ChatRunHandle | None:
        """Start a worker for *session_id* or return ``None`` if already running."""
        if session_id in self._handles:
            return None

        context = AiChatRunContext(
            session_id=session_id,
            user_message_id=user_message_id,
            user_text=user_text,
            run_generation=run_generation,
            model_id=model_id,
        )

        worker = AiChatWorker()
        worker.set_run(
            session_id=session_id,
            entry=entry,
            agent_id=agent_id,
            text=text,
            composer=composer,
        )
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        self._thread_generation += 1
        thread_generation = self._thread_generation
        bridge = _WorkerSignalBridge(
            self,
            session_id=session_id,
            run_generation=run_generation,
            thread=thread,
            worker=worker,
            thread_generation=thread_generation,
            parent=self,
        )

        queued = Qt.ConnectionType.QueuedConnection
        worker.chunk_received.connect(bridge.on_chunk, queued)
        worker.status_changed.connect(bridge.on_status, queued)
        research_signal = getattr(worker, "research_updated", None)
        if research_signal is not None:
            research_signal.connect(bridge.on_research, queued)
        worker.usage_updated.connect(bridge.on_usage, queued)
        worker.context_compacted.connect(bridge.on_compacted, queued)
        worker.assistant_finished.connect(bridge.on_finished, queued)
        worker.failed.connect(bridge.on_failed, queued)
        worker.assistant_finished.connect(thread.quit, queued)
        worker.failed.connect(thread.quit, queued)
        thread.finished.connect(bridge.on_thread_finished, queued)

        handle = ChatRunHandle(
            context=context,
            thread=thread,
            worker=worker,
            thread_generation=thread_generation,
            bridge=bridge,
            send_mode=str((composer or {}).get("send_mode") or "agent"),
        )
        self._handles[session_id] = handle
        self.running_sessions_changed.emit()
        thread.start()
        return handle

    def cancel(self, session_id: str) -> None:
        """Interrupt the worker for *session_id*, if running."""
        handle = self._handles.get(session_id)
        if handle is None:
            return
        if handle.research_state is not None and handle.research_state.is_active:
            handle.research_state.is_active = False
            stopped = json.dumps({"phase": "stopped", "status": "", "findings": ""})
            self.research_updated.emit(
                session_id,
                handle.context.run_generation,
                stopped,
            )
        handle.worker.cancel()

    def cancel_all(self) -> None:
        """Interrupt every in-flight worker (app shutdown)."""
        for handle in list(self._handles.values()):
            worker = handle.worker
            if worker is not None:
                worker.cancel()
        for handle in list(self._handles.values()):
            thread = handle.thread
            if thread.isRunning():
                thread.quit()
                thread.wait(5000)

    def _on_chunk(
        self,
        session_id: str,
        run_generation: int,
        thinking_delta: str,
        content_delta: str,
    ) -> None:
        handle = self._handles.get(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        if thinking_delta:
            handle.thinking_buffer = merge_stream_text(
                handle.thinking_buffer,
                thinking_delta,
            )
        if content_delta:
            handle.content_buffer = merge_stream_text(
                handle.content_buffer,
                content_delta,
            )
        self.chunk_received.emit(session_id, run_generation, thinking_delta, content_delta)

    def _on_status(self, session_id: str, run_generation: int, status: str) -> None:
        handle = self._handles.get(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        handle.status_text = status
        self.status_changed.emit(session_id, run_generation, status)

    def _on_research(self, session_id: str, run_generation: int, payload: str) -> None:
        """Update research state and fan out to the panel."""
        handle = self._handles.get(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        if handle.research_state is None:
            handle.research_state = ResearchTurnState(is_active=True)
        state = handle.research_state
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {"phase": "status", "status": payload, "findings": ""}
        phase = str(data.get("phase") or "")
        status = str(data.get("status") or "")
        findings = str(data.get("findings") or "")
        if status and status not in state.progress_lines:
            state.progress_lines.append(status)
            state.is_active = True
        if phase == "findings" and findings:
            state.findings_text = findings
            state.is_active = False
        elif phase == "stopped":
            state.is_active = False
        self.research_updated.emit(session_id, run_generation, payload)

    def _on_usage(self, session_id: str, run_generation: int, metrics: object) -> None:
        handle = self._handles.get(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        handle.pending_sdk_metrics = metrics
        self.usage_updated.emit(session_id, run_generation, metrics)

    def _release(
        self,
        session_id: str,
        thread: QThread,
        worker: AiChatWorker,
        thread_generation: int,
    ) -> None:
        handle = self._handles.get(session_id)
        if handle is None or handle.thread is not thread:
            return
        if handle.thread_generation != thread_generation:
            return
        run_generation = handle.context.run_generation
        bridge = handle.bridge
        del self._handles[session_id]
        with contextlib.suppress(TypeError, RuntimeError):
            worker.chunk_received.disconnect()
            worker.status_changed.disconnect()
            research_signal = getattr(worker, "research_updated", None)
            if research_signal is not None:
                research_signal.disconnect()
            worker.usage_updated.disconnect()
            worker.context_compacted.disconnect()
            worker.assistant_finished.disconnect()
            worker.failed.disconnect()
            thread.finished.disconnect(bridge.on_thread_finished)
        bridge.deleteLater()
        worker.deleteLater()
        if thread.isRunning():
            thread.wait(5000)
        thread.deleteLater()
        self.running_sessions_changed.emit()
        self.run_finished.emit(session_id, run_generation)


__all__ = [
    "MAX_CONCURRENT_CHAT_RUNS",
    "AiChatRunContext",
    "ChatRunHandle",
    "ChatRunRegistry",
    "ResearchTurnState",
]
