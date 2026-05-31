"""Top-level application window -- menu bar, status bar, and multi-pane layout."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QCursor, QGuiApplication, QKeySequence

if TYPE_CHECKING:
    from services.scripting.debug import DebugProtocol
    from ui.request.http_worker import HttpSendWorker

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from services.collection_service import CollectionService
from ui.collections.collection_widget import CollectionWidget
from ui.environments.environment_sidebar_panel import EnvironmentSidebarPanel
from ui.loading_screen import LoadingScreen
from ui.main_window.draft_controller import _DraftControllerMixin
from ui.main_window.send_pipeline import _SendPipelineMixin
from ui.main_window.tab_controller import _TabControllerMixin
from ui.main_window.tab_nav import _TabNavHistoryMixin
from ui.main_window.variable_controller import _VariableControllerMixin
from ui.panels.console_panel import ConsolePanel
from ui.request.navigation.breadcrumb_bar import BreadcrumbBar
from ui.request.navigation.request_tab_bar import RequestTabBar
from ui.request.navigation.tab_manager import TabContext
from ui.request.request_editor import RequestEditorWidget
from ui.request.response_viewer import ResponseViewerWidget
from ui.sidebar import LeftSidebar, RightSidebar
from ui.sidebar.snippets_sidebar_panel import SnippetsSidebarPanel
from ui.styling.icons import phi
from ui.styling.tab_settings_manager import TabSettingsManager
from ui.styling.theme import COLOR_ACCENT, COLOR_TEXT_MUTED
from ui.styling.theme_manager import ThemeManager

logger = logging.getLogger(__name__)


class MainWindow(
    _SendPipelineMixin,
    _VariableControllerMixin,
    _DraftControllerMixin,
    _TabNavHistoryMixin,
    _TabControllerMixin,
    QMainWindow,
):
    """Top-level application window.

    Sets up the menu bar, status bar, and five-pane layout
    (left activity rail + collections / environments or local scripts flyout
    | request editor | response viewer | right sidebar rail + flyout).

    Navigation: request open history (Alt+Left/Right), tab activation history
    (Go menu, Ctrl+Alt+Left/Right), and cyclic tab deck (View, Ctrl+Tab).
    """

    def __init__(
        self,
        theme_manager: ThemeManager | None = None,
        tab_settings_manager: TabSettingsManager | None = None,
    ) -> None:
        """Initialise the main window, layout, and child widgets."""
        super().__init__()
        self._theme_manager = theme_manager
        app = QApplication.instance()
        self._tab_settings_manager = tab_settings_manager or TabSettingsManager(app)
        self.setWindowTitle("Postmark")

        # Pre-size to the available screen geometry so the window fills
        # the screen immediately, avoiding a brief flash of a small
        # default-sized window before the window manager maximizes it.
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.availableGeometry())

        # Placeholders for future persistence logic
        self.collections: dict[str, Any] = {}
        self.environments: dict[str, Any] = {}

        # Navigation history
        self._history: list[int] = []  # request IDs
        self._history_index: int = -1
        self._tab_open_counter: int = 0
        self._tab_activation_counter: int = 0
        self._restoring_session: bool = False

        # Per-tab state: tab-bar index -> TabContext
        self._tabs: dict[int, TabContext] = {}
        # Deferred (not-yet-materialised) request tabs restored from session
        self._deferred_tabs: dict[int, dict] = {}
        self._init_tab_activation_history()

        # Legacy single-send state (used when no tab is found)
        self._send_thread: QThread | None = None
        self._send_worker: HttpSendWorker | None = None
        self._debug_protocol: DebugProtocol | None = None
        self._debug_script_host: Any | None = None

        self.collection_widget = CollectionWidget(self)
        self.local_scripts_widget = CollectionWidget(self, variant="local_scripts")

        # Side rails (created before _setup_ui so layout can embed them)
        self._left_sidebar = LeftSidebar()
        self._right_sidebar = RightSidebar()
        if self._theme_manager is not None:
            self._theme_manager.theme_changed.connect(self._left_sidebar.refresh_theme)
            self._theme_manager.theme_changed.connect(self._right_sidebar.refresh_theme)

        # Debounce timer for live snippet updates in the sidebar
        self._sidebar_debounce = QTimer(self)
        self._sidebar_debounce.setSingleShot(True)
        self._sidebar_debounce.timeout.connect(self._refresh_sidebar_snippet)

        # Debounce timer for heavy tab-change work (breadcrumb, sidebar,
        # variable map, tree sync) so rapid scrolling stays smooth.
        self._tab_change_debounce = QTimer(self)
        self._tab_change_debounce.setSingleShot(True)
        self._tab_change_debounce.setInterval(60)
        self._tab_change_debounce.timeout.connect(self._on_tab_change_settled)

        self._setup_ui()

        # Wire sidebar -> editor
        self.collection_widget.item_action_triggered.connect(self._on_item_action)
        self.local_scripts_widget.item_action_triggered.connect(self._on_item_action)

        # Wire draft request
        self.collection_widget.draft_request_requested.connect(self._open_draft_request)

        # Wire save -> save pipeline
        self.request_widget.save_requested.connect(self._on_save_request)
        self.request_widget.dirty_changed.connect(self._sync_save_btn)

        # Wire tab context menu signals
        self._tab_bar.close_others_requested.connect(self._close_others_tabs)
        self._tab_bar.close_all_requested.connect(self._close_all_tabs)
        self._tab_bar.force_close_all_requested.connect(self._close_all_tabs)
        self._tab_bar.tab_reordered.connect(self._on_tab_reordered)

        # Wire collection runner
        self.run_action.triggered.connect(self._on_run_collection)
        self.collection_widget.run_collection_requested.connect(self._on_run_collection_by_id)

        # Wire environment editor
        self._env_selector.manage_requested.connect(self._on_manage_environments)
        self._right_sidebar.saved_responses_panel.save_current_requested.connect(
            self._on_save_current_response_requested
        )
        self._right_sidebar.saved_responses_panel.rename_requested.connect(
            self._on_rename_saved_response
        )
        self._right_sidebar.saved_responses_panel.duplicate_requested.connect(
            self._on_duplicate_saved_response
        )
        self._right_sidebar.saved_responses_panel.delete_requested.connect(
            self._on_delete_saved_response
        )

        # Refresh variable highlighting when the environment changes
        self._env_selector.environment_changed.connect(self._on_environment_changed)

        # Register variable popup callbacks
        from ui.widgets.variable_popup import VariablePopup

        VariablePopup.set_save_callback(self._on_variable_updated)
        VariablePopup.set_local_override_callback(self._on_local_variable_override)
        VariablePopup.set_reset_local_override_callback(self._on_reset_local_override)
        VariablePopup.set_add_variable_callback(self._on_add_unresolved_variable)
        VariablePopup.set_has_environment(self._env_selector.current_environment_id() is not None)

        from ui.widgets.code_editor.editor_widget import CodeEditorWidget

        CodeEditorWidget.set_open_local_script_handler(self._open_local_script)

        # Wire loading screen
        self.collection_widget.load_finished.connect(self._on_load_finished)
        self._left_sidebar.panel_state_changed.connect(self._sync_sidebar_toggle_btn)

        # Wire breadcrumb navigation & rename
        self._breadcrumb_bar.item_clicked.connect(self._on_breadcrumb_clicked)
        self._breadcrumb_bar.last_segment_renamed.connect(self._on_breadcrumb_rename)

        # Wire tree rename -> update open tabs
        self.collection_widget.item_name_changed.connect(self._on_item_name_changed)
        self.local_scripts_widget.item_name_changed.connect(self._on_item_name_changed)
        self.local_scripts_widget.script_rename_requested.connect(self._on_local_script_tree_rename)

        # Start the collection fetch *after* all signals are connected so
        # a fast-completing fetch cannot emit load_finished before we listen.
        self.collection_widget._start_fetch()
        self.local_scripts_widget._start_fetch()

        # ---- Move to the screen that contains the mouse --------------
        self._move_to_mouse_screen()

    def _move_to_mouse_screen(self) -> None:
        """Center the window on the monitor that the cursor is on."""
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos)
        if screen is not None:
            screen_geom = screen.availableGeometry()
            win_geom = self.frameGeometry()
            win_geom.moveCenter(screen_geom.center())
            self.move(win_geom.topLeft())

    # ------------------------------------------------------------------
    # Menu creation
    # ------------------------------------------------------------------
    def _create_menus(self) -> None:
        """Build the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        new_req_act = QAction("&New Request", self)
        new_req_act.setIcon(phi("plus"))
        new_req_act.setShortcut(QKeySequence("Ctrl+N"))
        new_req_act.triggered.connect(self._open_draft_request)
        file_menu.addAction(new_req_act)

        file_menu.addSeparator()

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
        snippet_act.triggered.connect(self._on_snippet_shortcut)
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

        # Go menu — tab activation history
        go_menu = menubar.addMenu("&Go")
        self.tab_back_action = QAction(phi("arrow-left", size=20), "&Back", self)
        self.tab_back_action.setToolTip("Go to previously activated tab")
        self.tab_back_action.setShortcut(QKeySequence("Ctrl+Alt+Left"))
        self.tab_back_action.setEnabled(False)
        self.tab_back_action.triggered.connect(self._navigate_tab_back)
        go_menu.addAction(self.tab_back_action)
        self.addAction(self.tab_back_action)

        self.tab_forward_action = QAction(phi("arrow-right", size=20), "&Forward", self)
        self.tab_forward_action.setToolTip("Go forward in tab activation history")
        self.tab_forward_action.setShortcut(QKeySequence("Ctrl+Alt+Right"))
        self.tab_forward_action.setEnabled(False)
        self.tab_forward_action.triggered.connect(self._navigate_tab_forward)
        go_menu.addAction(self.tab_forward_action)
        self.addAction(self.tab_forward_action)

        # View menu
        view_menu = menubar.addMenu("&View")
        self._next_tab_action = QAction("&Next Tab", self)
        self._next_tab_action.setShortcuts([QKeySequence("Ctrl+Tab"), QKeySequence("Ctrl+PgDown")])
        self._next_tab_action.triggered.connect(self._activate_next_tab)
        view_menu.addAction(self._next_tab_action)

        self._previous_tab_action = QAction("&Previous Tab", self)
        self._previous_tab_action.setShortcuts(
            [QKeySequence("Ctrl+Shift+Tab"), QKeySequence("Ctrl+PgUp")]
        )
        self._previous_tab_action.triggered.connect(self._activate_previous_tab)
        view_menu.addAction(self._previous_tab_action)

        view_menu.addSeparator()

        self._toggle_response_action = QAction("&Toggle Response Pane", self)
        self._toggle_response_action.setShortcut(QKeySequence("Ctrl+\\"))
        self._toggle_response_action.triggered.connect(self._toggle_response_pane)
        view_menu.addAction(self._toggle_response_action)

        self._toggle_sidebar_action = QAction("Toggle &Sidebar", self)
        self._toggle_sidebar_action.setShortcut(QKeySequence("Ctrl+B"))
        self._toggle_sidebar_action.triggered.connect(self._toggle_sidebar)
        view_menu.addAction(self._toggle_sidebar_action)

        self._toggle_bottom_action = QAction("Toggle &Console", self)
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
        self._request_area = wrapper
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tab_bar = RequestTabBar(self._tab_settings_manager)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        self._tab_bar.tab_close_requested.connect(self._on_tab_close)
        self._tab_bar.tab_double_clicked.connect(self._on_tab_double_click)
        if self._theme_manager is not None:
            self._theme_manager.theme_changed.connect(self._tab_bar.refresh_theme)
        layout.addWidget(self._tab_bar)

        breadcrumb_row = QHBoxLayout()
        breadcrumb_row.setContentsMargins(0, 0, 0, 0)
        breadcrumb_row.setSpacing(8)

        self._breadcrumb_bar = BreadcrumbBar()
        breadcrumb_row.addWidget(self._breadcrumb_bar, 1)

        self._save_btn = QPushButton("Save")
        self._save_btn.setObjectName("saveButton")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setMinimumWidth(92)
        self._save_btn.setEnabled(False)
        self._save_btn.setToolTip("No changes to save")
        self._save_btn.setVisible(False)
        self._save_btn.clicked.connect(self._on_save_request)
        self._refresh_save_btn_icon()
        breadcrumb_row.addWidget(self._save_btn)

        # Right margin so Save aligns roughly with the Send button below
        breadcrumb_row.setContentsMargins(0, 0, 12, 0)

        layout.addLayout(breadcrumb_row)

        if self._theme_manager is not None:
            self._theme_manager.theme_changed.connect(self._refresh_save_btn_icon)

        self._editor_stack = QStackedWidget()
        layout.addWidget(self._editor_stack, 1)

        # Default editor (also reachable as self.request_widget)
        self._default_editor = RequestEditorWidget()
        self.request_widget = self._default_editor
        self._editor_stack.addWidget(self._default_editor)

        # Wire send for the default editor
        self.request_widget.send_requested.connect(self._on_send_request)
        self.request_widget.debug_step_requested.connect(self._on_debug_step)
        self.request_widget.open_collection_requested.connect(self._open_folder)
        self.request_widget.open_scripting_settings_requested.connect(
            self._on_open_scripting_settings
        )
        self.request_widget.scripts_tab_active_changed.connect(self._on_editor_scripts_tab_changed)

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
    # Navigation shortcuts (no visible toolbar)
    # ------------------------------------------------------------------
    def _create_nav_actions(self) -> None:
        """Register request open-history actions for Alt+Left / Alt+Right."""
        self.back_action = QAction(phi("arrow-left", size=20), "Go back", self)
        self.back_action.setToolTip("Go back to previously opened request")
        self.back_action.setShortcut(QKeySequence("Alt+Left"))
        self.back_action.setEnabled(False)
        self.back_action.triggered.connect(self._navigate_back)
        self.addAction(self.back_action)

        self.forward_action = QAction(phi("arrow-right", size=20), "Go forward", self)
        self.forward_action.setToolTip("Go forward in request open history")
        self.forward_action.setShortcut(QKeySequence("Alt+Right"))
        self.forward_action.setEnabled(False)
        self.forward_action.triggered.connect(self._navigate_forward)
        self.addAction(self.forward_action)

    # ------------------------------------------------------------------
    # Status bar creation
    # ------------------------------------------------------------------
    def _create_status_bar(self) -> None:
        """Build the bottom status bar with the sidebar collapse/expand button."""
        status_bar = QStatusBar()
        status_bar.setObjectName("appStatusBar")
        status_bar.setSizeGripEnabled(False)
        status_bar.setFixedHeight(22)
        status_bar.setContentsMargins(0, 0, 0, 0)
        layout = status_bar.layout()
        if layout is not None:
            layout.setContentsMargins(2, 0, 2, 0)
            layout.setSpacing(0)
        self.setStatusBar(status_bar)

        self._sidebar_toggle_btn = QPushButton()
        self._sidebar_toggle_btn.setObjectName("statusBarButton")
        self._sidebar_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sidebar_toggle_btn.setFlat(True)
        self._sidebar_toggle_btn.setFixedSize(24, 18)
        self._sidebar_toggle_btn.clicked.connect(self._toggle_sidebar)
        status_bar.addWidget(self._sidebar_toggle_btn)

    def _sync_sidebar_toggle_btn(self) -> None:
        """Update the sidebar toggle button icon and tooltip to match state."""
        hidden = not self._left_sidebar.is_open
        icon_name = "caret-double-right" if hidden else "caret-double-left"
        self._sidebar_toggle_btn.setIcon(phi(icon_name, size=12))
        self._sidebar_toggle_btn.setToolTip("Expand sidebar" if hidden else "Collapse sidebar")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        """Assemble the full window layout from menus, shortcuts, and panes."""
        # 1. Menu, navigation shortcuts, status bar
        self._create_menus()
        self._create_nav_actions()
        self._create_status_bar()

        # Hide them initially during loading
        self.menuBar().hide()
        self.statusBar().hide()

        # 2. Main stack: loading screen vs main UI
        self._main_stack = QStackedWidget()
        self.setCentralWidget(self._main_stack)

        self._loading_screen = LoadingScreen()
        self._main_stack.addWidget(self._loading_screen)
        self._loading_screen.start_animation()

        # 3. Main splitter: left rail + flyout (nav) + centre (request+response+right rail)
        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_stack.addWidget(central)

        self._main_splitter = QSplitter(Qt.Orientation.Horizontal, central)
        self._main_splitter.setObjectName("mainWindowHorizontalSplitter")
        self._main_splitter.setHandleWidth(1)
        main_layout.addWidget(self._main_splitter)

        # --- Left navigation: collections + environments (vertical splitter) ---
        self._left_nav_splitter = QSplitter(Qt.Orientation.Vertical)
        self._left_nav_splitter.setHandleWidth(6)
        self._left_nav_splitter.setChildrenCollapsible(False)
        self._left_nav_splitter.addWidget(self.collection_widget)

        self._env_selector = EnvironmentSidebarPanel()
        self._left_nav_splitter.addWidget(self._env_selector)
        self._left_nav_splitter.setStretchFactor(0, 4)
        self._left_nav_splitter.setStretchFactor(1, 1)
        self._left_nav_splitter.setSizes([520, 160])
        self._env_selector.refresh()

        self._left_sidebar.set_content(self._left_nav_splitter)

        self.snippets_sidebar_panel = SnippetsSidebarPanel(self)
        self._local_scripts_snippets_splitter = QSplitter(Qt.Orientation.Vertical)
        self._local_scripts_snippets_splitter.setHandleWidth(6)
        self._local_scripts_snippets_splitter.setChildrenCollapsible(False)
        self._local_scripts_snippets_splitter.addWidget(self.local_scripts_widget)
        self._local_scripts_snippets_splitter.addWidget(self.snippets_sidebar_panel)
        self._local_scripts_snippets_splitter.setStretchFactor(0, 3)
        self._local_scripts_snippets_splitter.setStretchFactor(1, 2)
        self._local_scripts_snippets_splitter.setSizes([360, 200])

        self._left_sidebar.set_local_scripts_panel(self._local_scripts_snippets_splitter)
        self._left_sidebar.install_in_splitter(self._main_splitter)

        # --- Centre: vertical splitter (request + response) ---
        request_area = self._build_request_area()

        self._right_splitter = QSplitter(Qt.Orientation.Vertical)

        # --- Content area: centre panes + right sidebar rail ---
        self._content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._content_splitter.setHandleWidth(4)
        self._main_splitter.addWidget(self._content_splitter)
        self._main_splitter.setStretchFactor(2, 3)

        self._content_splitter.addWidget(self._right_splitter)
        self._right_sidebar.install_in_splitter(self._content_splitter)
        self._content_splitter.setStretchFactor(0, 1)
        self._content_splitter.setCollapsible(0, False)

        # --- Request editor area ---
        self._right_splitter.addWidget(request_area)
        self._right_splitter.setCollapsible(0, False)

        # --- Response viewer area ---
        self._response_area = self._build_response_area()
        self._right_splitter.addWidget(self._response_area)

        # --- Bottom panel (Console) ---
        self._console_panel = ConsolePanel()
        self._bottom_panel = self._console_panel  # alias for toggle/tests
        self._bottom_panel.hide()
        self._right_splitter.addWidget(self._bottom_panel)

        # Track chrome geometry so the request/response splitter handle can be
        # dragged up to the section-tabs strip but not past it. The tab bar can
        # wrap to multiple rows as tabs are added, so the floor is recomputed
        # from live widget positions rather than a fixed height.
        self._tab_bar.installEventFilter(self)
        self._editor_stack.installEventFilter(self)
        self._editor_stack.currentChanged.connect(
            lambda _i: QTimer.singleShot(0, self._update_request_area_min)
        )
        QTimer.singleShot(0, self._update_request_area_min)

        self._sync_sidebar_toggle_btn()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Recompute request_area's min when chrome geometry changes (tab wrap, etc.)."""
        if event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.LayoutRequest,
        ) and (obj is self._tab_bar or obj is self._editor_stack):
            QTimer.singleShot(0, self._update_request_area_min)
        return bool(super().eventFilter(obj, event))

    def _update_request_area_min(self) -> None:
        """Clamp request_area's min to the section-tabs-strip bottom (in wrapper coords)."""
        from ui.request.request_editor import RequestEditorWidget as _REW

        if not hasattr(self, "_request_area") or self._request_area is None:
            return
        current = self._editor_stack.currentWidget() if hasattr(self, "_editor_stack") else None
        if not isinstance(current, _REW):
            self._request_area.setMinimumHeight(0)
            return
        bar = current._tabs.tabBar()
        if bar is None or not bar.isVisible():
            self._request_area.setMinimumHeight(0)
            return
        bottom = bar.mapTo(self._request_area, QPoint(0, bar.height())).y()
        if bottom <= 0:
            return
        self._request_area.setMinimumHeight(bottom)

    def _on_load_finished(self) -> None:
        """Switch from the loading screen to the main UI."""
        self._loading_screen.stop_animation()
        self._main_stack.setCurrentIndex(1)
        self.menuBar().show()
        self.statusBar().show()

        # Restore tabs from the previous session after collections are ready.
        self._restore_tabs()

    def refresh_snippets_sidebar(self) -> None:
        """Refresh the left-flyout snippets list and the open snippet picker."""
        if hasattr(self, "snippets_sidebar_panel"):
            self.snippets_sidebar_panel.refresh()
        from ui.widgets.snippets.popup import SnippetsPopup

        SnippetsPopup.reload_from_cache_if_visible()

    # ------------------------------------------------------------------
    # Sidebar -> editor wiring
    # ------------------------------------------------------------------
    def _on_item_action(self, item_type: str, item_id: int, action: str) -> None:
        """Handle actions triggered from the collection or local-scripts tree."""
        if item_type == "request":
            if action == "Open":
                self._open_request(item_id, push_history=True, is_preview=False)
            elif action == "Preview":
                self._open_request(item_id, push_history=True, is_preview=True)
        elif item_type == "script" and action == "Open":
            self._open_local_script(item_id)
        elif item_type == "folder" and action == "Open":
            self._open_folder(item_id)

    # ------------------------------------------------------------------
    # View toggles
    # ------------------------------------------------------------------
    def _toggle_response_pane(self) -> None:
        """Show or hide the response viewer pane."""
        self._response_area.setHidden(not self._response_area.isHidden())

    def _toggle_sidebar(self) -> None:
        """Collapse or expand the collections flyout; the left rail stays visible.

        Matches dragging the flyout splitter to zero width vs reopening: same
        splitter sizes and rail visibility as :meth:`LeftSidebar.close_panel` /
        :meth:`LeftSidebar.open_panel`.
        """
        if self._left_sidebar.is_open:
            self._left_sidebar.close_panel()
        else:
            self._left_sidebar.open_panel()
        self._sync_sidebar_toggle_btn()

    def _toggle_bottom_panel(self) -> None:
        """Show or hide the bottom panel (Console)."""
        self._bottom_panel.setVisible(self._bottom_panel.isHidden())

    def _toggle_layout_orientation(self) -> None:
        """Switch the request/response split between vertical and horizontal."""
        if self._right_splitter.orientation() == Qt.Orientation.Vertical:
            self._right_splitter.setOrientation(Qt.Orientation.Horizontal)
        else:
            self._right_splitter.setOrientation(Qt.Orientation.Vertical)

    def _activate_next_tab(self) -> None:
        """Select the next open tab, wrapping at the end of the deck."""
        self._tab_bar.select_next_tab()

    def _activate_previous_tab(self) -> None:
        """Select the previous open tab, wrapping at the start of the deck."""
        self._tab_bar.select_previous_tab()

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------
    def _on_settings(self) -> None:
        """Open the settings dialog (Appearance first)."""
        self._open_settings_dialog(initial_category="Appearance")

    def _on_open_scripting_settings(self) -> None:
        """Open Settings on the Scripting page (Deno path, download)."""
        self._open_settings_dialog(initial_category="Scripting")

    def _open_settings_dialog(self, *, initial_category: str) -> None:
        """Show the modal settings dialog and refresh script Deno banners when it closes."""
        from ui.dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            self._theme_manager,
            self._tab_settings_manager,
            self,
            initial_category=initial_category,
        )
        dialog.exec()
        w = self._editor_stack.currentWidget()
        if w is not None and hasattr(w, "_update_runtime_banners"):
            w._update_runtime_banners()  # type: ignore[union-attr]

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
        For draft tabs (``request_id is None``), opens the
        save-to-collection dialog.
        """
        ctx = self._current_tab_context()

        # Folder tabs use auto-save -- trigger immediately on Ctrl+S
        if ctx is not None and ctx.tab_type == "folder":
            if ctx.folder_editor is not None and ctx.collection_id is not None:
                data = ctx.folder_editor.get_collection_data()
                self._on_folder_auto_save(data)
            return

        if ctx is not None and ctx.tab_type == "environments":
            return

        if ctx is not None and ctx.tab_type == "local_script":
            self._on_save_local_script()
            return

        editor = ctx.require_editor() if ctx else self.request_widget

        request_id = editor.request_id

        # Draft request -- open save-to-collection dialog
        # Only when an actual tab exists (ctx is not None); a bare editor
        # with no tab is not saveable.
        if request_id is None:
            if ctx is not None:
                self._save_draft_request(ctx, editor)
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
    def _refresh_save_btn_icon(self) -> None:
        """Re-tint the floppy icon so it matches QSS (glyph icons ignore button text color)."""
        color = COLOR_ACCENT if self._save_btn.isEnabled() else COLOR_TEXT_MUTED
        self._save_btn.setIcon(phi("floppy-disk", color=color))

    def _sync_save_btn(self, dirty: bool) -> None:
        """Update the Save button enabled state and tooltip."""
        self._save_btn.setEnabled(dirty)
        self._save_btn.setToolTip("" if dirty else "No changes to save")
        self._refresh_save_btn_icon()

    # ------------------------------------------------------------------
    # Close event
    # ------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:
        """Persist session and clean up all tabs before closing."""
        if self._debug_protocol is not None:
            self._debug_protocol.stop()
            self._debug_protocol = None
        self._end_debug_ui()
        self._persist_open_tabs()
        for ctx in self._tabs.values():
            ctx.cancel_send()
            ctx.cleanup_thread()
            editor = getattr(ctx, "editor", None)
            for attr in ("_pre_output_panel", "_test_output_panel"):
                panel = getattr(editor, attr, None)
                if panel is not None:
                    panel.cleanup()
        self._cleanup_send_thread()
        self._console_panel.cleanup()

        from services.scripting.engine import ScriptLinter

        ScriptLinter.shutdown()

        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Collection runner
    # ------------------------------------------------------------------
    def _on_run_collection(self) -> None:
        """Open the folder tab and inline runner for the selected collection."""
        coll_id = self.collection_widget.selected_collection_id()
        if coll_id is None:
            logger.warning("No collection selected for runner")
            return
        self._on_run_collection_by_id(coll_id)

    def _on_run_collection_by_id(self, collection_id: int) -> None:
        """Open or focus the folder tab on Runs -> New run for *collection_id*."""
        self._open_folder(collection_id, focus_runner_panel=True)

    # ------------------------------------------------------------------
    # Environment editor
    # ------------------------------------------------------------------
    def _on_manage_environments(self) -> None:
        """Open the environments editor in a main-window tab."""
        self._open_environments_tab()

    # ------------------------------------------------------------------
    # Save response handler
    # ------------------------------------------------------------------
    def _on_save_response(self, data: dict) -> None:
        """Save the displayed response as a named example."""
        ctx = self._current_tab_context()
        if ctx is None or ctx.request_id is None:
            return
        code = data.get("code")
        status = data.get("status") or ""
        default_name = f"{code} {status}".strip() or "Saved Response"
        name, accepted = QInputDialog.getText(
            self,
            "Save Response",
            "Example name:",
            text=default_name,
        )
        if not accepted:
            return
        clean_name = name.strip() or default_name
        request_data = ctx.require_editor().get_request_data()
        CollectionService.save_response(
            ctx.request_id,
            name=clean_name,
            status=status or None,
            code=code if isinstance(code, int) else None,
            headers=data.get("headers"),
            body=data.get("body"),
            preview_language=data.get("preview_language"),
            original_request=request_data,
        )
        self._refresh_sidebar()

    def _on_save_current_response_requested(self) -> None:
        """Save the current live response from the active response viewer."""
        ctx = self._current_tab_context()
        if ctx is None:
            return
        payload = ctx.require_response_viewer().get_save_response_data()
        if payload is None:
            return
        self._on_save_response(payload)

    def _on_rename_saved_response(self, response_id: int) -> None:
        """Rename a saved response from the sidebar panel."""
        detail = CollectionService.get_saved_response(response_id)
        if detail is None:
            return
        name, accepted = QInputDialog.getText(
            self,
            "Rename Saved Response",
            "New name:",
            text=detail["name"],
        )
        if not accepted:
            return
        CollectionService.rename_saved_response(response_id, name)
        self._refresh_sidebar()
        self._right_sidebar.saved_responses_panel.select_response(response_id)

    def _on_duplicate_saved_response(self, response_id: int) -> None:
        """Duplicate a saved response from the sidebar panel."""
        new_id = CollectionService.duplicate_saved_response(response_id)
        self._refresh_sidebar()
        self._right_sidebar.saved_responses_panel.select_response(new_id)

    def _on_delete_saved_response(self, response_id: int) -> None:
        """Delete a saved response from the sidebar panel after confirmation."""
        confirm = QMessageBox.question(
            self,
            "Delete Saved Response",
            "Delete this saved response?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        CollectionService.delete_saved_response(response_id)
        self._refresh_sidebar()
