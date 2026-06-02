"""Background load of full send-history rows for orphan (deleted-request) tab open."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot, QMetaObject, Qt, Q_ARG
from shiboken6 import isValid

from services.request_history_service import RequestHistoryService


class _OrphanHistoryOpenWorker(QObject):
    """Loads a full history entry on a dedicated thread."""

    finished = Signal(int, object)

    @Slot(int, int)
    def load_entry(self, generation: int, entry_id: int) -> None:
        """Read files and emit ``finished(generation, payload)`` from the worker thread."""
        entry = RequestHistoryService.get_entry(entry_id)
        if entry is None:
            self.finished.emit(generation, None)
            return
        http = RequestHistoryService.entry_to_http_response_dict(entry)
        self.finished.emit(generation, {"entry": entry, "http": http})


class OrphanHistoryOpenLoader(QObject):
    """Schedule :class:`_OrphanHistoryOpenWorker` jobs (one result at a time)."""

    finished = Signal(int, object)

    def __init__(self, parent: QObject | None = None) -> None:
        """Create a loader owned by *parent* (typically :class:`MainWindow`)."""
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _OrphanHistoryOpenWorker | None = None
        self._active_generation: int | None = None

    def _ensure_worker_thread(self) -> None:
        """Start the worker thread on first use."""
        if self._thread is not None:
            return
        self._thread = QThread(self)
        self._worker = _OrphanHistoryOpenWorker()
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
        """Stop the worker thread (call when the main window closes)."""
        self.cancel()
        thread = self._thread
        if thread is None or not thread.isRunning():
            return
        thread.quit()
        thread.wait(5000)

    def load(self, entry_id: int, generation: int) -> None:
        """Start loading *entry_id*; emit ``finished(generation, payload)`` when done."""
        self._ensure_worker_thread()
        self._active_generation = generation
        assert self._worker is not None
        QMetaObject.invokeMethod(  # type: ignore[call-overload]
            self._worker,
            "load_entry",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, generation),
            Q_ARG(int, entry_id),
        )

    def _on_worker_finished(self, generation: int, payload: object) -> None:
        if generation != self._active_generation:
            return
        if not isValid(self):
            return
        self.finished.emit(generation, payload)
