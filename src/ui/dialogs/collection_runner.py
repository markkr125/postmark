"""Collection runner dialog for batch-executing requests.

Runs all requests in a collection sequentially on a background thread,
showing progress and results in a summary table.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.collection_service import CollectionService
from services.http_service import HttpService
from ui.theme import COLOR_ACCENT, COLOR_DANGER, COLOR_TEXT, COLOR_WHITE

logger = logging.getLogger(__name__)


class _RunnerWorker(QObject):
    """Background worker that runs requests sequentially.

    Signals:
        progress(int, dict): Emitted after each request with
            ``(index, result_dict)``.
        finished(list): Emitted when all requests are done.
        error(str): Emitted on fatal error.
    """

    progress = Signal(int, dict)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self) -> None:
        """Initialise with an empty request list."""
        super().__init__()
        self._requests: list[dict[str, Any]] = []
        self._cancelled = False

    def set_requests(self, requests: list[dict[str, Any]]) -> None:
        """Set the list of request dicts to execute."""
        self._requests = requests

    def cancel(self) -> None:
        """Cancel the runner."""
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        """Execute all requests sequentially."""
        results: list[dict[str, Any]] = []
        for i, req in enumerate(self._requests):
            if self._cancelled:
                self.error.emit("Runner cancelled")
                return
            try:
                result = HttpService.send_request(
                    method=req.get("method", "GET"),
                    url=req.get("url", ""),
                    headers=req.get("headers"),
                    body=req.get("body"),
                )
                result_dict = dict(result)
                result_dict["name"] = req.get("name", "")
                results.append(result_dict)
                self.progress.emit(i, result_dict)
            except Exception as exc:
                err_result: dict[str, Any] = {
                    "name": req.get("name", ""),
                    "error": str(exc),
                    "status_code": 0,
                    "elapsed_ms": 0,
                }
                results.append(err_result)
                self.progress.emit(i, err_result)
        self.finished.emit(results)


class CollectionRunnerDialog(QDialog):
    """Modal dialog that runs all requests in a collection."""

    def __init__(
        self,
        collection_id: int,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the runner dialog for the given collection."""
        super().__init__(parent)
        self.setWindowTitle("Collection Runner")
        self.setMinimumSize(650, 400)
        self.setModal(True)

        self._collection_id = collection_id
        self._thread: QThread | None = None
        self._worker: _RunnerWorker | None = None

        root = QVBoxLayout(self)

        # Header
        self._info_label = QLabel("Preparing\u2026")
        self._info_label.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT}; padding: 4px;")
        root.addWidget(self._info_label)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(f"QProgressBar::chunk {{ background: {COLOR_ACCENT}; }}")
        root.addWidget(self._progress)

        # Results table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Name", "Status", "Time (ms)", "Result"])
        header = self._table.horizontalHeader()
        if header:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self._table, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._run_btn = QPushButton("Run")
        self._run_btn.setStyleSheet(
            f"background: {COLOR_ACCENT}; color: {COLOR_WHITE}; border: none;"
            f" padding: 6px 20px; font-weight: bold; border-radius: 3px;"
        )
        self._run_btn.clicked.connect(self._start_run)
        btn_row.addWidget(self._run_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setStyleSheet(
            f"background: {COLOR_DANGER}; color: {COLOR_WHITE}; border: none;"
            f" padding: 6px 20px; font-weight: bold; border-radius: 3px;"
        )
        self._cancel_btn.clicked.connect(self._cancel_run)
        self._cancel_btn.setEnabled(False)
        btn_row.addWidget(self._cancel_btn)
        root.addLayout(btn_row)

        # Collect requests
        self._requests = self._collect_requests(collection_id)
        self._info_label.setText(f"{len(self._requests)} request(s) to run")
        self._progress.setMaximum(len(self._requests) or 1)

    @staticmethod
    def _collect_requests(collection_id: int) -> list[dict[str, Any]]:
        """Gather all requests in the collection tree (depth-first)."""
        tree = CollectionService.fetch_all()
        requests: list[dict[str, Any]] = []

        def _walk(node: dict[str, Any]) -> None:
            if node.get("type") == "request":
                requests.append(node)
                return
            for child in (node.get("children") or {}).values():
                _walk(child)

        # Find the target collection
        coll_data = tree.get(str(collection_id))
        if coll_data:
            _walk(coll_data)
        return requests

    def _start_run(self) -> None:
        """Start running requests on a background thread."""
        if not self._requests:
            self._info_label.setText("No requests to run.")
            return

        self._run_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._table.setRowCount(0)
        self._progress.setValue(0)
        self._info_label.setText("Running\u2026")

        self._worker = _RunnerWorker()
        self._worker.set_requests(self._requests)

        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._thread.start()

    def _cancel_run(self) -> None:
        """Cancel the running requests."""
        if self._worker:
            self._worker.cancel()
        self._cleanup_thread()
        self._info_label.setText("Cancelled")
        self._run_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)

    def _on_progress(self, index: int, result: dict) -> None:
        """Update the table with a completed request result."""
        self._progress.setValue(index + 1)
        row = self._table.rowCount()
        self._table.insertRow(row)

        name_item = QTableWidgetItem(result.get("name", ""))
        self._table.setItem(row, 0, name_item)

        status = result.get("status_code", 0)
        status_item = QTableWidgetItem(str(status) if status else "ERR")
        self._table.setItem(row, 1, status_item)

        elapsed = result.get("elapsed_ms", 0)
        time_item = QTableWidgetItem(f"{elapsed:.0f}" if elapsed else "-")
        self._table.setItem(row, 2, time_item)

        error = result.get("error", "")
        result_item = QTableWidgetItem(error if error else "OK")
        self._table.setItem(row, 3, result_item)

    def _on_finished(self, results: list) -> None:
        """Handle completion of all requests."""
        passed = sum(1 for r in results if not r.get("error"))
        failed = len(results) - passed
        self._info_label.setText(f"Done: {passed} passed, {failed} failed out of {len(results)}")
        self._run_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._cleanup_thread()

    def _on_error(self, message: str) -> None:
        """Handle a fatal runner error."""
        self._info_label.setText(f"Error: {message}")
        self._run_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._cleanup_thread()

    def _cleanup_thread(self) -> None:
        """Stop and delete the runner thread."""
        if self._thread is not None:
            if self._thread.isRunning():
                self._thread.quit()
                self._thread.wait(3000)
            self._thread.deleteLater()
            self._thread = None
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
