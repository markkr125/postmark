"""TypedDict schemas for the GUI app-context snapshot bridge."""

from __future__ import annotations

from typing import Literal, TypedDict

SNAPSHOT_FILENAME = "app_context_snapshot.json"
PREVIEW_MAX_CHARS = 8_000


class OpenTabEntry(TypedDict):
    """One open or deferred tab entry."""

    tab_type: Literal["request", "folder", "environments", "local_script"]
    request_id: int | None
    collection_id: int | None
    local_script_id: int | None
    label: str
    is_dirty: bool
    is_preview: bool


class ActiveTabSnapshot(TypedDict):
    """Active tab metadata and editor preview."""

    tab_type: str
    request_id: int | None
    collection_id: int | None
    local_script_id: int | None
    title: str
    method: str | None
    is_dirty: bool
    is_preview: bool
    draft_name: str | None
    active_sub_tab: str | None
    editor_preview: str


class TreeSelectionSnapshot(TypedDict):
    """Sidebar tree selection when it differs from the active tab."""

    kind: Literal["collection", "local_script", "none"]
    collection_id: int | None
    local_script_id: int | None
    label: str | None


class EnvironmentSnapshot(TypedDict):
    """Selected environment summary."""

    id: int | None
    name: str | None


class AppContextSnapshot(TypedDict):
    """Full snapshot written before each chat send."""

    captured_at: str
    send_mode: Literal["agent", "ask", "plan"]
    active_tab: ActiveTabSnapshot
    open_tabs: list[OpenTabEntry]
    deferred_tabs: list[OpenTabEntry]
    environment: EnvironmentSnapshot
    tree_selection: TreeSelectionSnapshot


def truncate_preview(text: str, *, limit: int = PREVIEW_MAX_CHARS) -> str:
    """Bound preview text length with a truncation marker."""
    if len(text) <= limit:
        return text
    return text[: limit - len("\n…[truncated]")] + "\n…[truncated]"
