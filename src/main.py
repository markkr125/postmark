#!/usr/bin/env python3
"""Application entry point -- QApplication bootstrap and database init."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from database.database import init_db
from ui.main_window import MainWindow

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
