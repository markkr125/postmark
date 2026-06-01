"""Tests for send-history replay helpers."""

from __future__ import annotations

from typing import cast

from services.request_history_service import RequestHistoryEntryDict, RequestHistoryService


def test_build_replay_request_dict_uses_snapshot_then_metadata() -> None:
    """Replay data prefers the stored snapshot and falls back to row fields."""
    entry = cast(
        RequestHistoryEntryDict,
        {
            "method": "POST",
            "url": "http://fallback",
            "request_name": "Name",
            "original_request": {"method": "GET", "url": "http://snap", "body": "{}"},
        },
    )
    data = RequestHistoryService.build_replay_request_dict(entry)
    assert data["method"] == "GET"
    assert data["url"] == "http://snap"
    assert data["body"] == "{}"


def test_can_replay_entry_requires_url() -> None:
    """Replay is disabled when no URL is available."""
    assert RequestHistoryService.can_replay_entry({"method": "GET", "url": ""}) is False
    assert RequestHistoryService.can_replay_entry({"method": "GET", "url": "http://x"}) is True


def test_build_send_payload_uses_sent_headers() -> None:
    """Replay send uses sent_headers from the snapshot, not editor auth reinjection."""
    entry = cast(
        RequestHistoryEntryDict,
        {
            "method": "GET",
            "url": "http://example.com",
            "original_request": {
                "method": "GET",
                "url": "http://example.com",
                "sent_headers": [{"key": "Authorization", "value": "Bearer tok"}],
            },
        },
    )
    payload = RequestHistoryService.build_send_payload_from_entry(entry)
    assert payload is not None
    assert "Authorization: Bearer tok" in (payload["headers"] or "")
    assert payload["url"] == "http://example.com"


def test_replay_source_link_text_includes_method_and_time() -> None:
    """Replay banner link text references method, status, and timestamp."""
    entry = cast(
        RequestHistoryEntryDict,
        {
            "method": "GET",
            "status_code": 400,
            "executed_at": "2024-06-01T13:34:42+00:00",
        },
    )
    text = RequestHistoryService.replay_source_link_text(entry)
    assert "GET" in text
    assert "400" in text
    assert "View" in text


def test_delete_entry_removes_row_and_files(tmp_path, monkeypatch) -> None:
    """delete_entry removes the DB row and payload files."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    from ui.styling.history_settings_manager import HistorySettingsManager

    settings = HistorySettingsManager()
    entry_id = RequestHistoryService.record_send(
        identity={
            "request_id": None,
            "request_name": "R",
            "method": "GET",
            "url": "http://example.com",
        },
        response={"status_code": 200, "elapsed_ms": 1.0, "headers": [], "body": "ok"},
        original_request={"method": "GET"},
        settings=settings,
    )
    assert entry_id is not None
    assert RequestHistoryService.get_entry(entry_id) is not None
    assert RequestHistoryService.delete_entry(entry_id) is True
    assert RequestHistoryService.get_entry(entry_id) is None
