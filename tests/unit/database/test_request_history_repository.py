"""Tests for request_history_repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from database.models.collections.collection_repository import (
    create_new_collection,
    create_new_request,
    delete_request,
)
from database.models.request_history import request_history_repository


def _insert(**kwargs: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "request_id": None,
        "request_name": "Req",
        "method": "GET",
        "url": "http://example.com",
        "status_code": 200,
        "elapsed_ms": 1.0,
        "error": None,
        "response_headers": [],
        "response_body": b"ok",
        "original_request": {"method": "GET", "url": "http://example.com"},
        "save_responses": True,
        "max_response_bytes": 1024,
        "retention_days": 30,
        "max_items_per_day": 100,
        "unlimited_per_day": True,
    }
    defaults.update(kwargs)
    return request_history_repository.insert_entry(**defaults)


def test_insert_writes_files_and_paths(tmp_path, monkeypatch) -> None:
    """Insert stores relative paths and creates body + snapshot files."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    row = _insert()
    assert row["was_persisted_request"] is False
    assert row["response_body_path"] == f"bodies/{row['id']}.bin"
    assert row["request_snapshot_path"] == f"requests/{row['id']}.json"
    full = request_history_repository.get_entry(int(row["id"]))
    assert full is not None
    assert full["body"] == b"ok"
    assert full["original_request"]["url"] == "http://example.com"


def test_save_responses_false_skips_body_file(tmp_path, monkeypatch) -> None:
    """When save_responses is false, snapshot is still written."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    row = _insert(save_responses=False, response_body=b"skip")
    assert row["response_body_path"] is None
    assert row["request_snapshot_path"] is not None


def test_nullify_request_id_on_delete(tmp_path, monkeypatch) -> None:
    """Deleting a request nullifies history request_id."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    coll = create_new_collection("C")
    req = create_new_request(coll.id, "GET", "http://x", "R")
    row = _insert(request_id=req.id, request_name="R")
    delete_request(req.id)
    loaded = request_history_repository.get_entry(int(row["id"]))
    assert loaded is not None
    assert loaded["request_id"] is None


def test_prune_drops_old_rows(tmp_path, monkeypatch) -> None:
    """Rows older than retention_days are removed."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    row = _insert(retention_days=1, unlimited_per_day=True)
    entry_id = int(row["id"])
    from database.database import get_session
    from database.models.request_history.model.request_history_entry_model import (
        RequestHistoryEntryModel,
    )

    with get_session() as session:
        model = session.get(RequestHistoryEntryModel, entry_id)
        assert model is not None
        model.executed_at = datetime.now(tz=UTC) - timedelta(days=5)
    request_history_repository.prune_old_entries(
        retention_days=1,
        max_items_per_day=100,
        unlimited_per_day=True,
    )
    assert request_history_repository.get_entry(entry_id) is None


def test_body_truncated_when_over_max_bytes(tmp_path, monkeypatch) -> None:
    """Response bodies longer than max_response_bytes are truncated on insert."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    row = _insert(response_body=b"abcdef", max_response_bytes=4)
    loaded = request_history_repository.get_entry(int(row["id"]))
    assert loaded is not None
    assert loaded["body_truncated"] is True
    assert loaded["body"] == b"abcd"


def test_was_persisted_request_set_for_saved_request(tmp_path, monkeypatch) -> None:
    """Persisted sends set was_persisted_request so legacy NOT NULL columns are satisfied."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    coll = create_new_collection("C")
    req = create_new_request(coll.id, "GET", "http://x", "R")
    row = _insert(request_id=req.id, request_name="R")
    assert row["was_persisted_request"] is True


def test_list_for_request_filters_by_request_id(tmp_path, monkeypatch) -> None:
    """list_for_request returns only rows for the given request_id."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    coll = create_new_collection("C")
    req_a = create_new_request(coll.id, "GET", "http://a", "A")
    req_b = create_new_request(coll.id, "GET", "http://b", "B")
    row_a = _insert(request_id=req_a.id, request_name="A", url="http://a")
    _insert(request_id=req_b.id, request_name="B", url="http://b")
    _insert(request_id=None, request_name="Draft", url="http://draft")

    listed = request_history_repository.list_for_request(req_a.id)
    assert len(listed) == 1
    assert listed[0]["id"] == row_a["id"]
    assert listed[0]["request_id"] == req_a.id


def test_list_for_request_search_by_url_and_status(tmp_path, monkeypatch) -> None:
    """Search filters by URL substring and exact status code."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    coll = create_new_collection("C")
    req = create_new_request(coll.id, "GET", "http://host", "R")
    _insert(
        request_id=req.id,
        request_name="Ok",
        url="http://host/ok",
        status_code=200,
    )
    bad = _insert(
        request_id=req.id,
        request_name="Bad",
        url="http://host/error",
        status_code=400,
    )

    by_url = request_history_repository.list_for_request(req.id, search="error")
    assert len(by_url) == 1
    assert by_url[0]["id"] == bad["id"]

    by_status = request_history_repository.list_for_request(req.id, search="400")
    assert len(by_status) == 1
    assert by_status[0]["status_code"] == 400
