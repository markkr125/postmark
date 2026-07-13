"""Workspace health insights package."""

from __future__ import annotations

from typing import Any

__all__ = ["_SECTION_KEYS", "_render_insights"]


def __getattr__(name: str) -> Any:
    """Lazy-load renderer symbols to avoid circular imports with dependencies."""
    if name in {"_SECTION_KEYS", "_render_insights"}:
        from .renderer import _SECTION_KEYS, _render_insights

        return {
            "_SECTION_KEYS": _SECTION_KEYS,
            "_render_insights": _render_insights,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
