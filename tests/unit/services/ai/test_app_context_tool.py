"""Unit tests for postmark_app_context tool executor."""

from __future__ import annotations

from unittest.mock import MagicMock

from services.ai.chat.tools.app_context import (
    AppContextAction,
    AppContextExecutor,
    PARENT_FORBIDDEN_FOCI,
)


def test_parent_forbidden_focus_redirect() -> None:
    """Parent agent with TaskToolSet cannot use search focus."""
    executor = AppContextExecutor()
    conversation = MagicMock()
    conversation.agent.tools_map = {"task_tool_set": object()}
    action = AppContextAction(focus="search", query="users")
    obs = executor(action, conversation)
    assert "workspace_researcher" in obs.text


def test_sub_agent_allows_search(tmp_path) -> None:
    """Sub-agent without TaskToolSet may search when snapshot exists."""
    snap = tmp_path / "app_context_snapshot.json"
    snap.write_text(
        '{"captured_at":"t","send_mode":"agent","active_tab":{"tab_type":"none",'
        '"request_id":null,"collection_id":null,"local_script_id":null,"title":"",'
        '"method":null,"is_dirty":false,"is_preview":false,"draft_name":null,'
        '"active_sub_tab":null,"editor_preview":""},"open_tabs":[],"deferred_tabs":[],'
        '"environment":{"id":null,"name":null},'
        '"tree_selection":{"kind":"none","collection_id":null,'
        '"local_script_id":null,"label":null}}',
        encoding="utf-8",
    )
    executor = AppContextExecutor()
    conversation = MagicMock()
    conversation.agent.tools_map = {}
    conversation.state.workspace.working_dir = str(tmp_path)
    action = AppContextAction(focus="current")
    obs = executor(action, conversation)
    assert "Current context" in obs.text


def test_parent_forbidden_foci_set() -> None:
    """Forbidden parent foci match the plan."""
    assert "search" in PARENT_FORBIDDEN_FOCI
    assert "workspace" in PARENT_FORBIDDEN_FOCI
