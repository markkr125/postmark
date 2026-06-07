"""Read-only queries for AI chat sessions and messages."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from database.database import get_session as db_session

from .ai_chat_repository import _session_to_dict
from .model.ai_chat_message_model import AiChatMessageModel
from .model.ai_chat_session_model import AiChatSessionModel


def list_sessions(
    *,
    search: str | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """List sessions ordered by ``updated_at`` descending."""
    with db_session() as session:
        stmt = select(AiChatSessionModel)
        if not include_archived:
            stmt = stmt.where(AiChatSessionModel.archived.is_(False))
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(AiChatSessionModel.title.like(pattern))
        stmt = stmt.order_by(AiChatSessionModel.updated_at.desc())
        rows = session.scalars(stmt).all()
        return [_session_to_dict(r) for r in rows]


def get_session_by_id(session_id: str) -> dict[str, Any] | None:
    """Return one session dict or ``None``."""
    with db_session() as db:
        row = db.get(AiChatSessionModel, session_id)
        if row is None:
            return None
        return _session_to_dict(row)


def search_messages(query: str) -> list[dict[str, Any]]:
    """Return sessions whose title or any message content matches *query*."""
    pattern = f"%{query}%"
    with db_session() as session:
        title_ids = session.scalars(
            select(AiChatSessionModel.id).where(AiChatSessionModel.title.like(pattern))
        ).all()
        message_ids = session.scalars(
            select(AiChatMessageModel.session_id)
            .where(AiChatMessageModel.content.like(pattern))
            .distinct()
        ).all()
        session_ids = list(dict.fromkeys([*title_ids, *message_ids]))
        if not session_ids:
            return []
        stmt = (
            select(AiChatSessionModel)
            .where(AiChatSessionModel.id.in_(session_ids))
            .order_by(AiChatSessionModel.updated_at.desc())
        )
        rows = session.scalars(stmt).all()
        return [_session_to_dict(r) for r in rows]
