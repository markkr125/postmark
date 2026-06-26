"""Tests for Postmark delegate tool registration."""

from __future__ import annotations

from services.ai.chat.subagent_limits import set_max_parallel_subagents
from services.ai.chat.tools.delegate_tool import (
    DELEGATE_TOOL_NAME,
    PostmarkDelegateTool,
    register_postmark_delegate_tool,
)
from services.ai.chat.tool_registry import resolve_tools


def test_register_delegate_tool() -> None:
    """Delegate tool resolves through the Postmark tool registry."""
    register_postmark_delegate_tool()
    tools = resolve_tools((DELEGATE_TOOL_NAME,))
    assert len(tools) == 1
    assert tools[0].name == DELEGATE_TOOL_NAME


def test_delegate_tool_create_uses_parallel_limit() -> None:
    """DelegateExecutor receives max_children from QSettings."""
    set_max_parallel_subagents(4)
    created = PostmarkDelegateTool.create(conv_state=None)
    assert len(created) == 1
    assert created[0].name == DELEGATE_TOOL_NAME
    executor = created[0].executor
    assert getattr(executor, "_max_children", None) == 4


def test_delegate_schema_tasks_values_are_plain_strings() -> None:
    """Delegate tool schema must not leave task value shape ambiguous."""
    tool = PostmarkDelegateTool.create(conv_state=None)[0]
    schema = tool.to_openai_tool(add_security_risk_prediction=True)
    params = schema["function"]["parameters"]
    tasks = params["properties"]["tasks"]

    assert tasks["additionalProperties"] == {"type": "string"}
    assert "Never use nested" in tasks["description"]
    assert params["properties"]["security_risk"]["description"] == (
        "Use LOW for Postmark wiki lookup delegation."
    )
