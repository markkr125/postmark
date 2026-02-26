"""SQLAlchemy model for the ``collections`` table -- self-referencing tree."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text, func

if TYPE_CHECKING:
    from .request_model import RequestModel

from sqlalchemy.orm import Mapped, backref, mapped_column, relationship
from sqlalchemy.types import JSON

from ...base import Base


class CollectionModel(Base):
    """A folder in the collection hierarchy.

    Collections form a self-referencing tree via ``parent_id``.  Deleting a
    parent cascades to all children and their requests.
    """

    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("collections.id"), default=None)

    # Date fields
    created_at: Mapped[datetime | None] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Optional text fields
    description: Mapped[str | None] = mapped_column(Text, default=None)

    # JSON fields
    events: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # e.g. {"pre_request": "...", "test": "..."}
    variables: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, default=None
    )  # e.g. [{"key": "host", "value": "localhost"}]
    auth: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # e.g. {"type": "bearer", "bearer": [{"key": "token", "value": "..."}]}

    # Self-referencing relationship - gives you collection.children
    children: Mapped[list[CollectionModel]] = relationship(
        backref=backref("parent", remote_side=[id]),
        cascade="all, delete-orphan",
        single_parent=True,
        lazy="selectin",
    )

    # One-to-many to requests
    requests: Mapped[list[RequestModel]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<CollectionModel(id={self.id}, name={self.name!r})>"
