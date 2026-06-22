"""Unit tests for chat mode profiles."""

from __future__ import annotations

from services.ai.chat.mode_profiles import resolve_chat_mode


def test_agent_mode_includes_task_tool() -> None:
    """Agent mode exposes wiki, task, and app_context tools."""
    mode = resolve_chat_mode("agent")
    assert "postmark_wiki_query" in mode.tool_names
    assert "postmark_app_context" in mode.tool_names
    assert any("task" in name for name in mode.tool_names)
    assert mode.inject_tier == "compact"
    assert mode.max_iteration_per_run == 5


def test_ask_mode_excludes_task_tool() -> None:
    """Ask mode does not include TaskToolSet."""
    mode = resolve_chat_mode("ask")
    assert "postmark_app_context" in mode.tool_names
    assert not any("task" in name for name in mode.tool_names)
    assert mode.inject_tier == "rich"


def test_plan_mode_preflight_tier() -> None:
    """Plan mode uses preflight inject tier and task tool."""
    mode = resolve_chat_mode("plan")
    assert mode.inject_tier == "preflight"
    assert any("task" in name for name in mode.tool_names)
