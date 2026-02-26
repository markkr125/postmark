from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text, func

if TYPE_CHECKING:
    from .collection_model import CollectionModel

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from ...base import Base


class RequestModel(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id")
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    method: Mapped[str] = mapped_column(String(10))  # GET, POST, ...
    url: Mapped[str] = mapped_column(Text, index=True)
    body: Mapped[str | None] = mapped_column(Text, default=None)
    request_parameters: Mapped[str | None] = mapped_column(String, default=None)
    headers: Mapped[str | None] = mapped_column(String, default=None)

    # Structured JSON data
    scripts: Mapped[Any | None] = mapped_column(JSON, default=None)
    settings: Mapped[Any | None] = mapped_column(JSON, default=None)
    events: Mapped[Any | None] = mapped_column(JSON, default=None)

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Relationship back to collection
    collection: Mapped[CollectionModel] = relationship(back_populates="requests")

    def __repr__(self) -> str:
        return f"<Request(id={self.id}, method={self.method!r}, url={self.url!r})>"
