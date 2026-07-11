"""Session-keyed GUI workspace snapshot for AI chat tool reads."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any, NotRequired, TypedDict

_lock = threading.Lock()
_by_session: dict[str, dict[str, Any]] = {}


def parent_session_id_from_persistence_dir(
    persistence_dir: str | Path | None,
) -> str | None:
    """Return the parent chat session id when *persistence_dir* is under ``subagents/``.

    OpenHands stores delegate/task child conversations at
    ``<ai_conversations>/<uuid.hex>/subagents/...``. Snapshot and search-hit
    keys use the canonical ``str(uuid.UUID(...))`` form of that hex folder.
    """
    if not persistence_dir:
        return None
    parts = Path(persistence_dir).parts
    try:
        idx = parts.index("subagents")
    except ValueError:
        return None
    if idx < 1:
        return None
    try:
        return str(uuid.UUID(parts[idx - 1]))
    except ValueError:
        return None


def resolve_workspace_session_id(
    conversation_id: str,
    *,
    persistence_dir: str | Path | None = None,
) -> str:
    """Resolve the session id used for workspace snapshots and search hits.

    Parent chat conversations use ``conversation.state.id`` directly. Subagent
    conversations use a child id; live scopes must look up the parent session
    snapshot captured at run start.
    """
    parent = parent_session_id_from_persistence_dir(persistence_dir)
    if parent:
        return parent
    return conversation_id or ""


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
