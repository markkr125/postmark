"""QSettings-backed cap for parallel delegate subagents per assistant turn."""

from __future__ import annotations

from PySide6.QtCore import QSettings

_ORG = "Postmark"
_APP = "Postmark"
_KEY_MAX_PARALLEL = "ai/max_parallel_subagents"

DEFAULT_MAX_PARALLEL_SUBAGENTS = 5
MIN_MAX_PARALLEL_SUBAGENTS = 1
MAX_MAX_PARALLEL_SUBAGENTS = 16


def _get_settings() -> QSettings:
    return QSettings(_ORG, _APP)


def _clamp(value: int) -> int:
    return max(MIN_MAX_PARALLEL_SUBAGENTS, min(MAX_MAX_PARALLEL_SUBAGENTS, value))


def max_parallel_subagents() -> int:
    """Return the hard cap for delegate fan-out from QSettings."""
    raw = _get_settings().value(_KEY_MAX_PARALLEL, DEFAULT_MAX_PARALLEL_SUBAGENTS)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return _clamp(raw)
    if isinstance(raw, str):
        try:
            return _clamp(int(raw.strip()))
        except ValueError:
            return DEFAULT_MAX_PARALLEL_SUBAGENTS
    return DEFAULT_MAX_PARALLEL_SUBAGENTS


def set_max_parallel_subagents(value: int) -> None:
    """Persist the parallel subagent cap."""
    _get_settings().setValue(_KEY_MAX_PARALLEL, _clamp(value))


__all__ = [
    "DEFAULT_MAX_PARALLEL_SUBAGENTS",
    "MAX_MAX_PARALLEL_SUBAGENTS",
    "MIN_MAX_PARALLEL_SUBAGENTS",
    "max_parallel_subagents",
    "set_max_parallel_subagents",
]
