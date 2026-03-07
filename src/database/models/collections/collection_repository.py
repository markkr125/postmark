"""Repository layer -- CRUD / mutation functions for collections and requests.

Read-only queries (tree fetching, breadcrumbs, ancestor chain walks)
live in :mod:`collection_query_repository`.

UI code must **not** import this directly -- use the service layer
(``services.collection_service``) instead.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import update

from database.database import get_session

from .model.collection_model import CollectionModel
from .model.request_model import RequestModel

logger = logging.getLogger(__name__)


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
