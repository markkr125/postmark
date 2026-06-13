"""Background load of AI chat session rows and transcript messages."""

from __future__ import annotations

from PySide6.QtCore import (Q_ARG, QMetaObject, QObject, Qt, QThread, Signal,
                            Slot)
from shiboken6 import isValid

from services.ai.chat.session_service import (AiChatSessionLoadDict,
                                              AiChatSessionService)


class AiChatSessionLoadWorker(QObject):
    """Loads session metadata and messages on a dedicated thread."""

    finished = Signal(int, object)

    @Slot(int, str)
    def load_session(self, generation: int, session_id: str) -> None:
        """Read SQLite and emit ``finished(generation, payload)``."""
        payload = AiChatSessionService.get_session_with_messages(session_id)
        self.finished.emit(generation, payload)


class AiChatSessionLoader(QObject):
    """Schedule :class:`AiChatSessionLoadWorker` jobs (one result at a time)."""

    finished = Signal(int, object)

    def __init__(self, parent: QObject | None = None) -> None:
        """Create a loader owned by *parent* (typically the main window)."""
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: AiChatSessionLoadWorker | None = None
        self._active_generation: int | None = None

    def _ensure_worker_thread(self) -> None:
        """Start the worker thread on first use."""
        if self._thread is not None:
            return
        self._thread = QThread(self)
        self._worker = AiChatSessionLoadWorker()
        self._worker.moveToThread(self._thread)
        assert self._worker is not None
        self._worker.finished.connect(
            self._on_worker_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        self._thread.start()

    def cancel(self) -> None:
        """Ignore in-flight results (the worker thread is not interrupted)."""
        self._active_generation = None

    def shutdown(self) -> None:
        """Stop the worker thread (call before tearing down the parent widget)."""
        self.cancel()
        thread = self._thread
        if thread is None or not thread.isRunning():
            return
        thread.quit()
        thread.wait(5000)

    def load(self, session_id: str, generation: int) -> None:
        """Start loading *session_id*; emit ``finished(generation, payload)`` when done."""
        self._ensure_worker_thread()
        self._active_generation = generation
        assert self._worker is not None
        QMetaObject.invokeMethod(  # type: ignore[call-overload]
            self._worker,
            "load_session",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, generation),
            Q_ARG(str, session_id),
        )

    def _on_worker_finished(self, generation: int, payload: object) -> None:
        if generation != self._active_generation:
            return
        if not isValid(self):
            return
        self.finished.emit(generation, payload)


__all__ = [
    "AiChatSessionLoadDict",
    "AiChatSessionLoadWorker",
    "AiChatSessionLoader",
]
