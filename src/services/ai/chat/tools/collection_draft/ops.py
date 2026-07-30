"""Operation dispatch for the incremental collection draft tool."""

from __future__ import annotations

import json
from typing import Any

from services.ai.chat.mutation.audit import append_mutation_audit
from services.ai.chat.mutation.bridge import enqueue_mutation_event
from services.ai.chat.tools.collection_draft.build import (
    build_import_result,
    enrichment_summary,
)
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
MAX_PARAMS_PER_REQUEST = 40
MAX_PARAM_DESCRIPTION_CHARS = 500
MAX_DESCRIPTION_CHARS = 8000
MAX_SCRIPT_CHARS = 8000


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


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    """Return ``(text, truncated)`` capped at *limit* characters."""
    value = text or ""
    if len(value) <= limit:
        return value, False
    return value[:limit], True


def _normalize_kv_rows(
    raw: list[dict[str, Any]] | dict[str, Any] | None,
    *,
    max_description: int = MAX_PARAM_DESCRIPTION_CHARS,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fold objects into key/value(/description) rows and truncate descriptions."""
    warnings: list[str] = []
    if raw is None:
        return [], warnings
    if isinstance(raw, dict):
        items: list[dict[str, Any]] = [{"key": str(k), "value": str(v)} for k, v in raw.items()]
    elif isinstance(raw, list):
        items = [dict(row) for row in raw if isinstance(row, dict)]
    else:
        return [], warnings
    rows: list[dict[str, Any]] = []
    for item in items:
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        row: dict[str, Any] = {
            "key": key,
            "value": str(item.get("value") or ""),
            "enabled": bool(item.get("enabled", True)),
        }
        description = str(item.get("description") or "").strip()
        if description:
            description, truncated = _truncate(description, max_description)
            if truncated:
                warnings.append(f"param description truncated for {key!r}")
            row["description"] = description
        rows.append(row)
    return rows, warnings


def _script_flags(pre: str, test: str) -> str:
    """Return a short ``pre,test`` / ``pre`` / ``test`` / ``none`` label."""
    parts: list[str] = []
    if (pre or "").strip():
        parts.append("pre")
    if (test or "").strip():
        parts.append("test")
    return ",".join(parts) if parts else "none"


def _status_body(draft: CollectionDraft) -> str:
    """Render what the draft currently holds so the agent can resume."""
    lines = [
        "ok: true",
        f"draft: {draft.name}",
        f"requests: {len(draft.requests)}",
        f"description: {'yes' if (draft.description or '').strip() else 'no'}",
        f"scripts: {_script_flags(draft.pre_script, draft.test_script)}",
    ]
    if draft.source:
        lines.append(f"source: {draft.source}")
    if draft.folders:
        lines.append(f"folders: {['/'.join(path) for path in draft.folders]}")
    for request in draft.requests:
        location = "/".join(request.folder_path) or "(root)"
        params_n = len(request.params)
        req_scripts = _script_flags(request.pre_script, request.test_script)
        lines.append(
            f"- [{location}] {request.method} {request.name} "
            f"(params: {params_n}, scripts: {req_scripts})"
        )
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
    warnings: list[str] = []
    description, desc_truncated = _truncate(
        str(fields.get("description") or "").strip(), MAX_DESCRIPTION_CHARS
    )
    if desc_truncated:
        warnings.append("collection description truncated")
    pre_script, pre_truncated = _truncate(
        str(fields.get("pre_script") or "").strip(), MAX_SCRIPT_CHARS
    )
    if pre_truncated:
        warnings.append("collection pre_script truncated")
    test_script, test_truncated = _truncate(
        str(fields.get("test_script") or "").strip(), MAX_SCRIPT_CHARS
    )
    if test_truncated:
        warnings.append("collection test_script truncated")
    draft = CollectionDraft(
        name=name,
        source=str(fields.get("source") or "").strip(),
        description=description,
        variables=[dict(var) for var in variables if isinstance(var, dict)],
        pre_script=pre_script,
        test_script=test_script,
    )
    start_draft(session_id, draft)
    lines = [
        "ok: true",
        f"draft: {name}",
        "requests: 0",
        f"description: {'yes' if description else 'no'}",
        f"scripts: {_script_flags(pre_script, test_script)}",
        "note: This draft supersedes any earlier import in this chat. Build it only "
        "from the document you are reading now.",
        "next_step: call operation=add_requests with a requests array, then "
        "operation=finish. JSON bodies must be objects or arrays, not encoded strings.",
    ]
    if warnings:
        lines.append(f"warnings: {warnings}")
    return "\n".join(lines) + "\n"


def _request_from_fields(fields: dict[str, Any]) -> tuple[DraftRequest | str, list[str]]:
    """Validate *fields* and return a draft request (or error body) plus warnings."""
    warnings: list[str] = []
    name = str(fields.get("name") or "").strip()
    url = str(fields.get("url") or "").strip()
    method = str(fields.get("method") or "GET").strip().upper()
    if not name:
        return _err("name_required", "Provide a short request name."), warnings
    if not url:
        return (
            _err("url_required", "Provide the request URL, variables like {{baseUrl}} allowed."),
            warnings,
        )
    if method not in _HTTP_METHODS:
        return _err("bad_method", f"Use one of: {', '.join(sorted(_HTTP_METHODS))}."), warnings
    path = _folder_path(str(fields.get("folder") or ""))
    if len(path) > MAX_FOLDER_DEPTH:
        return _err("folder_too_deep", f"Use at most {MAX_FOLDER_DEPTH} nested levels."), warnings
    headers = [dict(h) for h in (fields.get("headers") or []) if isinstance(h, dict)]
    params, param_warnings = _normalize_kv_rows(fields.get("params"))
    warnings.extend(param_warnings)
    if len(params) > MAX_PARAMS_PER_REQUEST:
        return (
            _err(
                "too_many_params",
                f"Use at most {MAX_PARAMS_PER_REQUEST} query parameters per request.",
            ),
            warnings,
        )
    body = fields.get("body")
    if isinstance(body, dict | list):
        body_text = json.dumps(body, indent=2, ensure_ascii=False)
    else:
        body_text = str(body or "")
    if len(body_text) > MAX_BODY_CHARS:
        return (
            _err(
                "body_too_large",
                f"'{name}': body is the request payload only — do not paste a response or "
                f"sample-response body, and do not add a response example as its own request. "
                f"Keep the body under {MAX_BODY_CHARS} characters.",
            ),
            warnings,
        )
    description, desc_truncated = _truncate(
        str(fields.get("description") or "").strip(), MAX_DESCRIPTION_CHARS
    )
    if desc_truncated:
        warnings.append(f"description truncated for {name!r}")
    pre_script, pre_truncated = _truncate(
        str(fields.get("pre_script") or "").strip(), MAX_SCRIPT_CHARS
    )
    if pre_truncated:
        warnings.append(f"pre_script truncated for {name!r}")
    test_script, test_truncated = _truncate(
        str(fields.get("test_script") or "").strip(), MAX_SCRIPT_CHARS
    )
    if test_truncated:
        warnings.append(f"test_script truncated for {name!r}")
    return (
        DraftRequest(
            name=name,
            method=method,
            url=url,
            folder_path=path,
            headers=headers,
            params=params,
            body=body_text,
            description=description,
            pre_script=pre_script,
            test_script=test_script,
        ),
        warnings,
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
    warnings: list[str] = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            return _err("bad_request", f"Request {index} must be an object.")
        request, item_warnings = _request_from_fields(item)
        if isinstance(request, str):
            code, hint = _unwrap_err(request)
            return _err("bad_request", f"Request {index} ({code}): {hint}")
        requests.append(request)
        warnings.extend(item_warnings)
    draft.requests.extend(requests)
    added = [f"{request.method} {request.name}" for request in requests]
    lines = [
        "ok: true",
        f"added: {added}",
        f"requests: {len(draft.requests)}",
    ]
    if warnings:
        lines.append(f"warnings: {warnings}")
    return "\n".join(lines) + "\n"


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

    summary_bits = enrichment_summary(draft)

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
    enrichment_parts: list[str] = []
    if summary_bits["has_description"]:
        enrichment_parts.append("description")
    if summary_bits["variables"]:
        enrichment_parts.append(f"{summary_bits['variables']} variable(s)")
    if summary_bits["collection_scripts"]:
        enrichment_parts.append("collection scripts")
    if summary_bits["request_scripts"]:
        enrichment_parts.append(f"{summary_bits['request_scripts']} request script(s)")
    if summary_bits["requests_with_params"]:
        enrichment_parts.append(f"{summary_bits['requests_with_params']} request(s) with params")
    enrichment = ", ".join(enrichment_parts) if enrichment_parts else "no extra enrichment"
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
        f"enrichment: {enrichment}\n"
        "next_step: The collection exists. Reply using the collection_links label above; "
        "never invent a collection id or link. Summarize what was enriched "
        f"({enrichment}). If you created local scripts for shared helpers, report each "
        'script name, postmark://script/<id> link, and pm.require("local:…") path.\n'
    )


__all__ = [
    "MAX_BODY_CHARS",
    "MAX_DESCRIPTION_CHARS",
    "MAX_PARAMS_PER_REQUEST",
    "MAX_PARAM_DESCRIPTION_CHARS",
    "MAX_SCRIPT_CHARS",
    "op_add_requests",
    "op_discard",
    "op_finish",
    "op_start",
    "op_status",
]
