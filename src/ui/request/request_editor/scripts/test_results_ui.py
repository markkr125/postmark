"""Test-result row widgets and export toolbar for :class:`ScriptOutputPanel`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.styling.icons import phi
from ui.styling.theme import COLOR_DANGER, COLOR_SUCCESS


def build_test_export_toolbar(
    *,
    on_export_json: Callable[[], None],
    on_export_junit: Callable[[], None],
    parent: QWidget | None = None,
) -> QWidget:
    """Return a toolbar row with Export JSON / JUnit actions."""
    bar = QWidget(parent)
    row = QHBoxLayout(bar)
    row.setContentsMargins(0, 0, 0, 0)
    row.addStretch()
    btn = QToolButton(bar)
    btn.setText("Export")
    btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    menu = QMenu(btn)
    json_act = menu.addAction("Export JSON")
    json_act.triggered.connect(on_export_json)
    junit_act = menu.addAction("Export JUnit XML")
    junit_act.triggered.connect(on_export_junit)
    btn.setMenu(menu)
    row.addWidget(btn)
    return bar


def build_test_result_row(
    result: dict[str, Any],
    *,
    on_rerun: Callable[[str], None] | None = None,
    parent: QWidget | None = None,
) -> QWidget:
    """Build one test-result row; optional *on_rerun* adds a Rerun button."""
    passed = result.get("passed", False)
    is_error = result.get("name") == "(runtime error)"
    icon_name = "warning" if is_error else ("check-circle" if passed else "x-circle")
    color = COLOR_DANGER if (is_error or not passed) else COLOR_SUCCESS

    row = QWidget(parent)
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 1, 0, 1)
    row_layout.setSpacing(6)

    icon_label = QLabel(row)
    icon_label.setPixmap(phi(icon_name, color=color).pixmap(14, 14))
    icon_label.setFixedSize(16, 16)
    row_layout.addWidget(icon_label)

    display = result.get("name", "unnamed")
    if is_error:
        source = result.get("source_name", "")
        display = f"Script error in \u2018{source}\u2019" if source else "Script error"
    name_label = QLabel(display, row)
    name_label.setStyleSheet("font-size: 12px;")
    row_layout.addWidget(name_label, 1)

    duration = result.get("duration_ms", 0.0)
    if duration > 0:
        dur_label = QLabel(f"{duration:.0f} ms", row)
        dur_label.setObjectName("mutedLabel")
        dur_label.setStyleSheet("font-size: 11px;")
        row_layout.addWidget(dur_label)

    test_name = str(result.get("name", ""))
    if on_rerun is not None and test_name and not is_error:
        rerun_btn = QPushButton("Rerun", row)
        rerun_btn.setObjectName("smallSecondaryButton")
        rerun_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rerun_btn.clicked.connect(lambda _checked=False, n=test_name: on_rerun(n))
        row_layout.addWidget(rerun_btn)

    error_msg = result.get("error")
    if error_msg and not passed:
        name_label.setToolTip(str(error_msg))
        err_label = QLabel(str(error_msg), row)
        err_label.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 11px;")
        err_label.setWordWrap(True)
        outer = QWidget(parent)
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(row)
        outer_layout.addWidget(err_label)
        return outer
    return row
