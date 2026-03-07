"""Top-level application window -- menu bar, toolbar, and three-pane layout."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSize, Qt, QThread
from PySide6.QtGui import QAction, QCloseEvent, QCursor, QGuiApplication, QKeySequence

if TYPE_CHECKING:
    from ui.request.http_worker import HttpSendWorker

from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from services.collection_service import CollectionService
from ui.collections.collection_widget import CollectionWidget
from ui.environments.environment_selector import EnvironmentSelector
from ui.loading_screen import LoadingScreen
from ui.main_window.send_pipeline import _SendPipelineMixin
from ui.main_window.tab_controller import _TabControllerMixin
from ui.main_window.variable_controller import _VariableControllerMixin
from ui.panels.console_panel import ConsolePanel
from ui.panels.history_panel import HistoryPanel
from ui.request.navigation.breadcrumb_bar import BreadcrumbBar
from ui.request.navigation.request_tab_bar import RequestTabBar
from ui.request.navigation.tab_manager import TabContext
from ui.request.request_editor import RequestEditorWidget
from ui.request.response_viewer import ResponseViewerWidget
from ui.styling.icons import phi
from ui.styling.theme_manager import ThemeManager

logger = logging.getLogger(__name__)


class MainWindow(
    _SendPipelineMixin,
    _VariableControllerMixin,
    _TabControllerMixin,
    QMainWindow,
):
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

        # Per-tab state: tab-bar index -> TabContext
        self._tabs: dict[int, TabContext] = {}

        # Legacy single-send state (used when no tab is found)
        self._send_thread: QThread | None = None
        self._send_worker: HttpSendWorker | None = None

        self.collection_widget = CollectionWidget(self)

        self._setup_ui()

        # Wire sidebar -> editor
        self.collection_widget.item_action_triggered.connect(self._on_item_action)

        # Wire save -> save pipeline
        self.request_widget.save_requested.connect(self._on_save_request)
        self.request_widget.dirty_changed.connect(self._sync_save_btn)

        # Wire tab context menu signals
        self._tab_bar.close_others_requested.connect(self._close_others_tabs)
        self._tab_bar.close_all_requested.connect(self._close_all_tabs)
        self._tab_bar.force_close_all_requested.connect(self._close_all_tabs)

        # Wire collection runner
        self.run_action.triggered.connect(self._on_run_collection)

        # Wire environment editor
        self._env_selector.manage_requested.connect(self._on_manage_environments)

        # Refresh variable highlighting when the environment changes
        self._env_selector.environment_changed.connect(self._on_environment_changed)

        # Register variable popup callbacks
        from ui.widgets.variable_popup import VariablePopup

        VariablePopup.set_save_callback(self._on_variable_updated)
        VariablePopup.set_local_override_callback(self._on_local_variable_override)
        VariablePopup.set_reset_local_override_callback(self._on_reset_local_override)
        VariablePopup.set_add_variable_callback(self._on_add_unresolved_variable)
        VariablePopup.set_has_environment(self._env_selector.current_environment_id() is not None)

        # Wire loading screen
        self.collection_widget.load_finished.connect(self._on_load_finished)

        # Wire breadcrumb navigation & rename
        self._breadcrumb_bar.item_clicked.connect(self._on_breadcrumb_clicked)
        self._breadcrumb_bar.last_segment_renamed.connect(self._on_breadcrumb_rename)

        # Wire tree rename -> update open tabs
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
            screen_geom = screen.availableGeometry()  # skip taskbars, docks
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
        run_act.setShortcut(QKeySequence("Ctrl+Shift+R"))
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

        breadcrumb_row = QHBoxLayout()
        breadcrumb_row.setContentsMargins(0, 0, 0, 0)
        breadcrumb_row.setSpacing(8)

        self._breadcrumb_bar = BreadcrumbBar()
        breadcrumb_row.addWidget(self._breadcrumb_bar, 1)

        self._save_btn = QPushButton("Save")
        self._save_btn.setIcon(phi("floppy-disk"))
        self._save_btn.setObjectName("saveButton")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setFixedWidth(80)
        self._save_btn.setEnabled(False)
        self._save_btn.setToolTip("No changes to save")
        self._save_btn.setVisible(False)
        self._save_btn.clicked.connect(self._on_save_request)
        breadcrumb_row.addWidget(self._save_btn)

        # Right margin so Save aligns roughly with the Send button below
        breadcrumb_row.setContentsMargins(0, 0, 12, 0)

        layout.addLayout(breadcrumb_row)

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
    # Sidebar -> editor wiring
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

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------
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
        body = editor.get_request_data().get("body") or None
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
    # Current tab helper
    # ------------------------------------------------------------------
    def _current_tab_context(self) -> TabContext | None:
        """Return the TabContext for the active tab, or ``None``."""
        return self._tabs.get(self._tab_bar.currentIndex())

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

        # Folder tabs use auto-save -- trigger immediately on Ctrl+S
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
            # Update sidebar item in-place (name + method)
            name = data.get("url") or data.get("name", "")
            method = data.get("method", "")
            if name:
                self.collection_widget.update_item_name(request_id, "request", name)
            if method:
                self.collection_widget.update_request_method(request_id, method)
            logger.info("Saved request id=%s", request_id)
        except Exception:
            logger.exception("Failed to save request id=%s", request_id)

    # ------------------------------------------------------------------
    # Save-button state helper
    # ------------------------------------------------------------------
    def _sync_save_btn(self, dirty: bool) -> None:
        """Update the Save button enabled state and tooltip."""
        self._save_btn.setEnabled(dirty)
        self._save_btn.setToolTip("" if dirty else "No changes to save")

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
