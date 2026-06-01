"""Incremental session tab restore so startup stays responsive on the GUI thread."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QTimer

from services.local_script_service import LocalScriptService

if TYPE_CHECKING:
    from ui.main_window.window import MainWindow

logger = logging.getLogger(__name__)

# Tabs restored per event-loop tick (request chips are cheap; folder/draft cost more).
_RESTORE_BATCH_SIZE = 2


@dataclass
class _SessionRestoreState:
    """Queued session-restore work between timer ticks."""

    data: dict[str, Any]
    active: int
    queue: list[dict[str, Any]] = field(default_factory=list)


def begin_session_restore(window: MainWindow) -> None:
    """Schedule batched tab restore after ``load_finished`` (non-blocking)."""
    state = _plan_session_restore(window)
    if state is None:
        return
    window._session_restore_state = state
    window._restoring_session = True
    QTimer.singleShot(0, lambda: _restore_step(window))


def flush_session_restore(window: MainWindow) -> None:
    """Run all pending restore steps synchronously (tests)."""
    while getattr(window, "_session_restore_state", None) is not None:
        _restore_step(window)


def restore_tabs_synchronous(window: MainWindow) -> None:
    """Restore the full session on the GUI thread (profiling / legacy callers)."""
    state = _plan_session_restore(window)
    if state is None:
        return
    window._restoring_session = True
    try:
        for entry in state.queue:
            _apply_restore_entry(window, entry)
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

    return _SessionRestoreState(data=data, active=active, queue=queue)


def _restore_step(window: MainWindow) -> None:
    """Restore up to ``_RESTORE_BATCH_SIZE`` tabs, then yield to the event loop."""
    state = getattr(window, "_session_restore_state", None)
    if state is None:
        return

    batch = 0
    while state.queue and batch < _RESTORE_BATCH_SIZE:
        entry = state.queue.pop(0)
        _apply_restore_entry(window, entry)
        batch += 1

    if state.queue:
        QTimer.singleShot(0, lambda: _restore_step(window))
        return

    window._session_restore_state = None
    window._restoring_session = False
    _finalize_session_restore(window, state)
    if hasattr(window, "session_restore_finished"):
        window.session_restore_finished.emit()


def _apply_restore_entry(window: MainWindow, entry: dict[str, Any]) -> None:
    """Restore a single persisted tab entry."""
    tab_type = entry.get("type")
    if tab_type == "draft":
        window._restore_draft(entry)
        return
    if tab_type == "environments":
        if window._find_environments_tab_index() is not None:
            return
        if not window._enforce_tab_limit_before_open():
            logger.warning(
                "Skipping environments tab restore: tab limit reached",
            )
            return
        window._materialize_environments_tab_at(window._tab_bar.count())
        return

    item_id = entry.get("id")
    if not isinstance(item_id, int):
        return

    if tab_type == "request":
        window._restore_request_deferred(entry, item_id)
    elif tab_type == "folder":
        window._open_folder(item_id, show_missing_warning=False)
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


__all__ = [
    "begin_session_restore",
    "flush_session_restore",
    "restore_tabs_synchronous",
]
