"""Per-session record of whether a real workspace write happened during a turn.

The chat worker (background thread) observes write-tool results; the GUI thread
decides the final assistant text. This ledger carries that one fact between them
without widening the ``assistant_finished`` signal chain, mirroring the
module-level queue in :mod:`services.ai.chat.mutation.bridge`.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_sessions: set[str] = set()
_collection_ids: dict[str, set[int]] = {}


def record_workspace_write(session_id: str) -> None:
    """Mark that *session_id* performed a real workspace write this turn."""
    if not session_id:
        return
    with _lock:
        _sessions.add(session_id)


def take_workspace_write(session_id: str) -> bool:
    """Return whether *session_id* wrote this turn, clearing the mark."""
    if not session_id:
        return False
    with _lock:
        wrote = session_id in _sessions
        _sessions.discard(session_id)
        return wrote


def record_collection_ids(session_id: str, ids: set[int]) -> None:
    """Record collection ids this turn actually created, for link verification."""
    if not session_id or not ids:
        return
    with _lock:
        _collection_ids.setdefault(session_id, set()).update(ids)


def take_collection_ids(session_id: str) -> set[int]:
    """Return and clear the collection ids produced by *session_id* this turn."""
    if not session_id:
        return set()
    with _lock:
        return _collection_ids.pop(session_id, set())


def clear_workspace_writes(session_id: str) -> None:
    """Drop any stale marks for *session_id* (call at turn start)."""
    if not session_id:
        return
    with _lock:
        _sessions.discard(session_id)
        _collection_ids.pop(session_id, None)


__all__ = [
    "clear_workspace_writes",
    "record_collection_ids",
    "record_workspace_write",
    "take_collection_ids",
    "take_workspace_write",
]
