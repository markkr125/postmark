"""Repository layer -- CRUD functions for environments.

UI code must **not** import this directly -- use the service layer instead.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, update

from database.database import get_session

from .model.environment_model import EnvironmentModel

logger = logging.getLogger(__name__)


def fetch_all_environments() -> list[dict[str, Any]]:
    """Return every environment as a list of dicts.

    Each dict contains ``id``, ``name``, and ``values``.
    """
    with get_session() as session:
        stmt = select(EnvironmentModel)
        envs = list(session.execute(stmt).scalars().all())
        return [
            {
                "id": env.id,
                "name": env.name,
                "values": env.values or [],
            }
            for env in envs
        ]


def create_environment(
    name: str,
    values: list[dict[str, Any]] | None = None,
) -> EnvironmentModel:
    """Create a new environment with the given *name* and optional *values*.

    Returns:
        The created ``EnvironmentModel`` instance.
    """
    with get_session() as session:
        env = EnvironmentModel(name=name, values=values)
        session.add(env)
        session.flush()
        session.refresh(env)
        return env


def get_environment_by_id(environment_id: int) -> EnvironmentModel | None:
    """Return the environment with the given *environment_id*, or ``None``."""
    with get_session() as session:
        return (
            session.execute(select(EnvironmentModel).where(EnvironmentModel.id == environment_id))
            .scalars()
            .first()
        )


def rename_environment(environment_id: int, new_name: str) -> None:
    """Update the ``name`` of the environment with the given *environment_id*."""
    with get_session() as session:
        stmt = (
            update(EnvironmentModel)
            .where(EnvironmentModel.id == environment_id)
            .values(name=new_name)
        )
        session.execute(stmt)


def delete_environment(environment_id: int) -> None:
    """Delete the environment with the given *environment_id*."""
    with get_session() as session:
        env = session.get(EnvironmentModel, environment_id)
        if env is None:
            raise ValueError(f"No environment found with id={environment_id}")
        session.delete(env)
