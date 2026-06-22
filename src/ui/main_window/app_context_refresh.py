"""Debounced live refresh of app-context snapshots during in-flight AI runs."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QObject, QTimer

if TYPE_CHECKING:
    from services.ai.chat.run_registry import ChatRunRegistry
    from ui.collections.collection_widget import CollectionWidget
    from ui.request.request_editor import RequestEditorWidget

_APP_CONTEXT_REFRESH_MS = 250


class _AppContextRefreshMixin:
    """Schedule snapshot rewrites for the active AI session while a run is in flight."""

    _active_ai_session_id: str | None
    _chat_run_registry: ChatRunRegistry
    _app_context_refresh_timer: QTimer | None
    collection_widget: CollectionWidget
    local_scripts_widget: CollectionWidget

    def _init_app_context_refresh(self) -> None:
        """Create the debounce timer (call once from ``MainWindow.__init__``)."""
        timer = QTimer(cast(QObject, self))
        timer.setSingleShot(True)
        timer.setInterval(_APP_CONTEXT_REFRESH_MS)
        timer.timeout.connect(self._on_app_context_refresh_timer)
        self._app_context_refresh_timer = timer

    def schedule_app_context_refresh(self) -> None:
        """Coalesce rapid UI events into one snapshot write."""
        if self._app_context_refresh_timer is None:
            self._init_app_context_refresh()
        timer = self._app_context_refresh_timer
        assert timer is not None
        timer.start()

    def flush_app_context_refresh(self) -> None:
        """Write the snapshot immediately (session focus path)."""
        timer = self._app_context_refresh_timer
        if timer is not None and timer.isActive():
            timer.stop()
        self.refresh_active_session_snapshot()

    def _on_app_context_refresh_timer(self) -> None:
        """Timer callback — refresh the active session snapshot."""
        self.refresh_active_session_snapshot()

    def refresh_active_session_snapshot(self) -> None:
        """Rewrite ``app_context_snapshot.json`` when the active session is running."""
        session_id = self._active_ai_session_id
        if session_id is None or not self._chat_run_registry.is_running(session_id):
            return
        handle = self._chat_run_registry.run_for(session_id)
        send_mode = handle.send_mode if handle is not None else "agent"
        write = getattr(self, "write_app_context_snapshot", None)
        if callable(write):
            write(session_id, send_mode)

    def connect_app_context_refresh_signals(self) -> None:
        """Wire sidebar and editor signals that should refresh the live snapshot."""
        self._init_app_context_refresh()
        coll_tree = self.collection_widget._tree_widget
        coll_tree.selected_collection_changed.connect(
            lambda *_args: self.schedule_app_context_refresh()
        )
        scripts_tree = self.local_scripts_widget._tree_widget
        scripts_tree.selected_collection_changed.connect(
            lambda *_args: self.schedule_app_context_refresh()
        )

    def wire_request_editor_app_context_refresh(self, editor: RequestEditorWidget) -> None:
        """Refresh when the user switches request sub-tabs (Headers, Body, …)."""
        editor._tabs.currentChanged.connect(lambda *_idx: self.schedule_app_context_refresh())


__all__ = ["_APP_CONTEXT_REFRESH_MS", "_AppContextRefreshMixin"]
