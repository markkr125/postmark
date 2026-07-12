"""Saved-response and collection-run scope renderers for the workspace query tool."""

from __future__ import annotations

from services.assertion_service import AssertionService
from services.collection_service import CollectionService, _normalize_header_list
from services.run_history_service import RunHistoryService
from services.scripting.context import mask_sensitive_value

from ...helpers import (
    _cap_rows,
    _follow_up_ids_block,
    _format_ts,
    _link,
    _mask_console_log_message,
    _mask_header_value,
    _redact_response_body,
    _request_label_link,
    _truncate_text,
    _with_leading_markers,
)


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
