"""Results view widget for the collection runner.

Displays a summary bar and a per-request results table with real-time
updates during the run and a final summary when complete.  Clicking a
result row shows a detail panel with response headers, body, and test
assertions.
"""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.styling.theme import COLOR_DANGER, COLOR_SUCCESS

_RESULT_HEADERS = [
    "Name",
    "Method",
    "Status",
    "Time (ms)",
    "Tests",
    "Result",
]


class RunnerResultsView(QWidget):
    """Real-time results display for a collection run.

    Updated row-by-row via :meth:`add_result` during execution.
    Call :meth:`show_summary` after the run completes.
    Clicking a row shows response details in a panel below the table.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the results view layout."""
        super().__init__(parent)
        self._results: list[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # Summary + export row
        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(4, 4, 4, 4)
        self._summary_label = QLabel()
        self._summary_label.setObjectName("mutedLabel")
        summary_row.addWidget(self._summary_label, 1)
        self._export_btn = QPushButton("Export\u2026")
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._export_results)
        summary_row.addWidget(self._export_btn)
        root.addLayout(summary_row)

        # Splitter: table on top, detail panel below
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Results table
        self._table = QTableWidget(0, len(_RESULT_HEADERS))
        self._table.setHorizontalHeaderLabels(_RESULT_HEADERS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.currentCellChanged.connect(self._on_row_selected)

        header = self._table.horizontalHeader()
        if header:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Name
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Method
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # Status
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # Time
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)  # Tests
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)  # Result
            header.setSectionsMovable(True)
            self._table.setColumnWidth(0, 320)
            self._table.setColumnWidth(1, 70)
            self._table.setColumnWidth(2, 70)
            self._table.setColumnWidth(3, 80)
            self._table.setColumnWidth(4, 70)

        splitter.addWidget(self._table)

        # Detail panel
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setPlaceholderText(
            "Select a row above to see response body, headers, and test results "
            "(\u2705 / \u274c per assertion)."
        )
        splitter.addWidget(self._detail)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

    def clear(self) -> None:
        """Clear the results table, detail panel, and summary."""
        self._results.clear()
        self._table.setRowCount(0)
        self._summary_label.setText("")
        self._detail.clear()
        self._export_btn.setEnabled(False)

    def add_result(self, result: dict[str, Any]) -> None:
        """Append a single request result row to the table."""
        self._results.append(result)
        row = self._table.rowCount()
        self._table.insertRow(row)

        # Name
        name_item = QTableWidgetItem(result.get("name", ""))
        self._table.setItem(row, 0, name_item)

        # Method
        method_item = QTableWidgetItem(result.get("method", ""))
        self._table.setItem(row, 1, method_item)

        # Status
        status = result.get("status_code", 0)
        status_text = "SKIP" if result.get("_skipped") else str(status) if status else "ERR"
        status_item = QTableWidgetItem(status_text)
        self._table.setItem(row, 2, status_item)

        # Time
        elapsed = result.get("elapsed_ms", 0)
        time_text = f"{elapsed:.0f}" if elapsed else "-"
        time_item = QTableWidgetItem(time_text)
        time_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, 3, time_item)

        # Tests
        test_results = result.get("test_results", [])
        if test_results:
            passed = sum(1 for t in test_results if t.get("passed"))
            total = len(test_results)
            tests_item = QTableWidgetItem(f"{passed}/{total}")
            if passed < total:
                tests_item.setForeground(QColor(COLOR_DANGER))  # type: ignore[arg-type]
            else:
                tests_item.setForeground(QColor(COLOR_SUCCESS))  # type: ignore[arg-type]
            self._table.setItem(row, 4, tests_item)
        else:
            self._table.setItem(row, 4, QTableWidgetItem("-"))

        # Result
        error = result.get("error", "")
        result_item = QTableWidgetItem(error if error else "OK")
        self._table.setItem(row, 5, result_item)

    def show_summary(self, results: list[dict[str, Any]]) -> None:
        """Display a final aggregate summary line."""
        req_passed = sum(1 for r in results if not r.get("error") and not r.get("_skipped"))
        req_failed = sum(1 for r in results if r.get("error"))
        req_skipped = sum(1 for r in results if r.get("_skipped"))
        all_tests = [t for r in results for t in r.get("test_results", [])]
        test_passed = sum(1 for t in all_tests if t.get("passed"))
        test_total = len(all_tests)

        parts = [f"Done: {req_passed}/{len(results)} requests OK"]
        if test_total:
            parts.append(f"Tests: {test_passed}/{test_total} passed")
        if req_failed:
            parts.append(f"{req_failed} error(s)")
        if req_skipped:
            parts.append(f"{req_skipped} skipped")
        self._summary_label.setText(" | ".join(parts))
        self._export_btn.setEnabled(bool(results))
        if self._table.rowCount() > 0 and self._table.currentRow() < 0:
            self._table.selectRow(0)

    # -- Detail panel --------------------------------------------------

    def _on_row_selected(self, row: int, _col: int, _prev_row: int, _prev_col: int) -> None:
        """Show details for the selected result row."""
        if row < 0 or row >= len(self._results):
            self._detail.clear()
            return
        result = self._results[row]
        lines: list[str] = []

        name = result.get("name", "")
        method = result.get("method", "")
        status = result.get("status_code", 0)
        lines.append(f"<b>{method} {name}</b>")

        if result.get("_skipped"):
            lines.append("Status: <i>Skipped</i>")
        else:
            lines.append(f"Status: {status}")
            elapsed = result.get("elapsed_ms", 0)
            lines.append(f"Time: {elapsed:.0f} ms")

        # Response headers
        resp_headers = result.get("headers") or []
        if resp_headers:
            lines.append("<br/><b>Response Headers</b>")
            if isinstance(resp_headers, list):
                for hdr in resp_headers:
                    if isinstance(hdr, list | tuple) and len(hdr) >= 2:
                        lines.append(f"  {hdr[0]}: {hdr[1]}")
                    elif isinstance(hdr, str):
                        lines.append(f"  {hdr}")
            elif isinstance(resp_headers, dict):
                for k, v in resp_headers.items():
                    lines.append(f"  {k}: {v}")

        # Response body (truncated)
        body = result.get("body", "")
        if body:
            lines.append("<br/><b>Response Body</b>")
            preview = body[:2000]
            if len(body) > 2000:
                preview += f"\n... ({len(body)} bytes total)"
            lines.append(f"<pre>{preview}</pre>")

        # Error
        error = result.get("error", "")
        if error:
            lines.append(f"<br/><b>Error:</b> {error}")

        # Test assertions — always show the section so users learn the feature exists.
        test_results = result.get("test_results", [])
        lines.append("<br/><b>Test Results</b>")
        if not test_results:
            lines.append("  <i>No post-response tests defined for this request.</i>")
        else:
            for t in test_results:
                icon = "\u2705" if t.get("passed") else "\u274c"
                lines.append(f"  {icon} {t.get('name', 'Unnamed')}")
                if not t.get("passed") and t.get("error"):
                    lines.append(f"     {t['error']}")

        self._detail.setHtml("<br/>".join(lines))

    # -- Export --------------------------------------------------------

    def _export_results(self) -> None:
        """Export the current results to a CSV or JSON file."""
        if not self._results:
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Results",
            "runner_results.csv",
            "CSV Files (*.csv);;JSON Files (*.json)",
        )
        if not path:
            return
        if selected_filter.startswith("JSON") or path.endswith(".json"):
            self._export_json(path)
        else:
            self._export_csv(path)

    def _export_csv(self, path: str) -> None:
        """Write results to a CSV file."""
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Name", "Method", "Status", "Time (ms)", "Tests", "Result"])
        for r in self._results:
            tests = r.get("test_results", [])
            passed = sum(1 for t in tests if t.get("passed"))
            total = len(tests)
            test_str = f"{passed}/{total}" if total else "-"
            status = "SKIP" if r.get("_skipped") else str(r.get("status_code", 0))
            writer.writerow(
                [
                    r.get("name", ""),
                    r.get("method", ""),
                    status,
                    f"{r.get('elapsed_ms', 0):.0f}",
                    test_str,
                    r.get("error", "") or "OK",
                ]
            )
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(output.getvalue())

    def _export_json(self, path: str) -> None:
        """Write results to a JSON file."""
        export = []
        for r in self._results:
            export.append(
                {
                    "name": r.get("name", ""),
                    "method": r.get("method", ""),
                    "status_code": r.get("status_code", 0),
                    "elapsed_ms": r.get("elapsed_ms", 0),
                    "error": r.get("error"),
                    "skipped": bool(r.get("_skipped")),
                    "test_results": r.get("test_results", []),
                }
            )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(export, f, indent=2, default=str)
