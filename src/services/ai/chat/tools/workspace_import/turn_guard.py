"""Prevent duplicate imports of one source within a single chat turn."""

from __future__ import annotations

import hashlib
import json
import threading

_lock = threading.Lock()
_results_by_session: dict[str, dict[str, str]] = {}


def import_source_key(fields: dict[str, str]) -> str:
    """Return a stable, non-reversible key for one normalized import source."""
    encoded = json.dumps(fields, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def prior_import_result(session_id: str, source_key: str) -> str | None:
    """Return the successful result for this source in the current turn."""
    if not session_id or not source_key:
        return None
    with _lock:
        return _results_by_session.get(session_id, {}).get(source_key)


def record_import_result(session_id: str, source_key: str, result_text: str) -> None:
    """Remember a successful import result for duplicate-call suppression."""
    if not session_id or not source_key or not result_text:
        return
    with _lock:
        _results_by_session.setdefault(session_id, {})[source_key] = result_text


def clear_import_turn(session_id: str) -> None:
    """Clear duplicate-import state at the start of a user turn."""
    if not session_id:
        return
    with _lock:
        _results_by_session.pop(session_id, None)


__all__ = [
    "clear_import_turn",
    "import_source_key",
    "prior_import_result",
    "record_import_result",
]
