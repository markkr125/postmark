"""Request-vs-history and response-shape drift insights scans."""

from __future__ import annotations

import json
from typing import Any

from services.request_history_service import RequestHistoryService

from ....constants import REDACTED_PLACEHOLDER
from ....helpers import _key_is_sensitive, _link


def scan_request_drift(
    request_rows: list[tuple[int, str, str, str]],
) -> list[str]:
    """Saved request differs from last-sent original snapshot."""
    lines: list[str] = []
    for rid, name, method, url in request_rows:
        latest = RequestHistoryService.latest_for_request(rid)
        if latest is None:
            continue
        original = latest.get("original_request") or {}
        if not isinstance(original, dict):
            continue
        sent_method = str(original.get("method") or "").upper()
        sent_url = str(original.get("url") or "")
        if sent_method and sent_method != method:
            lines.append(
                f"- {_link('request', rid, name)} — method changed since last send "
                f"({sent_method} → {method})"
            )
        elif sent_url and sent_url.strip() != url.strip():
            lines.append(f"- {_link('request', rid, name)} — URL changed since last send")
    return lines


def _json_type_name(value: Any) -> str:
    """Return a short type label for JSON schema-ish path diffs."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "num"
    if isinstance(value, float):
        return "num"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "arr"
    if isinstance(value, dict):
        return "obj"
    return "unknown"


def _safe_path_key(key: Any) -> str:
    """Return a path segment, redacting secret-shaped object keys."""
    text = str(key)
    if _key_is_sensitive(text):
        return REDACTED_PLACEHOLDER
    return text


def _typed_paths(value: Any, prefix: str = "") -> dict[str, str]:
    """Build ``path → type`` map for a JSON value (arrays use ``[]``).

    Array element shapes are **merged** across all items so reordering or a
    null-first element does not fabricate drift.
    """
    if isinstance(value, dict):
        if not value:
            return {prefix: "obj"} if prefix else {}
        out: dict[str, str] = {}
        for key, child in value.items():
            path = f"{prefix}.{_safe_path_key(key)}" if prefix else _safe_path_key(key)
            out.update(_typed_paths(child, path))
        return out
    if isinstance(value, list):
        path = f"{prefix}[]" if prefix else "[]"
        if not value:
            return {path: "arr"}
        merged: dict[str, str] = {}
        for item in value:
            child = _typed_paths(item, path)
            for child_path, child_type in child.items():
                prior = merged.get(child_path)
                if prior is None:
                    merged[child_path] = child_type
                elif prior != child_type:
                    merged[child_path] = "mixed"
        return merged if merged else {path: "arr"}
    if not prefix:
        return {}
    return {prefix: _json_type_name(value)}


def _diff_typed_paths(older: dict[str, str], newer: dict[str, str]) -> list[str]:
    """Return short human diffs between two typed path maps."""
    bits: list[str] = []
    for path in sorted(set(older) | set(newer)):
        if path not in older:
            bits.append(f"new field `{path}`")
        elif path not in newer:
            bits.append(f"removed `{path}`")
        elif older[path] != newer[path]:
            bits.append(f"`{path}` {older[path]} → {newer[path]}")
    return bits


def scan_response_drift(
    request_rows: list[tuple[int, str, str, str]],
) -> list[str]:
    """Compare typed JSON key-paths between the latest two successful JSON sends."""
    request_ids = [rid for rid, _n, _m, _u in request_rows]
    pair_ids = RequestHistoryService.latest_two_json_success_entry_ids(request_ids)
    if not pair_ids:
        return []
    name_by_id = {rid: name for rid, name, _m, _u in request_rows}
    lines: list[str] = []
    for rid, entry_ids in pair_ids.items():
        if len(entry_ids) < 2:
            continue
        newer_id, older_id = entry_ids[0], entry_ids[1]
        newer_entry = RequestHistoryService.get_entry(newer_id)
        older_entry = RequestHistoryService.get_entry(older_id)
        if newer_entry is None or older_entry is None:
            continue
        newer_detail = RequestHistoryService.entry_to_detail_snapshot(newer_entry)
        older_detail = RequestHistoryService.entry_to_detail_snapshot(older_entry)
        try:
            newer_json = json.loads(str(newer_detail.get("body") or ""))
            older_json = json.loads(str(older_detail.get("body") or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        diffs = _diff_typed_paths(_typed_paths(older_json), _typed_paths(newer_json))
        if not diffs:
            continue
        name = name_by_id.get(rid, str(rid))
        summary = "; ".join(diffs[:6])
        if len(diffs) > 6:
            summary += f" (+{len(diffs) - 6} more)"
        lines.append(f"- {_link('request', rid, name)}: {summary}")
    return lines
