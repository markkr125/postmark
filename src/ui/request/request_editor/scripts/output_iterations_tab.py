"""Iterations matrix tab for data-driven inline script runs."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styling.icons import phi
from ui.styling.theme import COLOR_DANGER, COLOR_SUCCESS, COLOR_TEXT_MUTED

_PASS_MARK = "\u2713"
_FAIL_MARK = "\u2716"
_SKIP_MARK = "\u2014"
_RUNTIME_ERROR = "(runtime error)"


class ScriptOutputIterationsTab(QWidget):
    """Matrix of iteration rows vs test columns with drill-down and re-run."""

    iteration_selected = Signal(int)
    rerun_failed_requested = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the matrix table and re-run toolbar."""
        super().__init__(parent)
        self._results: list[dict[str, Any]] = []
        self._test_names: list[str] = []
        self._source_data: list[dict[str, Any]] = []
        self._build_ui()

    def _build_ui(self) -> None:
        """Lay out toolbar and matrix table."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(4)

        toolbar = QHBoxLayout()
        self._summary = QLabel("Run with a data file to see iteration results.")
        self._summary.setObjectName("mutedLabel")
        toolbar.addWidget(self._summary, 1)

        self._rerun_failed_btn = QPushButton("Re-run failed only")
        self._rerun_failed_btn.setIcon(phi("arrow-clockwise"))
        self._rerun_failed_btn.setObjectName("outlineButton")
        self._rerun_failed_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rerun_failed_btn.setEnabled(False)
        self._rerun_failed_btn.clicked.connect(self._on_rerun_failed)
        toolbar.addWidget(self._rerun_failed_btn)
        root.addLayout(toolbar)

        self._table = QTableWidget(0, 0)
        self._table.setObjectName("scriptOutputIterationsTable")
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(True)
        self._table.cellClicked.connect(self._on_cell_clicked)
        root.addWidget(self._table, 1)

    def set_source_data(self, data: list[dict[str, Any]]) -> None:
        """Remember the data rows used for the current run (for re-run failed)."""
        self._source_data = list(data)

    def begin_run(self, *, iteration_count: int, test_names: list[str] | None = None) -> None:
        """Reset the matrix for a new multi-iteration run."""
        self._results = [{} for _ in range(iteration_count)]
        self._test_names = list(test_names or [])
        self._table.setColumnCount(len(self._test_names))
        self._table.setHorizontalHeaderLabels(self._test_names)
        self._table.setRowCount(iteration_count)
        for row in range(iteration_count):
            self._table.setVerticalHeaderItem(row, QTableWidgetItem(str(row + 1)))
            for col in range(len(self._test_names)):
                self._set_cell(row, col, _SKIP_MARK, COLOR_TEXT_MUTED)
        self._summary.setText(f"Running {iteration_count} iteration(s)…")
        self._rerun_failed_btn.setEnabled(False)

    def update_iteration(self, index: int, output: dict[str, Any]) -> None:
        """Merge one iteration result into the matrix."""
        while len(self._results) <= index:
            self._results.append({})
        self._results[index] = dict(output)

        test_results = output.get("test_results", [])
        names = [str(r.get("name", "")) for r in test_results if r.get("name") != _RUNTIME_ERROR]
        for name in names:
            if name and name not in self._test_names:
                self._test_names.append(name)

        if self._table.columnCount() != len(self._test_names):
            self._table.setColumnCount(len(self._test_names))
            self._table.setHorizontalHeaderLabels(self._test_names)

        if self._table.rowCount() <= index:
            self._table.setRowCount(index + 1)
            self._table.setVerticalHeaderItem(index, QTableWidgetItem(str(index + 1)))

        for col, name in enumerate(self._test_names):
            cell = self._lookup_test(test_results, name)
            if cell is None:
                self._set_cell(index, col, _SKIP_MARK, COLOR_TEXT_MUTED)
            elif cell.get("passed"):
                self._set_cell(index, col, _PASS_MARK, COLOR_SUCCESS)
            else:
                self._set_cell(index, col, _FAIL_MARK, COLOR_DANGER)

        runtime = [r for r in test_results if r.get("name") == _RUNTIME_ERROR]
        if runtime and not names:
            if self._test_names != [_RUNTIME_ERROR]:
                self._test_names = [_RUNTIME_ERROR]
                self._table.setColumnCount(1)
                self._table.setHorizontalHeaderLabels(self._test_names)
            self._set_cell(index, 0, _FAIL_MARK, COLOR_DANGER)

        self._refresh_summary()

    def iteration_result(self, index: int) -> dict[str, Any] | None:
        """Return stored output for *index*, or ``None`` if missing."""
        if 0 <= index < len(self._results) and self._results[index]:
            return self._results[index]
        return None

    def failed_row_indices(self) -> list[int]:
        """Return iteration indices where any test failed."""
        failed: list[int] = []
        for idx, output in enumerate(self._results):
            if not output:
                continue
            tests = output.get("test_results", [])
            if any(not r.get("passed") for r in tests):
                failed.append(idx)
        return failed

    def clear(self) -> None:
        """Reset to the idle empty state."""
        self._results = []
        self._test_names = []
        self._source_data = []
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._summary.setText("Run with a data file to see iteration results.")
        self._rerun_failed_btn.setEnabled(False)

    def _lookup_test(
        self,
        test_results: list[dict[str, Any]],
        name: str,
    ) -> dict[str, Any] | None:
        for r in test_results:
            if str(r.get("name", "")) == name:
                return r
        return None

    def _set_cell(self, row: int, col: int, text: str, color: str) -> None:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(color))
        self._table.setItem(row, col, item)

    def _refresh_summary(self) -> None:
        done = sum(1 for r in self._results if r)
        total = max(len(self._results), self._table.rowCount())
        if done < total:
            self._summary.setText(f"Completed {done}/{total} iteration(s)…")
            return
        passed_iters = sum(
            1
            for r in self._results
            if r and all(t.get("passed") for t in r.get("test_results", []))
        )
        self._summary.setText(f"{passed_iters}/{total} iteration(s) passed all tests")
        self._rerun_failed_btn.setEnabled(bool(self.failed_row_indices()))

    def _on_cell_clicked(self, row: int, _col: int) -> None:
        if row < len(self._results) and self._results[row]:
            self.iteration_selected.emit(row)

    def _on_rerun_failed(self) -> None:
        indices = self.failed_row_indices()
        if not indices or not self._source_data:
            return
        filtered = [self._source_data[i] for i in indices if i < len(self._source_data)]
        if filtered:
            self.rerun_failed_requested.emit(filtered)
