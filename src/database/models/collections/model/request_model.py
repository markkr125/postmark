"""SQLAlchemy model for the ``requests`` table."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text, func

if TYPE_CHECKING:
    from .collection_model import CollectionModel
    from .saved_response_model import SavedResponseModel

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from ...base import Base


class RequestModel(Base):
    """A saved HTTP request belonging to a :class:`CollectionModel`."""

    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"))
    name: Mapped[str] = mapped_column(String(255), index=True)
    method: Mapped[str] = mapped_column(String(10))  # GET, POST, ...
    url: Mapped[str] = mapped_column(Text, index=True)
    body: Mapped[str | None] = mapped_column(Text, default=None)
    request_parameters: Mapped[str | None] = mapped_column(String, default=None)
    headers: Mapped[str | None] = mapped_column(String, default=None)

    # Optional text fields
    description: Mapped[str | None] = mapped_column(Text, default=None)

    # Body format metadata
    body_mode: Mapped[str | None] = mapped_column(
        String(20), default=None
    )  # "raw", "formdata", "urlencoded", "graphql", "file", "none"
    body_options: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # e.g. {"raw": {"language": "json"}}

    # Auth configuration
    auth: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # e.g. {"type": "bearer", "bearer": [{"key": "token", "value": "..."}]}

    # Structured JSON data
    scripts: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # e.g. {"pre_request": "...", "test": "..."}
    settings: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # e.g. {"timeout": 5000, "follow_redirects": true}
    events: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # e.g. {"pre_request": "...", "test": "..."}
    protocol_profile_behavior: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # Postman-specific request behavior overrides

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Relationship back to collection
    collection: Mapped[CollectionModel] = relationship(back_populates="requests")

    # One-to-many to saved responses (Postman examples)
    saved_responses: Mapped[list[SavedResponseModel]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<RequestModel(id={self.id}, method={self.method!r}, url={self.url!r})>"
