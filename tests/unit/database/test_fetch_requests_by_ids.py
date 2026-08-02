"""Unit tests for bulk request fetch helpers."""

from __future__ import annotations

from services.collection_service import CollectionService


class TestFetchRequestsByIds:
    """``fetch_requests_by_ids`` returns RequestLoadDict rows keyed by id."""

    def test_returns_load_dict_for_batch(
        self,
        make_collection_with_request,
    ) -> None:
        """Bulk fetch includes method, name, and url for each id."""
        _coll, req = make_collection_with_request()
        request_id = req.id
        rows = CollectionService.fetch_requests_by_ids([request_id])
        assert request_id in rows
        row = rows[request_id]
        assert row["method"] == "GET"
        assert row["name"] == "Req"
        assert "x" in (row.get("url") or "")

    def test_empty_ids_returns_empty_dict(self) -> None:
        """Empty input list is a no-op."""
        assert CollectionService.fetch_requests_by_ids([]) == {}

    def test_breadcrumbs_bulk(self, make_collection_with_request) -> None:
        """Bulk breadcrumb fetch returns a path ending with the request."""
        _coll, req = make_collection_with_request()
        request_id = req.id
        crumbs = CollectionService.fetch_request_breadcrumbs_by_ids([request_id])
        assert request_id in crumbs
        path = crumbs[request_id]
        assert path[-1]["type"] == "request"
        assert path[-1]["id"] == request_id
