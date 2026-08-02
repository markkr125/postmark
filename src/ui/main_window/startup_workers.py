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


class HistoryReconcileWorker(QObject):
    """Run history orphan reconcile off the GUI startup path."""

    finished = Signal()

    def run(self) -> None:
        """Reconcile on-disk history bodies with SQLite metadata."""
        from database.database import reconcile_history_orphans

        reconcile_history_orphans()
        self.finished.emit()


class AiModelBackfillWorker(QObject):
    """Runs the one-time LiteLLM tier backfill off the GUI thread.

    Imports ``litellm`` (slow on first call) away from the startup path, then
    emits the refreshed model list so the GUI thread can persist and apply it.
    Uses ``persist=False`` so QSettings is never written from this thread.
    """

    finished = Signal(object)

    def run(self) -> None:
        """Load models with tier backfill enabled (no QSettings write) and emit."""
        from services.ai.ai_config import AiConfig

        models = AiConfig.get_models(backfill_tiers=True, persist=False)
        self.finished.emit(models)


__all__ = ["AiModelBackfillWorker", "HistoryReconcileWorker", "LocalProjectConfigWorker"]
