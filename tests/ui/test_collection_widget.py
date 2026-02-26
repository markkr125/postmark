"""End-to-end tests for the CollectionWidget (widget + service + DB)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from services.collection_service import CollectionService
from ui.collections.collection_widget import CollectionWidget
from ui.collections.tree import ROLE_ITEM_ID

from .conftest import make_collection_dict, top_level_items


class TestCollectionWidget:
    """End-to-end tests that exercise the widget -> service -> DB chain.

    The autouse ``_no_fetch`` fixture (see ``conftest.py``) patches out the
    background thread that ``CollectionWidget.__init__`` normally starts,
    avoiding SQLite's cross-thread restrictions while keeping every other
    code path live.
    """

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """CollectionWidget can be instantiated and has header + tree."""
        widget = CollectionWidget()
        qtbot.addWidget(widget)
        assert widget._header is not None
        assert widget._tree_widget is not None

    def test_set_collections(self, qapp: QApplication, qtbot) -> None:
        """Calling ``set_collections`` populates the inner tree."""
        widget = CollectionWidget()
        qtbot.addWidget(widget)

        data = make_collection_dict([{"id": 1, "name": "Direct"}])
        widget.set_collections(data)

        items = top_level_items(widget._tree_widget)
        assert len(items) == 1
        assert items[0].text(0) == "Direct"

    def test_create_collection_via_service(self, qapp: QApplication, qtbot) -> None:
        """``_create_new_collection`` persists to DB and adds to tree."""
        widget = CollectionWidget()
        qtbot.addWidget(widget)

        widget._create_new_collection(parent_id=None)

        # 1. Verify the tree got a new top-level item
        items = top_level_items(widget._tree_widget)
        assert len(items) >= 1
        new_item = items[-1]
        item_id = new_item.data(0, ROLE_ITEM_ID)
        assert item_id is not None

        # 2. Verify the DB actually has it
        svc = CollectionService()
        coll = svc.get_collection(item_id)
        assert coll is not None
        assert coll.name == "New Collection"

    def test_create_request_via_service(self, qapp: QApplication, qtbot) -> None:
        """``_create_new_request`` persists to DB and adds to tree."""
        svc = CollectionService()
        parent_coll = svc.create_collection("Host")

        widget = CollectionWidget()
        qtbot.addWidget(widget)

        # Feed the collection into the tree so the widget can find it
        data = make_collection_dict([{"id": parent_coll.id, "name": "Host"}])
        widget.set_collections(data)

        widget._create_new_request(collection_id=parent_coll.id)

        # 1. The tree should have a request under the folder
        folder = top_level_items(widget._tree_widget)[0]
        assert folder.childCount() >= 1

        # 2. The DB should have the request
        req_item = folder.child(folder.childCount() - 1)
        req_id = req_item.data(0, ROLE_ITEM_ID)
        req = svc.get_request(req_id)
        assert req is not None
        assert req.method == "GET"

    def test_rename_collection_signal(self, qapp: QApplication, qtbot) -> None:
        """Emitting ``collection_rename_requested`` persists the new name."""
        svc = CollectionService()
        coll = svc.create_collection("Before")

        widget = CollectionWidget()
        qtbot.addWidget(widget)

        widget._tree_widget.collection_rename_requested.emit(coll.id, "After")

        updated = svc.get_collection(coll.id)
        assert updated is not None
        assert updated.name == "After"

    def test_delete_collection_signal(self, qapp: QApplication, qtbot) -> None:
        """Emitting ``collection_delete_requested`` removes the record."""
        svc = CollectionService()
        coll = svc.create_collection("Doomed")

        widget = CollectionWidget()
        qtbot.addWidget(widget)

        widget._tree_widget.collection_delete_requested.emit(coll.id)

        assert svc.get_collection(coll.id) is None

    def test_rename_request_signal(self, qapp: QApplication, qtbot) -> None:
        """Emitting ``request_rename_requested`` persists the new name."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://x", "OldName")

        widget = CollectionWidget()
        qtbot.addWidget(widget)

        widget._tree_widget.request_rename_requested.emit(req.id, "NewName")

        updated = svc.get_request(req.id)
        assert updated is not None
        assert updated.name == "NewName"

    def test_delete_request_signal(self, qapp: QApplication, qtbot) -> None:
        """Emitting ``request_delete_requested`` removes the record."""
        svc = CollectionService()
        coll = svc.create_collection("Coll")
        req = svc.create_request(coll.id, "GET", "http://x", "Temp")

        widget = CollectionWidget()
        qtbot.addWidget(widget)

        widget._tree_widget.request_delete_requested.emit(req.id)

        assert svc.get_request(req.id) is None

    def test_move_request_signal(self, qapp: QApplication, qtbot) -> None:
        """Emitting ``request_moved`` updates the request's collection."""
        svc = CollectionService()
        coll_a = svc.create_collection("A")
        coll_b = svc.create_collection("B")
        req = svc.create_request(coll_a.id, "GET", "http://x", "Movable")

        widget = CollectionWidget()
        qtbot.addWidget(widget)

        widget._tree_widget.request_moved.emit(req.id, coll_b.id)

        moved = svc.get_request(req.id)
        assert moved is not None
        assert moved.collection_id == coll_b.id

    def test_move_collection_signal(self, qapp: QApplication, qtbot) -> None:
        """Emitting ``collection_moved`` re-parents the collection."""
        svc = CollectionService()
        parent = svc.create_collection("Parent")
        child = svc.create_collection("Child")

        widget = CollectionWidget()
        qtbot.addWidget(widget)

        widget._tree_widget.collection_moved.emit(child.id, parent.id)

        moved = svc.get_collection(child.id)
        assert moved is not None
        assert moved.parent_id == parent.id
