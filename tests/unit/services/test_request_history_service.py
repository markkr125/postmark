"""Tests for RequestHistoryService."""

from __future__ import annotations

from services.request_history_service import RequestHistoryService, SendIdentityDict
from ui.styling.history_settings_manager import HistorySettingsManager


def test_record_send_and_detail_snapshot(tmp_path, monkeypatch, qapp) -> None:
    """record_send persists rows readable via get_entry and detail snapshot."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    settings = HistorySettingsManager()
    identity: SendIdentityDict = {
        "request_id": None,
        "request_name": "",
        "method": "POST",
        "url": "http://example.com",
    }
    response = {
        "status_code": 201,
        "elapsed_ms": 12.5,
        "headers": [{"key": "Content-Type", "value": "text/plain"}],
        "body": "created",
    }
    snap = {"method": "POST", "url": "http://example.com", "body": "x"}
    entry_id = RequestHistoryService.record_send(
        identity=identity,
        response=response,
        original_request=snap,
        settings=settings,
    )
    assert entry_id is not None
    entry = RequestHistoryService.get_entry(entry_id)
    assert entry is not None
    assert entry["source_label"] == "(draft)"  # unsaved tab: no stored request name
    detail = RequestHistoryService.entry_to_detail_snapshot(entry)
    assert detail["body"] == "created"
    assert detail["original_request"]["url"] == "http://example.com"
