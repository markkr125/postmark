from __future__ import annotations

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text,
                        func)
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from ...base import Base


class RequestModel(Base):
    __tablename__ = "requests"

    id                  = Column(Integer, primary_key=True, index=True)
    collection_id       = Column(Integer, ForeignKey("collections.id"), nullable=False)
    name                = Column(String(255), nullable=False, index=True)
    method              = Column(String(10), nullable=False)   # GET, POST, …
    url                 = Column(Text, nullable=False, index=True)
    body                = Column(Text, nullable=True)
    request_parameters  = Column(String, nullable=True)
    headers             = Column(String, nullable=True)

    # Structured JSON data
    scripts             = Column(JSON, nullable=True)
    settings            = Column(JSON, nullable=True)
    events              = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationship back to collection
    collection = relationship("CollectionModel", back_populates="requests")

    def __repr__(self) -> str:
        return f"<Request(id={self.id}, method={self.method!r}, url={self.url!r})>"
