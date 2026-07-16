"""Tests for collection tree refresh and Agent mutate UI sync."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from services.collection_service import CollectionService
from ui.collections.collection_widget import CollectionWidget
from ui.collections.tree.constants import ROLE_ITEM_ID, ROLE_ITEM_TYPE
from ui.main_window.window import MainWindow
from ui.request.request_editor import RequestEditorWidget


def _sync_tree(widget: CollectionWidget) -> None:
    """Install current DB tree data on the GUI thread."""
    widget.set_collections(CollectionService.fetch_all())


def test_refresh_collections_shows_new_collection(qapp: QApplication, qtbot) -> None:
    """refresh_collections after first load includes newly created collections."""
    widget = CollectionWidget()
    qtbot.addWidget(widget)
    widget.refresh_collections()
    CollectionService.create_collection("Agent Created")
    widget.refresh_collections()
    tree = widget._tree_widget._tree
    names: list[str] = []
    for i in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(i)
        assert item is not None
        names.append(item.text(0))
    assert "Agent Created" in names


def test_refresh_collections_selects_collection(qapp: QApplication, qtbot) -> None:
    """Pending select_collection_id is applied after refresh."""
    col = CollectionService.create_collection("Select Me")
    widget = CollectionWidget()
    qtbot.addWidget(widget)
    widget.refresh_collections(select_collection_id=col.id)
    current = widget._tree_widget._tree.currentItem()
    assert current is not None
    assert current.data(0, ROLE_ITEM_ID) == col.id
    assert current.data(1, ROLE_ITEM_TYPE) == "folder"


def test_folder_tab_highlights_tree_row(qapp: QApplication, qtbot) -> None:
    """Active folder tab selects the matching collections-list row."""
    col = CollectionService.create_collection("Highlight Folder")
    window = MainWindow()
    qtbot.addWidget(window)
    _sync_tree(window.collection_widget)
    window._open_folder(col.id)
    qtbot.waitUntil(
        lambda: (
            window.collection_widget._tree_widget._tree.currentItem() is not None
            and window.collection_widget._tree_widget._tree.currentItem().data(0, ROLE_ITEM_ID)
            == col.id
        ),
        timeout=5000,
    )


def test_folder_highlight_survives_refresh(qapp: QApplication, qtbot) -> None:
    """After refresh_collections, the active folder tab stays highlighted."""
    col = CollectionService.create_collection("Stay Highlighted")
    window = MainWindow()
    qtbot.addWidget(window)
    _sync_tree(window.collection_widget)
    window._open_folder(col.id)
    window.collection_widget.refresh_collections()
    current = window.collection_widget._tree_widget._tree.currentItem()
    assert current is not None
    assert current.data(0, ROLE_ITEM_ID) == col.id


def test_reload_open_request_updates_editor(qapp: QApplication, qtbot) -> None:
    """Open request editors reload from DB after a mutate-style update."""
    col = CollectionService.create_collection("Reload Col")
    req = CollectionService.create_request(col.id, "GET", "https://old.example", "Old")
    window = MainWindow()
    qtbot.addWidget(window)
    _sync_tree(window.collection_widget)
    assert window._open_request(req.id, push_history=False, is_preview=False)
    CollectionService.update_request(
        req.id,
        name="New Name",
        method="POST",
        url="https://new.example/path",
        description="Updated docs",
    )
    window._reload_open_request_from_db(req.id)
    editor = window.request_widget
    assert isinstance(editor, RequestEditorWidget)
    assert editor._url_input.text() == "https://new.example/path"
    assert editor._method_combo.currentText() == "POST"
    assert editor._description_edit.toPlainText() == "Updated docs"
    assert not editor.is_dirty


def test_select_item_expands_ancestors(qapp: QApplication, qtbot) -> None:
    """Nested folder selection expands collapsed parents."""
    parent = CollectionService.create_collection("Parent Nest")
    child = CollectionService.create_collection("Child Nest", parent.id)
    widget = CollectionWidget()
    qtbot.addWidget(widget)
    _sync_tree(widget)
    parent_item = widget._tree_widget._find_item_by_id(
        widget._tree_widget._tree.invisibleRootItem(), parent.id, "folder"
    )
    assert parent_item is not None
    parent_item.setExpanded(False)
    widget.select_and_scroll_to(child.id, "folder")
    assert parent_item.isExpanded()
    current = widget._tree_widget._tree.currentItem()
    assert isinstance(current, QTreeWidgetItem)
    assert current.data(0, ROLE_ITEM_ID) == child.id
