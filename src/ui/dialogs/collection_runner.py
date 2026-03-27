"""Collection runner dialog for batch-executing requests.

Runs all requests in a collection sequentially on a background thread,
showing progress and results in a summary table.  Supports
``pm.execution.setNextRequest()`` / ``skipRequest()`` flow control
and data-driven iteration via CSV/JSON files.
"""

from __future__ import annotations

import csv
import json
import logging
from io import StringIO
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.collection_service import CollectionService
from services.http.http_service import HttpService
from services.script_service import ScriptService
from services.scripting import ScriptEntry
from services.scripting.context import (
    build_pre_request_context,
    build_test_context,
    load_globals,
    save_globals,
)
from services.scripting.engine import ScriptEngine
from ui.styling.icons import phi
from ui.styling.theme import COLOR_DANGER, COLOR_SUCCESS

logger = logging.getLogger(__name__)


def _scripts_enabled() -> bool:
    """Return ``True`` if the global scripting toggle is on."""
    from PySide6.QtCore import QSettings

    from ui.styling.theme_manager import _APP, _ORG

    val = QSettings(_ORG, _APP).value("scripting/enabled", True)
    if isinstance(val, str):
        return val.lower() not in {"0", "false", "no", "off", ""}
    return bool(val)


class _RunnerWorker(QObject):
    """Background worker that runs requests sequentially.

    Supports ``pm.execution.setNextRequest()`` for flow control and
    ``pm.execution.skipRequest()`` to skip individual requests.

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
        self._iteration_data: list[dict[str, Any]] = []
        self._iteration_count: int = 1
        self._cancelled = False

    def set_requests(self, requests: list[dict[str, Any]]) -> None:
        """Set the list of request dicts to execute."""
        self._requests = requests

    def set_iteration_data(
        self,
        data: list[dict[str, Any]],
        count: int = 1,
    ) -> None:
        """Configure data-driven iterations."""
        self._iteration_data = data
        self._iteration_count = max(1, count)

    def cancel(self) -> None:
        """Cancel the runner."""
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        """Execute all requests sequentially with script support."""
        results: list[dict[str, Any]] = []
        request_names = {r.get("name", ""): idx for idx, r in enumerate(self._requests)}
        iterations = self._iteration_count
        if self._iteration_data:
            iterations = max(iterations, len(self._iteration_data))
        progress_idx = 0

        for iteration in range(iterations):
            iter_data: dict[str, Any] = (
                self._iteration_data[iteration] if iteration < len(self._iteration_data) else {}
            )
            i = 0
            while i < len(self._requests):
                if self._cancelled:
                    self.error.emit("Runner cancelled")
                    return
                req = self._requests[i]
                result_dict = self._run_one(req, iteration, iterations, iter_data)
                results.append(result_dict)
                self.progress.emit(progress_idx, result_dict)
                progress_idx += 1

                # 5. Flow control: pm.execution.setNextRequest()
                next_req = result_dict.get("_next_request", _SENTINEL)
                if next_req is not _SENTINEL:
                    if next_req is None:
                        i = len(self._requests)  # stop
                    elif next_req in request_names:
                        i = request_names[next_req]
                    else:
                        i += 1
                else:
                    i += 1

        self.finished.emit(results)

    def _run_one(
        self,
        req: dict[str, Any],
        iteration: int,
        iteration_count: int,
        iter_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Run a single request with scripts and return the result dict."""
        try:
            request_id = req.get("id")
            variables = req.get("_variables", {})

            # 1. Fetch script chain (unless globally disabled).
            pre_scripts: list[ScriptEntry] = []
            test_scripts: list[ScriptEntry] = []
            if request_id is not None and _scripts_enabled():
                pre_scripts, test_scripts = ScriptService.build_script_chain(int(request_id))

            # 2. Run pre-request scripts.
            method: str = req.get("method", "GET")
            url: str = req.get("url", "")
            headers: dict[str, str] = req.get("headers") or {}
            body: str = req.get("body") or ""
            info: dict[str, Any] = {
                "requestName": req.get("name", ""),
                "requestId": str(request_id or ""),
                "iteration": iteration,
                "iterationCount": iteration_count,
            }
            all_console: list[Any] = []
            skip_request = False
            global_vars = load_globals() if (pre_scripts or test_scripts) else {}
            if pre_scripts:
                ctx = build_pre_request_context(
                    method=method,
                    url=url,
                    headers=headers,
                    body=body,
                    variables=variables,
                    environment_vars={},
                    collection_vars={},
                    global_vars=global_vars,
                    info=info,
                    iteration_data=iter_data or None,
                )
                pre_out = ScriptEngine.run_pre_request_scripts(pre_scripts, ctx)
                all_console.extend(pre_out.get("console_logs", []))
                mutations = pre_out.get("request_mutations")
                if mutations:
                    url = mutations.get("url", url)
                    method = mutations.get("method", method)
                    headers = mutations.get("headers", headers)
                    body = mutations.get("body", body)
                if pre_out.get("global_variable_changes"):
                    save_globals(pre_out["global_variable_changes"])
                    global_vars.update(pre_out["global_variable_changes"])
                if pre_out.get("skip_request"):
                    skip_request = True

            # 3. Send HTTP (unless skipped by pre-request script).
            if skip_request:
                result_dict: dict[str, Any] = {
                    "name": req.get("name", ""),
                    "status_code": 0,
                    "elapsed_ms": 0,
                    "body": "",
                    "headers": [],
                    "_skipped": True,
                }
            else:
                headers_str: str | None = (
                    "\n".join(f"{k}: {v}" for k, v in headers.items()) if headers else None
                )
                result = HttpService.send_request(
                    method=method,
                    url=url,
                    headers=headers_str,
                    body=body or None,
                )
                result_dict = dict(result)
                result_dict["name"] = req.get("name", "")

            # 4. Run test scripts.
            all_test_results: list[Any] = []
            next_request: Any = _SENTINEL
            if test_scripts and not skip_request:
                test_ctx = build_test_context(
                    request_data={
                        "url": url,
                        "method": method,
                        "headers": headers,
                        "body": body,
                    },
                    response_data=result_dict,
                    variables=variables,
                    environment_vars={},
                    collection_vars={},
                    global_vars=global_vars,
                    info=info,
                    iteration_data=iter_data or None,
                )
                test_out = ScriptEngine.run_test_scripts(test_scripts, test_ctx)
                all_test_results.extend(test_out.get("test_results", []))
                all_console.extend(test_out.get("console_logs", []))
                if test_out.get("global_variable_changes"):
                    save_globals(test_out["global_variable_changes"])
                if "next_request" in test_out:
                    next_request = test_out.get("next_request")

            result_dict["test_results"] = all_test_results
            result_dict["console_logs"] = all_console
            if next_request is not _SENTINEL:
                result_dict["_next_request"] = next_request
            return result_dict
        except Exception as exc:
            return {
                "name": req.get("name", ""),
                "error": str(exc),
                "status_code": 0,
                "elapsed_ms": 0,
                "test_results": [],
            }


# Sentinel to distinguish "setNextRequest not called" from "set to None"
_SENTINEL = object()


def _parse_data_file(path: Path) -> list[dict[str, Any]]:
    """Parse a CSV or JSON file into a list of row dicts."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, list):
            return [dict(row) for row in data if isinstance(row, dict)]
        return []
    # CSV
    reader = csv.DictReader(StringIO(text))
    return [dict(row) for row in reader]


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
        self._iteration_data: list[dict[str, Any]] = []

        root = QVBoxLayout(self)

        # Header
        self._info_label = QLabel("Preparing\u2026")
        root.addWidget(self._info_label)

        # Data file / iterations row
        data_row = QHBoxLayout()
        self._data_file_label = QLabel("No data file")
        data_row.addWidget(self._data_file_label, 1)
        data_btn = QPushButton("Data File\u2026")
        data_btn.setIcon(phi("file-csv"))
        data_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        data_btn.clicked.connect(self._pick_data_file)
        data_row.addWidget(data_btn)
        data_row.addWidget(QLabel("Iterations:"))
        self._iter_spin = QSpinBox()
        self._iter_spin.setRange(1, 10_000)
        self._iter_spin.setValue(1)
        data_row.addWidget(self._iter_spin)
        root.addLayout(data_row)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        root.addWidget(self._progress)

        # Results table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Name", "Status", "Time (ms)", "Tests", "Result"],
        )
        header = self._table.horizontalHeader()
        if header:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self._table, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._run_btn = QPushButton("Run")
        self._run_btn.setIcon(phi("play"))
        self._run_btn.setObjectName("primaryButton")
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.clicked.connect(self._start_run)
        btn_row.addWidget(self._run_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setIcon(phi("stop"))
        self._cancel_btn.setObjectName("dangerButton")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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

    def _pick_data_file(self) -> None:
        """Open a file dialog to choose a CSV or JSON data file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Data File",
            "",
            "Data Files (*.csv *.json);;All Files (*)",
        )
        if not path:
            return
        try:
            self._iteration_data = _parse_data_file(Path(path))
            name = Path(path).name
            self._data_file_label.setText(f"{name} ({len(self._iteration_data)} rows)")
            self._iter_spin.setValue(len(self._iteration_data))
        except Exception as exc:
            self._data_file_label.setText(f"Error: {exc}")
            self._iteration_data = []

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

        iterations = self._iter_spin.value()
        total = len(self._requests) * iterations
        self._progress.setMaximum(total or 1)

        self._worker = _RunnerWorker()
        self._worker.set_requests(self._requests)
        self._worker.set_iteration_data(self._iteration_data, iterations)

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
        if result.get("_skipped"):
            status_item = QTableWidgetItem("SKIP")
        else:
            status_item = QTableWidgetItem(str(status) if status else "ERR")
        self._table.setItem(row, 1, status_item)

        elapsed = result.get("elapsed_ms", 0)
        time_item = QTableWidgetItem(f"{elapsed:.0f}" if elapsed else "-")
        self._table.setItem(row, 2, time_item)

        # Tests column.
        test_results = result.get("test_results", [])
        if test_results:
            passed = sum(1 for t in test_results if t.get("passed"))
            total = len(test_results)
            tests_item = QTableWidgetItem(f"{passed}/{total}")
            if passed < total:
                tests_item.setForeground(
                    QColor(COLOR_DANGER),  # type: ignore[arg-type]
                )
            else:
                tests_item.setForeground(
                    QColor(COLOR_SUCCESS),  # type: ignore[arg-type]
                )
            self._table.setItem(row, 3, tests_item)
        else:
            self._table.setItem(row, 3, QTableWidgetItem("-"))

        error = result.get("error", "")
        result_item = QTableWidgetItem(error if error else "OK")
        self._table.setItem(row, 4, result_item)

    def _on_finished(self, results: list) -> None:
        """Handle completion of all requests."""
        req_passed = sum(1 for r in results if not r.get("error"))
        req_failed = len(results) - req_passed
        # Aggregate test verdicts.
        all_tests = [t for r in results for t in r.get("test_results", [])]
        test_passed = sum(1 for t in all_tests if t.get("passed"))
        test_total = len(all_tests)
        summary = f"Done: {req_passed}/{len(results)} requests OK"
        if test_total:
            summary += f" | Tests: {test_passed}/{test_total} passed"
        if req_failed:
            summary += f" | {req_failed} error(s)"
        self._info_label.setText(summary)
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
