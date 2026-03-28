"""Service layer for collection run history.

All methods are ``@staticmethod`` — no instance state.  UI code should
import from this module, never from the repository directly.
"""

from __future__ import annotations

from typing import Any


class RunHistoryService:
    """Thin bridge between UI and the run history repository."""

    @staticmethod
    def create_run(
        *,
        collection_id: int,
        source: str = "manual",
        iterations: int = 1,
        total_requests: int = 0,
    ) -> dict[str, Any]:
        """Start a new run and return its dict representation."""
        from database.models.runs.run_history_repository import create_run

        return create_run(
            collection_id=collection_id,
            source=source,
            iterations=iterations,
            total_requests=total_requests,
        )

    @staticmethod
    def finish_run(
        run_id: int,
        *,
        status: str = "completed",
        duration_ms: int = 0,
        total_tests: int = 0,
        passed: int = 0,
        failed: int = 0,
        skipped: int = 0,
        avg_response_ms: float = 0.0,
    ) -> None:
        """Finalise a run with aggregate statistics."""
        from database.models.runs.run_history_repository import finish_run

        finish_run(
            run_id,
            status=status,
            duration_ms=duration_ms,
            total_tests=total_tests,
            passed=passed,
            failed=failed,
            skipped=skipped,
            avg_response_ms=avg_response_ms,
        )

    @staticmethod
    def add_result(
        run_id: int,
        *,
        request_name: str = "",
        request_method: str = "GET",
        status_code: int = 0,
        elapsed_ms: float = 0.0,
        test_passed: int = 0,
        test_failed: int = 0,
        error: str | None = None,
        iteration: int = 0,
        test_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Record a per-request result within a run."""
        from database.models.runs.run_history_repository import add_result

        return add_result(
            run_id,
            request_name=request_name,
            request_method=request_method,
            status_code=status_code,
            elapsed_ms=elapsed_ms,
            test_passed=test_passed,
            test_failed=test_failed,
            error=error,
            iteration=iteration,
            test_results=test_results,
        )

    @staticmethod
    def get_runs(collection_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent runs for a collection, newest first."""
        from database.models.runs.run_history_repository import get_runs_for_collection

        return get_runs_for_collection(collection_id, limit=limit)

    @staticmethod
    def get_run_results(run_id: int) -> list[dict[str, Any]]:
        """Return per-request results for a specific run."""
        from database.models.runs.run_history_repository import get_run_results

        return get_run_results(run_id)

    @staticmethod
    def delete_run(run_id: int) -> bool:
        """Delete a single run and its results."""
        from database.models.runs.run_history_repository import delete_run

        return delete_run(run_id)

    @staticmethod
    def delete_runs_for_collection(collection_id: int) -> int:
        """Delete all runs for a collection."""
        from database.models.runs.run_history_repository import delete_runs_for_collection

        return delete_runs_for_collection(collection_id)
