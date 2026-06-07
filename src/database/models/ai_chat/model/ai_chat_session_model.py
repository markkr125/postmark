"""ORM model for AI chat session metadata (searchable index)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class AiChatSessionModel(Base):
    """One AI chat session row (SDK state lives on disk under ``session_disk_dir``)."""

    __tablename__ = "ai_chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True, default="")
    model_id: Mapped[str | None] = mapped_column(String(128), default=None)
    mode: Mapped[str] = mapped_column(String(32), default="agent", server_default="agent")
    agent_id: Mapped[str] = mapped_column(
        String(64),
        default="postmark-assistant",
        server_default="postmark-assistant",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        server_default=func.now(),
    )
    last_preview: Mapped[str | None] = mapped_column(Text, default=None)
    archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<AiChatSessionModel(id={self.id!r}, title={self.title!r})>"
