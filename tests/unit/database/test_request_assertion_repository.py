"""Repository tests for declarative request assertions."""

from __future__ import annotations

from database.models.collections.collection_repository import (
    create_new_collection,
    create_new_request,
)
from database.models.request_assertions.request_assertion_repository import (
    fetch_assertions_for_request,
    replace_assertions_for_request,
)
from services.assertion_service import AssertionService


class TestRequestAssertionRepository:
    """CRUD for ``request_assertions`` rows."""

    def test_replace_and_fetch_round_trip(self) -> None:
        col = create_new_collection("Assertions")
        req = create_new_request(col.id, "GET", "https://example.com/users", "GET Users")
        saved = replace_assertions_for_request(
            req.id,
            [
                {
                    "subject": "res.status",
                    "operator": "eq",
                    "expected": "200",
                    "enabled": True,
                    "order_index": 0,
                }
            ],
        )
        assert len(saved) == 1
        assert saved[0]["subject"] == "res.status"

        rows = fetch_assertions_for_request(req.id)
        assert len(rows) == 1
        assert rows[0]["expected"] == "200"

    def test_service_builds_declarative_script_entry(self) -> None:
        col = create_new_collection("Compile")
        req = create_new_request(col.id, "GET", "https://example.com/ping", "Ping")
        replace_assertions_for_request(
            req.id,
            [
                {
                    "subject": "res.status",
                    "operator": "eq",
                    "expected": "200",
                    "enabled": True,
                    "order_index": 0,
                }
            ],
        )
        entry = AssertionService.build_declarative_script_entry(req.id, "javascript")
        assert entry is not None
        assert entry["source_name"] == "declarative"
        assert "pm.test" in entry["code"]
