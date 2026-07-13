"""Auth-gap, secret-hygiene, local-deps, dead-request, and token-expiry scans."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.local_script_service import LocalScriptService
from services.scripting.context import load_globals
from services.scripting.local_dependency_diagnostics import (
    collect_direct_local_dependency_diagnostics,
)

from ....constants import _SEARCH_SCRIPT_SCAN_CAP
from ....helpers import _key_is_sensitive, _link
from ...search import (
    _count_local_scripts,
    _needle_looks_secret_like,
    _ordered_local_script_ids_for_scan,
)


def scan_auth_gaps(
    request_rows: list[tuple[int, str, str, str]],
    fields_by_id: dict[int, Any],
) -> list[str]:
    """Requests with no local auth and no inherited auth."""
    lines: list[str] = []
    for rid, name, _method, _url in request_rows:
        field = fields_by_id.get(rid)
        auth = field[6] if field is not None else None
        if isinstance(auth, dict) and auth:
            atype = str(auth.get("type", "")).lower()
            if atype and atype not in {"noauth", "none", ""}:
                continue
        inherited = CollectionService.get_request_auth_chain(rid)
        if isinstance(inherited, dict) and inherited:
            atype = str(inherited.get("type", "")).lower()
            if atype and atype not in {"noauth", "none", ""}:
                continue
        lines.append(f"- {_link('request', rid, name)} (no local or inherited auth)")
    return lines


def scan_secret_hygiene() -> list[str]:
    """Plain-typed or name/value-suspicious vars — keys and locations only."""
    lines: list[str] = []
    for env in EnvironmentService.fetch_all():
        eid = env.get("id")
        ename = str(env.get("name", ""))
        raw_values = env.get("values")
        values: list[Any] = raw_values if isinstance(raw_values, list) else []
        for item in values:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", ""))
            if not key:
                continue
            typ = str(item.get("type", "")).lower()
            if typ == "secret":
                continue
            val = str(item.get("value", ""))
            if _key_is_sensitive(key) or _needle_looks_secret_like(val):
                label = ename or str(eid)
                link = (
                    _link("environment", int(eid), label)
                    if isinstance(eid, int)
                    else f"environment {label}"
                )
                lines.append(f"- {link} · `{key}` (plain-typed / secret-shaped)")
    tree = CollectionService.fetch_all()
    scanned = 0

    def walk(ns: dict[str, Any]) -> None:
        nonlocal scanned
        for node in ns.values():
            if scanned >= _SEARCH_SCRIPT_SCAN_CAP:
                return
            if node.get("type") == "folder" and isinstance(node.get("id"), int):
                scanned += 1
                cid = int(node["id"])
                row = CollectionService.get_collection(cid)
                if row is not None and isinstance(row.variables, list):
                    for item in row.variables:
                        if not isinstance(item, dict):
                            continue
                        key = str(item.get("key", ""))
                        if not key or str(item.get("type", "")).lower() == "secret":
                            continue
                        val = str(item.get("value", ""))
                        if _key_is_sensitive(key) or _needle_looks_secret_like(val):
                            lines.append(
                                f"- {_link('collection', cid, str(row.name or cid))} · "
                                f"`{key}` (plain-typed / secret-shaped)"
                            )
                walk(node.get("children") or {})

    walk(tree)
    return lines


def scan_local_deps() -> list[str]:
    """Broken ``pm.require('local:…')`` diagnostics for local scripts."""
    tree = LocalScriptService.fetch_all()
    items = _ordered_local_script_ids_for_scan(tree, limit=_SEARCH_SCRIPT_SCAN_CAP)
    ids = [sid for sid, _path in items]
    path_by_id = dict(items)
    contents = {
        sid: (name, content)
        for sid, name, content in LocalScriptService.fetch_local_script_contents_for_ids(ids)
    }
    lines: list[str] = []
    for sid, _path in items:
        row = contents.get(sid)
        if row is None:
            continue
        name, content = row
        loaded = LocalScriptService.get_script_load_dict(sid)
        lang = str(loaded.get("language", "javascript")) if loaded else "javascript"
        bundle = collect_direct_local_dependency_diagnostics(str(content or ""), lang)
        msgs: list[str] = []
        for anchor in bundle.require_anchors:
            msgs.append(anchor.message)
        for diag in bundle.resolution_rows:
            msgs.append(getattr(diag, "message", str(diag)))
        if not msgs:
            continue
        display = path_by_id.get(sid, name)
        lines.append(f"- {_link('script', sid, display)} — {msgs[0]}")
    _ = _count_local_scripts(tree)
    return lines


def scan_dead_requests(
    request_rows: list[tuple[int, str, str, str]],
    *,
    history_ids: set[int],
    example_ids: set[int],
    linked_ids: set[int] | None = None,
) -> list[str]:
    """Flag requests with no send history and no saved examples."""
    lines: list[str] = []
    for rid, name, _method, _url in request_rows:
        if rid in history_ids or rid in example_ids:
            continue
        note = "no history, no examples"
        if linked_ids is not None and rid not in linked_ids:
            note += ", no {{var}} links"
            lines.append(f"- {_link('request', rid, name)} — likely abandoned ({note})")
        else:
            lines.append(f"- {_link('request', rid, name)} — never sent, no saved examples")
    return lines


def _jwt_exp(value: str) -> int | None:
    """Decode JWT ``exp`` claim when *value* looks like a three-segment JWT."""
    parts = value.split(".")
    if len(parts) != 3 or not all(parts):
        return None
    payload_b64 = parts[1]
    pad = "=" * (-len(payload_b64) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + pad)
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or "exp" not in payload:
        return None
    try:
        return int(payload["exp"])
    except (TypeError, ValueError):
        return None


def _format_relative_expiry(exp: int, *, now: datetime) -> str:
    """Return a short relative-expiry verdict for *exp* vs *now*."""
    now_ts = int(now.timestamp())
    delta = exp - now_ts
    abs_delta = abs(delta)
    if abs_delta < 60:
        unit, amount = "s", abs_delta
    elif abs_delta < 3600:
        unit, amount = "m", abs_delta // 60
    elif abs_delta < 86400:
        unit, amount = "h", abs_delta // 3600
    else:
        unit, amount = "d", abs_delta // 86400
    if delta < 0:
        return f"EXPIRED ~{amount}{unit} ago"
    return f"expires in ~{amount}{unit}"


def _iter_sensitive_var_rows() -> list[tuple[str, str, str]]:
    """Yield ``(link_markdown, key, value)`` for sensitive-keyed variables."""
    rows: list[tuple[str, str, str]] = []
    for env in EnvironmentService.fetch_all():
        eid = env.get("id")
        ename = str(env.get("name", ""))
        raw_values = env.get("values")
        values: list[Any] = raw_values if isinstance(raw_values, list) else []
        for item in values:
            if not isinstance(item, dict) or not item.get("enabled", True):
                continue
            key = str(item.get("key", ""))
            if not key or not _key_is_sensitive(key):
                continue
            label = ename or str(eid)
            link = (
                _link("environment", int(eid), label)
                if isinstance(eid, int)
                else f"environment {label}"
            )
            rows.append((link, key, str(item.get("value", ""))))
    globals_data = load_globals()
    for key, value in globals_data.items():
        if not key or not _key_is_sensitive(key):
            continue
        rows.append(("globals", key, str(value)))
    tree = CollectionService.fetch_all()
    scanned = 0

    def walk(ns: dict[str, Any]) -> None:
        nonlocal scanned
        for node in ns.values():
            if scanned >= _SEARCH_SCRIPT_SCAN_CAP:
                return
            if node.get("type") == "folder" and isinstance(node.get("id"), int):
                scanned += 1
                cid = int(node["id"])
                row = CollectionService.get_collection(cid)
                if row is not None and isinstance(row.variables, list):
                    for item in row.variables:
                        if not isinstance(item, dict) or not item.get("enabled", True):
                            continue
                        key = str(item.get("key", ""))
                        if not key or not _key_is_sensitive(key):
                            continue
                        link = _link("collection", cid, str(row.name or cid))
                        rows.append((link, key, str(item.get("value", ""))))
                walk(node.get("children") or {})

    walk(tree)
    return rows


def scan_token_expiry(*, now: datetime) -> tuple[list[str], int]:
    """JWT-shaped sensitive vars — relative expiry only; returns (lines, skipped)."""
    lines: list[str] = []
    skipped = 0
    for link, key, value in _iter_sensitive_var_rows():
        if not value or "{{" in value:
            continue
        exp = _jwt_exp(value)
        if exp is None:
            skipped += 1
            continue
        verdict = _format_relative_expiry(exp, now=now)
        lines.append(f"- {link} · `{key}` — {verdict}")
    return lines, skipped
