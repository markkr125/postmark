"""Session-keyed GUI workspace snapshot for AI chat tool reads."""

from __future__ import annotations

import threading
from typing import Any, NotRequired, TypedDict

_lock = threading.Lock()
_by_session: dict[str, dict[str, Any]] = {}


class TabSnapshot(TypedDict):
    """One open editor tab captured at chat run start."""

    index: int
    tab_type: str
    name: str
    request_id: int | None
    collection_id: int | None
    local_script_id: int | None
    is_dirty: bool
    is_active: bool
    is_deferred: NotRequired[bool]
    request_data: NotRequired[dict[str, Any] | None]
    local_script_content: NotRequired[str | None]
    local_script_language: NotRequired[str | None]


class WorkspaceSnapshot(TypedDict):
    """GUI-thread workspace state for one chat session."""

    active_tab_index: int
    active_collection_id: int | None
    current_env_id: int | None
    active_response: dict[str, Any] | None
    tabs: list[TabSnapshot]
    captured_at: NotRequired[str]


def set_workspace_snapshot(session_id: str, snapshot: dict[str, Any]) -> None:
    """Store *snapshot* for *session_id* (overwrites any prior value)."""
    if not session_id:
        return
    with _lock:
        _by_session[session_id] = snapshot


def get_workspace_snapshot(session_id: str) -> dict[str, Any] | None:
    """Return the snapshot for *session_id*, or ``None`` when unset."""
    if not session_id:
        return None
    with _lock:
        snap = _by_session.get(session_id)
    if snap is None:
        return None
    return dict(snap)


def clear_workspace_snapshot(session_id: str | None = None) -> None:
    """Drop snapshot entries for one session or all sessions (tests)."""
    with _lock:
        if session_id is None:
            _by_session.clear()
        else:
            _by_session.pop(session_id, None)
    clear_last_search_hits(session_id)


_last_search_hits_lock = threading.Lock()
_last_search_hits: dict[str, list[int]] = {}

# Sentinel for within_ids: use the session's last scope=search hit set.
WITHIN_IDS_LAST_SENTINEL = -1


def set_last_search_hits(session_id: str, request_ids: list[int]) -> None:
    """Store full request-id hit set from the latest scope=search for *session_id*."""
    if not session_id:
        return
    cleaned = [int(rid) for rid in request_ids if isinstance(rid, int) and rid > 0]
    with _last_search_hits_lock:
        if cleaned:
            _last_search_hits[session_id] = cleaned
        else:
            _last_search_hits.pop(session_id, None)


def get_last_search_hits(session_id: str) -> list[int] | None:
    """Return the last search hit ids for *session_id*, or ``None`` when unset."""
    if not session_id:
        return None
    with _last_search_hits_lock:
        hits = _last_search_hits.get(session_id)
    if hits is None:
        return None
    return list(hits)


def clear_last_search_hits(session_id: str | None = None) -> None:
    """Drop last-search hit entries for one session or all sessions (tests)."""
    with _last_search_hits_lock:
        if session_id is None:
            _last_search_hits.clear()
        else:
            _last_search_hits.pop(session_id, None)
