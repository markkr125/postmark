from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, func

if TYPE_CHECKING:
    from .request_model import RequestModel

from sqlalchemy.orm import Mapped, backref, mapped_column, relationship
from sqlalchemy.types import JSON

from ...base import Base


class CollectionModel(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("collections.id"), default=None
    )

    # Date fields
    created_at: Mapped[datetime | None] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # JSON fields
    events: Mapped[Any | None] = mapped_column(JSON, default=None)
    variables: Mapped[Any | None] = mapped_column(JSON, default=None)

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
    )

    def __repr__(self) -> str:
        return f"<CollectionModel(id={self.id}, name={self.name!r})>"
