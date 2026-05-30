"""Unit tests for the run history repository CRUD layer."""

from __future__ import annotations

from database.models.runs.run_history_repository import (
    add_result,
    create_run,
    delete_run,
    delete_runs_for_collection,
    finish_run,
    get_run_results,
    get_runs_for_collection,
)


class TestCreateRun:
    """Tests for create_run."""

    def test_creates_and_returns_dict(self) -> None:
        """create_run returns a dict with an auto-generated ID."""
        run = create_run(collection_id=1, source="manual", total_requests=5)
        assert run["id"] is not None
        assert run["collection_id"] == 1
        assert run["source"] == "manual"
        assert run["status"] == "running"
        assert run["total_requests"] == 5

    def test_defaults(self) -> None:
        """Default values are applied for optional fields."""
        run = create_run(collection_id=2)
        assert run["iterations"] == 1
        assert run["passed"] == 0
        assert run["failed"] == 0
        assert run["avg_response_ms"] == 0.0


class TestFinishRun:
    """Tests for finish_run."""

    def test_finalises_run(self) -> None:
        """finish_run updates status and statistics."""
        run = create_run(collection_id=1)
        finish_run(
            run["id"],
            status="completed",
            duration_ms=1234,
            total_tests=10,
            passed=8,
            failed=2,
            avg_response_ms=45.5,
        )
        runs = get_runs_for_collection(1)
        finished = runs[0]
        assert finished["status"] == "completed"
        assert finished["duration_ms"] == 1234
        assert finished["passed"] == 8
        assert finished["failed"] == 2

    def test_finish_nonexistent_run(self) -> None:
        """finish_run silently returns for a missing run ID."""
        finish_run(999999, status="completed")

    def test_finish_with_skipped(self) -> None:
        """finish_run records the skipped count."""
        run = create_run(collection_id=1)
        finish_run(run["id"], status="completed", skipped=3)
        runs = get_runs_for_collection(1)
        assert runs[0]["skipped"] == 3


class TestAddResult:
    """Tests for add_result."""

    def test_adds_result_to_run(self) -> None:
        """add_result persists a per-request result row."""
        run = create_run(collection_id=1)
        result = add_result(
            run["id"],
            request_name="Get Users",
            request_method="GET",
            status_code=200,
            elapsed_ms=42.0,
            test_passed=3,
            test_failed=1,
        )
        assert result["run_id"] == run["id"]
        assert result["request_name"] == "Get Users"
        assert result["status_code"] == 200
        assert result["test_passed"] == 3

    def test_stores_test_results_json(self) -> None:
        """Test results list is stored as JSON."""
        run = create_run(collection_id=1)
        tests = [{"name": "status is 200", "passed": True}]
        result = add_result(run["id"], test_results=tests)
        assert result["test_results"] == tests


class TestGetRunsForCollection:
    """Tests for get_runs_for_collection."""

    def test_returns_newest_first(self) -> None:
        """Runs are returned in reverse chronological order."""
        create_run(collection_id=1, source="first")
        create_run(collection_id=1, source="second")
        runs = get_runs_for_collection(1)
        assert len(runs) == 2
        assert runs[0]["source"] == "second"
        assert runs[1]["source"] == "first"

    def test_empty_collection(self) -> None:
        """Returns empty list for a collection with no runs."""
        runs = get_runs_for_collection(999)
        assert runs == []

    def test_limit(self) -> None:
        """Respects the limit parameter."""
        for _ in range(5):
            create_run(collection_id=1)
        runs = get_runs_for_collection(1, limit=3)
        assert len(runs) == 3


class TestGetRunResults:
    """Tests for get_run_results."""

    def test_returns_results_in_order(self) -> None:
        """Results are returned in insertion order."""
        run = create_run(collection_id=1)
        add_result(run["id"], request_name="A")
        add_result(run["id"], request_name="B")
        results = get_run_results(run["id"])
        assert len(results) == 2
        assert results[0]["request_name"] == "A"
        assert results[1]["request_name"] == "B"


class TestDeleteRun:
    """Tests for delete_run."""

    def test_deletes_existing_run(self) -> None:
        """delete_run removes the run and returns True."""
        run = create_run(collection_id=1)
        add_result(run["id"], request_name="A")
        assert delete_run(run["id"]) is True
        assert get_run_results(run["id"]) == []

    def test_returns_false_for_missing(self) -> None:
        """delete_run returns False for a nonexistent ID."""
        assert delete_run(999999) is False


class TestDeleteRunsForCollection:
    """Tests for delete_runs_for_collection."""

    def test_deletes_all_runs(self) -> None:
        """Deletes all runs for the given collection."""
        create_run(collection_id=1)
        create_run(collection_id=1)
        create_run(collection_id=2)
        count = delete_runs_for_collection(1)
        assert count == 2
        assert get_runs_for_collection(1) == []
        assert len(get_runs_for_collection(2)) == 1
