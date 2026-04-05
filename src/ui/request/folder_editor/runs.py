"""Runs tab mixin for the folder editor.

Provides the run-history table builder and row-population logic that
``FolderEditorWidget`` inherits via ``_RunsMixin``.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

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

    The host class must define ``_collection_id``, ``run_requested``,
    and ``_runs_table`` attributes.
    """

    # Attribute stubs for type checkers
    _collection_id: int | None
    _runs_table: QTableWidget

    def _on_run_clicked(self) -> None:
        """Emit ``run_requested`` when the Run button is clicked."""
        if self._collection_id is not None:
            self.run_requested.emit(self._collection_id)  # type: ignore[attr-defined]

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
            self._runs_table.setItem(row, 0, QTableWidgetItem(str(started)))
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
