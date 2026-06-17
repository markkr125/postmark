"""Per-row gear control for the Budgets settings table."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from ui.styling.icons import phi


def make_budget_row_gear_button(*, on_open: Callable[[], None]) -> QWidget:
    """Gear button that opens the connection limits/spend dialog."""
    wrap = QWidget()
    row = QHBoxLayout(wrap)
    row.setContentsMargins(4, 0, 4, 0)
    row.setSpacing(0)
    row.addStretch(1)

    btn = QPushButton(wrap)
    btn.setObjectName("aiBudgetActionsButton")
    btn.setIcon(phi("gear"))
    btn.setToolTip("Limits and spend details")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(30, 28)
    btn.clicked.connect(on_open)
    row.addWidget(btn)
    return wrap


__all__ = ["make_budget_row_gear_button"]
