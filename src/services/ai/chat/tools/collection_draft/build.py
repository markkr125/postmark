"""Assemble a ``ParsedCollection`` tree from an incremental draft."""

from __future__ import annotations

from typing import Any

from services.ai.chat.tools.collection_draft.state import CollectionDraft, DraftRequest
from services.import_parser.models import (
    ImportResult,
    ParsedCollection,
    ParsedFolder,
    ParsedRequest,
)


def _new_folder(name: str) -> ParsedFolder:
    """Return an empty parsed folder node."""
    return {
        "type": "folder",
        "name": name,
        "description": None,
        "auth": None,
        "events": None,
        "children": [],
    }


def _parsed_request(request: DraftRequest) -> ParsedRequest:
    """Convert one draft request into the import intermediate representation."""
    parsed: ParsedRequest = {
        "type": "request",
        "name": request.name,
        "method": request.method.upper(),
        "url": request.url,
    }
    if request.headers:
        parsed["headers"] = list(request.headers)
    if request.body:
        parsed["body"] = request.body
        parsed["body_mode"] = "raw"
    if request.description:
        parsed["description"] = request.description
    return parsed


def _ensure_folder(
    items: list[ParsedFolder | ParsedRequest],
    index: dict[tuple[str, ...], ParsedFolder],
    path: tuple[str, ...],
) -> list[ParsedFolder | ParsedRequest]:
    """Return the child list for *path*, creating intermediate folders as needed."""
    children = items
    for depth in range(len(path)):
        prefix = path[: depth + 1]
        folder = index.get(prefix)
        if folder is None:
            folder = _new_folder(prefix[-1])
            index[prefix] = folder
            children.append(folder)
        children = folder["children"]
    return children


def build_parsed_collection(draft: CollectionDraft) -> ParsedCollection:
    """Build the collection tree, preserving the order requests were added."""
    items: list[ParsedFolder | ParsedRequest] = []
    index: dict[tuple[str, ...], ParsedFolder] = {}

    for path in draft.folders:
        _ensure_folder(items, index, path)
    for request in draft.requests:
        children = _ensure_folder(items, index, request.folder_path)
        children.append(_parsed_request(request))

    collection: ParsedCollection = {"name": draft.name, "items": items}
    description = draft.description or (f"Imported from {draft.source}" if draft.source else "")
    if description:
        collection["description"] = description
    if draft.variables:
        collection["variables"] = [dict(var) for var in draft.variables]
    return collection


def build_import_result(draft: CollectionDraft) -> ImportResult:
    """Wrap the draft collection in an ``ImportResult`` ready to persist."""
    errors: list[str] = []
    collections: list[ParsedCollection] = [build_parsed_collection(draft)]
    environments: list[Any] = []
    return {"collections": collections, "environments": environments, "errors": errors}


__all__ = ["build_import_result", "build_parsed_collection"]
