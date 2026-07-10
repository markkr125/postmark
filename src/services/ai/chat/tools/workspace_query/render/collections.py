"""Collection and history scope renderers for the workspace query tool."""

from __future__ import annotations

import json
import statistics
from typing import Any, cast

from services.assertion_service import AssertionService
from services.collection_service import CollectionService, _normalize_header_list
from services.environment_service import EnvironmentService
from services.request_history_service import (
    RequestHistoryService,
    _normalize_history_response_headers,
)
from services.run_history_service import RunHistoryService
from services.script_service import ScriptService, normalize_disabled_inherited
from services.scripting.context import mask_sensitive_value

from ..constants import _HEADER_VALUE_MAX, _URL_PREVIEW_MAX
from ..helpers import (
    _cap_rows,
    _follow_up_ids_block,
    _format_env_pairs,
    _format_request_body_preview,
    _format_ts,
    _link,
    _mask_console_log_message,
    _mask_header_value,
    _mask_param_value,
    _parse_history_search,
    _redact_auth,
    _redact_env_values,
    _redact_response_body,
    _redact_url,
    _request_label_link,
    _scope_variable_lines,
    _scripts_from_data,
    _truncate_text,
    _truncate_url,
    _unresolved_variable_lines,
    _walk_tree,
    _with_leading_markers,
)


def _latency_percentile(values: list[float], pct: float) -> int:
    """Return an integer latency percentile from *values* (linear interpolation)."""
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return int(ordered[0])
    rank = (pct / 100.0) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return int(ordered[lo] + (ordered[hi] - ordered[lo]) * frac)


def _render_collection_tree(search: str) -> str:
    """Render folder→request tree with optional filter."""
    tree = CollectionService.fetch_all()
    lines = _walk_tree(tree, search=search.strip())
    if not lines:
        return "No collections or requests match." if search.strip() else "No collections."
    title = "Collection tree"
    if search.strip():
        title += f' (filter: "{search.strip()}")'
    body = _cap_rows(lines, label="rows")
    return title + ":\n" + "\n".join(body)


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


def _render_request_history(request_id: int, *, search: str = "") -> str:
    """List recent sends for a request."""
    row = CollectionService.get_request(request_id)
    label = row.name if row else f"request {request_id}"
    text_filter, since, until = _parse_history_search(search)
    entries = RequestHistoryService.list_for_request(
        request_id,
        search=text_filter,
        executed_from=since,
        executed_to=until,
    )
    if not entries:
        hint = ""
        if row is None:
            hint = " (request not found — get a valid link from collection_tree)"
        if text_filter or since is not None or until is not None:
            filter_bits = []
            if text_filter:
                filter_bits.append(f'search="{text_filter}"')
            if since is not None:
                filter_bits.append(f"since:{since.isoformat()}")
            if until is not None:
                filter_bits.append(f"until:{until.isoformat()}")
            return _with_leading_markers(
                f"No send history matches for {_link('request', request_id, label)} "
                f"({', '.join(filter_bits)}). History search matches stored URL, name, "
                f"method, and status only — not response bodies or params-table-only "
                f"values.{hint}",
                [
                    "[partial] Filtered history search found no rows — this is not proof "
                    "the send never happened if the needle was only in a body or "
                    "params-table field."
                ],
            )
        return f"No send history for {_link('request', request_id, label)}.{hint}"
    lines = [f"Send history for {_link('request', request_id, label)} (newest first):"]
    ok = 0
    errors = 0
    latencies: list[float] = []
    status_counts: dict[str, int] = {}
    for entry in entries:
        code = entry.get("status_code")
        err = entry.get("error")
        is_error = err is not None or not (isinstance(code, int) and 200 <= code < 400)
        if is_error:
            errors += 1
        else:
            ok += 1
        elapsed = entry.get("elapsed_ms")
        if not is_error and isinstance(elapsed, int | float) and float(elapsed) > 0:
            latencies.append(float(elapsed))
        status_key = str(code if code is not None else "?")
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
    error_rate = int(round(errors * 100 / len(entries))) if entries else 0
    avg_lat = int(sum(latencies) / len(latencies)) if latencies else 0
    median_lat = int(statistics.median(latencies)) if latencies else 0
    p95_lat = _latency_percentile(latencies, 95)
    status_bits = ", ".join(f"{code}x{count}" for code, count in sorted(status_counts.items()))
    count_label = "latest 200 sends" if len(entries) == 200 else f"{len(entries)} sends"
    lines.append(
        f"  Summary: {count_label} · {ok} succeeded · {errors} failed "
        f"({error_rate}% error rate) · latency (ok sends): avg {avg_lat} ms · "
        f"median {median_lat} ms · p95 {p95_lat} ms · statuses: {status_bits}"
    )
    follow_ups: list[tuple[str, int]] = []
    shown = entries[:25]
    for entry in shown:
        eid = entry.get("id")
        when = _format_ts(entry.get("executed_at") or entry.get("created_at") or "")
        status = entry.get("status_code") or "?"
        latency = entry.get("elapsed_ms")
        lat = f" · {latency} ms" if latency is not None else ""
        err = entry.get("error")
        err_s = f" · error: {_truncate_text(str(err), max_len=200)}" if err else ""
        title = f"{when} · {status}{lat}{err_s}"
        if isinstance(eid, int):
            lines.append(f"- {_link('history', eid, title)}")
            follow_ups.append((f"history_entry · {when} · {status}", eid))
        else:
            lines.append(f"- {title}")
    if len(entries) > 25:
        extra = len(entries) - 25
        overflow = (
            "…older sends beyond the newest 200 — pass search=… to filter."
            if len(entries) == 200
            else f"…and {extra} older sends — pass search=… to filter."
        )
        lines.append(overflow)
    lines.extend(_follow_up_ids_block(follow_ups))
    return "\n".join(lines)


def _render_history_entry(entry_id: int) -> str:
    """Render one past send's stored response."""
    entry = RequestHistoryService.get_entry(entry_id)
    if entry is None:
        return "History entry not found."
    detail = RequestHistoryService.entry_to_detail_snapshot(entry)
    method = str(detail.get("method") or "GET")
    url = _truncate_url(str(detail.get("url") or ""))
    title = f"{method} {url}"
    lines = [f"History entry · {_link('history', entry_id, title)}:"]
    err = detail.get("error")
    if err:
        lines.append(f"  Error: {_truncate_text(str(err), max_len=200)}")
    else:
        code = detail.get("status_code")
        elapsed = detail.get("elapsed_ms")
        stat = f"  {code}".strip()
        if elapsed is not None:
            stat += f" · {int(elapsed)} ms"
        lines.append(stat)
    headers = _normalize_history_response_headers(detail.get("headers"))
    for h in headers[:20]:
        k = str(h.get("key", ""))
        v = _mask_header_value(k, str(h.get("value", "")))
        lines.append(f"  Header: {k}: {v}")
    body = detail.get("body")
    if body:
        raw = str(body)
        preview = _truncate_text(_redact_response_body(raw, "text", headers=headers))
        truncated_note = " (truncated in storage)" if detail.get("body_truncated") else ""
        lines.append(f"  Body ({len(raw)} chars){truncated_note}: {preview}")
    original = detail.get("original_request")
    if isinstance(original, dict):
        lines.append("\n  Sent request:")
        sent_method = str(original.get("method") or method)
        sent_url = _redact_url(str(original.get("url") or ""))
        if len(sent_url) > _URL_PREVIEW_MAX:
            sent_url = f"{sent_url[:_URL_PREVIEW_MAX]}…"
        lines.append(f"    {sent_method} {sent_url}")
        sent_headers = original.get("sent_headers")
        if isinstance(sent_headers, list):
            for h in sent_headers[:20]:
                if isinstance(h, dict):
                    k = str(h.get("key", ""))
                    v = _mask_header_value(k, str(h.get("value", "")))
                    lines.append(f"    Header: {k}: {v}")
        sent_body = original.get("body")
        if sent_body:
            body_ctx = {
                "body_mode": original.get("body_mode"),
                "body_options": original.get("body_options"),
                "headers": sent_headers if isinstance(sent_headers, list) else None,
                "auth": original.get("auth"),
            }
            lines.append(f"    Body: {_format_request_body_preview(str(sent_body), body_ctx)}")
    lines.extend(_follow_up_ids_block([(f"history_entry · {method} {url}", entry_id)]))
    return "\n".join(lines)


def _render_saved_responses(request_id: int) -> str:
    """List saved example responses and declarative assertions."""
    row = CollectionService.get_request(request_id)
    label = row.name if row else f"request {request_id}"
    examples = CollectionService.get_saved_responses(request_id)
    assertions = AssertionService.fetch_for_request(request_id)
    enabled = [a for a in assertions if a.get("enabled", True)]
    lines = [f"Saved examples for {_link('request', request_id, label)}:"]
    if not examples:
        hint = ""
        if row is None:
            hint = " (request not found — get a valid link from collection_tree)"
        lines.append(f"  (no saved example responses){hint}")
    else:
        example_lines: list[str] = []
        follow_ups: list[tuple[str, int]] = []
        for ex in examples:
            code = ex.get("code")
            status = ex.get("status") or ""
            eid = ex.get("id")
            name = _truncate_text(str(ex.get("name", "")), max_len=120)
            meta = f"{name} · {code} {status}".strip()
            if isinstance(eid, int):
                example_lines.append(f"  - {_link('saved_response', eid, meta)}")
                follow_ups.append((f"saved_response · {name}", eid))
            else:
                example_lines.append(f"  - {meta}")
        lines.extend(_cap_rows(example_lines, label="saved examples"))
        lines.extend(_follow_up_ids_block(follow_ups))
    lines.append(f"\nDeclarative assertions ({len(enabled)}):")
    if not enabled:
        lines.append("  (none)")
    else:
        assertion_lines: list[str] = []
        for a in enabled:
            subject = str(a.get("subject", ""))
            expected_raw = str(a.get("expected", ""))
            expected = mask_sensitive_value(subject, expected_raw)
            expected = _truncate_text(expected, max_len=200)
            assertion_lines.append(f"  - {a.get('subject')} {a.get('operator')} {expected!r}")
        lines.extend(_cap_rows(assertion_lines, label="assertions"))
    lines.append(f"\nOpen assertions: {_link('request', request_id, label, focus='assertions')}")
    return "\n".join(lines)


def _render_saved_response(response_id: int) -> str:
    """Render one saved example response."""
    ex = CollectionService.get_saved_response(response_id)
    if ex is None:
        return "Saved response not found."
    name = str(ex.get("name", f"example {response_id}"))
    lines = [f"Saved example · {_link('saved_response', response_id, name)}:"]
    code = ex.get("code")
    status = ex.get("status") or ""
    lines.append(f"  {code} {status}".strip())
    headers = _normalize_header_list(ex.get("headers")) or []
    for h in headers[:20]:
        k = str(h.get("key", ""))
        v = _mask_header_value(k, str(h.get("value", "")))
        lines.append(f"  Header: {k}: {v}")
    body = ex.get("body")
    if body is not None:
        lang = str(ex.get("preview_language") or "text")
        size = ex.get("body_size", len(str(body)))
        preview = _truncate_text(
            _redact_response_body(str(body), lang, headers=headers),
        )
        lines.append(f"  Body ({lang}, {size} bytes): {preview}")
    lines.extend(_follow_up_ids_block([(f"saved_response · {name}", response_id)]))
    return "\n".join(lines)


def _render_runs(collection_id: int) -> str:
    """Summarize recent collection runner results."""
    coll = CollectionService.get_collection(collection_id)
    label = coll.name if coll else f"collection {collection_id}"
    _RUNS_LIMIT = 10
    runs = RunHistoryService.get_runs(collection_id, limit=_RUNS_LIMIT)
    if not runs:
        hint = ""
        if coll is None:
            hint = " (target_id must be a collection/folder id, not a request id)"
        return f"No runs for {_link('collection', collection_id, label)}.{hint}"
    lines = [f"Runs for {_link('collection', collection_id, label)} (latest first):"]
    follow_ups: list[tuple[str, int]] = []
    for run in runs:
        when = _format_ts(run.get("finished_at") or run.get("started_at") or "")
        status = run.get("status", "")
        total = run.get("total_requests", 0)
        tests = run.get("total_tests", 0)
        passed = run.get("passed", 0)
        failed = run.get("failed", 0)
        avg = run.get("avg_response_ms", 0)
        iterations = run.get("iterations", 1)
        skipped = run.get("skipped", 0)
        duration = run.get("duration_ms", 0)
        rid = run.get("id")
        iter_part = f" · {iterations} iter" if iterations > 1 else ""
        skip_part = f" · {skipped} skipped" if skipped > 0 else ""
        lines.append(
            f"- {when} · {status} · {total} req{iter_part} · "
            f"{tests} tests · {passed} passed / {failed} failed{skip_part} · "
            f"{duration} ms total · avg {avg:.0f} ms"
        )
        if isinstance(rid, int):
            follow_ups.append((f"run · {when} · {status}", rid))
    latest = runs[0]
    run_id = latest.get("id")
    if isinstance(run_id, int) and latest.get("failed", 0):
        lines.append("  Latest run failures:")
        failures: list[str] = []
        for result in RunHistoryService.get_run_results(run_id):
            if result.get("test_failed", 0) or result.get("error"):
                method = result.get("request_method", "GET")
                name = _truncate_text(str(result.get("request_name", "")), max_len=120)
                req_id = result.get("request_id")
                name_bit = _request_label_link(
                    req_id if isinstance(req_id, int) else None,
                    name,
                )
                code = result.get("status_code", 0)
                err = _truncate_text(str(result.get("error") or ""), max_len=200)
                failures.append(f"    failed: {method} {name_bit} — {code} {err}".strip())
        lines.extend(_cap_rows(failures, label="run failures", limit=20))
    lines.extend(_follow_up_ids_block(follow_ups))
    body = "\n".join(lines)
    if len(runs) >= _RUNS_LIMIT:
        return _with_leading_markers(
            body,
            [
                f"[partial] Showing latest {_RUNS_LIMIT} runs "
                "(older runs may exist — use scope=run with a follow-up target_id)."
            ],
        )
    return body


def _render_run(run_id: int) -> str:
    """Render per-request results for one collection run."""
    results = RunHistoryService.get_run_results(run_id)
    if not results:
        return "Run not found or has no results."
    lines = ["Run results:"]
    multi_iter = any(
        isinstance(r.get("iteration"), int) and int(r.get("iteration", 0)) > 0 for r in results
    ) or len({r.get("request_name") for r in results}) < len(results)
    rows: list[str] = []
    for result in results:
        method = result.get("request_method", "GET")
        name = _truncate_text(str(result.get("request_name", "")), max_len=120)
        req_id = result.get("request_id")
        name_bit = _request_label_link(
            req_id if isinstance(req_id, int) else None,
            name,
        )
        code = result.get("status_code", 0)
        elapsed = result.get("elapsed_ms")
        lat = f" · {int(elapsed)} ms" if elapsed is not None else ""
        passed = result.get("test_passed", 0)
        failed = result.get("test_failed", 0)
        iter_n = result.get("iteration")
        prefix = ""
        if multi_iter and isinstance(iter_n, int):
            prefix = f"iter {iter_n + 1}: "
        row = (
            f"- {prefix}{method} {name_bit} · {code}{lat} · tests {passed} passed / {failed} failed"
        )
        if failed and result.get("test_results"):
            test_rows = result.get("test_results")
            if isinstance(test_rows, list):
                for test_row in test_rows:
                    if not isinstance(test_row, dict) or test_row.get("passed"):
                        continue
                    tname = _truncate_text(str(test_row.get("name", "")), max_len=120)
                    terr = test_row.get("error")
                    if terr:
                        masked = _mask_console_log_message(str(terr))
                        row += f"\n    failed: {tname}: {_truncate_text(masked, max_len=200)}"
        err = result.get("error")
        if err:
            masked_err = _mask_console_log_message(str(err))
            row += f"\n    error: {_truncate_text(masked_err, max_len=200)}"
        rows.append(row)
    lines.extend(_cap_rows(rows, label="run results"))
    lines.extend(_follow_up_ids_block([("run · results", run_id)]))
    return "\n".join(lines)


def _render_environments(*, env_id: int | None = None) -> str:
    """List environments with masked secret variable values."""
    if env_id is not None:
        env = EnvironmentService.get_environment(env_id)
        if env is None:
            return "Environment not found."
        values = _redact_env_values(env.values if isinstance(env.values, list) else None)
        var_rows = [
            f"{v.get('key', '')} = {_truncate_text(str(v.get('value', '')), max_len=_HEADER_VALUE_MAX)}"
            for v in values
            if v.get("enabled", True)
        ]
        lines = [f"Environment {_link('environment', env_id, env.name)}:"]
        if var_rows:
            lines.extend(_cap_rows([f"- {row}" for row in var_rows], label="variables"))
        else:
            lines.append("(no variables)")
        lines.extend(_follow_up_ids_block([(f"environment · {env.name}", env_id)]))
        return "\n".join(lines)
    envs = EnvironmentService.fetch_all()
    if not envs:
        return "No environments."
    env_lines: list[str] = []
    follow_ups: list[tuple[str, int]] = []
    for env_row in envs:
        eid = env_row.get("id")
        name = str(env_row.get("name", ""))
        values = _redact_env_values(env_row.get("values") or [])
        pairs = _format_env_pairs(values)
        header = _link("environment", eid, name) if isinstance(eid, int) else name
        env_lines.append(f"- {header}: {', '.join(pairs) if pairs else '(no variables)'}")
        if isinstance(eid, int):
            follow_ups.append((f"environment · {name}", eid))
    lines = ["Environments:"]
    lines.extend(_cap_rows(env_lines, label="environments"))
    lines.extend(_follow_up_ids_block(follow_ups))
    return "\n".join(lines)


def _render_collection(collection_id: int) -> str:
    """Render one folder's own configuration and direct children."""
    row = CollectionService.get_collection(collection_id)
    if row is None:
        return "Collection not found."
    breadcrumb = CollectionService.get_collection_breadcrumb(collection_id)
    path = " / ".join(str(seg.get("name", "")) for seg in breadcrumb)
    lines = [
        f"{_link('collection', collection_id, row.name)}:",
        f"  Path: {path}",
    ]
    if row.description:
        lines.append(f"  Description: {_truncate_text(str(row.description), max_len=400)}")
    auth = _redact_auth(row.auth if isinstance(row.auth, dict) else None)
    if auth:
        lines.append(f"  Auth: {json.dumps(auth, ensure_ascii=False)}")
    elif row.auth is None:
        inherited = _redact_auth(CollectionService.get_collection_inherited_auth(collection_id))
        if inherited:
            lines.append(f"  Inherited auth: {json.dumps(inherited, ensure_ascii=False)}")
        else:
            lines.append("  Inherited auth: (none / no-auth)")
    values = _redact_env_values(row.variables if isinstance(row.variables, list) else None)
    if values:
        pairs = _format_env_pairs(values)
        lines.append(f"  Variables: {', '.join(pairs)}")
    scripts = _scripts_from_data({"events": row.events})
    for kind, src in scripts.items():
        lines.append(
            f"\n  {kind} script ({_link('collection', collection_id, row.name, focus=kind)}):"
        )
        lines.append(_truncate_text(src, max_len=1200))
    count = CollectionService.get_folder_request_count(collection_id)
    lines.append(f"  Requests in subtree: {count}")
    child_lines: list[str] = []
    tree = CollectionService.fetch_all()

    def _find_node(nodes: dict[str, Any], cid: int) -> dict[str, Any] | None:
        for node in nodes.values():
            if node.get("type") == "folder" and node.get("id") == cid:
                return cast(dict[str, Any], node)
            found = _find_node(node.get("children") or {}, cid)
            if found is not None:
                return found
        return None

    node = _find_node(tree, collection_id)
    if node is not None:
        for _key, child in sorted(
            (node.get("children") or {}).items(),
            key=lambda kv: str(kv[1].get("name", "")).casefold(),
        ):
            ctype = child.get("type")
            cid = child.get("id")
            cname = str(child.get("name", ""))
            if ctype == "folder" and isinstance(cid, int):
                child_lines.append(f"  - {_link('collection', cid, cname)} (folder)")
            elif ctype == "request" and isinstance(cid, int):
                method = str(child.get("method", "GET"))
                url = _truncate_url(str(child.get("url", "")))
                child_lines.append(f"  - {_link('request', cid, cname)} — {method} {url}")
    if child_lines:
        lines.append("  Direct children:")
        lines.extend(_cap_rows(child_lines, label="children"))
    return "\n".join(lines)


def _render_recent_history(*, search: str = "") -> str:
    """List workspace-wide recent sends (newest first)."""
    _RECENT_LIMIT = 25
    text_filter, since, until = _parse_history_search(search)
    entries = RequestHistoryService.list_for_sidebar(
        text_filter,
        executed_from=since,
        executed_to=until,
        limit=_RECENT_LIMIT,
    )
    if not entries:
        return "No recent send history."
    lines = ["Recent send history (newest first):"]
    follow_ups: list[tuple[str, int]] = []
    for entry in entries:
        eid = entry.get("id")
        when = _format_ts(entry.get("executed_at") or "")
        status = entry.get("status_code") or "?"
        latency = entry.get("elapsed_ms")
        lat = f" · {int(latency)} ms" if latency is not None else ""
        err = entry.get("error")
        err_s = f" · error: {_truncate_text(str(err), max_len=200)}" if err else ""
        rid = entry.get("request_id")
        plain_name = str(
            entry.get("request_name")
            or (f"request {rid}" if isinstance(rid, int) else None)
            or entry.get("source_label")
            or "draft send"
        )
        req_label = _link("request", rid, plain_name) if isinstance(rid, int) else plain_name
        hist_title = f"{when} · {status}{lat}{err_s}"
        if isinstance(eid, int):
            lines.append(f"- {_link('history', eid, hist_title)} · {req_label}")
            follow_ups.append((f"history_entry · {when} · {plain_name}", eid))
        else:
            lines.append(f"- {when} · {req_label} · {status}{lat}{err_s}")
    lines.extend(_follow_up_ids_block(follow_ups))
    body = "\n".join(lines)
    if len(entries) >= _RECENT_LIMIT:
        return _with_leading_markers(
            body,
            [
                f"[partial] Showing latest {_RECENT_LIMIT} sends "
                "(older history may exist — pass search=… or use request_history)."
            ],
        )
    return body


def _render_insights() -> str:
    """List requests missing test scripts and declarative assertions."""
    from ..constants import _SEARCH_SCRIPT_SCAN_CAP

    tree = CollectionService.fetch_all()
    request_ids: list[int] = []

    def _collect_ids(nodes: dict[str, Any]) -> None:
        for node in nodes.values():
            if len(request_ids) >= _SEARCH_SCRIPT_SCAN_CAP:
                return
            if node.get("type") == "folder":
                _collect_ids(node.get("children") or {})
            elif node.get("type") == "request" and isinstance(node.get("id"), int):
                request_ids.append(node["id"])

    _collect_ids(tree)
    if not request_ids:
        return "No requests in the workspace."
    scripts_by_id = {
        rid: (name, scripts, events)
        for rid, name, scripts, events in CollectionService.fetch_request_scripts_for_ids(
            request_ids
        )
    }
    assertion_counts = {
        rid: (total, enabled)
        for rid, total, enabled in CollectionService.fetch_assertion_counts_for_ids(request_ids)
    }
    missing_lines: list[str] = []
    for rid in request_ids:
        row = scripts_by_id.get(rid)
        name = row[0] if row else f"request {rid}"
        scripts = _scripts_from_data(
            {"scripts": row[1], "events": row[2]} if row is not None else None
        )
        has_test_script = bool(scripts.get("test"))
        _total, enabled_assertions = assertion_counts.get(rid, (0, 0))
        if has_test_script or enabled_assertions > 0:
            continue
        missing_lines.append(f"- {_link('request', rid, name)} (no test script or assertions)")
    lines = ["Workspace test coverage insights:"]
    if not missing_lines:
        lines.append("  All scanned requests have a test script or declarative assertions.")
    else:
        lines.extend(_cap_rows(missing_lines, label="requests missing tests"))
    body = "\n".join(lines)
    if len(request_ids) >= _SEARCH_SCRIPT_SCAN_CAP:
        return _with_leading_markers(
            body,
            [
                f"[partial] Scan limited to the first {_SEARCH_SCRIPT_SCAN_CAP} "
                "requests in tree order."
            ],
        )
    return body
