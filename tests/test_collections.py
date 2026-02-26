"""Tests for the collections repository layer (collections_utils)."""
from __future__ import annotations

import pytest

from database.models.collections.collections_utils import (
    create_new_collection,
    create_new_request,
    delete_collection,
    delete_request,
    fetch_all_collections,
    get_collection_by_id,
    get_request_by_id,
    rename_collection,
    rename_request,
    update_collection_parent,
    update_request_collection,
)


# ------------------------------------------------------------------
# Collection CRUD
# ------------------------------------------------------------------
class TestCollectionCRUD:
    def test_create_root_collection(self):
        coll = create_new_collection("My Collection")
        assert coll.id is not None
        assert coll.name == "My Collection"
        assert coll.parent_id is None

    def test_create_child_collection(self):
        parent = create_new_collection("Parent")
        child = create_new_collection("Child", parent_id=parent.id)
        assert child.parent_id == parent.id

    def test_fetch_all_returns_roots_only(self):
        root1 = create_new_collection("Root A")
        root2 = create_new_collection("Root B")
        create_new_collection("Child of A", parent_id=root1.id)

        roots = fetch_all_collections()
        root_ids = {r.id for r in roots}
        assert root1.id in root_ids
        assert root2.id in root_ids
        assert len(roots) == 2

    def test_rename_collection(self):
        coll = create_new_collection("Old Name")
        rename_collection(coll.id, "New Name")
        updated = get_collection_by_id(coll.id)
        assert updated is not None
        assert updated.name == "New Name"

    def test_delete_collection_cascades(self):
        parent = create_new_collection("Parent")
        child = create_new_collection("Child", parent_id=parent.id)
        create_new_request(child.id, "GET", "http://example.com", "Req 1")

        delete_collection(parent.id)

        assert get_collection_by_id(parent.id) is None
        assert get_collection_by_id(child.id) is None

    def test_delete_nonexistent_collection_raises(self):
        with pytest.raises(ValueError, match="No collection found"):
            delete_collection(99999)

    def test_move_collection(self):
        root_a = create_new_collection("A")
        root_b = create_new_collection("B")
        child = create_new_collection("Child", parent_id=root_a.id)

        update_collection_parent(child.id, root_b.id)

        moved = get_collection_by_id(child.id)
        assert moved is not None
        assert moved.parent_id == root_b.id


# ------------------------------------------------------------------
# Request CRUD
# ------------------------------------------------------------------
class TestRequestCRUD:
    def test_create_request(self):
        coll = create_new_collection("Coll")
        req = create_new_request(coll.id, "POST", "http://api.test/data", "Create Item")
        assert req.id is not None
        assert req.method == "POST"
        assert req.name == "Create Item"
        assert req.collection_id == coll.id

    def test_create_request_invalid_collection_raises(self):
        with pytest.raises(ValueError, match="not found"):
            create_new_request(99999, "GET", "http://x", "Nope")

    def test_rename_request(self):
        coll = create_new_collection("Coll")
        req = create_new_request(coll.id, "GET", "http://x", "Old")
        rename_request(req.id, "New")
        updated = get_request_by_id(req.id)
        assert updated is not None
        assert updated.name == "New"

    def test_delete_request(self):
        coll = create_new_collection("Coll")
        req = create_new_request(coll.id, "GET", "http://x", "Temp")
        delete_request(req.id)
        assert get_request_by_id(req.id) is None

    def test_delete_nonexistent_request_raises(self):
        with pytest.raises(ValueError, match="No request found"):
            delete_request(99999)

    def test_move_request_to_different_collection(self):
        coll_a = create_new_collection("A")
        coll_b = create_new_collection("B")
        req = create_new_request(coll_a.id, "GET", "http://x", "Req")

        update_request_collection(req.id, coll_b.id)

        moved = get_request_by_id(req.id)
        assert moved is not None
        assert moved.collection_id == coll_b.id

    def test_create_request_with_optional_fields(self):
        coll = create_new_collection("Coll")
        req = create_new_request(
            coll.id,
            "PUT",
            "http://x",
            "Full",
            body="hello",
            scripts={"pre": "console.log(1)"},
            settings={"timeout": 5000},
        )
        assert req.body == "hello"
        assert req.scripts == {"pre": "console.log(1)"}
        assert req.settings == {"timeout": 5000}


# ------------------------------------------------------------------
# Service layer (thin wrapper, smoke test)
# ------------------------------------------------------------------
class TestCollectionService:
    def test_service_roundtrip(self):
        from services.collection_service import CollectionService

        svc = CollectionService()
        coll = svc.create_collection("Via Service")
        assert coll.id is not None

        fetched = svc.get_collection(coll.id)
        assert fetched is not None
        assert fetched.name == "Via Service"

        svc.rename_collection(coll.id, "Renamed")
        renamed = svc.get_collection(coll.id)
        assert renamed is not None
        assert renamed.name == "Renamed"

        req = svc.create_request(coll.id, "GET", "http://test", "Test Req")
        assert req.id is not None

        svc.delete_request(req.id)
        assert svc.get_request(req.id) is None

        svc.delete_collection(coll.id)
        assert svc.get_collection(coll.id) is None
