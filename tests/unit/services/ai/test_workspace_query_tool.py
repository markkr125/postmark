"""Tests for the workspace query OpenHands tool."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest

from database.models.collections.collection_repository import create_new_request
from services.ai.chat.agent_registry import DEFAULT_AGENT_ID, get_agent_def
from services.ai.chat.tools.workspace_query import (
    REDACTED_PLACEHOLDER,
    SECRET_PLACEHOLDER,
    WorkspaceQueryAction,
    WorkspaceQueryExecutor,
    _MAX_OUTPUT_CHARS,
    _cap_rows,
    _link,
    _truncate_url,
    execute_workspace_query,
    register_workspace_query_tool,
)
from services.ai.chat.tool_registry import resolve_tools
from services.ai.chat.workspace_snapshot import clear_workspace_snapshot, set_workspace_snapshot
from services.assertion_service import AssertionService
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.scripting.context import normalize_events
from services.request_history_service import RequestHistoryService
from services.run_history_service import RunHistoryService
from ui.styling.history_settings_manager import HistorySettingsManager


@pytest.fixture(autouse=True)
def _clear_snapshots() -> None:
    clear_workspace_snapshot()


def _fake_conversation(session_id: str) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(id=session_id))


def _seed_snapshot(session_id: str, **overrides: Any) -> dict[str, Any]:
    snap: dict[str, Any] = {
        "active_tab_index": 0,
        "active_collection_id": None,
        "current_env_id": None,
        "active_response": None,
        "tabs": [
            {
                "index": 0,
                "tab_type": "request",
                "name": "Get Users",
                "request_id": None,
                "collection_id": None,
                "local_script_id": None,
                "is_dirty": False,
                "is_active": True,
                "request_data": None,
            }
        ],
    }
    snap.update(overrides)
    set_workspace_snapshot(session_id, snap)
    return snap


def test_normalize_events_plain_string_scripts() -> None:
    """Script extraction uses normalize_events for editor/DB shapes."""
    assert normalize_events({"pre_request": "pm.test('ok', () => {});"})["pre_request"] == (
        "pm.test('ok', () => {});"
    )
    assert normalize_events(None) == {}


def test_normalize_events_coerces_non_string_exec_lines() -> None:
    """Postman list-format exec lines coerce non-strings instead of raising."""
    got = normalize_events([{"listen": "prerequest", "script": {"exec": [0]}}])
    assert got["pre_request"] == "0"


def test_link_with_focus() -> None:
    """Deep links include optional focus query params."""
    assert _link("request", 12, "Create user", focus="test") == (
        "[Create user](postmark://request/12?focus=test)"
    )


def test_unknown_scope_lists_allowed() -> None:
    """Invalid scope returns guidance."""
    result = execute_workspace_query("nope", session_id="s")
    assert "Unknown scope" in result
    assert "overview" in result


def test_register_workspace_query_tool() -> None:
    """Tool resolves through the Postmark registry."""
    register_workspace_query_tool()
    tools = resolve_tools(("postmark_workspace_query",))
    assert len(tools) == 1
    assert tools[0].name == "postmark_workspace_query"


def test_default_agent_includes_workspace_tool() -> None:
    """Default assistant advertises the workspace query tool."""
    defn = get_agent_def(DEFAULT_AGENT_ID)
    assert "postmark_workspace_query" in defn.tool_names


def test_overview_and_open_tabs(make_collection_with_request: Any) -> None:
    """Overview and open_tabs read the session snapshot."""
    coll, req = make_collection_with_request(name="Users API")
    session_id = str(uuid.uuid4())
    _seed_snapshot(
        session_id,
        active_collection_id=coll.id,
        current_env_id=3,
        tabs=[
            {
                "index": 0,
                "tab_type": "request",
                "name": req.name,
                "request_id": req.id,
                "collection_id": coll.id,
                "local_script_id": None,
                "is_dirty": True,
                "is_active": True,
                "request_data": {"method": "GET", "url": "http://api/users"},
            }
        ],
    )
    overview = execute_workspace_query("overview", session_id=session_id)
    assert "Users API" in overview or "folders" in overview
    assert "Active environment:" in overview
    assert "postmark://environment/3" in overview or "environment 3" in overview
    assert "target_id=3" in overview

    tabs = execute_workspace_query("open_tabs", session_id=session_id)
    assert "dirty" in tabs
    assert f"postmark://request/{req.id}" in tabs


def test_open_tabs_links_unsaved_draft() -> None:
    """Unsaved draft tabs get postmark://tab/<n> links; saved tabs keep entity links."""
    session_id = str(uuid.uuid4())
    _seed_snapshot(
        session_id,
        tabs=[
            {
                "index": 0,
                "tab_type": "request",
                "name": "Saved",
                "request_id": 7,
                "collection_id": None,
                "local_script_id": None,
                "is_dirty": False,
                "is_active": True,
                "request_data": {"method": "GET", "url": "http://saved"},
            },
            {
                "index": 1,
                "tab_type": "request",
                "name": "Draft",
                "request_id": None,
                "collection_id": None,
                "local_script_id": None,
                "is_dirty": True,
                "is_active": False,
                "request_data": {"method": "POST", "url": "http://draft"},
            },
        ],
    )
    text = execute_workspace_query("open_tabs", session_id=session_id)
    assert "postmark://request/7" in text
    assert "postmark://tab/2" in text
    assert "[Draft](postmark://tab/2)" in text
    assert "POST http://draft" in text


def test_overview_counts_use_aggregates(make_collection_with_request: Any) -> None:
    """Overview uses aggregate counts instead of loading the full tree."""
    coll, req = make_collection_with_request()
    session_id = str(uuid.uuid4())
    _seed_snapshot(session_id, active_collection_id=coll.id)
    with patch.object(CollectionService, "fetch_all", side_effect=AssertionError("no tree load")):
        overview = execute_workspace_query("overview", session_id=session_id)
    assert "1 folders" in overview
    assert "1 requests" in overview


def test_overview_resolves_active_env_name() -> None:
    """Overview shows the active environment name when resolvable."""
    env = EnvironmentService.create_environment(
        "Staging",
        values=[{"key": "host", "value": "stg", "enabled": True}],
    )
    session_id = str(uuid.uuid4())
    _seed_snapshot(session_id, current_env_id=env.id)
    overview = execute_workspace_query("overview", session_id=session_id)
    assert "Active environment: Staging" in overview or (
        "Active environment:" in overview and f"postmark://environment/{env.id}" in overview
    )
    assert f"(id={env.id})" not in overview
    assert f"target_id={env.id}" in overview


def test_active_tab_caps_params() -> None:
    """Active tab caps the number of rendered query parameters."""
    session_id = str(uuid.uuid4())
    params = [{"key": f"p{i}", "value": f"v{i}", "enabled": True} for i in range(60)]
    _seed_snapshot(
        session_id,
        tabs=[
            {
                "index": 0,
                "tab_type": "request",
                "name": "Many params",
                "request_id": 1,
                "is_active": True,
                "request_data": {
                    "method": "GET",
                    "url": "http://x",
                    "request_parameters": params,
                },
            }
        ],
    )
    text = execute_workspace_query("active_tab", session_id=session_id)
    param_lines = [line for line in text.splitlines() if line.startswith("Param:")]
    assert len(param_lines) == 50
    assert "[partial]" in text
    assert "of 60 params" in text


def test_executor_missing_conversation() -> None:
    """Executor with no conversation uses empty snapshot defaults."""
    tab_obs = WorkspaceQueryExecutor()(
        WorkspaceQueryAction(scope="active_tab"),
        None,
    )
    tab_text = getattr(tab_obs.content[0], "text", "")
    assert "snapshot unavailable" in tab_text
    req_obs = WorkspaceQueryExecutor()(
        WorkspaceQueryAction(scope="request"),
        None,
    )
    req_text = getattr(req_obs.content[0], "text", "")
    assert req_text.startswith("No request id")


def test_active_response_shows_failing_tests() -> None:
    """Active response lists individual failing test rows when present."""
    session_id = str(uuid.uuid4())
    _seed_snapshot(
        session_id,
        active_response={
            "code": 500,
            "status": "Error",
            "test_summary": {"passed": 1, "failed": 1},
            "test_results": [
                {"name": "status is 200", "passed": False, "error": "expected 200 got 500"},
                {"name": "ok", "passed": True},
            ],
        },
    )
    text = execute_workspace_query("active_response", session_id=session_id)
    assert "failed: status is 200" in text
    assert "expected 200 got 500" in text
    assert not any(line.startswith("    failed:") and "ok" in line for line in text.splitlines())


def test_request_history_search_and_tail_note(
    make_collection_with_request: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """Request history notes overflow and supports search filtering."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    _coll, req = make_collection_with_request()
    settings = HistorySettingsManager()
    for i in range(26):
        RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": f"Send {i}",
                "method": "GET",
                "url": f"http://x/{i}",
            },
            response={"status_code": 200, "elapsed_ms": 1.0},
            original_request={"method": "GET", "url": f"http://x/{i}"},
            settings=settings,
        )
    session_id = str(uuid.uuid4())
    all_text = execute_workspace_query("request_history", session_id=session_id, target_id=req.id)
    assert "older sends — pass search=" in all_text
    filtered = execute_workspace_query(
        "request_history",
        session_id=session_id,
        target_id=req.id,
        search="Send 24",
    )
    assert "[id=25]" not in filtered
    assert "target_id=25" in filtered
    assert "target_id=1" not in filtered
    assert "[id=1]" not in filtered


def test_request_scope_resolved_variables(make_collection_with_request: Any) -> None:
    """Request scope shows resolved variables with secret env masking."""
    coll, req = make_collection_with_request()
    env = EnvironmentService.create_environment(
        "Secrets",
        values=[
            {"key": "api_secret", "value": "RAWSECRET", "enabled": True, "type": "secret"},
        ],
    )
    CollectionService.update_collection(
        coll.id,
        variables=[{"key": "tenant", "value": "acme", "enabled": True}],
    )
    session_id = str(uuid.uuid4())
    _seed_snapshot(session_id, current_env_id=env.id)
    text = execute_workspace_query("request", session_id=session_id, target_id=req.id)
    assert SECRET_PLACEHOLDER in text
    assert "RAWSECRET" not in text
    assert "tenant = acme (collection)" in text


def test_active_tab_and_response(make_collection_with_request: Any) -> None:
    """Active tab and live response scopes use snapshot payloads."""
    coll, req = make_collection_with_request()
    session_id = str(uuid.uuid4())
    _seed_snapshot(
        session_id,
        tabs=[
            {
                "index": 0,
                "tab_type": "request",
                "name": req.name,
                "request_id": req.id,
                "collection_id": coll.id,
                "local_script_id": None,
                "is_dirty": False,
                "is_active": True,
                "request_data": {
                    "method": "POST",
                    "url": "http://x",
                    "scripts": {
                        "test": "pm.test('ok', () => {});",
                    },
                },
            }
        ],
        active_response={
            "code": 201,
            "status": "Created",
            "elapsed_ms": 142,
            "size_bytes": 512,
            "headers": [{"key": "Authorization", "value": "Bearer secret"}],
            "body": '{"id":"u_1"}',
            "preview_language": "json",
            "test_summary": {"passed": 2, "failed": 0},
        },
    )
    tab_text = execute_workspace_query("active_tab", session_id=session_id)
    assert "pm.test" in tab_text
    assert f"postmark://request/{req.id}?focus=test" in tab_text

    resp_text = execute_workspace_query("active_response", session_id=session_id)
    assert "201" in resp_text
    assert REDACTED_PLACEHOLDER in resp_text
    assert "2 passed" in resp_text


def test_draft_active_tab_without_request_id() -> None:
    """Draft tabs render captured request_data even without a saved id."""
    session_id = str(uuid.uuid4())
    _seed_snapshot(
        session_id,
        tabs=[
            {
                "index": 0,
                "tab_type": "draft",
                "name": "Untitled",
                "request_id": None,
                "collection_id": None,
                "local_script_id": None,
                "is_dirty": True,
                "is_active": True,
                "request_data": {
                    "method": "PATCH",
                    "url": "http://draft/edit",
                    "scripts": {"pre_request": "console.log('prep');"},
                },
            }
        ],
    )
    text = execute_workspace_query("active_tab", session_id=session_id)
    assert "PATCH" in text
    assert "http://draft/edit" in text
    assert "console.log" in text
    assert "postmark://tab/1" in text
    assert "[Untitled](postmark://tab/1)" in text


def test_request_scope_redaction_and_assertions(make_collection_with_request: Any) -> None:
    """Request scope redacts bearer list auth and lists assertions."""
    coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        auth={
            "type": "bearer",
            "bearer": [{"key": "token", "value": "sekrit", "type": "string"}],
        },
        headers=[{"key": "Authorization", "value": "Bearer abc"}],
        scripts={
            "test": "pm.test('t', () => {});",
        },
    )
    AssertionService.save_for_request(
        req.id,
        [
            {
                "subject": "status",
                "operator": "equals",
                "expected": "200",
                "enabled": True,
                "order_index": 0,
            }
        ],
    )
    session_id = str(uuid.uuid4())
    text = execute_workspace_query("request", session_id=session_id, target_id=req.id)
    assert REDACTED_PLACEHOLDER in text
    assert "sekrit" not in text
    assert "status eq '200'" in text
    assert f"postmark://request/{req.id}?focus=test" in text


def test_request_history_shows_error(
    make_collection_with_request: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """Request history scope surfaces transport errors."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    _coll, req = make_collection_with_request()
    settings = HistorySettingsManager()
    RequestHistoryService.record_send(
        identity={
            "request_id": req.id,
            "request_name": req.name,
            "method": "GET",
            "url": "http://x",
        },
        response={"error": "Connection refused", "elapsed_ms": 0.0},
        original_request={"method": "GET", "url": "http://x"},
        settings=settings,
    )
    session_id = str(uuid.uuid4())
    text = execute_workspace_query("request_history", session_id=session_id, target_id=req.id)
    assert "Connection refused" in text


def test_collection_tree_includes_url(make_collection_with_request: Any) -> None:
    """Collection tree and search match on request URLs."""
    _coll, req = make_collection_with_request(url="https://api.example.com/v1/items")
    session_id = str(uuid.uuid4())
    tree = execute_workspace_query("collection_tree", session_id=session_id)
    assert "https://api.example.com/v1/items" in tree
    search = execute_workspace_query("search", session_id=session_id, search="api.example.com")
    assert f"postmark://request/{req.id}" in search


def test_runs_scope(make_collection_with_request: Any) -> None:
    """Runs scope summarizes collection runner history."""
    coll, _req = make_collection_with_request()
    run = RunHistoryService.create_run(collection_id=coll.id, total_requests=2)
    RunHistoryService.add_result(
        run["id"],
        request_name="Fail req",
        request_method="DELETE",
        status_code=500,
        test_failed=1,
    )
    RunHistoryService.finish_run(
        run["id"],
        status="completed",
        total_tests=1,
        passed=0,
        failed=1,
        avg_response_ms=138.0,
    )
    session_id = str(uuid.uuid4())
    text = execute_workspace_query("runs", session_id=session_id, target_id=coll.id)
    assert f"postmark://collection/{coll.id}" in text
    assert "failed" in text.lower()
    assert "DELETE" in text


def test_saved_responses_scope(make_collection_with_request: Any) -> None:
    """Saved responses scope lists examples and assertions."""
    coll, req = make_collection_with_request()
    CollectionService.save_response(
        req.id,
        "Example",
        "OK",
        200,
        [{"key": "content-type", "value": "application/json"}],
        "{}",
    )
    session_id = str(uuid.uuid4())
    text = execute_workspace_query("saved_responses", session_id=session_id, target_id=req.id)
    assert "Example" in text
    assert "focus=assertions" in text


def test_search_scope_matches_name_and_script(make_collection_with_request: Any) -> None:
    """Search matches script content even when the needle is absent from name/URL."""
    _coll, req = make_collection_with_request(req_name="Users list", url="http://api/users")
    CollectionService.update_request(
        req.id,
        scripts={"test": "// audit-marker check"},
    )
    session_id = str(uuid.uuid4())
    text = execute_workspace_query("search", session_id=session_id, search="audit-marker")
    assert f"postmark://request/{req.id}" in text
    assert "Script-content matches:" in text
    assert "(test script match)" in text
    assert "limited to the first" not in text


def test_search_scope_empty_is_authoritative(make_collection_with_request: Any) -> None:
    """An empty search states it covered the whole workspace and not to fall back to the wiki."""
    make_collection_with_request(req_name="Users list", url="http://api/users")
    session_id = str(uuid.uuid4())
    text = execute_workspace_query("search", session_id=session_id, search="nonexistent-xyz")
    assert "No matching requests" in text
    assert "[authoritative]" in text
    assert "wiki" in text.lower()
    assert "entire workspace" not in text
    assert "snippets" in text.casefold()


def test_truncate_url_and_cap_rows_helpers() -> None:
    """Long URLs shrink and long result lists are capped with a leading partial marker."""
    long_url = "http://x/?p=" + "a" * 500
    shortened = _truncate_url(long_url)
    assert shortened.endswith("…")
    assert len(shortened) < len(long_url)
    capped = _cap_rows([f"r{i}" for i in range(120)], label="matches")
    assert len(capped) == 51
    assert "more matches" in capped[0] or "of 120 matches" in capped[0]
    assert "[partial]" in capped[0]
    assert "narrow with a more specific scope" in capped[0]


def test_search_truncates_long_urls(make_collection_with_request: Any) -> None:
    """Search must not dump full multi-thousand-character URLs into context."""
    huge = "https://api/search?checkIn=2022-01-01&ids=" + ",".join(str(i) for i in range(2000))
    _coll, req = make_collection_with_request(req_name="Big search", url=huge)
    session_id = str(uuid.uuid4())
    text = execute_workspace_query("search", session_id=session_id, search="checkin")
    assert f"postmark://request/{req.id}" in text
    assert huge not in text
    assert "…" in text


def test_executor_uses_conversation_session_id(make_collection_with_request: Any) -> None:
    """WorkspaceQueryExecutor reads session id from the conversation."""
    coll, req = make_collection_with_request()
    session_id = str(uuid.uuid4())
    _seed_snapshot(
        session_id,
        tabs=[
            {
                "index": 0,
                "tab_type": "folder",
                "name": coll.name,
                "request_id": None,
                "collection_id": coll.id,
                "local_script_id": None,
                "is_dirty": False,
                "is_active": True,
            }
        ],
        active_collection_id=coll.id,
    )
    executor = WorkspaceQueryExecutor()
    obs = executor(
        WorkspaceQueryAction(scope="open_tabs"),
        cast(Any, _fake_conversation(session_id)),
    )
    chunk = obs.content[0]
    text = getattr(chunk, "text", "")
    assert f"postmark://collection/{coll.id}" in text


def test_executor_resolves_parent_session_for_subagent(
    make_collection_with_request: Any,
) -> None:
    """Subagent conversations use the parent session snapshot for live scopes."""
    coll, _req = make_collection_with_request()
    parent_id = str(uuid.uuid4())
    child_id = str(uuid.uuid4())
    _seed_snapshot(
        parent_id,
        tabs=[
            {
                "index": 0,
                "tab_type": "folder",
                "name": coll.name,
                "request_id": None,
                "collection_id": coll.id,
                "local_script_id": None,
                "is_dirty": False,
                "is_active": True,
            }
        ],
        active_collection_id=coll.id,
    )
    persistence = f"/tmp/ai/{uuid.UUID(parent_id).hex}/subagents/{uuid.UUID(child_id).hex}"
    conversation = SimpleNamespace(state=SimpleNamespace(id=child_id, persistence_dir=persistence))
    obs = WorkspaceQueryExecutor()(
        WorkspaceQueryAction(scope="open_tabs"),
        cast(Any, conversation),
    )
    text = getattr(obs.content[0], "text", "")
    assert f"postmark://collection/{coll.id}" in text
    # Child id alone must not find the parent snapshot.
    missing = execute_workspace_query("open_tabs", session_id=child_id)
    assert "Live GUI snapshot unavailable" in missing


def test_open_tabs_capped() -> None:
    """open_tabs caps row count at _MAX_RESULT_ROWS."""
    session_id = str(uuid.uuid4())
    tabs = [
        {
            "index": i,
            "tab_type": "request",
            "name": f"Tab {i}",
            "request_id": i + 1,
            "collection_id": None,
            "local_script_id": None,
            "is_dirty": False,
            "is_active": i == 0,
            "request_data": {"method": "GET", "url": "http://x"},
        }
        for i in range(60)
    ]
    _seed_snapshot(session_id, tabs=tabs)
    text = execute_workspace_query("open_tabs", session_id=session_id)
    tab_lines = [line for line in text.splitlines() if line.startswith("- ")]
    assert len(tab_lines) == 50
    assert "[partial]" in text
    assert "of" in text and "open tabs" in text
    assert "narrow with a more specific scope" in text


def test_collection_tree_large_workspace_within_output_cap(
    make_collection_with_request: Any,
) -> None:
    """Large collection_tree output stays within the global execute_workspace_query cap."""
    coll, _req = make_collection_with_request()
    long_url = "http://example.com/items?" + "id=" + "&id=".join(str(i) for i in range(80))
    for i in range(499):
        create_new_request(coll.id, "GET", long_url, f"Bulk request {i}")
    text = execute_workspace_query("collection_tree", session_id=str(uuid.uuid4()))
    link_lines = [line for line in text.splitlines() if line.lstrip().startswith("- [")]
    assert len(link_lines) == 50
    assert "[partial]" in text
    assert "of 501 rows" in text or "of 501" in text
    assert len(text) <= _MAX_OUTPUT_CHARS
