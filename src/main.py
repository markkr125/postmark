#!/usr/bin/env python3

import sys

# ── Qt imports ─────────────────────────────────────────────────────
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import (QAction, QCursor, QGuiApplication, QIcon,
                           QKeySequence)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow,
                               QSplitter, QToolBar, QVBoxLayout, QWidget)

# ── Local imports ───────────────────────────────────────────────────
from database.database import init_db
from ui.collections.collection_widget import CollectionWidget


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Postmark")
        self.resize(1200, 800)

        # Place-holders for future persistence logic
        self.collections: dict = {}
        self.environments: dict = {}

        self.collection_widget = CollectionWidget(self)

        self._setup_ui()

        # ---- Move to the screen that contains the mouse --------------
        self._move_to_mouse_screen()

    def _move_to_mouse_screen(self):
        """Center the window on the monitor that the cursor is on."""
        # 1. Find the screen that the cursor is currently on
        cursor_pos = QCursor.pos()                # global screen coordinates
        screen = QGuiApplication.screenAt(cursor_pos)

        # 2. If we found a screen, move the window so it is centered there
        if screen is not None:
            screen_geom = screen.availableGeometry()   # skip taskbars, docks…
            win_geom   = self.frameGeometry()          # includes frame
            win_geom.moveCenter(screen_geom.center())
            self.move(win_geom.topLeft())

        # 3. If screen is None (rare), just leave the window where Qt chose


    # ----------------------------------------------------------------------
    # Menu creation
    # ----------------------------------------------------------------------
    def _create_menus(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
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

    # ----------------------------------------------------------------------
    # Request/response area helpers
    # ----------------------------------------------------------------------
    def _build_request_area(self) -> None:
        self.request_widget = QWidget()
        QVBoxLayout(self.request_widget)

    def _build_response_area(self) -> None:
        self.response_widget = QWidget()
        QVBoxLayout(self.response_widget)

    # ----------------------------------------------------------------------
    # Toolbar creation
    # ----------------------------------------------------------------------
    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(32, 32))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.back_action = QAction(QIcon.fromTheme("go-previous"), "Go back", self)
        self.back_action.setShortcut(QKeySequence("Alt+Left"))
        toolbar.addAction(self.back_action)

        self.forward_action = QAction(QIcon.fromTheme("go-next"), "Go forward", self)
        self.forward_action.setShortcut(QKeySequence("Alt+Right"))
        toolbar.addAction(self.forward_action)

    # ----------------------------------------------------------------------
    # UI construction
    # ----------------------------------------------------------------------
    def _setup_ui(self) -> None:
        # 1️⃣ Menu & toolbar
        self._create_menus()
        self._create_toolbar()

        # 2️⃣ Main splitter: left (nav) + right (request+response)
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
        splitter.setStretchFactor(1, 3)   # right side takes 3x the space

        # --- Request editor area ---
        self._build_request_area()
        right_splitter.addWidget(self.request_widget)

        # --- Response viewer area ---
        self._build_response_area()
        right_splitter.addWidget(self.response_widget)




# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Initialise the database before any widget accesses it
    init_db()

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
