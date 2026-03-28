"""Collection runner dialog — batch-execute requests with history.

Orchestrates the config view, results view, background worker, and
run history persistence.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QDialog, QProgressBar, QVBoxLayout, QWidget

from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.run_history_service import RunHistoryService
from ui.dialogs.collection_runner.config import RunnerConfigView
from ui.dialogs.collection_runner.results import RunnerResultsView
from ui.dialogs.collection_runner.worker import RunnerWorker

logger = logging.getLogger(__name__)


class CollectionRunnerDialog(QDialog):
    """Modal dialog that runs all requests in a collection.

    Persists each run to the ``run_history`` table so the folder's
    Runs tab can display past executions.
    """

    def __init__(
        self,
        collection_id: int,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the runner dialog for the given collection."""
        super().__init__(parent)
        self.setWindowTitle("Collection Runner")
        self.setMinimumSize(720, 480)
        self.setModal(True)

        self._collection_id = collection_id
        self._thread: QThread | None = None
        self._worker: RunnerWorker | None = None
        self._run_id: int | None = None
        self._start_time: float = 0.0

        root = QVBoxLayout(self)

        # Config panel
        self._config = RunnerConfigView()
        self._config.run_requested.connect(self._start_run)
        self._config.cancel_requested.connect(self._cancel_run)
        root.addWidget(self._config)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        root.addWidget(self._progress)

        # Results panel
        self._results = RunnerResultsView()
        root.addWidget(self._results, 1)

        # Collect requests
        self._requests = self._collect_requests(collection_id)
        self._config.set_request_count(len(self._requests))
        self._config.load_requests(self._requests)
        self._progress.setMaximum(len(self._requests) or 1)

        # Populate environments
        self._config.load_environments(EnvironmentService.fetch_all())

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

        coll_data = tree.get(str(collection_id))
        if coll_data:
            _walk(coll_data)
        return requests

    def _start_run(self) -> None:
        """Start running requests on a background thread."""
        selected = self._config.selected_indices
        active_requests = [self._requests[i] for i in selected]
        if not active_requests:
            self._config.info_label.setText("No requests selected.")
            return

        self._config.set_running(True)
        self._results.clear()
        self._progress.setValue(0)
        self._config.info_label.setText("Running\u2026")

        iterations = self._config.iterations
        total = len(active_requests) * iterations
        self._progress.setMaximum(total or 1)

        # Create run history record
        run_dict = RunHistoryService.create_run(
            collection_id=self._collection_id,
            source="manual",
            iterations=iterations,
            total_requests=len(active_requests),
        )
        self._run_id = run_dict["id"]
        self._start_time = time.monotonic()

        self._worker = RunnerWorker()
        self._worker.set_requests(active_requests)
        self._worker.set_iteration_data(self._config.iteration_data, iterations)
        self._worker.set_delay(self._config.delay_ms)

        # Load environment variables for the selected environment
        env_id = self._config.environment_id
        env_vars = EnvironmentService.build_variable_map(env_id)
        self._worker.set_environment_vars(env_vars)

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

        # Finalise run as cancelled
        if self._run_id is not None:
            elapsed = int((time.monotonic() - self._start_time) * 1000)
            RunHistoryService.finish_run(self._run_id, status="cancelled", duration_ms=elapsed)
            self._run_id = None

        self._config.info_label.setText("Cancelled")
        self._config.set_running(False)

    def _on_progress(self, index: int, result: dict) -> None:
        """Update the results view and persist the result."""
        self._progress.setValue(index + 1)
        self._results.add_result(result)

        # Persist individual result
        if self._run_id is not None:
            test_results = result.get("test_results", [])
            passed = sum(1 for t in test_results if t.get("passed"))
            failed = len(test_results) - passed
            RunHistoryService.add_result(
                self._run_id,
                request_name=result.get("name", ""),
                request_method=result.get("method", "GET"),
                status_code=result.get("status_code", 0),
                elapsed_ms=result.get("elapsed_ms", 0.0),
                test_passed=passed,
                test_failed=failed,
                error=result.get("error"),
                test_results=test_results or None,
            )

    def _on_finished(self, results: list) -> None:
        """Handle completion of all requests."""
        self._results.show_summary(results)
        self._config.set_running(False)

        # Finalise run history
        if self._run_id is not None:
            elapsed = int((time.monotonic() - self._start_time) * 1000)
            all_tests = [t for r in results for t in r.get("test_results", [])]
            test_passed = sum(1 for t in all_tests if t.get("passed"))
            test_total = len(all_tests)
            test_failed = test_total - test_passed
            skipped = sum(1 for r in results if r.get("_skipped"))
            elapsed_list = [r.get("elapsed_ms", 0) for r in results if r.get("elapsed_ms")]
            avg_ms = sum(elapsed_list) / len(elapsed_list) if elapsed_list else 0.0
            RunHistoryService.finish_run(
                self._run_id,
                status="completed",
                duration_ms=elapsed,
                total_tests=test_total,
                passed=test_passed,
                failed=test_failed,
                skipped=skipped,
                avg_response_ms=avg_ms,
            )
            self._run_id = None

        self._cleanup_thread()

    def _on_error(self, message: str) -> None:
        """Handle a fatal runner error."""
        self._config.info_label.setText(f"Error: {message}")
        self._config.set_running(False)

        if self._run_id is not None:
            elapsed = int((time.monotonic() - self._start_time) * 1000)
            RunHistoryService.finish_run(self._run_id, status="error", duration_ms=elapsed)
            self._run_id = None

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
