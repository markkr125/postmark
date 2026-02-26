"""SQLAlchemy model for the ``environments`` table."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ...base import Base


class EnvironmentModel(Base):
    """A named set of key-value variables (analogous to a Postman environment).

    Variables are stored as a JSON array of dicts, e.g.::

        [
            {"key": "base_url", "value": "https://api.example.com", "enabled": true, "type": "text"},
            {"key": "api_key", "value": "secret", "enabled": true, "type": "secret"},
        ]
    """

    __tablename__ = "environments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    values: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, default=None
    )  # [{key, value, enabled, type}]

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<EnvironmentModel(id={self.id}, name={self.name!r})>"
