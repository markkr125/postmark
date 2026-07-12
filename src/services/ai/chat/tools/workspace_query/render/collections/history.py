"""History scope renderers for the workspace query tool."""

from __future__ import annotations

import statistics

from services.collection_service import CollectionService
from services.request_history_service import (
    RequestHistoryService,
    _normalize_history_response_headers,
)

from ...constants import _URL_PREVIEW_MAX
from ...helpers import (
    _follow_up_ids_block,
    _format_request_body_preview,
    _format_ts,
    _link,
    _mask_header_value,
    _parse_history_search,
    _redact_response_body,
    _redact_url,
    _truncate_text,
    _truncate_url,
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


def _render_request_history(request_id: int, *, search: str = "") -> str:
    """List recent sends for a request.

    Prefix ``body:<needle>`` searches redacted response bodies among the latest
    sends (always ``[partial]`` — never authoritative-empty for body-only misses).
    """
    row = CollectionService.get_request(request_id)
    label = row.name if row else f"request {request_id}"
    raw_search = search.strip()
    if raw_search.lower().startswith("body:"):
        needle = raw_search.split(":", 1)[1].strip().casefold()
        if not needle:
            return "body: search requires a non-empty needle."
        entries = RequestHistoryService.list_for_request(request_id)[:25]
        hits: list[str] = []
        for entry in entries:
            eid = entry.get("id")
            if not isinstance(eid, int):
                continue
            detail = RequestHistoryService.entry_to_detail_snapshot(entry)
            body = str(detail.get("body") or "")
            headers = _normalize_history_response_headers(detail.get("headers"))
            redacted = _redact_response_body(body, "text", headers=headers)
            if needle in redacted.casefold():
                when = _format_ts(entry.get("executed_at") or "")
                status = entry.get("status_code") or "?"
                hits.append(f"- {_link('history', eid, f'{when} · {status}')} (body match)")
        body_out = (
            f"History body search for {_link('request', request_id, label)} "
            f'(needle "{needle}", latest {len(entries)}):\n'
            + ("\n".join(hits) if hits else "No body matches in the latest sends scanned.")
        )
        return _with_leading_markers(
            body_out,
            [
                "[partial] History body search is redacted and limited to the latest 25 "
                "sends — never treat empty as proof the needle is absent from older history."
            ],
        )
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
