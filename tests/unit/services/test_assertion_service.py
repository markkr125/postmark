"""Unit tests for :class:`AssertionService`."""

from __future__ import annotations

from database.models.collections.collection_repository import (
    create_new_collection,
    create_new_request,
)
from services.assertion_service import AssertionDict, AssertionService


class TestAssertionServiceFetchSave:
    """Service-level CRUD and normalisation."""

    def test_fetch_empty_for_new_request(self) -> None:
        col = create_new_collection("Svc")
        req = create_new_request(col.id, "GET", "https://example.com", "R")
        assert AssertionService.fetch_for_request(req.id) == []

    def test_save_normalises_invalid_operator_to_eq(self) -> None:
        col = create_new_collection("Norm")
        req = create_new_request(col.id, "GET", "https://example.com", "R")
        rows = AssertionService.save_for_request(
            req.id,
            [
                {
                    "subject": "res.status",
                    "operator": "not-a-real-op",
                    "expected": "200",
                    "enabled": True,
                    "order_index": 0,
                }
            ],
        )
        assert rows[0]["operator"] == "eq"

    def test_save_preserves_order_index(self) -> None:
        col = create_new_collection("Order")
        req = create_new_request(col.id, "GET", "https://example.com", "R")
        saved = AssertionService.save_for_request(
            req.id,
            [
                AssertionDict(
                    subject="res.status",
                    operator="eq",
                    expected="200",
                    enabled=True,
                    order_index=2,
                ),
            ],
        )
        assert saved[0]["order_index"] == 2

    def test_delete_for_request_clears_rows(self) -> None:
        col = create_new_collection("Del")
        req = create_new_request(col.id, "GET", "https://example.com", "R")
        AssertionService.save_for_request(
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
        AssertionService.delete_for_request(req.id)
        assert AssertionService.fetch_for_request(req.id) == []


class TestAssertionServiceCompilerBridge:
    """Declarative script entry generation."""

    def test_build_declarative_script_entry_none_when_disabled_only(self) -> None:
        col = create_new_collection("Off")
        req = create_new_request(col.id, "GET", "https://example.com", "R")
        AssertionService.save_for_request(
            req.id,
            [
                {
                    "subject": "res.status",
                    "operator": "eq",
                    "expected": "200",
                    "enabled": False,
                    "order_index": 0,
                }
            ],
        )
        assert AssertionService.build_declarative_script_entry(req.id, "javascript") is None

    def test_build_declarative_script_entry_python(self) -> None:
        col = create_new_collection("Py")
        req = create_new_request(col.id, "GET", "https://example.com", "R")
        AssertionService.save_for_request(
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
        entry = AssertionService.build_declarative_script_entry(req.id, "python")
        assert entry is not None
        assert entry["language"] == "python"
        assert "pm.test" in entry["code"]
        assert entry["source_name"] == "declarative"

    def test_build_declarative_script_entry_omits_empty_subject_tests(self) -> None:
        col = create_new_collection("Empty")
        req = create_new_request(col.id, "GET", "https://example.com", "R")
        AssertionService.save_for_request(
            req.id,
            [
                {
                    "subject": "",
                    "operator": "eq",
                    "expected": "200",
                    "enabled": True,
                    "order_index": 0,
                }
            ],
        )
        entry = AssertionService.build_declarative_script_entry(req.id, "javascript")
        assert entry is not None
        assert "pm.test(" not in entry["code"]
