"""Local scripts tree shows brand language icons on script rows."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from database.models.local_scripts.local_script_query_repository import (
    fetch_all_local_scripts_tree,
)
from database.models.local_scripts.local_script_repository import create_folder, create_script
from ui.collections.collection_widget import CollectionWidget
from ui.collections.tree.constants import ROLE_LANGUAGE


def test_script_row_stores_language_role(qapp: QApplication, qtbot) -> None:
    """Script leaves expose ``ROLE_LANGUAGE`` for the tree delegate."""
    root = create_folder("Root")
    script = create_script(root.id, "App", language="typescript")

    widget = CollectionWidget(variant="local_scripts")
    qtbot.addWidget(widget)
    widget.set_collections(fetch_all_local_scripts_tree())

    item = widget._tree_widget._find_item_by_id(
        widget._tree_widget._tree.invisibleRootItem(),
        script.id,
        "script",
    )
    assert item is not None
    assert item.data(0, ROLE_LANGUAGE) == "typescript"
