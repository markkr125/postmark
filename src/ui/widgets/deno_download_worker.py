"""Background worker that downloads the managed Deno binary.

Used by :class:`ui.widgets.runtime_banner.RuntimeBanner` and
:class:`ui.dialogs.settings_dialog.SettingsDialog` so the download path is
shared; Deno is only ever downloaded on explicit user action.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class DenoDownloadWorker(QObject):
    """Runs :meth:`services.scripting.deno_manager.DenoManager.download` in a thread."""

    progress = Signal(int, int)
    finished = Signal(str)
    error = Signal(str)

    def run(self) -> None:
        """Download Deno and emit progress updates."""
        from services.scripting.deno_manager import DenoManager

        try:
            path = DenoManager.download(
                progress_callback=lambda received, total: self.progress.emit(
                    received,
                    total,
                ),
            )
            self.finished.emit(str(path))
        except Exception as exc:
            self.error.emit(str(exc))


__all__ = ["DenoDownloadWorker"]
