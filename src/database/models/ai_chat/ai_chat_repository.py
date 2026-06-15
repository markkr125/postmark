"""Repository layer — CRUD for AI chat sessions and messages."""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from database.data_paths import session_disk_dir
from database.database import get_session

from .model.ai_chat_message_model import AiChatMessageModel
from .model.ai_chat_session_model import AiChatSessionModel

logger = logging.getLogger(__name__)

DEFAULT_AGENT_ID = "postmark-assistant"


def _session_to_dict(row: AiChatSessionModel) -> dict[str, Any]:
    """Convert a session ORM row to a plain dict."""
    created = row.created_at
    updated = row.updated_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return {
        "id": row.id,
        "title": row.title,
        "model_id": row.model_id,
        "mode": row.mode,
        "agent_id": row.agent_id,
        "created_at": created.isoformat(),
        "updated_at": updated.isoformat(),
        "last_preview": row.last_preview,
        "archived": row.archived,
    }


def _message_to_dict(row: AiChatMessageModel) -> dict[str, Any]:
    """Convert a message ORM row to a plain dict."""
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return {
        "id": row.id,
        "session_id": row.session_id,
        "role": row.role,
        "content": row.content,
        "thinking": row.thinking or "",
        "thinking_duration_seconds": row.thinking_duration_seconds,
        "model_id": row.model_id,
        "model_label": row.model_label,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "reasoning_tokens": row.reasoning_tokens,
        "created_at": created.isoformat(),
    }


def create_session(
    *,
    session_id: str,
    title: str,
    model_id: str | None,
    mode: str,
    agent_id: str = DEFAULT_AGENT_ID,
) -> dict[str, Any]:
    """Insert a new AI chat session row."""
    now = datetime.now(tz=UTC)
    with get_session() as session:
        row = AiChatSessionModel(
            id=session_id,
            title=title,
            model_id=model_id,
            mode=mode,
            agent_id=agent_id,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _session_to_dict(row)


def rename_session(session_id: str, title: str) -> dict[str, Any] | None:
    """Update the session title."""
    with get_session() as session:
        row = session.get(AiChatSessionModel, session_id)
        if row is None:
            return None
        row.title = title
        row.updated_at = datetime.now(tz=UTC)
        session.commit()
        session.refresh(row)
        return _session_to_dict(row)


def touch_session(
    session_id: str,
    *,
    last_preview: str | None = None,
) -> dict[str, Any] | None:
    """Bump ``updated_at`` and optionally set ``last_preview``."""
    with get_session() as session:
        row = session.get(AiChatSessionModel, session_id)
        if row is None:
            return None
        row.updated_at = datetime.now(tz=UTC)
        if last_preview is not None:
            row.last_preview = last_preview
        session.commit()
        session.refresh(row)
        return _session_to_dict(row)


def archive_session(session_id: str, *, archived: bool = True) -> dict[str, Any] | None:
    """Set the archived flag on a session."""
    with get_session() as session:
        row = session.get(AiChatSessionModel, session_id)
        if row is None:
            return None
        row.archived = archived
        row.updated_at = datetime.now(tz=UTC)
        session.commit()
        session.refresh(row)
        return _session_to_dict(row)


def delete_session(session_id: str) -> bool:
    """Delete message rows, the session row, and the SDK disk directory."""
    disk_path = session_disk_dir(session_id)
    with get_session() as session:
        row = session.get(AiChatSessionModel, session_id)
        if row is None:
            return False
        session.execute(
            delete(AiChatMessageModel).where(AiChatMessageModel.session_id == session_id)
        )
        session.delete(row)
        session.commit()
    if disk_path.is_dir():
        shutil.rmtree(disk_path)
    return True


def append_message(
    *,
    session_id: str,
    role: str,
    content: str,
    thinking: str = "",
    thinking_duration_seconds: int | None = None,
    model_id: str | None = None,
    model_label: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    reasoning_tokens: int | None = None,
) -> dict[str, Any]:
    """Append a message row to a session."""
    now = datetime.now(tz=UTC)
    with get_session() as session:
        row = AiChatMessageModel(
            session_id=session_id,
            role=role,
            content=content,
            thinking=thinking,
            thinking_duration_seconds=thinking_duration_seconds,
            model_id=model_id,
            model_label=model_label,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _message_to_dict(row)


def delete_message(message_id: int) -> str | None:
    """Delete one message row and return its session id, or ``None`` when missing."""
    with get_session() as session:
        row = session.get(AiChatMessageModel, message_id)
        if row is None:
            return None
        session_id = row.session_id
        session.delete(row)
        session.commit()
        return session_id


def get_session_row(session_id: str) -> dict[str, Any] | None:
    """Return one session dict or ``None``."""
    with get_session() as session:
        row = session.get(AiChatSessionModel, session_id)
        if row is None:
            return None
        return _session_to_dict(row)


def list_messages(session_id: str) -> list[dict[str, Any]]:
    """Return all messages for a session ordered by creation time."""
    with get_session() as session:
        stmt = (
            select(AiChatMessageModel)
            .where(AiChatMessageModel.session_id == session_id)
            .order_by(AiChatMessageModel.created_at.asc(), AiChatMessageModel.id.asc())
        )
        rows = session.scalars(stmt).all()
        return [_message_to_dict(r) for r in rows]


def get_last_assistant_usage_cumulative(session_id: str) -> dict[str, int] | None:
    """Return summed turn usage across assistant rows, or ``None`` when empty."""
    with get_session() as session:
        stmt = (
            select(AiChatMessageModel)
            .where(
                AiChatMessageModel.session_id == session_id,
                AiChatMessageModel.role == "assistant",
            )
            .order_by(AiChatMessageModel.id.asc())
        )
        rows = session.scalars(stmt).all()
        if not rows:
            return None
        prompt = 0
        completion = 0
        reasoning = 0
        has_usage = False
        for row in rows:
            if row.prompt_tokens is not None:
                prompt += int(row.prompt_tokens)
                has_usage = True
            if row.completion_tokens is not None:
                completion += int(row.completion_tokens)
                has_usage = True
            if row.reasoning_tokens is not None:
                reasoning += int(row.reasoning_tokens)
                has_usage = True
        if not has_usage:
            return None
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "reasoning_tokens": reasoning,
        }


def list_messages_up_to(session_id: str, message_id: int) -> list[dict[str, Any]]:
    """Return messages with ``id <= message_id`` ordered by creation time."""
    with get_session() as session:
        stmt = (
            select(AiChatMessageModel)
            .where(
                AiChatMessageModel.session_id == session_id,
                AiChatMessageModel.id <= message_id,
            )
            .order_by(AiChatMessageModel.created_at.asc(), AiChatMessageModel.id.asc())
        )
        rows = session.scalars(stmt).all()
        return [_message_to_dict(r) for r in rows]


def bulk_append_messages(
    session_id: str,
    messages: list[dict[str, Any]],
) -> None:
    """Insert copied message rows preserving content and usage fields."""
    if not messages:
        return
    now = datetime.now(tz=UTC)
    with get_session() as session:
        for msg in messages:
            created_raw = msg.get("created_at")
            created_at = now
            if isinstance(created_raw, str) and created_raw.strip():
                try:
                    created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                except ValueError:
                    created_at = now
            row = AiChatMessageModel(
                session_id=session_id,
                role=str(msg["role"]),
                content=str(msg.get("content") or ""),
                thinking=str(msg.get("thinking") or ""),
                thinking_duration_seconds=msg.get("thinking_duration_seconds"),
                model_id=msg.get("model_id"),
                model_label=msg.get("model_label"),
                prompt_tokens=msg.get("prompt_tokens"),
                completion_tokens=msg.get("completion_tokens"),
                reasoning_tokens=msg.get("reasoning_tokens"),
                created_at=created_at,
            )
            session.add(row)
        session.commit()
