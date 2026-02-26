"""Shared fixtures for all tests."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from database.database import init_db


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Provide every test with a fresh, isolated SQLite database.

    The database is created in a temporary directory and torn down
    automatically when the test finishes.
    """
    import database.database as db_mod

    # Reset module-level state so init_db() can run again
    db_mod._engine = None
    db_mod._SessionLocal = None

    db_path = tmp_path / "test.db"
    init_db(db_path)

    yield

    # Cleanup: reset state for the next test
    db_mod._engine = None
    db_mod._SessionLocal = None
