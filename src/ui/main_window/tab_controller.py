"""Tab lifecycle and navigation mixin for the main window.

Provides ``_TabControllerMixin`` with tab CRUD, folder tabs, breadcrumb
handling, and navigation history.  Mixed into ``MainWindow``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

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
    back_action: QAction
    forward_action: QAction
    _tab_settings_manager: TabSettingsManager
    _tab_open_counter: int
    _tab_activation_counter: int

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
    def _refresh_sidebar(self, ctx: TabContext | None = None) -> None: ...
    def _schedule_sidebar_snippet_refresh(self) -> None: ...

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
            self._replace_tab(
                current_idx,
                request_id,
                data,
                is_preview=is_preview,
                path=request_path,
            )
        else:
            # 3. Open a new tab
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
        editor.save_requested.connect(self._on_save_request)
        editor.dirty_changed.connect(self._sync_save_btn)
        editor.dirty_changed.connect(self._on_editor_dirty_changed)
        editor.request_changed.connect(lambda _: self._schedule_sidebar_snippet_refresh())
        viewer.save_response_requested.connect(self._on_save_response)
        viewer.save_availability_changed.connect(lambda _enabled: self._refresh_sidebar())

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
        path: str | None = None,
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
            path=path,
            is_preview=is_preview,
            is_dirty=False,
        )

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

    def _on_editor_dirty_changed(self, dirty: bool) -> None:
        """Sync dirty state from the emitting editor back into the tab metadata."""
        sender_fn = cast(Any, getattr(self, "sender", None))
        sender = sender_fn() if callable(sender_fn) else None
        if sender is None:
            return
        for idx, ctx in self._tabs.items():
            if ctx.tab_type == "request" and ctx.editor is sender:
                ctx.is_dirty = dirty
                self._tab_bar.update_tab(idx, is_dirty=dirty)
                break

    def _on_tab_changed(self, index: int) -> None:
        """Switch the stacked widgets when the active tab changes."""
        ctx = self._tabs.get(index)
        if ctx is not None:
            self._tab_activation_counter += 1
            ctx.last_activated_order = self._tab_activation_counter

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

        # Refresh right sidebar for the active tab using the same context
        # that drove the stacked-widget switch.
        self._refresh_sidebar(ctx)

        # Sync collection tree selection to the active tab.
        self._sync_tree_selection(ctx)

    def _sync_tree_selection(self, ctx: TabContext | None) -> None:
        """Highlight the active tab's item in the collection tree."""
        if ctx is None:
            return
        if ctx.tab_type == "folder" and ctx.collection_id is not None:
            self.collection_widget.select_and_scroll_to(ctx.collection_id, "folder")
        elif ctx.request_id is not None:
            self.collection_widget.select_and_scroll_to(ctx.request_id, "request")

    # ------------------------------------------------------------------
    # Tab close
    # ------------------------------------------------------------------
    def _on_tab_close(self, index: int) -> None:
        """Close a tab and clean up its context."""
        target_old_index = self._target_tab_after_close(index)
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

        # Re-index remaining tabs
        new_tabs: dict[int, TabContext] = {}
        for old_idx, old_ctx in self._tabs.items():
            new_idx = old_idx if old_idx < index else old_idx - 1
            new_tabs[new_idx] = old_ctx
        self._tabs = new_tabs

        target_new_index = self._normalize_target_index_after_close(index, target_old_index)
        if target_new_index is not None and 0 <= target_new_index < self._tab_bar.count():
            self._tab_bar.setCurrentIndex(target_new_index)
            self._on_tab_changed(target_new_index)
        else:
            self._on_tab_changed(self._tab_bar.currentIndex())

    def _on_tab_double_click(self, index: int) -> None:
        """Promote a preview tab to a permanent tab."""
        ctx = self._tabs.get(index)
        if ctx is not None and ctx.is_preview:
            ctx.is_preview = False
            self._tab_bar.update_tab(index, is_preview=False)

    def _target_tab_after_close(self, closing_index: int) -> int | None:
        """Return the preferred old-index tab to activate after closing one."""
        if not self._tabs:
            return None

        current = self._tab_bar.currentIndex()
        if current != closing_index:
            return current

        remaining = [idx for idx in self._tabs if idx != closing_index]
        if not remaining:
            return None

        policy = self._tab_settings_manager.activate_on_close
        if policy == "left":
            left = [idx for idx in remaining if idx < closing_index]
            return max(left) if left else min(remaining)
        if policy == "right":
            right = [idx for idx in remaining if idx > closing_index]
            return min(right) if right else max(remaining)

        best_idx: int | None = None
        best_order = -1
        for idx in remaining:
            last_activated = self._tabs[idx].last_activated_order
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
        return eligible

    def _find_tab_limit_candidate(self) -> int | None:
        """Choose a safe tab to close when the configured limit is exceeded."""
        candidates = self._safe_limit_candidate_indices()
        if not candidates:
            return None

        policy = self._tab_settings_manager.tab_limit_policy
        if policy == "close_unchanged":
            return min(candidates)
        return min(candidates, key=lambda idx: self._tabs[idx].last_activated_order)

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
        ordered_indices = sorted(self._tabs)
        ordered_contexts = [self._tabs[idx] for idx in ordered_indices]
        moved = ordered_contexts.pop(from_index)
        ordered_contexts.insert(to_index, moved)
        for order, ctx in enumerate(ordered_contexts, start=1):
            ctx.opened_order = order
        self._tabs = {idx: ctx for idx, ctx in enumerate(ordered_contexts)}

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
        self.collection_widget.update_item_name(item_id, item_type, new_name)

    def _on_item_name_changed(self, item_type: str, item_id: int, new_name: str) -> None:
        """Sync open tab names when the tree emits a rename."""
        self._sync_name_across_tabs(item_type, item_id, new_name)

    def _sync_name_across_tabs(self, item_type: str, item_id: int, new_name: str) -> None:
        """Update the tab label and breadcrumb for any open tab matching the item."""
        for idx, ctx in self._tabs.items():
            if item_type == "request" and ctx.request_id == item_id:
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
