"""Postmark agent definitions for AI chat (extension point for custom agents)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openhands.sdk import Agent

DEFAULT_AGENT_ID = "postmark-assistant"
DEFAULT_MAX_ITERATIONS = 1
WIKI_AGENT_MAX_ITERATIONS = 5
WORKSPACE_RESEARCHER_ID = "workspace_researcher"

_REGISTRY: dict[str, PostmarkAgentDef] = {}
_APP_CONTEXT_STACK_REGISTERED = False
_DEFAULTS_REGISTERED = False

_WORKSPACE_RESEARCHER_PROMPT = (
    "You are a read-only workspace researcher inside Postmark.\n"
    "Use only postmark_app_context. Start with focus=search, then drill into top hits "
    "with focus=request, local_script, collection, send_history, or saved_response.\n"
    "Output exactly:\n"
    "## Matches\n"
    "- [type] label (id=…) — one-line snippet; suffix (deleted) or (draft) when applicable\n"
    "## Notes\n"
    "Brief synthesis for the parent agent. No user-facing prose.\n"
    "Never modify data. Never call wiki or task tools."
)

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
    _ensure_defaults_registered()
    _REGISTRY[defn.id] = defn


def get_agent_def(agent_id: str) -> PostmarkAgentDef:
    """Return the agent definition for *agent_id*."""
    _ensure_defaults_registered()
    if agent_id not in _REGISTRY:
        msg = f"Unknown Postmark agent: {agent_id!r}"
        raise KeyError(msg)
    return _REGISTRY[agent_id]


def list_agent_defs() -> list[PostmarkAgentDef]:
    """Return all registered agent definitions."""
    _ensure_defaults_registered()
    return list(_REGISTRY.values())


def ensure_app_context_stack() -> None:
    """Register app context tool, TaskToolSet, and workspace_researcher once."""
    global _APP_CONTEXT_STACK_REGISTERED
    if _APP_CONTEXT_STACK_REGISTERED:
        return
    from openhands.sdk import Agent

    from services.ai.chat.tool_registry import resolve_tools
    from services.ai.chat.tools.app_context import register_app_context_tool

    register_app_context_tool()
    try:
        from openhands.tools.task import TaskToolSet
        from openhands.sdk.subagent import register_agent
        from openhands.sdk.subagent.schema import AgentDefinition

        _ = TaskToolSet.name

        def _create_workspace_researcher(llm: object) -> Agent:
            return Agent(
                llm=llm,  # type: ignore[arg-type]
                tools=resolve_tools(("postmark_app_context",)),
                system_prompt=_WORKSPACE_RESEARCHER_PROMPT,
                include_default_tools=[],
            )

        register_agent(
            name=WORKSPACE_RESEARCHER_ID,
            factory_func=_create_workspace_researcher,
            description=AgentDefinition(
                name=WORKSPACE_RESEARCHER_ID,
                description="Read-only workspace search sub-agent for Postmark.",
                tools=["postmark_app_context"],
                system_prompt=_WORKSPACE_RESEARCHER_PROMPT,
                max_iteration_per_run=6,
            ),
        )
    except ImportError:
        pass
    _APP_CONTEXT_STACK_REGISTERED = True


def _register_defaults() -> None:
    """Ship the default chat agent with the user wiki tool."""
    from services.ai.chat.tools.wiki_query import register_wiki_query_tool

    register_wiki_query_tool()
    _REGISTRY[DEFAULT_AGENT_ID] = PostmarkAgentDef(
        id=DEFAULT_AGENT_ID,
        display_name="Postmark Assistant",
        system_prompt=_WIKI_SYSTEM_PROMPT,
        tool_names=("postmark_wiki_query",),
        include_default_tools=(),
        max_iteration_per_run=WIKI_AGENT_MAX_ITERATIONS,
    )


def _ensure_defaults_registered() -> None:
    """Register built-in agents on first chat registry access."""
    global _DEFAULTS_REGISTERED
    if _DEFAULTS_REGISTERED:
        return
    _register_defaults()
    _DEFAULTS_REGISTERED = True
