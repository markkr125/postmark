"""Register OpenHands subagent types for Postmark chat delegation."""

from __future__ import annotations

from database.data_paths import project_root
from openhands.sdk import Agent, AgentContext, Tool
from openhands.sdk.subagent import register_agent, register_file_agents

_WIKI_RESEARCHER_SUFFIX = (
    "You are a Postmark app knowledge specialist. Search the user wiki with "
    "postmark_wiki_query before answering. Use short keywords, trust returned pages, "
    "and return concise excerpts with repo-relative paths when relevant. Do not invent "
    "UI labels, shortcuts, or pm/postman APIs."
)

_WORKSPACE_RESEARCHER_SUFFIX = (
    "You are a Postmark workspace specialist. Use postmark_workspace_query with a "
    "focused scope before answering. Prefer short searches and target_id follow-ups "
    "from tool output. Trust returned slices; copy postmark:// links verbatim. Do not "
    "invent requests, collections, tabs, scripts, environments, or history entries."
)

_GENERAL_PURPOSE_SUFFIX = (
    "You are a focused helper for the Postmark API client. Answer concisely from the "
    "prompt only. Do not call tools unless the parent delegated tool use explicitly."
)


def _create_wiki_researcher(llm: object) -> Agent:
    """Factory for the wiki-researcher subagent."""
    return Agent(
        llm=llm,  # type: ignore[arg-type]
        tools=[Tool(name="postmark_wiki_query")],
        agent_context=AgentContext(system_message_suffix=_WIKI_RESEARCHER_SUFFIX),
    )


def _create_workspace_researcher(llm: object) -> Agent:
    """Factory for the workspace-researcher subagent."""
    return Agent(
        llm=llm,  # type: ignore[arg-type]
        tools=[Tool(name="postmark_workspace_query")],
        agent_context=AgentContext(system_message_suffix=_WORKSPACE_RESEARCHER_SUFFIX),
    )


def _create_general_purpose(llm: object) -> Agent:
    """Factory for the general-purpose subagent."""
    return Agent(
        llm=llm,  # type: ignore[arg-type]
        tools=[],
        agent_context=AgentContext(system_message_suffix=_GENERAL_PURPOSE_SUFFIX),
    )


def register_postmark_subagents() -> list[str]:
    """Register built-in and file-based subagent types.

    Returns:
        Names registered from file-based discovery (project + user dirs).
    """
    register_agent(
        name="wiki-researcher",
        factory_func=_create_wiki_researcher,
        description=(
            "Searches Postmark user wiki for UI workflows, scripting, and settings. "
            "Use for KB lookups instead of guessing."
        ),
    )
    register_agent(
        name="workspace-researcher",
        factory_func=_create_workspace_researcher,
        description=(
            "Reads the user's Postmark workspace (collections, requests, tabs, "
            "scripts, environments, history). Use for parallel workspace lookups."
        ),
    )
    register_agent(
        name="general-purpose",
        factory_func=_create_general_purpose,
        description=(
            "Short synthesis and consolidation without tools. Use for summaries "
            "and combining delegated results."
        ),
    )
    return register_file_agents(project_root())


__all__ = ["register_postmark_subagents"]
