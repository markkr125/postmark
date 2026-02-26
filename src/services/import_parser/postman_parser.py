"""Parser for Postman Collection v2.1.0 and Environment JSON files.

Handles individual collection files, environment files, and archive
folders (containing an ``archive.json`` index with UUIDs referencing
``collection/`` and ``environment/`` sub-directories).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

from .models import (
    ImportResult,
    ParsedCollection,
    ParsedEnvironment,
    ParsedFolder,
    ParsedRequest,
    ParsedSavedResponse,
)

logger = logging.getLogger(__name__)

# The schema URL that identifies a Postman Collection v2.1.0 file.
_POSTMAN_SCHEMA_V21 = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def detect_postman_type(data: dict[str, Any]) -> Literal["collection", "environment", "archive", "unknown"]:
    """Auto-detect whether *data* represents a collection, environment, or archive index.

    Returns one of ``"collection"``, ``"environment"``, ``"archive"``,
    or ``"unknown"``.
    """
    if "info" in data and "item" in data:
        return "collection"
    if "values" in data and "name" in data:
        return "environment"
    if "collection" in data and "environment" in data:
        return "archive"
    return "unknown"


def parse_collection_file(path: Path) -> ImportResult:
    """Parse a single Postman Collection v2.1.0 JSON file.

    Returns an ``ImportResult`` with one collection in ``collections``
    or errors if the file is invalid.
    """
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return ImportResult(collections=[], environments=[], errors=[f"Empty file: {path.name}"])
        data = json.loads(text)
    except (json.JSONDecodeError, OSError) as exc:
        return ImportResult(collections=[], environments=[], errors=[f"{path.name}: {exc}"])

    file_type = detect_postman_type(data)
    if file_type == "collection":
        collection = _parse_collection_data(data)
        return ImportResult(collections=[collection], environments=[], errors=[])
    if file_type == "environment":
        env = _parse_environment_data(data)
        return ImportResult(collections=[], environments=[env], errors=[])
    return ImportResult(
        collections=[], environments=[],
        errors=[f"{path.name}: unrecognised Postman format"],
    )


def parse_environment_file(path: Path) -> ImportResult:
    """Parse a single Postman Environment JSON file."""
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return ImportResult(collections=[], environments=[], errors=[f"Empty file: {path.name}"])
        data = json.loads(text)
    except (json.JSONDecodeError, OSError) as exc:
        return ImportResult(collections=[], environments=[], errors=[f"{path.name}: {exc}"])

    if detect_postman_type(data) != "environment":
        return ImportResult(
            collections=[], environments=[],
            errors=[f"{path.name}: not a valid environment file"],
        )

    env = _parse_environment_data(data)
    return ImportResult(collections=[], environments=[env], errors=[])


def parse_archive_folder(path: Path) -> ImportResult:
    """Parse a Postman data-dump folder containing ``archive.json``.

    The folder is expected to contain:
    - ``archive.json`` — index with ``collection`` and ``environment`` UUID maps.
    - ``collection/*.json`` — individual collection files.
    - ``environment/*.json`` — individual environment files.
    """
    collections: list[ParsedCollection] = []
    environments: list[ParsedEnvironment] = []
    errors: list[str] = []

    archive_index = path / "archive.json"
    if not archive_index.exists():
        # Not an archive folder — try parsing each JSON file individually.
        return _parse_json_folder(path)

    try:
        index_data = json.loads(archive_index.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return ImportResult(collections=[], environments=[], errors=[f"archive.json: {exc}"])

    # 1. Parse collections
    coll_dir = path / "collection"
    for uuid in index_data.get("collection", {}):
        coll_file = coll_dir / f"{uuid}.json"
        if not coll_file.exists():
            errors.append(f"Collection file missing: {uuid}.json")
            continue
        result = parse_collection_file(coll_file)
        collections.extend(result.get("collections", []))
        errors.extend(result.get("errors", []))

    # 2. Parse environments
    env_dir = path / "environment"
    for uuid in index_data.get("environment", {}):
        env_file = env_dir / f"{uuid}.json"
        if not env_file.exists():
            errors.append(f"Environment file missing: {uuid}.json")
            continue
        result = parse_environment_file(env_file)
        environments.extend(result.get("environments", []))
        errors.extend(result.get("errors", []))

    return ImportResult(collections=collections, environments=environments, errors=errors)


def parse_json_text(text: str) -> ImportResult:
    """Parse raw JSON text as a collection or environment.

    Returns an ``ImportResult`` with the detected data, or errors.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return ImportResult(collections=[], environments=[], errors=[f"Invalid JSON: {exc}"])

    file_type = detect_postman_type(data)
    if file_type == "collection":
        collection = _parse_collection_data(data)
        return ImportResult(collections=[collection], environments=[], errors=[])
    if file_type == "environment":
        env = _parse_environment_data(data)
        return ImportResult(collections=[], environments=[env], errors=[])
    return ImportResult(
        collections=[], environments=[],
        errors=["Unrecognised JSON format — expected a Postman collection or environment"],
    )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _parse_json_folder(path: Path) -> ImportResult:
    """Parse all ``*.json`` files in a directory (non-archive folder)."""
    collections: list[ParsedCollection] = []
    environments: list[ParsedEnvironment] = []
    errors: list[str] = []

    for json_file in sorted(path.rglob("*.json")):
        result = parse_collection_file(json_file)
        collections.extend(result.get("collections", []))
        environments.extend(result.get("environments", []))
        errors.extend(result.get("errors", []))

    return ImportResult(collections=collections, environments=environments, errors=errors)


def _parse_collection_data(data: dict[str, Any]) -> ParsedCollection:
    """Convert raw Postman collection JSON into a ``ParsedCollection``."""
    info = data.get("info", {})
    items = _parse_items(data.get("item", []))

    return ParsedCollection(
        name=info.get("name", "Untitled Collection"),
        description=info.get("description"),
        events=data.get("event"),
        variables=data.get("variable"),
        auth=data.get("auth"),
        items=items,
    )


def _parse_environment_data(data: dict[str, Any]) -> ParsedEnvironment:
    """Convert raw Postman environment JSON into a ``ParsedEnvironment``."""
    values: list[dict[str, Any]] = []
    for val in data.get("values", []):
        values.append({
            "key": val.get("key", ""),
            "value": val.get("value", ""),
            "enabled": val.get("enabled", True),
            "type": val.get("type", "text"),
        })
    return ParsedEnvironment(
        name=data.get("name", "Untitled Environment"),
        values=values,
    )


def _parse_items(items: list[dict[str, Any]]) -> list[ParsedFolder | ParsedRequest]:
    """Recursively convert Postman ``item`` array into parsed nodes."""
    result: list[ParsedFolder | ParsedRequest] = []
    for item in items:
        if "request" in item:
            result.append(_parse_request_item(item))
        elif "item" in item:
            result.append(_parse_folder_item(item))
        else:
            # Skip unrecognised items
            logger.warning("Skipping unrecognised item: %s", item.get("name", "<unnamed>"))
    return result


def _parse_folder_item(item: dict[str, Any]) -> ParsedFolder:
    """Convert a Postman folder-type item into a ``ParsedFolder``."""
    children = _parse_items(item.get("item", []))
    return ParsedFolder(
        type="folder",
        name=item.get("name", "Untitled Folder"),
        description=item.get("description"),
        auth=item.get("auth"),
        events=item.get("event"),
        children=children,
    )


def _parse_request_item(item: dict[str, Any]) -> ParsedRequest:
    """Convert a Postman request-type item into a ``ParsedRequest``."""
    req = item.get("request", {})
    if isinstance(req, str):
        # Postman sometimes stores the URL directly as a string.
        return ParsedRequest(
            type="request",
            name=item.get("name", "Untitled Request"),
            method="GET",
            url=req,
        )

    url = _extract_url(req.get("url", ""))
    body, body_mode, body_options = _extract_body(req.get("body"))
    headers = _extract_key_value_list(req.get("header", []))
    query_params = _extract_query_params(req.get("url", {}))

    saved_responses = [
        _parse_saved_response(resp)
        for resp in item.get("response", [])
    ]

    return ParsedRequest(
        type="request",
        name=item.get("name", "Untitled Request"),
        method=req.get("method", "GET"),
        url=url,
        headers=headers if headers else None,
        request_parameters=query_params if query_params else None,
        body=body,
        body_mode=body_mode,
        body_options=body_options,
        auth=req.get("auth"),
        description=req.get("description"),
        events=item.get("event"),
        protocol_profile_behavior=item.get("protocolProfileBehavior"),
        saved_responses=saved_responses,
    )


def _parse_saved_response(resp: dict[str, Any]) -> ParsedSavedResponse:
    """Convert a Postman saved-response entry."""
    return ParsedSavedResponse(
        name=resp.get("name", "Untitled Response"),
        status=resp.get("status"),
        code=resp.get("code"),
        headers=resp.get("header"),
        body=resp.get("body"),
        preview_language=resp.get("_postman_previewlanguage"),
        original_request=resp.get("originalRequest"),
    )


def _extract_url(url_data: str | dict[str, Any]) -> str:
    """Extract the raw URL string from a Postman URL object or string."""
    if isinstance(url_data, str):
        return url_data
    raw: str = url_data.get("raw", "")
    return raw


def _extract_query_params(url_data: str | dict[str, Any]) -> list[dict[str, Any]]:
    """Extract query parameters from a Postman URL object."""
    if isinstance(url_data, str):
        return []
    return [
        {
            "key": p.get("key", ""),
            "value": p.get("value", ""),
            "disabled": p.get("disabled", False),
        }
        for p in url_data.get("query", [])
        if isinstance(p, dict)
    ]


def _extract_body(
    body_data: dict[str, Any] | None,
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """Extract body content, mode, and options from a Postman body object.

    Returns:
        A 3-tuple of ``(body_text, body_mode, body_options)``.
    """
    if not body_data:
        return None, None, None

    mode = body_data.get("mode")
    options = body_data.get("options")
    body_text: str | None = None

    if mode == "raw":
        body_text = body_data.get("raw")
    elif mode == "graphql":
        graphql = body_data.get("graphql", {})
        body_text = json.dumps(graphql) if graphql else None
    elif mode in ("formdata", "urlencoded"):
        # Store the structured form data as a JSON string.
        form_data = body_data.get(mode, [])
        body_text = json.dumps(form_data) if form_data else None
    elif mode == "file":
        file_data = body_data.get("file", {})
        body_text = json.dumps(file_data) if file_data else None

    return body_text, mode, options


def _extract_key_value_list(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalise a Postman header/param list to a consistent schema."""
    if not items:
        return []
    return [
        {
            "key": item.get("key", ""),
            "value": item.get("value", ""),
            "disabled": item.get("disabled", False),
            "type": item.get("type", "text"),
        }
        for item in items
        if isinstance(item, dict)
    ]
