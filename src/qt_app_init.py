"""Qt process bootstrap — must run before the first ``QApplication`` is created.

Sets Hi-DPI scale-factor rounding while no ``QGuiApplication`` instance exists.
On fractional system scales (125 %, 150 %, etc.) this avoids non-integer device
pixel ratios that often make all UI text look soft or muddy, especially on
Linux and Windows.  (High-DPI pixmaps are handled by Qt 6 by default.)
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication


def configure_before_qapplication() -> None:
    """Round fractional Hi-DPI scale factors (no-op if a GUI app already exists)."""
    if QGuiApplication.instance() is not None:
        return
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.RoundPreferFloor
    )
