"""Top-level application window -- menu bar, toolbar, and three-pane layout."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QCursor, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QSplitter, QToolBar, QVBoxLayout, QWidget

from services.collection_service import CollectionService
from ui.collections.collection_widget import CollectionWidget
from ui.request_editor import RequestEditorWidget

logger = logging.getLogger(__name__)

# Maximum number of entries in the back/forward navigation history
_MAX_HISTORY = 50


class MainWindow(QMainWindow):
    """Top-level application window.

    Sets up the menu bar, toolbar, and the three-pane layout
    (collection sidebar | request editor | response viewer).
    """

    def __init__(self) -> None:
        """Initialise the main window, layout, and child widgets."""
        super().__init__()
        self.setWindowTitle("Postmark")
        self.resize(1200, 800)

        # Placeholders for future persistence logic
        self.collections: dict[str, Any] = {}
        self.environments: dict[str, Any] = {}

        # Navigation history
        self._history: list[int] = []  # request IDs
        self._history_index: int = -1

        self.collection_widget = CollectionWidget(self)

        self._setup_ui()

        # Wire sidebar → editor
        self.collection_widget.item_action_triggered.connect(self._on_item_action)

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
        import_act.setShortcut(QKeySequence("Ctrl+I"))
        import_act.triggered.connect(self._on_import)
        file_menu.addAction(import_act)

        file_menu.addSeparator()

        exit_act = QAction("&Exit", self)
        exit_act.setShortcut(QKeySequence("Ctrl+Q"))
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # Collection menu
        coll_menu = menubar.addMenu("&Collection")
        run_act = QAction("Run &All", self)
        run_act.setShortcut(QKeySequence("Ctrl+R"))
        self.run_action = run_act
        coll_menu.addAction(run_act)

    # ------------------------------------------------------------------
    # Request/response area helpers
    # ------------------------------------------------------------------
    def _build_request_area(self) -> None:
        """Create the request editor pane."""
        self.request_widget = RequestEditorWidget()

    def _build_response_area(self) -> None:
        """Create the placeholder widget for the response viewer pane."""
        self.response_widget = QWidget()
        QVBoxLayout(self.response_widget)

    # ------------------------------------------------------------------
    # Toolbar creation
    # ------------------------------------------------------------------
    def _create_toolbar(self) -> None:
        """Build the main toolbar with navigation actions."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(32, 32))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.back_action = QAction(QIcon.fromTheme("go-previous"), "Go back", self)
        self.back_action.setShortcut(QKeySequence("Alt+Left"))
        self.back_action.setEnabled(False)
        self.back_action.triggered.connect(self._navigate_back)
        toolbar.addAction(self.back_action)

        self.forward_action = QAction(QIcon.fromTheme("go-next"), "Go forward", self)
        self.forward_action.setShortcut(QKeySequence("Alt+Right"))
        self.forward_action.setEnabled(False)
        self.forward_action.triggered.connect(self._navigate_forward)
        toolbar.addAction(self.forward_action)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        """Assemble the full window layout from menus, toolbar, and panes."""
        # 1. Menu & toolbar
        self._create_menus()
        self._create_toolbar()

        # 2. Main splitter: left (nav) + right (request+response)
        central = QWidget()
        main_layout = QHBoxLayout(central)
        self.setCentralWidget(central)

        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        main_layout.addWidget(splitter)

        # --- Left navigation pane ---
        splitter.addWidget(self.collection_widget)

        # --- Right side (vertical splitter) ---
        right_splitter = QSplitter(Qt.Orientation.Vertical, central)
        splitter.addWidget(right_splitter)
        splitter.setStretchFactor(1, 3)  # right side takes 3x the space

        # --- Request editor area ---
        self._build_request_area()
        right_splitter.addWidget(self.request_widget)

        # --- Response viewer area ---
        self._build_response_area()
        right_splitter.addWidget(self.response_widget)

    # ------------------------------------------------------------------
    # Sidebar → editor wiring
    # ------------------------------------------------------------------
    def _on_item_action(self, item_type: str, item_id: int, action: str) -> None:
        """Handle actions triggered from the collection tree."""
        if action == "Open" and item_type == "request":
            self._open_request(item_id, push_history=True)

    def _open_request(self, request_id: int, *, push_history: bool) -> None:
        """Load a request from the DB and display it in the editor."""
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
            "scripts": request.scripts,
        }
        self.request_widget.load_request(data)

        if push_history:
            # Trim forward history when navigating to a new page
            self._history = self._history[: self._history_index + 1]
            self._history.append(request_id)
            if len(self._history) > _MAX_HISTORY:
                self._history = self._history[-_MAX_HISTORY:]
            self._history_index = len(self._history) - 1
            self._update_nav_actions()

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
        self.back_action.setEnabled(self._history_index > 0)
        self.forward_action.setEnabled(self._history_index < len(self._history) - 1)

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------
    def _on_import(self) -> None:
        """Open the import dialog."""
        from ui.import_dialog import ImportDialog

        dialog = ImportDialog(self)
        dialog.import_completed.connect(self.collection_widget._start_fetch)
        dialog.exec()
        dialog.import_completed.connect(self.collection_widget._start_fetch)
        dialog.exec()
