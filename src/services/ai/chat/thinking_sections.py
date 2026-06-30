"""Pack/unpack primary vs post-subagent thinking phases in one DB column."""

from __future__ import annotations

from services.ai.chat.response_text import pick_richest_text

# Invisible separator unlikely to appear in model output.
THINKING_PHASE_SEPARATOR = "\n\n\u2063POSTMARK_THINKING_PHASE\u2063\n\n"


def has_thinking_phase_separator(stored: str) -> bool:
    """Return whether *stored* contains a packed post-subagent thinking phase."""
    return THINKING_PHASE_SEPARATOR in stored


def pack_thinking_phases(primary: str, post_subagent: str) -> str:
    """Serialize two thinking blocks into one persisted string."""
    primary = primary.strip()
    post = post_subagent.strip()
    if primary and post:
        return f"{primary}{THINKING_PHASE_SEPARATOR}{post}"
    if post:
        return post
    return primary


def unpack_thinking_phases(stored: str) -> tuple[str, str]:
    """Split persisted thinking into primary and post-subagent phases."""
    if THINKING_PHASE_SEPARATOR not in stored:
        return stored.strip(), ""
    primary, post = stored.split(THINKING_PHASE_SEPARATOR, 1)
    return primary.strip(), post.strip()


def resolve_thinking_for_persist(sdk_thinking: str, panel_packed: str) -> str:
    """Prefer phase-packed panel thinking over merged SDK text when split exists."""
    panel = panel_packed.strip()
    if has_thinking_phase_separator(panel):
        return panel
    sdk = sdk_thinking.strip()
    if has_thinking_phase_separator(sdk):
        return sdk
    return pick_richest_text(sdk, panel)


__all__ = [
    "THINKING_PHASE_SEPARATOR",
    "has_thinking_phase_separator",
    "pack_thinking_phases",
    "resolve_thinking_for_persist",
    "unpack_thinking_phases",
]
