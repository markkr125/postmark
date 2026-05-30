"""SQLAlchemy model for the ``run_results`` table.

Stores per-request results from a collection runner execution — status
code, elapsed time, test pass/fail counts, and error messages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from ...base import Base

if TYPE_CHECKING:
    from .run_history_model import RunHistoryModel


class RunResultModel(Base):
    """A single request result within a collection run.

    Each row records the outcome of one request execution — HTTP status,
    timing, test verdicts, and any error message.
    """

    __tablename__ = "run_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("run_history.id", ondelete="CASCADE"), index=True
    )
    request_name: Mapped[str] = mapped_column(String(255), default="")
    request_method: Mapped[str] = mapped_column(String(10), default="GET")
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_ms: Mapped[float] = mapped_column(Float, default=0.0)
    test_passed: Mapped[int] = mapped_column(Integer, default=0)
    test_failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    test_results: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=None)

    run: Mapped[RunHistoryModel] = relationship(back_populates="results")

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return (
            f"<RunResultModel(id={self.id}, run={self.run_id}, "
            f"name={self.request_name!r}, status={self.status_code})>"
        )
