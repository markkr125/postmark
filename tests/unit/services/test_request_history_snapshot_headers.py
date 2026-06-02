"""Tests for send-history snapshot header capture."""

from __future__ import annotations

from services.request_history_service import RequestHistoryService
from ui.sidebar.history.helpers import extract_history_request_headers


def test_enrich_snapshot_stores_sent_headers() -> None:
    """Auth-injected headers from the worker are stored on the snapshot."""
    snap = {"method": "GET", "url": "http://example.com", "headers": []}
    response = {
        "request_method": "GET",
        "request_url": "http://example.com/ok",
        "request_headers": [
            {"key": "Authorization", "value": "Bearer secret"},
            {"key": "X-Custom", "value": "1"},
        ],
    }
    merged = RequestHistoryService.enrich_snapshot_for_history(snap, response)
    assert merged["url"] == "http://example.com/ok"
    assert merged["sent_headers"] == response["request_headers"]
    text = extract_history_request_headers(merged)
    assert "Authorization: Bearer secret" in text
    assert "X-Custom: 1" in text


def test_extract_history_request_headers_falls_back_to_editor_headers() -> None:
    """Older rows without sent_headers still show editor header rows."""
    snap = {
        "headers": [{"key": "Accept", "value": "application/json"}],
    }
    text = extract_history_request_headers(snap)
    assert "Accept: application/json" in text
