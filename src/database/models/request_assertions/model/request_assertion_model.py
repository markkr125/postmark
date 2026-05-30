"""SQLAlchemy model for the ``request_assertions`` table."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...base import Base

if TYPE_CHECKING:
    from database.models.collections.model.request_model import RequestModel


class RequestAssertionModel(Base):
    """A declarative test assertion row attached to a saved request."""

    __tablename__ = "request_assertions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("requests.id", ondelete="CASCADE"),
        index=True,
    )
    subject: Mapped[str] = mapped_column(String(255), default="")
    operator: Mapped[str] = mapped_column(String(20), default="eq")
    expected: Mapped[str | None] = mapped_column(Text, default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    request: Mapped[RequestModel] = relationship(back_populates="assertions")

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return (
            f"<RequestAssertionModel(id={self.id}, request_id={self.request_id}, "
            f"subject={self.subject!r}, operator={self.operator!r})>"
        )
