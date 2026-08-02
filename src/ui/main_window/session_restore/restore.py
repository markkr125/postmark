"""Incremental session tab restore — batched chips + parallel prefetch."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import QApplication

from services.local_script_service import LocalScriptService
from ui.main_window.session_restore.prefetch import SessionPrefetchResult, SessionPrefetchWorker
from ui.main_window.session_restore.types import (
    collect_prefetch_folder_ids,
    collect_prefetch_local_script_ids,
    collect_prefetch_request_ids,
    partition_restore_queue,
)

if TYPE_CHECKING:
    from ui.main_window.window import MainWindow

logger = logging.getLogger(__name__)

# Deferred chips restore in one event-loop tick (cheap — no DB, no editors).
_DEFERRED_RESTORE_BATCH_SIZE = 512
# Draft tabs restore in one batch after all chips (unavoidable eager editor build).
_EAGER_DRAFT_BATCH_SIZE = 32
# Single paint yield before finalize (not 25 ms per tab).
_RESTORE_PAINT_YIELD_MS = 0
_RESTORE_FINALIZE_DELAY_MS = 0


@dataclass
class _SessionRestoreState:
    """Queued session-restore work between timer ticks."""

    data: dict[str, Any]
    active: int
    deferred_queue: list[dict[str, Any]] = field(default_factory=list)
    eager_draft_queue: list[dict[str, Any]] = field(default_factory=list)
    phase: str = "deferred"


def begin_session_restore(window: MainWindow) -> None:
    """Schedule batched tab restore after ``load_finished``."""
    state = _plan_session_restore(window)
    if state is None:
        return
    window._session_restore_state = state
    window._restoring_session = True
    _start_session_prefetch(window, state)
    window._schedule_startup_task(_RESTORE_PAINT_YIELD_MS, lambda: _restore_step(window))


def flush_session_restore(window: MainWindow) -> None:
    """Run all pending restore steps synchronously (tests)."""
    state = getattr(window, "_session_restore_state", None)
    if state is None:
        state = _plan_session_restore(window)
        if state is None:
            return
        window._session_restore_state = state
        window._restoring_session = True
        _start_session_prefetch(window, state)
    while state.phase != "done":
        _restore_step(window)
    window._session_restore_state = None
    _finish_session_restore(window, state)


def restore_tabs_synchronous(window: MainWindow) -> None:
    """Restore the full session on the GUI thread (profiling / legacy callers)."""
    state = _plan_session_restore(window)
    if state is None:
        return
    window._restoring_session = True
    _start_session_prefetch(window, state)
    try:
        _restore_all_deferred(window, state)
        _restore_all_drafts(window, state)
    finally:
        window._restoring_session = False
    _finalize_session_restore(window, state)
    if hasattr(window, "session_restore_finished"):
        window.session_restore_finished.emit()


def _plan_session_restore(window: MainWindow) -> _SessionRestoreState | None:
    """Load persisted tab data and build the restore queue."""
    data = window._tab_settings_manager.load_open_tabs()
    if data is None:
        window._left_sidebar.open_panel()
        return None

    tabs_list = data.get("tabs")
    if not isinstance(tabs_list, list):
        return None

    active = data.get("active", 0)
    if not isinstance(active, int):
        active = 0

    queue: list[dict[str, Any]] = []
    for entry in tabs_list:
        if isinstance(entry, dict):
            queue.append(entry)

    deferred, eager_drafts = partition_restore_queue(queue)
    return _SessionRestoreState(
        data=data,
        active=active,
        deferred_queue=deferred,
        eager_draft_queue=eager_drafts,
    )


def _start_session_prefetch(window: MainWindow, state: _SessionRestoreState) -> None:
    """Kick off parallel read-only DB prefetch for all session tab ids."""
    all_entries = state.deferred_queue + state.eager_draft_queue
    request_ids = collect_prefetch_request_ids(all_entries)
    script_ids = collect_prefetch_local_script_ids(all_entries)
    folder_ids = collect_prefetch_folder_ids(all_entries)

    if not request_ids and not script_ids and not folder_ids:
        window._session_prefetch_result = SessionPrefetchResult()
        window._session_prefetch_ready = True
        return

    import os

    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        _apply_prefetch_sync(window, request_ids, script_ids, folder_ids)
        return

    window._session_prefetch_ready = False
    window._session_prefetch_result = None

    thread = QThread(window)
    worker = SessionPrefetchWorker(
        request_ids=request_ids,
        local_script_ids=script_ids,
        folder_ids=folder_ids,
    )
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(
        lambda result: _on_prefetch_finished(window, result),
        Qt.ConnectionType.QueuedConnection,
    )
    worker.failed.connect(
        lambda msg: _on_prefetch_failed(window, msg),
        Qt.ConnectionType.QueuedConnection,
    )
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(lambda: _clear_prefetch_thread_refs(window))

    window._session_prefetch_thread = thread
    window._session_prefetch_worker = worker
    thread.start()


def _apply_prefetch_sync(
    window: MainWindow,
    request_ids: list[int],
    local_script_ids: list[int],
    folder_ids: list[int],
) -> None:
    """Run prefetch synchronously (UI tests / offscreen platform)."""
    from services.collection_service import CollectionService
    from services.local_script_service import LocalScriptService

    result = SessionPrefetchResult()
    if request_ids:
        result.requests = CollectionService.fetch_requests_by_ids(request_ids)
        result.breadcrumbs = CollectionService.fetch_request_breadcrumbs_by_ids(request_ids)
    if local_script_ids:
        result.local_scripts = LocalScriptService.fetch_local_script_load_dicts_by_ids(
            local_script_ids
        )
    if folder_ids:
        result.folder_names = CollectionService.fetch_collection_names_by_ids(folder_ids)
    window._session_prefetch_result = result
    window._session_prefetch_ready = True


def _clear_prefetch_thread_refs(window: MainWindow) -> None:
    """Drop prefetch thread refs after the worker exits."""
    window._session_prefetch_thread = None
    window._session_prefetch_worker = None


def _on_prefetch_finished(window: MainWindow, result: object) -> None:
    """Store prefetch payloads and refresh any waiting active tab."""
    if not isinstance(result, SessionPrefetchResult):
        return
    window._session_prefetch_result = result
    window._session_prefetch_ready = True
    _apply_late_prefetch_to_active_tab(window)


def _on_prefetch_failed(window: MainWindow, message: str) -> None:
    """Log prefetch failure; materialization falls back to live DB reads."""
    logger.warning("Session prefetch failed: %s", message)
    window._session_prefetch_result = SessionPrefetchResult()
    window._session_prefetch_ready = True


def _apply_late_prefetch_to_active_tab(window: MainWindow) -> None:
    """If finalize materialized before prefetch finished, reload from cache."""
    if getattr(window, "_restoring_session", False):
        return
    handler = getattr(window, "_on_session_prefetch_late_arrival", None)
    if callable(handler):
        handler()


def _restore_step(window: MainWindow) -> None:
    """Restore deferred chips, then drafts, then finalize."""
    state = getattr(window, "_session_restore_state", None)
    if state is None:
        return

    if state.phase == "deferred":
        _restore_all_deferred(window, state)
        state.phase = "drafts" if state.eager_draft_queue else "finalize"
        if state.phase != "deferred":
            window._schedule_startup_task(_RESTORE_PAINT_YIELD_MS, lambda: _restore_step(window))
        return

    if state.phase == "drafts":
        _restore_all_drafts(window, state)
        state.phase = "finalize"
        window._schedule_startup_task(_RESTORE_FINALIZE_DELAY_MS, lambda: _restore_step(window))
        return

    if state.phase == "finalize":
        state.phase = "done"
        window._session_restore_state = None
        _finish_session_restore(window, state)


def _restore_all_deferred(window: MainWindow, state: _SessionRestoreState) -> None:
    """Restore every deferred tab chip in one batch."""
    if not state.deferred_queue:
        return
    window._tab_bar.blockSignals(True)
    try:
        batch = 0
        while state.deferred_queue and batch < _DEFERRED_RESTORE_BATCH_SIZE:
            entry = state.deferred_queue.pop(0)
            _apply_deferred_restore_entry(window, entry)
            batch += 1
    finally:
        window._tab_bar.blockSignals(False)
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def _restore_all_drafts(window: MainWindow, state: _SessionRestoreState) -> None:
    """Restore draft tabs in one batch after chips."""
    if not state.eager_draft_queue:
        return
    batch = 0
    while state.eager_draft_queue and batch < _EAGER_DRAFT_BATCH_SIZE:
        entry = state.eager_draft_queue.pop(0)
        window._restore_draft(entry)
        batch += 1


def _apply_deferred_restore_entry(window: MainWindow, entry: dict[str, Any]) -> None:
    """Restore a single cheap (chip-only) tab entry."""
    tab_type = entry.get("type")
    if tab_type == "environments":
        if window._find_environments_tab_index() is not None:
            return
        if not window._enforce_tab_limit_before_open():
            logger.warning("Skipping environments tab restore: tab limit reached")
            return
        window._materialize_environments_tab_at(window._tab_bar.count())
        return

    item_id = entry.get("id")
    if not isinstance(item_id, int):
        return

    if tab_type == "request":
        window._restore_request_deferred(entry, item_id)
    elif tab_type == "folder":
        window._restore_folder_deferred(entry, item_id)
    elif tab_type == "local_script":
        if LocalScriptService.get_script(item_id) is None:
            return
        window._restore_local_script_deferred(entry, item_id)


def _finalize_session_restore(window: MainWindow, state: _SessionRestoreState) -> None:
    """Activate the saved tab and restore sidebar flyout state."""
    active = state.active
    if 0 <= active < window._tab_bar.count():
        window._tab_bar.setCurrentIndex(active)
        window._on_tab_changed(active)
        window._flush_tab_change()

    window._seed_tab_nav_after_restore()

    data = state.data
    left_panel = data.get("left_sidebar_panel")
    if isinstance(left_panel, str):
        window._left_sidebar.open_panel(left_panel)
    elif not window._left_sidebar.is_open:
        window._left_sidebar.open_panel()

    sidebar_panel = data.get("sidebar_panel")
    if isinstance(sidebar_panel, str):
        window._right_sidebar.open_panel(sidebar_panel)
        sidebar_width = data.get("sidebar_width")
        if isinstance(sidebar_width, int) and sidebar_width > 0:
            window._right_sidebar._expand_flyout(sidebar_width)


def _finish_session_restore(window: MainWindow, state: _SessionRestoreState) -> None:
    """Finish restore and emit completion."""
    window._restoring_session = False
    _finalize_session_restore(window, state)
    if hasattr(window, "session_restore_finished"):
        window.session_restore_finished.emit()


__all__ = [
    "begin_session_restore",
    "flush_session_restore",
    "restore_tabs_synchronous",
]
