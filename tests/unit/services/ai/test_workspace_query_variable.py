"""Tests for workspace query scope=variable."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from services.ai.chat.tools.workspace_query import SECRET_PLACEHOLDER, execute_workspace_query
from services.ai.chat.workspace_snapshot import clear_workspace_snapshot, set_workspace_snapshot
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService


@pytest.fixture(autouse=True)
def _clear_snapshots() -> None:
    clear_workspace_snapshot()


def _session() -> str:
    return str(uuid.uuid4())


def _seed_active(
    session_id: str,
    *,
    env_id: int | None = None,
    request_id: int | None = None,
) -> None:
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "active_collection_id": None,
            "current_env_id": env_id,
            "active_response": None,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": "Active",
                    "request_id": request_id,
                    "collection_id": None,
                    "local_script_id": None,
                    "is_dirty": False,
                    "is_active": True,
                    "request_data": None,
                }
            ],
        },
    )


def test_variable_empty_search_guidance() -> None:
    """Empty search returns guidance for scope=variable."""
    text = execute_workspace_query("variable", session_id=_session(), search="")
    assert "Provide non-empty" in text
    assert "scope=variable" in text


def test_variable_definitions_across_scopes(
    make_collection_with_request: Any,
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    """Definitions list globals, environments (with flags), and collections."""
    globals_path = tmp_path / "globals.json"
    globals_path.write_text('{"base_url": "https://global.example"}', encoding="utf-8")
    monkeypatch.setattr("services.scripting.context._GLOBALS_PATH", globals_path)
    coll, req = make_collection_with_request()
    CollectionService.update_collection(
        coll.id,
        variables=[{"key": "base_url", "value": "https://coll.example", "enabled": True}],
    )
    env = EnvironmentService.create_environment(
        "Dev",
        values=[
            {"key": "base_url", "value": "https://env.example", "enabled": True},
        ],
    )
    session_id = _session()
    _seed_active(session_id, env_id=env.id, request_id=req.id)
    text = execute_workspace_query("variable", session_id=session_id, search="base_url")
    assert "Definitions:" in text
    assert "Globals · base_url" in text
    assert f"postmark://environment/{env.id}" in text
    assert f"postmark://collection/{coll.id}" in text


def test_variable_disabled_flag(make_collection_with_request: Any) -> None:
    """Disabled environment variables are flagged in definitions."""
    env = EnvironmentService.create_environment(
        "Flags",
        values=[{"key": "feature_x", "value": "1", "enabled": False}],
    )
    text = execute_workspace_query("variable", session_id=_session(), search="feature_x")
    assert "(disabled)" in text
    assert f"postmark://environment/{env.id}" in text


def test_variable_secret_masked_in_definitions() -> None:
    """Secret-typed env values are masked even when the key name is not sensitive."""
    env = EnvironmentService.create_environment(
        "Secrets",
        values=[
            {
                "key": "internal_marker",
                "value": "RAWVARSECRET",
                "enabled": True,
                "type": "secret",
            },
        ],
    )
    text = execute_workspace_query("variable", session_id=_session(), search="internal_marker")
    assert SECRET_PLACEHOLDER in text
    assert "RAWVARSECRET" not in text
    assert f"postmark://environment/{env.id}" in text
    assert "(secret)" in text


def test_variable_collection_secret_masked_in_resolution(
    make_collection_with_request: Any,
) -> None:
    """Collection-sourced secret winners must not leak in Resolution."""
    coll, req = make_collection_with_request()
    CollectionService.update_collection(
        coll.id,
        variables=[
            {
                "key": "internal_marker",
                "value": "hunter2-collection-secret",
                "enabled": True,
                "type": "secret",
            },
            {
                "key": "plain_marker",
                "value": "visible-plain",
                "enabled": True,
                "type": "default",
            },
        ],
    )
    session_id = _session()
    _seed_active(session_id, request_id=req.id)
    text = execute_workspace_query("variable", session_id=session_id, search="internal_marker")
    assert "hunter2-collection-secret" not in text
    assert SECRET_PLACEHOLDER in text
    assert "(wins)" in text
    assert "Resolution (" in text
    plain = execute_workspace_query("variable", session_id=session_id, search="plain_marker")
    assert "visible-plain" in plain


def test_variable_no_secret_leak_across_sections(
    make_collection_with_request: Any,
) -> None:
    """Secret literals must not appear in definitions, resolution, or usages."""
    coll, req = make_collection_with_request(url="https://{{internal_marker}}/x")
    env = EnvironmentService.create_environment(
        "LeakCheck",
        values=[
            {
                "key": "internal_marker",
                "value": "LEAKMESECRET99",
                "enabled": True,
                "type": "secret",
            },
        ],
    )
    session_id = _session()
    _seed_active(session_id, env_id=env.id, request_id=req.id)
    text = execute_workspace_query("variable", session_id=session_id, search="internal_marker")
    assert "LEAKMESECRET99" not in text
    assert SECRET_PLACEHOLDER in text
    assert f"postmark://request/{req.id}" in text
    assert "url" in text
    assert coll.name in text or " · in " in text


def test_variable_override_chain_order(
    make_collection_with_request: Any,
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    """Active override chain lists environment → collection → globals."""
    globals_path = tmp_path / "globals.json"
    globals_path.write_text('{"host": "global-host"}', encoding="utf-8")
    monkeypatch.setattr("services.scripting.context._GLOBALS_PATH", globals_path)
    coll, req = make_collection_with_request()
    CollectionService.update_collection(
        coll.id,
        variables=[{"key": "host", "value": "coll-host", "enabled": True}],
    )
    env = EnvironmentService.create_environment(
        "ActiveEnv",
        values=[{"key": "host", "value": "env-host", "enabled": True}],
    )
    session_id = _session()
    _seed_active(session_id, env_id=env.id, request_id=req.id)
    text = execute_workspace_query("variable", session_id=session_id, search="host")
    assert "Active override chain" in text
    assert "(wins)" in text
    # Environment winner must appear before the collection fallback in the chain.
    chain_line = next(line for line in text.splitlines() if "→" in line or "(wins)" in line)
    assert "environment" in chain_line.casefold()
    assert "collection" in chain_line.casefold()
    assert "globals" in chain_line.casefold()
    assert chain_line.casefold().index("environment") < chain_line.casefold().index("collection")
    assert chain_line.casefold().index("collection") < chain_line.casefold().index("globals")
    assert f"environment: ActiveEnv, request: {req.name}" in text
    assert "env-host" in text
    assert "coll-host" in text
    assert "global-host" in text


def test_variable_usage_fields_and_breadcrumb(make_collection_with_request: Any) -> None:
    """Usages list matching fields, script {{refs}}, and nested path breadcrumbs."""
    parent = CollectionService.create_collection("VarParent")
    child = CollectionService.create_collection("VarChild", parent_id=parent.id)
    req = CollectionService.create_request(child.id, "GET", "https://{{host}}/api", "UsesHost")
    CollectionService.update_request(
        req.id,
        headers=[{"key": "X-Host", "value": "{{host}}", "enabled": True}],
        scripts={
            "test": (
                "// resolves {{host}} at send time\n"
                "pm.test('h', () => { pm.expect(pm.variables.get('host')); });"
            )
        },
    )
    text = execute_workspace_query("variable", session_id=_session(), search="host")
    assert f"postmark://request/{req.id}" in text
    assert "url" in text
    assert "headers" in text
    assert "test script" in text
    assert " · in VarParent/VarChild/UsesHost" in text


def test_variable_usage_cap_is_partial(monkeypatch: Any, make_collection_with_request: Any) -> None:
    """When usage scan is capped, empty-usages path (or marker) is partial."""
    make_collection_with_request(url="https://example.com")
    monkeypatch.setattr(
        "services.ai.chat.tools.workspace_query.render.variables.renderer._SEARCH_SCRIPT_SCAN_CAP",
        0,
    )
    # Cap of 0 means no requests scanned for usages of an unused-but-defined key.
    EnvironmentService.create_environment(
        "CapEnv",
        values=[{"key": "unused_cap_key", "value": "1", "enabled": True}],
    )
    text = execute_workspace_query("variable", session_id=_session(), search="unused_cap_key")
    assert "[partial]" in text
    assert "[authoritative]" not in text
    assert "scanned subset" in text.casefold() or "capped" in text.casefold()


def test_variable_display_cap_does_not_claim_scan_capped(
    monkeypatch: Any,
    make_collection_with_request: Any,
) -> None:
    """Display-row capping must not claim the tree scan was incomplete."""
    coll = CollectionService.create_collection("ManyUsages")
    for i in range(55):
        CollectionService.create_request(
            coll.id, "GET", f"https://{{{{shared_key}}}}/u{i}", f"U{i}"
        )
    monkeypatch.setattr(
        "services.ai.chat.tools.workspace_query.helpers._MAX_RESULT_ROWS",
        50,
    )
    text = execute_workspace_query("variable", session_id=_session(), search="shared_key")
    assert "[partial] Showing first 50" in text
    assert "scan capped at the first" not in text


def test_variable_unused_is_authoritative(make_collection_with_request: Any) -> None:
    """Unused defined keys get an authoritative no-usages marker."""
    make_collection_with_request()
    EnvironmentService.create_environment(
        "UnusedEnv",
        values=[{"key": "never_referenced_xyz", "value": "1", "enabled": True}],
    )
    text = execute_workspace_query(
        "variable",
        session_id=_session(),
        search="never_referenced_xyz",
    )
    assert "[authoritative]" in text
    assert "No usages" in text


def test_variable_similar_key_suggestions() -> None:
    """Undefined keys still render usages and suggest similar defined keys."""
    EnvironmentService.create_environment(
        "Suggest",
        values=[{"key": "base_url", "value": "https://x", "enabled": True}],
    )
    text = execute_workspace_query("variable", session_id=_session(), search="base_ur")
    assert "Similar keys:" in text or "similar" in text.casefold()
    assert "base_url" in text


def test_variable_casefold_to_exact_spelling() -> None:
    """Casefold lookup renders the exact spelling found in definitions."""
    EnvironmentService.create_environment(
        "Case",
        values=[{"key": "Base_URL", "value": "https://x", "enabled": True}],
    )
    text = execute_workspace_query("variable", session_id=_session(), search="base_url")
    assert "Definitions:" in text
    assert "Base_URL" in text


def test_variable_casefold_definition_still_finds_needle_usage(
    make_collection_with_request: Any,
) -> None:
    """Case-mismatched {{needle}} refs must still list as usages (not authoritative-empty)."""
    _coll, req = make_collection_with_request(url="https://{{base_url}}/x")
    EnvironmentService.create_environment(
        "CaseUse",
        values=[{"key": "Base_URL", "value": "https://x", "enabled": True}],
    )
    text = execute_workspace_query("variable", session_id=_session(), search="base_url")
    assert "Definitions:" in text
    assert "Base_URL" in text
    usages = text.split("Usages:", 1)[-1]
    assert f"postmark://request/{req.id}" in usages
    assert "url" in usages
    assert "[authoritative]" not in text


def test_variable_usage_is_case_sensitive(make_collection_with_request: Any) -> None:
    """Usages match exact spelling; {{MYHOST}} is not a usage of ``myhost``."""
    _coll, req = make_collection_with_request(url="https://{{MYHOST}}/x")
    EnvironmentService.create_environment(
        "ExactCase",
        values=[{"key": "myhost", "value": "example.com", "enabled": True}],
    )
    text = execute_workspace_query("variable", session_id=_session(), search="myhost")
    assert "Definitions:" in text
    usages = text.split("Usages:", 1)[-1]
    assert f"postmark://request/{req.id}" not in usages


def test_variable_used_but_undefined(make_collection_with_request: Any) -> None:
    """Used-but-undefined keys still scan usages with the raw needle."""
    _coll, req = make_collection_with_request(url="https://{{missing_host}}/x")
    text = execute_workspace_query("variable", session_id=_session(), search="missing_host")
    assert "No exact definitions" in text or "not defined" in text.casefold()
    assert f"postmark://request/{req.id}" in text
    assert "url" in text


def test_variable_sets_it_flag(make_collection_with_request: Any) -> None:
    """Script assignments surface a (sets it) usage flag."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        scripts={"pre_request": "pm.environment.set('dyn_token', 'x');"},
    )
    EnvironmentService.create_environment(
        "Dyn",
        values=[{"key": "dyn_token", "value": "old", "enabled": True}],
    )
    text = execute_workspace_query("variable", session_id=_session(), search="dyn_token")
    assert "sets it" in text
    assert f"postmark://request/{req.id}" in text


def test_variable_collection_context_without_request_tab(
    make_collection_with_request: Any,
) -> None:
    """Folder-tab snapshots resolve collection variables via active_collection_id."""
    coll, _req = make_collection_with_request()
    CollectionService.update_collection(
        coll.id,
        variables=[{"key": "folder_host", "value": "from-folder", "enabled": True}],
    )
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "active_collection_id": coll.id,
            "current_env_id": None,
            "active_response": None,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "folder",
                    "name": coll.name,
                    "request_id": None,
                    "collection_id": coll.id,
                    "local_script_id": None,
                    "is_dirty": False,
                    "is_active": True,
                    "request_data": None,
                }
            ],
        },
    )
    text = execute_workspace_query("variable", session_id=session_id, search="folder_host")
    assert "from-folder" in text
    assert "(wins)" in text
    assert f"collection: {coll.name}" in text


def test_variable_defined_only_in_non_active_env() -> None:
    """Definitions in other environments are noted when absent from active context."""
    EnvironmentService.create_environment(
        "OtherOnly",
        values=[{"key": "other_only_key", "value": "1", "enabled": True}],
    )
    active = EnvironmentService.create_environment("ActiveEmpty", values=[])
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "active_collection_id": None,
            "current_env_id": active.id,
            "active_response": None,
            "tabs": [],
        },
    )
    text = execute_workspace_query("variable", session_id=session_id, search="other_only_key")
    assert "Definitions:" in text
    assert "defined only in other environments" in text.casefold() or "not in the active" in text


def test_variable_disabled_in_active_env_message() -> None:
    """Disabled active-env definitions get an explicit disabled resolution message."""
    env = EnvironmentService.create_environment(
        "DisabledActive",
        values=[{"key": "feature_flag", "value": "1", "enabled": False}],
    )
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "active_collection_id": None,
            "current_env_id": env.id,
            "active_response": None,
            "tabs": [],
        },
    )
    text = execute_workspace_query("variable", session_id=session_id, search="feature_flag")
    assert "(disabled)" in text
    assert "disabled" in text.casefold()
    assert "defined only in other environments" not in text.casefold()


def test_variable_global_only_resolution(
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    """Global-only keys note that globals are scripts-only."""
    globals_path = tmp_path / "globals.json"
    globals_path.write_text('{"script_only_flag": "1"}', encoding="utf-8")
    monkeypatch.setattr("services.scripting.context._GLOBALS_PATH", globals_path)
    text = execute_workspace_query("variable", session_id=_session(), search="script_only_flag")
    assert "globals" in text.casefold()
    assert "scripts only" in text.casefold() or "pm.globals" in text
