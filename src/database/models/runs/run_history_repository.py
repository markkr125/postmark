"""Repository layer — CRUD functions for collection run history.

UI code must **not** import this directly — use the service layer instead.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from database.database import get_session

from .model.run_history_model import RunHistoryModel
from .model.run_result_model import RunResultModel

logger = logging.getLogger(__name__)


def create_run(
    *,
    collection_id: int,
    source: str = "manual",
    iterations: int = 1,
    total_requests: int = 0,
) -> dict[str, Any]:
    """Create a new run history record and return it as a dict."""
    with get_session() as session:
        run = RunHistoryModel(
            collection_id=collection_id,
            source=source,
            iterations=iterations,
            total_requests=total_requests,
            status="running",
        )
        session.add(run)
        session.flush()
        session.refresh(run)
        return _run_to_dict(run)


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
    with get_session() as session:
        run = session.get(RunHistoryModel, run_id)
        if run is None:
            logger.warning("Run %d not found for finish", run_id)
            return
        run.status = status
        run.finished_at = datetime.now(tz=UTC)
        run.duration_ms = duration_ms
        run.total_tests = total_tests
        run.passed = passed
        run.failed = failed
        run.skipped = skipped
        run.avg_response_ms = avg_response_ms


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
    """Add a per-request result row to a run."""
    with get_session() as session:
        result = RunResultModel(
            run_id=run_id,
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
        session.add(result)
        session.flush()
        session.refresh(result)
        return _result_to_dict(result)


def get_runs_for_collection(
    collection_id: int,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return recent runs for a collection, newest first."""
    with get_session() as session:
        stmt = (
            select(RunHistoryModel)
            .where(RunHistoryModel.collection_id == collection_id)
            .order_by(RunHistoryModel.id.desc())
            .limit(limit)
        )
        rows = list(session.execute(stmt).scalars().all())
        return [_run_to_dict(r) for r in rows]


def get_run_results(run_id: int) -> list[dict[str, Any]]:
    """Return all per-request results for a specific run."""
    with get_session() as session:
        stmt = (
            select(RunResultModel)
            .where(RunResultModel.run_id == run_id)
            .order_by(RunResultModel.id.asc())
        )
        rows = list(session.execute(stmt).scalars().all())
        return [_result_to_dict(r) for r in rows]


def delete_run(run_id: int) -> bool:
    """Delete a run and its results.  Returns ``True`` if found."""
    with get_session() as session:
        run = session.get(RunHistoryModel, run_id)
        if run is None:
            return False
        session.delete(run)
        return True


def delete_runs_for_collection(collection_id: int) -> int:
    """Delete all runs for a collection.  Returns the count deleted."""
    with get_session() as session:
        stmt = select(RunHistoryModel).where(RunHistoryModel.collection_id == collection_id)
        rows = list(session.execute(stmt).scalars().all())
        for row in rows:
            session.delete(row)
        return len(rows)


# -- Internal helpers --------------------------------------------------


def _run_to_dict(run: RunHistoryModel) -> dict[str, Any]:
    """Convert a ``RunHistoryModel`` to a plain dict."""
    return {
        "id": run.id,
        "collection_id": run.collection_id,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "source": run.source,
        "duration_ms": run.duration_ms,
        "total_requests": run.total_requests,
        "total_tests": run.total_tests,
        "passed": run.passed,
        "failed": run.failed,
        "skipped": run.skipped,
        "avg_response_ms": run.avg_response_ms,
        "status": run.status,
        "iterations": run.iterations,
    }


def _result_to_dict(result: RunResultModel) -> dict[str, Any]:
    """Convert a ``RunResultModel`` to a plain dict."""
    return {
        "id": result.id,
        "run_id": result.run_id,
        "request_name": result.request_name,
        "request_method": result.request_method,
        "status_code": result.status_code,
        "elapsed_ms": result.elapsed_ms,
        "test_passed": result.test_passed,
        "test_failed": result.test_failed,
        "error": result.error,
        "iteration": result.iteration,
        "test_results": result.test_results,
    }
