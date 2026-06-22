"""Composer mode profiles for Agent / Ask / Plan chat runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

InjectTier = Literal["compact", "rich", "preflight"]

TASK_TOOL_SET_NAME = "task_tool_set"

_AGENT_SUFFIX = (
    " You can read the user's current editor via postmark_app_context. "
    'For cross-workspace search, call task(subagent_type="workspace_researcher", …) '
    "— do not use focus=search on postmark_app_context."
)
_ASK_SUFFIX = (
    " Answer from the injected app context and postmark_app_context when needed. "
    "You cannot delegate to sub-agents; use postmark_app_context for the active "
    "request, script, or environment only."
)
_PLAN_SUFFIX = (
    " Before proposing steps, use postmark_app_context (preflight context is injected) "
    "and task(workspace_researcher) when you need to search the workspace. "
    "Output a numbered plan; do not execute changes."
)


@dataclass(frozen=True, slots=True)
class ChatModeProfile:
    """Resolved tool/prompt settings for one composer mode."""

    send_mode: str
    tool_names: tuple[str, ...]
    system_prompt_suffix: str
    max_iteration_per_run: int
    include_default_tools: tuple[str, ...]
    inject_tier: InjectTier


def _task_tool_name() -> str:
    """Return the OpenHands TaskToolSet registered name."""
    return TASK_TOOL_SET_NAME


def resolve_chat_mode(send_mode: str | None) -> ChatModeProfile:
    """Map composer pill mode to tools, prompt suffix, and inject tier."""
    mode = (send_mode or "agent").strip().lower()
    task_name = _task_tool_name()
    if mode == "ask":
        return ChatModeProfile(
            send_mode="ask",
            tool_names=("postmark_wiki_query", "postmark_app_context"),
            system_prompt_suffix=_ASK_SUFFIX,
            max_iteration_per_run=2,
            include_default_tools=(),
            inject_tier="rich",
        )
    if mode == "plan":
        return ChatModeProfile(
            send_mode="plan",
            tool_names=("postmark_wiki_query", task_name, "postmark_app_context"),
            system_prompt_suffix=_PLAN_SUFFIX,
            max_iteration_per_run=5,
            include_default_tools=(),
            inject_tier="preflight",
        )
    return ChatModeProfile(
        send_mode="agent",
        tool_names=("postmark_wiki_query", task_name, "postmark_app_context"),
        system_prompt_suffix=_AGENT_SUFFIX,
        max_iteration_per_run=5,
        include_default_tools=(),
        inject_tier="compact",
    )
