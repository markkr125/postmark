"""Postmark agent definitions for AI chat (extension point for custom agents)."""

from __future__ import annotations

from dataclasses import dataclass

from services.ai.chat.tools.wiki_query import register_wiki_query_tool

DEFAULT_AGENT_ID = "postmark-assistant"
DEFAULT_MAX_ITERATIONS = 1
WIKI_AGENT_MAX_ITERATIONS = 5

_REGISTRY: dict[str, PostmarkAgentDef] = {}

_WIKI_SYSTEM_PROMPT = (
    "You are the AI assistant inside Postmark, a native desktop API client (similar to "
    "Postman) for building and testing HTTP requests, organized into collections and "
    "environments, with pre-request and test scripting in JavaScript, TypeScript, and "
    "Python. This is the Postmark API client application — NOT the Postmark email-delivery "
    "service; do not confuse the two and do not speculate about what the app is. "
    "Help the user with API development, HTTP requests, scripting, and using the app. "
    "Be concise and practical. "
    "For questions about how Postmark works (UI, workflows, settings, scripting, debugging), "
    "call postmark_wiki_query with short keywords before answering — do not guess exact "
    "file paths, and do not invent menu items or shortcuts. "
    "When writing pre-request or test scripts, base them on the wiki's scripting/API pages; "
    "use only documented pm/postman members and the sandbox global helpers listed in the "
    "quickref (e.g. datetime_now(), uuid_v4(), require() — called WITHOUT a pm. prefix); "
    "never use raw fetch, axios, or Node-only APIs; prefer pm.sendRequest for chaining. "
    "Once the wiki returns relevant pages, trust them and answer directly: give the steps and "
    "a short example. Keep reasoning brief — decide in one pass and do not re-verify the same "
    "point repeatedly or second-guess settled facts."
)


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
    """Ship the default chat agent with the user wiki tool."""
    register_wiki_query_tool()
    register_postmark_agent(
        PostmarkAgentDef(
            id=DEFAULT_AGENT_ID,
            display_name="Postmark Assistant",
            system_prompt=_WIKI_SYSTEM_PROMPT,
            tool_names=("postmark_wiki_query",),
            include_default_tools=(),
            max_iteration_per_run=WIKI_AGENT_MAX_ITERATIONS,
        )
    )


_register_defaults()
