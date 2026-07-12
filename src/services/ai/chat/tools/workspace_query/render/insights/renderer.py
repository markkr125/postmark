"""Workspace health renderer for scope=insights."""

from __future__ import annotations

from typing import Any

from services.ai.chat.workspace_snapshot import get_last_search_hits, set_last_search_hits
from services.collection_service import CollectionService

from ...constants import _SEARCH_SCRIPT_SCAN_CAP
from ...helpers import _cap_rows, _with_leading_markers
from ..search import _resolve_within_ids
from .scans import (
    _collect_dup_groups,
    _walk_request_nodes,
    scan_auth_gaps,
    scan_duplicates,
    scan_local_deps,
    scan_missing_tests,
    scan_request_drift,
    scan_script_regressions,
    scan_secret_hygiene,
    scan_variable_issues,
)

_SECTION_KEYS = frozenset(
    {
        "missing_tests",
        "duplicates",
        "unresolved",
        "unused",
        "case_mismatch",
        "disabled_ref",
        "auth",
        "secret_hygiene",
        "local_deps",
        "drift",
        "script_regression",
    }
)


def _want(sections: set[str] | None, key: str) -> bool:
    """Return True when *key* should be rendered."""
    return sections is None or key in sections


def _render_insights(
    *,
    snap: dict[str, Any] | None = None,
    within_ids: list[int] | None = None,
    session_id: str | None = None,
    sections: list[str] | None = None,
) -> str:
    """Render workspace health insights (read-only audits)."""
    snap = snap or {}
    section_filter: set[str] | None = None
    if sections:
        section_filter = {s for s in sections if s in _SECTION_KEYS}
        if not section_filter:
            return "Unknown insights sections. Valid: " + ", ".join(sorted(_SECTION_KEYS)) + "."

    within: set[int] | None = None
    if within_ids is not None:
        resolved, err = _resolve_within_ids(within_ids, session_id=session_id or "")
        if err:
            return err
        within = resolved

    env_raw = snap.get("current_env_id")
    env_id = env_raw if isinstance(env_raw, int) else None
    tree = CollectionService.fetch_all()
    request_rows = _walk_request_nodes(tree, within=within, limit=_SEARCH_SCRIPT_SCAN_CAP)
    request_ids = [rid for rid, _n, _m, _u in request_rows]
    dup_groups = _collect_dup_groups(tree, within=within)

    if not request_ids and not any(len(g) > 1 for g in dup_groups.values()):
        if within is not None:
            return "No matching requests in the within_ids set for insights."
        return "No requests in the workspace."

    scripts_by_id = {
        rid: (name, scripts, events)
        for rid, name, scripts, events in CollectionService.fetch_request_scripts_for_ids(
            request_ids
        )
    }
    fields_by_id = {
        rid: (name, body, body_mode, body_options, description, headers, auth, params)
        for rid, name, body, body_mode, body_options, description, headers, auth, params in (
            CollectionService.fetch_request_fields_for_ids(request_ids)
        )
    }
    assertion_counts = {
        rid: (total, enabled)
        for rid, total, enabled in CollectionService.fetch_assertion_counts_for_ids(request_ids)
    }

    markers: list[str] = []
    counts: dict[str, int] = {}
    blocks: list[str] = []

    if _want(section_filter, "missing_tests"):
        missing = scan_missing_tests(request_rows, scripts_by_id, assertion_counts)
        counts["missing_tests"] = len(missing)
        blocks.append("\nMissing tests:")
        if not missing:
            blocks.append("  All scanned requests have a test script or declarative assertions.")
        else:
            blocks.extend(_cap_rows(missing, label="requests missing tests"))

    if _want(section_filter, "duplicates"):
        dupes = scan_duplicates(dup_groups)
        counts["duplicates"] = len(dupes)
        if dupes:
            blocks.append("\nDuplicate requests (same method + URL):")
            blocks.extend(_cap_rows(dupes, label="duplicate groups"))

    need_vars = any(
        _want(section_filter, k) for k in ("unresolved", "unused", "case_mismatch", "disabled_ref")
    )
    if need_vars:
        unresolved, unused, mismatch, disabled = scan_variable_issues(
            request_rows,
            env_id=env_id,
            fields_by_id=fields_by_id,
            scripts_by_id=scripts_by_id,
        )
        if _want(section_filter, "unresolved"):
            counts["unresolved"] = len(unresolved)
            if unresolved:
                blocks.append("\nUnresolved variables:")
                blocks.extend(_cap_rows(unresolved, label="unresolved requests"))
        if _want(section_filter, "unused"):
            counts["unused"] = len(unused)
            if unused:
                blocks.append("\nUnused definitions:")
                blocks.extend(_cap_rows(unused, label="unused keys"))
        if _want(section_filter, "case_mismatch"):
            counts["case_mismatch"] = len(mismatch)
            if mismatch:
                blocks.append("\nCase-mismatch references:")
                blocks.extend(_cap_rows(mismatch, label="case-mismatch refs"))
        if _want(section_filter, "disabled_ref"):
            counts["disabled_ref"] = len(disabled)
            if disabled:
                blocks.append("\nDisabled-but-referenced:")
                blocks.extend(_cap_rows(disabled, label="disabled refs"))

    if _want(section_filter, "auth"):
        auth_gaps = scan_auth_gaps(request_rows, fields_by_id)
        counts["auth"] = len(auth_gaps)
        if auth_gaps:
            blocks.append("\nAuth gaps:")
            blocks.extend(_cap_rows(auth_gaps, label="auth gaps"))

    if _want(section_filter, "secret_hygiene"):
        hygiene = scan_secret_hygiene()
        counts["secret_hygiene"] = len(hygiene)
        if hygiene:
            blocks.append("\nSecret hygiene (keys only):")
            blocks.extend(_cap_rows(hygiene, label="hygiene findings"))

    if _want(section_filter, "local_deps"):
        local_lines = scan_local_deps()
        counts["local_deps"] = len(local_lines)
        if local_lines:
            blocks.append("\nLocal-script breakage:")
            blocks.extend(_cap_rows(local_lines, label="local dependency issues"))

    if _want(section_filter, "drift"):
        drift = scan_request_drift(request_rows)
        counts["drift"] = len(drift)
        if drift:
            blocks.append("\nRequest drift (vs last send):")
            blocks.extend(_cap_rows(drift, label="drift findings"))

    if _want(section_filter, "script_regression"):
        regs = scan_script_regressions(request_rows, scripts_by_id)
        counts["script_regression"] = len(regs)
        if regs:
            blocks.append("\nScript regressions:")
            blocks.extend(_cap_rows(regs, label="script regressions"))

    summary_parts = [f"{k}={v}" for k, v in counts.items() if v]
    summary = ", ".join(summary_parts) if summary_parts else "no issues in scanned sections"
    header = ["Workspace health:", f"  Summary: {summary}"]
    if within is not None:
        header.append(f"  Restricted to {len(within)} request id(s).")
    body = "\n".join([*header, *blocks])

    if len(request_ids) >= _SEARCH_SCRIPT_SCAN_CAP:
        markers.append(
            f"[partial] Request-scoped health scans limited to the first "
            f"{_SEARCH_SCRIPT_SCAN_CAP} requests in tree order "
            "(duplicate URL grouping follows the same within/filter rules)."
        )
    if session_id and request_ids:
        prior = get_last_search_hits(session_id) or []
        if not prior:
            set_last_search_hits(session_id, request_ids)

    return _with_leading_markers(body, markers) if markers else body
