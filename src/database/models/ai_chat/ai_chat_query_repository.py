"""Read-only queries for AI chat sessions and messages."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select

from database.database import get_session as db_session

from .ai_chat_repository import _session_to_dict
from .model.ai_chat_message_model import AiChatMessageModel
from .model.ai_chat_session_model import AiChatSessionModel

_FORK_SUFFIX_RE = re.compile(r"^(.+) \((\d+)\)$")
_SESSION_TITLE_MAX_LEN = 255


def fork_base_title(title: str) -> str:
    """Return the root title without a trailing `` (N)`` fork suffix."""
    cleaned = (title or "Chat").strip() or "Chat"
    match = _FORK_SUFFIX_RE.fullmatch(cleaned)
    return match.group(1) if match else cleaned


def is_fork_family_title(title: str, base_title: str) -> bool:
    """Return whether *title* is *base_title* or ``base_title (N)``."""
    if title == base_title:
        return True
    match = _FORK_SUFFIX_RE.fullmatch(title)
    return match is not None and match.group(1) == base_title


def count_fork_family_sessions(
    base_title: str,
    *,
    exclude_session_id: str | None = None,
) -> int:
    """Count non-archived sessions whose title matches the fork family for *base_title*."""
    with db_session() as session:
        stmt = select(AiChatSessionModel.id, AiChatSessionModel.title).where(
            AiChatSessionModel.archived.is_(False)
        )
        if exclude_session_id is not None:
            stmt = stmt.where(AiChatSessionModel.id != exclude_session_id)
        rows = session.execute(stmt).all()
    return sum(1 for _sid, title in rows if is_fork_family_title(title, base_title))


def allocate_fork_session_title(source_session_id: str, source_title: str) -> str:
    """Allocate ``{base title} (N)`` where *N* is the family size in the index + 1."""
    base = fork_base_title(source_title)
    count = count_fork_family_sessions(base, exclude_session_id=source_session_id) + 1
    suffix = f" ({count})"
    if len(base) + len(suffix) > _SESSION_TITLE_MAX_LEN:
        trim = _SESSION_TITLE_MAX_LEN - len(suffix) - 1
        base = base[:trim] + "…"
    return f"{base}{suffix}"


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


def get_session_with_messages(
    session_id: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Return session metadata and ordered messages in one read transaction."""
    from .ai_chat_repository import _message_to_dict

    with db_session() as db:
        row = db.get(AiChatSessionModel, session_id)
        if row is None:
            return None, []
        stmt = (
            select(AiChatMessageModel)
            .where(AiChatMessageModel.session_id == session_id)
            .order_by(AiChatMessageModel.created_at.asc(), AiChatMessageModel.id.asc())
        )
        messages = [_message_to_dict(message_row) for message_row in db.scalars(stmt).all()]
        return _session_to_dict(row), messages


def _ordered_messages_stmt(session_id: str):
    """Base statement for chronologically ordered session messages."""
    return (
        select(AiChatMessageModel)
        .where(AiChatMessageModel.session_id == session_id)
        .order_by(AiChatMessageModel.created_at.asc(), AiChatMessageModel.id.asc())
    )


def list_messages_tail(
    session_id: str,
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Return the newest *limit* messages (oldest-first) and whether older rows exist."""
    from .ai_chat_repository import _message_to_dict

    if limit <= 0:
        return [], False
    probe = limit + 1
    with db_session() as db:
        stmt = (
            select(AiChatMessageModel)
            .where(AiChatMessageModel.session_id == session_id)
            .order_by(AiChatMessageModel.created_at.desc(), AiChatMessageModel.id.desc())
            .limit(probe)
        )
        rows = list(db.scalars(stmt).all())
    has_older = len(rows) > limit
    slice_rows = rows[:limit]
    slice_rows.reverse()
    return [_message_to_dict(row) for row in slice_rows], has_older


def list_messages_before(
    session_id: str,
    *,
    before_id: int,
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Return up to *limit* messages strictly before *before_id* (oldest-first)."""
    from .ai_chat_repository import _message_to_dict

    if limit <= 0:
        return [], False
    probe = limit + 1
    with db_session() as db:
        anchor = db.get(AiChatMessageModel, before_id)
        if anchor is None or anchor.session_id != session_id:
            return [], False
        stmt = (
            select(AiChatMessageModel)
            .where(AiChatMessageModel.session_id == session_id)
            .where(
                (AiChatMessageModel.created_at < anchor.created_at)
                | (
                    (AiChatMessageModel.created_at == anchor.created_at)
                    & (AiChatMessageModel.id < anchor.id)
                )
            )
            .order_by(AiChatMessageModel.created_at.desc(), AiChatMessageModel.id.desc())
            .limit(probe)
        )
        rows = list(db.scalars(stmt).all())
    has_older = len(rows) > limit
    slice_rows = rows[:limit]
    slice_rows.reverse()
    return [_message_to_dict(row) for row in slice_rows], has_older


def list_messages_after(
    session_id: str,
    *,
    after_id: int,
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Return up to *limit* messages strictly after *after_id* (oldest-first)."""
    from .ai_chat_repository import _message_to_dict

    if limit <= 0:
        return [], False
    probe = limit + 1
    with db_session() as db:
        anchor = db.get(AiChatMessageModel, after_id)
        if anchor is None or anchor.session_id != session_id:
            return [], False
        stmt = (
            select(AiChatMessageModel)
            .where(AiChatMessageModel.session_id == session_id)
            .where(
                (AiChatMessageModel.created_at > anchor.created_at)
                | (
                    (AiChatMessageModel.created_at == anchor.created_at)
                    & (AiChatMessageModel.id > anchor.id)
                )
            )
            .order_by(AiChatMessageModel.created_at.asc(), AiChatMessageModel.id.asc())
            .limit(probe)
        )
        rows = list(db.scalars(stmt).all())
    has_newer = len(rows) > limit
    return [_message_to_dict(row) for row in rows[:limit]], has_newer


def count_messages(session_id: str) -> int:
    """Return the number of messages in *session_id*."""
    from sqlalchemy import func

    with db_session() as db:
        count = db.scalar(
            select(func.count())
            .select_from(AiChatMessageModel)
            .where(AiChatMessageModel.session_id == session_id)
        )
    return int(count or 0)


def list_assistant_usage_messages(
    *,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return assistant messages with token usage, optionally filtered by ``created_at``."""
    from datetime import UTC

    from .ai_chat_repository import _message_to_dict

    with db_session() as db:
        stmt = (
            select(AiChatMessageModel)
            .where(AiChatMessageModel.role == "assistant")
            .where(
                (
                    AiChatMessageModel.prompt_tokens.is_not(None)
                    & (AiChatMessageModel.prompt_tokens > 0)
                )
                | (
                    AiChatMessageModel.completion_tokens.is_not(None)
                    & (AiChatMessageModel.completion_tokens > 0)
                )
                | (
                    AiChatMessageModel.reasoning_tokens.is_not(None)
                    & (AiChatMessageModel.reasoning_tokens > 0)
                )
            )
            .order_by(AiChatMessageModel.created_at.asc(), AiChatMessageModel.id.asc())
        )
        if created_from is not None:
            start = created_from
            if start.tzinfo is None:
                start = start.replace(tzinfo=UTC)
            stmt = stmt.where(AiChatMessageModel.created_at >= start)
        if created_to is not None:
            end = created_to
            if end.tzinfo is None:
                end = end.replace(tzinfo=UTC)
            stmt = stmt.where(AiChatMessageModel.created_at < end)
        rows = list(db.scalars(stmt).all())
    return [_message_to_dict(row) for row in rows]


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
