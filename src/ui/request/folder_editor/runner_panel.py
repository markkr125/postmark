"""Inline collection runner panel for the folder editor Runs tab.

Orchestrates :class:`~ui.dialogs.collection_runner.config.RunnerConfigView`,
:class:`~ui.dialogs.collection_runner.results.RunnerResultsView`, and
:class:`~ui.dialogs.collection_runner.worker.RunnerWorker` without a modal
dialog shell.
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QProgressBar, QVBoxLayout, QWidget

from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.run_history_service import RunHistoryService
from ui.dialogs.collection_runner.config import RunnerConfigView
from ui.dialogs.collection_runner.results import RunnerResultsView
from ui.dialogs.collection_runner.worker import RunnerWorker


class _RunnerPanel(QWidget):
    """Background-thread collection runner embedded in the folder editor.

    Persists each run to ``run_history`` and emits :py:attr:`run_finished`
    when a run reaches a terminal state (completed, cancelled, or error).
    """

    run_finished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build config, progress, and results widgets with idle state."""
        super().__init__(parent)

        self._collection_id: int | None = None
        self._thread: QThread | None = None
        self._worker: RunnerWorker | None = None
        self._run_id: int | None = None
        self._start_time: float = 0.0
        self._requests: list[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._config = RunnerConfigView()
        self._config.run_requested.connect(self._start_run)
        self._config.cancel_requested.connect(self._cancel_run)
        root.addWidget(self._config)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        root.addWidget(self._progress)

        self._results = RunnerResultsView()
        root.addWidget(self._results, 1)

        self._progress.setMaximum(1)

    def load_collection(self, collection_id: int) -> None:
        """Load requests and environments for *collection_id*."""
        self._collection_id = collection_id
        self._requests = self._collect_requests(collection_id)
        self._config.load_requests(self._requests)
        self._config.set_request_count(len(self._requests))
        self._progress.setMaximum(len(self._requests) or 1)
        self._progress.setValue(0)
        self._config.load_environments(EnvironmentService.fetch_all())
        self._results.clear()
        self._config.set_running(False)

    def clear(self) -> None:
        """Reset the panel when no folder is loaded."""
        finish = "cancelled" if self._run_id is not None else None
        self._shutdown_thread(finish_run_status=finish)
        self._collection_id = None
        self._requests = []
        self._config.set_request_count(0)
        self._config.load_requests([])
        self._progress.setMaximum(1)
        self._progress.setValue(0)
        self._results.clear()
        self._config.set_running(False)
        self._config.info_label.setText("")

    def shutdown(self) -> None:
        """Cancel any in-flight run before the host widget is destroyed."""
        finish = "cancelled" if self._run_id is not None else None
        self._shutdown_thread(finish_run_status=finish)

    @staticmethod
    def _collect_requests(collection_id: int) -> list[dict[str, Any]]:
        """Gather all requests under *collection_id* (depth-first, any nesting).

        ``CollectionService.fetch_all()`` only keys **root** collections at the
        top level; nested folders must be found by walking each root subtree.
        """
        tree = CollectionService.fetch_all()
        requests: list[dict[str, Any]] = []

        def _walk(node: dict[str, Any]) -> None:
            if node.get("type") == "request":
                requests.append(node)
                return
            for child in (node.get("children") or {}).values():
                _walk(child)

        def _find(node: dict[str, Any]) -> dict[str, Any] | None:
            if node.get("type") != "request" and node.get("id") == collection_id:
                return node
            for child in (node.get("children") or {}).values():
                hit = _find(child)
                if hit is not None:
                    return hit
            return None

        for root in tree.values():
            target = _find(root)
            if target is not None:
                _walk(target)
                break
        return requests

    def _start_run(self) -> None:
        """Start running requests on a background thread."""
        if self._collection_id is None:
            self._config.info_label.setText("No collection loaded.")
            return

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

        env_id = self._config.environment_id
        env_vars = EnvironmentService.build_variable_map(env_id)
        self._worker.set_environment_vars(env_vars)
        env_name = ""
        if env_id is not None:
            env = EnvironmentService.get_environment(env_id)
            if env is not None:
                env_name = str(env.name or "")
        self._worker.set_environment_name(env_name)

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

        if self._run_id is not None:
            elapsed = int((time.monotonic() - self._start_time) * 1000)
            RunHistoryService.finish_run(self._run_id, status="cancelled", duration_ms=elapsed)
            self._run_id = None

        self._config.info_label.setText("Cancelled")
        self._config.set_running(False)
        self.run_finished.emit()

    def _on_progress(self, index: int, result: dict) -> None:
        """Update the results view and persist the result."""
        self._progress.setValue(index + 1)
        self._results.add_result(result)

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
        ok = sum(1 for r in results if not r.get("error") and not r.get("_skipped"))
        errs = sum(1 for r in results if r.get("error"))
        self._config.info_label.setText(f"Done: {ok}/{len(results)} OK | {errs} error(s)")
        self._config.set_running(False)

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
        self.run_finished.emit()

    def _on_error(self, message: str) -> None:
        """Handle a fatal runner error."""
        self._config.info_label.setText(f"Error: {message}")
        self._config.set_running(False)

        if self._run_id is not None:
            elapsed = int((time.monotonic() - self._start_time) * 1000)
            RunHistoryService.finish_run(self._run_id, status="error", duration_ms=elapsed)
            self._run_id = None

        self._cleanup_thread()
        self.run_finished.emit()

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

    def _shutdown_thread(self, finish_run_status: str | None) -> None:
        """Tear down the worker thread, optionally finalising an active run."""
        if self._worker:
            self._worker.cancel()
        self._cleanup_thread()

        if finish_run_status is not None and self._run_id is not None:
            elapsed = int((time.monotonic() - self._start_time) * 1000)
            RunHistoryService.finish_run(
                self._run_id, status=finish_run_status, duration_ms=elapsed
            )
            self._run_id = None
