"""Test-result row widgets and export toolbar for :class:`ScriptOutputPanel`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from services.scripting.script_error_format import format_script_runtime_error
from ui.styling.icons import phi
from ui.styling.theme import COLOR_DANGER, COLOR_SUCCESS, COLOR_TEXT

_EXPORT_BTN_TOOLTIP = (
    "Save this run's test results to a file.\n"
    "• JSON — full structured results (name, passed/failed, duration, errors).\n"
    "• JUnit XML — drop into CI test-report dashboards (Jenkins, GitLab, etc.)."
)


def build_test_export_toolbar(
    *,
    on_export_json: Callable[[], None],
    on_export_junit: Callable[[], None],
    parent: QWidget | None = None,
) -> QToolButton:
    """Return the Export-results button (JSON / JUnit XML in its menu)."""
    btn = QToolButton(parent)
    btn.setObjectName("exportResultsBtn")
    btn.setText("Export results")
    btn.setIcon(phi("download-simple", color=COLOR_TEXT, size=14))
    btn.setIconSize(QSize(14, 14))
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    btn.setArrowType(Qt.ArrowType.DownArrow)
    btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(_EXPORT_BTN_TOOLTIP)
    menu = QMenu(btn)
    json_act = menu.addAction("Save as JSON (.json)…")
    json_act.setToolTip("Full structured results — useful for scripts or diffing.")
    json_act.triggered.connect(on_export_json)
    junit_act = menu.addAction("Save as JUnit XML (.xml)…")
    junit_act.setToolTip("Standard CI test-report format consumed by Jenkins, GitLab, etc.")
    junit_act.triggered.connect(on_export_junit)
    menu.setToolTipsVisible(True)
    btn.setMenu(menu)
    return btn


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
        display_error = format_script_runtime_error(str(error_msg))
        name_label.setToolTip(str(error_msg))
        err_label = QLabel(display_error, row)
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
