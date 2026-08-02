"""Operation dispatch for the incremental collection draft tool."""

from __future__ import annotations

from typing import Any

from services.ai.chat.mutation.audit import append_mutation_audit
from services.ai.chat.mutation.bridge import enqueue_mutation_event
from services.ai.chat.tools.collection_draft.build import (
    build_import_result,
    enrichment_summary,
)
from services.ai.chat.tools.collection_draft.ops.limits import (
    MAX_BODY_CHARS,
    MAX_DEFAULT_HEADERS,
    MAX_DESCRIPTION_CHARS,
    MAX_PARAMS_PER_REQUEST,
    MAX_REQUESTS_PER_BATCH,
    MAX_SCRIPT_CHARS,
    _HTTP_METHODS,
)
from services.ai.chat.tools.collection_draft.ops.normalize import (
    coerce_request_body,
    err,
    folder_path,
    missing_body_warning,
    normalize_auth,
    normalize_kv_rows,
    normalize_saved_responses,
    normalize_variables,
    parse_signature,
    script_flags,
    truncate,
    unwrap_err,
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


def _status_body(draft: CollectionDraft) -> str:
    """Render what the draft currently holds so the agent can resume."""
    lines = [
        "ok: true",
        f"draft: {draft.name}",
        f"requests: {len(draft.requests)}",
        f"description: {'yes' if (draft.description or '').strip() else 'no'}",
        f"scripts: {script_flags(draft.pre_script, draft.test_script)}",
        f"signature: {draft.signature_recipe.kind if draft.signature_recipe else 'none'}",
        f"auth: {'yes' if draft.auth else 'no'}",
        f"default_headers: {len(draft.default_headers)}",
    ]
    if draft.source:
        lines.append(f"source: {draft.source}")
    if draft.folders:
        lines.append(f"folders: {['/'.join(path) for path in draft.folders]}")
    for request in draft.requests:
        location = "/".join(request.folder_path) or "(root)"
        params_n = len(request.params)
        req_scripts = script_flags(request.pre_script, request.test_script)
        resp_n = len(request.responses)
        lines.append(
            f"- [{location}] {request.method} {request.name} "
            f"(params: {params_n}, scripts: {req_scripts}, responses: {resp_n})"
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
        return err("name_required", "Provide the collection name to create.")
    variables, var_warnings, var_err = normalize_variables(fields.get("variables"))
    if var_err is not None:
        return var_err
    warnings: list[str] = list(var_warnings)
    description, desc_truncated = truncate(
        str(fields.get("description") or "").strip(), MAX_DESCRIPTION_CHARS
    )
    if desc_truncated:
        warnings.append("collection description truncated")
    pre_script, pre_truncated = truncate(
        str(fields.get("pre_script") or "").strip(), MAX_SCRIPT_CHARS
    )
    if pre_truncated:
        warnings.append("collection pre_script truncated")
    test_script, test_truncated = truncate(
        str(fields.get("test_script") or "").strip(), MAX_SCRIPT_CHARS
    )
    if test_truncated:
        warnings.append("collection test_script truncated")

    recipe, sig_err = parse_signature(fields.get("signature"))
    if sig_err is not None:
        return sig_err

    auth, auth_err = normalize_auth(fields.get("auth"))
    if auth_err is not None:
        return auth_err
    default_headers, header_warnings = normalize_kv_rows(fields.get("default_headers"))
    warnings.extend(header_warnings)
    if len(default_headers) > MAX_DEFAULT_HEADERS:
        warnings.append(
            f"default_headers trimmed to {MAX_DEFAULT_HEADERS} "
            f"(dropped {len(default_headers) - MAX_DEFAULT_HEADERS})"
        )
        default_headers = default_headers[:MAX_DEFAULT_HEADERS]

    draft = CollectionDraft(
        name=name,
        source=str(fields.get("source") or "").strip(),
        description=description,
        variables=variables,
        pre_script=pre_script,
        test_script=test_script,
        signature_recipe=recipe,
        auth=auth,
        default_headers=default_headers,
    )
    start_draft(session_id, draft)
    lines = [
        "ok: true",
        f"draft: {name}",
        "requests: 0",
        f"description: {'yes' if description else 'no'}",
        f"scripts: {script_flags(pre_script, test_script)}",
        f"signature: {recipe.kind if recipe else 'none'}",
        f"auth: {'yes' if auth else 'no'}",
        f"default_headers: {len(default_headers)}",
        "note: This draft supersedes any earlier import in this chat. Build it only "
        "from the document you are reading now.",
        "next_step: call operation=add_requests with a requests array, then "
        "operation=finish. For POST/PUT/PATCH, include the documented request "
        "input (body and/or params) — a parameter table in description is not "
        "enough; re-add endpoints you warned about.",
    ]
    if warnings:
        lines.append(f"warnings: {warnings}")
    return "\n".join(lines) + "\n"


def _request_from_fields(fields: dict[str, Any]) -> tuple[DraftRequest | str, list[str]]:
    """Validate *fields* and return a draft request (or skip reason) plus warnings.

    Soft-caps (body, params, folder depth, responses) truncate with warnings.
    Missing name/url or an unknown method skip the request; a POST/PUT/PATCH
    with no body and no query input stays but carries a loud warning.
    """
    warnings: list[str] = []
    name = str(fields.get("name") or "").strip()
    url = str(fields.get("url") or "").strip()
    method = str(fields.get("method") or "GET").strip().upper()
    if not name:
        return err("name_required", "Provide a short request name."), warnings
    if not url:
        return (
            err("url_required", "Provide the request URL, variables like {{baseUrl}} allowed."),
            warnings,
        )
    if method not in _HTTP_METHODS:
        return err("bad_method", f"Use one of: {', '.join(sorted(_HTTP_METHODS))}."), warnings
    path = folder_path(str(fields.get("folder") or ""))
    if len(path) > MAX_FOLDER_DEPTH:
        warnings.append(f"folder trimmed to {MAX_FOLDER_DEPTH} levels for {name!r}")
        path = path[:MAX_FOLDER_DEPTH]
    headers = [dict(h) for h in (fields.get("headers") or []) if isinstance(h, dict)]
    params, param_warnings = normalize_kv_rows(fields.get("params"))
    warnings.extend(param_warnings)
    if len(params) > MAX_PARAMS_PER_REQUEST:
        warnings.append(
            f"params trimmed to {MAX_PARAMS_PER_REQUEST} for {name!r} "
            f"(dropped {len(params) - MAX_PARAMS_PER_REQUEST})"
        )
        params = params[:MAX_PARAMS_PER_REQUEST]
    description_raw = str(fields.get("description") or "").strip()
    body_text, body_warnings = coerce_request_body(
        fields.get("body"),
        description=description_raw,
    )
    warnings.extend(body_warnings)
    body_text, body_truncated = truncate(body_text, MAX_BODY_CHARS)
    if body_truncated:
        warnings.append(
            f"body truncated for {name!r} — keep the request payload under "
            f"{MAX_BODY_CHARS} characters (do not paste response examples as body)"
        )
    has_input = bool(body_text.strip()) or bool(params) or ("?" in url)
    if not has_input:
        warning = missing_body_warning(name, method)
        if warning:
            warnings.append(warning)
    description, desc_truncated = truncate(description_raw, MAX_DESCRIPTION_CHARS)
    if desc_truncated:
        warnings.append(f"description truncated for {name!r}")
    pre_script, pre_truncated = truncate(
        str(fields.get("pre_script") or "").strip(), MAX_SCRIPT_CHARS
    )
    if pre_truncated:
        warnings.append(f"pre_script truncated for {name!r}")
    test_script, test_truncated = truncate(
        str(fields.get("test_script") or "").strip(), MAX_SCRIPT_CHARS
    )
    if test_truncated:
        warnings.append(f"test_script truncated for {name!r}")
    responses, response_warnings = normalize_saved_responses(
        fields.get("responses"),
        request_name=name,
    )
    warnings.extend(response_warnings)
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
            responses=responses,
        ),
        warnings,
    )


def op_add_requests(session_id: str, fields: dict[str, Any]) -> str:
    """Append one chunk's requests; soft-skip bad items so the batch stays green."""
    draft = get_draft(session_id)
    if draft is None:
        return err("no_draft", "Call operation=start before adding to a draft.")
    raw = fields.get("requests")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        return err(
            "requests_required",
            "Provide a requests array (use [] when this chunk has no endpoints).",
        )
    # Empty batches are normal for TOC / prose chunks — soft no-op, not a red card.
    if not raw:
        return (
            "ok: true\n"
            "added: []\n"
            f"requests: {len(draft.requests)}\n"
            "note: No endpoints in this chunk — draft unchanged. "
            "Read the next chunk, or finish if the document is done.\n"
        )

    warnings: list[str] = []
    items = list(raw)
    if len(items) > MAX_REQUESTS_PER_BATCH:
        warnings.append(
            f"batch trimmed to {MAX_REQUESTS_PER_BATCH} "
            f"(dropped {len(items) - MAX_REQUESTS_PER_BATCH})"
        )
        items = items[:MAX_REQUESTS_PER_BATCH]

    room = MAX_REQUESTS_PER_DRAFT - len(draft.requests)
    if room <= 0:
        return err("draft_full", f"A draft holds at most {MAX_REQUESTS_PER_DRAFT} requests.")
    if len(items) > room:
        warnings.append(
            f"draft nearly full — accepted {room} of {len(items)} requests "
            f"(cap {MAX_REQUESTS_PER_DRAFT})"
        )
        items = items[:room]

    requests: list[DraftRequest] = []
    skipped: list[str] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            skipped.append(f"Request {index}: not an object")
            continue
        request, item_warnings = _request_from_fields(item)
        warnings.extend(item_warnings)
        if isinstance(request, str):
            code, hint = unwrap_err(request)
            label = str(item.get("name") or f"Request {index}").strip()
            skipped.append(f"{label} ({code}): {hint}")
            continue
        requests.append(request)

    if not requests:
        return err(
            "all_skipped",
            "No valid requests in this batch. "
            + ("; ".join(skipped) if skipped else "Each entry needs name, method, and url."),
        )

    draft.requests.extend(requests)
    added = [f"{request.method} {request.name}" for request in requests]
    lines = [
        "ok: true",
        f"added: {added}",
        f"requests: {len(draft.requests)}",
    ]
    if skipped:
        lines.append(f"skipped: {skipped}")
    if warnings:
        lines.append(f"warnings: {warnings}")
    return "\n".join(lines) + "\n"


def op_status(session_id: str, _fields: dict[str, Any]) -> str:
    """Report the draft contents so a drifting agent can resume."""
    draft = get_draft(session_id)
    if draft is None:
        return err("no_draft", "No draft in progress. Call operation=start first.")
    return _status_body(draft)


def op_discard(session_id: str, _fields: dict[str, Any]) -> str:
    """Throw the draft away without creating anything."""
    draft = get_draft(session_id)
    if draft is None:
        return err("no_draft", "No draft in progress.")
    clear_draft(session_id)
    return f"ok: true\ndiscarded: {draft.name}\n"


def op_finish(session_id: str, fields: dict[str, Any], *, mutation_id: str) -> str:
    """Persist the draft as a real collection and return its true identity."""
    draft = get_draft(session_id)
    if draft is None:
        return err("no_draft", "Call operation=start and add requests before finishing.")
    if not draft.requests:
        return err("draft_empty", "Add at least one request with operation=add_requests.")
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
        return err("import_failed", "Nothing was created; the draft was kept for a retry.")

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
    if summary_bits.get("signature"):
        enrichment_parts.append(f"signature script ({summary_bits['signature']})")
    if summary_bits.get("has_auth"):
        enrichment_parts.append("auth")
    if summary_bits.get("default_headers"):
        enrichment_parts.append(f"{summary_bits['default_headers']} default header(s)")
    if summary_bits.get("saved_responses"):
        enrichment_parts.append(f"{summary_bits['saved_responses']} saved response(s)")
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
    "op_add_requests",
    "op_discard",
    "op_finish",
    "op_start",
    "op_status",
]
