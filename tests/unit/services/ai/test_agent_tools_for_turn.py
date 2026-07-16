"""Tests for tools_for_turn / max_iterations_for_turn mode matrix."""

from __future__ import annotations

from services.ai.chat.agent_registry import DEFAULT_AGENT_ID
from services.ai.chat.agent_tools import (
    EXECUTE_TOOL,
    MUTATE_TOOL,
    MUTATING_MAX_ITERATIONS,
    max_iterations_for_turn,
    tools_for_turn,
)


class TestToolsForTurn:
    """Ask/Plan stay read-only; Agent always gets write tools."""

    def test_ask_plan_exclude_write_tools(self) -> None:
        """Ask and Plan never expose mutate/execute."""
        for mode in ("ask", "plan", "ASK", "Plan"):
            names = tools_for_turn(DEFAULT_AGENT_ID, send_mode=mode)
            assert MUTATE_TOOL not in names
            assert EXECUTE_TOOL not in names
            assert "postmark_wiki_query" in names
            assert "postmark_workspace_query" in names

    def test_agent_always_includes_write_tools(self) -> None:
        """Agent mode always receives mutate/execute."""
        names = tools_for_turn(DEFAULT_AGENT_ID, send_mode="agent")
        assert MUTATE_TOOL in names
        assert EXECUTE_TOOL in names

    def test_default_mode_is_ask_readonly(self) -> None:
        """Missing/None send_mode behaves like ask."""
        names = tools_for_turn(DEFAULT_AGENT_ID, send_mode=None)
        assert MUTATE_TOOL not in names
        assert EXECUTE_TOOL not in names


class TestMaxIterationsForTurn:
    """Agent turns raise the iteration budget."""

    def test_agent_raises_budget(self) -> None:
        """Agent mode uses at least MUTATING_MAX_ITERATIONS."""
        n = max_iterations_for_turn(DEFAULT_AGENT_ID, send_mode="agent")
        assert n >= MUTATING_MAX_ITERATIONS

    def test_ask_keeps_default_budget(self) -> None:
        """Ask mode keeps a lower budget than Agent mutating turns."""
        ask_n = max_iterations_for_turn(DEFAULT_AGENT_ID, send_mode="ask")
        agent_n = max_iterations_for_turn(DEFAULT_AGENT_ID, send_mode="agent")
        assert ask_n >= 3
        assert agent_n >= ask_n
        assert agent_n >= MUTATING_MAX_ITERATIONS
