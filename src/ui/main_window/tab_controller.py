"""Tab lifecycle and navigation mixin for the main window.

Provides ``_TabControllerMixin`` with tab CRUD, folder tabs, breadcrumb
handling, and navigation history.  Mixed into ``MainWindow``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from services.collection_service import CollectionService, RequestLoadDict
from ui.request.navigation.tab_manager import TabContext
from ui.request.request_editor import RequestEditorWidget
from ui.request.response_viewer import ResponseViewerWidget

if TYPE_CHECKING:
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QPushButton, QStackedWidget, QWidget

    from ui.collections.collection_widget import CollectionWidget
    from ui.request.navigation.breadcrumb_bar import BreadcrumbBar
    from ui.request.navigation.request_tab_bar import RequestTabBar

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
    back_action: QAction
    forward_action: QAction

    def _on_send_request(self) -> None: ...
    def _on_save_request(self) -> None: ...
    def _on_save_response(self, data: dict) -> None: ...
    def _sync_save_btn(self, dirty: bool) -> None: ...
    def _current_tab_context(self) -> TabContext | None: ...
    def _refresh_variable_map(
        self,
        editor: RequestEditorWidget,
        request_id: int | None,
        local_overrides: dict | None = ...,
    ) -> None: ...

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
        request = CollectionService.get_request(request_id)
        if request is None:
            logger.warning("Request id=%s not found", request_id)
            return

        data: RequestLoadDict = {
            "name": request.name,
            "method": request.method,
            "url": request.url,
            "body": request.body,
            "request_parameters": request.request_parameters,
            "headers": request.headers,
            "description": request.description,
            "scripts": request.scripts,
            "body_mode": request.body_mode,
            "body_options": request.body_options,
            "auth": request.auth,
        }

        # 1. Check if already open in a tab
        for idx, ctx in self._tabs.items():
            if ctx.request_id == request_id:
                self._tab_bar.setCurrentIndex(idx)
                # Promote preview -> permanent on explicit Open
                if not is_preview and ctx.is_preview:
                    ctx.is_preview = False
                    self._tab_bar.update_tab(idx, is_preview=False)
                return

        # 2. Replace current preview tab if one exists
        current_idx = self._tab_bar.currentIndex()
        current_ctx = self._tabs.get(current_idx)
        if current_ctx is not None and current_ctx.is_preview:
            self._replace_tab(current_idx, request_id, data, is_preview=is_preview)
        else:
            # 3. Open a new tab
            self._create_tab(request_id, data, is_preview=is_preview)

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
    ) -> int:
        """Create a new tab for a request and switch to it."""
        editor = RequestEditorWidget()
        viewer = ResponseViewerWidget()

        self._editor_stack.addWidget(editor)
        self._response_stack.addWidget(viewer)

        ctx = TabContext(
            request_id=request_id,
            editor=editor,
            response_viewer=viewer,
            is_preview=is_preview,
        )

        # Block signals while adding the tab to avoid premature
        # _on_tab_changed before ctx is stored.
        self._tab_bar.blockSignals(True)
        try:
            idx = self._tab_bar.add_request_tab(
                data.get("method", "GET"),
                data.get("name", ""),
                is_preview=is_preview,
            )
        finally:
            self._tab_bar.blockSignals(False)

        self._tabs[idx] = ctx

        editor.load_request(data, request_id=request_id)
        editor.send_requested.connect(self._on_send_request)
        editor.save_requested.connect(self._on_save_request)
        editor.dirty_changed.connect(self._sync_save_btn)
        viewer.save_response_requested.connect(self._on_save_response)

        # Now switch to the tab (triggers _on_tab_changed safely)
        self._tab_bar.setCurrentIndex(idx)
        # Ensure stacks are synced even if setCurrentIndex didn't emit
        self._on_tab_changed(idx)
        return idx

    def _replace_tab(
        self,
        index: int,
        request_id: int,
        data: RequestLoadDict,
        *,
        is_preview: bool = False,
    ) -> None:
        """Replace the content of an existing tab with a new request."""
        ctx = self._tabs.get(index)
        if ctx is None:
            return

        ctx.cancel_send()
        ctx.request_id = request_id
        ctx.is_preview = is_preview
        ctx.editor.load_request(data, request_id=request_id)
        ctx.response_viewer.clear()

        # Refresh variable map for the replaced tab
        self._refresh_variable_map(ctx.editor, request_id, ctx.local_overrides)

        self._tab_bar.update_tab(
            index,
            method=data.get("method", "GET"),
            name=data.get("name", ""),
            is_preview=is_preview,
            is_dirty=False,
        )

    def _on_tab_changed(self, index: int) -> None:
        """Switch the stacked widgets when the active tab changes."""
        ctx = self._tabs.get(index)
        if ctx is not None and ctx.tab_type == "folder":
            # Folder tab -- show folder editor, hide response pane
            if ctx.folder_editor is not None:
                self._editor_stack.setCurrentWidget(ctx.folder_editor)
            self._response_area.hide()
            self._save_btn.setVisible(False)
            # Update breadcrumb for folder
            if ctx.collection_id is not None:
                crumbs = CollectionService.get_collection_breadcrumb(ctx.collection_id)
                self._breadcrumb_bar.set_path(crumbs)
            else:
                self._breadcrumb_bar.clear()
        elif ctx is not None:
            self._editor_stack.setCurrentWidget(ctx.editor)
            self._response_stack.setCurrentWidget(ctx.response_viewer)
            self.request_widget = ctx.editor
            self.response_widget = ctx.response_viewer
            self._response_area.show()
            self._save_btn.setVisible(True)
            self._sync_save_btn(ctx.editor.is_dirty)
            # Update breadcrumb
            if ctx.request_id is not None:
                crumbs = CollectionService.get_request_breadcrumb(ctx.request_id)
                self._breadcrumb_bar.set_path(crumbs)
            elif ctx.draft_name is not None:
                # Draft tab — show editable single-segment breadcrumb
                self._breadcrumb_bar.set_path(
                    [{"name": ctx.draft_name, "type": "request", "id": 0}]
                )
            else:
                self._breadcrumb_bar.clear()
            # Load saved responses
            if ctx.request_id is not None:
                saved = CollectionService.get_saved_responses(ctx.request_id)
                ctx.response_viewer.load_saved_responses(saved)
            # Refresh variable map for highlighting and tooltips
            self._refresh_variable_map(ctx.editor, ctx.request_id, ctx.local_overrides)
        else:
            # No active tab -- fall back to the default widgets.
            self._editor_stack.setCurrentWidget(self._default_editor)
            self._response_stack.setCurrentWidget(self._default_response_viewer)
            self.request_widget = self._default_editor
            self.response_widget = self._default_response_viewer
            self._breadcrumb_bar.clear()
            self._save_btn.setVisible(False)

    # ------------------------------------------------------------------
    # Tab close
    # ------------------------------------------------------------------
    def _on_tab_close(self, index: int) -> None:
        """Close a tab and clean up its context."""
        ctx = self._tabs.pop(index, None)
        if ctx is None:
            return

        ctx.cancel_send()
        ctx.cleanup_thread()

        if ctx.tab_type == "folder":
            # Folder tab cleanup
            folder_editor = ctx.folder_editor
            if folder_editor is not None:
                folder_editor.collection_changed.disconnect(self._on_folder_auto_save)
                self._editor_stack.removeWidget(folder_editor)
                folder_editor.setParent(None)

            ctx.dispose()
            del ctx

            self._tab_bar.remove_request_tab(index)
        else:
            # Request tab cleanup
            # Grab local references before dispose() nulls the context.
            editor = ctx.editor
            viewer = ctx.response_viewer

            # Disconnect signals that reference MainWindow slots so the
            # sender objects can be garbage-collected.
            editor.send_requested.disconnect(self._on_send_request)
            editor.save_requested.disconnect(self._on_save_request)
            editor.dirty_changed.disconnect(self._sync_save_btn)
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

        # Re-index remaining tabs
        new_tabs: dict[int, TabContext] = {}
        for old_idx, old_ctx in self._tabs.items():
            new_idx = old_idx if old_idx < index else old_idx - 1
            new_tabs[new_idx] = old_ctx
        self._tabs = new_tabs

        # Reset widget references so closed widgets can be collected.
        # _on_tab_changed may already have run (triggered by removeTab),
        # but the re-indexing above can leave stale refs.  Force a sync.
        current = self._tab_bar.currentIndex()
        self._on_tab_changed(current)

    def _on_tab_double_click(self, index: int) -> None:
        """Promote a preview tab to a permanent tab."""
        ctx = self._tabs.get(index)
        if ctx is not None and ctx.is_preview:
            ctx.is_preview = False
            self._tab_bar.update_tab(index, is_preview=False)

    # ------------------------------------------------------------------
    # Folder tab management
    # ------------------------------------------------------------------
    def _open_folder(self, collection_id: int) -> None:
        """Open a folder detail view in a tab.

        If an existing tab for this folder is already open, switch to it.
        Otherwise create a new folder tab.
        """
        collection = CollectionService.get_collection(collection_id)
        if collection is None:
            logger.warning("Collection id=%s not found", collection_id)
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
                return

        # 2. Open a new folder tab
        self._create_folder_tab(
            collection_id,
            data,
            request_count,
            created_at=created_at,
            updated_at=updated_at,
            recent_requests=recent_requests,
        )

    def _create_folder_tab(
        self,
        collection_id: int,
        data: dict,
        request_count: int,
        *,
        created_at: str | None = None,
        updated_at: str | None = None,
        recent_requests: list[dict] | None = None,
    ) -> int:
        """Create a new folder tab and switch to it."""
        from ui.request.folder_editor import FolderEditorWidget

        folder_editor = FolderEditorWidget()

        self._editor_stack.addWidget(folder_editor)

        ctx = TabContext(
            tab_type="folder",
            collection_id=collection_id,
            folder_editor=folder_editor,
        )

        # Block signals while adding the tab to avoid premature
        # _on_tab_changed before ctx is stored.
        self._tab_bar.blockSignals(True)
        try:
            idx = self._tab_bar.add_folder_tab(data.get("name", ""))
        finally:
            self._tab_bar.blockSignals(False)

        self._tabs[idx] = ctx
        folder_editor.collection_changed.connect(self._on_folder_auto_save)

        # Switch to the new tab BEFORE loading data so that the folder
        # editor is visible even if load_collection raises.
        self._tab_bar.setCurrentIndex(idx)
        self._on_tab_changed(idx)

        folder_editor.load_collection(
            data,
            collection_id=collection_id,
            request_count=request_count,
            created_at=created_at,
            updated_at=updated_at,
            recent_requests=recent_requests,
        )
        return idx

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
            self._tab_bar.update_tab(idx, name=new_name)
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
        self.collection_widget.update_item_name(item_id, item_type, new_name)

    def _on_item_name_changed(self, item_type: str, item_id: int, new_name: str) -> None:
        """Sync open tab names when the tree emits a rename."""
        self._sync_name_across_tabs(item_type, item_id, new_name)

    def _sync_name_across_tabs(self, item_type: str, item_id: int, new_name: str) -> None:
        """Update the tab label and breadcrumb for any open tab matching the item."""
        for idx, ctx in self._tabs.items():
            if item_type == "request" and ctx.request_id == item_id:
                self._tab_bar.update_tab(idx, name=new_name)
                # Refresh breadcrumb if this is the active tab
                if idx == self._tab_bar.currentIndex():
                    self._breadcrumb_bar.update_last_segment_text(new_name)
            elif (
                item_type == "folder" and ctx.tab_type == "folder" and ctx.collection_id == item_id
            ):
                self._tab_bar.update_tab(idx, name=new_name)
                if idx == self._tab_bar.currentIndex():
                    self._breadcrumb_bar.update_last_segment_text(new_name)

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
        indices = sorted(self._tabs.keys(), reverse=True)
        for idx in indices:
            if idx != keep_index:
                self._on_tab_close(idx)

    def _close_all_tabs(self) -> None:
        """Close all open tabs."""
        indices = sorted(self._tabs.keys(), reverse=True)
        for idx in indices:
            self._on_tab_close(idx)
