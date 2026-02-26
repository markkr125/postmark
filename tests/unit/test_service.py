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
