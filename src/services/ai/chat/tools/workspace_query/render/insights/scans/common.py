"""Shared tree walks and request-field helpers for insights scans."""

from __future__ import annotations

from typing import Any

import services.environment_service as environment_service_module
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.scripting.context import load_globals

from ....constants import _SEARCH_SCRIPT_SCAN_CAP
from ....helpers import _scripts_from_data

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
