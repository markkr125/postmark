"""Schedules :class:`FormatTextRunnable` jobs and returns results on the GUI thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThreadPool, Signal

from ui.widgets.text_format_async.worker import FormatTextRunnable, FormatTextSignals


class AsyncTextFormatRunner(QObject):
    """Run :func:`format_code_text` asynchronously via the global thread pool."""

    formatted = Signal(int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        """Create a runner owned by *parent* (typically a widget)."""
        super().__init__(parent)
        self._signals = FormatTextSignals(self)
        self._signals.finished.connect(self._on_worker_finished)
        self._active_generation: int | None = None

    def cancel(self) -> None:
        """Ignore results from in-flight jobs (pool workers are not interrupted)."""
        self._active_generation = None

    def format_async(
        self,
        generation: int,
        text: str,
        language: str,
        *,
        pretty: bool,
    ) -> None:
        """Pretty-print *text* on a worker thread; emit ``formatted(generation, result)``."""
        self._active_generation = generation
        runnable = FormatTextRunnable(
            self._signals,
            generation,
            text,
            language,
            pretty=pretty,
        )
        QThreadPool.globalInstance().start(runnable)

    def _on_worker_finished(self, generation: int, text: str) -> None:
        """Forward formatted text when this job is still the active one."""
        if generation != self._active_generation:
            return
        self.formatted.emit(generation, text)
