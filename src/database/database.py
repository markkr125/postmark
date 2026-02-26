from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from .models.base import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state (initialised lazily by ``init_db``)
# ---------------------------------------------------------------------------
_engine: Engine | None = None
_SessionLocal: scoped_session | None = None


def init_db(db_path: Path | None = None) -> None:
    """
    Create the database engine, run DDL, and prepare the session factory.

    Call this **once** at application startup (before any UI is constructed).
    If *db_path* is ``None`` the default location
    ``<project_root>/data/database/main.db`` is used.
    """
    global _engine, _SessionLocal

    if db_path is None:
        project_root = Path(__file__).resolve().parents[2]
        db_path = project_root / "data" / "database" / "main.db"

    os.makedirs(db_path.parent, exist_ok=True)
    database_url = f"sqlite:///{db_path}"

    _engine = create_engine(database_url, echo=False, future=True)
    Base.metadata.create_all(_engine)

    _SessionLocal = scoped_session(
        sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    )
    logger.info("Database initialised: %s", database_url)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Provide a transactional scope around a series of operations.

    Usage::

        with get_session() as session:
            session.add(obj)
            # commit happens automatically; rollback on exception.
    """
    if _SessionLocal is None:
        raise RuntimeError("Database not initialised - call init_db() first")

    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
