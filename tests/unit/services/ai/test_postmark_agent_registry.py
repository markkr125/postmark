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
    assert defn.tool_names == (
        "postmark_wiki_query",
        "postmark_workspace_query",
        "postmark_datetime",
        "task_tool_set",
        "delegate",
    )
    assert defn.include_default_tools == ()
    assert defn.system_prompt
    assert "postmark_wiki_query" in defn.system_prompt
    assert "postmark_workspace_query" in defn.system_prompt
    assert "postmark_datetime" in defn.system_prompt
    assert "never invent wall-clock times" in defn.system_prompt
    assert "Unix seconds" in defn.system_prompt
    assert "delegate" in defn.system_prompt
    assert "workspace-researcher" in defn.system_prompt
    assert defn.max_iteration_per_run == 10
    assert DEFAULT_AGENT_ID in {d.id for d in list_agent_defs()}


def test_default_agent_workspace_prompt_phrases() -> None:
    """Workspace query guidance appears in both tool description and system prompt."""
    from services.ai.chat.tools.workspace_query import WORKSPACE_QUERY_DESCRIPTION

    defn = get_agent_def(DEFAULT_AGENT_ID)
    prompt = defn.system_prompt or ""
    for phrase in (
        "target_id is a request id",
        "captured at turn start",
        "open_tabs or collection_tree",
        "pre_request, test",
        "scope=insights",
        "script/script_versions",
        "globals",
        "snippets",
        "local_scripts",
        "recent_history",
        "history-entry id",
        "run id",
        "read-only",
        "authoritative",
        "partial or capped",
        "always require target_id",
        "request_script_versions",
        "settings",
        "Ids for follow-up calls",
        "tool arguments only",
        "prefer active_tab",
        "scope=request_history",
        "within_ids",
        "Do not use scope=search for send history",
        "translate silently into",
        "method:POST in:body checkout",
        "User-facing replies must stay natural language only",
    ):
        assert phrase in prompt
    for desc_phrase in (
        "id-type per scope",
        "captured at turn start",
        "open_tabs or collection_tree",
        "pre_request, test",
        "saved example id for saved_response",
        "snippet id for snippet",
        "scope=insights",
        "script_versions",
        "globals",
        "history-entry id",
        "run id",
        "read-only",
        "authoritative",
        "partial",
        "recent_history",
        "request_script_versions",
        "settings",
        "since:YYYY-MM-DD",
        "Ids for follow-up calls",
        "tool arguments only",
        "prefer ``active_tab``",
        "request params tables",
        "Translate the user's plain-language find",
        "method:POST in:body checkout",
        "follow-ups stay plain English",
        "scope=request_history",
        "within_ids",
        "within_ids=[-1]",
        "Do **not** use ``scope=search`` for send history",
        "Live GUI scopes",
    ):
        assert desc_phrase in WORKSPACE_QUERY_DESCRIPTION
    for link_phrase in (
        "the Name column must be the link",
        "postmark://request|collection|script|tab|history|environment|saved_response",
        "NEVER shown to the user",
        "never ask the user",
        "self-contained",
        "postmark://request/<id>",
    ):
        assert link_phrase in prompt
        assert link_phrase in WORKSPACE_QUERY_DESCRIPTION
    assert "postmark://request/1087" not in prompt
    assert "postmark://request/1087" not in WORKSPACE_QUERY_DESCRIPTION
    assert "local-script id for script and saved_response" not in WORKSPACE_QUERY_DESCRIPTION
    assert "within_ids=[-1]" in prompt
    assert "turn-start snapshots" in prompt


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
