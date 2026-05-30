"""SQLAlchemy model for the ``script_versions`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ...base import Base


class ScriptVersionModel(Base):
    """A snapshot of a script's content at a point in time.

    Each version records the full content of a single script editor
    (pre-request or test) for a request or collection.  Used for
    version history, diff viewing, and cross-session undo.
    """

    __tablename__ = "script_versions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("requests.id", ondelete="CASCADE"), default=None, index=True
    )
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), default=None, index=True
    )
    local_script_id: Mapped[int | None] = mapped_column(
        ForeignKey("local_scripts.id", ondelete="CASCADE"), default=None, index=True
    )
    script_type: Mapped[str] = mapped_column(
        String(20), index=True
    )  # pre_request | test | local_script
    content: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(20), default="javascript")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        owner = f"request={self.request_id}" if self.request_id else f"coll={self.collection_id}"
        return f"<ScriptVersionModel(id={self.id}, {owner}, type={self.script_type!r})>"
