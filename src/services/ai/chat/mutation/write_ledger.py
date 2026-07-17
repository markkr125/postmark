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


def clear_workspace_writes(session_id: str) -> None:
    """Drop any stale mark for *session_id* (call at turn start)."""
    if not session_id:
        return
    with _lock:
        _sessions.discard(session_id)


__all__ = [
    "clear_workspace_writes",
    "record_workspace_write",
    "take_workspace_write",
]
