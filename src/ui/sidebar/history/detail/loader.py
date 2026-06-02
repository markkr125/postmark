"""Background load of full send-history payloads for the detail pane."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from services.request_history_service import RequestHistoryService


class HistoryDetailLoadSignals(QObject):
    """Delivers loaded entry payloads on the GUI thread (queued connection)."""

    finished = Signal(int, object)


class HistoryDetailLoadRunnable(QRunnable):
    """Read body/snapshot files and build detail snapshot off the GUI thread."""

    def __init__(
        self,
        signals: HistoryDetailLoadSignals,
        generation: int,
        entry_id: int,
    ) -> None:
        """Store job parameters for :meth:`run`."""
        super().__init__()
        self.setAutoDelete(True)
        self._signals = signals
        self._generation = generation
        self._entry_id = entry_id

    def run(self) -> None:
        """Load entry files and emit ``(generation, {entry, detail})`` or ``None``."""
        entry = RequestHistoryService.get_entry(self._entry_id)
        if entry is None:
            self._signals.finished.emit(self._generation, None)
            return
        detail = RequestHistoryService.entry_to_detail_snapshot(entry)
        self._signals.finished.emit(self._generation, {"entry": entry, "detail": detail})


class HistoryDetailLoader(QObject):
    """Schedule :class:`HistoryDetailLoadRunnable` jobs (one result at a time)."""

    finished = Signal(int, object)

    def __init__(self, parent: QObject | None = None) -> None:
        """Create a loader owned by *parent* (typically :class:`HistoryPanel`)."""
        super().__init__(parent)
        self._signals = HistoryDetailLoadSignals(self)
        self._signals.finished.connect(self._forward_finished)
        self._active_generation: int | None = None

    def cancel(self) -> None:
        """Ignore in-flight results (pool workers are not interrupted)."""
        self._active_generation = None

    def load(self, entry_id: int, generation: int) -> None:
        """Start loading *entry_id*; emit ``finished(generation, payload)`` when done."""
        self._active_generation = generation
        runnable = HistoryDetailLoadRunnable(self._signals, generation, entry_id)
        QThreadPool.globalInstance().start(runnable)

    def _forward_finished(self, generation: int, payload: object) -> None:
        if generation != self._active_generation:
            return
        self.finished.emit(generation, payload)
