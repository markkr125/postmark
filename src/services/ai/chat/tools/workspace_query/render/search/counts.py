"""Tree counting and ordered-id collectors for workspace search."""

from __future__ import annotations

from typing import Any

from ...constants import _SEARCH_SCRIPT_SCAN_CAP


def _count_tree_requests(nodes: dict[str, Any]) -> int:
    """Count all request nodes in a collection tree."""
    count = 0
    for node in nodes.values():
        if node.get("type") == "folder":
            count += _count_tree_requests(node.get("children") or {})
        elif node.get("type") == "request":
            count += 1
    return count


def _count_tree_folders(nodes: dict[str, Any]) -> int:
    """Count all folder nodes in a collection tree."""
    count = 0
    for node in nodes.values():
        if node.get("type") == "folder":
            count += 1
            count += _count_tree_folders(node.get("children") or {})
    return count


def _count_local_scripts(nodes: dict[str, Any]) -> int:
    """Count all script nodes in the local-script tree."""
    count = 0
    for node in nodes.values():
        if node.get("type") == "folder":
            count += _count_local_scripts(node.get("children") or {})
        elif node.get("type") == "script":
            count += 1
    return count


def _ordered_request_ids_for_script_scan(
    nodes: dict[str, Any],
    *,
    limit: int = _SEARCH_SCRIPT_SCAN_CAP,
) -> list[int]:
    """DFS-collect request ids in tree order, capped for script-content scanning."""
    ids: list[int] = []

    def walk(ns: dict[str, Any]) -> None:
        for node in ns.values():
            if len(ids) >= limit:
                return
            if node.get("type") == "folder":
                walk(node.get("children") or {})
            elif node.get("type") == "request" and isinstance(node.get("id"), int):
                ids.append(node["id"])
                if len(ids) >= limit:
                    return

    walk(nodes)
    return ids


def _ordered_collection_ids_for_script_scan(
    nodes: dict[str, Any],
    *,
    limit: int = _SEARCH_SCRIPT_SCAN_CAP,
) -> list[int]:
    """DFS-collect folder ids in tree order, capped for folder-script scanning."""
    ids: list[int] = []

    def walk(ns: dict[str, Any]) -> None:
        for node in ns.values():
            if len(ids) >= limit:
                return
            if node.get("type") == "folder" and isinstance(node.get("id"), int):
                ids.append(node["id"])
                walk(node.get("children") or {})
                if len(ids) >= limit:
                    return

    walk(nodes)
    return ids


def _ordered_local_script_ids_for_scan(
    nodes: dict[str, Any],
    *,
    limit: int = _SEARCH_SCRIPT_SCAN_CAP,
) -> list[tuple[int, str]]:
    """DFS-collect local script (id, path) pairs in tree order, capped for scanning."""
    items: list[tuple[int, str]] = []

    def walk(ns: dict[str, Any], prefix: str = "") -> None:
        for node in ns.values():
            if len(items) >= limit:
                return
            name = str(node.get("name", ""))
            path = f"{prefix}/{name}" if prefix else name
            if node.get("type") == "folder":
                walk(node.get("children") or {}, path)
            elif node.get("type") == "script" and isinstance(node.get("id"), int):
                items.append((node["id"], path))
                if len(items) >= limit:
                    return

    walk(nodes)
    return items
