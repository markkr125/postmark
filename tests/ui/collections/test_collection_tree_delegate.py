"""Tests for the CollectionTreeDelegate custom item delegate."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from ui.collections.tree import ROLE_METHOD, CollectionTree

from ..conftest import make_collection_dict, top_level_items


class TestCollectionTreeDelegate:
    """Tests for delegate-based badge painting on request items."""

    def test_delegate_is_set_on_tree(self, qapp: QApplication, qtbot) -> None:
        """The tree widget has the custom delegate installed."""
        from ui.collections.tree.collection_tree_delegate import \
            CollectionTreeDelegate

        tree = CollectionTree()
        qtbot.addWidget(tree)

        delegate = tree._tree.itemDelegate()
        assert isinstance(delegate, CollectionTreeDelegate)

    def test_request_items_store_method_role(self, qapp: QApplication, qtbot) -> None:
        """Request items have the HTTP method stored in ``ROLE_METHOD``."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict(
            [
                {
                    "id": 1,
                    "name": "Coll",
                    "requests": [
                        {"id": 10, "name": "Get", "method": "GET"},
                        {"id": 11, "name": "Post", "method": "POST"},
                    ],
                },
            ]
        )
        tree.set_collections(data)

        folder = top_level_items(tree)[0]
        methods = {folder.child(i).data(0, ROLE_METHOD) for i in range(folder.childCount())}
        assert methods == {"GET", "POST"}

    def test_request_items_no_item_widget(self, qapp: QApplication, qtbot) -> None:
        """Request items must NOT have a per-row ``setItemWidget``."""
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

        req = top_level_items(tree)[0].child(0)
        assert tree._tree.itemWidget(req, 0) is None

    def test_folder_items_no_method_role(self, qapp: QApplication, qtbot) -> None:
        """Folder items should not have ``ROLE_METHOD`` set."""
        tree = CollectionTree()
        qtbot.addWidget(tree)

        data = make_collection_dict([{"id": 1, "name": "Folder"}])
        tree.set_collections(data)

        folder = top_level_items(tree)[0]
        assert folder.data(0, ROLE_METHOD) is None

    def test_delegate_size_hint_for_request(self, qapp: QApplication, qtbot) -> None:
        """Delegate returns a fixed-height size hint for request items."""
        from ui.theme import TREE_ROW_HEIGHT

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

        req = top_level_items(tree)[0].child(0)
        index = tree._tree.indexFromItem(req, 0)

        delegate = tree._tree.itemDelegate()
        option = QStyleOptionViewItem()
        hint = delegate.sizeHint(option, index)
        assert hint.height() == TREE_ROW_HEIGHT

    def test_delegate_create_editor_returns_none_for_request(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Delegate suppresses the default editor for request items."""
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

        req = top_level_items(tree)[0].child(0)
        index = tree._tree.indexFromItem(req, 0)

        delegate = tree._tree.itemDelegate()
        option = QStyleOptionViewItem()
        editor = delegate.createEditor(tree._tree.viewport(), option, index)
        assert editor is None
        assert editor is None
