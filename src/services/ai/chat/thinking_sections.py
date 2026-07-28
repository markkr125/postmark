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
    return pack_thinking_sections([primary, post_subagent])


def pack_thinking_sections(sections: list[str]) -> str:
    """Serialize any number of chronological thinking blocks."""
    parts = [section.strip() for section in sections if section.strip()]
    return THINKING_PHASE_SEPARATOR.join(parts)


def unpack_thinking_phases(stored: str) -> tuple[str, str]:
    """Split persisted thinking into primary and post-subagent phases."""
    sections = unpack_thinking_sections(stored)
    if not sections:
        return "", ""
    return sections[0], THINKING_PHASE_SEPARATOR.join(sections[1:])


def unpack_thinking_sections(stored: str) -> list[str]:
    """Return all persisted thinking blocks in chronological order."""
    return [
        section.strip() for section in stored.split(THINKING_PHASE_SEPARATOR) if section.strip()
    ]


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
    "pack_thinking_sections",
    "resolve_thinking_for_persist",
    "unpack_thinking_phases",
    "unpack_thinking_sections",
]
