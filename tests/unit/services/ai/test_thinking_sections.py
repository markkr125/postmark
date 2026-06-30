"""Unit tests for thinking phase pack/unpack helpers."""

from __future__ import annotations

from services.ai.chat.thinking_sections import (
    THINKING_PHASE_SEPARATOR,
    has_thinking_phase_separator,
    pack_thinking_phases,
    resolve_thinking_for_persist,
    unpack_thinking_phases,
)


def test_pack_roundtrip_two_phases() -> None:
    """Primary and post-subagent thinking survive pack/unpack."""
    primary = "Plan the wiki search."
    post = "Synthesize results into the answer."
    stored = pack_thinking_phases(primary, post)
    assert has_thinking_phase_separator(stored)
    assert unpack_thinking_phases(stored) == (primary, post)


def test_unpack_legacy_merged_thinking() -> None:
    """Messages without a separator keep all text in the primary phase."""
    merged = "First block.\n\nSecond block after subagents."
    assert unpack_thinking_phases(merged) == (merged, "")
    assert not has_thinking_phase_separator(merged)


def test_resolve_thinking_for_persist_prefers_packed_panel() -> None:
    """Persist prefers panel split over merged SDK text."""
    sdk = "A" * 100 + "B" * 200
    panel = pack_thinking_phases("A" * 100, "B" * 200)
    assert resolve_thinking_for_persist(sdk, panel) == panel


def test_pack_primary_only() -> None:
    """Single-phase thinking stores without a separator."""
    stored = pack_thinking_phases("only primary", "")
    assert stored == "only primary"
    assert THINKING_PHASE_SEPARATOR not in stored
