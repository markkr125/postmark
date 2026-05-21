"""SQLAlchemy model for user-authored script snippets."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ...base import Base


class SnippetModel(Base):
    """A user-saved script snippet (name, body, language, scope, context).

    ``scope_collection_id`` and ``scope_local_script_id`` are both ``None`` for
    global snippets.  At most one scope column should be set.
    """

    __tablename__ = "snippets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    language: Mapped[str] = mapped_column(String(8), index=True)  # js | py | ts
    category: Mapped[str] = mapped_column(String(255), default="My snippets")
    body: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[str] = mapped_column(String(16), default="both")  # pre | test | both
    scope_collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"),
        default=None,
        index=True,
    )
    scope_local_script_id: Mapped[int | None] = mapped_column(
        ForeignKey("local_scripts.id", ondelete="CASCADE"),
        default=None,
        index=True,
    )
    created_at: Mapped[datetime | None] = mapped_column(server_default=func.now())

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<SnippetModel(id={self.id}, name={self.name!r}, lang={self.language!r})>"
