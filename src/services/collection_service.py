"""
Service layer that sits between the UI and the database repository.

All database access from the UI should go through this module so that
the widgets never import ``collections_utils`` directly.
"""
from __future__ import annotations

import logging

from database.models.collections.collections_utils import (
    create_new_collection, create_new_request, delete_collection,
    delete_request, fetch_all_collections, get_collection_by_id,
    get_request_by_id, rename_collection, rename_request,
    update_collection_parent, update_request_collection)
from database.models.collections.model.collection_model import CollectionModel
from database.models.collections.model.request_model import RequestModel

logger = logging.getLogger(__name__)


class CollectionService:
    """Thin service that wraps repository calls and can be extended with
    business logic (validation, caching, undo/redo, etc.) later."""

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    @staticmethod
    def fetch_all() -> list[CollectionModel]:
        return fetch_all_collections()

    @staticmethod
    def get_collection(collection_id: int) -> CollectionModel | None:
        return get_collection_by_id(collection_id)

    @staticmethod
    def get_request(request_id: int) -> RequestModel | None:
        return get_request_by_id(request_id)

    # ------------------------------------------------------------------
    # Mutations - collections
    # ------------------------------------------------------------------
    @staticmethod
    def create_collection(
        name: str, parent_id: int | None = None
    ) -> CollectionModel:
        return create_new_collection(name, parent_id)

    @staticmethod
    def rename_collection(collection_id: int, new_name: str) -> None:
        rename_collection(collection_id, new_name)

    @staticmethod
    def delete_collection(collection_id: int) -> None:
        delete_collection(collection_id)

    @staticmethod
    def move_collection(
        collection_id: int, new_parent_id: int | None
    ) -> None:
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
        rename_request(request_id, new_name)

    @staticmethod
    def delete_request(request_id: int) -> None:
        delete_request(request_id)

    @staticmethod
    def move_request(
        request_id: int, new_collection_id: int
    ) -> None:
        update_request_collection(request_id, new_collection_id)
