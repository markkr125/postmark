"""Local scripts tree selection used by breadcrumb navigation."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from database.models.local_scripts.local_script_query_repository import (
    fetch_all_local_scripts_tree,
)
from database.models.local_scripts.local_script_repository import create_folder, create_script
from ui.collections.collection_widget import CollectionWidget
from ui.collections.tree.constants import ROLE_ITEM_ID, ROLE_ITEM_TYPE


def test_select_and_scroll_to_folder_in_local_scripts_tree(
    qapp: QApplication,
    qtbot,
) -> None:
    """``select_and_scroll_to`` highlights a folder row in the local-scripts tree."""
    outer = create_folder("Outer")
    inner = create_folder("Inner", parent_id=outer.id)
    create_script(inner.id, "Leaf", language="javascript")

    widget = CollectionWidget(variant="local_scripts")
    qtbot.addWidget(widget)
    widget.set_collections(fetch_all_local_scripts_tree())

    widget.select_and_scroll_to(inner.id, "folder")
    current = widget._tree_widget._tree.currentItem()
    assert current is not None
    assert current.data(0, ROLE_ITEM_ID) == inner.id
    assert current.data(0, ROLE_ITEM_TYPE) == "folder"
