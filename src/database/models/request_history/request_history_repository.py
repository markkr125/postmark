"""Repository layer — CRUD for HTTP request send history."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select

from database.database import get_session

from . import body_store
from .model.request_history_entry_model import RequestHistoryEntryModel

logger = logging.getLogger(__name__)


def local_date(executed_at: datetime) -> date:
    """Return the local calendar date for *executed_at* (timezone-aware)."""
    if executed_at.tzinfo is None:
        executed_at = executed_at.replace(tzinfo=UTC)
    return executed_at.astimezone().date()


def _entry_to_dict(row: RequestHistoryEntryModel) -> dict[str, Any]:
    """Convert an ORM row to a plain dict (metadata only)."""
    executed = row.executed_at
    if executed.tzinfo is None:
        executed = executed.replace(tzinfo=UTC)
    return {
        "id": row.id,
        "executed_at": executed.isoformat(),
        "request_id": row.request_id,
        "was_persisted_request": row.was_persisted_request,
        "request_name": row.request_name,
        "method": row.method,
        "url": row.url,
        "status_code": row.status_code,
        "elapsed_ms": row.elapsed_ms,
        "error": row.error,
        "response_headers": row.response_headers,
        "response_body_path": row.response_body_path,
        "body_truncated": row.body_truncated,
        "response_size_bytes": row.response_size_bytes,
        "request_snapshot_path": row.request_snapshot_path,
    }


def insert_entry(
    *,
    request_id: int | None,
    request_name: str,
    method: str,
    url: str,
    status_code: int,
    elapsed_ms: float,
    error: str | None,
    response_headers: list[Any] | dict[str, Any] | None,
    response_body: bytes | None,
    original_request: dict[str, Any] | None,
    save_responses: bool,
    max_response_bytes: int,
    retention_days: int,
    max_items_per_day: int,
    unlimited_per_day: bool,
) -> dict[str, Any]:
    """Insert metadata, write disk files, update paths, and prune old rows."""
    body_truncated = False
    response_size_bytes = 0
    body_path: str | None = None
    snapshot_path: str | None = None

    if response_body is not None and save_responses:
        response_size_bytes = len(response_body)
        to_write = response_body
        if len(to_write) > max_response_bytes:
            to_write = to_write[:max_response_bytes]
            body_truncated = True
    else:
        to_write = None

    with get_session() as session:
        row = RequestHistoryEntryModel(
            executed_at=datetime.now(tz=UTC),
            request_id=request_id,
            was_persisted_request=request_id is not None,
            request_name=request_name,
            method=method,
            url=url,
            status_code=status_code,
            elapsed_ms=elapsed_ms,
            error=error,
            response_headers=response_headers if save_responses else None,
            body_truncated=body_truncated,
            response_size_bytes=response_size_bytes,
        )
        session.add(row)
        session.flush()
        entry_id = row.id

        if to_write is not None:
            body_path = body_store.write_body(entry_id, to_write)
            row.response_body_path = body_path
            if body_store.read_body(body_path) is None:
                raise RuntimeError(f"request history body file not written for entry {entry_id}")
        if original_request is not None:
            try:
                snapshot_path = body_store.write_request_snapshot(entry_id, original_request)
                row.request_snapshot_path = snapshot_path
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "Request history %s: could not serialize request snapshot: %s",
                    entry_id,
                    exc,
                )
        session.flush()
        result = _entry_to_dict(row)

    prune_old_entries(
        retention_days=retention_days,
        max_items_per_day=max_items_per_day,
        unlimited_per_day=unlimited_per_day,
    )
    return result


def delete_entry(entry_id: int) -> bool:
    """Delete one history row and its on-disk payload files."""
    with get_session() as session:
        row = session.get(RequestHistoryEntryModel, entry_id)
        if row is None:
            return False
        _delete_rows(session, [row])
    return True


def get_entry(entry_id: int) -> dict[str, Any] | None:
    """Load one entry with body bytes and request snapshot attached."""
    with get_session() as session:
        row = session.get(RequestHistoryEntryModel, entry_id)
        if row is None:
            return None
        data = _entry_to_dict(row)
    body_bytes = body_store.read_body(data.get("response_body_path"))
    data["body"] = body_bytes
    data["original_request"] = body_store.read_request_snapshot(data.get("request_snapshot_path"))
    return data


def list_entries_for_sidebar(*, search: str = "", limit: int = 500) -> list[dict[str, Any]]:
    """Return metadata rows newest-first; optional SQL search over all retained rows."""
    term = search.strip()
    with get_session() as session:
        stmt = select(RequestHistoryEntryModel).order_by(
            RequestHistoryEntryModel.executed_at.desc(),
            RequestHistoryEntryModel.id.desc(),
        )
        stmt = _apply_history_search(stmt, term) if term else stmt.limit(limit)
        rows = list(session.execute(stmt).scalars().all())
    return [_entry_to_dict(row) for row in rows]


def _apply_history_search(stmt: Any, term: str) -> Any:
    """Filter history rows by URL, name, method, or exact status code."""
    pattern = f"%{term}%"
    clauses: list[Any] = [
        RequestHistoryEntryModel.request_name.ilike(pattern),
        RequestHistoryEntryModel.url.ilike(pattern),
        RequestHistoryEntryModel.method.ilike(pattern),
    ]
    if term.isdigit():
        clauses.append(RequestHistoryEntryModel.status_code == int(term))
    return stmt.where(or_(*clauses))


def list_for_request(
    request_id: int,
    *,
    search: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return metadata rows for one saved request, newest first."""
    term = search.strip()
    with get_session() as session:
        stmt = (
            select(RequestHistoryEntryModel)
            .where(RequestHistoryEntryModel.request_id == request_id)
            .order_by(
                RequestHistoryEntryModel.executed_at.desc(),
                RequestHistoryEntryModel.id.desc(),
            )
        )
        stmt = _apply_history_search(stmt, term) if term else stmt.limit(limit)
        rows = list(session.execute(stmt).scalars().all())
    return [_entry_to_dict(row) for row in rows]


def _delete_rows(session: Any, rows: list[RequestHistoryEntryModel]) -> None:
    """Unlink on-disk files and delete ORM rows."""
    for row in rows:
        body_store.delete_file(row.response_body_path)
        body_store.delete_file(row.request_snapshot_path)
        session.delete(row)


def prune_old_entries(
    *,
    retention_days: int,
    max_items_per_day: int,
    unlimited_per_day: bool,
) -> None:
    """Drop rows older than *retention_days* and enforce per-local-day caps."""
    cutoff = datetime.now(tz=UTC) - timedelta(days=max(1, retention_days))
    with get_session() as session:
        stmt = select(RequestHistoryEntryModel).where(RequestHistoryEntryModel.executed_at < cutoff)
        stale = list(session.execute(stmt).scalars().all())
        if stale:
            _delete_rows(session, stale)

        if not unlimited_per_day:
            stmt_all = select(RequestHistoryEntryModel).order_by(
                RequestHistoryEntryModel.executed_at.asc(),
                RequestHistoryEntryModel.id.asc(),
            )
            all_rows = list(session.execute(stmt_all).scalars().all())
            by_day: dict[date, list[RequestHistoryEntryModel]] = defaultdict(list)
            for row in all_rows:
                executed = row.executed_at
                if executed.tzinfo is None:
                    executed = executed.replace(tzinfo=UTC)
                by_day[local_date(executed)].append(row)
            to_drop: list[RequestHistoryEntryModel] = []
            cap = max(1, max_items_per_day)
            for day_rows in by_day.values():
                if len(day_rows) > cap:
                    to_drop.extend(day_rows[: len(day_rows) - cap])
            if to_drop:
                _delete_rows(session, to_drop)


def nullify_request_id(request_id: int) -> None:
    """Clear ``request_id`` on history rows when the saved request is deleted."""
    from sqlalchemy import update

    with get_session() as session:
        stmt = (
            update(RequestHistoryEntryModel)
            .where(RequestHistoryEntryModel.request_id == request_id)
            .values(request_id=None)
        )
        session.execute(stmt)
