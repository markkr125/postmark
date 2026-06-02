"""Background runnable that pretty-prints response bodies off the GUI thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal
from shiboken6 import isValid

from ui.sidebar.saved_responses.helpers import format_code_text


class FormatTextSignals(QObject):
    """Cross-thread delivery of formatted text (queued to the GUI thread)."""

    finished = Signal(int, str)


class FormatTextRunnable(QRunnable):
    """Run :func:`format_code_text` on a thread-pool worker."""

    def __init__(
        self,
        signals: FormatTextSignals,
        generation: int,
        text: str,
        language: str,
        *,
        pretty: bool,
    ) -> None:
        """Store payload; *signals* must live on the GUI thread."""
        super().__init__()
        self.setAutoDelete(True)
        self._signals = signals
        self._generation = generation
        self._text = text
        self._language = language
        self._pretty = pretty

    def run(self) -> None:
        """Format text and emit the result with the job *generation* id."""
        if not isValid(self._signals):
            return
        try:
            formatted = format_code_text(self._text, self._language, pretty=self._pretty)
        except Exception:
            formatted = self._text
        if not isValid(self._signals):
            return
        self._signals.finished.emit(self._generation, formatted)


# Backward-compatible alias for tests.
FormatTextWorker = FormatTextRunnable
