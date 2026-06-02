"""Shared thresholds for async text formatting in the UI."""

from __future__ import annotations

# Above this size, skip a synchronous ``set_text`` before async Pretty format.
LARGE_INLINE_TEXT_CHARS = 32_768


def skip_inline_text_for_async_pretty(text: str, *, pretty: bool) -> bool:
    """Return True when pretty-print should run off-thread without a sync preview."""
    return pretty and len(text) > LARGE_INLINE_TEXT_CHARS
