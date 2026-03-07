"""Read-only query functions for collections and requests.

Tree traversal, breadcrumb resolution, ancestor chain walks,
and aggregate queries live here.  Mutation / CRUD functions
live in ``collection_repository``.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select

from database.database import get_session

from .model.collection_model import CollectionModel
from .model.request_model import RequestModel

logger = logging.getLogger(__name__)


def _get_descendant_collection_ids(
    session: Any,
    root_id: int,
) -> list[int]:
    """Return *root_id* and all its descendant collection IDs via BFS."""
    queue = [root_id]
    all_ids: list[int] = [root_id]
    while queue:
        current = queue.pop(0)
        stmt = select(CollectionModel.id).where(CollectionModel.parent_id == current)
        children = list(session.execute(stmt).scalars().all())
        all_ids.extend(children)
        queue.extend(children)
    return all_ids


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


def get_request_variable_chain_detailed(request_id: int) -> dict[str, tuple[str, int]]:
    """Walk the parent chain and return ``{key: (value, collection_id)}``.

    Like :func:`get_request_variable_chain` but each entry also carries
    the ``collection_id`` where the variable is defined.  This is used
    by the variable popup to know which collection to update when the
    user edits a value.
    """
    with get_session() as session:
        req = session.get(RequestModel, request_id)
        if req is None:
            return {}
        layers: list[tuple[int, list[dict[str, Any]]]] = []
        coll = session.get(CollectionModel, req.collection_id)
        while coll is not None:
            if coll.variables:
                layers.append((coll.id, coll.variables))
            if coll.parent_id is None:
                break
            coll = session.get(CollectionModel, coll.parent_id)
        merged: dict[str, tuple[str, int]] = {}
        for coll_id, var_list in reversed(layers):
            for entry in var_list:
                if not entry.get("enabled", True):
                    continue
                key = entry.get("key", "")
                value = entry.get("value", "")
                if key:
                    merged[key] = (value, coll_id)
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
        all_ids = _get_descendant_collection_ids(session, collection_id)

        # 2. Count requests in all collected collection IDs
        count_stmt = (
            select(sa_func.count())
            .select_from(RequestModel)
            .where(RequestModel.collection_id.in_(all_ids))
        )
        result = session.execute(count_stmt).scalar()
        return result or 0


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
        all_ids = _get_descendant_collection_ids(session, collection_id)

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
