"""Tests for OpenHands subagent registration."""

from __future__ import annotations

from openhands.sdk.subagent import get_registered_agent_definitions


def test_register_postmark_subagents_registers_builtins() -> None:
    """Built-in wiki-researcher and general-purpose are registered at startup."""
    names = {d.name for d in get_registered_agent_definitions()}
    assert "wiki-researcher" in names
    assert "general-purpose" in names
