"""Top-level application window -- menu bar, toolbar, and three-pane layout."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSize, Qt, QThread
from PySide6.QtGui import (QAction, QCloseEvent, QCursor, QGuiApplication,
                           QKeySequence)

if TYPE_CHECKING:
    from ui.request.http_worker import HttpSendWorker

from PySide6.QtWidgets import (QHBoxLayout, QMainWindow, QSizePolicy,
                               QSplitter, QStackedWidget, QTabWidget, QToolBar,
                               QVBoxLayout, QWidget)

from services.collection_service import CollectionService
from ui.collections.collection_widget import CollectionWidget
from ui.environments.environment_selector import EnvironmentSelector
from ui.icons import phi
from ui.loading_screen import LoadingScreen
from ui.panels.console_panel import ConsolePanel
from ui.panels.history_panel import HistoryPanel
from ui.request.breadcrumb_bar import BreadcrumbBar
from ui.request.request_editor import RequestEditorWidget
from ui.request.request_tab_bar import RequestTabBar
from ui.request.response_viewer import ResponseViewerWidget
from ui.request.tab_manager import TabContext
from ui.theme_manager import ThemeManager

logger = logging.getLogger(__name__)

# Maximum number of entries in the back/forward navigation history
_MAX_HISTORY = 50


class MainWindow(QMainWindow):
    """Top-level application window.

    Sets up the menu bar, toolbar, and the three-pane layout
    (collection sidebar | request editor | response viewer).
    """

    def __init__(self, theme_manager: ThemeManager | None = None) -> None:
        """Initialise the main window, layout, and child widgets."""
        super().__init__()
        self._theme_manager = theme_manager
        self.setWindowTitle("Postmark")
        self.resize(1200, 800)

        # Placeholders for future persistence logic
        self.collections: dict[str, Any] = {}
        self.environments: dict[str, Any] = {}

        # Navigation history
        self._history: list[int] = []  # request IDs
        self._history_index: int = -1

        # Per-tab state: tab-bar index → TabContext
        self._tabs: dict[int, TabContext] = {}

        # Legacy single-send state (used when no tab is found)
        self._send_thread: QThread | None = None
        self._send_worker: HttpSendWorker | None = None

        self.collection_widget = CollectionWidget(self)

        self._setup_ui()

        # Wire sidebar → editor
        self.collection_widget.item_action_triggered.connect(self._on_item_action)

        # Wire save → save pipeline
        self.request_widget.save_requested.connect(self._on_save_request)

        # Wire tab context menu signals
        self._tab_bar.close_others_requested.connect(self._close_others_tabs)
        self._tab_bar.close_all_requested.connect(self._close_all_tabs)
        self._tab_bar.force_close_all_requested.connect(self._close_all_tabs)

        # Wire collection runner
        self.run_action.triggered.connect(self._on_run_collection)

        # Wire environment editor
        self._env_selector.manage_requested.connect(self._on_manage_environments)

        # Wire loading screen
        self.collection_widget.load_finished.connect(self._on_load_finished)

        # Wire breadcrumb navigation & rename
        self._breadcrumb_bar.item_clicked.connect(self._on_breadcrumb_clicked)
        self._breadcrumb_bar.last_segment_renamed.connect(self._on_breadcrumb_rename)

        # Wire tree rename → update open tabs
        self.collection_widget.item_name_changed.connect(self._on_item_name_changed)

        # ---- Move to the screen that contains the mouse --------------
        self._move_to_mouse_screen()

    def _move_to_mouse_screen(self) -> None:
        """Center the window on the monitor that the cursor is on."""
        # 1. Find the screen that the cursor is currently on
        cursor_pos = QCursor.pos()  # global screen coordinates
        screen = QGuiApplication.screenAt(cursor_pos)

        # 2. If we found a screen, move the window so it is centered there
        if screen is not None:
            screen_geom = screen.availableGeometry()  # skip taskbars, docks…
            win_geom = self.frameGeometry()  # includes frame
            win_geom.moveCenter(screen_geom.center())
            self.move(win_geom.topLeft())

        # 3. If screen is None (rare), just leave the window where Qt chose

    # ------------------------------------------------------------------
    # Menu creation
    # ------------------------------------------------------------------
    def _create_menus(self) -> None:
        """Build the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        import_act = QAction("&Import...", self)
        import_act.setIcon(phi("download-simple"))
        import_act.setShortcut(QKeySequence("Ctrl+I"))
        import_act.triggered.connect(self._on_import)
        file_menu.addAction(import_act)

        save_act = QAction("&Save", self)
        save_act.setIcon(phi("floppy-disk"))
        save_act.setShortcut(QKeySequence("Ctrl+S"))
        save_act.triggered.connect(self._on_save_request)
        file_menu.addAction(save_act)

        file_menu.addSeparator()

        snippet_act = QAction("Generate Code &Snippet\u2026", self)
        snippet_act.setIcon(phi("code"))
        snippet_act.setShortcut(QKeySequence("Ctrl+Shift+C"))
        snippet_act.triggered.connect(self._on_code_snippet)
        file_menu.addAction(snippet_act)

        file_menu.addSeparator()

        settings_act = QAction("&Settings\u2026", self)
        settings_act.setIcon(phi("gear"))
        settings_act.setShortcut(QKeySequence("Ctrl+,"))
        settings_act.triggered.connect(self._on_settings)
        file_menu.addAction(settings_act)

        file_menu.addSeparator()

        exit_act = QAction("&Exit", self)
        exit_act.setIcon(phi("sign-out"))
        exit_act.setShortcut(QKeySequence("Ctrl+Q"))
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # Collection menu
        coll_menu = menubar.addMenu("&Collection")
        run_act = QAction("Run &All", self)
        run_act.setIcon(phi("play"))
        run_act.setShortcut(QKeySequence("Ctrl+R"))
        self.run_action = run_act
        coll_menu.addAction(run_act)

        # View menu
        view_menu = menubar.addMenu("&View")
        self._toggle_response_action = QAction("&Toggle Response Pane", self)
        self._toggle_response_action.setShortcut(QKeySequence("Ctrl+\\"))
        self._toggle_response_action.triggered.connect(self._toggle_response_pane)
        view_menu.addAction(self._toggle_response_action)

        self._toggle_sidebar_action = QAction("Toggle &Sidebar", self)
        self._toggle_sidebar_action.setShortcut(QKeySequence("Ctrl+B"))
        self._toggle_sidebar_action.triggered.connect(self._toggle_sidebar)
        view_menu.addAction(self._toggle_sidebar_action)

        self._toggle_bottom_action = QAction("Toggle &Bottom Panel", self)
        self._toggle_bottom_action.setShortcut(QKeySequence("Ctrl+J"))
        self._toggle_bottom_action.triggered.connect(self._toggle_bottom_panel)
        view_menu.addAction(self._toggle_bottom_action)

        self._toggle_layout_action = QAction("Toggle &Layout Orientation", self)
        self._toggle_layout_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        self._toggle_layout_action.triggered.connect(self._toggle_layout_orientation)
        view_menu.addAction(self._toggle_layout_action)

    # ------------------------------------------------------------------
    # Request/response area helpers
    # ------------------------------------------------------------------
    def _build_request_area(self) -> QWidget:
        """Create the request editor pane with the tab bar above it.

        Returns a wrapper widget containing the tab bar, a stacked widget
        for editors, and the default (single) editor.
        """
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tab_bar = RequestTabBar()
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        self._tab_bar.tab_close_requested.connect(self._on_tab_close)
        self._tab_bar.tab_double_clicked.connect(self._on_tab_double_click)
        layout.addWidget(self._tab_bar)

        self._breadcrumb_bar = BreadcrumbBar()
        layout.addWidget(self._breadcrumb_bar)

        self._editor_stack = QStackedWidget()
        layout.addWidget(self._editor_stack, 1)

        # Default editor (also reachable as self.request_widget)
        self._default_editor = RequestEditorWidget()
        self.request_widget = self._default_editor
        self._editor_stack.addWidget(self._default_editor)

        # Wire send for the default editor
        self.request_widget.send_requested.connect(self._on_send_request)

        return wrapper

    def _build_response_area(self) -> QWidget:
        """Create the response viewer with a stacked widget for per-tab views.

        Returns a wrapper widget containing the response viewer stack.
        """
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._response_stack = QStackedWidget()
        layout.addWidget(self._response_stack, 1)

        # Default response viewer
        self._default_response_viewer = ResponseViewerWidget()
        self.response_widget = self._default_response_viewer
        self._response_stack.addWidget(self._default_response_viewer)

        return wrapper

    # ------------------------------------------------------------------
    # Toolbar creation
    # ------------------------------------------------------------------
    def _create_toolbar(self) -> None:
        """Build the main toolbar with navigation actions."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(32, 32))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.back_action = QAction(phi("arrow-left", size=20), "Go back", self)
        self.back_action.setShortcut(QKeySequence("Alt+Left"))
        self.back_action.setEnabled(False)
        self.back_action.triggered.connect(self._navigate_back)
        toolbar.addAction(self.back_action)

        self.forward_action = QAction(phi("arrow-right", size=20), "Go forward", self)
        self.forward_action.setShortcut(QKeySequence("Alt+Right"))
        self.forward_action.setEnabled(False)
        self.forward_action.triggered.connect(self._navigate_forward)
        toolbar.addAction(self.forward_action)

        # Spacer to push environment selector to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # Environment selector
        self._env_selector = EnvironmentSelector()
        toolbar.addWidget(self._env_selector)
        self._env_selector.refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        """Assemble the full window layout from menus, toolbar, and panes."""
        # 1. Menu & toolbar
        self._create_menus()
        self._create_toolbar()

        # Hide them initially during loading
        self.menuBar().hide()
        # We need to hide the toolbar, but we didn't save a reference to it.
        # Let's find it.
        for tb in self.findChildren(QToolBar):
            tb.hide()

        # 2. Main stack: loading screen vs main UI
        self._main_stack = QStackedWidget()
        self.setCentralWidget(self._main_stack)

        self._loading_screen = LoadingScreen()
        self._main_stack.addWidget(self._loading_screen)
        self._loading_screen.start_animation()

        # 3. Main splitter: left (nav) + right (request+response)
        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(9, 0, 0, 0)
        self._main_stack.addWidget(central)

        self._main_splitter = QSplitter(Qt.Orientation.Horizontal, central)
        self._main_splitter.setHandleWidth(6)
        main_layout.addWidget(self._main_splitter)

        # --- Left navigation pane ---
        self._main_splitter.addWidget(self.collection_widget)

        # --- Right side: vertical splitter (request + response) ---
        request_area = self._build_request_area()

        self._right_splitter = QSplitter(Qt.Orientation.Vertical)
        self._main_splitter.addWidget(self._right_splitter)
        self._main_splitter.setStretchFactor(1, 3)  # right side takes 3x the space

        # --- Request editor area ---
        self._right_splitter.addWidget(request_area)
        self._right_splitter.setCollapsible(0, False)

        # --- Response viewer area ---
        self._response_area = self._build_response_area()
        self._right_splitter.addWidget(self._response_area)

        # --- Bottom panel (History + Console) ---
        self._bottom_panel = QTabWidget()
        self._bottom_panel.setTabPosition(QTabWidget.TabPosition.South)
        self._history_panel = HistoryPanel()
        self._console_panel = ConsolePanel()
        self._bottom_panel.addTab(self._history_panel, "History")
        self._bottom_panel.addTab(self._console_panel, "Console")
        self._bottom_panel.hide()
        self._right_splitter.addWidget(self._bottom_panel)

    def _on_load_finished(self) -> None:
        """Switch from the loading screen to the main UI."""
        self._loading_screen.stop_animation()
        self._main_stack.setCurrentIndex(1)
        self.menuBar().show()
        for tb in self.findChildren(QToolBar):
            tb.show()

    # ------------------------------------------------------------------
    # Sidebar → editor wiring
    # ------------------------------------------------------------------
    def _on_item_action(self, item_type: str, item_id: int, action: str) -> None:
        """Handle actions triggered from the collection tree."""
        if item_type == "request":
            if action == "Open":
                self._open_request(item_id, push_history=True, is_preview=False)
            elif action == "Preview":
                self._open_request(item_id, push_history=True, is_preview=True)
        elif item_type == "folder" and action == "Open":
            self._open_folder(item_id)

    def _open_request(
        self,
        request_id: int,
        *,
        push_history: bool,
        is_preview: bool = False,
    ) -> None:
        """Load a request in a tab — reuse existing or create new.

        When *is_preview* is ``True`` the tab is italic and will be
        replaced by subsequent preview opens.  When ``False`` (the
        default) the tab is permanent — double-click or context-menu
        "Open" behaviour.
        """
        request = CollectionService.get_request(request_id)
        if request is None:
            logger.warning("Request id=%s not found", request_id)
            return

        data = {
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
                # Promote preview → permanent on explicit Open
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
    # Tab management
    # ------------------------------------------------------------------
    def _create_tab(
        self,
        request_id: int,
        data: dict,
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
        data: dict,
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
            # Folder tab — show folder editor, hide response pane
            if ctx.folder_editor is not None:
                self._editor_stack.setCurrentWidget(ctx.folder_editor)
            self._response_area.hide()
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
            # Update breadcrumb
            if ctx.request_id is not None:
                crumbs = CollectionService.get_request_breadcrumb(ctx.request_id)
                self._breadcrumb_bar.set_path(crumbs)
            else:
                self._breadcrumb_bar.clear()
            # Load saved responses
            if ctx.request_id is not None:
                saved = CollectionService.get_saved_responses(ctx.request_id)
                ctx.response_viewer.load_saved_responses(saved)
        else:
            # No active tab — fall back to the default widgets.
            self._editor_stack.setCurrentWidget(self._default_editor)
            self._response_stack.setCurrentWidget(self._default_response_viewer)
            self.request_widget = self._default_editor
            self.response_widget = self._default_response_viewer
            self._breadcrumb_bar.clear()

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
    # View toggles
    # ------------------------------------------------------------------
    def _toggle_response_pane(self) -> None:
        """Show or hide the response viewer pane."""
        self._response_area.setHidden(not self._response_area.isHidden())

    def _toggle_sidebar(self) -> None:
        """Show or hide the collection sidebar."""
        self.collection_widget.setHidden(not self.collection_widget.isHidden())

    def _toggle_bottom_panel(self) -> None:
        """Show or hide the bottom panel (History / Console)."""
        self._bottom_panel.setVisible(self._bottom_panel.isHidden())

    def _toggle_layout_orientation(self) -> None:
        """Switch the request/response split between vertical and horizontal."""
        if self._right_splitter.orientation() == Qt.Orientation.Vertical:
            self._right_splitter.setOrientation(Qt.Orientation.Horizontal)
        else:
            self._right_splitter.setOrientation(Qt.Orientation.Vertical)

    def _on_code_snippet(self) -> None:
        """Open the code snippet dialog for the current request."""
        from ui.dialogs.code_snippet_dialog import CodeSnippetDialog

        ctx = self._current_tab_context()
        if ctx is not None and ctx.tab_type == "folder":
            return
        editor = ctx.editor if ctx else self.request_widget
        method = editor._method_combo.currentText()
        url = editor._url_input.text().strip()
        headers = editor.get_headers_text()
        body = editor._body_edit.toPlainText() or None
        dialog = CodeSnippetDialog(
            method=method,
            url=url,
            headers=headers,
            body=body,
            parent=self,
        )
        dialog.exec()

    def _on_settings(self) -> None:
        """Open the settings dialog."""
        from ui.dialogs.settings_dialog import SettingsDialog

        if self._theme_manager is not None:
            dialog = SettingsDialog(self._theme_manager, parent=self)
            dialog.exec()

    # ------------------------------------------------------------------
    # HTTP send pipeline
    # ------------------------------------------------------------------
    def _current_tab_context(self) -> TabContext | None:
        """Return the TabContext for the active tab, or ``None``."""
        return self._tabs.get(self._tab_bar.currentIndex())

    def _on_send_request(self) -> None:
        """Send the current request on a background thread."""
        ctx = self._current_tab_context()

        # Folder tabs cannot send requests
        if ctx is not None and ctx.tab_type == "folder":
            return

        # If already sending, treat as cancel
        if ctx is not None and ctx.is_sending:
            self._cancel_send()
            return
        if self._send_thread is not None and self._send_thread.isRunning():
            self._cancel_send()
            return

        # 1. Gather request data from the current editor
        editor = ctx.editor if ctx else self.request_widget
        viewer = ctx.response_viewer if ctx else self.response_widget

        method = editor._method_combo.currentText()
        url = editor._url_input.text().strip()
        if not url:
            viewer.show_error("URL is empty")
            return

        headers = editor.get_headers_text()
        body = editor._body_edit.toPlainText() or None

        # 2. Gather auth (with inheritance) and env_id for worker thread
        auth_data = editor._get_auth_data()
        if ctx and ctx.request_id and (not auth_data or auth_data.get("type") in (None, "noauth")):
            inherited = CollectionService.get_request_auth_chain(ctx.request_id)
            if inherited:
                auth_data = inherited

        env_id = self._env_selector.current_environment_id()

        # 3. Tear down any previous send thread
        if ctx is not None:
            ctx.cleanup_thread()
        else:
            self._cleanup_send_thread()

        # 4. Show loading state, spinner, and toggle button to Cancel
        viewer.show_loading()
        self._set_send_button_cancel(True)
        if ctx is not None:
            idx = self._tab_bar.currentIndex()
            self._tab_bar.update_tab(idx, is_sending=True)

        # 5. Create worker — variable resolution + auth on worker thread
        from ui.request.http_worker import HttpSendWorker

        worker = HttpSendWorker()
        worker.set_request(
            method=method,
            url=url,
            headers=headers,
            body=body,
            env_id=env_id,
            auth_data=auth_data,
        )

        thread = QThread()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_send_finished)
        worker.error.connect(self._on_send_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)

        if ctx is not None:
            ctx.thread = thread
            ctx.worker = worker
            ctx.is_sending = True
        else:
            self._send_thread = thread
            self._send_worker = worker
        thread.start()

    def _on_send_finished(self, data: dict) -> None:
        """Handle a successful HTTP response from the worker thread."""
        ctx = self._current_tab_context()
        viewer = ctx.response_viewer if ctx else self.response_widget
        viewer.load_response(data)
        self._set_send_button_cancel(False)
        if ctx is not None:
            idx = self._tab_bar.currentIndex()
            self._tab_bar.update_tab(idx, is_sending=False)
            ctx.cleanup_thread()
        else:
            self._cleanup_send_thread()
        # Add to history panel
        editor = ctx.editor if ctx else self.request_widget
        self._history_panel.add_entry(
            editor._method_combo.currentText(),
            editor._url_input.text(),
            data.get("status_code"),
            data.get("elapsed_ms", 0),
        )

    def _on_send_error(self, message: str) -> None:
        """Handle an error from the HTTP send worker."""
        ctx = self._current_tab_context()
        viewer = ctx.response_viewer if ctx else self.response_widget
        viewer.show_error(message)
        self._set_send_button_cancel(False)
        if ctx is not None:
            idx = self._tab_bar.currentIndex()
            self._tab_bar.update_tab(idx, is_sending=False)
            ctx.cleanup_thread()
        else:
            self._cleanup_send_thread()
        # Add error entry to history panel
        editor = ctx.editor if ctx else self.request_widget
        self._history_panel.add_entry(
            editor._method_combo.currentText(),
            editor._url_input.text(),
        )

    def _cancel_send(self) -> None:
        """Cancel the in-flight HTTP request."""
        ctx = self._current_tab_context()
        if ctx is not None:
            ctx.cancel_send()
            ctx.response_viewer.show_error("Request cancelled")
        else:
            if self._send_worker is not None:
                self._send_worker.cancel()
            self.response_widget.show_error("Request cancelled")
            self._cleanup_send_thread()
        self._set_send_button_cancel(False)

    def _set_send_button_cancel(self, is_cancel: bool) -> None:
        """Toggle the Send button between Send and Cancel states."""
        ctx = self._current_tab_context()
        if ctx is not None and ctx.tab_type == "folder":
            return
        editor = ctx.editor if ctx else self.request_widget
        btn = editor._send_btn
        if is_cancel:
            btn.setText("Cancel")
            btn.setObjectName("dangerButton")
        else:
            btn.setText("Send")
            btn.setObjectName("primaryButton")
        # Force style recalculation after objectName change
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _cleanup_send_thread(self) -> None:
        """Clean up the background send thread and worker."""
        if self._send_thread is not None:
            if self._send_thread.isRunning():
                self._send_thread.quit()
                self._send_thread.wait(3000)
            self._send_thread.deleteLater()
            self._send_thread = None
        if self._send_worker is not None:
            self._send_worker.deleteLater()
            self._send_worker = None

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------
    def _on_import(self) -> None:
        """Open the import dialog."""
        from ui.dialogs.import_dialog import ImportDialog

        dialog = ImportDialog(self)
        dialog.import_completed.connect(self.collection_widget._start_fetch)
        dialog.exec()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def _on_save_request(self) -> None:
        """Save the current request editor contents to the database.

        For folder tabs, triggers an immediate auto-save instead.
        """
        ctx = self._current_tab_context()

        # Folder tabs use auto-save — trigger immediately on Ctrl+S
        if ctx is not None and ctx.tab_type == "folder":
            if ctx.folder_editor is not None and ctx.collection_id is not None:
                data = ctx.folder_editor.get_collection_data()
                self._on_folder_auto_save(data)
            return

        editor = ctx.editor if ctx else self.request_widget

        request_id = editor.request_id
        if request_id is None:
            return
        if not editor.is_dirty:
            return

        data = editor.get_request_data()
        try:
            CollectionService.update_request(request_id, **data)
            editor._set_dirty(False)
            # Update tab bar to reflect saved state
            if ctx is not None:
                idx = self._tab_bar.currentIndex()
                self._tab_bar.update_tab(idx, is_dirty=False)
            # Refresh sidebar to reflect any name/method change
            self.collection_widget._start_fetch()
            logger.info("Saved request id=%s", request_id)
        except Exception:
            logger.exception("Failed to save request id=%s", request_id)

    # ------------------------------------------------------------------
    # Close event
    # ------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:
        """Clean up all tabs and the console panel before closing."""
        for ctx in self._tabs.values():
            ctx.cancel_send()
            ctx.cleanup_thread()
        self._cleanup_send_thread()
        self._console_panel.cleanup()
        super().closeEvent(event)

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

    # ------------------------------------------------------------------
    # Collection runner
    # ------------------------------------------------------------------
    def _on_run_collection(self) -> None:
        """Open the collection runner dialog for the selected collection."""
        coll_id = self.collection_widget.selected_collection_id()
        if coll_id is None:
            logger.warning("No collection selected for runner")
            return
        from ui.dialogs.collection_runner import CollectionRunnerDialog

        dialog = CollectionRunnerDialog(coll_id, parent=self)
        dialog.exec()

    # ------------------------------------------------------------------
    # Environment editor
    # ------------------------------------------------------------------
    def _on_manage_environments(self) -> None:
        """Open the environment editor dialog."""
        from ui.environments.environment_editor import EnvironmentEditorDialog

        dialog = EnvironmentEditorDialog(parent=self)
        dialog.environments_changed.connect(self._env_selector.refresh)
        dialog.exec()

    # ------------------------------------------------------------------
    # Save response handler
    # ------------------------------------------------------------------
    def _on_save_response(self, data: dict) -> None:
        """Save the displayed response as a named example."""
        ctx = self._current_tab_context()
        if ctx is None or ctx.request_id is None:
            return
        CollectionService.save_response(
            ctx.request_id,
            name="Saved Response",
            status=data.get("status"),
            code=None,
            headers=data.get("headers"),
            body=data.get("body"),
        )
        saved = CollectionService.get_saved_responses(ctx.request_id)
        ctx.response_viewer.load_saved_responses(saved)
