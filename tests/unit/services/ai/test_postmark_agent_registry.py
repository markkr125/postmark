"""Tests for Postmark agent and tool registries."""

from __future__ import annotations

from services.ai.chat.agent_registry import (
    DEFAULT_AGENT_ID,
    PostmarkAgentDef,
    get_agent_def,
    list_agent_defs,
    register_postmark_agent,
)
from services.ai.chat.tool_registry import resolve_tools


def test_default_agent_registered() -> None:
    """The default Postmark assistant agent is always present."""
    defn = get_agent_def(DEFAULT_AGENT_ID)
    assert defn.tool_names == ("postmark_wiki_query", "task_tool_set", "delegate")
    assert defn.include_default_tools == ()
    assert defn.system_prompt
    assert "postmark_wiki_query" in defn.system_prompt
    assert "delegate" in defn.system_prompt
    assert defn.max_iteration_per_run == 10
    assert DEFAULT_AGENT_ID in {d.id for d in list_agent_defs()}


def test_register_and_resolve_agent() -> None:
    """Custom agents can be registered and fetched."""
    custom = PostmarkAgentDef(
        id="test-agent",
        display_name="Test",
        system_prompt="test",
        tool_names=(),
    )
    register_postmark_agent(custom)
    assert get_agent_def("test-agent").display_name == "Test"


def test_resolve_tools_empty() -> None:
    """An empty tool name tuple resolves to an empty list."""
    assert resolve_tools(()) == []


def test_resolve_tools_returns_tool_specs() -> None:
    """Named tools resolve to OpenHands Tool specs."""
    tools = resolve_tools(("ExampleTool",))
    assert len(tools) == 1
    assert tools[0].name == "ExampleTool"
