"""File-backed storage for request-history response bodies and request snapshots."""

from __future__ import annotations

import json
import logging
import os
import shutil
from contextlib import suppress
from pathlib import Path

import database.data_paths as data_paths
from database.database import get_session

from .model.request_history_entry_model import RequestHistoryEntryModel

logger = logging.getLogger(__name__)


def normalize_history_relative_path(relative_path: str | None) -> str | None:
    """Strip a legacy ``history/`` prefix mistakenly stored in SQLite paths."""
    if not relative_path:
        return None
    path = relative_path.replace("\\", "/").lstrip("/")
    while path.startswith("history/"):
        path = path[len("history/") :]
    return path or None


def _legacy_project_history_root() -> Path:
    """Return the pre-user-data history directory under the project tree."""
    return data_paths.project_root() / "data" / "history"


def resolve_history_path(relative_path: str) -> Path:
    """Resolve a DB-relative path under :func:`user_history_root`."""
    normalized = normalize_history_relative_path(relative_path) or relative_path
    return data_paths.user_history_root() / normalized


def _read_candidates(relative_path: str | None) -> list[Path]:
    """Return filesystem paths to try when loading a stored relative path."""
    if not relative_path:
        return []
    normalized = normalize_history_relative_path(relative_path)
    if not normalized:
        return []
    candidates = [
        data_paths.user_history_root() / normalized,
        _legacy_project_history_root() / normalized,
    ]
    raw = relative_path.replace("\\", "/").lstrip("/")
    if raw != normalized:
        candidates.append(_legacy_project_history_root() / raw)
    # De-duplicate while preserving order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def _bodies_dir() -> Path:
    path = data_paths.user_history_root() / "bodies"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _requests_dir() -> Path:
    path = data_paths.user_history_root() / "requests"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write(target: Path, data: bytes) -> None:
    """Write *data* to *target* via a same-directory temp file and ``os.replace``."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)


def write_body(entry_id: int, data: bytes) -> str:
    """Write response body bytes; return relative path ``bodies/{id}.bin``."""
    rel = f"bodies/{entry_id}.bin"
    _atomic_write(_bodies_dir() / f"{entry_id}.bin", data)
    return rel


def read_body(relative_path: str | None) -> bytes | None:
    """Read body bytes; return ``None`` when the file is missing."""
    for path in _read_candidates(relative_path):
        if path.is_file():
            return path.read_bytes()
    return None


def write_request_snapshot(entry_id: int, snap: dict) -> str:
    """Write request snapshot JSON; return relative path ``requests/{id}.json``."""
    rel = f"requests/{entry_id}.json"
    payload = json.dumps(snap, ensure_ascii=False, default=str).encode("utf-8")
    _atomic_write(_requests_dir() / f"{entry_id}.json", payload)
    return rel


def read_request_snapshot(relative_path: str | None) -> dict | None:
    """Read request snapshot JSON; return ``None`` when missing or invalid."""
    for path in _read_candidates(relative_path):
        if not path.is_file():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        return loaded if isinstance(loaded, dict) else None
    return None


def delete_file(relative_path: str | None) -> None:
    """Best-effort unlink of a history file in all known storage locations."""
    if not relative_path:
        return
    for path in _read_candidates(relative_path):
        with suppress(OSError):
            path.unlink(missing_ok=True)


def _copy_legacy_file_to_user_store(relative_path: str) -> None:
    """Copy a file from a legacy location into ``user_history_root`` when missing."""
    normalized = normalize_history_relative_path(relative_path)
    if not normalized:
        return
    dest = data_paths.user_history_root() / normalized
    if dest.is_file():
        return
    for src in _read_candidates(relative_path):
        if src.is_file() and src != dest:
            _atomic_write(dest, src.read_bytes())
            return


def _copy_tree_if_missing(src_root: Path, dest_root: Path, subdir: str) -> None:
    """Copy ``subdir`` files from *src_root* into *dest_root* when absent in dest."""
    src_dir = src_root / subdir
    if not src_dir.is_dir():
        return
    dest_dir = dest_root / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in src_dir.iterdir():
        if not src.is_file():
            continue
        dest = dest_dir / src.name
        if not dest.is_file():
            shutil.copy2(src, dest)


def _migrate_files_from_legacy_roots() -> None:
    """Import bodies/requests from project ``data/history`` into the user-data store."""
    dest = data_paths.user_history_root()
    src = _legacy_project_history_root()
    if src.resolve() == dest.resolve():
        return
    _copy_tree_if_missing(src, dest, "bodies")
    _copy_tree_if_missing(src, dest, "requests")


def _ensure_row_files_present(row: RequestHistoryEntryModel) -> None:
    """Copy missing payload files for one DB row from any legacy location."""
    for attr in ("response_body_path", "request_snapshot_path"):
        rel = getattr(row, attr)
        if rel:
            _copy_legacy_file_to_user_store(str(rel))


def migrate_legacy_paths_and_files() -> None:
    """Normalize DB paths, import legacy trees, and backfill missing row files."""
    from sqlalchemy import select

    _migrate_files_from_legacy_roots()
    with get_session() as session:
        rows = list(session.execute(select(RequestHistoryEntryModel)).scalars().all())
        for row in rows:
            for attr in ("response_body_path", "request_snapshot_path"):
                old = getattr(row, attr)
                new = normalize_history_relative_path(old)
                if new and new != old:
                    setattr(row, attr, new)
            _ensure_row_files_present(row)
        session.flush()


def reconcile_orphans() -> None:
    """Remove body/snapshot files that do not belong to any history row id."""
    bodies_dir = data_paths.user_history_root() / "bodies"
    requests_dir = data_paths.user_history_root() / "requests"
    if not bodies_dir.is_dir() and not requests_dir.is_dir():
        return

    from sqlalchemy import select

    with get_session() as session:
        rows = list(session.execute(select(RequestHistoryEntryModel)).scalars().all())
    known_entry_ids = {int(row.id) for row in rows}

    has_body_files = bodies_dir.is_dir() and any(bodies_dir.iterdir())
    if has_body_files and not known_entry_ids:
        logger.warning(
            "Skipping request-history orphan cleanup: payload files exist but "
            "request_history_entries is empty"
        )
        return

    if bodies_dir.is_dir():
        for path in bodies_dir.iterdir():
            if not path.is_file() or path.suffix != ".bin":
                continue
            try:
                entry_id = int(path.stem)
            except ValueError:
                delete_file(f"bodies/{path.name}")
                continue
            if entry_id not in known_entry_ids:
                delete_file(f"bodies/{path.name}")
    if requests_dir.is_dir():
        for path in requests_dir.iterdir():
            if not path.is_file() or path.suffix != ".json":
                continue
            try:
                entry_id = int(path.stem)
            except ValueError:
                delete_file(f"requests/{path.name}")
                continue
            if entry_id not in known_entry_ids:
                delete_file(f"requests/{path.name}")


def verify_body_files() -> int:
    """Log rows whose body files are missing on disk; return the missing count."""
    from sqlalchemy import select

    missing = 0
    with get_session() as session:
        rows = list(session.execute(select(RequestHistoryEntryModel)).scalars().all())
    for row in rows:
        if row.response_size_bytes <= 0:
            continue
        if read_body(row.response_body_path) is None:
            missing += 1
            logger.debug(
                "Request history entry %s body file missing (path=%r, size=%s)",
                row.id,
                row.response_body_path,
                row.response_size_bytes,
            )
    return missing
