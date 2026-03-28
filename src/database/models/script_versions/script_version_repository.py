"""Repository layer — CRUD functions for script version history.

UI code must **not** import this directly — use the service layer instead.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, func, select

from database.database import get_session

from .model.script_version_model import ScriptVersionModel

logger = logging.getLogger(__name__)

# Maximum snapshots kept per script (oldest pruned beyond this).
_MAX_VERSIONS_PER_SCRIPT = 100


def save_script_version(
    *,
    request_id: int | None = None,
    collection_id: int | None = None,
    script_type: str,
    content: str,
    language: str = "javascript",
) -> ScriptVersionModel:
    """Create a new version snapshot and return it.

    Automatically prunes old versions beyond ``_MAX_VERSIONS_PER_SCRIPT``.
    """
    with get_session() as session:
        version = ScriptVersionModel(
            request_id=request_id,
            collection_id=collection_id,
            script_type=script_type,
            content=content,
            language=language,
        )
        session.add(version)
        session.flush()
        session.refresh(version)

        # Prune old versions.
        _prune_versions(
            session,
            request_id=request_id,
            collection_id=collection_id,
            script_type=script_type,
        )

        return version


def get_script_versions(
    *,
    request_id: int | None = None,
    collection_id: int | None = None,
    script_type: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return recent versions for a script, newest first.

    Each dict contains ``id``, ``content``, ``language``, and
    ``created_at``.
    """
    with get_session() as session:
        stmt = (
            select(ScriptVersionModel)
            .where(_owner_filter(request_id, collection_id))
            .where(ScriptVersionModel.script_type == script_type)
            .order_by(ScriptVersionModel.id.desc())
            .limit(limit)
        )
        rows = list(session.execute(stmt).scalars().all())
        return [
            {
                "id": v.id,
                "content": v.content,
                "language": v.language,
                "created_at": v.created_at,
            }
            for v in rows
        ]


def get_script_version(version_id: int) -> dict[str, Any] | None:
    """Return a single version by its PK, or ``None``."""
    with get_session() as session:
        v = session.get(ScriptVersionModel, version_id)
        if v is None:
            return None
        return {
            "id": v.id,
            "content": v.content,
            "language": v.language,
            "created_at": v.created_at,
            "request_id": v.request_id,
            "collection_id": v.collection_id,
            "script_type": v.script_type,
        }


def delete_script_versions(
    *,
    request_id: int | None = None,
    collection_id: int | None = None,
) -> int:
    """Delete all versions for a given request or collection.

    Returns the number of deleted rows.
    """
    with get_session() as session:
        stmt = select(ScriptVersionModel).where(_owner_filter(request_id, collection_id))
        rows = list(session.execute(stmt).scalars().all())
        for row in rows:
            session.delete(row)
        return len(rows)


# -- Internal helpers --------------------------------------------------


def _owner_filter(
    request_id: int | None,
    collection_id: int | None,
) -> Any:
    """Return a SQLAlchemy filter clause matching the owner."""
    if request_id is not None:
        return ScriptVersionModel.request_id == request_id
    return ScriptVersionModel.collection_id == collection_id


def _prune_versions(
    session: Any,
    *,
    request_id: int | None,
    collection_id: int | None,
    script_type: str,
) -> None:
    """Delete the oldest versions beyond ``_MAX_VERSIONS_PER_SCRIPT``."""
    count_stmt = (
        select(func.count())
        .select_from(ScriptVersionModel)
        .where(_owner_filter(request_id, collection_id))
        .where(ScriptVersionModel.script_type == script_type)
    )
    total = session.execute(count_stmt).scalar() or 0

    if total <= _MAX_VERSIONS_PER_SCRIPT:
        return

    # Find the ID threshold — keep the newest N.
    keep_stmt = (
        select(ScriptVersionModel.id)
        .where(_owner_filter(request_id, collection_id))
        .where(ScriptVersionModel.script_type == script_type)
        .order_by(ScriptVersionModel.id.desc())
        .limit(_MAX_VERSIONS_PER_SCRIPT)
    )
    keep_ids = {row for row in session.execute(keep_stmt).scalars().all()}

    del_stmt = (
        delete(ScriptVersionModel)
        .where(_owner_filter(request_id, collection_id))
        .where(ScriptVersionModel.script_type == script_type)
        .where(ScriptVersionModel.id.notin_(keep_ids))
    )
    session.execute(del_stmt)
