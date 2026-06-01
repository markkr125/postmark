"""Shared fixtures and helpers for UI tests."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from ui.collections.collection_widget import CollectionWidget
from ui.collections.tree import CollectionTree


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _no_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent CollectionWidget from spawning a background fetch thread.

    SQLite rejects cross-thread access by default.  Patching out the
    fetch keeps tests fast and deterministic while the rest of the
    widget integration (signals, service calls) is still exercised.
    """
    monkeypatch.setattr(CollectionWidget, "_start_fetch", lambda self: None)


@pytest.fixture(autouse=True)
def _no_script_linter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent ``ScriptLinter`` from spawning Deno subprocesses in most UI tests.

    Every ``CodeEditorWidget`` with language ``javascript`` or ``python``
    triggers ``_validate_script()`` on a 300 ms debounce timer, which
    for JavaScript runs Esprima through ``deno run``.  In a full test run
    with many editor instances, the accumulated child processes are slow
    and can stress the test runner.

    Tests that specifically verify linting integration should override
    this fixture with ``@pytest.mark.usefixtures()`` or call
    ``monkeypatch.undo()`` to restore the real ``ScriptLinter``.
    """
    from services.scripting.engine import ScriptLinter

    monkeypatch.setattr(ScriptLinter, "check", staticmethod(lambda *_a, **_kw: []))


@pytest.fixture(autouse=True)
def _reset_popup_and_flush_widgets(qapp: QApplication) -> Iterator[None]:
    """Reset ``VariablePopup`` class state and flush deferred widget deletions.

    ``MainWindow.__init__`` calls
    ``VariablePopup.set_save_callback(self._on_variable_updated)``
    which stores a bound-method reference on the **class**.  That
    prevents ``deleteLater()`` disposals from cascading through the
    widget tree.  Across 67+ ``MainWindow`` tests the zombie widgets
    accumulate (~25 000) and any subsequent
    ``QApplication.setStyleSheet()`` call becomes O(n) — turning
    later ``ThemeManager`` tests into a multi-minute crawl.

    Clearing the class-level references then dispatching pending
    ``DeferredDelete`` events keeps the live widget count low.
    """
    yield
    # 1. Break reference cycle: class var -> bound method -> MainWindow.
    from ui.widgets.variable_popup import VariablePopup

    if VariablePopup._instance is not None:
        VariablePopup._instance.close()
        VariablePopup._instance = None
    VariablePopup._save_callback = None
    VariablePopup._local_override_callback = None
    VariablePopup._reset_local_override_callback = None
    VariablePopup._add_variable_callback = None

    # 2. Reset code-editor popup singletons (see ``tests/qt_popup_cleanup.py``).
    from tests.qt_popup_cleanup import (
        dismiss_all_top_level_test_widgets,
        flush_deferred_widget_deletes,
        reset_code_editor_popups,
    )

    reset_code_editor_popups()
    dismiss_all_top_level_test_widgets(qapp)
    flush_deferred_widget_deletes(qapp)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def finish_main_window_startup(window: object) -> None:
    """Emit ``load_finished`` when needed and run session restore to completion."""
    from ui.main_window.session_restore import flush_session_restore

    if window._main_stack.currentIndex() == 0:  # type: ignore[attr-defined]
        window.collection_widget.load_finished.emit()  # type: ignore[attr-defined]
    flush_session_restore(window)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _inline_local_project_config_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid background mirror sync threads in UI tests (sync on demand elsewhere)."""
    from ui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_start_local_project_config_sync", lambda self: None)


def make_collection_dict(
    collections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the nested dict that ``CollectionTree.set_collections`` expects.

    Each entry in *collections* should have ``id``, ``name``, and optionally
    ``children`` (a list of the same shape) or ``requests`` (list of dicts
    with ``id``, ``name``, ``method``).
    """
    result: dict[str, Any] = {}
    for coll in collections:
        children: dict[str, Any] = {}
        for req in coll.get("requests", []):
            children[str(req["id"])] = {
                "type": "request",
                "id": req["id"],
                "name": req["name"],
                "method": req.get("method", "GET"),
            }
        for sub in coll.get("children", []):
            sub_dict = make_collection_dict([sub])
            children.update(sub_dict)
        result[str(coll["id"])] = {
            "id": coll["id"],
            "name": coll["name"],
            "type": "folder",
            "children": children,
        }
    return result


def top_level_items(tree: CollectionTree) -> list[QTreeWidgetItem]:
    """Return all top-level items from the inner QTreeWidget."""
    root = tree._tree.invisibleRootItem()
    return [root.child(i) for i in range(root.childCount())]
