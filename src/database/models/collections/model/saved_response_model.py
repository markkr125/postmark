"""SQLAlchemy model for the ``saved_responses`` table (Postman examples)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from ...base import Base

if TYPE_CHECKING:
    from .request_model import RequestModel


class SavedResponseModel(Base):
    """A saved HTTP response (example) belonging to a :class:`RequestModel`.

    Captures the full response snapshot: status, headers, body, and the
    original request that produced it.
    """

    __tablename__ = "saved_responses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(50), default=None)  # e.g. "OK"
    code: Mapped[int | None] = mapped_column(Integer, default=None)  # e.g. 200
    headers: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, default=None
    )  # [{key, value}]
    body: Mapped[str | None] = mapped_column(Text, default=None)
    preview_language: Mapped[str | None] = mapped_column(
        String(20), default=None
    )  # "json", "xml", "html", "text"
    original_request: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # snapshot of the request at time of response

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(server_default=func.now())

    # Relationship back to request
    request: Mapped[RequestModel] = relationship(back_populates="saved_responses")

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return (
            f"<SavedResponseModel(id={self.id}, name={self.name!r}, code={self.code})>"
        )
