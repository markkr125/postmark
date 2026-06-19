"""QSettings-backed advisory limit for concurrent AI chat session runs."""

from __future__ import annotations

from PySide6.QtCore import QSettings

_ORG = "Postmark"
_APP = "Postmark"
_KEY_MAX_CONCURRENT = "ai/max_concurrent_runs"

DEFAULT_MAX_CONCURRENT_CHAT_RUNS = 10
MIN_MAX_CONCURRENT_CHAT_RUNS = 1
MAX_MAX_CONCURRENT_CHAT_RUNS = 64


def _get_settings() -> QSettings:
    return QSettings(_ORG, _APP)


def _clamp(value: int) -> int:
    return max(MIN_MAX_CONCURRENT_CHAT_RUNS, min(MAX_MAX_CONCURRENT_CHAT_RUNS, value))


def max_concurrent_chat_runs() -> int:
    """Return the advisory concurrent-run threshold from QSettings."""
    raw = _get_settings().value(_KEY_MAX_CONCURRENT, DEFAULT_MAX_CONCURRENT_CHAT_RUNS)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return _clamp(raw)
    if isinstance(raw, str):
        try:
            return _clamp(int(raw.strip()))
        except ValueError:
            return DEFAULT_MAX_CONCURRENT_CHAT_RUNS
    return DEFAULT_MAX_CONCURRENT_CHAT_RUNS


def set_max_concurrent_chat_runs(value: int) -> None:
    """Persist the advisory concurrent-run threshold."""
    _get_settings().setValue(_KEY_MAX_CONCURRENT, _clamp(value))


__all__ = [
    "DEFAULT_MAX_CONCURRENT_CHAT_RUNS",
    "MAX_MAX_CONCURRENT_CHAT_RUNS",
    "MIN_MAX_CONCURRENT_CHAT_RUNS",
    "max_concurrent_chat_runs",
    "set_max_concurrent_chat_runs",
]
