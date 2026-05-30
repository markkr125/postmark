"""Test-result rows and summary for :class:`ScriptOutputPanel`."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from ui.styling.theme import COLOR_DANGER, COLOR_SUCCESS


def add_test_row(panel: Any, result: dict[str, Any]) -> None:
    """Add a single test-result row."""
    from ui.request.request_editor.scripts.test_results_ui import build_test_result_row

    on_rerun = None
    if panel._script_type == "test":
        on_rerun = panel._on_rerun_test_clicked
    widget = build_test_result_row(result, on_rerun=on_rerun, parent=panel)
    panel._insert_row(widget)
    name = str(result.get("name", ""))
    if name:
        panel._test_row_widgets[name] = widget


def sync_timing_row(panel: Any) -> None:
    """Single source of truth for Export-button + timing-row visibility.

    Export shows iff there are stored test results AND the panel actually
    has an Export button (pre-request panels don't). The whole row is shown
    iff the Export button OR the elapsed label has something to display.
    """
    export_btn = getattr(panel, "_export_btn", None)
    has_results = bool(getattr(panel, "_last_test_results", None))
    has_elapsed = bool(panel._elapsed_label.text())
    export_wants_visible = has_results and export_btn is not None
    if export_btn is not None:
        export_btn.setVisible(export_wants_visible)
    panel._timing_row.setVisible(export_wants_visible or has_elapsed)


def apply_run_elapsed_header(
    panel: Any,
    elapsed_ms: float,
    test_results: list[dict[str, Any]],
) -> None:
    """Show total run time only when no test rows carry duration."""
    if test_results:
        panel._elapsed_label.setText("")
    else:
        panel._elapsed_label.setText(f"{elapsed_ms:.0f} ms")
    sync_timing_row(panel)


def add_test_summary(panel: Any, results: list[dict[str, Any]]) -> None:
    """Add a summary line for test results."""
    runtime_errors = [r for r in results if r.get("name") == "(runtime error)"]
    real_tests = [r for r in results if r.get("name") != "(runtime error)"]

    if runtime_errors and not real_tests:
        text = f"<span style='color:{COLOR_DANGER};font-weight:bold;'>Script error</span>"
    else:
        passed = sum(1 for r in results if r.get("passed"))
        total = len(results)
        color = COLOR_SUCCESS if passed == total else COLOR_DANGER
        text = f"<span style='color:{color};font-weight:bold;'>{passed}/{total} tests passed</span>"

    summary = QLabel(text)
    summary.setTextFormat(Qt.TextFormat.RichText)
    summary.setStyleSheet("font-size: 12px; padding-top: 4px;")
    panel._insert_row(summary)


def refresh_test_rows(
    panel: Any,
    test_results: list[dict[str, Any]],
    *,
    elapsed_ms: float,
) -> None:
    """Replace stored test rows after a filtered single-test rerun."""
    panel._last_test_results = list(test_results)
    for w in list(panel._test_row_widgets.values()):
        w.deleteLater()
    panel._test_row_widgets.clear()
    apply_run_elapsed_header(panel, elapsed_ms, test_results)
    for result in test_results:
        add_test_row(panel, result)
    if test_results:
        add_test_summary(panel, test_results)
    panel.setVisible(True)
