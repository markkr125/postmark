"""Postmark agent definitions for AI chat (extension point for custom agents)."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_AGENT_ID = "postmark-assistant"
DEFAULT_MAX_ITERATIONS = 1

_REGISTRY: dict[str, PostmarkAgentDef] = {}


@dataclass(frozen=True, slots=True)
class PostmarkAgentDef:
    """One Postmark-defined agent (prompt + tool names + loop cap)."""

    id: str
    display_name: str
    system_prompt: str | None
    tool_names: tuple[str, ...]
    include_default_tools: tuple[str, ...] = ("FinishTool", "ThinkTool")
    max_iteration_per_run: int | None = DEFAULT_MAX_ITERATIONS


def register_postmark_agent(defn: PostmarkAgentDef) -> None:
    """Register or replace a Postmark agent definition."""
    _REGISTRY[defn.id] = defn


def get_agent_def(agent_id: str) -> PostmarkAgentDef:
    """Return the agent definition for *agent_id*."""
    if agent_id not in _REGISTRY:
        msg = f"Unknown Postmark agent: {agent_id!r}"
        raise KeyError(msg)
    return _REGISTRY[agent_id]


def list_agent_defs() -> list[PostmarkAgentDef]:
    """Return all registered agent definitions."""
    return list(_REGISTRY.values())


def _register_defaults() -> None:
    """Ship the v1 default chat agent (no custom tools)."""
    register_postmark_agent(
        PostmarkAgentDef(
            id=DEFAULT_AGENT_ID,
            display_name="Postmark Assistant",
            system_prompt=(
                "You are Postmark's AI assistant. Help the user with API development, "
                "HTTP requests, scripting, and related tasks. Be concise and practical."
            ),
            tool_names=(),
            include_default_tools=(),
            max_iteration_per_run=DEFAULT_MAX_ITERATIONS,
        )
    )


_register_defaults()
