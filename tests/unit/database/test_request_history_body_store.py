"""Tests for request-history file storage."""

from __future__ import annotations

import database.data_paths as data_paths
from database.models.request_history import body_store


def test_write_and_read_body() -> None:
    """Body files are written under bodies/ and read back."""
    rel = body_store.write_body(7, b"hello")
    assert rel == "bodies/7.bin"
    assert body_store.read_body(rel) == b"hello"
    assert (data_paths.user_history_root() / "bodies" / "7.bin").is_file()


def test_write_and_read_snapshot() -> None:
    """Request snapshots round-trip as JSON."""
    snap = {"method": "GET", "url": "http://example.com"}
    rel = body_store.write_request_snapshot(3, snap)
    assert rel == "requests/3.json"
    loaded = body_store.read_request_snapshot(rel)
    assert loaded == snap


def test_read_missing_returns_none() -> None:
    """Missing files return None without raising."""
    assert body_store.read_body("bodies/missing.bin") is None
    assert body_store.read_request_snapshot("requests/missing.json") is None


def test_read_legacy_history_prefix_and_project_data_dir(tmp_path, monkeypatch) -> None:
    """Rows stored as ``history/bodies/…`` load from project ``data/history``."""
    monkeypatch.setattr(
        "database.models.request_history.body_store.data_paths.project_root",
        lambda: tmp_path / "repo",
    )
    legacy = tmp_path / "repo" / "data" / "history" / "bodies"
    legacy.mkdir(parents=True)
    (legacy / "1.bin").write_bytes(b'{"error":true}')

    loaded = body_store.read_body("history/bodies/1.bin")
    assert loaded == b'{"error":true}'


def test_migrate_legacy_paths_normalizes_db_and_copies_files(tmp_path, monkeypatch) -> None:
    """Startup migration fixes path strings and copies bodies into user-data."""
    monkeypatch.setattr(
        "database.models.request_history.body_store.data_paths.project_root",
        lambda: tmp_path / "repo",
    )
    from database.database import get_session
    from database.models.request_history import request_history_repository
    from database.models.request_history.model.request_history_entry_model import (
        RequestHistoryEntryModel,
    )

    row = request_history_repository.insert_entry(
        request_id=None,
        request_name="R",
        method="GET",
        url="http://example.com",
        status_code=200,
        elapsed_ms=1.0,
        error=None,
        response_headers=[],
        response_body=b"migrated",
        original_request=None,
        save_responses=True,
        max_response_bytes=1024,
        retention_days=30,
        max_items_per_day=100,
        unlimited_per_day=True,
    )
    entry_id = int(row["id"])
    primary = data_paths.user_history_root() / "bodies" / f"{entry_id}.bin"
    legacy_dir = tmp_path / "repo" / "data" / "history" / "bodies"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = legacy_dir / f"{entry_id}.bin"
    legacy_file.write_bytes(primary.read_bytes())
    primary.unlink()

    with get_session() as session:
        loaded = session.get(RequestHistoryEntryModel, entry_id)
        assert loaded is not None
        loaded.response_body_path = f"history/bodies/{entry_id}.bin"
        session.flush()

    body_store.migrate_legacy_paths_and_files()
    with get_session() as session:
        loaded = session.get(RequestHistoryEntryModel, entry_id)
        assert loaded is not None
        assert loaded.response_body_path == f"bodies/{entry_id}.bin"
    assert body_store.read_body(f"bodies/{entry_id}.bin") == b"migrated"
    assert primary.is_file()


def test_reconcile_orphans_keeps_files_for_known_entry_ids() -> None:
    """Orphan sweep keeps ``bodies/{entry_id}.bin`` when the row id exists."""
    from database.models.request_history import request_history_repository

    row = request_history_repository.insert_entry(
        request_id=None,
        request_name="R",
        method="GET",
        url="http://example.com",
        status_code=200,
        elapsed_ms=1.0,
        error=None,
        response_headers=[],
        response_body=b"keep",
        original_request=None,
        save_responses=True,
        max_response_bytes=1024,
        retention_days=30,
        max_items_per_day=100,
        unlimited_per_day=True,
    )
    entry_id = int(row["id"])
    path = data_paths.user_history_root() / "bodies" / f"{entry_id}.bin"
    assert path.is_file()
    body_store.reconcile_orphans()
    assert path.is_file()
    assert path.read_bytes() == b"keep"


def test_reconcile_orphans_removes_stray_file() -> None:
    """Orphan files under bodies/ are removed when not referenced in the DB."""
    from database.models.request_history import request_history_repository

    row = request_history_repository.insert_entry(
        request_id=None,
        request_name="R",
        method="GET",
        url="http://example.com",
        status_code=200,
        elapsed_ms=1.0,
        error=None,
        response_headers=[],
        response_body=b"keep",
        original_request=None,
        save_responses=True,
        max_response_bytes=1024,
        retention_days=30,
        max_items_per_day=100,
        unlimited_per_day=True,
    )
    entry_id = int(row["id"])
    bodies = data_paths.user_history_root() / "bodies"
    orphan = bodies / "99.bin"
    orphan.write_bytes(b"orphan")
    body_store.reconcile_orphans()
    assert not orphan.exists()
    assert (bodies / f"{entry_id}.bin").is_file()


def test_reconcile_skips_when_db_empty_but_body_files_exist() -> None:
    """Do not delete real payloads when the DB has no rows (e.g. isolated test DB)."""
    bodies = data_paths.user_history_root() / "bodies"
    bodies.mkdir(parents=True, exist_ok=True)
    survivor = bodies / "42.bin"
    survivor.write_bytes(b"payload")
    body_store.reconcile_orphans()
    assert survivor.is_file()
    assert survivor.read_bytes() == b"payload"
