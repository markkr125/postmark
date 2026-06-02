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


def test_entry_to_http_response_dict_success(tmp_path, monkeypatch, qapp) -> None:
    """entry_to_http_response_dict maps stored payloads for the response viewer."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    settings = HistorySettingsManager()
    identity: SendIdentityDict = {
        "request_id": None,
        "request_name": "",
        "method": "GET",
        "url": "http://example.com",
    }
    response = {
        "status_code": 200,
        "elapsed_ms": 5.0,
        "headers": [{"key": "Content-Type", "value": "application/json"}],
        "body": '{"ok":true}',
    }
    entry_id = RequestHistoryService.record_send(
        identity=identity,
        response=response,
        original_request={"method": "GET", "url": "http://example.com"},
        settings=settings,
    )
    assert entry_id is not None
    entry = RequestHistoryService.get_entry(entry_id)
    assert entry is not None
    shaped = RequestHistoryService.entry_to_http_response_dict(entry)
    assert shaped["status_code"] == 200
    assert shaped["status_text"] == "OK"
    assert shaped["body"] == '{"ok":true}'
    assert shaped["request_url"] == "http://example.com"
    assert shaped["headers"][0]["key"] == "Content-Type"


def test_source_label_deleted_vs_draft(tmp_path, monkeypatch, qapp) -> None:
    """was_persisted_request distinguishes (deleted) from (draft)."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    from database.models.collections.collection_repository import (
        create_new_collection,
        create_new_request,
        delete_request,
    )

    settings = HistorySettingsManager()
    coll = create_new_collection("C")
    req = create_new_request(coll.id, "GET", "http://x", "Named")
    persisted_id = RequestHistoryService.record_send(
        identity={
            "request_id": req.id,
            "request_name": "Named",
            "method": "GET",
            "url": "http://x",
        },
        response={"status_code": 200, "elapsed_ms": 1.0, "body": "a"},
        original_request={"method": "GET", "url": "http://x"},
        settings=settings,
    )
    delete_request(req.id)
    assert persisted_id is not None
    deleted = RequestHistoryService.get_entry(persisted_id)
    assert deleted is not None
    assert deleted["source_label"] == "(deleted)"

    draft_id = RequestHistoryService.record_send(
        identity={
            "request_id": None,
            "request_name": "",
            "method": "GET",
            "url": "http://y",
        },
        response={"status_code": 200, "elapsed_ms": 1.0, "body": "b"},
        original_request=None,
        settings=settings,
    )
    assert draft_id is not None
    draft = RequestHistoryService.get_entry(draft_id)
    assert draft is not None
    assert draft["source_label"] == "(draft)"


def test_source_label_none_for_persisted_request(tmp_path, monkeypatch, qapp) -> None:
    """Persisted rows have no source_label suffix."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    from database.models.collections.collection_repository import (
        create_new_collection,
        create_new_request,
    )

    settings = HistorySettingsManager()
    coll = create_new_collection("C")
    req = create_new_request(coll.id, "GET", "http://z", "Live")
    entry_id = RequestHistoryService.record_send(
        identity={
            "request_id": req.id,
            "request_name": "Live",
            "method": "GET",
            "url": "http://z",
        },
        response={"status_code": 200, "elapsed_ms": 1.0, "body": "ok"},
        original_request={"method": "GET", "url": "http://z"},
        settings=settings,
    )
    assert entry_id is not None
    entry = RequestHistoryService.get_entry(entry_id)
    assert entry is not None
    assert entry.get("source_label") is None


def test_entry_to_http_response_dict_error(tmp_path, monkeypatch, qapp) -> None:
    """Error sends map to load_stored_response error shape."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    settings = HistorySettingsManager()
    entry_id = RequestHistoryService.record_send(
        identity={
            "request_id": None,
            "request_name": "",
            "method": "GET",
            "url": "http://fail.example",
        },
        response={"error": "Connection refused", "elapsed_ms": 12.0},
        original_request={"method": "GET", "url": "http://fail.example"},
        settings=settings,
    )
    assert entry_id is not None
    entry = RequestHistoryService.get_entry(entry_id)
    assert entry is not None
    shaped = RequestHistoryService.entry_to_http_response_dict(entry)
    assert shaped.get("error") == "Connection refused"
    assert shaped.get("elapsed_ms") == 0.0
