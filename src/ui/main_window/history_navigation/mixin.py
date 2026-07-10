"""Open workspace history entries in request tabs (left-rail global history)."""

# mypy: disable-error-code=attr-defined

from __future__ import annotations

from typing import Any, cast

from PySide6.QtCore import QTimer
from shiboken6 import Shiboken

from services.collection_service import CollectionService, RequestLoadDict
from services.request_history_service import RequestHistoryEntryDict, RequestHistoryService
from ui.main_window.history_navigation.orphan_open import OrphanHistoryOpenLoader
from ui.request.navigation.tab_manager import TabContext


class _HistoryNavigationMixin:
    """Navigate from global send history into editor tabs and right-rail History.

    Expects the host class (``MainWindow``) to provide tab/sidebar APIs.
    """

    _global_history_open_busy: bool
    _orphan_history_open_loader: OrphanHistoryOpenLoader
    _orphan_open_generation: int
    _pending_orphan_open_tab_index: int | None

    def _init_orphan_history_open_loader(self) -> None:
        """Wire async loader for opening deleted-request history rows."""
        loader = OrphanHistoryOpenLoader(self)  # type: ignore[arg-type]
        loader.finished.connect(self._on_orphan_history_open_loaded)
        self._orphan_history_open_loader = loader
        self._orphan_open_generation = 0
        self._pending_orphan_open_tab_index = None

    def _refresh_global_history_panel(self) -> None:
        """Reload the left-rail workspace history list."""
        panel = getattr(self, "_global_history_panel", None)
        if panel is not None:
            panel.refresh()

    def _open_from_global_history(self, entry_id: int) -> None:
        """Queue open on the next event-loop tick so the tree click returns immediately."""
        if getattr(self, "_global_history_open_busy", False):
            self._show_history_open_status("Wait for history to finish opening")
            return
        QTimer.singleShot(0, lambda eid=entry_id: self._run_open_from_global_history(eid))

    def _run_open_from_global_history(self, entry_id: int) -> None:
        """Load history entry into editor tabs (runs after the click handler returns)."""
        if getattr(self, "_global_history_open_busy", False):
            self._show_history_open_status("Wait for history to finish opening")
            return
        self._global_history_open_busy = True
        try:
            self._open_from_global_history_impl(entry_id)
        finally:
            self._global_history_open_busy = False

    def _open_from_global_history_impl(self, entry_id: int) -> None:
        """Open a history row in the editor and per-request History flyout."""
        meta = RequestHistoryService.get_entry_metadata(entry_id)
        if meta is None:
            self._show_history_open_status("History entry is no longer available")
            return

        request_id = meta.get("request_id")
        if request_id is not None:
            rid = int(request_id)
            if CollectionService.get_request(rid) is not None:
                QTimer.singleShot(
                    0,
                    lambda: self._open_existing_request_from_history(rid, entry_id),
                )
                return
        self._open_orphan_history_as_draft(entry_id)

    def _show_history_open_status(self, message: str) -> None:
        """Show a short status-bar message for global history open failures."""
        status = self.statusBar() if hasattr(self, "statusBar") else None
        if status is not None:
            status.showMessage(message, 5000)

    def _open_existing_request_from_history(
        self,
        request_id: int,
        entry_id: int,
    ) -> None:
        """Activate a saved request tab and select the send in the right History panel."""
        ctx = self._tab_context_for_request_id(request_id)
        if ctx is not None and ctx.is_sending:
            self._show_history_open_status("Wait for the current send to finish")
            return

        self._open_request(request_id, push_history=True, is_preview=False)  # type: ignore[attr-defined]
        if self._tab_context_for_request_id(request_id) is None:
            self._show_history_open_status("Could not open request tab")
            return
        QTimer.singleShot(
            0,
            lambda: self._finish_open_existing_history(request_id, entry_id),
        )

    def _finish_open_existing_history(
        self,
        request_id: int,
        entry_id: int,
    ) -> None:
        """Focus the request tab, then load the send detail on the right asynchronously."""
        ctx = self._tab_context_for_request_id(request_id)
        if ctx is None or ctx.tab_type != "request" or ctx.request_id != request_id:
            self._show_history_open_status("Could not open request tab")
            return
        if ctx.is_sending:
            self._show_history_open_status("Wait for the current send to finish")
            return
        self._refresh_sidebar(history_load_detail=False)  # type: ignore[attr-defined]
        self._right_sidebar.open_panel("request_history")
        panel = getattr(self, "_request_history_panel", None)
        if panel is not None:
            QTimer.singleShot(0, lambda: panel.schedule_detail_load(entry_id))

    def _open_orphan_history_as_draft(self, entry_id: int) -> None:
        """Open a deleted-request history send in a draft tab (async full load)."""
        meta = RequestHistoryService.get_entry_metadata(entry_id)
        if meta is None:
            self._show_history_open_status("History entry is no longer available")
            return
        if not self._open_draft_request():  # type: ignore[attr-defined]
            self._show_history_open_status("Could not open request tab")
            return
        idx = self._tab_bar.currentIndex()  # type: ignore[attr-defined]
        ctx = self._tabs.get(idx)
        if ctx is None or ctx.request_id is not None:
            self._show_history_open_status("Could not open request tab")
            return

        name = str(meta.get("request_name", "") or "Untitled Request")
        method = str(meta.get("method", "GET") or "GET")
        url = str(meta.get("url", "") or "")
        ctx.draft_name = name
        ctx.variable_collection_id = None
        editor = ctx.require_editor()
        editor.load_request(
            cast(RequestLoadDict, {"method": method, "url": url, "name": name}),
            request_id=None,
        )
        editor._set_dirty(True)
        self._tab_bar.update_tab(idx, method=method, name=name)  # type: ignore[attr-defined]
        self._breadcrumb_bar.set_path(  # type: ignore[attr-defined]
            [{"name": name, "type": "request", "id": 0}]
        )
        viewer = ctx.response_viewer
        if viewer is not None:
            viewer.show_loading()

        self._orphan_history_open_loader.cancel()
        self._orphan_open_generation += 1
        generation = self._orphan_open_generation
        self._pending_orphan_open_tab_index = idx
        self._orphan_history_open_loader.load(entry_id, generation)

    def _on_orphan_history_open_loaded(self, generation: int, payload: object) -> None:
        """Apply async history payload to the draft tab opened for an orphan row."""
        if generation != self._orphan_open_generation:
            return
        idx = self._pending_orphan_open_tab_index
        self._pending_orphan_open_tab_index = None
        if idx is None:
            return
        ctx = self._tabs.get(idx)  # type: ignore[attr-defined]
        if ctx is None or ctx.request_id is not None:
            return
        entry_raw = payload.get("entry") if isinstance(payload, dict) else None
        if not isinstance(entry_raw, dict) or entry_raw.get("id") is None:
            self._show_history_open_status("History entry is no longer available")
            viewer = ctx.response_viewer
            if viewer is not None:
                viewer.show_error("History entry is no longer available")
            return
        http_raw = payload.get("http") if isinstance(payload, dict) else None
        http_data = http_raw if isinstance(http_raw, dict) else None
        entry = cast(RequestHistoryEntryDict, entry_raw)
        QTimer.singleShot(
            0,
            lambda c=ctx, e=entry, h=http_data: self._apply_orphan_history_to_tab(c, e, h),
        )

    def _apply_orphan_history_to_tab(
        self,
        ctx: TabContext,
        entry: RequestHistoryEntryDict,
        http_response: dict[str, Any] | None,
    ) -> None:
        """Populate draft tab editor and response viewer from a full history entry."""
        editor = ctx.editor
        if editor is None or not Shiboken.isValid(editor):
            return
        viewer = ctx.response_viewer
        snapshot = RequestHistoryService.build_replay_request_dict(entry)
        coll_raw = snapshot.get("collection_id")
        if isinstance(coll_raw, int):
            ctx.variable_collection_id = coll_raw
        else:
            ctx.variable_collection_id = None
        editor.load_request(cast(RequestLoadDict, snapshot), request_id=None)
        editor._set_dirty(True)
        name = str(entry.get("request_name", "") or snapshot.get("name", "") or "Untitled Request")
        ctx.draft_name = name
        method = str(snapshot.get("method", "GET") or "GET")
        idx = self._tab_bar.currentIndex()  # type: ignore[attr-defined]
        self._tab_bar.update_tab(idx, method=method, name=name)  # type: ignore[attr-defined]
        self._breadcrumb_bar.set_path(  # type: ignore[attr-defined]
            [{"name": name, "type": "request", "id": 0}]
        )
        if viewer is not None and http_response is not None:
            viewer.load_stored_response(http_response)
        self._refresh_variable_map(  # type: ignore[attr-defined]
            editor,
            None,
            ctx.local_overrides,
            collection_id=ctx.variable_collection_id,
        )
        self._refresh_sidebar(history_load_detail=False)  # type: ignore[attr-defined]
        QTimer.singleShot(0, self._persist_open_tabs)  # type: ignore[attr-defined]

    def _tab_context_for_request_id(self, request_id: int) -> TabContext | None:
        """Return the tab context for an open request tab, if any."""
        for ctx in self._tabs.values():  # type: ignore[attr-defined]
            if ctx.tab_type == "request" and ctx.request_id == request_id:
                return cast(TabContext, ctx)
        return None
