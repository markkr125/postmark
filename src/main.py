#!/usr/bin/env python3
"""Application entry point -- QApplication bootstrap and database init."""

from __future__ import annotations

import sys

# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------
if __name__ == "__main__":
    from qt_app_init import configure_before_qapplication

    configure_before_qapplication()

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("Postmark")
    app.setApplicationDisplayName("Postmark")

    from ui.loading_screen import LoadingScreen

    splash = LoadingScreen()
    splash.setWindowTitle("Loading Postmark…")
    splash.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    splash.showMaximized()
    splash.start_animation()
    app.processEvents()

    from database.database import init_db
    from services.lsp.server_registry import LspRegistry
    from ui.main_window import MainWindow
    from ui.styling.history_settings_manager import HistorySettingsManager
    from ui.styling.icons import load_font
    from ui.styling.tab_settings_manager import TabSettingsManager
    from ui.styling.theme_manager import ThemeManager

    # Apply theme (reads QSettings, sets style + palette + global QSS)
    theme_manager = ThemeManager(app)
    tab_settings_manager = TabSettingsManager(app)
    history_settings_manager = HistorySettingsManager(app)

    # Load the Phosphor icon font (must happen after QApplication)
    load_font()

    app.aboutToQuit.connect(lambda: LspRegistry.instance().shutdown())

    # Initialise the database before any widget accesses it
    init_db()

    window = MainWindow(
        theme_manager=theme_manager,
        tab_settings_manager=tab_settings_manager,
        history_settings_manager=history_settings_manager,
    )
    window.showMaximized()
    splash.stop_animation()
    splash.close()
    app.processEvents()
    ret = app.exec()

    from services.scripting.engine import ScriptLinter

    ScriptLinter.shutdown()

    sys.exit(ret)
