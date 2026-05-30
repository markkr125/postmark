"""Refcount shared LSP document URIs for local script tabs."""

from __future__ import annotations

from threading import Lock

_lock = Lock()
_counts: dict[str, int] = {}


def acquire_uri(uri: str) -> bool:
    """Increment *uri* refcount; return True when this is the first owner (``didOpen``)."""
    with _lock:
        n = _counts.get(uri, 0) + 1
        _counts[uri] = n
        return n == 1


def release_uri(uri: str) -> bool:
    """Decrement *uri* refcount; return True when the last owner released (``didClose``)."""
    with _lock:
        n = _counts.get(uri, 0) - 1
        if n <= 0:
            _counts.pop(uri, None)
            return True
        _counts[uri] = n
        return False
