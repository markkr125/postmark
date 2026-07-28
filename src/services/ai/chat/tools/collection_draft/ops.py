"""Operation dispatch for the incremental collection draft tool."""

from __future__ import annotations

import json
from typing import Any

from services.ai.chat.mutation.audit import append_mutation_audit
from services.ai.chat.mutation.bridge import enqueue_mutation_event
from services.ai.chat.tools.collection_draft.build import build_import_result
from services.ai.chat.tools.collection_draft.state import (
    MAX_FOLDER_DEPTH,
    MAX_REQUESTS_PER_DRAFT,
    CollectionDraft,
    DraftRequest,
    clear_draft,
    get_draft,
    start_draft,
)

_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"})
MAX_REQUESTS_PER_BATCH = 20

# A request body is the request payload (the doc's request example), which is small.
# Pasting a full nested *response* example as a body is the pattern that produced
# huge, deeply-nested tool-call JSON the model then malformed. Cap the body so that
# mistake comes back as a recoverable error instead of a giant argument to fumble.
MAX_BODY_CHARS = 4000


def _err(code: str, hint: str) -> str:
    """Return a machine- and human-readable failure body."""
    return f"ok: false\nerror: {code}\nhint: {hint}\n"


def _unwrap_err(block: str) -> tuple[str, str]:
    """Return the ``(error, hint)`` from an ``_err`` block, so it can be re-wrapped flat."""
    fields = {
        key.strip(): value.strip()
        for key, _, value in (line.partition(": ") for line in block.strip().splitlines())
        if key.strip() in ("error", "hint")
    }
    return fields.get("error", "invalid"), fields.get("hint", block.strip())


def _folder_path(raw: str) -> tuple[str, ...]:
    """Split a ``A/B`` folder path into cleaned segments."""
    return tuple(segment.strip() for segment in raw.split("/") if segment.strip())


def _status_body(draft: CollectionDraft) -> str:
    """Render what the draft currently holds so the agent can resume."""
    lines = [
        "ok: true",
        f"draft: {draft.name}",
        f"requests: {len(draft.requests)}",
    ]
    if draft.source:
        lines.append(f"source: {draft.source}")
    if draft.folders:
        lines.append(f"folders: {['/'.join(path) for path in draft.folders]}")
    for request in draft.requests:
        location = "/".join(request.folder_path) or "(root)"
        lines.append(f"- [{location}] {request.method} {request.name}")
    lines.append(
        "next_step: add remaining requests with operation=add_requests, "
        "then operation=finish to create the collection."
    )
    return "\n".join(lines) + "\n"


def op_start(session_id: str, fields: dict[str, Any]) -> str:
    """Begin a new draft, replacing any earlier one in this session."""
    name = str(fields.get("name") or "").strip()
    if not name:
        return _err("name_required", "Provide the collection name to create.")
    variables = fields.get("variables") or []
    draft = CollectionDraft(
        name=name,
        source=str(fields.get("source") or "").strip(),
        description=str(fields.get("description") or "").strip(),
        variables=[dict(var) for var in variables if isinstance(var, dict)],
    )
    start_draft(session_id, draft)
    return (
        f"ok: true\ndraft: {name}\nrequests: 0\n"
        "note: This draft supersedes any earlier import in this chat. Build it only "
        "from the document you are reading now.\n"
        "next_step: call operation=add_requests with a requests array, then "
        "operation=finish. JSON bodies must be objects or arrays, not encoded strings.\n"
    )


def _request_from_fields(fields: dict[str, Any]) -> DraftRequest | str:
    """Validate *fields* and return a draft request or an error body."""
    name = str(fields.get("name") or "").strip()
    url = str(fields.get("url") or "").strip()
    method = str(fields.get("method") or "GET").strip().upper()
    if not name:
        return _err("name_required", "Provide a short request name.")
    if not url:
        return _err("url_required", "Provide the request URL, variables like {{baseUrl}} allowed.")
    if method not in _HTTP_METHODS:
        return _err("bad_method", f"Use one of: {', '.join(sorted(_HTTP_METHODS))}.")
    path = _folder_path(str(fields.get("folder") or ""))
    if len(path) > MAX_FOLDER_DEPTH:
        return _err("folder_too_deep", f"Use at most {MAX_FOLDER_DEPTH} nested levels.")
    headers = [dict(h) for h in (fields.get("headers") or []) if isinstance(h, dict)]
    body = fields.get("body")
    if isinstance(body, dict | list):
        body_text = json.dumps(body, indent=2, ensure_ascii=False)
    else:
        body_text = str(body or "")
    if len(body_text) > MAX_BODY_CHARS:
        return _err(
            "body_too_large",
            f"'{name}': body is the request payload only — do not paste a response or "
            f"sample-response body, and do not add a response example as its own request. "
            f"Keep the body under {MAX_BODY_CHARS} characters.",
        )
    return DraftRequest(
        name=name,
        method=method,
        url=url,
        folder_path=path,
        headers=headers,
        body=body_text,
        description=str(fields.get("description") or "").strip(),
    )


def op_add_requests(session_id: str, fields: dict[str, Any]) -> str:
    """Append one chunk's requests atomically in a single model round-trip."""
    draft = get_draft(session_id)
    if draft is None:
        return _err("no_draft", "Call operation=start before adding to a draft.")
    raw = fields.get("requests")
    if not isinstance(raw, list) or not raw:
        return _err("requests_required", "Provide the endpoints found in this chunk.")
    if len(raw) > MAX_REQUESTS_PER_BATCH:
        return _err(
            "batch_too_large",
            f"Add at most {MAX_REQUESTS_PER_BATCH} requests from one document chunk.",
        )
    if len(draft.requests) + len(raw) > MAX_REQUESTS_PER_DRAFT:
        return _err("draft_full", f"A draft holds at most {MAX_REQUESTS_PER_DRAFT} requests.")

    requests: list[DraftRequest] = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            return _err("bad_request", f"Request {index} must be an object.")
        request = _request_from_fields(item)
        if isinstance(request, str):
            code, hint = _unwrap_err(request)
            return _err("bad_request", f"Request {index} ({code}): {hint}")
        requests.append(request)
    draft.requests.extend(requests)
    added = [f"{request.method} {request.name}" for request in requests]
    return f"ok: true\nadded: {added}\nrequests: {len(draft.requests)}\n"


def op_status(session_id: str, _fields: dict[str, Any]) -> str:
    """Report the draft contents so a drifting agent can resume."""
    draft = get_draft(session_id)
    if draft is None:
        return _err("no_draft", "No draft in progress. Call operation=start first.")
    return _status_body(draft)


def op_discard(session_id: str, _fields: dict[str, Any]) -> str:
    """Throw the draft away without creating anything."""
    draft = get_draft(session_id)
    if draft is None:
        return _err("no_draft", "No draft in progress.")
    clear_draft(session_id)
    return f"ok: true\ndiscarded: {draft.name}\n"


def op_finish(session_id: str, fields: dict[str, Any], *, mutation_id: str) -> str:
    """Persist the draft as a real collection and return its true identity."""
    draft = get_draft(session_id)
    if draft is None:
        return _err("no_draft", "Call operation=start and add requests before finishing.")
    if not draft.requests:
        return _err("draft_empty", "Add at least one request with operation=add_requests.")
    override = str(fields.get("name") or "").strip()
    if override:
        draft.name = override

    from services.import_service import ImportService

    try:
        summary = ImportService.import_parsed(build_import_result(draft))
    except Exception as exc:
        return f"ok: false\nerror: {type(exc).__name__}\nmessage: {exc}\n"

    created = [
        {"id": int(ref["id"]), "name": str(ref["name"])}
        for ref in (summary.get("imported_collections") or [])
        if isinstance(ref, dict) and ref.get("id")
    ]
    if not created:
        return _err("import_failed", "Nothing was created; the draft was kept for a retry.")

    clear_draft(session_id)
    req_count = int(summary.get("requests_imported") or 0)
    text = f"Created collection {created[0]['name']!r} with {req_count} request(s)"
    enqueue_mutation_event(
        {
            "type": "mutated",
            "entity": "import",
            "action": "create",
            "ids": {},
            "warnings": [str(e) for e in (summary.get("errors") or [])[:10]],
            "payload": {
                "collections_imported": len(created),
                "requests_imported": req_count,
                "environments_imported": 0,
            },
        }
    )
    append_mutation_audit(
        {
            "mutation_id": mutation_id,
            "action": "create",
            "entity": "import",
            "ids": {"collection": created[0]["id"]},
            "summary": text,
        }
    )
    links = [f"[{ref['name']}](postmark://collection/{ref['id']})" for ref in created]
    return (
        "ok: true\n"
        f"mutation_id: {mutation_id}\n"
        f"summary: {text}\n"
        "action: create\n"
        "entity: import\n"
        f"collections_imported: {len(created)}\n"
        f"requests_imported: {req_count}\n"
        f"imported_collections: {created}\n"
        f"collection_links: {links}\n"
        "next_step: The collection exists. Reply using the collection_links label above; "
        "never invent a collection id or link.\n"
    )


__all__ = [
    "op_add_requests",
    "op_discard",
    "op_finish",
    "op_start",
    "op_status",
]
