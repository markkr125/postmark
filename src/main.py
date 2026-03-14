#!/usr/bin/env python3
"""Application entry point -- QApplication bootstrap and database init."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from database.database import init_db
from ui.main_window import MainWindow
from ui.styling.icons import load_font
from ui.styling.tab_settings_manager import TabSettingsManager
from ui.styling.theme_manager import ThemeManager

# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Apply theme (reads QSettings, sets style + palette + global QSS)
    theme_manager = ThemeManager(app)
    tab_settings_manager = TabSettingsManager(app)

    # Load the Phosphor icon font (must happen after QApplication)
    load_font()

    # Initialise the database before any widget accesses it
    init_db()

    window = MainWindow(
        theme_manager=theme_manager,
        tab_settings_manager=tab_settings_manager,
    )
    window.show()
    sys.exit(app.exec())
