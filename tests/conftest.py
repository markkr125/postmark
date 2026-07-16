"""Shared fixtures for all tests."""

from __future__ import annotations

import atexit
import os
import tempfile
from collections.abc import Generator
from pathlib import Path

# Render Qt offscreen so parallel UI tests do not open windows on the developer
# desktop (same as CI). Explicit QT_QPA_PLATFORM in the environment wins;
# set POSTMARK_TEST_VISIBLE=1 to skip forcing offscreen when debugging widgets.
if os.environ.get("POSTMARK_TEST_VISIBLE", "").lower() not in ("1", "true", "yes"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Isolate QSettings before any other import constructs QSettings("Postmark", …).
_settings_tmp = tempfile.mkdtemp(prefix="postmark_test_settings_")
from PySide6.QtCore import QSettings  # noqa: E402

QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, _settings_tmp)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _settings_tmp)

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from database.database import init_db  # noqa: E402
from qt_app_init import configure_before_qapplication  # noqa: E402
from services.scripting._subprocess_env import reap_zombie_children  # noqa: E402

configure_before_qapplication()


def _cleanup_test_process_leaks() -> None:
    """Drop stale GUI log sinks and reap sandbox child zombies."""
    from services.ai.ai_logging import set_ui_log_sink

    set_ui_log_sink(None)
    reap_zombie_children()


atexit.register(_cleanup_test_process_leaks)


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    """Cap parallel workers so sandbox subprocess tests do not OOM the desktop."""
    _ = config
    cpu = os.cpu_count() or 4
    return max(1, min(cpu, 8))


@pytest.fixture(autouse=True)
def _reset_ai_ui_log_sink() -> Generator[None, None, None]:
    """Prevent deleted settings dialogs from staying registered as AI log sinks."""
    yield
    from services.ai.ai_logging import set_ui_log_sink

    set_ui_log_sink(None)


@pytest.fixture(autouse=True)
def _clear_mutation_bridge_queue() -> Generator[None, None, None]:
    """Isolate Agent mutate/execute GUI bridge events across tests."""
    from services.ai.chat.mutation.bridge import clear_mutation_events

    clear_mutation_events()
    yield
    clear_mutation_events()


@pytest.fixture(autouse=True)
def _reap_child_processes() -> Generator[None, None, None]:
    """Reap sandbox and worker child zombies so repeated runs do not accumulate."""
    yield
    reap_zombie_children()


# ------------------------------------------------------------------
# QApplication (session-scoped, created once for all UI tests)
# ------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    """Return the single QApplication instance shared across all tests.

    If an instance already exists (e.g. from pytest-qt) it is reused;
    otherwise a new one is created.
    """
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    app.setApplicationName("PostmarkTests")
    app.setApplicationDisplayName("Postmark Tests")
    yield app
    from tests.qt_popup_cleanup import dismiss_all_top_level_test_widgets

    dismiss_all_top_level_test_widgets(app)
    _cleanup_test_process_leaks()


# ------------------------------------------------------------------
# Fresh database (autouse, per-test)
# ------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolated_request_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep send-history payloads out of the developer's real user-data history tree.

    Without this, ``init_db()`` → ``reconcile_orphans()`` on an empty per-test
    SQLite DB would delete bodies in the real storage directory while metadata
    in ``data/database/main.db`` remained — the “erased after restart” symptom.
    """
    history = tmp_path / "history"

    def _history() -> Path:
        history.mkdir(parents=True, exist_ok=True)
        return history

    monkeypatch.setattr("database.data_paths.user_history_root", _history)


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _isolated_request_history: None):
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


@pytest.fixture(autouse=True)
def _isolated_postmark_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect ``postmark_user_data_dir()`` to a temp folder for every test."""
    root = tmp_path / "postmark"

    def _root() -> Path:
        root.mkdir(parents=True, exist_ok=True)
        return root

    monkeypatch.setattr("database.data_paths.postmark_user_data_dir", _root)


@pytest.fixture(autouse=True)
def _isolated_lsp_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test its own Deno LSP workspace directory.

    The mirror (``local/``), ``deno.json`` and ambient stubs live under
    ``user_lsp_root``. Local-script mutations sync there via
    ``LocalScriptService._refresh_mirror``; without per-test isolation, parallel
    (xdist) workers share the real ``~/.local/share/postmark`` workspace and
    ``sync_all``'s orphan prune races delete each other's mirror files — a flaky
    error that moves between tests.

    Patch ``user_lsp_root`` directly rather than ``XDG_DATA_HOME``: the managed
    Deno runtime also lives under ``XDG_DATA_HOME`` (see ``DenoManager``), so
    redirecting the env var would hide Deno and skip every runtime test.
    """
    ws_root = tmp_path / "lsp-workspace"

    def _root() -> Path:
        ws_root.mkdir(parents=True, exist_ok=True)
        return ws_root

    monkeypatch.setattr("services.lsp.servers._workspace.user_lsp_root", _root)


@pytest.fixture(autouse=True)
def _reset_tab_settings() -> None:
    """Clear persisted tab settings so tests do not leak UI preferences."""
    settings = QSettings("Postmark", "Postmark")
    settings.remove("tabs")
    settings.remove("scripts")
    settings.remove("ai")
    settings.remove("ui/kv_col_widths")
    settings.sync()


@pytest.fixture(autouse=True)
def _disable_script_lsp_in_tests() -> Generator[None, None, None]:
    """Do not spawn Deno/jedi LSP servers unless a test enables ``scripting/lsp_enabled``."""
    settings = QSettings("Postmark", "Postmark")
    settings.setValue("scripting/lsp_enabled", False)
    yield


@pytest.fixture(autouse=True)
def _shutdown_lsp_clients(qapp: QApplication) -> Generator[None, None, None]:
    """Stop LSP subprocess threads after each test so Qt teardown stays clean."""
    yield
    from PySide6.QtCore import QThreadPool

    from services.lsp.server_registry import LspRegistry, reset_registry_for_tests

    inst = LspRegistry._instance
    if inst is not None:
        inst.shutdown()
    reset_registry_for_tests()
    QThreadPool.globalInstance().waitForDone(5000)
    qapp.processEvents()


@pytest.fixture(autouse=True)
def _reset_code_editor_popups_after_test(qapp: QApplication) -> Generator[None, None, None]:
    """Dismiss app-wide completion/hint popups so non-``tests/ui`` Qt tests cannot leave windows up."""
    yield
    from PySide6.QtCore import QThreadPool

    from tests.qt_popup_cleanup import (
        dismiss_all_top_level_test_widgets,
        flush_deferred_widget_deletes,
        reset_code_editor_popups,
    )

    reset_code_editor_popups()
    QThreadPool.globalInstance().waitForDone(5000)
    qapp.processEvents()
    dismiss_all_top_level_test_widgets(qapp)
    flush_deferred_widget_deletes(qapp)


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
