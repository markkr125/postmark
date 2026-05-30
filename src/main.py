#!/usr/bin/env python3
"""Application entry point -- QApplication bootstrap and database init."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from database.database import init_db
from qt_app_init import configure_before_qapplication
from services.lsp.server_registry import LspRegistry
from ui.main_window import MainWindow
from ui.styling.icons import load_font
from ui.styling.tab_settings_manager import TabSettingsManager
from ui.styling.theme_manager import ThemeManager

# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------
if __name__ == "__main__":
    configure_before_qapplication()
    app = QApplication(sys.argv)
    app.setApplicationName("Postmark")
    app.setApplicationDisplayName("Postmark")

    # Apply theme (reads QSettings, sets style + palette + global QSS)
    theme_manager = ThemeManager(app)
    tab_settings_manager = TabSettingsManager(app)

    # Load the Phosphor icon font (must happen after QApplication)
    load_font()

    app.aboutToQuit.connect(lambda: LspRegistry.instance().shutdown())

    # Initialise the database before any widget accesses it
    init_db()
    from services.scripting.local_scripts_project.deno_config import ensure_local_project_config

    ensure_local_project_config()

    window = MainWindow(
        theme_manager=theme_manager,
        tab_settings_manager=tab_settings_manager,
    )
    window.showMaximized()
    ret = app.exec()

    from services.scripting.engine import ScriptLinter

    ScriptLinter.shutdown()

    sys.exit(ret)
