"""Live snapshot scope renderers for the workspace query tool."""

from __future__ import annotations

import json
from typing import Any

from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.local_script_service import LocalScriptService

from ..helpers import (
    _active_tab,
    _cap_rows,
    _follow_up_ids_block,
    _format_request_body_preview,
    _format_network_compact,
    _format_size_breakdown,
    _format_timing_compact,
    _format_variable_changes,
    _link,
    _mask_console_log_message,
    _mask_header_value,
    _mask_param_value,
    _redact_auth,
    _redact_response_body,
    _scope_variable_lines,
    _scripts_from_data,
    _truncate_text,
    _truncate_url,
    _with_leading_markers,
)


def _render_overview(snap: dict[str, Any]) -> str:
    """Render workspace overview."""
    folders = CollectionService.count_all_collections()
    requests = CollectionService.count_all_requests()
    envs = EnvironmentService.fetch_all()
    env_names = [str(e.get("name", "")) for e in envs]
    active_env = snap.get("current_env_id")
    follow_ups: list[tuple[str, int]] = []
    if active_env is None:
        env_label = "(none)"
    else:
        name = next((str(e.get("name", "")) for e in envs if e.get("id") == active_env), "")
        plain = name if name else f"environment {active_env}"
        if isinstance(active_env, int):
            env_label = _link("environment", active_env, plain)
            follow_ups.append((f"environment · {plain}", active_env))
        else:
            env_label = plain
    lines = [
        "Workspace overview:",
        f"- Collections: {folders} folders, {requests} requests",
        f"- Environments: {', '.join(env_names) or '(none)'}",
        f"- Active environment: {env_label}",
        f"- Open tabs: {len(snap.get('tabs') or [])}",
    ]
    captured_at = snap.get("captured_at")
    if captured_at:
        lines.append(
            f"- Snapshot captured at: {captured_at} (turn-start; mid-turn edits may differ)"
        )
    tab = _active_tab(snap)
    if tab:
        label = str(tab.get("name", "tab"))
        ttype = str(tab.get("tab_type", ""))
        linked = label
        if ttype in ("request", "draft") and isinstance(tab.get("request_id"), int):
            linked = _link("request", int(tab["request_id"]), label)
        elif ttype == "folder" and isinstance(tab.get("collection_id"), int):
            linked = _link("collection", int(tab["collection_id"]), label)
        elif ttype == "local_script" and isinstance(tab.get("local_script_id"), int):
            linked = _link("script", int(tab["local_script_id"]), label)
        else:
            linked = _link("tab", int(tab.get("index", 0)) + 1, label)
        dirty = (
            "dirty" if tab.get("is_dirty") else ("deferred" if tab.get("is_deferred") else "saved")
        )
        detail = ""
        if ttype in ("request", "draft"):
            data = tab.get("request_data") or {}
            if isinstance(data, dict) and data:
                method = str(data.get("method", "GET"))
                url = _truncate_url(str(data.get("url", "")))
                if url:
                    detail = f" — {method} {url}"
            elif isinstance(tab.get("request_id"), int):
                row = CollectionService.get_request(int(tab["request_id"]))
                if row is not None:
                    method = str(row.method or "GET")
                    url_text = str(row.url or "")
                    if url_text:
                        detail = f" — {method} {_truncate_url(url_text)}"
        lines.append(f"- Active tab: {linked} ({ttype}, {dirty}){detail}")
    lines.extend(_follow_up_ids_block(follow_ups))
    return "\n".join(lines)


def _render_open_tabs(snap: dict[str, Any]) -> str:
    """List every open editor tab."""
    tabs = snap.get("tabs") or []
    if not tabs:
        return "No open tabs."
    missing_ids: list[int] = []
    for tab in tabs:
        if (
            tab.get("tab_type") in ("request", "draft")
            and isinstance(tab.get("request_id"), int)
            and not tab.get("request_data")
        ):
            missing_ids.append(int(tab["request_id"]))
    db_rows: dict[int, Any] = {}
    for rid in missing_ids:
        row = CollectionService.get_request(rid)
        if row is not None:
            db_rows[rid] = row
    lines = ["Open tabs:"]
    tab_lines: list[str] = []
    for tab in sorted(tabs, key=lambda t: int(t.get("index", 0))):
        name = str(tab.get("name", ""))
        ttype = str(tab.get("tab_type", ""))
        if tab.get("is_deferred"):
            dirty = "deferred"
        elif tab.get("is_dirty"):
            dirty = "dirty"
        else:
            dirty = "saved"
        active = " (active)" if tab.get("is_active") else ""
        detail = ""
        if ttype == "request" and isinstance(tab.get("request_id"), int):
            rid = int(tab["request_id"])
            data = tab.get("request_data") or {}
            if data:
                method = str(data.get("method", "GET"))
                url = _truncate_url(str(data.get("url", "")))
                detail = f" — {method} {url}"
            elif rid in db_rows:
                row = db_rows[rid]
                method = str(row.method or "GET")
                url_text = str(row.url or "")
                if url_text:
                    detail = f" — {method} {_truncate_url(url_text)}"
            name = _link("request", rid, name)
        elif ttype == "folder" and isinstance(tab.get("collection_id"), int):
            name = _link("collection", tab["collection_id"], name)
        elif ttype == "local_script" and isinstance(tab.get("local_script_id"), int):
            name = _link("script", tab["local_script_id"], name)
        else:
            name = _link("tab", int(tab.get("index", 0)) + 1, name)
            if ttype in ("request", "draft"):
                data = tab.get("request_data") or {}
                rid = tab.get("request_id")
                if data:
                    method = str(data.get("method", "GET"))
                    url = _truncate_url(str(data.get("url", "")))
                    if url:
                        detail = f" — {method} {url}"
                elif isinstance(rid, int) and rid in db_rows:
                    row = db_rows[rid]
                    method = str(row.method or "GET")
                    url_text = str(row.url or "")
                    if url_text:
                        detail = f" — {method} {_truncate_url(url_text)}"
        last_resp = tab.get("last_response")
        if isinstance(last_resp, dict):
            code = last_resp.get("status_code")
            elapsed = last_resp.get("elapsed_ms")
            if code is not None:
                ms = f" ({int(elapsed)} ms)" if isinstance(elapsed, int | float) else ""
                detail += f" · last: {code}{ms}"
        tab_lines.append(f"- {name}{detail} [{dirty}]{active}")
    lines.extend(_cap_rows(tab_lines, label="open tabs"))
    lines.append(
        "Note: tab deep-links use turn-start bar indices "
        "(reorder/close mid-turn may invalidate them)."
    )
    return "\n".join(lines)


def _append_active_tab_request_details(lines: list[str], data: dict[str, Any]) -> None:
    """Append auth, headers, params, and body for an active request tab."""
    auth = data.get("auth")
    redacted = _redact_auth(auth if isinstance(auth, dict) else None)
    if redacted:
        lines.append(f"Auth: {json.dumps(redacted, ensure_ascii=False)}")
    headers = data.get("headers")
    if isinstance(headers, list):
        for h in headers[:20]:
            if isinstance(h, dict):
                k = str(h.get("key", ""))
                v = _mask_header_value(k, str(h.get("value", "")))
                disabled = " (disabled)" if h.get("enabled") is False else ""
                lines.append(f"Header: {k}: {v}{disabled}")
        if len(headers) > 20:
            lines.append(f"…and {len(headers) - 20} more headers")
    params = data.get("request_parameters")
    if isinstance(params, list):
        param_lines: list[str] = []
        for p in params:
            if isinstance(p, dict):
                k = str(p.get("key", ""))
                v = _mask_param_value(k, str(p.get("value", "")))
                disabled = " (disabled)" if p.get("enabled") is False else ""
                param_lines.append(f"Param: {k}: {v}{disabled}")
        lines.extend(_cap_rows(param_lines, label="params"))
    body = data.get("body")
    if body:
        mode = str(data.get("body_mode") or "")
        prefix = f"Body ({mode}):" if mode else "Body:"
        lines.append(f"{prefix} {_format_request_body_preview(body, data)}")


def _render_tab_entry(tab: dict[str, Any], snap: dict[str, Any]) -> str:
    """Describe one tab dict from a workspace snapshot."""
    ttype = str(tab.get("tab_type", ""))
    name = str(tab.get("name", ""))
    lines = [f"Tab: {name} ({ttype})"]
    if tab.get("is_dirty"):
        lines.append("Unsaved edits: yes")
    if ttype in ("request", "draft"):
        data = tab.get("request_data") or {}
        rid = tab.get("request_id")
        if isinstance(rid, int) and not data:
            row = CollectionService.get_request(rid)
            if row is not None:
                data = {
                    "method": row.method,
                    "url": row.url,
                    "body": row.body,
                    "body_mode": row.body_mode,
                    "headers": row.headers,
                    "auth": row.auth,
                    "request_parameters": row.request_parameters,
                    "scripts": row.scripts,
                    "events": row.events,
                }
        if isinstance(rid, int):
            lines[0] = f"Tab: {_link('request', rid, name)}"
        else:
            tab_link_id = int(tab.get("index", 0)) + 1
            lines[0] = f"Tab: {_link('tab', tab_link_id, name)}"
        if data:
            lines.append(f"Method: {data.get('method', 'GET')}")
            lines.append(f"URL: {_truncate_url(str(data.get('url', '')))}")
            _append_active_tab_request_details(lines, data)
            if isinstance(rid, int):
                env_raw = snap.get("current_env_id")
                env_id = env_raw if isinstance(env_raw, int) else None
                var_lines = _scope_variable_lines(env_id, rid)
                overrides = tab.get("local_overrides")
                if isinstance(overrides, dict) and overrides:
                    lines.append("Local variable overrides (this tab):")
                    for key, value in sorted(overrides.items()):
                        lines.append(f"- {key} = {value}")
                if var_lines:
                    lines.append("Variables in scope:")
                    override_keys = set(overrides.keys()) if isinstance(overrides, dict) else set()
                    for line in var_lines:
                        annotated = line
                        for key in override_keys:
                            if line.startswith(f"  {key} ="):
                                annotated = f"{line} (overridden in tab)"
                                break
                        lines.append(annotated)
            scripts = _scripts_from_data(data)
            for kind, src in scripts.items():
                focus = kind
                if isinstance(rid, int):
                    open_link = _link("request", rid, name, focus=focus)
                    lines.append(f"\n{kind} script ({open_link}):")
                else:
                    lines.append(f"\n{kind} script:")
                lines.append(_truncate_text(src, max_len=1200))
    elif ttype == "folder" and isinstance(tab.get("collection_id"), int):
        cid = int(tab["collection_id"])
        lines[0] = f"Tab: {_link('collection', cid, name)}"
        folder_data = tab.get("collection_data")
        if isinstance(folder_data, dict) and tab.get("is_dirty"):
            lines.append(
                "[partial] Showing unsaved folder editor state at turn start "
                "(DB may differ until save)."
            )
            if folder_data.get("description"):
                lines.append(
                    f"Description: {_truncate_text(str(folder_data.get('description')), max_len=400)}"
                )
            scripts = _scripts_from_data(folder_data)
            for kind, src in scripts.items():
                lines.append(f"\n{kind} script ({_link('collection', cid, name, focus=kind)}):")
                lines.append(_truncate_text(src, max_len=800))
        else:
            lines.append("Next call: scope=collection")
        lines.extend(_follow_up_ids_block([(f"collection · {name}", cid)]))
    elif ttype == "environments":
        if tab.get("environment_dirty"):
            lines.append(
                "[partial] Dirty environment editor at turn start — "
                "unsaved values are not fully snapshotted; open the Environments tab "
                "or scope=environments after save for authoritative values."
            )
            eid = tab.get("environment_id")
            if isinstance(eid, int):
                lines.append(f"  Editing: {_link('environment', eid, 'current environment')}")
        else:
            lines.append("Next call: scope=environments")
    elif ttype == "local_script" and isinstance(tab.get("local_script_id"), int):
        sid = tab["local_script_id"]
        lines[0] = f"Tab: {_link('script', sid, name)}"
        lang = tab.get("local_script_language") or "javascript"
        content = tab.get("local_script_content") or ""
        if not content:
            loaded = LocalScriptService.get_script_load_dict(sid)
            if loaded:
                lang = loaded.get("language", lang)
                content = loaded.get("content") or ""
        lines.append(f"Language: {lang}")
        if content:
            lines.append(_truncate_text(content, max_len=1200))
    return "\n".join(lines)


def _render_tab(snap: dict[str, Any], tab_index: int) -> str:
    """Render one open tab by 1-based index."""
    tabs = snap.get("tabs") or []
    zero_index = tab_index - 1
    tab = next((t for t in tabs if int(t.get("index", 0)) == zero_index), None)
    if tab is None:
        return f"No tab at index {tab_index}."
    return _render_tab_entry(tab, snap)


def _render_active_tab(snap: dict[str, Any]) -> str:
    """Describe the focused tab including unsaved edits and scripts."""
    tab = _active_tab(snap)
    if tab is None:
        return "No active tab."
    text = _render_tab_entry(tab, snap)
    return text.replace("Tab:", "Active tab:", 1)


def _render_active_response(snap: dict[str, Any], *, search: str = "") -> str:
    """Describe the response currently shown in the active tab.

    When ``search`` is ``diff:<history_entry_id>``, append a redacted replay-diff
    against that stored send (always ``[partial]`` — bodies are truncated/redacted).
    """
    diff_id: int | None = None
    raw = search.strip()
    if raw.lower().startswith("diff:"):
        try:
            diff_id = int(raw.split(":", 1)[1].strip())
        except ValueError:
            return "active_response diff requires search=diff:<history_entry_id>."

    resp = snap.get("active_response")
    if isinstance(resp, dict):
        send_error = resp.get("send_error")
        if send_error:
            return "Last send FAILED: " + _mask_console_log_message(str(send_error))
        stored_id = resp.get("viewing_stored_entry_id")
        if isinstance(stored_id, int) and diff_id is None:
            lines = [
                "Viewer is showing a stored history entry — "
                f"{_link('history', stored_id, 'open this send')} "
                "(or use scope=history_entry with the follow-up target_id for details).",
            ]
            lines.extend(_follow_up_ids_block([("history_entry · stored viewer entry", stored_id)]))
            return "\n".join(lines)
    if not resp:
        return "No live response in the active tab."
    tab = _active_tab(snap) or {}
    rid = tab.get("request_id")
    header = "Active response"
    if isinstance(rid, int):
        label = str(tab.get("name", f"request {rid}"))
        header = f"Active response for {_link('request', rid, label)}"
    code = resp.get("code")
    status = resp.get("status") or ""
    elapsed = resp.get("elapsed_ms")
    size = resp.get("size_bytes")
    parts = [header + ":"]
    markers: list[str] = []
    stat_line = f"  {code} {status}".strip()
    if elapsed is not None:
        stat_line += f" · {int(elapsed)} ms"
    if size is not None:
        stat_line += f" · {size} B"
    parts.append(stat_line)
    headers = resp.get("headers") or []
    if headers:
        hdr_bits = []
        for h in headers[:12]:
            if isinstance(h, dict):
                k = str(h.get("key", ""))
                v = _mask_header_value(k, str(h.get("value", "")))
                hdr_bits.append(f"{k}: {v}")
        if hdr_bits:
            parts.append("  Headers: " + "; ".join(hdr_bits))
    body = resp.get("body")
    if body is not None:
        preview_lang = str(resp.get("preview_language") or "text")
        raw_body = str(body)
        preview = _truncate_text(
            _redact_response_body(raw_body, preview_lang, headers=headers if headers else None)
        )
        parts.append(f"  Body ({preview_lang}, {len(raw_body)} chars): {preview}")
    if diff_id is not None:
        from services.request_history_service import RequestHistoryService

        entry = RequestHistoryService.get_entry(diff_id)
        markers.append(
            "[partial] Replay-diff compares redacted/truncated previews only — "
            "not a byte-identical forensic diff."
        )
        if entry is None:
            parts.append(f"\n  Replay-diff: history entry {diff_id} not found.")
        else:
            detail = RequestHistoryService.entry_to_detail_snapshot(entry)
            hist_code = detail.get("status_code")
            hist_body = str(detail.get("body") or "")
            live_code = code
            parts.append(f"\n  Replay-diff vs {_link('history', diff_id, f'send {diff_id}')}:")
            if live_code != hist_code:
                parts.append(f"    Status: live={live_code} · history={hist_code}")
            else:
                parts.append(f"    Status: both {live_code}")
            live_s = _truncate_text(
                _redact_response_body(str(body or ""), "text", headers=headers),
                max_len=200,
            )
            hist_s = _truncate_text(
                _redact_response_body(hist_body, "text"),
                max_len=200,
            )
            if live_s != hist_s:
                parts.append(f"    Body live: {live_s}")
                parts.append(f"    Body hist: {hist_s}")
            else:
                parts.append("    Body preview: identical (after redaction/truncation)")
    tests = resp.get("test_summary")
    if isinstance(tests, dict):
        passed = tests.get("passed", 0)
        failed = tests.get("failed", 0)
        parts.append(f"  Tests: {passed} passed, {failed} failed")
        test_results = resp.get("test_results")
        if isinstance(test_results, list):
            pass_lines: list[str] = []
            for row in test_results:
                if not isinstance(row, dict):
                    continue
                if not row.get("passed"):
                    continue
                name = _truncate_text(str(row.get("name", "")), max_len=120)
                pass_lines.append(f"    passed: {name}")
            if pass_lines:
                parts.append("  Passing tests:")
                parts.extend(_cap_rows(pass_lines, label="passing tests", limit=20))
            if failed:
                fail_lines: list[str] = []
                for row in test_results:
                    if not isinstance(row, dict):
                        continue
                    if row.get("passed"):
                        continue
                    name = _truncate_text(str(row.get("name", "")), max_len=120)
                    err = row.get("error")
                    err_s = ""
                    if err:
                        masked = _mask_console_log_message(str(err))
                        err_s = f" — {_truncate_text(masked, max_len=200)}"
                    fail_lines.append(f"    failed: {name}{err_s}")
                parts.extend(_cap_rows(fail_lines, label="failed tests", limit=20))
            total_tests = int(passed) + int(failed)
            if total_tests > len(test_results):
                parts.append(
                    f"  (showing {len(test_results)} of {total_tests} results; "
                    "failures listed first)"
                )
    pre_changes = resp.get("pre_request_variable_changes")
    if isinstance(pre_changes, dict) and pre_changes:
        parts.append("  Pre-request variable changes:")
        parts.extend(_cap_rows(_format_variable_changes(pre_changes), label="pre-request changes"))
    var_changes = resp.get("variable_changes")
    if isinstance(var_changes, dict) and var_changes:
        parts.append("  Variable changes:")
        parts.extend(_cap_rows(_format_variable_changes(var_changes), label="variable changes"))
    timing = resp.get("timing")
    if isinstance(timing, dict):
        timing_line = _format_timing_compact(timing)
        if timing_line:
            parts.append(f"  Timing: {timing_line}")
    size_line = _format_size_breakdown(resp)
    if size_line:
        parts.append(f"  Sizes: {size_line}")
    network = resp.get("network")
    if isinstance(network, dict):
        network_line = _format_network_compact(network)
        if network_line:
            parts.append(f"  Network: {network_line}")
    console_logs = resp.get("console_logs")
    if isinstance(console_logs, list) and console_logs:
        console_lines: list[str] = []
        for entry in console_logs:
            if not isinstance(entry, dict):
                continue
            level = str(entry.get("level", "log"))
            message = _truncate_text(
                _mask_console_log_message(str(entry.get("message", ""))),
                max_len=200,
            )
            console_lines.append(f"    {level}: {message}")
        if console_lines:
            parts.append("  Console:")
            parts.extend(_cap_rows(console_lines, label="console lines"))
    body_out = "\n".join(parts)
    if markers:
        return _with_leading_markers(body_out, markers)
    return body_out
