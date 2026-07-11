"""Tests for OpenHands subagent registration."""

from __future__ import annotations

from openhands.sdk.subagent import get_registered_agent_definitions


def test_register_postmark_subagents_registers_builtins() -> None:
    """Built-in wiki, workspace, and general-purpose agents are registered."""
    by_name = {d.name: d for d in get_registered_agent_definitions()}
    assert "wiki-researcher" in by_name
    assert "workspace-researcher" in by_name
    assert "general-purpose" in by_name
    assert "workspace" in by_name["workspace-researcher"].description.lower()
