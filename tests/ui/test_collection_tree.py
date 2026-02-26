"""Tests for the CollectionTree widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.collections.tree import ROLE_ITEM_ID, ROLE_ITEM_TYPE, CollectionTree

from .conftest import make_collection_dict, top_level_items


class TestCollectionTree:
    """Tests for the tree widget that displays the collection hierarchy."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Tree widget can be instantiated without errors."""
        tree = CollectionTree()
        qtbot.addWidget(tree)
        assert tree is not None

    def test_set_collections_populates_tree(self, qapp: QApplication, qtbot) -> None:
        """``set_collections`` creates top-level folder items."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {"id": 1, "name": "Alpha"},
                {"id": 2, "name": "Beta"},
            ]
        )
        tree.set_collections(data)

        items = top_level_items(tree)
        assert len(items) == 2
        names = {it.text(0) for it in items}
        assert names == {"Alpha", "Beta"}

    def test_set_collections_with_nested_requests(self, qapp: QApplication, qtbot) -> None:
        """Requests appear as children of their parent folder."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 1,
                    "name": "API",
                    "requests": [
                        {"id": 10, "name": "List users", "method": "GET"},
                        {"id": 11, "name": "Create user", "method": "POST"},
                    ],
                },
            ]
        )
        tree.set_collections(data)

        items = top_level_items(tree)
        assert len(items) == 1
        folder = items[0]
        assert folder.childCount() == 2

    def test_set_collections_clears_previous(self, qapp: QApplication, qtbot) -> None:
        """Calling ``set_collections`` twice replaces old data."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.set_collections(make_collection_dict([{"id": 1, "name": "Old"}]))
        tree.set_collections(make_collection_dict([{"id": 2, "name": "New"}]))

        items = top_level_items(tree)
        assert len(items) == 1
        assert items[0].text(0) == "New"

    def test_add_collection_root(self, qapp: QApplication, qtbot) -> None:
        """``add_collection`` with parent_id=None adds a top-level folder."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.set_collections({})
        tree.add_collection({"id": 5, "name": "Root Folder"}, parent_id=None)

        items = top_level_items(tree)
        assert len(items) == 1
        assert items[0].data(0, ROLE_ITEM_ID) == 5

    def test_add_collection_nested(self, qapp: QApplication, qtbot) -> None:
        """``add_collection`` with a parent_id nests under that folder."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.set_collections(make_collection_dict([{"id": 1, "name": "Parent"}]))
        tree.add_collection({"id": 2, "name": "Child"}, parent_id=1)

        parent = top_level_items(tree)[0]
        assert parent.childCount() == 1
        child = parent.child(0)
        assert child.data(0, ROLE_ITEM_ID) == 2
        assert child.data(1, ROLE_ITEM_TYPE) == "folder"

    def test_add_request(self, qapp: QApplication, qtbot) -> None:
        """``add_request`` inserts a request child under the given folder."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.set_collections(make_collection_dict([{"id": 1, "name": "Coll"}]))
        tree.add_request(
            {"id": 10, "name": "Get items", "method": "GET", "url": "/items"},
            parent_id=1,
        )

        folder = top_level_items(tree)[0]
        assert folder.childCount() == 1
        req = folder.child(0)
        assert req.data(0, ROLE_ITEM_ID) == 10
        assert req.data(1, ROLE_ITEM_TYPE) == "request"

    def test_remove_item_folder(self, qapp: QApplication, qtbot) -> None:
        """``remove_item`` removes a top-level folder."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.set_collections(make_collection_dict([{"id": 1, "name": "Gone"}]))
        assert len(top_level_items(tree)) == 1

        tree.remove_item(1, "folder")
        assert len(top_level_items(tree)) == 0

    def test_remove_item_request(self, qapp: QApplication, qtbot) -> None:
        """``remove_item`` removes a request from its parent folder."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 1,
                    "name": "Coll",
                    "requests": [{"id": 10, "name": "Req", "method": "GET"}],
                },
            ]
        )
        tree.set_collections(data)

        folder = top_level_items(tree)[0]
        assert folder.childCount() == 1

        tree.remove_item(10, "request")
        assert folder.childCount() == 0

    def test_select_item_by_id(self, qapp: QApplication, qtbot) -> None:
        """``select_item_by_id`` sets the current item in the tree."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        tree.set_collections(
            make_collection_dict(
                [
                    {"id": 1, "name": "A"},
                    {"id": 2, "name": "B"},
                ]
            )
        )
        tree.select_item_by_id(2, "folder")

        current = tree._tree.currentItem()
        assert current is not None
        assert current.data(0, ROLE_ITEM_ID) == 2

    def test_item_roles_stored_correctly(self, qapp: QApplication, qtbot) -> None:
        """Items store the correct ID and type in UserRole data."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 3,
                    "name": "Folder",
                    "requests": [{"id": 7, "name": "Req", "method": "POST"}],
                },
            ]
        )
        tree.set_collections(data)

        folder = top_level_items(tree)[0]
        assert folder.data(0, ROLE_ITEM_ID) == 3
        assert folder.data(1, ROLE_ITEM_TYPE) == "folder"

        req = folder.child(0)
        assert req.data(0, ROLE_ITEM_ID) == 7
        assert req.data(1, ROLE_ITEM_TYPE) == "request"
        assert req.data(1, ROLE_ITEM_TYPE) == "request"
