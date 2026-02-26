from __future__ import annotations

from sqlalchemy import (JSON, Column, DateTime, ForeignKey, Integer, String,
                        func)
from sqlalchemy.orm import backref, relationship

from ...base import Base


class CollectionModel(Base):
    __tablename__ = "collections"

    id        = Column(Integer, primary_key=True, index=True)
    name      = Column(String(255), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("collections.id"), nullable=True)

    # Date fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # New JSON field for storing collection-specific data
    events    = Column(JSON, nullable=True)

    # New JSON field for storing variables
    variables = Column(JSON, nullable=True)  # New field for storing variables

    # Self-referencing relationship - gives you collection.children
    children = relationship(
        "CollectionModel",
        backref=backref("parent", remote_side=[id]),   # gives you child.parent
        cascade="all, delete-orphan",
        single_parent=True,
        lazy="selectin",            # eager-load the children in a single query
    )

    # One-to-many to requests
    requests = relationship(
        "RequestModel",
        back_populates="collection",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<CollectionModel(id={self.id}, name={self.name!r})>"
