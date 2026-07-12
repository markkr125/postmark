"""Workspace health scan helpers for scope=insights."""

from __future__ import annotations

import re
from typing import Any

import services.environment_service as environment_service_module
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.local_script_service import LocalScriptService
from services.request_history_service import RequestHistoryService
from services.script_version_service import ScriptVersionService
from services.scripting.context import load_globals
from services.scripting.local_dependency_diagnostics import (
    collect_direct_local_dependency_diagnostics,
)

from ...constants import _SEARCH_SCRIPT_SCAN_CAP
from ...helpers import (
    _key_is_sensitive,
    _link,
    _script_assigned_variable_keys,
    _scripts_from_data,
    _truncate_url,
)
from ..search import (
    _count_local_scripts,
    _needle_looks_secret_like,
    _ordered_local_script_ids_for_scan,
)

_VAR_FIND_RE = environment_service_module._VAR_PATTERN


def _walk_request_nodes(
    nodes: dict[str, Any],
    *,
    within: set[int] | None,
    limit: int,
) -> list[tuple[int, str, str, str]]:
    """DFS collect ``(id, name, method, url)`` up to *limit*, optionally filtered."""
    out: list[tuple[int, str, str, str]] = []

    def walk(ns: dict[str, Any]) -> None:
        for node in ns.values():
            if len(out) >= limit:
                return
            if node.get("type") == "folder":
                walk(node.get("children") or {})
            elif node.get("type") == "request" and isinstance(node.get("id"), int):
                rid = int(node["id"])
                if within is not None and rid not in within:
                    continue
                out.append(
                    (
                        rid,
                        str(node.get("name", "")),
                        str(node.get("method", "GET")).upper(),
                        str(node.get("url") or ""),
                    )
                )

    walk(nodes)
    return out


def _collect_dup_groups(
    nodes: dict[str, Any],
    *,
    within: set[int] | None,
) -> dict[tuple[str, str], list[tuple[int, str, str]]]:
    """Group non-empty URLs by method + normalized URL (exhaustive)."""
    groups: dict[tuple[str, str], list[tuple[int, str, str]]] = {}

    def walk(ns: dict[str, Any]) -> None:
        for node in ns.values():
            if node.get("type") == "folder":
                walk(node.get("children") or {})
            elif node.get("type") == "request" and isinstance(node.get("id"), int):
                rid = int(node["id"])
                if within is not None and rid not in within:
                    continue
                url_raw = str(node.get("url") or "").strip()
                if not url_raw:
                    continue
                method = str(node.get("method", "GET")).upper()
                key = (method, url_raw.casefold().rstrip("/"))
                groups.setdefault(key, []).append((rid, str(node.get("name", "")), url_raw))

    walk(nodes)
    return groups


def _extract_var_refs(*texts: str) -> set[str]:
    """Return exact ``{{key}}`` spellings found in *texts*."""
    keys: set[str] = set()
    for text in texts:
        if "{{" not in text:
            continue
        for match in _VAR_FIND_RE.finditer(text):
            keys.add(match.group(1).strip())
    return keys


def _request_field_texts(
    rid: int,
    url: str,
    fields_by_id: dict[int, Any],
    scripts_by_id: dict[int, Any],
) -> tuple[list[str], str | None, str | None]:
    """Build haystack texts plus pre/test script sources for one request."""
    texts: list[str] = [url]
    pre: str | None = None
    test: str | None = None
    field = fields_by_id.get(rid)
    if field is not None:
        (
            _name,
            body,
            _mode,
            _opts,
            _desc,
            headers,
            auth,
            params,
        ) = field
        if body:
            texts.append(str(body))
        if isinstance(headers, list):
            for row in headers:
                if isinstance(row, dict):
                    texts.append(str(row.get("key", "")))
                    texts.append(str(row.get("value", "")))
        if isinstance(params, list):
            for row in params:
                if isinstance(row, dict):
                    texts.append(str(row.get("key", "")))
                    texts.append(str(row.get("value", "")))
        if isinstance(auth, dict):
            texts.append(str(auth))
    script_row = scripts_by_id.get(rid)
    if script_row is not None:
        norm = _scripts_from_data({"scripts": script_row[1], "events": script_row[2]})
        pre = norm.get("pre_request") or None
        test = norm.get("test") or None
        if pre:
            texts.append(pre)
        if test:
            texts.append(test)
    return texts, pre, test


def _defined_keys() -> dict[str, list[str]]:
    """Map exact key spelling → location labels (no values)."""
    locs: dict[str, list[str]] = {}

    def add(key: str, label: str) -> None:
        if not key:
            return
        locs.setdefault(key, []).append(label)

    for gkey in load_globals():
        add(str(gkey), "globals")
    for env in EnvironmentService.fetch_all():
        eid = env.get("id")
        ename = str(env.get("name", ""))
        raw_values = env.get("values")
        values: list[Any] = raw_values if isinstance(raw_values, list) else []
        for item in values:
            if not isinstance(item, dict):
                continue
            add(str(item.get("key", "")), f"environment {ename or eid}")
    tree = CollectionService.fetch_all()
    folder_ids: list[int] = []

    def walk(ns: dict[str, Any]) -> None:
        for node in ns.values():
            if len(folder_ids) >= _SEARCH_SCRIPT_SCAN_CAP:
                return
            if node.get("type") == "folder" and isinstance(node.get("id"), int):
                folder_ids.append(int(node["id"]))
                walk(node.get("children") or {})

    walk(tree)
    for cid in folder_ids:
        row = CollectionService.get_collection(cid)
        if row is None or not isinstance(row.variables, list):
            continue
        for item in row.variables:
            if not isinstance(item, dict):
                continue
            add(str(item.get("key", "")), f"collection {row.name or cid}")
    return locs


def _active_disabled_keys(env_id: int | None) -> set[str]:
    """Exact keys disabled in the active environment."""
    if env_id is None:
        return set()
    env = EnvironmentService.get_environment(env_id)
    if env is None or not isinstance(env.values, list):
        return set()
    out: set[str] = set()
    for item in env.values:
        if isinstance(item, dict) and item.get("enabled") is False:
            key = str(item.get("key", ""))
            if key:
                out.add(key)
    return out


def scan_missing_tests(
    request_rows: list[tuple[int, str, str, str]],
    scripts_by_id: dict[int, Any],
    assertion_counts: dict[int, tuple[int, int]],
) -> list[str]:
    """Rows for requests with neither test script nor enabled assertions."""
    lines: list[str] = []
    for rid, name, _method, _url in request_rows:
        row = scripts_by_id.get(rid)
        scripts = _scripts_from_data(
            {"scripts": row[1], "events": row[2]} if row is not None else None
        )
        _total, enabled = assertion_counts.get(rid, (0, 0))
        if scripts.get("test") or enabled > 0:
            continue
        lines.append(f"- {_link('request', rid, name)} (no test script or assertions)")
    return lines


def scan_duplicates(
    dup_groups: dict[tuple[str, str], list[tuple[int, str, str]]],
) -> list[str]:
    """Rows for duplicate method+URL groups."""
    lines: list[str] = []
    for (method, _key), group in sorted(dup_groups.items(), key=lambda kv: (-len(kv[1]), kv[0][0])):
        if len(group) < 2:
            continue
        names = ", ".join(_link("request", rid, name) for rid, name, _raw in group)
        lines.append(f"- {method} {_truncate_url(group[0][2])}: {names}")
    return lines


def scan_variable_issues(
    request_rows: list[tuple[int, str, str, str]],
    *,
    env_id: int | None,
    fields_by_id: dict[int, Any],
    scripts_by_id: dict[int, Any],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return unresolved, unused, case-mismatch, and disabled-ref rows."""
    defined = _defined_keys()
    defined_cf: dict[str, list[str]] = {}
    for key in defined:
        defined_cf.setdefault(key.casefold(), []).append(key)
    disabled = _active_disabled_keys(env_id)
    used_exact: set[str] = set()
    assigned: set[str] = set()
    unresolved_lines: list[str] = []
    mismatch_lines: list[str] = []
    disabled_lines: list[str] = []

    for rid, name, _method, url in request_rows:
        texts, pre, test = _request_field_texts(rid, url, fields_by_id, scripts_by_id)
        assigned |= _script_assigned_variable_keys(pre, test)
        refs = _extract_var_refs(*texts)
        used_exact |= refs
        variables = EnvironmentService.build_combined_variable_map(env_id, rid)
        unresolved_keys: list[str] = []
        for key in sorted(refs):
            token = "{{" + key + "}}"
            substituted = EnvironmentService.substitute(token, variables)
            if substituted == token and key not in assigned:
                unresolved_keys.append(key)
            if key not in defined and key.casefold() in defined_cf:
                exact = defined_cf[key.casefold()][0]
                mismatch_lines.append(
                    f"- {_link('request', rid, name)} — `{{{{{key}}}}}` (defined as `{exact}`)"
                )
            if key in disabled:
                disabled_lines.append(
                    f"- {_link('request', rid, name)} — `{{{{{key}}}}}` "
                    "(disabled in active environment)"
                )
        if unresolved_keys:
            unresolved_lines.append(
                f"- {_link('request', rid, name)} — "
                + ", ".join(f"`{{{{{k}}}}}`" for k in unresolved_keys)
            )

    unused_lines: list[str] = []
    for key, labels in sorted(defined.items(), key=lambda kv: kv[0].casefold()):
        if key in used_exact or key in assigned:
            continue
        unused_lines.append(f"- `{key}` ({', '.join(labels[:3])})")
    return unresolved_lines, unused_lines, mismatch_lines, disabled_lines


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


def scan_script_regressions(
    request_rows: list[tuple[int, str, str, str]],
    scripts_by_id: dict[int, Any],
) -> list[str]:
    """Test script previously had content / pm.test but current is empty."""
    lines: list[str] = []
    for rid, name, _method, _url in request_rows:
        row = scripts_by_id.get(rid)
        current = ""
        if row is not None:
            norm = _scripts_from_data({"scripts": row[1], "events": row[2]})
            current = str(norm.get("test") or "")
        versions = ScriptVersionService.list_versions(request_id=rid, script_type="test", limit=2)
        if len(versions) < 2:
            continue
        previous = str(versions[1].get("content") or "")
        if not previous.strip():
            continue
        prev_has_test = bool(re.search(r"\bpm\.test\b", previous)) or bool(previous.strip())
        curr_has_test = bool(re.search(r"\bpm\.test\b", current)) or bool(current.strip())
        if prev_has_test and not curr_has_test:
            lines.append(f"- {_link('request', rid, name)} — test script emptied vs prior version")
    return lines
