"""Per-turn tool name resolution for Ask / Plan / Agent modes."""

from __future__ import annotations

from services.ai.chat.agent_registry import get_agent_def

MUTATE_TOOL = "postmark_workspace_mutate"
EXECUTE_TOOL = "postmark_workspace_execute"
_WRITE_TOOLS = frozenset({MUTATE_TOOL, EXECUTE_TOOL})

MUTATING_MAX_ITERATIONS = 15


def tools_for_turn(
    agent_id: str,
    *,
    send_mode: str | None,
) -> tuple[str, ...]:
    """Return tool names for this turn based on composer mode.

    Ask and Plan are always read-only. Agent always receives mutate/execute;
    write safety is Approve / auto-approve, not a Settings master switch.
    """
    def_ = get_agent_def(agent_id)
    names = tuple(def_.tool_names)
    mode = (send_mode or "ask").strip().lower()
    if mode == "agent":
        return names
    return tuple(n for n in names if n not in _WRITE_TOOLS)


def max_iterations_for_turn(
    agent_id: str,
    *,
    send_mode: str | None,
) -> int:
    """Return ``max_iteration_per_run`` for this turn."""
    def_ = get_agent_def(agent_id)
    default = max(def_.max_iteration_per_run or 1, 3)
    mode = (send_mode or "ask").strip().lower()
    if mode == "agent":
        return max(default, MUTATING_MAX_ITERATIONS)
    return default


__all__ = [
    "EXECUTE_TOOL",
    "MUTATE_TOOL",
    "MUTATING_MAX_ITERATIONS",
    "max_iterations_for_turn",
    "tools_for_turn",
]
