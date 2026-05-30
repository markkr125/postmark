"""SQLAlchemy model for user-authored script snippets."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ...base import Base


class SnippetModel(Base):
    """A user-saved script snippet (name, body, language, context)."""

    __tablename__ = "snippets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    language: Mapped[str] = mapped_column(String(8), index=True)  # js | py | ts
    category: Mapped[str] = mapped_column(String(255), default="My snippets")
    body: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[str] = mapped_column(String(16), default="both")  # pre | test | both
    created_at: Mapped[datetime | None] = mapped_column(server_default=func.now())

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<SnippetModel(id={self.id}, name={self.name!r}, lang={self.language!r})>"
