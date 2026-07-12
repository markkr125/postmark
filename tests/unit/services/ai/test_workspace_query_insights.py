"""Tests for workspace health insights and fielded/multi-goal search."""

from __future__ import annotations

from typing import Any

from services.ai.chat.tools.workspace_query import SECRET_PLACEHOLDER, execute_workspace_query
from services.ai.chat.tools.workspace_query.query_parse import parse_fielded_query
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.local_script_service import LocalScriptService


def _session() -> str:
    """Return a unique session id for snapshot isolation."""
    import uuid

    return str(uuid.uuid4())


def test_parse_fielded_query_operators() -> None:
    """Fielded parser extracts in/method/has and rejects unknown ops."""
    q = parse_fielded_query('in:script method:POST has:assert "exact phrase" foo OR bar -noise')
    assert q.error is None
    assert "script" in q.in_buckets
    assert q.method == "POST"
    assert "assert" in q.has
    assert "exact phrase" in q.phrases
    assert q.or_groups
    assert "noise" in q.exclude_tokens
    bad = parse_fielded_query("foo:bar")
    assert bad.error is not None
    assert "Unknown" in bad.error


def test_insights_workspace_health_header(make_collection_with_request: Any) -> None:
    """Insights leads with Workspace health summary."""
    make_collection_with_request(req_name="UntestedHealth")
    text = execute_workspace_query("insights", session_id=_session())
    assert "Workspace health:" in text
    assert "Missing tests:" in text


def test_insights_unresolved_and_unused(make_collection_with_request: Any) -> None:
    """Insights reports unresolved vars and unused definitions."""
    env = EnvironmentService.create_environment("HealthEnv")
    EnvironmentService.update_environment_values(
        env.id,
        [
            {"key": "unused_health_key", "value": "x", "enabled": True, "type": "default"},
            {
                "key": "base_url",
                "value": "https://api.example.com",
                "enabled": True,
                "type": "default",
            },
        ],
    )
    _coll, req = make_collection_with_request(
        req_name="NeedsVar",
        url="http://{{missing_health_host}}/path",
    )
    from services.ai.chat.workspace_snapshot import set_workspace_snapshot

    sid = _session()
    set_workspace_snapshot(sid, {"current_env_id": env.id, "tabs": [], "active_tab_index": 0})
    text = execute_workspace_query("insights", session_id=sid, search="unresolved,unused")
    assert "Unresolved" in text or "missing_health_host" in text or f"request/{req.id}" in text
    assert "unused_health_key" in text or "Unused" in text
    assert (
        SECRET_PLACEHOLDER not in text
        or "secret" not in text.lower()
        or "keys only" in text.lower()
    )


def test_insights_case_mismatch(make_collection_with_request: Any) -> None:
    """Case-mismatch section flags {{Base_URL}} vs base_url definition."""
    env = EnvironmentService.create_environment("CaseEnv")
    EnvironmentService.update_environment_values(
        env.id,
        [{"key": "base_url", "value": "https://x.test", "enabled": True, "type": "default"}],
    )
    _coll, req = make_collection_with_request(
        req_name="CaseMismatch",
        url="http://{{Base_URL}}/v1",
    )
    from services.ai.chat.workspace_snapshot import set_workspace_snapshot

    sid = _session()
    set_workspace_snapshot(sid, {"current_env_id": env.id, "tabs": [], "active_tab_index": 0})
    text = execute_workspace_query("insights", session_id=sid, search="case_mismatch")
    assert f"postmark://request/{req.id}" in text or "Case-mismatch" in text


def test_fielded_search_in_script(make_collection_with_request: Any) -> None:
    """in:script matches script body without requiring name/URL hit."""
    _coll, req = make_collection_with_request(req_name="ScriptOnlyReq")
    CollectionService.update_request(
        req.id,
        scripts={"test": "pm.test('fielded_script_marker_xyz', function () {});"},
    )
    text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="in:script fielded_script_marker_xyz",
    )
    assert f"postmark://request/{req.id}" in text
    assert "script match" in text.lower() or "Script-content" in text


def test_fielded_search_method_filter(make_collection_with_request: Any) -> None:
    """method:POST filters structural results."""
    _coll, req = make_collection_with_request(req_name="PostOnly", method="POST")
    text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="method:POST PostOnly",
    )
    assert f"postmark://request/{req.id}" in text


def test_fielded_unknown_operator_errors() -> None:
    """Unknown fielded operators hard-error."""
    text = execute_workspace_query("search", session_id=_session(), search="bogus:1 foo")
    assert "Unknown" in text


def test_multi_goal_chain(make_collection_with_request: Any) -> None:
    """Goals batch runs search then insights with within chaining."""
    _coll, req = make_collection_with_request(
        req_name="GoalChainReq", url="https://goal-chain.example/x"
    )
    text = execute_workspace_query(
        "overview",
        session_id=_session(),
        goals=[
            {"id": "hits", "scope": "search", "search": "GoalChainReq"},
            {"id": "health", "scope": "insights", "sections": ["missing_tests"], "within": "hits"},
        ],
    )
    assert "Multi-goal exploration:" in text
    assert "Goal `hits`" in text
    assert "Goal `health`" in text
    assert f"postmark://request/{req.id}" in text


def test_env_diff() -> None:
    """Environments search=diff compares two envs without leaking secrets."""
    a = EnvironmentService.create_environment("DiffA")
    b = EnvironmentService.create_environment("DiffB")
    EnvironmentService.update_environment_values(
        a.id,
        [
            {"key": "shared", "value": "one", "enabled": True, "type": "default"},
            {"key": "only_a", "value": "secret_a_value", "enabled": True, "type": "secret"},
        ],
    )
    EnvironmentService.update_environment_values(
        b.id,
        [
            {"key": "shared", "value": "two", "enabled": True, "type": "default"},
            {"key": "only_b", "value": "x", "enabled": True, "type": "default"},
        ],
    )
    text = execute_workspace_query(
        "environments",
        session_id=_session(),
        search=f"diff:{a.id}:{b.id}",
    )
    assert "Environment diff:" in text
    assert "only_a" in text
    assert "only_b" in text
    assert "shared" in text
    assert "secret_a_value" not in text


def test_local_script_polyglot_inventory() -> None:
    """local_scripts includes polyglot inventory counts."""
    folder = LocalScriptService.create_folder("PolyglotFolder")
    LocalScriptService.create_script(folder.id, "poly.js", language="javascript")
    text = execute_workspace_query("local_scripts", session_id=_session())
    assert "Polyglot inventory" in text
