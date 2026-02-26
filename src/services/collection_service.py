"""Service layer that sits between the UI and the database repository.

All database access from the UI should go through this module so that
the widgets never import ``collection_repository`` directly.
"""

from __future__ import annotations

import logging

from database.models.collections.collection_repository import (
    create_new_collection, create_new_request, delete_collection,
    delete_request, fetch_all_collections, get_collection_by_id,
    get_request_by_id, rename_collection, rename_request,
    update_collection_parent, update_request_collection)
from database.models.collections.model.collection_model import CollectionModel
from database.models.collections.model.request_model import RequestModel

logger = logging.getLogger(__name__)


class CollectionService:
    """Thin service that wraps repository calls.

    All methods are ``@staticmethod`` today -- the class exists so it can
    later gain instance state for caching, undo/redo, or validation without
    changing the call sites in the UI layer.
    """

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    @staticmethod
    def fetch_all() -> list[CollectionModel]:
        """Return all root-level collections with children eagerly loaded."""
        return fetch_all_collections()

    @staticmethod
    def get_collection(collection_id: int) -> CollectionModel | None:
        """Look up a single collection by primary key."""
        return get_collection_by_id(collection_id)

    @staticmethod
    def get_request(request_id: int) -> RequestModel | None:
        """Look up a single request by primary key."""
        return get_request_by_id(request_id)

    # ------------------------------------------------------------------
    # Mutations - collections
    # ------------------------------------------------------------------
    @staticmethod
    def create_collection(name: str, parent_id: int | None = None) -> CollectionModel:
        """Create a new collection, optionally nested under *parent_id*."""
        return create_new_collection(name, parent_id)

    @staticmethod
    def rename_collection(collection_id: int, new_name: str) -> None:
        """Rename an existing collection."""
        rename_collection(collection_id, new_name)

    @staticmethod
    def delete_collection(collection_id: int) -> None:
        """Delete a collection and cascade to children and requests."""
        delete_collection(collection_id)

    @staticmethod
    def move_collection(collection_id: int, new_parent_id: int | None) -> None:
        """Re-parent a collection (or move to root if *new_parent_id* is None)."""
        update_collection_parent(collection_id, new_parent_id)

    # ------------------------------------------------------------------
    # Mutations - requests
    # ------------------------------------------------------------------
    @staticmethod
    def create_request(
        collection_id: int,
        method: str,
        url: str,
        name: str,
        body: str | None = None,
        request_parameters: str | None = None,
        headers: str | None = None,
        scripts: dict | None = None,
        settings: dict | None = None,
    ) -> RequestModel:
        """Create a new request inside the given collection."""
        return create_new_request(
            collection_id,
            method,
            url,
            name,
            body=body,
            request_parameters=request_parameters,
            headers=headers,
            scripts=scripts,
            settings=settings,
        )

    @staticmethod
    def rename_request(request_id: int, new_name: str) -> None:
        """Rename an existing request."""
        rename_request(request_id, new_name)

    @staticmethod
    def delete_request(request_id: int) -> None:
        """Delete a single request."""
        delete_request(request_id)

    @staticmethod
    def move_request(request_id: int, new_collection_id: int) -> None:
        """Move a request to a different collection."""
        update_request_collection(request_id, new_collection_id)
