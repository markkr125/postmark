from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from sqlalchemy import Table, create_engine, inspect, text
from sqlalchemy.schema import CreateTable
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Import all models so Base.metadata.create_all() discovers every table.
from .models import CollectionModel as CollectionModel
from .models import EnvironmentModel as EnvironmentModel
from .models import LocalScriptFolderModel as LocalScriptFolderModel
from .models import LocalScriptModel as LocalScriptModel
from .models import RequestAssertionModel as RequestAssertionModel
from .models import RequestModel as RequestModel
from .models import RunHistoryModel as RunHistoryModel
from .models import RunResultModel as RunResultModel
from .models import SavedResponseModel as SavedResponseModel
from .models import ScriptVersionModel as ScriptVersionModel
from .models import SnippetModel as SnippetModel
from .models.base import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state (initialised lazily by ``init_db``)
# ---------------------------------------------------------------------------
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_db(db_path: Path | None = None) -> None:
    """Create the database engine, run DDL, and prepare the session factory.

    Safe to call multiple times: if the engine already exists, returns
    immediately without re-running DDL. Tests reset module-level state and call
    ``init_db`` again with a fresh path via ``_fresh_db`` in ``conftest.py``.

    At application startup, call before any database access. If *db_path* is
    ``None`` the default location ``<project_root>/data/database/main.db`` is
    used.
    """
    global _engine, _SessionLocal

    if _engine is not None:
        return

    if db_path is None:
        project_root = Path(__file__).resolve().parents[2]
        db_path = project_root / "data" / "database" / "main.db"

    os.makedirs(db_path.parent, exist_ok=True)
    database_url = f"sqlite:///{db_path}"

    _engine = create_engine(
        database_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Enable WAL journal mode for concurrent read access from worker threads.
    with _engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()
    Base.metadata.create_all(_engine)
    _migrate_add_missing_columns(_engine)
    _migrate_drop_snippet_scope_columns(_engine)

    _SessionLocal = sessionmaker(
        bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    logger.info("Database initialised: %s", database_url)


# ---------------------------------------------------------------------------
# Lightweight schema migration — add missing columns to existing tables
# ---------------------------------------------------------------------------

# Map SQLAlchemy Python types to SQLite column type strings.
_TYPE_MAP: dict[str, str] = {
    "VARCHAR": "VARCHAR",
    "TEXT": "TEXT",
    "INTEGER": "INTEGER",
    "JSON": "JSON",
    "DATETIME": "DATETIME",
    "FLOAT": "FLOAT",
    "BOOLEAN": "BOOLEAN",
}


def _migration_default_clause(col: object) -> str:
    """Return a SQLite ``DEFAULT`` fragment from an ORM column ``server_default``."""
    from sqlalchemy.schema import Column

    if not isinstance(col, Column):
        return ""
    default = col.server_default
    if default is None:
        return ""
    arg = getattr(default, "arg", None)
    if isinstance(arg, str):
        escaped = arg.replace("'", "''")
        return f" DEFAULT '{escaped}'"
    return ""


def _migrate_add_missing_columns(engine: Engine) -> None:
    """Add missing columns to existing tables via ALTER TABLE.

    Inspects every mapped table and issues ``ALTER TABLE ADD COLUMN`` for
    any columns that exist in the ORM model but are absent on disk.
    This is a forward-only migration: it never drops or renames columns.
    """
    insp = inspect(engine)

    for table in Base.metadata.sorted_tables:
        table_name = table.name
        if not insp.has_table(table_name):
            # Table was just created by create_all() — nothing to migrate.
            continue

        existing_cols = {col["name"] for col in insp.get_columns(table_name)}

        for col in table.columns:
            if col.name in existing_cols:
                continue

            # Derive the SQLite type string from the compiled column type.
            col_type = col.type.compile(dialect=engine.dialect)
            null_sql = "" if col.nullable else " NOT NULL"
            default_sql = _migration_default_clause(col)
            alter_sql = (
                f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}{null_sql}{default_sql}"
            )
            logger.info("Migrating: %s", alter_sql)

            with engine.begin() as conn:
                conn.execute(text(alter_sql))


def _migrate_drop_snippet_scope_columns(engine: Engine) -> None:
    """One-time rebuild of ``snippets`` to drop legacy ``scope_*`` columns.

    SQLite cannot ``DROP`` indexed/foreign-key columns, so rebuild the table
    from the current ORM definition and copy the surviving rows. Idempotent:
    a no-op once the columns are gone or on a freshly created database.
    """
    insp = inspect(engine)
    if not insp.has_table("snippets"):
        return
    existing = {col["name"] for col in insp.get_columns("snippets")}
    legacy = {"scope_collection_id", "scope_local_script_id"}
    if not (existing & legacy):
        return
    table = cast(Table, SnippetModel.__table__)  # new schema (scope columns already removed)
    cols = ", ".join(col.name for col in table.columns)
    logger.info("Migrating: rebuilding snippets to drop %s", sorted(existing & legacy))
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS snippets__old"))
        conn.execute(text("ALTER TABLE snippets RENAME TO snippets__old"))
        conn.execute(CreateTable(table))
        conn.execute(text(f"INSERT INTO snippets ({cols}) SELECT {cols} FROM snippets__old"))
        conn.execute(text("DROP TABLE snippets__old"))
        for index in table.indexes:
            index.create(bind=conn)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations.

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
