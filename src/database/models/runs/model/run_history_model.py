"""SQLAlchemy model for the ``run_history`` table.

Stores metadata for each collection runner execution — which collection
was run, when it started/finished, and aggregate test statistics.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...base import Base

if TYPE_CHECKING:
    from .run_result_model import RunResultModel


class RunHistoryModel(Base):
    """A single collection runner execution.

    Each row represents one Run invocation (potentially with multiple
    iterations).  Aggregate statistics are updated as the run progresses
    and finalised when the run completes.
    """

    __tablename__ = "run_history"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    avg_response_ms: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="running")
    iterations: Mapped[int] = mapped_column(Integer, default=1)

    results: Mapped[list[RunResultModel]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return (
            f"<RunHistoryModel(id={self.id}, collection={self.collection_id}, "
            f"status={self.status!r})>"
        )
