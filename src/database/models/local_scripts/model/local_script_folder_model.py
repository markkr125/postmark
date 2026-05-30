"""SQLAlchemy model for the ``local_script_folders`` table."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

if TYPE_CHECKING:
    from .local_script_model import LocalScriptModel

from ...base import Base


class LocalScriptFolderModel(Base):
    """A folder in the local-scripts hierarchy (mirrors :class:`CollectionModel`)."""

    __tablename__ = "local_script_folders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("local_script_folders.id"),
        default=None,
    )

    created_at: Mapped[datetime | None] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    children: Mapped[list[LocalScriptFolderModel]] = relationship(
        backref=backref("parent", remote_side=[id]),
        cascade="all, delete-orphan",
        single_parent=True,
        lazy="selectin",
    )

    scripts: Mapped[list[LocalScriptModel]] = relationship(
        back_populates="folder",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<LocalScriptFolderModel(id={self.id}, name={self.name!r})>"
