"""Repository layer — CRUD for user-authored script snippets.

UI code must **not** import this directly — use :class:`~services.snippet_service.SnippetService`.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, select

from database.database import get_session

from .model.snippet_model import SnippetModel

logger = logging.getLogger(__name__)


def list_snippets(
    *,
    language: str,
    collection_id: int | None = None,
    local_script_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return snippets for *language* visible in the current scope.

    Includes global rows (both scope columns ``None``) plus rows scoped to
    *collection_id* or *local_script_id* when provided.
    """
    with get_session() as session:
        scope_clause = SnippetModel.scope_collection_id.is_(None) & (
            SnippetModel.scope_local_script_id.is_(None)
        )
        if collection_id is not None:
            scope_clause = scope_clause | (SnippetModel.scope_collection_id == collection_id)
        if local_script_id is not None:
            scope_clause = scope_clause | (SnippetModel.scope_local_script_id == local_script_id)
        stmt = (
            select(SnippetModel)
            .where(SnippetModel.language == language)
            .where(scope_clause)
            .order_by(SnippetModel.category.asc(), SnippetModel.name.asc(), SnippetModel.id.asc())
        )
        rows = list(session.execute(stmt).scalars().all())
        return [_row_to_dict(r) for r in rows]


def create_snippet(
    *,
    name: str,
    language: str,
    category: str,
    body: str,
    context: str,
    scope_collection_id: int | None = None,
    scope_local_script_id: int | None = None,
) -> SnippetModel:
    """Insert a new snippet and return the persisted row."""
    with get_session() as session:
        row = SnippetModel(
            name=name,
            language=language,
            category=category,
            body=body,
            context=context,
            scope_collection_id=scope_collection_id,
            scope_local_script_id=scope_local_script_id,
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return row


def update_snippet(
    snippet_id: int,
    *,
    name: str | None = None,
    category: str | None = None,
    body: str | None = None,
    context: str | None = None,
) -> None:
    """Update mutable fields on an existing snippet."""
    with get_session() as session:
        row = session.get(SnippetModel, snippet_id)
        if row is None:
            raise ValueError(f"No snippet found with id={snippet_id}")
        if name is not None:
            row.name = name
        if category is not None:
            row.category = category
        if body is not None:
            row.body = body
        if context is not None:
            row.context = context


def delete_snippet(snippet_id: int) -> None:
    """Delete the snippet with the given primary key."""
    with get_session() as session:
        stmt = delete(SnippetModel).where(SnippetModel.id == snippet_id)
        session.execute(stmt)


def get_snippet_by_id(snippet_id: int) -> dict[str, Any] | None:
    """Return one snippet dict or ``None``."""
    with get_session() as session:
        row = session.get(SnippetModel, snippet_id)
        if row is None:
            return None
        return _row_to_dict(row)


def _row_to_dict(row: SnippetModel) -> dict[str, Any]:
    """Convert an ORM row to the service interchange dict."""
    return {
        "id": row.id,
        "name": row.name,
        "language": row.language,
        "category": row.category,
        "body": row.body,
        "context": row.context,
        "scope_collection_id": row.scope_collection_id,
        "scope_local_script_id": row.scope_local_script_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "is_user": True,
    }
