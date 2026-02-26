from __future__ import annotations

import logging

from sqlalchemy import select, update

from database.database import get_session

from .model.collection_model import CollectionModel
from .model.request_model import RequestModel

logger = logging.getLogger(__name__)


def fetch_all_collections() -> list[CollectionModel]:
    """
    Return every root collection (``parent_id IS NULL``).

    The returned objects are fully populated with their ``children``
    and ``requests`` relationships thanks to SQLAlchemy eager loading.
    """
    with get_session() as session:
        return (
            session.query(CollectionModel)
            .filter(CollectionModel.parent_id.is_(None))
            .all()
        )


def create_new_collection(
    name: str, parent_id: int | None = None
) -> CollectionModel:
    """
    Create a new collection with the specified *name* and optional *parent_id*.

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
            update(CollectionModel)
            .where(CollectionModel.id == collection_id)
            .values(name=new_name)
        )
        session.execute(stmt)


def rename_request(request_id: int, new_name: str) -> None:
    """Update the ``name`` of the request with the given *request_id*."""
    with get_session() as session:
        stmt = (
            update(RequestModel)
            .where(RequestModel.id == request_id)
            .values(name=new_name)
        )
        session.execute(stmt)


def delete_collection(collection_id: int) -> None:
    """
    Delete the collection with the given *collection_id*.

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
) -> RequestModel:
    """
    Add a new request to the specified collection.

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


def update_request_collection(
    request_id: int, new_collection_id: int | None
) -> None:
    """Move a request to a different collection."""
    with get_session() as session:
        stmt = (
            update(RequestModel)
            .where(RequestModel.id == request_id)
            .values(collection_id=new_collection_id)
        )
        session.execute(stmt)


def update_collection_parent(
    collection_id: int, new_parent_id: int | None
) -> None:
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
        return session.execute(
            select(CollectionModel).where(CollectionModel.id == collection_id)
        ).scalars().first()


def get_request_by_id(request_id: int) -> RequestModel | None:
    """Return the request with the given *request_id*, or ``None``."""
    with get_session() as session:
        return session.execute(
            select(RequestModel).where(RequestModel.id == request_id)
        ).scalars().first()
