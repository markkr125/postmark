"""Request scope renderer for the workspace query tool."""

from __future__ import annotations

import json
from typing import Any

from services.assertion_service import AssertionService
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.request_history_service import RequestHistoryService
from services.script_service import ScriptService, normalize_disabled_inherited
from services.scripting.context import mask_sensitive_value

from ...helpers import (
    _cap_rows,
    _format_request_body_preview,
    _format_ts,
    _link,
    _mask_header_value,
    _mask_param_value,
    _redact_auth,
    _scope_variable_lines,
    _scripts_from_data,
    _truncate_text,
    _truncate_url,
    _unresolved_variable_lines,
    _with_leading_markers,
)


def _dirty_request_overlay(request_id: int, snap: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return unsaved editor ``request_data`` when a dirty tab matches *request_id*."""
    if not snap:
        return None
    tabs = snap.get("tabs")
    if not isinstance(tabs, list):
        return None
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        if tab.get("request_id") != request_id:
            continue
        if not tab.get("is_dirty"):
            continue
        data = tab.get("request_data")
        if isinstance(data, dict) and data:
            return data
    return None


def _render_request(
    request_id: int,
    *,
    env_id: int | None = None,
    snap: dict[str, Any] | None = None,
) -> str:
    """Render one saved request with scripts and redacted auth.

    When the turn-start snapshot has a dirty open tab for *request_id*, merge that
    tab's ``request_data`` over DB fields and lead with a ``[partial]`` banner.
    """
    row = CollectionService.get_request(request_id)
    if row is None:
        return "Request not found."
    overlay = _dirty_request_overlay(request_id, snap)
    name = str(row.name or "")
    method = str(overlay.get("method", row.method) if overlay else row.method)
    url = str(overlay.get("url", row.url) if overlay else (row.url or ""))
    body = overlay.get("body", row.body) if overlay else row.body
    headers = overlay.get("headers", row.headers) if overlay else row.headers
    description = overlay.get("description", row.description) if overlay else row.description
    auth = overlay.get("auth", row.auth) if overlay else row.auth
    scripts_raw = overlay.get("scripts", row.scripts) if overlay else row.scripts
    body_mode = overlay.get("body_mode", row.body_mode) if overlay else row.body_mode
    body_options = overlay.get("body_options", row.body_options) if overlay else row.body_options
    params = (
        overlay.get("request_parameters", row.request_parameters)
        if overlay
        else row.request_parameters
    )
    data = {
        "name": name,
        "method": method,
        "url": url,
        "body": body,
        "headers": headers,
        "description": description,
        "auth": auth,
        "scripts": scripts_raw,
        "events": row.events,
    }
    lines = [
        f"{_link('request', request_id, name)}:",
        f"  {method} {_truncate_url(url)}",
    ]
    if getattr(row, "updated_at", None) is not None:
        lines.append(f"  Last edited: {_format_ts(row.updated_at)}")
    latest = RequestHistoryService.latest_for_request(request_id)
    if latest is not None:
        when = _format_ts(latest.get("executed_at") or "")
        status = latest.get("status_code")
        err = latest.get("error")
        outcome = "error" if err else (str(status) if status is not None else "?")
        lines.append(f"  Last sent: {when} → {outcome}")
        original = latest.get("original_request") or {}
        if isinstance(original, dict):
            sent_method = str(original.get("method") or "").upper()
            sent_url = str(original.get("url") or "")
            if sent_method and sent_method != method.upper():
                lines.append(
                    f"  Drift vs last send: method {sent_method} → {method} "
                    f"({_link('history', int(latest['id']), 'last send')})"
                    if isinstance(latest.get("id"), int)
                    else f"  Drift vs last send: method {sent_method} → {method}"
                )
            elif sent_url and sent_url.strip() != url.strip():
                hist_bit = (
                    f" ({_link('history', int(latest['id']), 'last send')})"
                    if isinstance(latest.get("id"), int)
                    else ""
                )
                lines.append(f"  Drift vs last send: URL changed{hist_bit}")
    if description:
        lines.append(f"  Description: {_truncate_text(str(description), max_len=400)}")
    redacted_auth = _redact_auth(auth if isinstance(auth, dict) else None)
    if redacted_auth:
        lines.append(f"  Auth: {json.dumps(redacted_auth, ensure_ascii=False)}")
    elif auth is None:
        resolved = CollectionService.get_request_auth_chain(request_id)
        inherited = _redact_auth(resolved)
        if inherited:
            lines.append(f"  Inherited auth: {json.dumps(inherited, ensure_ascii=False)}")
        else:
            lines.append("  Inherited auth: (none / no-auth)")
    if isinstance(headers, list):
        for h in headers[:20]:
            if isinstance(h, dict):
                k = str(h.get("key", ""))
                v = _mask_header_value(k, str(h.get("value", "")))
                disabled = " (disabled)" if h.get("enabled") is False else ""
                lines.append(f"  Header: {k}: {v}{disabled}")
        if len(headers) > 20:
            lines.append(f"  …and {len(headers) - 20} more headers")
    if isinstance(params, list):
        param_lines: list[str] = []
        for p in params:
            if isinstance(p, dict):
                k = str(p.get("key", ""))
                v = _mask_param_value(k, str(p.get("value", "")))
                disabled = " (disabled)" if p.get("enabled") is False else ""
                param_lines.append(f"  Param: {k}: {v}{disabled}")
        lines.extend(_cap_rows(param_lines, label="params"))
    body_text = str(body or "")
    if body_text:
        mode = str(body_mode or "")
        lang = ""
        raw_opts = body_options
        if isinstance(raw_opts, dict):
            raw_sub = raw_opts.get("raw")
            if isinstance(raw_sub, dict):
                lang = str(raw_sub.get("language", ""))
        annot = ", ".join(x for x in (mode, lang) if x)
        suffix = f" ({annot})" if annot else ""
        body_ctx = {"body_mode": body_mode, "body_options": body_options}
        lines.append(f"\n  Body{suffix}:")
        lines.append(_format_request_body_preview(body_text, body_ctx))
    var_details = EnvironmentService.build_combined_variable_detail_map(env_id, request_id)
    var_map = {
        key: str(detail.get("value", ""))
        for key, detail in var_details.items()
        if isinstance(detail, dict)
    }
    var_lines = _scope_variable_lines(env_id, request_id, details=var_details)
    if var_lines:
        env_name = "none"
        if env_id is not None:
            env_row = EnvironmentService.get_environment(env_id)
            env_name = str(env_row.name or env_id) if env_row is not None else "unknown"
        lines.append(f"  Variables in scope (environment: {env_name}):")
        lines.extend(var_lines)
    unresolved = _unresolved_variable_lines(
        env_id=env_id,
        request_id=request_id,
        url=url,
        headers=headers if isinstance(headers, list) else None,
        body=body_text or None,
        params=params if isinstance(params, list) else None,
        pre_request_script=_scripts_from_data(data).get("pre_request"),
        variables=var_map,
    )
    lines.extend(unresolved)
    scripts = _scripts_from_data(data)
    for kind, src in scripts.items():
        lines.append(f"\n  {kind} script ({_link('request', request_id, name, focus=kind)}):")
        lines.append(_truncate_text(src, max_len=1200))
    pre_chain, test_chain = ScriptService.build_script_chain(request_id)
    if pre_chain or test_chain:
        lines.append("\n  Effective script chain:")
        for entry in pre_chain:
            lines.append(f"    - {entry.get('source_name')} (pre_request)")
        for entry in test_chain:
            lines.append(f"    - {entry.get('source_name')} (test)")
    raw_scripts = scripts_raw if isinstance(scripts_raw, dict) else {}
    for item in normalize_disabled_inherited(raw_scripts.get("disabled_inherited")):
        cid = item.get("collection_id")
        st = item.get("script_type")
        if isinstance(cid, int):
            coll_row = CollectionService.get_collection(cid)
            coll_label = coll_row.name if coll_row is not None else f"collection {cid}"
            source = _link("collection", cid, coll_label)
        else:
            source = "collection"
        lines.append(f"    inherited {st} from {source} — disabled for this request")
    assertions = AssertionService.fetch_for_request(request_id)
    enabled = [a for a in assertions if a.get("enabled", True)]
    disabled_count = len(assertions) - len(enabled)
    if enabled:
        header = f"\n  Declarative assertions ({len(enabled)})"
        if disabled_count > 0:
            header += f" (+{disabled_count} disabled)"
        lines.append(header + ":")
        for a in enabled[:20]:
            subject = str(a.get("subject", ""))
            expected_raw = str(a.get("expected", ""))
            expected = mask_sensitive_value(subject, expected_raw)
            expected = _truncate_text(expected, max_len=200)
            lines.append(f"    - {a.get('subject')} {a.get('operator')} {expected!r}")
    body_out = "\n".join(lines)
    if overlay is not None:
        return _with_leading_markers(
            body_out,
            [
                "[partial] Showing unsaved editor state for this request "
                "(dirty open tab at turn start — DB may differ until save)."
            ],
        )
    return body_out
