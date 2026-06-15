"""ORM model for AI chat message rows (searchable transcript index)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class AiChatMessageModel(Base):
    """One message in an AI chat session transcript."""

    __tablename__ = "ai_chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, index=True, default="")
    thinking: Mapped[str] = mapped_column(Text, default="", server_default="")
    thinking_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return (
            f"<AiChatMessageModel(id={self.id}, session_id={self.session_id!r}, "
            f"role={self.role!r})>"
        )
