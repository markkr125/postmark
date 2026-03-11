"""Service layer that sits between the UI and the database repository.

All database access from the UI should go through this module so that
the widgets never import ``collection_repository`` directly.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from database.models.collections.collection_query_repository import (
    count_collection_requests,
    fetch_all_collections,
    get_collection_breadcrumb,
    get_collection_by_id,
    get_collection_inherited_auth,
    get_recent_requests_for_collection,
    get_request_auth_chain,
    get_request_breadcrumb,
    get_request_by_id,
    get_request_inherited_auth,
    get_request_variable_chain,
    get_saved_responses_for_request,
)
from database.models.collections.collection_repository import (
    create_new_collection,
    create_new_request,
    delete_collection,
    delete_request,
    rename_collection,
    rename_request,
    save_response,
    update_collection,
    update_collection_parent,
    update_request,
    update_request_collection,
)
from database.models.collections.model.collection_model import CollectionModel
from database.models.collections.model.request_model import RequestModel

logger = logging.getLogger(__name__)


class RequestLoadDict(TypedDict, total=False):
    """Data dict used to populate a :class:`RequestEditorWidget`.

    Built from :class:`RequestModel` attributes in
    ``_TabControllerMixin._open_request``.  All keys are optional
    because callers may omit fields they don't need.
    """

    name: str
    method: str
    url: str
    body: str | None
    request_parameters: str | list[dict[str, Any]] | None
    headers: str | list[dict[str, Any]] | None
    description: str | None
    scripts: dict[str, Any] | None
    body_mode: str | None
    body_options: dict[str, Any] | None
    auth: dict[str, Any] | None


class CollectionService:
    """Service that wraps repository calls with validation and logging.

    All methods are ``@staticmethod`` today -- the class exists so it can
    later gain instance state for caching, undo/redo, or batch operations
    without changing the call sites in the UI layer.
    """

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    @staticmethod
    def fetch_all() -> dict[str, Any]:
        """Return all root-level collections as a nested dict."""
        result = fetch_all_collections()
        logger.debug("Fetched collections tree with %d roots", len(result))
        return result

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
        """Create a new collection, optionally nested under *parent_id*.

        Raises:
            ValueError: If *name* is empty or whitespace-only.
        """
        name = name.strip()
        if not name:
            raise ValueError("Collection name must not be empty")
        result = create_new_collection(name, parent_id)
        logger.info("Created collection id=%s name=%r parent=%s", result.id, name, parent_id)
        return result

    @staticmethod
    def rename_collection(collection_id: int, new_name: str) -> None:
        """Rename an existing collection.

        Raises:
            ValueError: If *new_name* is empty or whitespace-only.
        """
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Collection name must not be empty")
        rename_collection(collection_id, new_name)
        logger.info("Renamed collection id=%s to %r", collection_id, new_name)

    @staticmethod
    def delete_collection(collection_id: int) -> None:
        """Delete a collection and cascade to children and requests."""
        delete_collection(collection_id)
        logger.info("Deleted collection id=%s", collection_id)

    @staticmethod
    def move_collection(collection_id: int, new_parent_id: int | None) -> None:
        """Re-parent a collection (or move to root if *new_parent_id* is None).

        Raises:
            ValueError: If trying to move a collection into itself.
        """
        if collection_id == new_parent_id:
            raise ValueError("Cannot move a collection into itself")
        update_collection_parent(collection_id, new_parent_id)
        logger.info("Moved collection id=%s to parent=%s", collection_id, new_parent_id)

    @staticmethod
    def update_collection(collection_id: int, **fields: Any) -> None:
        """Update one or more editable fields on a collection.

        Only columns listed in the repository's
        ``_EDITABLE_COLLECTION_FIELDS`` are accepted.

        Raises:
            ValueError: If *collection_id* does not exist or a field
                name is invalid.
        """
        update_collection(collection_id, **fields)
        logger.info("Updated collection id=%s fields=%s", collection_id, list(fields))

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
        """Create a new request inside the given collection.

        Raises:
            ValueError: If *name* or *method* is empty.
        """
        name = name.strip()
        method = method.strip().upper()
        if not name:
            raise ValueError("Request name must not be empty")
        if not method:
            raise ValueError("HTTP method must not be empty")
        result = create_new_request(
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
        logger.info("Created request id=%s in collection=%s", result.id, collection_id)
        return result

    @staticmethod
    def rename_request(request_id: int, new_name: str) -> None:
        """Rename an existing request.

        Raises:
            ValueError: If *new_name* is empty or whitespace-only.
        """
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Request name must not be empty")
        rename_request(request_id, new_name)
        logger.info("Renamed request id=%s to %r", request_id, new_name)

    @staticmethod
    def delete_request(request_id: int) -> None:
        """Delete a single request."""
        delete_request(request_id)
        logger.info("Deleted request id=%s", request_id)

    @staticmethod
    def move_request(request_id: int, new_collection_id: int) -> None:
        """Move a request to a different collection."""
        update_request_collection(request_id, new_collection_id)
        logger.info("Moved request id=%s to collection=%s", request_id, new_collection_id)

    @staticmethod
    def update_request(request_id: int, **fields: Any) -> None:
        """Update one or more editable fields on a request.

        Only columns listed in the repository's ``_EDITABLE_REQUEST_FIELDS``
        are accepted.

        Raises:
            ValueError: If *request_id* does not exist or a field name is
                invalid.
        """
        update_request(request_id, **fields)
        logger.info("Updated request id=%s fields=%s", request_id, list(fields))

    # ------------------------------------------------------------------
    # Auth inheritance
    # ------------------------------------------------------------------
    @staticmethod
    def get_request_auth_chain(request_id: int) -> dict[str, Any] | None:
        """Return the effective auth for a request, walking parent chain.

        Respects the inherit / noauth distinction:

        - ``auth is None`` → inherit from parent (walk up the chain).
        - ``{"type": "noauth"}`` → explicit no-auth (stop).
        - Any other auth dict → use it.
        """
        return get_request_auth_chain(request_id)

    @staticmethod
    def get_request_inherited_auth(request_id: int) -> dict[str, Any] | None:
        """Return only the *parent* auth a request would inherit.

        Skips the request's own auth and walks from its parent
        collection upward.  Used by the "Inherit auth from parent" UI
        to preview the resolved auth.
        """
        return get_request_inherited_auth(request_id)

    @staticmethod
    def get_collection_inherited_auth(collection_id: int) -> dict[str, Any] | None:
        """Return only the *parent* auth a collection would inherit.

        Starts from the collection's parent and walks up.  Used by
        the folder editor's "Inherit auth from parent" UI.
        """
        return get_collection_inherited_auth(collection_id)

    @staticmethod
    def get_request_variable_chain(request_id: int) -> dict[str, str]:
        """Return the merged collection variables for a request.

        Walks the parent collection chain from the request's immediate
        parent up to the root, merging ``variables`` arrays.  Variables
        from closer ancestors take priority over those further up.
        Returns an empty dict if no collection variables are found.
        """
        return get_request_variable_chain(request_id)

    # ------------------------------------------------------------------
    # Breadcrumb
    # ------------------------------------------------------------------
    @staticmethod
    def get_request_breadcrumb(request_id: int) -> list[dict[str, Any]]:
        """Return the breadcrumb path from root collection to request."""
        return get_request_breadcrumb(request_id)

    @staticmethod
    def get_collection_breadcrumb(collection_id: int) -> list[dict[str, Any]]:
        """Return the breadcrumb path from root collection to the folder."""
        return get_collection_breadcrumb(collection_id)

    # ------------------------------------------------------------------
    # Folder stats
    # ------------------------------------------------------------------
    @staticmethod
    def get_folder_request_count(collection_id: int) -> int:
        """Return the total number of requests under a collection subtree."""
        return count_collection_requests(collection_id)

    # ------------------------------------------------------------------
    # Recent requests
    # ------------------------------------------------------------------
    @staticmethod
    def get_recent_requests(
        collection_id: int,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return the most recently updated requests in a collection subtree."""
        return get_recent_requests_for_collection(collection_id, limit)

    # ------------------------------------------------------------------
    # Saved responses
    # ------------------------------------------------------------------
    @staticmethod
    def get_saved_responses(request_id: int) -> list[dict[str, Any]]:
        """Return all saved responses (examples) for a request."""
        return get_saved_responses_for_request(request_id)

    @staticmethod
    def save_response(
        request_id: int,
        name: str,
        status: str | None,
        code: int | None,
        headers: Any,
        body: str | None,
    ) -> int:
        """Save a response as a named example and return its ID."""
        result = save_response(request_id, name, status, code, headers, body)
        logger.info("Saved response for request id=%s", request_id)
        return result
