"""Background load of AI chat session index rows for the history popover."""

from __future__ import annotations

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt, QThread, Signal, Slot
from shiboken6 import isValid

from services.ai.chat.session_service import AiChatSessionDict, AiChatSessionService


class SessionListLoadWorker(QObject):
    """Loads session metadata rows on a dedicated thread."""

    finished = Signal(int, object)

    @Slot(int, str)
    def load(self, generation: int, search: str) -> None:
        """Query the session index and emit ``finished(generation, sessions)``."""
        needle = search.strip() or None
        sessions = AiChatSessionService.list_sessions(search=needle)
        self.finished.emit(generation, sessions)


class SessionListLoader(QObject):
    """Schedule :class:`SessionListLoadWorker` jobs (one result at a time)."""

    finished = Signal(int, object)

    def __init__(self, parent: QObject | None = None) -> None:
        """Create a loader owned by *parent* (typically the history popover)."""
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: SessionListLoadWorker | None = None
        self._active_generation = 0
        self._latest_generation = 0

    def _ensure_worker_thread(self) -> None:
        """Start the worker thread on first use."""
        if self._thread is not None:
            return
        self._thread = QThread(self)
        self._worker = SessionListLoadWorker()
        self._worker.moveToThread(self._thread)
        assert self._worker is not None
        self._worker.finished.connect(
            self._on_worker_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        self._thread.start()

    def cancel(self) -> None:
        """Ignore in-flight results (the worker thread is not interrupted)."""
        self._latest_generation += 1
        self._active_generation = self._latest_generation

    def shutdown(self) -> None:
        """Stop the worker thread (call before tearing down the parent widget)."""
        self.cancel()
        thread = self._thread
        if thread is None or not thread.isRunning():
            return
        thread.quit()
        thread.wait(5000)

    def load(self, search: str = "") -> int:
        """Start loading sessions matching *search*; return the request generation."""
        self._ensure_worker_thread()
        self._latest_generation += 1
        generation = self._latest_generation
        self._active_generation = generation
        assert self._worker is not None
        QMetaObject.invokeMethod(  # type: ignore[call-overload]
            self._worker,
            "load",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, generation),
            Q_ARG(str, search),
        )
        return generation

    def _on_worker_finished(self, generation: int, payload: object) -> None:
        if not isValid(self):
            return
        if generation != self._active_generation:
            return
        self.finished.emit(generation, payload)


__all__ = [
    "AiChatSessionDict",
    "SessionListLoadWorker",
    "SessionListLoader",
]
