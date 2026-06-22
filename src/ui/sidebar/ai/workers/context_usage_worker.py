"""Background worker that builds AI chat context usage breakdowns."""

from __future__ import annotations

from PySide6.QtCore import QMetaObject, QObject, Qt, QThread, Signal, Slot
from shiboken6 import isValid

from services.ai.ai_config import AiModelEntry
from services.ai.chat.context_usage import (
    ContextUsageBreakdown,
    ContextUsageSdkMetrics,
    build_breakdown,
)
from services.ai.chat.session_service import AiChatMessageDict


class ContextUsageWorker(QObject):
    """Compute context usage off the GUI thread."""

    finished = Signal(object)

    def __init__(self) -> None:
        """Initialise with empty parameters."""
        super().__init__()
        self._session_id: str | None = None
        self._messages: list[AiChatMessageDict] = []
        self._entry: AiModelEntry | None = None
        self._agent_id: str = ""
        self._draft_text: str = ""
        self._streaming_thinking: str = ""
        self._streaming_content: str = ""
        self._sdk_metrics: ContextUsageSdkMetrics | None = None
        self._send_mode: str | None = None

    def set_request(
        self,
        *,
        session_id: str | None,
        messages: list[AiChatMessageDict],
        entry: AiModelEntry | None,
        agent_id: str,
        draft_text: str = "",
        streaming_thinking: str = "",
        streaming_content: str = "",
        sdk_metrics: ContextUsageSdkMetrics | None = None,
        send_mode: str | None = None,
    ) -> None:
        """Configure the next breakdown build (call before ``run``)."""
        self._session_id = session_id
        self._messages = list(messages)
        self._entry = entry
        self._agent_id = agent_id
        self._draft_text = draft_text
        self._streaming_thinking = streaming_thinking
        self._streaming_content = streaming_content
        self._sdk_metrics = sdk_metrics
        self._send_mode = send_mode

    @Slot()
    def run(self) -> None:
        """Build the breakdown and emit ``finished``."""
        breakdown: ContextUsageBreakdown = build_breakdown(
            session_id=self._session_id,
            messages=self._messages,
            entry=self._entry,
            agent_id=self._agent_id,
            draft_text=self._draft_text,
            streaming_thinking=self._streaming_thinking,
            streaming_content=self._streaming_content,
            sdk_metrics=self._sdk_metrics,
            send_mode=self._send_mode,
        )
        self.finished.emit(breakdown)


class ContextUsageLoader(QObject):
    """Schedule :class:`ContextUsageWorker` jobs on one persistent background thread."""

    finished = Signal(int, object)

    def __init__(self, parent: QObject | None = None) -> None:
        """Create a loader owned by *parent* (typically :class:`AiChatPanel`)."""
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: ContextUsageWorker | None = None
        self._active_generation: int | None = None
        self._running = False

    def is_running(self) -> bool:
        """Return whether a breakdown build is in flight."""
        return self._running

    def _ensure_worker_thread(self) -> ContextUsageWorker:
        """Start the worker thread on first use."""
        if self._worker is not None:
            return self._worker
        self._thread = QThread(self)
        self._worker = ContextUsageWorker()
        self._worker.moveToThread(self._thread)
        self._worker.finished.connect(
            self._on_worker_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        self._thread.start()
        return self._worker

    def run_breakdown(self, generation: int, **kwargs: object) -> None:
        """Queue one breakdown build for *generation*."""
        worker = self._ensure_worker_thread()
        worker.set_request(**kwargs)  # type: ignore[arg-type]
        if self._running:
            return
        self._running = True
        self._active_generation = generation
        QMetaObject.invokeMethod(  # type: ignore[call-overload]
            worker,
            "run",
            Qt.ConnectionType.QueuedConnection,
        )

    @Slot(object)
    def _on_worker_finished(self, breakdown: object) -> None:
        """Forward worker results to GUI listeners."""
        if not isValid(self):
            return
        generation = self._active_generation
        self._running = False
        self._active_generation = None
        if generation is None:
            return
        self.finished.emit(generation, breakdown)

    def shutdown(self) -> None:
        """Stop the worker thread (call before tearing down the parent widget)."""
        self._running = False
        self._active_generation = None
        thread = self._thread
        if thread is None or not thread.isRunning():
            return
        thread.quit()
        thread.wait(5000)
        self._thread = None
        self._worker = None


__all__ = ["ContextUsageLoader", "ContextUsageWorker"]
