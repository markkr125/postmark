"""Repository layer — CRUD for declarative request assertions.

UI code must **not** import this directly — use :class:`AssertionService`.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, select

from database.database import get_session

from .model.request_assertion_model import RequestAssertionModel

logger = logging.getLogger(__name__)


def _row_to_dict(row: RequestAssertionModel) -> dict[str, Any]:
    """Convert an ORM row to the service interchange dict."""
    return {
        "id": row.id,
        "request_id": row.request_id,
        "subject": row.subject,
        "operator": row.operator,
        "expected": row.expected or "",
        "enabled": bool(row.enabled),
        "order_index": row.order_index,
    }


def fetch_assertions_for_request(request_id: int) -> list[dict[str, Any]]:
    """Return assertion rows for *request_id*, ordered by ``order_index``."""
    with get_session() as session:
        stmt = (
            select(RequestAssertionModel)
            .where(RequestAssertionModel.request_id == request_id)
            .order_by(RequestAssertionModel.order_index, RequestAssertionModel.id)
        )
        rows = list(session.execute(stmt).scalars().all())
        return [_row_to_dict(row) for row in rows]


def replace_assertions_for_request(
    request_id: int,
    assertions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace all assertions for *request_id* with *assertions*.

    Returns the persisted rows (with database ids assigned).
    """
    with get_session() as session:
        session.execute(
            delete(RequestAssertionModel).where(RequestAssertionModel.request_id == request_id)
        )
        saved: list[dict[str, Any]] = []
        for index, item in enumerate(assertions):
            row = RequestAssertionModel(
                request_id=request_id,
                subject=str(item.get("subject", "")).strip(),
                operator=str(item.get("operator", "eq")).strip() or "eq",
                expected=str(item.get("expected", "") or ""),
                enabled=bool(item.get("enabled", True)),
                order_index=int(item.get("order_index", index)),
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            saved.append(_row_to_dict(row))
        return saved


def delete_assertions_for_request(request_id: int) -> None:
    """Remove every assertion row for *request_id*."""
    with get_session() as session:
        session.execute(
            delete(RequestAssertionModel).where(RequestAssertionModel.request_id == request_id)
        )
