"""Tab lifecycle and navigation mixin for the main window.

Provides ``_TabControllerMixin`` with tab CRUD, folder tabs, breadcrumb
handling, and navigation history.  Mixed into ``MainWindow``.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import QTimer

from services.collection_service import CollectionService, RequestLoadDict
from services.local_script_service import LocalScriptService
from ui.local_scripts.local_script_editor_widget import LocalScriptEditorWidget
from ui.local_scripts.script_filename import script_display_name
from ui.request.navigation.tab_manager import TabContext, allocate_tab_nav_token
from ui.request.request_editor import RequestEditorWidget
from ui.request.response_viewer import ResponseViewerWidget

if TYPE_CHECKING:
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QPushButton, QStackedWidget, QWidget

    from ui.collections.collection_widget import CollectionWidget
    from ui.environments.environment_sidebar_panel import EnvironmentSidebarPanel
    from ui.request.navigation.breadcrumb_bar import BreadcrumbBar
    from ui.request.navigation.request_tab_bar import RequestTabBar
    from ui.sidebar.left_sidebar import LeftSidebar
    from ui.sidebar.sidebar_widget import RightSidebar
    from ui.styling.tab_settings_manager import TabSettingsManager

logger = logging.getLogger(__name__)

# Maximum number of entries in the back/forward navigation history
_MAX_HISTORY = 50


class _TabControllerMixin:
    """Mixin that manages request / folder tab lifecycle.

    Expects the host class to provide ``_tabs``, ``_tab_bar``,
    ``_editor_stack``, ``_response_stack``, ``_breadcrumb_bar``,
    ``_response_area``, ``_save_btn``, ``request_widget``,
    ``response_widget``, ``_default_editor``,
    ``_default_response_viewer``, ``_history``, ``_history_index``,
    ``collection_widget``, and the variable / send helper methods.
    """

    # -- Host-class interface (declared for mypy) -----------------------
    _tabs: dict[int, TabContext]
    _tab_bar: RequestTabBar
    _editor_stack: QStackedWidget
    _response_stack: QStackedWidget
    _breadcrumb_bar: BreadcrumbBar
    _response_area: QWidget
    _save_btn: QPushButton
    _default_editor: RequestEditorWidget
    _default_response_viewer: ResponseViewerWidget
    _history: list[int]
    _history_index: int
    request_widget: RequestEditorWidget
    response_widget: ResponseViewerWidget
    collection_widget: CollectionWidget
    local_scripts_widget: CollectionWidget
    back_action: QAction
    forward_action: QAction
    _tab_settings_manager: TabSettingsManager
    _tab_open_counter: int
    _tab_activation_counter: int
    _restoring_session: bool
    _deferred_tabs: dict[int, dict]
    _tab_change_debounce: QTimer
    _left_sidebar: LeftSidebar
    _right_sidebar: RightSidebar
    _env_selector: EnvironmentSidebarPanel

    def _on_send_request(self) -> None: ...
    def _on_save_request(self) -> None: ...
    def _on_save_response(self, data: dict) -> None: ...
    def _sync_save_btn(self, dirty: bool) -> None: ...
    def _current_tab_context(self) -> TabContext | None: ...
    def _on_run_collection_by_id(self, collection_id: int) -> None: ...
    def _on_debug_step(self, mode_name: str) -> None: ...
    def _on_open_scripting_settings(self) -> None: ...
    def _refresh_variable_map(
        self,
        editor: RequestEditorWidget,
        request_id: int | None,
        local_overrides: dict | None = ...,
    ) -> None: ...
    def _refresh_sidebar(self, ctx: TabContext | None = None) -> None: ...
    def _schedule_sidebar_snippet_refresh(self) -> None: ...
    def _on_environments_data_changed(self) -> None: ...
    def _record_tab_activation(self, index: int) -> None: ...
    def _seed_tab_nav_after_restore(self) -> None: ...
    def _purge_tab_nav_token(self, token: int) -> None: ...

    # ------------------------------------------------------------------
    # Open request
    # ------------------------------------------------------------------
    def _open_request(
        self,
        request_id: int,
        *,
        push_history: bool,
        is_preview: bool = False,
    ) -> None:
        """Load a request in a tab -- reuse existing or create new.

        When *is_preview* is ``True`` the tab is italic and will be
        replaced by subsequent preview opens.  When ``False`` (the
        default) the tab is permanent.
        """
        if is_preview and not self._tab_settings_manager.enable_preview_tab:
            is_preview = False

        # 1. Check if already open in a materialised tab — no DB needed
        for idx, ctx in self._tabs.items():
            if ctx.request_id == request_id:
                self._tab_bar.setCurrentIndex(idx)
                # Promote preview -> permanent on explicit Open
                if not is_preview and ctx.is_preview:
                    ctx.is_preview = False
                    self._tab_bar.update_tab(idx, is_preview=False)
                self._flush_tab_change()
                return

        # 1b. Check if already open in a deferred (lazy) tab — no DB needed
        for idx, info in self._deferred_tabs.items():
            if info.get("request_id") == request_id:
                self._tab_bar.setCurrentIndex(idx)
                self._flush_tab_change()
                return

        # 2. Fetch from database only when we actually need to create a tab
        request = CollectionService.get_request(request_id)
        if request is None:
            logger.warning("Request id=%s not found", request_id)
            return

        request_path = self._request_full_path(request_id)

        data: RequestLoadDict = {
            "name": request.name,
            "method": request.method,
            "url": request.url,
            "body": request.body,
            "request_parameters": request.request_parameters,
            "headers": request.headers,
            "description": request.description,
            "scripts": request.scripts or request.events,
            "body_mode": request.body_mode,
            "body_options": request.body_options,
            "auth": request.auth,
        }

        # 3. Replace current preview tab if one exists
        current_idx = self._tab_bar.currentIndex()
        current_ctx = self._tabs.get(current_idx)
        if current_ctx is not None and current_ctx.is_preview:
            self._replace_tab(
                current_idx,
                request_id,
                data,
                is_preview=is_preview,
                path=request_path,
            )
        else:
            # 4. Open a new tab
            self._create_tab(request_id, data, is_preview=is_preview, path=request_path)

        if push_history:
            self._history = self._history[: self._history_index + 1]
            self._history.append(request_id)
            if len(self._history) > _MAX_HISTORY:
                self._history = self._history[-_MAX_HISTORY:]
            self._history_index = len(self._history) - 1
            self._update_nav_actions()

    # ------------------------------------------------------------------
    # Tab CRUD
    # ------------------------------------------------------------------
    def _create_tab(
        self,
        request_id: int,
        data: RequestLoadDict,
        *,
        is_preview: bool = False,
        path: str | None = None,
    ) -> int:
        """Create a new tab for a request and switch to it."""
        if not self._enforce_tab_limit_before_open():
            return self._tab_bar.currentIndex()

        editor = RequestEditorWidget()
        viewer = ResponseViewerWidget()

        self._editor_stack.addWidget(editor)
        self._response_stack.addWidget(viewer)

        ctx = TabContext(
            request_id=request_id,
            editor=editor,
            response_viewer=viewer,
            is_preview=is_preview,
            opened_order=self._next_tab_open_order(),
        )

        insert_index = self._next_tab_insert_index()
        self._shift_tabs_for_insert(insert_index)

        # Block signals while adding the tab to avoid premature
        # _on_tab_changed before ctx is stored.
        self._tab_bar.blockSignals(True)
        try:
            idx = self._tab_bar.add_request_tab(
                data.get("method", "GET"),
                data.get("name", ""),
                is_preview=is_preview,
                path=path,
                index=insert_index,
            )
        finally:
            self._tab_bar.blockSignals(False)

        self._tabs[idx] = ctx

        editor.load_request(data, request_id=request_id)
        editor.send_requested.connect(self._on_send_request)
        editor.debug_step_requested.connect(self._on_debug_step)
        editor.open_collection_requested.connect(self._open_folder)
        editor.open_scripting_settings_requested.connect(self._on_open_scripting_settings)
        editor.save_requested.connect(self._on_save_request)
        editor.dirty_changed.connect(self._sync_save_btn)
        editor.dirty_changed.connect(self._on_editor_dirty_changed)
        editor.request_changed.connect(lambda _: self._schedule_sidebar_snippet_refresh())
        editor.scripts_tab_active_changed.connect(self._on_editor_scripts_tab_changed)
        viewer.save_response_requested.connect(self._on_save_response)
        viewer.save_availability_changed.connect(lambda _enabled: self._refresh_sidebar())

        # Now switch to the tab (triggers _on_tab_changed safely)
        self._tab_bar.setCurrentIndex(idx)
        # Ensure stacks are synced even if setCurrentIndex didn't emit
        self._on_tab_changed(idx)
        # Flush the debounced heavy work immediately for programmatic opens
        self._flush_tab_change()
        self._persist_open_tabs()
        return idx

    def _open_local_script(self, script_id: int) -> None:
        """Open a persisted local script in a centre editor tab."""
        if not self._enforce_tab_limit_before_open():
            return

        for idx, ctx in self._tabs.items():
            if ctx.tab_type == "local_script" and ctx.local_script_id == script_id:
                self._tab_bar.setCurrentIndex(idx)
                self._flush_tab_change()
                return

        data = LocalScriptService.get_script_load_dict(script_id)
        if data is None:
            return

        editor = LocalScriptEditorWidget()
        self._editor_stack.addWidget(editor)

        ctx = TabContext(
            tab_type="local_script",
            local_script_id=script_id,
            local_script_editor=editor,
            opened_order=self._next_tab_open_order(),
        )

        insert_index = self._next_tab_insert_index()
        self._shift_tabs_for_insert(insert_index)

        language = data.get("language", "javascript")
        module_format = data.get("module_format", "esm") or "esm"
        self._tab_bar.blockSignals(True)
        try:
            idx = self._tab_bar.add_script_tab(
                language,
                data.get("name", "Script"),
                path=None,
                module_format=module_format,
                index=insert_index,
            )
        finally:
            self._tab_bar.blockSignals(False)

        self._tabs[idx] = ctx
        editor.load_script(data)
        self._bind_local_script_autosave(editor, script_id)
        editor.dirty_changed.connect(self._sync_save_btn)
        editor.dirty_changed.connect(self._on_local_script_dirty_changed)
        editor.save_requested.connect(self._on_save_local_script)
        editor.open_scripting_settings_requested.connect(self._on_open_scripting_settings)
        editor.debug_step_requested.connect(self._on_debug_step)
        editor.local_script_saved.connect(self._on_local_script_saved)

        self._tab_bar.setCurrentIndex(idx)
        self._on_tab_changed(idx)
        self._flush_tab_change()
        self._persist_open_tabs()

    def _replace_tab(
        self,
        index: int,
        request_id: int,
        data: RequestLoadDict,
        *,
        is_preview: bool = False,
        path: str | None = None,
    ) -> None:
        """Replace the content of an existing tab with a new request."""
        ctx = self._tabs.get(index)
        if ctx is None:
            return

        ctx.cancel_send()
        ctx.request_id = request_id
        ctx.is_preview = is_preview
        editor = ctx.require_editor()
        viewer = ctx.require_response_viewer()
        editor.load_request(data, request_id=request_id)
        viewer.clear()

        # Refresh variable map for the replaced tab
        self._refresh_variable_map(editor, request_id, ctx.local_overrides)

        self._tab_bar.update_tab(
            index,
            method=data.get("method", "GET"),
            name=data.get("name", ""),
            path=path,
            is_preview=is_preview,
            is_dirty=False,
        )
        self._persist_open_tabs()

    def _request_full_path(self, request_id: int) -> str | None:
        """Return the full breadcrumb path for a request tab."""
        crumbs = CollectionService.get_request_breadcrumb(request_id)
        if not crumbs:
            return None
        return " / ".join(str(crumb.get("name", "")) for crumb in crumbs if crumb.get("name"))

    def _next_tab_open_order(self) -> int:
        """Return the next creation-order token for a new tab."""
        self._tab_open_counter += 1
        return self._tab_open_counter

    def _next_tab_insert_index(self) -> int:
        """Return the insertion index for a new tab according to settings."""
        current = self._tab_bar.currentIndex()
        if self._tab_settings_manager.open_new_tabs_at_end or current < 0:
            return self._tab_bar.count()
        return current + 1

    def _shift_tabs_for_insert(self, index: int) -> None:
        """Shift tab contexts when inserting a tab into the middle."""
        self._tabs = {
            (old_idx if old_idx < index else old_idx + 1): ctx
            for old_idx, ctx in self._tabs.items()
        }
        self._deferred_tabs = {
            (old_idx if old_idx < index else old_idx + 1): info
            for old_idx, info in self._deferred_tabs.items()
        }

    def _tab_index_for_debug_host(self, host: Any) -> int | None:
        """Return the tab index whose editor matches *host*, if any."""
        if host is None:
            return None
        for idx, ctx in self._tabs.items():
            if ctx.tab_type == "request" and ctx.editor is host:
                return idx
            if ctx.tab_type == "folder" and ctx.folder_editor is host:
                return idx
            if ctx.tab_type == "local_script" and ctx.local_script_editor is host:
                return idx
        return None

    def _clear_tab_debug_indicators(self) -> None:
        """Remove debug icon/accent from every tab."""
        for idx, ctx in self._tabs.items():
            if not ctx.is_debugging:
                continue
            ctx.is_debugging = False
            self._tab_bar.update_tab(idx, is_debugging=False)

    def _set_tab_debugging_for_host(self, host: Any, active: bool) -> None:
        """Show or hide the debug tab indicator on the tab that owns *host*."""
        if active:
            self._clear_tab_debug_indicators()
        idx = self._tab_index_for_debug_host(host)
        if idx is None:
            return
        ctx = self._tabs.get(idx)
        if ctx is None:
            return
        ctx.is_debugging = active
        self._tab_bar.update_tab(idx, is_debugging=active)

    def _on_editor_dirty_changed(self, dirty: bool) -> None:
        """Sync dirty state from the emitting editor back into the tab metadata."""
        sender_fn = cast(Any, getattr(self, "sender", None))
        sender = sender_fn() if callable(sender_fn) else None
        if sender is None:
            return
        for idx, ctx in self._tabs.items():
            if ctx.tab_type == "request" and ctx.require_editor() is sender:
                ctx.is_dirty = dirty
                self._tab_bar.update_tab(idx, is_dirty=dirty)
                break

    def _on_local_script_dirty_changed(self, dirty: bool) -> None:
        """Sync dirty state from a local-script editor into tab metadata."""
        sender_fn = cast(Any, getattr(self, "sender", None))
        sender = sender_fn() if callable(sender_fn) else None
        if sender is None:
            return
        for idx, ctx in self._tabs.items():
            if (
                ctx.tab_type == "local_script"
                and ctx.local_script_editor is not None
                and ctx.local_script_editor is sender
            ):
                ctx.is_dirty = dirty
                self._tab_bar.update_tab(idx, is_dirty=dirty)
                break

    def _on_local_script_saved(self, script_id: int) -> None:
        """Refresh host script editors that directly require *script_id*."""
        from ui.widgets.code_editor.editor_lsp_glue import refresh_dependency_diagnostics_for_script

        refresh_dependency_diagnostics_for_script(script_id)

    def _go_to_local_script_position(self, script_id: int, line_1: int, column_1: int) -> None:
        """Open or focus a local script tab and move the cursor."""
        for idx, ctx in self._tabs.items():
            if ctx.tab_type == "local_script" and ctx.local_script_id == script_id:
                self._tab_bar.setCurrentIndex(idx)
                self._flush_tab_change()
                editor = ctx.local_script_editor
                if editor is not None:
                    editor.go_to_position(line_1, column_1)
                return
        self._open_local_script(script_id)
        opened_ctx = self._tabs.get(self._tab_bar.currentIndex())
        if opened_ctx is not None and opened_ctx.local_script_editor is not None:
            opened_ctx.local_script_editor.go_to_position(line_1, column_1)

    def _on_editor_scripts_tab_changed(self, scripts_active: bool) -> None:
        """Hide the response area while the active editor's Scripts tab is open.

        Gated on ``sender is active editor`` so a Scripts-tab toggle on a
        background tab doesn't affect the currently visible response area.
        Folder tabs already hide the response area unconditionally; leave
        that path alone.
        """
        sender_fn = cast(Any, getattr(self, "sender", None))
        sender = sender_fn() if callable(sender_fn) else None
        if sender is not self.request_widget:
            return
        ctx = self._current_tab_context()
        if ctx is not None and ctx.tab_type in ("folder", "environments"):
            return
        self._response_area.setVisible(not scripts_active)

    def _on_tab_changed(self, index: int) -> None:
        """Switch the stacked widgets when the active tab changes.

        Only the lightweight visual switch runs synchronously.  Heavy
        work (breadcrumb fetch, variable map, sidebar refresh, tree
        sync) is debounced via ``_tab_change_debounce`` so that rapid
        scrolling through tabs does not pile up expensive DB calls.
        """
        if getattr(self, "_restoring_session", False):
            return

        # Materialise deferred (lazy-loaded) tab on first selection
        if index in getattr(self, "_deferred_tabs", {}):
            self._materialise_deferred_tab(index)

        ctx = self._tabs.get(index)
        if ctx is not None:
            self._tab_activation_counter += 1
            ctx.last_activated_order = self._tab_activation_counter

        # -- Fast visual switch (no DB calls) --------------------------
        if ctx is not None and ctx.tab_type == "folder":
            if ctx.folder_editor is not None:
                self._editor_stack.setCurrentWidget(ctx.folder_editor)
            self._response_area.hide()
            self._save_btn.setVisible(False)
        elif ctx is not None and ctx.tab_type == "environments":
            if ctx.environment_editor is not None:
                self._editor_stack.setCurrentWidget(ctx.environment_editor)
            self._response_area.hide()
            self._save_btn.setVisible(False)
        elif ctx is not None and ctx.tab_type == "local_script":
            if ctx.local_script_editor is not None:
                self._editor_stack.setCurrentWidget(ctx.local_script_editor)
            self._response_area.hide()
            self._save_btn.setVisible(True)
            if ctx.local_script_editor is not None:
                self._sync_save_btn(ctx.local_script_editor.is_dirty())
        elif ctx is not None:
            editor = ctx.require_editor()
            viewer = ctx.require_response_viewer()
            self._editor_stack.setCurrentWidget(editor)
            self._response_stack.setCurrentWidget(viewer)
            self.request_widget = editor
            self.response_widget = viewer
            # Response area defaults to visible, but the Scripts section tab
            # gives its Output/Problems/Mock panel the full bottom row.
            self._response_area.setVisible(not editor.is_scripts_tab_active())
            self._save_btn.setVisible(True)
            self._sync_save_btn(editor.is_dirty)
        else:
            self._editor_stack.setCurrentWidget(self._default_editor)
            self._response_stack.setCurrentWidget(self._default_response_viewer)
            self.request_widget = self._default_editor
            self.response_widget = self._default_response_viewer
            self._breadcrumb_bar.clear()
            self._save_btn.setVisible(False)

        # -- Debounce the heavy work -----------------------------------
        self._tab_change_debounce.start()
        self._record_tab_activation(index)

    def _on_tab_change_settled(self, *, sync_tree: bool = True) -> None:
        """Run expensive refresh work after tab changes settle.

        Invoked by the ``_tab_change_debounce`` single-shot timer so
        that rapid scrolling coalesces into one heavy update.

        Collection tree selection is synced by default so clicking a
        tab highlights the corresponding item in the sidebar.
        """
        index = self._tab_bar.currentIndex()
        ctx = self._tabs.get(index)

        # -- Breadcrumb ------------------------------------------------
        if ctx is not None and ctx.tab_type == "folder":
            if ctx.collection_id is not None:
                crumbs = CollectionService.get_collection_breadcrumb(ctx.collection_id)
                self._breadcrumb_bar.set_path(crumbs)
            else:
                self._breadcrumb_bar.clear()
        elif ctx is not None and ctx.tab_type == "environments":
            self._breadcrumb_bar.clear()
        elif ctx is not None and ctx.tab_type == "local_script":
            if ctx.local_script_id is not None:
                self._breadcrumb_bar.set_path(
                    self._local_script_breadcrumbs_with_display(ctx.local_script_id)
                )
            else:
                self._breadcrumb_bar.clear()
        elif ctx is not None:
            if ctx.request_id is not None:
                cached = getattr(ctx, "_cached_crumbs", None)
                if cached is not None:
                    crumbs = cached
                    del ctx._cached_crumbs  # type: ignore[attr-defined]
                else:
                    crumbs = CollectionService.get_request_breadcrumb(ctx.request_id)
                self._breadcrumb_bar.set_path(crumbs)
            elif ctx.draft_name is not None:
                self._breadcrumb_bar.set_path(
                    [{"name": ctx.draft_name, "type": "request", "id": 0}]
                )
            else:
                self._breadcrumb_bar.clear()
            # Refresh variable map for highlighting and tooltips
            self._refresh_variable_map(ctx.require_editor(), ctx.request_id, ctx.local_overrides)

        # Refresh right sidebar for the active tab.
        self._refresh_sidebar(ctx)

        # Sync collection tree selection only on programmatic opens —
        # not on timer-fired calls from tab-bar scrolling, to avoid
        # hijacking the tree scroll while the user browses the sidebar.
        if sync_tree:
            self._sync_tree_selection(ctx)

    def _flush_tab_change(self) -> None:
        """Immediately run pending debounced tab-change work.

        Called after programmatic tab opens and closes so the heavy
        refresh happens synchronously instead of after the timer delay.
        Tree selection sync is included since this is user-initiated.
        """
        if self._tab_change_debounce.isActive():
            self._tab_change_debounce.stop()
            self._on_tab_change_settled(sync_tree=True)

    def _sync_tree_selection(self, ctx: TabContext | None) -> None:
        """Highlight the active tab's item in the collection tree."""
        if ctx is None:
            return
        if ctx.tab_type == "environments":
            return
        if ctx.tab_type == "folder" and ctx.collection_id is not None:
            self.collection_widget.select_and_scroll_to(ctx.collection_id, "folder")
        elif ctx.tab_type == "local_script" and ctx.local_script_id is not None:
            self.local_scripts_widget.select_and_scroll_to(ctx.local_script_id, "script")
        elif ctx.request_id is not None:
            self.collection_widget.select_and_scroll_to(ctx.request_id, "request")

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------
    def _persist_open_tabs(self) -> None:
        """Save the current tab list to settings for session restore."""
        if getattr(self, "_restoring_session", False):
            return
        tabs_list: list[dict[str, object]] = []
        all_indices = sorted(set(self._tabs) | set(self._deferred_tabs))
        for idx in all_indices:
            ctx = self._tabs.get(idx)
            if ctx is not None:
                if ctx.tab_type == "folder" and ctx.collection_id is not None:
                    tabs_list.append({"type": "folder", "id": ctx.collection_id})
                elif ctx.tab_type == "environments":
                    tabs_list.append({"type": "environments"})
                elif ctx.tab_type == "local_script" and ctx.local_script_id is not None:
                    _method, name = self._tab_bar.tab_request_info(idx)
                    pane = ctx.local_script_editor
                    language = "javascript"
                    module_format = "esm"
                    if pane is not None:
                        language = pane._pane.editor.language
                        module_format = pane._pane.editor.script_module_format
                    tabs_list.append(
                        {
                            "type": "local_script",
                            "id": ctx.local_script_id,
                            "name": name,
                            "language": language,
                            "module_format": module_format,
                        }
                    )
                elif ctx.tab_type == "request" and ctx.request_id is not None:
                    method, name = self._tab_bar.tab_request_info(idx)
                    ed = ctx.require_editor()
                    tabs_list.append(
                        {
                            "type": "request",
                            "id": ctx.request_id,
                            "method": method or ed.get_request_data().get("method", "GET"),
                            "name": name,
                        }
                    )
                elif ctx.tab_type == "request" and ctx.request_id is None:
                    # Draft (unsaved) tab — snapshot the editor state.
                    ed = ctx.require_editor()
                    entry: dict[str, object] = {
                        "type": "draft",
                        "data": ed.get_request_data(),
                    }
                    draft_debug = ed.collect_draft_debug_blob()
                    if draft_debug:
                        entry["debug"] = draft_debug
                    if ctx.draft_name:
                        entry["draft_name"] = ctx.draft_name
                    tabs_list.append(entry)
            else:
                # Deferred (not-yet-materialised) tab
                info = self._deferred_tabs.get(idx)
                if info is not None:
                    if info.get("type") == "local_script":
                        tabs_list.append(
                            {
                                "type": "local_script",
                                "id": info["script_id"],
                                "name": info.get("name", "Script"),
                                "language": info.get("language", "javascript"),
                                "module_format": info.get("module_format", "esm"),
                            }
                        )
                    else:
                        tabs_list.append(
                            {
                                "type": "request",
                                "id": info["request_id"],
                                "method": info.get("method", "GET"),
                                "name": info.get("name", ""),
                            }
                        )
        data: dict[str, object] = {
            "tabs": tabs_list,
            "active": self._tab_bar.currentIndex(),
            "left_sidebar_panel": self._left_sidebar.session_panel_key(),
            "sidebar_panel": self._right_sidebar.active_panel,
            "sidebar_width": self._right_sidebar.flyout_width,
        }
        self._tab_settings_manager.save_open_tabs(data)

    def _restore_tabs(self) -> None:
        """Restore tabs from the last session after collections have loaded.

        Request tabs are restored **lazily**: only a lightweight tab-bar
        chip is created upfront.  The actual editor and response viewer
        widgets are materialised on first selection via
        :meth:`_materialise_deferred_tab`.  Draft and folder tabs are
        still created eagerly because they require immediate state
        (editor snapshot / folder metadata).  **Environments** tabs are
        materialised eagerly (no database id); each ``{"type": "environments"}``
        entry creates the global editor widget.
        """
        data = self._tab_settings_manager.load_open_tabs()
        if data is None:
            self._left_sidebar.open_panel()
            return

        tabs_list = data.get("tabs")
        if not isinstance(tabs_list, list):
            return

        active = data.get("active", 0)

        # Suppress per-tab persist calls — the data is already saved.
        self._restoring_session = True
        try:
            for entry in tabs_list:
                if not isinstance(entry, dict):
                    continue
                tab_type = entry.get("type")
                if tab_type == "draft":
                    self._restore_draft(entry)
                    continue
                if tab_type == "environments":
                    if self._find_environments_tab_index() is not None:
                        continue
                    if not self._enforce_tab_limit_before_open():
                        logger.warning(
                            "Skipping environments tab restore: tab limit reached",
                        )
                        continue
                    self._materialize_environments_tab_at(self._tab_bar.count())
                    continue
                item_id = entry.get("id")
                if not isinstance(item_id, int):
                    continue
                if tab_type == "request":
                    self._restore_request_deferred(entry, item_id)
                elif tab_type == "folder":
                    self._open_folder(item_id, show_missing_warning=False)
                elif tab_type == "local_script":
                    if LocalScriptService.get_script(item_id) is None:
                        continue
                    self._restore_local_script_deferred(entry, item_id)
        finally:
            self._restoring_session = False

        if isinstance(active, int) and 0 <= active < self._tab_bar.count():
            self._tab_bar.setCurrentIndex(active)
            self._on_tab_changed(active)
            self._flush_tab_change()

        self._seed_tab_nav_after_restore()

        left_panel = data.get("left_sidebar_panel")
        if isinstance(left_panel, str):
            self._left_sidebar.open_panel(left_panel)
        elif not self._left_sidebar.is_open:
            self._left_sidebar.open_panel()

        sidebar_panel = data.get("sidebar_panel")
        if isinstance(sidebar_panel, str):
            self._right_sidebar.open_panel(sidebar_panel)
            sidebar_width = data.get("sidebar_width")
            if isinstance(sidebar_width, int) and sidebar_width > 0:
                self._right_sidebar._expand_flyout(sidebar_width)

    def _restore_request_deferred(self, entry: dict, request_id: int) -> None:
        """Create a lightweight tab chip for a persisted request tab.

        If the session entry contains ``method`` and ``name`` (new format),
        the chip is created without any database query.  Otherwise we fall
        back to eager loading via :meth:`_open_request`.
        """
        method = entry.get("method")
        name = entry.get("name")
        if not isinstance(method, str) or not isinstance(name, str):
            # Old format — fall back to eager loading
            self._open_request(request_id, push_history=False, is_preview=False)
            return

        # Block signals while adding the tab to avoid premature events.
        self._tab_bar.blockSignals(True)
        try:
            idx = self._tab_bar.add_request_tab(
                method,
                name,
                is_preview=False,
                path=None,
            )
        finally:
            self._tab_bar.blockSignals(False)

        self._deferred_tabs[idx] = {
            "request_id": request_id,
            "method": method,
            "name": name,
            "nav_token": allocate_tab_nav_token(),
        }

    def _restore_local_script_deferred(self, entry: dict, script_id: int) -> None:
        """Create a lightweight tab chip for a persisted local script tab."""
        name = str(entry.get("name") or "Script")
        language = str(entry.get("language") or "javascript")
        module_format = str(entry.get("module_format") or "esm")
        self._tab_bar.blockSignals(True)
        try:
            idx = self._tab_bar.add_script_tab(
                language,
                name,
                path=None,
                module_format=module_format,
            )
        finally:
            self._tab_bar.blockSignals(False)
        self._deferred_tabs[idx] = {
            "type": "local_script",
            "script_id": script_id,
            "name": name,
            "language": language,
            "module_format": module_format,
            "nav_token": allocate_tab_nav_token(),
        }

    def _materialise_deferred_tab(self, index: int) -> None:
        """Build the editor and viewer for a deferred tab on first selection.

        Fetches the full request data from the database, creates the
        editor/viewer pair, populates the editor, and wires signals.
        If the database record was deleted between sessions, the tab
        chip is silently removed.

        The breadcrumb crumbs are cached on the context as
        ``_cached_crumbs`` so that :meth:`_on_tab_changed` can skip
        the redundant ``get_request_breadcrumb`` call.
        """
        info = self._deferred_tabs.pop(index)
        if info.get("type") == "local_script":
            self._materialise_deferred_local_script(index, info)
            return

        request_id: int = info["request_id"]

        request = CollectionService.get_request(request_id)
        if request is None:
            logger.warning("Deferred request id=%s not found, removing tab", request_id)
            raw_token = info.get("nav_token")
            if isinstance(raw_token, int):
                self._purge_tab_nav_token(raw_token)
            self._tab_bar.remove_request_tab(index)
            self._reindex_tabs_after_close(index)
            return

        req_data: RequestLoadDict = {
            "name": request.name,
            "method": request.method,
            "url": request.url,
            "body": request.body,
            "request_parameters": request.request_parameters,
            "headers": request.headers,
            "description": request.description,
            "scripts": request.scripts or request.events,
            "body_mode": request.body_mode,
            "body_options": request.body_options,
            "auth": request.auth,
        }

        editor = RequestEditorWidget()
        viewer = ResponseViewerWidget()
        self._editor_stack.addWidget(editor)
        self._response_stack.addWidget(viewer)

        saved_token = info.get("nav_token")
        nav_token = saved_token if isinstance(saved_token, int) else None
        ctx = TabContext(
            request_id=request_id,
            editor=editor,
            response_viewer=viewer,
            is_preview=False,
            opened_order=self._next_tab_open_order(),
            nav_token=nav_token,
        )
        self._tabs[index] = ctx

        editor.load_request(req_data, request_id=request_id)
        editor.send_requested.connect(self._on_send_request)
        editor.debug_step_requested.connect(self._on_debug_step)
        editor.open_collection_requested.connect(self._open_folder)
        editor.open_scripting_settings_requested.connect(self._on_open_scripting_settings)
        editor.save_requested.connect(self._on_save_request)
        editor.dirty_changed.connect(self._sync_save_btn)
        editor.dirty_changed.connect(self._on_editor_dirty_changed)
        editor.request_changed.connect(lambda _: self._schedule_sidebar_snippet_refresh())
        editor.scripts_tab_active_changed.connect(self._on_editor_scripts_tab_changed)
        viewer.save_response_requested.connect(self._on_save_response)
        viewer.save_availability_changed.connect(lambda _enabled: self._refresh_sidebar())

        # Fetch breadcrumb once — reused by both the tab tooltip and
        # _on_tab_changed (via _cached_crumbs) to avoid a duplicate query.
        crumbs = CollectionService.get_request_breadcrumb(request_id)
        request_path = (
            " / ".join(str(c.get("name", "")) for c in crumbs if c.get("name")) if crumbs else None
        )
        ctx._cached_crumbs = crumbs  # type: ignore[attr-defined]

        self._tab_bar.update_tab(
            index,
            method=req_data.get("method", "GET"),
            name=req_data.get("name", ""),
            path=request_path,
        )

    def _materialise_deferred_local_script(self, index: int, info: dict) -> None:
        """Build the local script editor on first selection of a deferred tab chip."""
        script_id: int = info["script_id"]
        data = LocalScriptService.get_script_load_dict(script_id)
        if data is None:
            logger.warning("Deferred local script id=%s not found, removing tab", script_id)
            raw_token = info.get("nav_token")
            if isinstance(raw_token, int):
                self._purge_tab_nav_token(raw_token)
            self._tab_bar.remove_request_tab(index)
            self._reindex_tabs_after_close(index)
            return

        editor = LocalScriptEditorWidget()
        self._editor_stack.addWidget(editor)

        saved_token = info.get("nav_token")
        nav_token = saved_token if isinstance(saved_token, int) else None
        ctx = TabContext(
            tab_type="local_script",
            local_script_id=script_id,
            local_script_editor=editor,
            opened_order=self._next_tab_open_order(),
            nav_token=nav_token,
        )
        self._tabs[index] = ctx

        editor.load_script(data)
        self._bind_local_script_autosave(editor, script_id)
        editor.dirty_changed.connect(self._sync_save_btn)
        editor.dirty_changed.connect(self._on_local_script_dirty_changed)
        editor.save_requested.connect(self._on_save_local_script)
        editor.open_scripting_settings_requested.connect(self._on_open_scripting_settings)
        editor.debug_step_requested.connect(self._on_debug_step)
        editor.local_script_saved.connect(self._on_local_script_saved)

        crumbs = self._local_script_breadcrumbs_with_display(script_id)
        script_path = (
            " / ".join(str(c.get("name", "")) for c in crumbs if c.get("name")) if crumbs else None
        )
        self._tab_bar.update_tab(
            index,
            name=data.get("name", info.get("name", "Script")),
            path=script_path,
        )

    def _restore_draft(self, entry: dict) -> None:
        """Restore a single draft tab from persisted session data."""
        draft_data = entry.get("data")
        if not isinstance(draft_data, dict):
            return
        draft_name = entry.get("draft_name")
        if isinstance(draft_name, str):
            draft_data["name"] = draft_name
        self._open_draft_request()  # type: ignore[attr-defined]
        # The new draft tab is now the active tab — overwrite its
        # default blank state with the persisted editor snapshot.
        idx = self._tab_bar.currentIndex()
        ctx = self._tabs.get(idx)
        if ctx is None or ctx.request_id is not None:
            return
        ed = ctx.require_editor()
        ed.load_request(cast(RequestLoadDict, draft_data), request_id=None)
        draft_debug = entry.get("debug")
        if draft_debug is not None:
            ed.apply_draft_debug_blob(draft_debug)
        ed._set_dirty(True)
        if isinstance(draft_name, str):
            ctx.draft_name = draft_name
            method = draft_data.get("method", "GET")
            self._tab_bar.update_tab(idx, method=method, name=draft_name)

    # ------------------------------------------------------------------
    # Tab close
    # ------------------------------------------------------------------
    def _on_tab_close(self, index: int) -> None:
        """Close a tab and clean up its context."""
        # Handle deferred (lazy) tab close — no widgets to clean up
        if index in self._deferred_tabs:
            target_old_index = self._target_tab_after_close(index)
            deferred_info = self._deferred_tabs[index]
            raw_token = deferred_info.get("nav_token")
            if isinstance(raw_token, int):
                self._purge_tab_nav_token(raw_token)
            self._deferred_tabs.pop(index)
            self._tab_bar.remove_request_tab(index)
            self._reindex_tabs_after_close(index)
            target_new_index = self._normalize_target_index_after_close(index, target_old_index)
            if target_new_index is not None and 0 <= target_new_index < self._tab_bar.count():
                self._tab_bar.setCurrentIndex(target_new_index)
                self._on_tab_changed(target_new_index)
            else:
                self._on_tab_changed(self._tab_bar.currentIndex())
            self._flush_tab_change()
            self._persist_open_tabs()
            return

        target_old_index = self._target_tab_after_close(index)
        ctx = self._tabs.get(index)
        if ctx is None:
            return
        self._purge_tab_nav_token(ctx.nav_token)
        ctx = self._tabs.pop(index)

        ctx.cancel_send()
        ctx.cleanup_thread()

        from ui.widgets.code_editor import popup_registry

        _shared_completion = popup_registry.completion_popup()
        _shared_completion.clear_target()
        _shared_completion.hide()

        if ctx.tab_type == "folder":
            # Folder tab cleanup
            folder_editor = ctx.folder_editor
            if folder_editor is not None:
                flush_debug = getattr(folder_editor, "flush_debug_metadata_persist_sync", None)
                if callable(flush_debug):
                    flush_debug()
                folder_editor.shutdown_runner()
                folder_editor.collection_changed.disconnect(self._on_folder_auto_save)
                self._editor_stack.removeWidget(folder_editor)
                folder_editor.setParent(None)

            ctx.dispose()
            del ctx

            self._tab_bar.remove_request_tab(index)
        elif ctx.tab_type == "environments":
            env_ed = ctx.environment_editor
            if env_ed is not None:
                with contextlib.suppress(TypeError, RuntimeError):
                    env_ed.environments_changed.disconnect(self._env_selector.refresh)
                with contextlib.suppress(TypeError, RuntimeError):
                    env_ed.environments_changed.disconnect(self._on_environments_data_changed)
                self._editor_stack.removeWidget(env_ed)
                env_ed.setParent(None)
            ctx.dispose()
            del ctx
            self._tab_bar.remove_request_tab(index)
        elif ctx.tab_type == "local_script":
            script_ed = ctx.local_script_editor
            if script_ed is not None:
                pane = getattr(script_ed, "_pane", None)
                if pane is not None and hasattr(pane, "cancel_async_lsp_prep"):
                    pane.cancel_async_lsp_prep()
                with contextlib.suppress(TypeError, RuntimeError):
                    script_ed.dirty_changed.disconnect(self._sync_save_btn)
                with contextlib.suppress(TypeError, RuntimeError):
                    script_ed.dirty_changed.disconnect(self._on_local_script_dirty_changed)
                with contextlib.suppress(TypeError, RuntimeError):
                    script_ed.save_requested.disconnect(self._on_save_local_script)
                with contextlib.suppress(TypeError, RuntimeError):
                    script_ed.open_scripting_settings_requested.disconnect(
                        self._on_open_scripting_settings
                    )
                with contextlib.suppress(TypeError, RuntimeError):
                    script_ed.debug_step_requested.disconnect(self._on_debug_step)
                self._editor_stack.removeWidget(script_ed)
                script_ed.setParent(None)
            ctx.dispose()
            del ctx
            self._tab_bar.remove_request_tab(index)
        else:
            # Request tab cleanup
            # Grab local references before dispose() nulls the context.
            editor = ctx.require_editor()
            viewer = ctx.require_response_viewer()

            flush_debug = getattr(editor, "flush_debug_metadata_persist_sync", None)
            if callable(flush_debug):
                flush_debug()

            # Disconnect signals that reference MainWindow slots so the
            # sender objects can be garbage-collected.
            editor.send_requested.disconnect(self._on_send_request)
            editor.save_requested.disconnect(self._on_save_request)
            editor.dirty_changed.disconnect(self._sync_save_btn)
            editor.dirty_changed.disconnect(self._on_editor_dirty_changed)
            editor.request_changed.disconnect()
            viewer.save_response_requested.disconnect(self._on_save_response)

            # Remove from stacked widgets and detach from parent hierarchy.
            self._editor_stack.removeWidget(editor)
            self._response_stack.removeWidget(viewer)

            # Clear heavy data so memory is freed even before the C++
            # destructor runs.
            viewer.clear()

            # Detach from any Qt parent so the C++ side is destroyed when
            # the Python wrapper is garbage-collected.
            editor.setParent(None)
            viewer.setParent(None)

            # Release all Python references held by the TabContext.
            ctx.dispose()
            del editor, viewer, ctx

            self._tab_bar.remove_request_tab(index)

        # Re-index remaining tabs (both materialised and deferred)
        self._reindex_tabs_after_close(index)

        target_new_index = self._normalize_target_index_after_close(index, target_old_index)
        if target_new_index is not None and 0 <= target_new_index < self._tab_bar.count():
            self._tab_bar.setCurrentIndex(target_new_index)
            self._on_tab_changed(target_new_index)
        else:
            self._on_tab_changed(self._tab_bar.currentIndex())
        self._flush_tab_change()
        self._persist_open_tabs()

    def _reindex_tabs_after_close(self, closed_index: int) -> None:
        """Shift tab indices down after removing a tab at *closed_index*."""
        self._tabs = {
            (idx if idx < closed_index else idx - 1): ctx for idx, ctx in self._tabs.items()
        }
        self._deferred_tabs = {
            (idx if idx < closed_index else idx - 1): info
            for idx, info in self._deferred_tabs.items()
        }

    def _on_tab_double_click(self, index: int) -> None:
        """Promote a preview tab to a permanent tab."""
        ctx = self._tabs.get(index)
        if ctx is not None and ctx.is_preview:
            ctx.is_preview = False
            self._tab_bar.update_tab(index, is_preview=False)

    def _target_tab_after_close(self, closing_index: int) -> int | None:
        """Return the preferred old-index tab to activate after closing one."""
        all_indices = set(self._tabs) | set(self._deferred_tabs)
        if not all_indices:
            return None

        current = self._tab_bar.currentIndex()
        if current != closing_index:
            return current

        remaining = [idx for idx in all_indices if idx != closing_index]
        if not remaining:
            return None

        policy = self._tab_settings_manager.activate_on_close
        if policy == "left":
            left = [idx for idx in remaining if idx < closing_index]
            return max(left) if left else min(remaining)
        if policy == "right":
            right = [idx for idx in remaining if idx > closing_index]
            return min(right) if right else max(remaining)

        # MRU policy — deferred tabs have last_activated_order = 0
        best_idx: int | None = None
        best_order = -1
        for idx in remaining:
            ctx = self._tabs.get(idx)
            last_activated = ctx.last_activated_order if ctx is not None else 0
            if last_activated > best_order:
                best_idx = idx
                best_order = last_activated
        return best_idx

    @staticmethod
    def _normalize_target_index_after_close(
        closing_index: int,
        target_old_index: int | None,
    ) -> int | None:
        """Translate a pre-close target index into the post-close index space."""
        if target_old_index is None:
            return None
        return target_old_index if target_old_index < closing_index else target_old_index - 1

    def _safe_limit_candidate_indices(self) -> list[int]:
        """Return the indices that are eligible for safe auto-close policies."""
        active = self._tab_bar.currentIndex()
        eligible: list[int] = []
        for idx, ctx in self._tabs.items():
            if idx == active:
                continue
            if ctx.tab_type != "request":
                continue
            if ctx.request_id is None:
                continue
            if ctx.is_sending or ctx.is_dirty:
                continue
            eligible.append(idx)
        # Deferred tabs are always safe (not dirty, not sending)
        for idx in self._deferred_tabs:
            if idx != active:
                eligible.append(idx)
        return eligible

    def _find_tab_limit_candidate(self) -> int | None:
        """Choose a safe tab to close when the configured limit is exceeded."""
        candidates = self._safe_limit_candidate_indices()
        if not candidates:
            return None

        policy = self._tab_settings_manager.tab_limit_policy
        if policy == "close_unchanged":
            return min(candidates)
        return min(
            candidates,
            key=lambda idx: self._tabs[idx].last_activated_order if idx in self._tabs else 0,
        )

    def _enforce_tab_limit_before_open(self) -> bool:
        """Close one safe tab when needed so a new tab can be opened."""
        if self._tab_bar.count() < self._tab_settings_manager.tab_limit:
            return True

        candidate = self._find_tab_limit_candidate()
        if candidate is not None:
            self._on_tab_close(candidate)
            return True

        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(
            self,  # type: ignore[arg-type]
            "Tab limit reached",
            "All open tabs are protected. Close a tab manually before opening another request.",
        )
        return False

    def _on_tab_reordered(self, from_index: int, to_index: int) -> None:
        """Keep logical tab state aligned with the visual tab order after drag-reorder."""
        if from_index == to_index:
            return
        # Build a unified ordered list of (index, state) where state is
        # either a TabContext or a deferred info dict.
        all_indices = sorted(set(self._tabs) | set(self._deferred_tabs))
        entries: list[TabContext | dict] = [
            self._tabs.get(idx) or self._deferred_tabs[idx] for idx in all_indices
        ]
        moved = entries.pop(from_index)
        entries.insert(to_index, moved)
        new_tabs: dict[int, TabContext] = {}
        new_deferred: dict[int, dict] = {}
        for order, item in enumerate(entries):
            if isinstance(item, TabContext):
                item.opened_order = order + 1
                new_tabs[order] = item
            else:
                new_deferred[order] = item
        self._tabs = new_tabs
        self._deferred_tabs = new_deferred
        self._persist_open_tabs()

    # ------------------------------------------------------------------
    # Folder tab management
    # ------------------------------------------------------------------
    def _open_folder(
        self,
        collection_id: int,
        *,
        focus_scripts_kind: str | None = None,
        focus_runner_panel: bool = False,
        show_missing_warning: bool = True,
    ) -> None:
        """Open a folder detail view in a tab.

        If an existing tab for this folder is already open, switch to it.
        Otherwise create a new folder tab.

        When *focus_scripts_kind* is ``'pre_request'`` or ``'test'``, the folder
        editor shows the Scripts tab with that script sub-tab selected.

        When *focus_runner_panel* is ``True``, the Runs tab shows **New run**
        (mutually exclusive with *focus_scripts_kind* in typical use).
        """
        collection = CollectionService.get_collection(collection_id)
        if collection is None:
            logger.warning("Collection id=%s not found", collection_id)
            if show_missing_warning:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(
                    self,  # type: ignore[arg-type]
                    "Collection not found",
                    f"The collection (id {collection_id}) could not be loaded. "
                    "It may have been removed or the data may be out of date.",
                )
            return

        data: dict = {
            "name": collection.name,
            "description": collection.description,
            "auth": collection.auth,
            "events": collection.events,
            "variables": collection.variables,
        }

        request_count = CollectionService.get_folder_request_count(collection_id)
        recent_requests = CollectionService.get_recent_requests(collection_id)

        # Format timestamps for display
        created_at = (
            collection.created_at.strftime("%Y-%m-%d %H:%M") if collection.created_at else None
        )
        updated_at = (
            collection.updated_at.strftime("%Y-%m-%d %H:%M") if collection.updated_at else None
        )

        # 1. Check if already open in a tab
        for idx, ctx in self._tabs.items():
            if ctx.tab_type == "folder" and ctx.collection_id == collection_id:
                self._tab_bar.setCurrentIndex(idx)
                self._flush_tab_change()
                if ctx.folder_editor is not None:
                    if focus_runner_panel:
                        ctx.folder_editor.focus_runner_panel()
                    elif focus_scripts_kind:
                        ctx.folder_editor.focus_scripts_panel(focus_scripts_kind)
                return

        # 2. Open a new folder tab
        crumbs = CollectionService.get_collection_breadcrumb(collection_id)
        folder_path = " / ".join(
            str(crumb.get("name", "")) for crumb in crumbs if crumb.get("name")
        )
        self._create_folder_tab(
            collection_id,
            data,
            request_count,
            path=folder_path,
            created_at=created_at,
            updated_at=updated_at,
            recent_requests=recent_requests,
            focus_scripts_kind=focus_scripts_kind,
            focus_runner_panel=focus_runner_panel,
        )

    def _create_folder_tab(
        self,
        collection_id: int,
        data: dict,
        request_count: int,
        *,
        path: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
        recent_requests: list[dict] | None = None,
        focus_scripts_kind: str | None = None,
        focus_runner_panel: bool = False,
    ) -> int:
        """Create a new folder tab and switch to it."""
        if not self._enforce_tab_limit_before_open():
            return self._tab_bar.currentIndex()

        from ui.request.folder_editor import FolderEditorWidget

        folder_editor = FolderEditorWidget()

        self._editor_stack.addWidget(folder_editor)

        ctx = TabContext(
            tab_type="folder",
            collection_id=collection_id,
            folder_editor=folder_editor,
            opened_order=self._next_tab_open_order(),
        )

        insert_index = self._next_tab_insert_index()
        self._shift_tabs_for_insert(insert_index)

        # Block signals while adding the tab to avoid premature
        # _on_tab_changed before ctx is stored.
        self._tab_bar.blockSignals(True)
        try:
            idx = self._tab_bar.add_folder_tab(
                data.get("name", ""),
                path=path,
                index=insert_index,
            )
        finally:
            self._tab_bar.blockSignals(False)

        self._tabs[idx] = ctx
        folder_editor.collection_changed.connect(self._on_folder_auto_save)
        folder_editor.debug_step_requested.connect(self._on_debug_step)

        # Switch to the new tab BEFORE loading data so that the folder
        # editor is visible even if load_collection raises.
        self._tab_bar.setCurrentIndex(idx)
        self._on_tab_changed(idx)
        # Flush the debounced heavy work immediately for programmatic opens
        self._flush_tab_change()

        folder_editor.load_collection(
            data,
            collection_id=collection_id,
            request_count=request_count,
            created_at=created_at,
            updated_at=updated_at,
            recent_requests=recent_requests,
        )

        # Load run history for the Runs tab
        from services.run_history_service import RunHistoryService

        runs = RunHistoryService.get_runs(collection_id)
        folder_editor.load_runs(runs)

        if focus_runner_panel:
            folder_editor.focus_runner_panel()
        elif focus_scripts_kind:
            folder_editor.focus_scripts_panel(focus_scripts_kind)

        self._persist_open_tabs()
        return idx

    # ------------------------------------------------------------------
    # Environments tab
    # ------------------------------------------------------------------
    def _find_environments_tab_index(self) -> int | None:
        """Return the tab-bar index of an open **Environments** tab, if any."""
        for idx, tab_ctx in self._tabs.items():
            if tab_ctx.tab_type == "environments":
                return idx
        return None

    def _materialize_environments_tab_at(self, insert_index: int) -> int:
        """Insert a new environments editor tab at *insert_index* and return its index.

        Caller must enforce the tab limit and ensure no environments tab exists yet.
        """
        from ui.environments.environment_editor import EnvironmentEditorWidget

        env_widget = EnvironmentEditorWidget()
        self._editor_stack.addWidget(env_widget)

        tab_ctx = TabContext(
            tab_type="environments",
            environment_editor=env_widget,
            opened_order=self._next_tab_open_order(),
        )

        self._shift_tabs_for_insert(insert_index)

        self._tab_bar.blockSignals(True)
        try:
            idx = self._tab_bar.add_environments_tab(name="Environments", index=insert_index)
        finally:
            self._tab_bar.blockSignals(False)

        self._tabs[idx] = tab_ctx
        env_widget.environments_changed.connect(self._env_selector.refresh)
        env_widget.environments_changed.connect(self._on_environments_data_changed)
        return idx

    def _open_environments_tab(self) -> None:
        """Open or focus the global environments editor tab."""
        existing = self._find_environments_tab_index()
        if existing is not None:
            self._tab_bar.setCurrentIndex(existing)
            self._flush_tab_change()
            return

        if not self._enforce_tab_limit_before_open():
            return

        idx = self._materialize_environments_tab_at(self._next_tab_insert_index())

        self._tab_bar.setCurrentIndex(idx)
        self._on_tab_changed(idx)
        self._flush_tab_change()
        self._persist_open_tabs()

    def _on_folder_auto_save(self, data: dict) -> None:
        """Auto-save folder changes triggered by the debounced signal."""
        ctx = self._current_tab_context()
        if ctx is None or ctx.tab_type != "folder" or ctx.collection_id is None:
            return
        try:
            CollectionService.update_collection(ctx.collection_id, **data)
            logger.info("Auto-saved collection id=%s", ctx.collection_id)
        except Exception:
            logger.exception("Failed to auto-save collection id=%s", ctx.collection_id)

    # ------------------------------------------------------------------
    # Breadcrumb navigation & rename
    # ------------------------------------------------------------------
    def _on_breadcrumb_clicked(self, item_type: str, item_id: int) -> None:
        """Navigate to a parent breadcrumb segment and scroll in the tree."""
        if item_type == "local_scripts_root":
            self._left_sidebar.open_panel("local_scripts")
            return

        idx = self._tab_bar.currentIndex()
        ctx = self._tabs.get(idx)
        on_local_script_tab = ctx is not None and ctx.tab_type == "local_script"

        if item_type == "folder" and on_local_script_tab:
            self._left_sidebar.open_panel("local_scripts")
            self.local_scripts_widget.select_and_scroll_to(item_id, "folder")
            return

        if item_type == "folder":
            self._open_folder(item_id)
            self.collection_widget.select_and_scroll_to(item_id, "folder")

    def _on_breadcrumb_rename(self, new_name: str) -> None:
        """Rename the current request/folder from the breadcrumb bar."""
        idx = self._tab_bar.currentIndex()
        ctx = self._tabs.get(idx)

        # Draft tab — no DB entry yet, update tab name and context only
        if ctx is not None and ctx.request_id is None and ctx.draft_name is not None:
            ctx.draft_name = new_name
            self._tab_bar.update_tab(idx, name=new_name, path=new_name)
            return

        seg = self._breadcrumb_bar.last_segment_info
        if seg is None:
            return
        item_type = seg["type"]
        item_id = seg["id"]
        try:
            if item_type == "request":
                CollectionService.rename_request(item_id, new_name)
            else:
                CollectionService.rename_collection(item_id, new_name)
        except Exception:
            logger.exception("Failed to rename %s id=%s", item_type, item_id)
            return
        # 1. Update the tab bar label
        self._sync_name_across_tabs(item_type, item_id, new_name)
        # 2. Update the collection tree sidebar
        if item_type == "script":
            self.local_scripts_widget.update_item_name(item_id, item_type, new_name)
        else:
            self.collection_widget.update_item_name(item_id, item_type, new_name)

    def _on_item_name_changed(self, item_type: str, item_id: int, new_name: str) -> None:
        """Sync open tab names when the tree emits a rename."""
        self._sync_name_across_tabs(item_type, item_id, new_name)

    def _on_local_script_tree_rename(
        self,
        script_id: int,
        basename: str,
        language: str,
        module_format: str,
    ) -> None:
        """Sync tab label, icon, and breadcrumb after an inline tree rename."""
        display = script_display_name(basename, language, module_format)
        for idx, ctx in self._tabs.items():
            if ctx.tab_type != "local_script" or ctx.local_script_id != script_id:
                continue
            self._tab_bar.update_tab(
                idx, method=language, name=basename, path=display, module_format=module_format
            )
            if ctx.local_script_editor is not None:
                ctx.local_script_editor._pane.editor.refresh_script_module_format(module_format)
            if idx == self._tab_bar.currentIndex():
                self._breadcrumb_bar.update_last_segment_text(display)

    def _sync_name_across_tabs(self, item_type: str, item_id: int, new_name: str) -> None:
        """Update the tab label and breadcrumb for any open tab matching the item."""
        for idx, ctx in self._tabs.items():
            if (
                item_type == "script"
                and ctx.tab_type == "local_script"
                and ctx.local_script_id == item_id
            ):
                lang = self._local_script_tab_language(ctx)
                display = script_display_name(new_name, lang)
                self._tab_bar.update_tab(idx, name=new_name, path=display)
                if idx == self._tab_bar.currentIndex():
                    self._breadcrumb_bar.update_last_segment_text(display)
            elif item_type == "request" and ctx.request_id == item_id:
                self._tab_bar.update_tab(
                    idx,
                    name=new_name,
                    path=self._request_full_path(item_id),
                )
                # Refresh breadcrumb if this is the active tab
                if idx == self._tab_bar.currentIndex():
                    self._breadcrumb_bar.update_last_segment_text(new_name)
            elif (
                item_type == "folder" and ctx.tab_type == "folder" and ctx.collection_id == item_id
            ):
                crumbs = CollectionService.get_collection_breadcrumb(item_id)
                folder_path = " / ".join(
                    str(crumb.get("name", "")) for crumb in crumbs if crumb.get("name")
                )
                self._tab_bar.update_tab(idx, name=new_name, path=folder_path)
                if idx == self._tab_bar.currentIndex():
                    self._breadcrumb_bar.update_last_segment_text(new_name)
        # Also update deferred tab chips (label only, no editor to refresh).
        if item_type == "request":
            for idx, info in self._deferred_tabs.items():
                if info["request_id"] == item_id:
                    info["name"] = new_name
                    self._tab_bar.update_tab(idx, name=new_name)

    # ------------------------------------------------------------------
    # Navigation history
    # ------------------------------------------------------------------
    def _navigate_back(self) -> None:
        """Go back to the previously viewed request."""
        if self._history_index > 0:
            self._history_index -= 1
            self._open_request(self._history[self._history_index], push_history=False)
            self._update_nav_actions()

    def _navigate_forward(self) -> None:
        """Go forward to the next request in the history."""
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._open_request(self._history[self._history_index], push_history=False)
            self._update_nav_actions()

    def _update_nav_actions(self) -> None:
        """Enable/disable back/forward actions based on history position."""
        self.back_action.setEnabled(self._history_index > 0)
        self.forward_action.setEnabled(self._history_index < len(self._history) - 1)

    # ------------------------------------------------------------------
    # Tab context-menu handlers
    # ------------------------------------------------------------------
    def _close_others_tabs(self, keep_index: int) -> None:
        """Close every tab except the one at *keep_index*."""
        indices = sorted(set(self._tabs) | set(self._deferred_tabs), reverse=True)
        for idx in indices:
            if idx != keep_index:
                self._on_tab_close(idx)

    def _close_all_tabs(self) -> None:
        """Close all open tabs."""
        indices = sorted(set(self._tabs) | set(self._deferred_tabs), reverse=True)
        for idx in indices:
            self._on_tab_close(idx)

    def _on_save_local_script(self) -> None:
        """Persist the active local-script editor buffer."""
        ctx = self._current_tab_context()
        if ctx is None or ctx.tab_type != "local_script" or ctx.local_script_editor is None:
            return
        if not ctx.local_script_editor.is_dirty():
            return
        if ctx.local_script_editor.save():
            idx = self._tab_bar.currentIndex()
            self._tab_bar.update_tab(idx, is_dirty=False)
            if ctx.local_script_id is not None:
                _, lang = ctx.local_script_editor._pane.get_content()
                mod_fmt = ctx.local_script_editor._pane.editor.script_module_format
                self.local_scripts_widget.update_script_metadata(
                    ctx.local_script_id,
                    language=lang,
                    module_format=mod_fmt,
                )

    def _bind_local_script_autosave(self, editor: LocalScriptEditorWidget, script_id: int) -> None:
        """Wire auto-save to refresh tree language icon when the buffer language changes."""

        def _persist() -> None:
            editor._persist_for_autosave()
            _, lang = editor._pane.get_content()
            mod_fmt = editor._pane.editor.script_module_format
            self.local_scripts_widget.update_script_metadata(
                script_id,
                language=lang,
                module_format=mod_fmt,
            )

        editor._pane.persist_content_callback = _persist

    def _local_script_tab_language(self, ctx: TabContext) -> str:
        """Return the current language code for an open local-script tab."""
        if ctx.local_script_editor is not None:
            _, lang = ctx.local_script_editor._pane.get_content()
            return lang or "javascript"
        return "javascript"

    def _local_script_breadcrumbs_with_display(self, script_id: int) -> list[dict[str, Any]]:
        """Breadcrumb segments with a file-style name on the script leaf."""
        crumbs = LocalScriptService.get_script_breadcrumb(script_id)
        data = LocalScriptService.get_script_load_dict(script_id)
        lang = (data or {}).get("language", "javascript") or "javascript"
        mod_fmt = (data or {}).get("module_format", "esm") or "esm"
        out: list[dict[str, Any]] = []
        for seg in crumbs:
            entry = dict(seg)
            if entry.get("type") == "script":
                entry["name"] = script_display_name(str(entry.get("name", "")), lang, mod_fmt)
            out.append(entry)
        return out
