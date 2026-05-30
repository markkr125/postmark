"""SQLAlchemy model for the ``local_scripts`` table."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .local_script_folder_model import LocalScriptFolderModel

from ...base import Base


class LocalScriptModel(Base):
    """A saved local script belonging to a :class:`LocalScriptFolderModel`."""

    __tablename__ = "local_scripts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("local_script_folders.id"))
    name: Mapped[str] = mapped_column(String(255), index=True)
    language: Mapped[str] = mapped_column(String(32), default="javascript")
    module_format: Mapped[str] = mapped_column(String(16), nullable=False, server_default="esm")
    content: Mapped[str | None] = mapped_column(Text, default="")
    debug_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

    created_at: Mapped[datetime | None] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    folder: Mapped[LocalScriptFolderModel] = relationship(back_populates="scripts")

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<LocalScriptModel(id={self.id}, name={self.name!r})>"
