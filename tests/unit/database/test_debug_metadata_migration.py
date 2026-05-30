"""Migration test for ``local_scripts.debug_metadata``."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import inspect

import database.database as db_mod
from database.database import init_db


def test_init_db_adds_debug_metadata_column(tmp_path: Path) -> None:
    """``_migrate_add_missing_columns`` adds JSON column on an old schema file."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE local_scripts (
                id INTEGER PRIMARY KEY,
                folder_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                language VARCHAR(32),
                module_format VARCHAR(16) NOT NULL DEFAULT 'esm',
                content TEXT,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    db_mod._engine = None
    db_mod._SessionLocal = None
    init_db(db_path)
    assert db_mod._engine is not None
    insp = inspect(db_mod._engine)
    cols = {c["name"] for c in insp.get_columns("local_scripts")}
    assert "debug_metadata" in cols
