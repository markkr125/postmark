#!/usr/bin/env python3
"""Close desktop windows left behind by pytest/Qt UI tests.

Run after a stuck test run::

    poetry run python scripts/close_stuck_qt_test_windows.py

If windows remain, stop stray pytest workers first::

    pkill -f 'pytest.*postmark' || true
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, _ROOT)


def main() -> int:
    """Close orphan top-level widgets in the current QApplication."""
    from PySide6.QtWidgets import QApplication

    from qt_app_init import configure_before_qapplication
    from tests.qt_popup_cleanup import dismiss_all_top_level_test_widgets

    configure_before_qapplication()
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication(sys.argv)
    before = len(app.topLevelWidgets())
    dismiss_all_top_level_test_widgets(app)
    after = len(app.topLevelWidgets())
    closed = max(0, before - after)
    print(f"Closed {closed} top-level widget(s); {after} remain (including QApplication).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
