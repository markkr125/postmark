"""Shared fixtures and helpers for UI tests."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from PySide6.QtCore import QEvent
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

    # 2. Dispatch every queued DeferredDelete so C++ widgets are freed.
    qapp.sendPostedEvents(None, int(QEvent.Type.DeferredDelete))


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
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
