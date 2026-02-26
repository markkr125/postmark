"""Unit tests for the collection service layer."""

from __future__ import annotations

from services.collection_service import CollectionService


class TestCollectionService:
    """Smoke tests verifying the service delegates correctly to the repository."""

    def test_service_roundtrip(self):
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
