"""Background load of AI chat session rows and transcript messages."""

from __future__ import annotations

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt, QThread, Signal, Slot
from shiboken6 import isValid

from services.ai.chat.session_service import (
    AiChatSessionService,
    AiChatSessionTailLoadDict,
    AiChatTranscriptPageDict,
)


class AiChatSessionLoadWorker(QObject):
    """Loads session metadata and messages on a dedicated thread."""

    finished = Signal(int, object)

    @Slot(int, str)
    def load_tail(self, generation: int, session_id: str) -> None:
        """Read session tail and emit ``finished(generation, ('tail', payload))``."""
        payload = AiChatSessionService.get_session_tail(session_id)
        self.finished.emit(generation, ("tail", payload))

    @Slot(int, str, int)
    def load_older(self, generation: int, session_id: str, before_id: int) -> None:
        """Fetch an older transcript page."""
        page = AiChatSessionService.load_older_messages(session_id, before_id=before_id)
        self.finished.emit(generation, ("older", page))

    @Slot(int, str, int)
    def load_newer(self, generation: int, session_id: str, after_id: int) -> None:
        """Fetch a newer transcript page after eviction."""
        page = AiChatSessionService.load_newer_messages(session_id, after_id=after_id)
        self.finished.emit(generation, ("newer", page))


class AiChatSessionLoader(QObject):
    """Schedule :class:`AiChatSessionLoadWorker` jobs (one result at a time)."""

    finished = Signal(int, object)

    def __init__(self, parent: QObject | None = None) -> None:
        """Create a loader owned by *parent* (typically the main window)."""
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: AiChatSessionLoadWorker | None = None
        self._active_generation: int | None = None
        self._window_generation: int | None = None

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
        self._window_generation = None

    def shutdown(self) -> None:
        """Stop the worker thread (call before tearing down the parent widget)."""
        self.cancel()
        thread = self._thread
        if thread is None or not thread.isRunning():
            return
        thread.quit()
        thread.wait(5000)

    def load_tail(self, session_id: str, generation: int) -> None:
        """Start loading the tail of *session_id*."""
        self._ensure_worker_thread()
        self._active_generation = generation
        assert self._worker is not None
        QMetaObject.invokeMethod(  # type: ignore[call-overload]
            self._worker,
            "load_tail",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, generation),
            Q_ARG(str, session_id),
        )

    def load_older(self, session_id: str, before_id: int, generation: int) -> None:
        """Fetch messages older than *before_id*."""
        self._ensure_worker_thread()
        self._window_generation = generation
        assert self._worker is not None
        QMetaObject.invokeMethod(  # type: ignore[call-overload]
            self._worker,
            "load_older",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, generation),
            Q_ARG(str, session_id),
            Q_ARG(int, before_id),
        )

    def load_newer(self, session_id: str, after_id: int, generation: int) -> None:
        """Fetch messages newer than *after_id*."""
        self._ensure_worker_thread()
        self._window_generation = generation
        assert self._worker is not None
        QMetaObject.invokeMethod(  # type: ignore[call-overload]
            self._worker,
            "load_newer",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, generation),
            Q_ARG(str, session_id),
            Q_ARG(int, after_id),
        )

    def _on_worker_finished(self, generation: int, payload: object) -> None:
        if not isValid(self):
            return
        if isinstance(payload, tuple) and len(payload) == 2 and payload[0] in {"older", "newer"}:
            if generation != self._window_generation:
                return
            self.finished.emit(generation, payload)
            return
        if generation != self._active_generation:
            return
        self.finished.emit(generation, payload)


__all__ = [
    "AiChatSessionLoadWorker",
    "AiChatSessionLoader",
    "AiChatSessionTailLoadDict",
    "AiChatTranscriptPageDict",
]
