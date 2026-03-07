"""Main window sub-package.

Re-exports :class:`MainWindow` so existing imports continue to work:

    from ui.main_window import MainWindow
"""

from __future__ import annotations

from ui.main_window.window import MainWindow

__all__ = ["MainWindow"]
