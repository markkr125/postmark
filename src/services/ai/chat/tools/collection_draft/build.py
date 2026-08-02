"""Assemble a ``ParsedCollection`` tree from an incremental draft."""

from __future__ import annotations

import json
import re
from typing import Any

from services.ai.chat.tools.collection_draft.config import draft_script_language
from services.ai.chat.tools.collection_draft.recipes import (
    build_signing_script,
    recipe_variables,
)
from services.ai.chat.tools.collection_draft.state import (
    CollectionDraft,
    DraftRequest,
    DraftSavedResponse,
)
from services.import_parser.models import (
    ImportResult,
    ParsedCollection,
    ParsedFolder,
    ParsedRequest,
    ParsedSavedResponse,
)

# Rewrite doc/OpenAPI/Postman placeholders to the app's ``{{var}}`` format.
_ANGLE_VAR_RE = re.compile(r"<([A-Za-z_][A-Za-z0-9_-]*)>")
_BRACE_VAR_RE = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")
_COLON_PATH_VAR_RE = re.compile(r"/:([A-Za-z_][A-Za-z0-9_]*)")
_DOUBLE_BRACE_VAR_RE = re.compile(r"\{\{([A-Za-z_$][A-Za-z0-9_]*)\}\}")
_AUTH_CREDENTIAL_VARS: dict[str, tuple[str, ...]] = {
    "apikey": ("apiKey",),
    "bearer": ("bearerToken",),
    "basic": ("username", "password"),
    "oauth2": ("oauth_access_token",),
}


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


def _merge_headers(
    default_headers: list[dict[str, Any]],
    request_headers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge collection default headers with request headers (request wins).

    Request headers are kept in order, including duplicate keys. A default
    header is omitted when the request already sets the same key
    (case-insensitive).
    """
    request_keys: set[str] = set()
    normalized_request: list[dict[str, Any]] = []
    for raw in request_headers:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        if not key:
            continue
        request_keys.add(key.lower())
        normalized_request.append(
            {
                "key": key,
                "value": str(raw.get("value") or ""),
                "enabled": bool(raw.get("enabled", True)),
            }
        )
    out: list[dict[str, Any]] = []
    for raw in default_headers:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        if not key or key.lower() in request_keys:
            continue
        out.append(
            {
                "key": key,
                "value": str(raw.get("value") or ""),
                "enabled": bool(raw.get("enabled", True)),
            }
        )
    out.extend(normalized_request)
    return out


def _sniff_body_language(body: str) -> str | None:
    """Guess syntax-highlight language from body text (json/xml/html)."""
    text = (body or "").strip()
    if not text:
        return None
    if text[0] in ("{", "["):
        try:
            json.loads(text)
            return "json"
        except (json.JSONDecodeError, ValueError):
            pass
    lower = text[:120].lower()
    if lower.startswith("<?xml") or (
        text[0] == "<"
        and not lower.startswith("<!doctype html")
        and not lower.startswith("<html")
        and re.match(r"<[A-Za-z_][\w:.-]*(\s|>|/)", text)
    ):
        return "xml"
    if lower.startswith("<!doctype html") or lower.startswith("<html"):
        return "html"
    return None


def _postman_header_rows(headers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert merged header rows to Postman ``header`` list shape."""
    rows: list[dict[str, Any]] = []
    for raw in headers:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        if not key:
            continue
        rows.append({"key": key, "value": str(raw.get("value") or "")})
    return rows


def _original_request_snapshot(
    request: DraftRequest,
    *,
    default_headers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a Postman-shaped request snapshot for saved-response examples."""
    headers = _merge_headers(default_headers or [], request.headers)
    snapshot: dict[str, Any] = {
        "method": request.method.upper(),
        "url": {"raw": normalize_url_variables(request.url)},
        "header": _postman_header_rows(headers),
    }
    body_text = (request.body or "").strip()
    if body_text:
        lang = _sniff_body_language(body_text) or "text"
        body_obj: dict[str, Any] = {
            "mode": "raw",
            "raw": request.body,
        }
        if lang != "text":
            body_obj["options"] = {"raw": {"language": lang}}
        snapshot["body"] = body_obj
    return snapshot


def _parsed_saved_responses(
    responses: list[DraftSavedResponse],
    *,
    request: DraftRequest,
    default_headers: list[dict[str, Any]] | None = None,
) -> list[ParsedSavedResponse]:
    """Convert draft saved-response rows into the import IR."""
    snapshot = _original_request_snapshot(request, default_headers=default_headers)
    out: list[ParsedSavedResponse] = []
    for item in responses:
        name = (item.name or "").strip() or "Example"
        body_text = item.body or ""
        parsed: ParsedSavedResponse = {
            "name": name,
            "status": (item.status or "").strip() or None,
            "code": item.code,
            "headers": list(item.headers) if item.headers else None,
            "body": body_text or None,
            "preview_language": _sniff_body_language(body_text),
            "original_request": snapshot,
        }
        out.append(parsed)
    return out


def _parsed_request(
    request: DraftRequest,
    *,
    default_headers: list[dict[str, Any]] | None = None,
) -> ParsedRequest:
    """Convert one draft request into the import intermediate representation."""
    parsed: ParsedRequest = {
        "type": "request",
        "name": request.name,
        "method": request.method.upper(),
        "url": normalize_url_variables(request.url),
    }
    headers = _merge_headers(default_headers or [], request.headers)
    if headers:
        parsed["headers"] = headers
    params = _param_rows(request.params)
    if params:
        parsed["request_parameters"] = params
    if request.body:
        parsed["body"] = request.body
        parsed["body_mode"] = "raw"
        body_lang = _sniff_body_language(request.body)
        if body_lang:
            parsed["body_options"] = {"raw": {"language": body_lang}}
    if request.description:
        parsed["description"] = request.description
    scripts = _scripts_dict(pre=request.pre_script, test=request.test_script)
    if scripts:
        parsed["scripts"] = scripts
    saved = _parsed_saved_responses(
        request.responses,
        request=request,
        default_headers=default_headers,
    )
    if saved:
        parsed["saved_responses"] = saved
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


def _auth_credential_keys(auth: dict[str, Any] | None) -> set[str]:
    """Return placeholder variable names implied by a Postmark auth dict.

    Prefer ``{{var}}`` names embedded in auth field values. Fall back to the
    conventional credential names for the auth type only when no placeholders
    are present.
    """
    if not isinstance(auth, dict):
        return set()
    names: set[str] = set()
    for value in auth.values():
        if isinstance(value, list):
            for row in value:
                if isinstance(row, dict):
                    names |= _variable_names_in_text(str(row.get("value") or ""))
        elif isinstance(value, str):
            names |= _variable_names_in_text(value)
    if names:
        return names
    auth_type = str(auth.get("type") or "").strip().lower()
    return set(_AUTH_CREDENTIAL_VARS.get(auth_type, ()))


def collect_variable_rows(draft: CollectionDraft) -> list[dict[str, Any]]:
    """Merge explicit draft variables with auto-detected ``{{var}}`` names.

    Auto-detected names come from rewritten request URLs, header values,
    signature recipe credentials, and auth credential placeholders.
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

    if draft.signature_recipe is not None:
        for row in recipe_variables(draft.signature_recipe):
            key = str(row["key"])
            if key not in by_key:
                by_key[key] = dict(row)

    detected: set[str] = set()
    for request in draft.requests:
        detected |= _variable_names_in_text(normalize_url_variables(request.url))
        for header in _merge_headers(draft.default_headers, request.headers):
            detected |= _variable_names_in_text(str(header.get("value") or ""))
            detected |= _variable_names_in_text(str(header.get("key") or ""))
    detected |= _auth_credential_keys(draft.auth)
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
    saved_responses = sum(len(request.responses) for request in draft.requests)
    return {
        "has_description": bool((draft.description or "").strip()),
        "variables": len(variables),
        "collection_scripts": bool(
            (draft.pre_script or draft.test_script).strip() or draft.signature_recipe is not None
        ),
        "request_scripts": request_scripts,
        "requests_with_params": sum(1 for request in draft.requests if request.params),
        "signature": draft.signature_recipe.kind if draft.signature_recipe else "",
        "has_auth": bool(draft.auth),
        "default_headers": len(draft.default_headers),
        "saved_responses": saved_responses,
    }


def build_parsed_collection(draft: CollectionDraft) -> ParsedCollection:
    """Build the collection tree, preserving the order requests were added."""
    items: list[ParsedFolder | ParsedRequest] = []
    index: dict[tuple[str, ...], ParsedFolder] = {}

    for path in draft.folders:
        _ensure_folder(items, index, path)
    for request in draft.requests:
        children = _ensure_folder(items, index, request.folder_path)
        children.append(_parsed_request(request, default_headers=draft.default_headers))

    collection: ParsedCollection = {"name": draft.name, "items": items}
    description = draft.description or (f"Imported from {draft.source}" if draft.source else "")
    if description:
        collection["description"] = description
    variables = collect_variable_rows(draft)
    if variables:
        collection["variables"] = variables
    if draft.auth:
        collection["auth"] = dict(draft.auth)

    pre_script = (draft.pre_script or "").strip()
    if draft.signature_recipe is not None:
        signing = build_signing_script(draft.signature_recipe).strip()
        if signing:
            pre_script = f"{signing}\n{pre_script}".strip() if pre_script else signing
    events = _scripts_dict(pre=pre_script, test=draft.test_script)
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
