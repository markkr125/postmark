"""Repository layer -- bulk-import functions for collections, requests, and responses.

Unlike the standard session-per-function pattern, import operations use a
**single session** so the entire collection tree is inserted atomically.
If any part fails, the whole import rolls back.

UI code must **not** import this directly -- use the service layer instead.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from database.database import get_session

from .model.collection_model import CollectionModel
from .model.request_model import RequestModel
from .model.saved_response_model import SavedResponseModel

logger = logging.getLogger(__name__)


def _create_request_in_session(
    session: Session,
    collection_id: int,
    req_data: dict[str, Any],
) -> RequestModel:
    """Create a single request row inside an existing *session*.

    *req_data* should follow the ``ParsedRequest`` dictionary schema
    produced by the import parsers.
    """
    headers_raw = req_data.get("headers")
    params_raw = req_data.get("request_parameters")

    request = RequestModel(
        collection_id=collection_id,
        name=req_data.get("name", "Untitled Request"),
        method=req_data.get("method", "GET"),
        url=req_data.get("url", ""),
        body=req_data.get("body"),
        request_parameters=params_raw,
        headers=headers_raw,
        description=req_data.get("description"),
        body_mode=req_data.get("body_mode"),
        body_options=req_data.get("body_options"),
        auth=req_data.get("auth"),
        scripts=req_data.get("scripts"),
        settings=req_data.get("settings"),
        events=req_data.get("events"),
        protocol_profile_behavior=req_data.get("protocol_profile_behavior"),
    )
    session.add(request)
    session.flush()

    # Saved responses (Postman examples)
    for resp_data in req_data.get("saved_responses", []):
        _create_saved_response_in_session(session, request.id, resp_data)

    return request


def _create_saved_response_in_session(
    session: Session,
    request_id: int,
    resp_data: dict[str, Any],
) -> SavedResponseModel:
    """Create a single saved response row inside an existing *session*."""
    response = SavedResponseModel(
        request_id=request_id,
        name=resp_data.get("name", "Untitled Response"),
        status=resp_data.get("status"),
        code=resp_data.get("code"),
        headers=resp_data.get("headers"),
        body=resp_data.get("body"),
        preview_language=resp_data.get("preview_language"),
        original_request=resp_data.get("original_request"),
    )
    session.add(response)
    session.flush()
    return response


def _import_items_recursive(
    session: Session,
    items: list[dict[str, Any]],
    parent_id: int | None,
    counters: dict[str, int],
) -> None:
    """Recursively walk a parsed item tree and persist folders + requests.

    *counters* is mutated in-place to track ``collections_imported``,
    ``requests_imported``, and ``responses_imported``.
    """
    for item in items:
        if item.get("type") == "request" or "request" in item:
            # Leaf request node
            if parent_id is None:
                # Requests must live inside a collection.  Create an
                # auto-folder named after the source collection.
                raise ValueError("Requests must be nested inside a collection folder")
            _create_request_in_session(session, parent_id, item)
            counters["requests_imported"] += 1
            counters["responses_imported"] += len(item.get("saved_responses", []))
        else:
            # Folder node
            folder = CollectionModel(
                name=item.get("name", "Untitled Folder"),
                parent_id=parent_id,
                description=item.get("description"),
                events=item.get("events"),
                variables=item.get("variables"),
                auth=item.get("auth"),
            )
            session.add(folder)
            session.flush()
            counters["collections_imported"] += 1

            # Recurse into children
            children = item.get("children", [])
            _import_items_recursive(session, children, folder.id, counters)


def import_collection_tree(parsed: dict[str, Any]) -> dict[str, int]:
    """Import a fully parsed collection tree into the database.

    *parsed* follows the ``ParsedCollection`` dictionary schema::

        {
            "name": "Collection Name",
            "description": "...",          # optional
            "events": [...],               # optional
            "variables": [...],            # optional
            "auth": {...},                 # optional
            "items": [                     # folders and requests
                { "type": "folder", "name": "...", "children": [...] },
                { "type": "request", "name": "...", "method": "GET", ... },
            ]
        }

    Returns:
        A dict with ``collections_imported``, ``requests_imported``, and
        ``responses_imported`` counts.
    """
    counters: dict[str, int] = {
        "collections_imported": 0,
        "requests_imported": 0,
        "responses_imported": 0,
    }

    with get_session() as session:
        # 1. Create the root collection folder
        root = CollectionModel(
            name=parsed.get("name", "Imported Collection"),
            parent_id=None,
            description=parsed.get("description"),
            events=parsed.get("events"),
            variables=parsed.get("variables"),
            auth=parsed.get("auth"),
        )
        session.add(root)
        session.flush()
        counters["collections_imported"] += 1

        # 2. Recursively import items
        items = parsed.get("items", [])
        _import_items_recursive(session, items, root.id, counters)

    logger.info(
        "Imported collection %r: %d collections, %d requests, %d responses",
        parsed.get("name"),
        counters["collections_imported"],
        counters["requests_imported"],
        counters["responses_imported"],
    )
    return counters
