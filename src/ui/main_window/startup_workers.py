"""Background workers for deferred application startup tasks."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class LocalProjectConfigWorker(QObject):
    """Runs ``ensure_local_project_config`` (ambient types + local mirror sync) off the GUI thread."""

    finished = Signal()

    def run(self) -> None:
        """Write ambient stubs and sync the Deno ``local/`` mirror from the database."""
        from services.scripting.local_scripts_project.deno_config import ensure_local_project_config

        ensure_local_project_config()
        self.finished.emit()


__all__ = ["LocalProjectConfigWorker"]
