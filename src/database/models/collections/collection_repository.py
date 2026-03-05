"""Repository layer -- CRUD functions for collections and requests.

This module is the single point of database access for collections and
requests.  UI code must **not** import this directly -- use the service
layer (``services.collection_service``) instead.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select, update

from database.database import get_session

from .model.collection_model import CollectionModel
from .model.request_model import RequestModel

logger = logging.getLogger(__name__)


def _build_tree_dict_lightweight() -> dict[str, Any]:
    """Build the sidebar tree dict by streaming two lightweight queries.

    Rows are consumed one at a time via ``yield_per`` and written directly
    into the target dict, so the intermediate SQLAlchemy ``Row`` objects
    are discarded immediately rather than being held alongside the final
    dict.  Only columns needed for the tree display are fetched:

    - collections: ``id``, ``name``, ``parent_id``
    - requests: ``id``, ``name``, ``method``, ``collection_id``

    Heavy columns (body, headers, JSON blobs) and ``saved_responses`` are
    never touched.
    """
    _YIELD_CHUNK = 500

    col_by_id: dict[int, dict[str, Any]] = {}

    with get_session() as session:
        # 1. Stream collections into the lookup dict
        col_stmt = select(
            CollectionModel.id,
            CollectionModel.name,
            CollectionModel.parent_id,
        )
        for cid, cname, pid in session.execute(col_stmt).yield_per(_YIELD_CHUNK):
            col_by_id[cid] = {
                "id": cid,
                "name": cname,
                "parent_id": pid,
                "type": "folder",
                "children": {},
            }

        # 2. Stream requests directly into their parent collection
        req_stmt = select(
            RequestModel.id,
            RequestModel.name,
            RequestModel.method,
            RequestModel.collection_id,
        )
        for rid, rname, rmethod, rcol_id in session.execute(req_stmt).yield_per(_YIELD_CHUNK):
            parent = col_by_id.get(rcol_id)
            if parent is not None:
                parent["children"][str(rid)] = {
                    "type": "request",
                    "id": rid,
                    "name": rname,
                    "method": rmethod,
                }

    # 3. Build the tree by nesting children under parents
    roots: dict[str, Any] = {}
    for cid, node in col_by_id.items():
        pid = node.pop("parent_id")  # no longer needed in output
        if pid is None:
            roots[str(cid)] = node
        else:
            parent = col_by_id.get(pid)
            if parent is not None:
                parent["children"][str(cid)] = node

    return roots


def fetch_all_collections() -> dict[str, Any]:
    """Return every root collection as a nested dict.

    Uses two streamed scalar queries (``yield_per``) that build the tree
    dict in place, so intermediate ``Row`` objects are discarded
    immediately.  Only the columns needed for the sidebar tree are
    fetched — heavy columns and relationships are never touched.
    """
    return _build_tree_dict_lightweight()


def create_new_collection(name: str, parent_id: int | None = None) -> CollectionModel:
    """Create a new collection with the specified *name* and optional *parent_id*.

    Returns:
        The created ``CollectionModel`` instance.
    """
    with get_session() as session:
        new_collection = CollectionModel(name=name, parent_id=parent_id)
        session.add(new_collection)
        session.flush()
        session.refresh(new_collection)
        return new_collection


def rename_collection(collection_id: int, new_name: str) -> None:
    """Update the ``name`` of the collection with the given *collection_id*."""
    with get_session() as session:
        stmt = (
            update(CollectionModel).where(CollectionModel.id == collection_id).values(name=new_name)
        )
        session.execute(stmt)


def rename_request(request_id: int, new_name: str) -> None:
    """Update the ``name`` of the request with the given *request_id*."""
    with get_session() as session:
        stmt = update(RequestModel).where(RequestModel.id == request_id).values(name=new_name)
        session.execute(stmt)


def delete_collection(collection_id: int) -> None:
    """Delete the collection with the given *collection_id*.

    Cascade rules defined in ``CollectionModel`` ensure that child
    collections and associated requests are removed as well.
    """
    with get_session() as session:
        collection = session.get(CollectionModel, collection_id)
        if collection is None:
            raise ValueError(f"No collection found with id={collection_id}")
        session.delete(collection)


def create_new_request(
    collection_id: int,
    method: str,
    url: str,
    name: str,
    body: str | None = None,
    request_parameters: str | None = None,
    headers: str | None = None,
    scripts: dict | None = None,
    settings: dict | None = None,
    description: str | None = None,
    auth: dict | None = None,
    body_mode: str | None = None,
    body_options: dict | None = None,
    events: dict | None = None,
    protocol_profile_behavior: dict | None = None,
) -> RequestModel:
    """Add a new request to the specified collection.

    Args:
        collection_id: ID of the parent collection.
        method: HTTP method (GET, POST, etc.).
        url: Request URL.
        name: Display name for the request.
        body: Optional body content.
        request_parameters: Optional serialised parameters.
        headers: Optional serialised headers.
        scripts: Optional JSON-serialisable scripts.
        settings: Optional JSON-serialisable settings.
        description: Optional description text.
        auth: Optional auth configuration dict.
        body_mode: Optional body mode (raw, formdata, etc.).
        body_options: Optional body options (language, etc.).
        events: Optional event scripts.
        protocol_profile_behavior: Optional Postman behavior overrides.

    Returns:
        The newly created ``RequestModel`` instance.
    """
    with get_session() as session:
        collection = session.get(CollectionModel, collection_id)
        if not collection:
            raise ValueError(f"Collection with id {collection_id} not found")

        new_request = RequestModel(
            collection_id=collection_id,
            method=method,
            url=url,
            name=name,
            body=body,
            request_parameters=request_parameters,
            headers=headers,
            scripts=scripts,
            settings=settings,
            description=description,
            auth=auth,
            body_mode=body_mode,
            body_options=body_options,
            events=events,
            protocol_profile_behavior=protocol_profile_behavior,
        )
        session.add(new_request)
        session.flush()
        session.refresh(new_request)
        return new_request


def delete_request(request_id: int) -> None:
    """Delete the request identified by *request_id*."""
    with get_session() as session:
        req = session.get(RequestModel, request_id)
        if req is None:
            raise ValueError(f"No request found with id={request_id}")
        session.delete(req)


def update_request_collection(request_id: int, new_collection_id: int | None) -> None:
    """Move a request to a different collection."""
    with get_session() as session:
        stmt = (
            update(RequestModel)
            .where(RequestModel.id == request_id)
            .values(collection_id=new_collection_id)
        )
        session.execute(stmt)


def update_collection_parent(collection_id: int, new_parent_id: int | None) -> None:
    """Move a collection under a different parent."""
    with get_session() as session:
        stmt = (
            update(CollectionModel)
            .where(CollectionModel.id == collection_id)
            .values(parent_id=new_parent_id)
        )
        session.execute(stmt)


def get_collection_by_id(collection_id: int) -> CollectionModel | None:
    """Return the collection with the given *collection_id*, or ``None``."""
    with get_session() as session:
        return (
            session.execute(select(CollectionModel).where(CollectionModel.id == collection_id))
            .scalars()
            .first()
        )


def get_request_by_id(request_id: int) -> RequestModel | None:
    """Return the request with the given *request_id*, or ``None``."""
    with get_session() as session:
        return (
            session.execute(select(RequestModel).where(RequestModel.id == request_id))
            .scalars()
            .first()
        )


def get_request_auth_chain(request_id: int) -> dict[str, Any] | None:
    """Walk the parent collection chain to find the effective auth config.

    Returns the request's own auth if set and not ``noauth``.  Otherwise
    walks up through parent collections and returns the first auth found.
    Returns ``None`` if no auth is configured anywhere in the chain.
    """
    with get_session() as session:
        req = session.get(RequestModel, request_id)
        if req is None:
            return None
        # 1. Check request's own auth
        if req.auth and req.auth.get("type") not in (None, "noauth"):
            return req.auth
        # 2. Walk parent collection chain
        coll = session.get(CollectionModel, req.collection_id)
        while coll is not None:
            if coll.auth and coll.auth.get("type") not in (None, "noauth"):
                return coll.auth
            if coll.parent_id is None:
                break
            coll = session.get(CollectionModel, coll.parent_id)
        return None


def get_request_variable_chain(request_id: int) -> dict[str, str]:
    """Walk the parent collection chain and merge all collection variables.

    Starts from the request's immediate parent collection and walks up to
    the root.  Variables defined on closer ancestors take priority over
    those defined further up the tree (child overrides parent).

    Returns an empty dict if no collection variables are found.
    """
    with get_session() as session:
        req = session.get(RequestModel, request_id)
        if req is None:
            return {}
        # 1. Collect variable lists from nearest ancestor first
        layers: list[list[dict[str, Any]]] = []
        coll = session.get(CollectionModel, req.collection_id)
        while coll is not None:
            if coll.variables:
                layers.append(coll.variables)
            if coll.parent_id is None:
                break
            coll = session.get(CollectionModel, coll.parent_id)
        # 2. Merge from root to leaf so child overrides parent
        merged: dict[str, str] = {}
        for var_list in reversed(layers):
            for entry in var_list:
                if not entry.get("enabled", True):
                    continue
                key = entry.get("key", "")
                value = entry.get("value", "")
                if key:
                    merged[key] = value
        return merged


def get_request_breadcrumb(request_id: int) -> list[dict[str, Any]]:
    """Return the breadcrumb path from root collection to the request.

    Each entry has ``id``, ``name``, and ``type`` (``folder`` or
    ``request``) keys.
    """
    with get_session() as session:
        req = session.get(RequestModel, request_id)
        if req is None:
            return []
        path: list[dict[str, Any]] = []
        # Walk up the collection chain
        coll = session.get(CollectionModel, req.collection_id)
        while coll is not None:
            path.append({"id": coll.id, "name": coll.name, "type": "folder"})
            if coll.parent_id is None:
                break
            coll = session.get(CollectionModel, coll.parent_id)
        path.reverse()
        path.append({"id": req.id, "name": req.name, "type": "request"})
        return path


def get_saved_responses_for_request(request_id: int) -> list[dict[str, Any]]:
    """Return all saved responses for a request as dicts."""
    from .model.saved_response_model import SavedResponseModel

    with get_session() as session:
        stmt = select(SavedResponseModel).where(SavedResponseModel.request_id == request_id)
        responses = list(session.execute(stmt).scalars().all())
        return [
            {
                "id": sr.id,
                "name": sr.name,
                "status": sr.status,
                "code": sr.code,
                "headers": sr.headers,
                "body": sr.body,
            }
            for sr in responses
        ]


def save_response(
    request_id: int,
    name: str,
    status: str | None,
    code: int | None,
    headers: Any,
    body: str | None,
) -> int:
    """Save a response as a named example and return its ID."""
    from .model.saved_response_model import SavedResponseModel

    with get_session() as session:
        sr = SavedResponseModel(
            request_id=request_id,
            name=name,
            status=status,
            code=code,
            headers=headers,
            body=body,
        )
        session.add(sr)
        session.flush()
        return sr.id


# Columns on CollectionModel that may be updated via update_collection().
_EDITABLE_COLLECTION_FIELDS = {
    "description",
    "auth",
    "events",
    "variables",
}


def update_collection(collection_id: int, **fields: Any) -> None:
    """Update one or more editable fields on a collection.

    Only columns listed in ``_EDITABLE_COLLECTION_FIELDS`` are accepted.

    Raises:
        ValueError: If *collection_id* does not exist or an unsupported
            field is passed.
    """
    bad = set(fields) - _EDITABLE_COLLECTION_FIELDS
    if bad:
        raise ValueError(f"Non-editable fields: {bad}")
    if not fields:
        return
    with get_session() as session:
        coll = session.get(CollectionModel, collection_id)
        if coll is None:
            raise ValueError(f"No collection found with id={collection_id}")
        stmt = update(CollectionModel).where(CollectionModel.id == collection_id).values(**fields)
        session.execute(stmt)


def get_collection_breadcrumb(collection_id: int) -> list[dict[str, Any]]:
    """Return the breadcrumb path from root collection to the given folder.

    Each entry has ``id``, ``name``, and ``type`` (always ``folder``) keys.
    """
    with get_session() as session:
        coll = session.get(CollectionModel, collection_id)
        if coll is None:
            return []
        path: list[dict[str, Any]] = []
        while coll is not None:
            path.append({"id": coll.id, "name": coll.name, "type": "folder"})
            if coll.parent_id is None:
                break
            coll = session.get(CollectionModel, coll.parent_id)
        path.reverse()
        return path


def count_collection_requests(collection_id: int) -> int:
    """Count all requests recursively under a collection.

    Walks the collection subtree (children and their descendants) and
    returns the total number of requests contained.
    """
    with get_session() as session:
        # 1. Gather all descendant collection IDs (BFS)
        queue = [collection_id]
        all_ids: list[int] = [collection_id]
        while queue:
            current = queue.pop(0)
            stmt = select(CollectionModel.id).where(CollectionModel.parent_id == current)
            children = list(session.execute(stmt).scalars().all())
            all_ids.extend(children)
            queue.extend(children)

        # 2. Count requests in all collected collection IDs
        count_stmt = (
            select(sa_func.count())
            .select_from(RequestModel)
            .where(RequestModel.collection_id.in_(all_ids))
        )
        result = session.execute(count_stmt).scalar()
        return result or 0


# Columns on RequestModel that may be updated via update_request().
_EDITABLE_REQUEST_FIELDS = {
    "name",
    "method",
    "url",
    "body",
    "request_parameters",
    "headers",
    "description",
    "body_mode",
    "body_options",
    "auth",
    "scripts",
    "settings",
    "events",
    "protocol_profile_behavior",
}


def update_request(request_id: int, **fields: Any) -> None:
    """Update one or more editable fields on a request.

    Only columns listed in ``_EDITABLE_REQUEST_FIELDS`` are accepted.

    Raises:
        ValueError: If *request_id* does not exist or an unsupported
            field is passed.
    """
    bad = set(fields) - _EDITABLE_REQUEST_FIELDS
    if bad:
        raise ValueError(f"Non-editable fields: {bad}")
    if not fields:
        return
    with get_session() as session:
        req = session.get(RequestModel, request_id)
        if req is None:
            raise ValueError(f"No request found with id={request_id}")
        stmt = update(RequestModel).where(RequestModel.id == request_id).values(**fields)
        session.execute(stmt)


def get_recent_requests_for_collection(
    collection_id: int,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return the most recently updated requests under *collection_id*.

    Walks the collection subtree (BFS) and returns up to *limit*
    requests ordered by ``updated_at DESC``.  Each entry is a dict with
    ``name``, ``method``, and ``updated_at`` keys.
    """
    with get_session() as session:
        # 1. Gather all descendant collection IDs (BFS)
        queue = [collection_id]
        all_ids: list[int] = [collection_id]
        while queue:
            current = queue.pop(0)
            stmt = select(CollectionModel.id).where(
                CollectionModel.parent_id == current,
            )
            children = list(session.execute(stmt).scalars().all())
            all_ids.extend(children)
            queue.extend(children)

        # 2. Fetch recently-updated requests
        req_stmt = (
            select(
                RequestModel.name,
                RequestModel.method,
                RequestModel.updated_at,
            )
            .where(RequestModel.collection_id.in_(all_ids))
            .order_by(RequestModel.updated_at.desc())
            .limit(limit)
        )
        rows = session.execute(req_stmt).all()
        return [
            {
                "name": r.name,
                "method": r.method,
                "updated_at": r.updated_at,
            }
            for r in rows
        ]
