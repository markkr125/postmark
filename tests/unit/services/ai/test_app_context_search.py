"""Unit tests for app context search formatting."""

from __future__ import annotations

from database.models.request_history import request_history_repository
from services.ai.chat.app_context.search import search_app_context


def test_search_empty_query() -> None:
    """Empty query returns guidance text."""
    assert "non-empty" in search_app_context("", "all").lower()


def test_deleted_history_label_in_search(
    make_collection_with_request, tmp_path, monkeypatch
) -> None:
    """Deleted history rows are searchable and labeled (deleted)."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    _coll, req = make_collection_with_request()
    request_history_repository.insert_entry(
        request_id=req.id,
        request_name="Gone Request",
        method="GET",
        url="https://example.com/gone",
        status_code=200,
        elapsed_ms=1.0,
        error=None,
        response_headers=[],
        response_body=b"ok",
        original_request={"method": "GET", "url": "https://example.com/gone"},
        save_responses=True,
        max_response_bytes=1024,
        retention_days=30,
        max_items_per_day=100,
        unlimited_per_day=True,
    )
    request_history_repository.nullify_request_id(req.id)
    text = search_app_context("gone", "send_history")
    assert "(deleted)" in text
