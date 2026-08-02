"""Classify persisted session tab entries for restore batching."""

from __future__ import annotations

from typing import Any, Literal

RestoreKind = Literal[
    "deferred_request",
    "deferred_local_script",
    "deferred_folder",
    "deferred_old_request",
    "eager_draft",
    "eager_environments",
    "skip",
]


def classify_restore_entry(entry: dict[str, Any]) -> RestoreKind:
    """Return how *entry* should be restored (cheap chip vs eager widget build).

    Cheap (batched, no inter-tab delay): deferred chips for requests, local
    scripts, and folders when enough metadata is present (or filled by prefetch).
    Eager: drafts (full editor snapshot) and environments (single materialized tab).
    """
    tab_type = entry.get("type")
    if tab_type == "draft":
        return "eager_draft"
    if tab_type == "environments":
        return "eager_environments"
    if tab_type == "folder":
        item_id = entry.get("id")
        if isinstance(item_id, int):
            return "deferred_folder"
        return "skip"
    if tab_type == "local_script":
        item_id = entry.get("id")
        if isinstance(item_id, int):
            return "deferred_local_script"
        return "skip"
    if tab_type == "request":
        item_id = entry.get("id")
        if not isinstance(item_id, int):
            return "skip"
        method = entry.get("method")
        name = entry.get("name")
        if isinstance(method, str) and isinstance(name, str) and method and name:
            return "deferred_request"
        return "deferred_old_request"
    return "skip"


def partition_restore_queue(
    queue: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split *queue* into deferred (chip) entries and eager (draft) entries.

    Environments and folders stay in the deferred list — they are cheap chips.
    Drafts are returned separately for a single post-chip eager batch.
    """
    deferred: list[dict[str, Any]] = []
    eager_drafts: list[dict[str, Any]] = []
    for entry in queue:
        kind = classify_restore_entry(entry)
        if kind == "eager_draft":
            eager_drafts.append(entry)
        elif kind != "skip":
            deferred.append(entry)
    return deferred, eager_drafts


def collect_prefetch_request_ids(queue: list[dict[str, Any]]) -> list[int]:
    """Return unique request ids from session entries (including old-format rows)."""
    seen: set[int] = set()
    ids: list[int] = []
    for entry in queue:
        if entry.get("type") != "request":
            continue
        item_id = entry.get("id")
        if isinstance(item_id, int) and item_id not in seen:
            seen.add(item_id)
            ids.append(item_id)
    return ids


def collect_prefetch_local_script_ids(queue: list[dict[str, Any]]) -> list[int]:
    """Return unique local script ids from session entries."""
    seen: set[int] = set()
    ids: list[int] = []
    for entry in queue:
        if entry.get("type") != "local_script":
            continue
        item_id = entry.get("id")
        if isinstance(item_id, int) and item_id not in seen:
            seen.add(item_id)
            ids.append(item_id)
    return ids


def collect_prefetch_folder_ids(queue: list[dict[str, Any]]) -> list[int]:
    """Return unique folder collection ids missing a persisted display name."""
    seen: set[int] = set()
    ids: list[int] = []
    for entry in queue:
        if entry.get("type") != "folder":
            continue
        item_id = entry.get("id")
        name = entry.get("name")
        if not isinstance(item_id, int) or item_id in seen:
            continue
        if isinstance(name, str) and name.strip():
            continue
        seen.add(item_id)
        ids.append(item_id)
    return ids


__all__ = [
    "RestoreKind",
    "classify_restore_entry",
    "collect_prefetch_folder_ids",
    "collect_prefetch_local_script_ids",
    "collect_prefetch_request_ids",
    "partition_restore_queue",
]
