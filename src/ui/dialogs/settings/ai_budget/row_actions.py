"""Per-row gear menu for the Budgets settings table."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QHBoxLayout, QMenu, QPushButton, QWidget

from ui.styling.icons import phi, phi_menu


def make_budget_row_gear_button(
    *,
    on_limits: Callable[[], None] | None,
    on_details: Callable[[], None],
) -> QWidget:
    """Gear menu aligned to the right of the actions column."""
    wrap = QWidget()
    row = QHBoxLayout(wrap)
    row.setContentsMargins(4, 0, 4, 0)
    row.setSpacing(0)
    row.addStretch(1)

    menu = QMenu(wrap)
    menu.setObjectName("aiBudgetActionsMenu")
    menu.setToolTipsVisible(True)
    if on_limits is not None:
        limits_act = menu.addAction(phi_menu("currency-dollar"), "Limits")
        limits_act.setToolTip("Set reset schedule and USD spending limits")
        limits_act.triggered.connect(on_limits)
    details_act = menu.addAction(phi_menu("chart-bar"), "Spend details")
    details_act.setToolTip("View per-model spend breakdown for this connection")
    details_act.triggered.connect(on_details)

    btn = QPushButton(wrap)
    btn.setObjectName("aiBudgetActionsButton")
    btn.setIcon(phi("gear"))
    btn.setToolTip("Connection actions")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(30, 28)
    btn.clicked.connect(lambda: menu.exec(btn.mapToGlobal(QPoint(0, btn.height()))))
    row.addWidget(btn)
    return wrap


__all__ = ["make_budget_row_gear_button"]
