"""Unit tests for the collection service layer."""

from __future__ import annotations

import pytest

from services.collection_service import CollectionService


class TestCollectionService:
    """Tests verifying the service delegates correctly to the repository."""

    def test_create_collection(self) -> None:
        """Creating a collection returns a persisted model with an id."""
        svc = CollectionService()
        coll = svc.create_collection("Via Service")
        assert coll.id is not None
        assert coll.name == "Via Service"

    def test_get_collection(self) -> None:
        """A created collection can be fetched by id."""
        svc = CollectionService()
        coll = svc.create_collection("Fetchable")
        fetched = svc.get_collection(coll.id)
        assert fetched is not None
        assert fetched.name == "Fetchable"

    def test_rename_collection(self) -> None:
        """Renaming a collection updates its persisted name."""
        svc = CollectionService()
        coll = svc.create_collection("Original")
        svc.rename_collection(coll.id, "Renamed")
        renamed = svc.get_collection(coll.id)
        assert renamed is not None
        assert renamed.name == "Renamed"

    def test_delete_collection(self) -> None:
        """Deleting a collection removes it from the database."""
        svc = CollectionService()
        coll = svc.create_collection("Doomed")
        svc.delete_collection(coll.id)
        assert svc.get_collection(coll.id) is None

    def test_create_request(self) -> None:
        """Creating a request under a collection returns a persisted model."""
        svc = CollectionService()
        coll = svc.create_collection("Parent")
        req = svc.create_request(coll.id, "GET", "http://test", "Test Req")
        assert req.id is not None
        assert req.name == "Test Req"

    def test_delete_request(self) -> None:
        """Deleting a request removes it from the database."""
        svc = CollectionService()
        coll = svc.create_collection("Parent")
        req = svc.create_request(coll.id, "POST", "http://x", "Ephemeral")
        svc.delete_request(req.id)
        assert svc.get_request(req.id) is None

    def test_create_collection_rejects_empty_name(self) -> None:
        """An empty or whitespace-only name raises ValueError."""
        svc = CollectionService()
        with pytest.raises(ValueError, match="Collection name must not be empty"):
            svc.create_collection("   ")

    def test_create_request_rejects_empty_name(self) -> None:
        """An empty request name raises ValueError."""
        svc = CollectionService()
        coll = svc.create_collection("Parent")
        with pytest.raises(ValueError, match="Request name must not be empty"):
            svc.create_request(coll.id, "GET", "http://x", "  ")

    def test_update_request(self) -> None:
        """update_request delegates to the repository and updates fields."""
        svc = CollectionService()
        coll = svc.create_collection("Parent")
        req = svc.create_request(coll.id, "GET", "http://x", "Updatable")
        svc.update_request(req.id, method="POST", body="data")
        updated = svc.get_request(req.id)
        assert updated is not None
        assert updated.method == "POST"
        assert updated.body == "data"

    def test_update_request_rejects_bad_fields(self) -> None:
        """update_request raises ValueError for non-editable fields."""
        svc = CollectionService()
        coll = svc.create_collection("Parent")
        req = svc.create_request(coll.id, "GET", "http://x", "Req")
        with pytest.raises(ValueError, match="Non-editable fields"):
            svc.update_request(req.id, id=999)


class TestAuthChain:
    """Tests for auth inheritance through the collection chain."""

    def test_request_own_auth(self) -> None:
        """Request with its own auth returns that auth."""
        svc = CollectionService()
        coll = svc.create_collection("Root")
        req = svc.create_request(coll.id, "GET", "http://x", "R")
        svc.update_request(
            req.id, auth={"type": "bearer", "bearer": [{"key": "token", "value": "t"}]}
        )
        result = svc.get_request_auth_chain(req.id)
        assert result is not None
        assert result["type"] == "bearer"

    def test_no_auth_returns_none(self) -> None:
        """Request with no auth anywhere returns None."""
        svc = CollectionService()
        coll = svc.create_collection("Root")
        req = svc.create_request(coll.id, "GET", "http://x", "R")
        assert svc.get_request_auth_chain(req.id) is None


class TestBreadcrumb:
    """Tests for the request breadcrumb path."""

    def test_breadcrumb_path(self) -> None:
        """Breadcrumb returns root → folder → request path."""
        svc = CollectionService()
        root = svc.create_collection("Root")
        req = svc.create_request(root.id, "GET", "http://x", "R")
        crumbs = svc.get_request_breadcrumb(req.id)
        assert len(crumbs) == 2
        assert crumbs[0]["name"] == "Root"
        assert crumbs[0]["type"] == "folder"
        assert crumbs[1]["name"] == "R"
        assert crumbs[1]["type"] == "request"


class TestSavedResponses:
    """Tests for saved responses."""

    def test_save_and_fetch(self) -> None:
        """Save a response and fetch it back."""
        svc = CollectionService()
        coll = svc.create_collection("C")
        req = svc.create_request(coll.id, "GET", "http://x", "R")
        sr_id = svc.save_response(req.id, "Example", "200 OK", 200, "H: V", "body")
        assert sr_id > 0
        responses = svc.get_saved_responses(req.id)
        assert len(responses) == 1
        assert responses[0]["name"] == "Example"
        assert responses[0]["body"] == "body"
