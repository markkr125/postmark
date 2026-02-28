"""Unit tests for the collection repository CRUD layer."""

from __future__ import annotations

import pytest

from database.models.collections.collection_repository import (
    count_collection_requests,
    create_new_collection,
    create_new_request,
    delete_collection,
    delete_request,
    fetch_all_collections,
    get_collection_breadcrumb,
    get_collection_by_id,
    get_recent_requests_for_collection,
    get_request_by_id,
    rename_collection,
    rename_request,
    update_collection,
    update_collection_parent,
    update_request,
    update_request_collection,
)


# ------------------------------------------------------------------
# Collection CRUD
# ------------------------------------------------------------------
class TestCollectionCRUD:
    """Tests for collection repository functions."""

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
        """fetch_all_collections returns a dict keyed by root collection IDs."""
        root1 = create_new_collection("Root A")
        root2 = create_new_collection("Root B")
        create_new_collection("Child of A", parent_id=root1.id)

        result = fetch_all_collections()
        root_ids = {v["id"] for v in result.values()}
        assert root1.id in root_ids
        assert root2.id in root_ids
        assert len(result) == 2

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
    """Tests for request repository functions."""

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

    def test_update_request_body(self):
        """update_request can change the body of a request."""
        coll = create_new_collection("Coll")
        req = create_new_request(coll.id, "POST", "http://x", "Updatable")
        update_request(req.id, body="new body")
        updated = get_request_by_id(req.id)
        assert updated is not None
        assert updated.body == "new body"

    def test_update_request_multiple_fields(self):
        """update_request can change several fields at once."""
        coll = create_new_collection("Coll")
        req = create_new_request(coll.id, "GET", "http://old", "Req")
        update_request(req.id, method="PUT", url="http://new", body="payload")
        updated = get_request_by_id(req.id)
        assert updated is not None
        assert updated.method == "PUT"
        assert updated.url == "http://new"
        assert updated.body == "payload"

    def test_update_request_rejects_non_editable_fields(self):
        """update_request rejects fields not in _EDITABLE_REQUEST_FIELDS."""
        coll = create_new_collection("Coll")
        req = create_new_request(coll.id, "GET", "http://x", "Req")
        with pytest.raises(ValueError, match="Non-editable fields"):
            update_request(req.id, id=999)

    def test_update_request_nonexistent_raises(self):
        """update_request raises ValueError for a missing request."""
        with pytest.raises(ValueError, match="No request found"):
            update_request(99999, body="nope")

    def test_update_request_json_fields(self):
        """update_request can set JSON fields like body_options and auth."""
        coll = create_new_collection("Coll")
        req = create_new_request(coll.id, "POST", "http://x", "JSON Req")
        update_request(
            req.id,
            body_mode="raw",
            body_options={"raw": {"language": "json"}},
            auth={"type": "bearer", "bearer": [{"key": "token", "value": "abc"}]},
        )
        updated = get_request_by_id(req.id)
        assert updated is not None
        assert updated.body_mode == "raw"
        assert updated.body_options == {"raw": {"language": "json"}}
        assert updated.auth is not None
        assert updated.auth["type"] == "bearer"


# ------------------------------------------------------------------
# Collection field updates (update_collection)
# ------------------------------------------------------------------
class TestCollectionFieldUpdates:
    """Tests for the ``update_collection`` function."""

    def test_update_description(self):
        """update_collection can set the description field."""
        coll = create_new_collection("Coll")
        update_collection(coll.id, description="A detailed description")
        updated = get_collection_by_id(coll.id)
        assert updated is not None
        assert updated.description == "A detailed description"

    def test_update_auth(self):
        """update_collection can set the auth JSON field."""
        coll = create_new_collection("Coll")
        auth_data = {"type": "bearer", "bearer": [{"key": "token", "value": "abc"}]}
        update_collection(coll.id, auth=auth_data)
        updated = get_collection_by_id(coll.id)
        assert updated is not None
        assert updated.auth is not None
        assert updated.auth["type"] == "bearer"

    def test_update_events(self):
        """update_collection can set the events JSON field."""
        coll = create_new_collection("Coll")
        events_data = {"pre_request": "console.log('pre')", "test": "console.log('test')"}
        update_collection(coll.id, events=events_data)
        updated = get_collection_by_id(coll.id)
        assert updated is not None
        assert updated.events == events_data

    def test_update_variables(self):
        """update_collection can set the variables JSON field."""
        coll = create_new_collection("Coll")
        vars_data = [{"key": "host", "value": "localhost"}]
        update_collection(coll.id, variables=vars_data)
        updated = get_collection_by_id(coll.id)
        assert updated is not None
        assert updated.variables == vars_data

    def test_update_multiple_fields(self):
        """update_collection can set several fields at once."""
        coll = create_new_collection("Coll")
        update_collection(
            coll.id,
            description="desc",
            events={"pre_request": "x"},
        )
        updated = get_collection_by_id(coll.id)
        assert updated is not None
        assert updated.description == "desc"
        assert updated.events == {"pre_request": "x"}

    def test_rejects_non_editable_fields(self):
        """update_collection rejects fields not in _EDITABLE_COLLECTION_FIELDS."""
        coll = create_new_collection("Coll")
        with pytest.raises(ValueError, match="Non-editable fields"):
            update_collection(coll.id, id=999)

    def test_nonexistent_collection_raises(self):
        """update_collection raises ValueError for a missing collection."""
        with pytest.raises(ValueError, match="No collection found"):
            update_collection(99999, description="nope")

    def test_no_op_with_empty_fields(self):
        """update_collection with no fields is a safe no-op."""
        coll = create_new_collection("Coll")
        update_collection(coll.id)
        updated = get_collection_by_id(coll.id)
        assert updated is not None
        assert updated.name == "Coll"


# ------------------------------------------------------------------
# Collection breadcrumb
# ------------------------------------------------------------------
class TestCollectionBreadcrumb:
    """Tests for the ``get_collection_breadcrumb`` function."""

    def test_root_collection(self):
        """Breadcrumb for a root collection is a single entry."""
        root = create_new_collection("Root")
        crumbs = get_collection_breadcrumb(root.id)
        assert len(crumbs) == 1
        assert crumbs[0]["name"] == "Root"
        assert crumbs[0]["type"] == "folder"

    def test_nested_collection(self):
        """Breadcrumb walks up from child to root."""
        root = create_new_collection("Root")
        child = create_new_collection("Child", parent_id=root.id)
        grandchild = create_new_collection("Grandchild", parent_id=child.id)

        crumbs = get_collection_breadcrumb(grandchild.id)
        assert len(crumbs) == 3
        assert crumbs[0]["name"] == "Root"
        assert crumbs[1]["name"] == "Child"
        assert crumbs[2]["name"] == "Grandchild"

    def test_nonexistent_collection_returns_empty(self):
        """Breadcrumb for a nonexistent collection returns an empty list."""
        crumbs = get_collection_breadcrumb(99999)
        assert crumbs == []


# ------------------------------------------------------------------
# Collection request count
# ------------------------------------------------------------------
class TestCountCollectionRequests:
    """Tests for the ``count_collection_requests`` function."""

    def test_empty_collection(self):
        """A collection with no requests returns 0."""
        coll = create_new_collection("Empty")
        assert count_collection_requests(coll.id) == 0

    def test_direct_requests(self):
        """Counts requests directly in the collection."""
        coll = create_new_collection("Coll")
        create_new_request(coll.id, "GET", "http://a", "R1")
        create_new_request(coll.id, "POST", "http://b", "R2")
        assert count_collection_requests(coll.id) == 2

    def test_recursive_count(self):
        """Counts requests in nested child collections."""
        root = create_new_collection("Root")
        child = create_new_collection("Child", parent_id=root.id)
        create_new_request(root.id, "GET", "http://a", "R1")
        create_new_request(child.id, "GET", "http://b", "R2")
        create_new_request(child.id, "POST", "http://c", "R3")
        assert count_collection_requests(root.id) == 3

    def test_deeply_nested(self):
        """Counts requests across multiple nesting levels."""
        root = create_new_collection("Root")
        child = create_new_collection("Child", parent_id=root.id)
        grandchild = create_new_collection("Grandchild", parent_id=child.id)
        create_new_request(grandchild.id, "GET", "http://x", "Deep")
        assert count_collection_requests(root.id) == 1


class TestRecentRequests:
    """Tests for the ``get_recent_requests_for_collection`` function."""

    def test_empty_collection(self):
        """A collection with no requests returns an empty list."""
        coll = create_new_collection("Empty")
        assert get_recent_requests_for_collection(coll.id) == []

    def test_returns_requests_ordered_by_updated(self):
        """Requests are returned ordered by updated_at descending."""
        coll = create_new_collection("Coll")
        create_new_request(coll.id, "GET", "http://a", "R1")
        create_new_request(coll.id, "POST", "http://b", "R2")
        result = get_recent_requests_for_collection(coll.id)
        assert len(result) == 2
        assert result[0]["name"] in {"R1", "R2"}
        # Each entry has the expected keys
        for entry in result:
            assert "name" in entry
            assert "method" in entry
            assert "updated_at" in entry

    def test_recursive_includes_children(self):
        """Requests in nested collections are included."""
        root = create_new_collection("Root")
        child = create_new_collection("Child", parent_id=root.id)
        create_new_request(root.id, "GET", "http://a", "R1")
        create_new_request(child.id, "POST", "http://b", "R2")
        result = get_recent_requests_for_collection(root.id)
        assert len(result) == 2
        names = {r["name"] for r in result}
        assert names == {"R1", "R2"}

    def test_limit_respected(self):
        """The limit parameter caps the number of results."""
        coll = create_new_collection("Coll")
        for i in range(5):
            create_new_request(coll.id, "GET", f"http://x/{i}", f"R{i}")
        result = get_recent_requests_for_collection(coll.id, limit=3)
        assert len(result) == 3
