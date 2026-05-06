"""Runs tab mixin for the folder editor.

Provides the run-history table builder and row-population logic that
``FolderEditorWidget`` inherits via ``_RunsMixin``.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from services.run_history_service import RunHistoryService

_RUNS_HEADERS = [
    "Start time",
    "Source",
    "Duration",
    "All tests",
    "Passed",
    "Failed",
    "Skipped",
    "Avg. Resp. Time",
    "Status",
]


def _build_runs_table() -> QTableWidget:
    """Create a read-only table widget for displaying run history."""
    table = QTableWidget(0, len(_RUNS_HEADERS))
    table.setHorizontalHeaderLabels(_RUNS_HEADERS)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    header = table.horizontalHeader()
    if header:
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(_RUNS_HEADERS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
    return table


class _RunsMixin:
    """Mixin providing run-history methods for ``FolderEditorWidget``.

    The host class must define ``_runs_table`` and ``_run_detail_table``.
    """

    # Attribute stubs for type checkers
    _runs_table: QTableWidget
    _run_detail_table: QTableWidget

    def load_runs(self, runs: list[dict[str, Any]]) -> None:
        """Populate the Runs tab table with run history data.

        Each dict should contain ``started_at``, ``source``, ``duration_ms``,
        ``total_tests``, ``passed``, ``failed``, ``avg_response_ms``, and
        ``status``.
        """
        self._runs_table.setRowCount(0)
        for run in runs:
            row = self._runs_table.rowCount()
            self._runs_table.insertRow(row)

            started = run.get("started_at", "")
            if hasattr(started, "strftime"):
                started = started.strftime("%Y-%m-%d %H:%M:%S")
            started_item = QTableWidgetItem(str(started))
            run_id = run.get("id")
            if run_id is not None:
                started_item.setData(Qt.ItemDataRole.UserRole, int(run_id))
            self._runs_table.setItem(row, 0, started_item)
            self._runs_table.setItem(row, 1, QTableWidgetItem(run.get("source", "")))

            dur = run.get("duration_ms", 0)
            dur_str = f"{dur / 1000:.1f}s" if dur >= 1000 else f"{dur}ms"
            self._runs_table.setItem(row, 2, QTableWidgetItem(dur_str))

            self._runs_table.setItem(row, 3, QTableWidgetItem(str(run.get("total_tests", 0))))
            self._runs_table.setItem(row, 4, QTableWidgetItem(str(run.get("passed", 0))))
            self._runs_table.setItem(row, 5, QTableWidgetItem(str(run.get("failed", 0))))
            self._runs_table.setItem(row, 6, QTableWidgetItem(str(run.get("skipped", 0))))

            avg = run.get("avg_response_ms", 0.0)
            self._runs_table.setItem(row, 7, QTableWidgetItem(f"{avg:.0f}ms"))
            self._runs_table.setItem(row, 8, QTableWidgetItem(run.get("status", "")))

    def _on_run_history_row_selected(self) -> None:
        """Populate the per-request detail table for the highlighted run."""
        self._run_detail_table.setRowCount(0)
        items = self._runs_table.selectedItems()
        if not items:
            return
        row = items[0].row()
        started_item = self._runs_table.item(row, 0)
        if started_item is None:
            return
        run_id = started_item.data(Qt.ItemDataRole.UserRole)
        if run_id is None:
            return
        results = RunHistoryService.get_run_results(int(run_id))
        for r in results:
            i = self._run_detail_table.rowCount()
            self._run_detail_table.insertRow(i)
            self._run_detail_table.setItem(i, 0, QTableWidgetItem(str(r.get("request_name", ""))))
            self._run_detail_table.setItem(i, 1, QTableWidgetItem(str(r.get("request_method", ""))))
            self._run_detail_table.setItem(i, 2, QTableWidgetItem(str(r.get("status_code", ""))))
            self._run_detail_table.setItem(
                i, 3, QTableWidgetItem(f"{float(r.get('elapsed_ms', 0) or 0):.0f}")
            )
            passed = int(r.get("test_passed", 0) or 0)
            failed = int(r.get("test_failed", 0) or 0)
            total = passed + failed
            tests_cell = f"{passed}/{total}" if total else "-"
            self._run_detail_table.setItem(i, 4, QTableWidgetItem(tests_cell))
            err = r.get("error")
            result_text = str(err) if err else "OK"
            self._run_detail_table.setItem(i, 5, QTableWidgetItem(result_text))
