"""Shared fixtures for all tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from database.database import init_db

# ------------------------------------------------------------------
# Isolate QSettings so tests never overwrite user preferences
# ------------------------------------------------------------------
# Create the temp directory once at import time — before any QSettings
# instance is constructed — so that even session-scoped fixtures read
# from the sandbox rather than the real config path.
_settings_tmp = tempfile.mkdtemp(prefix="postmark_test_settings_")
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, _settings_tmp)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _settings_tmp)


# ------------------------------------------------------------------
# QApplication (session-scoped, created once for all UI tests)
# ------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Return the single QApplication instance shared across all tests.

    If an instance already exists (e.g. from pytest-qt) it is reused;
    otherwise a new one is created.
    """
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


# ------------------------------------------------------------------
# Fresh database (autouse, per-test)
# ------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Provide every test with a fresh, isolated SQLite database.

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


# ------------------------------------------------------------------
# Collection + request factory (convenience for UI & service tests)
# ------------------------------------------------------------------
@pytest.fixture()
def make_collection_with_request():
    """Factory that creates a persisted collection with one request.

    Returns ``(collection, request)`` — both are detached model snapshots.

    Usage::

        coll, req = make_collection_with_request()
        coll, req = make_collection_with_request(
            name="MyColl", method="POST", url="http://x", req_name="R",
        )
    """
    from services.collection_service import CollectionService

    def _make(
        name: str = "Coll",
        method: str = "GET",
        url: str = "http://x",
        req_name: str = "Req",
    ):
        svc = CollectionService()
        coll = svc.create_collection(name)
        req = svc.create_request(coll.id, method, url, req_name)
        return coll, req

    return _make
