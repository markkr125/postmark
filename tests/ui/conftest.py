"""Shared fixtures and helpers for UI tests."""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtWidgets import QTreeWidgetItem

from ui.collections.collection_tree import CollectionTree
from ui.collections.collection_widget import CollectionWidget


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------
@pytest.fixture()
def _no_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent CollectionWidget from spawning a background fetch thread.

    SQLite rejects cross-thread access by default.  Patching out the
    fetch keeps tests fast and deterministic while the rest of the
    widget integration (signals, service calls) is still exercised.
    """
    monkeypatch.setattr(CollectionWidget, "_start_fetch", lambda self: None)


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
