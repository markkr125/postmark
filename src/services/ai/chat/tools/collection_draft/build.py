"""Assemble a ``ParsedCollection`` tree from an incremental draft."""

from __future__ import annotations

import re
from typing import Any

from services.ai.chat.tools.collection_draft.config import draft_script_language
from services.ai.chat.tools.collection_draft.state import CollectionDraft, DraftRequest
from services.import_parser.models import (
    ImportResult,
    ParsedCollection,
    ParsedFolder,
    ParsedRequest,
)

# Rewrite doc/OpenAPI/Postman placeholders to the app's ``{{var}}`` format.
_ANGLE_VAR_RE = re.compile(r"<([A-Za-z_][A-Za-z0-9_-]*)>")
_BRACE_VAR_RE = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")
_COLON_PATH_VAR_RE = re.compile(r"/:([A-Za-z_][A-Za-z0-9_]*)")
_DOUBLE_BRACE_VAR_RE = re.compile(r"\{\{([A-Za-z_$][A-Za-z0-9_]*)\}\}")


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


def normalize_url_variables(url: str) -> str:
    """Rewrite ``{var}``, ``:var``, and ``<var>`` placeholders to ``{{var}}``.

    Only the path portion (before ``?``) is rewritten for ``:var`` so schemes,
    ports, userinfo, and query values are never touched. Bodies are never
    scanned by callers of this helper.
    """
    text = url or ""
    if "?" in text:
        path, query = text.split("?", 1)
        query_suffix = "?" + query
    else:
        path, query_suffix = text, ""
    path = _ANGLE_VAR_RE.sub(r"{{\1}}", path)
    path = _BRACE_VAR_RE.sub(r"{{\1}}", path)
    path = _COLON_PATH_VAR_RE.sub(r"/{{\1}}", path)
    return path + query_suffix


def _scripts_dict(*, pre: str, test: str) -> dict[str, str] | None:
    """Return a scripts/events dict, or None when both script bodies are empty."""
    pre_code = (pre or "").strip()
    test_code = (test or "").strip()
    if not pre_code and not test_code:
        return None
    language = draft_script_language()
    result: dict[str, str] = {
        "language": language,
        "pre_language": language,
        "test_language": language,
    }
    if pre_code:
        result["pre_request"] = pre_code
    if test_code:
        result["test"] = test_code
    return result


def _param_rows(params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize draft param rows for persistence."""
    rows: list[dict[str, Any]] = []
    for raw in params:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        if not key:
            continue
        row: dict[str, Any] = {
            "key": key,
            "value": str(raw.get("value") or ""),
            "enabled": bool(raw.get("enabled", True)),
        }
        description = str(raw.get("description") or "").strip()
        if description:
            row["description"] = description
        rows.append(row)
    return rows


def _parsed_request(request: DraftRequest) -> ParsedRequest:
    """Convert one draft request into the import intermediate representation."""
    parsed: ParsedRequest = {
        "type": "request",
        "name": request.name,
        "method": request.method.upper(),
        "url": normalize_url_variables(request.url),
    }
    if request.headers:
        parsed["headers"] = list(request.headers)
    params = _param_rows(request.params)
    if params:
        parsed["request_parameters"] = params
    if request.body:
        parsed["body"] = request.body
        parsed["body_mode"] = "raw"
    if request.description:
        parsed["description"] = request.description
    scripts = _scripts_dict(pre=request.pre_script, test=request.test_script)
    if scripts:
        parsed["scripts"] = scripts
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


def _variable_names_in_text(text: str) -> set[str]:
    """Return ``{{var}}`` names in *text*, excluding dynamic ``$…`` vars."""
    names: set[str] = set()
    for match in _DOUBLE_BRACE_VAR_RE.finditer(text or ""):
        name = match.group(1)
        if name.startswith("$"):
            continue
        names.add(name)
    return names


def collect_variable_rows(draft: CollectionDraft) -> list[dict[str, Any]]:
    """Merge explicit draft variables with auto-detected ``{{var}}`` names.

    Auto-detected names come from rewritten request URLs and header values.
    Request bodies are never scanned (JSON braces are not variables).
    """
    by_key: dict[str, dict[str, Any]] = {}
    for raw in draft.variables:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        if not key:
            continue
        row: dict[str, Any] = {
            "key": key,
            "value": str(raw.get("value") or ""),
            "enabled": bool(raw.get("enabled", True)),
            "type": str(raw.get("type") or "default"),
        }
        description = str(raw.get("description") or "").strip()
        if description:
            row["description"] = description
        by_key[key] = row

    detected: set[str] = set()
    for request in draft.requests:
        detected |= _variable_names_in_text(normalize_url_variables(request.url))
        for header in request.headers:
            if isinstance(header, dict):
                detected |= _variable_names_in_text(str(header.get("value") or ""))
                detected |= _variable_names_in_text(str(header.get("key") or ""))
    for name in sorted(detected):
        if name not in by_key:
            by_key[name] = {
                "key": name,
                "value": "",
                "enabled": True,
                "type": "default",
            }
    return list(by_key.values())


def enrichment_summary(draft: CollectionDraft) -> dict[str, Any]:
    """Return counts used in the finish observation / assistant reply."""
    variables = collect_variable_rows(draft)
    request_scripts = sum(
        1 for request in draft.requests if (request.pre_script or request.test_script).strip()
    )
    return {
        "has_description": bool((draft.description or "").strip()),
        "variables": len(variables),
        "collection_scripts": bool((draft.pre_script or draft.test_script).strip()),
        "request_scripts": request_scripts,
        "requests_with_params": sum(1 for request in draft.requests if request.params),
    }


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
    variables = collect_variable_rows(draft)
    if variables:
        collection["variables"] = variables
    events = _scripts_dict(pre=draft.pre_script, test=draft.test_script)
    if events:
        collection["events"] = events
    return collection


def build_import_result(draft: CollectionDraft) -> ImportResult:
    """Wrap the draft collection in an ``ImportResult`` ready to persist."""
    errors: list[str] = []
    collections: list[ParsedCollection] = [build_parsed_collection(draft)]
    environments: list[Any] = []
    return {"collections": collections, "environments": environments, "errors": errors}


__all__ = [
    "build_import_result",
    "build_parsed_collection",
    "collect_variable_rows",
    "enrichment_summary",
    "normalize_url_variables",
]
