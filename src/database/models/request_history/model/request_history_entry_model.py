"""ORM model for persisted HTTP send history entries."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class RequestHistoryEntryModel(Base):
    """One recorded main-window Send (metadata in SQLite; bodies on disk)."""

    __tablename__ = "request_history_entries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        server_default=func.now(),
    )
    request_id: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    was_persisted_request: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    request_name: Mapped[str] = mapped_column(String(255), default="")
    method: Mapped[str] = mapped_column(String(10), default="GET")
    url: Mapped[str] = mapped_column(Text, default="")
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    response_headers: Mapped[list | dict | None] = mapped_column(JSON, default=None)
    response_body_path: Mapped[str | None] = mapped_column(String(512), default=None)
    body_truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    response_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    request_snapshot_path: Mapped[str | None] = mapped_column(String(512), default=None)

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return (
            f"<RequestHistoryEntryModel(id={self.id}, method={self.method!r}, "
            f"status={self.status_code})>"
        )
