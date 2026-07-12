"""Audit remediation tests for postmark_workspace_query."""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import patch

import pytest

from database.models.collections.collection_repository import create_new_request
from services.ai.chat.tools.workspace_query import (
    REDACTED_PLACEHOLDER,
    SECRET_PLACEHOLDER,
    _MAX_OUTPUT_CHARS,
    _truncate_url,
    execute_workspace_query,
)
from services.ai.chat.workspace_snapshot import set_workspace_snapshot
from services.assertion_service import AssertionDict, AssertionService
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.local_script_service import LocalScriptService
from services.request_history_service import RequestHistoryService
from services.run_history_service import RunHistoryService
from services.snippet_service import SnippetService
from ui.styling.history_settings_manager import HistorySettingsManager


def _session() -> str:
    return str(uuid.uuid4())


def test_imported_postman_scripts_visible(make_collection_with_request: Any) -> None:
    """Postman event-array scripts appear in request, active_tab, and search."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        scripts=None,
        events=[
            {
                "listen": "prerequest",
                "script": {"exec": ["console.log(1)"]},
            },
            {
                "listen": "test",
                "script": {"exec": ["pm.test('x',()=>{})"]},
            },
        ],
    )
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "active_collection_id": None,
            "current_env_id": None,
            "active_response": None,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": req.name,
                    "request_id": req.id,
                    "collection_id": None,
                    "local_script_id": None,
                    "is_dirty": False,
                    "is_active": True,
                    "request_data": None,
                }
            ],
        },
    )
    request_text = execute_workspace_query("request", session_id=session_id, target_id=req.id)
    assert "console.log(1)" in request_text
    assert "pm.test" in request_text

    tab_text = execute_workspace_query("active_tab", session_id=session_id)
    assert "console.log(1)" in tab_text

    search_text = execute_workspace_query("search", session_id=session_id, search="console.log")
    assert f"postmark://request/{req.id}" in search_text
    assert "No matching requests" not in search_text


def test_truncate_url_redacts_secrets() -> None:
    """Sensitive query params are redacted; {{var}} placeholders are kept."""
    redacted = _truncate_url("http://x/?api_key=live_sk_secret123")
    assert REDACTED_PLACEHOLDER in redacted
    assert "live_sk_secret123" not in redacted
    intact = _truncate_url("http://x/?key={{apiKey}}")
    assert "{{apiKey}}" in intact
    assert REDACTED_PLACEHOLDER not in intact


def test_active_tab_redacts_secret_params_and_body() -> None:
    """Active tab must not leak secret query params or JSON body fields to the LLM."""
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": "Secret req",
                    "request_id": 42,
                    "is_active": True,
                    "request_data": {
                        "method": "POST",
                        "url": "https://api/x?api_key=PARAMSECRET",
                        "request_parameters": [
                            {"key": "api_key", "value": "PARAMSECRET", "enabled": True},
                        ],
                        "body": '{"client_secret":"BODYSECRET","user":"a"}',
                        "body_mode": "raw",
                        "body_options": {"raw": {"language": "json"}},
                    },
                }
            ],
        },
    )
    text = execute_workspace_query("active_tab", session_id=session_id)
    assert "PARAMSECRET" not in text
    assert "BODYSECRET" not in text
    assert REDACTED_PLACEHOLDER in text
    assert SECRET_PLACEHOLDER in text
    assert '"user": "a"' in text or '"user":"a"' in text


def test_request_scope_redacts_body_secrets(make_collection_with_request: Any) -> None:
    """Request scope redacts secret keys inside JSON request bodies."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        body='{"client_secret":"BODYSECRET","user":"ok"}',
        body_mode="raw",
        body_options={"raw": {"language": "json"}},
    )
    text = execute_workspace_query("request", session_id=_session(), target_id=req.id)
    assert "BODYSECRET" not in text
    assert SECRET_PLACEHOLDER in text
    assert '"user": "ok"' in text or '"user":"ok"' in text


def test_saved_response_body_redacts_secrets(make_collection_with_request: Any) -> None:
    """Saved example bodies redact secret JSON keys like live/history responses."""
    _coll, req = make_collection_with_request()
    sr_id = CollectionService.save_response(
        req.id,
        "Token example",
        "OK",
        200,
        [],
        '{"access_token":"TOKENSECRET","ok":true}',
    )
    detail = execute_workspace_query("saved_response", session_id=_session(), target_id=sr_id)
    assert "TOKENSECRET" not in detail
    assert SECRET_PLACEHOLDER in detail


def test_form_urlencoded_body_masks_param_values(make_collection_with_request: Any) -> None:
    """Form-urlencoded request bodies mask secret field values."""
    _coll, req = make_collection_with_request()
    form_body = json.dumps(
        [
            {"key": "client_secret", "value": "SUPERSECRET", "enabled": True},
            {"key": "grant_type", "value": "client_credentials", "enabled": True},
        ]
    )
    CollectionService.update_request(
        req.id,
        body_mode="x-www-form-urlencoded",
        body=form_body,
    )
    session_id = _session()
    request_text = execute_workspace_query("request", session_id=session_id, target_id=req.id)
    assert "SUPERSECRET" not in request_text
    assert REDACTED_PLACEHOLDER in request_text
    assert "client_credentials" in request_text

    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": req.name,
                    "request_id": req.id,
                    "is_active": True,
                    "request_data": {
                        "method": "POST",
                        "url": "http://token",
                        "body": form_body,
                        "body_mode": "x-www-form-urlencoded",
                    },
                }
            ],
        },
    )
    tab_text = execute_workspace_query("active_tab", session_id=session_id)
    assert "SUPERSECRET" not in tab_text
    assert REDACTED_PLACEHOLDER in tab_text
    assert "client_credentials" in tab_text


def test_camelcase_secret_keys_masked() -> None:
    """CamelCase JSON secret keys are masked in active_response bodies."""
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [{"index": 0, "tab_type": "request", "name": "R", "is_active": True}],
            "active_response": {
                "code": 200,
                "status": "OK",
                "body": '{"accessToken":"A1","refreshToken":"R1","clientSecret":"C1","user":"ok"}',
                "preview_language": "json",
            },
        },
    )
    text = execute_workspace_query("active_response", session_id=session_id)
    assert "A1" not in text
    assert "R1" not in text
    assert "C1" not in text
    assert SECRET_PLACEHOLDER in text
    assert "ok" in text


def test_raw_xml_and_form_bodies_redacted(make_collection_with_request: Any) -> None:
    """XML element text and plain form bodies redact secrets."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        body="<wsse:Password>hunter2</wsse:Password>",
        body_mode="raw",
        body_options={"raw": {"language": "xml"}},
    )
    xml_text = execute_workspace_query("request", session_id=_session(), target_id=req.id)
    assert "hunter2" not in xml_text
    assert SECRET_PLACEHOLDER in xml_text

    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [{"index": 0, "tab_type": "request", "name": "R", "is_active": True}],
            "active_response": {
                "code": 200,
                "status": "OK",
                "body": "access_token=SECRETTOK&token_type=bearer",
                "preview_language": "text",
            },
        },
    )
    form_text = execute_workspace_query("active_response", session_id=session_id)
    assert "SECRETTOK" not in form_text
    assert REDACTED_PLACEHOLDER in form_text
    assert "token_type=bearer" in form_text


def test_xml_markup_redacted_when_lang_is_text() -> None:
    """XML/SOAP bodies are redacted even when preview_language is text."""
    from services.ai.chat.tools.workspace_query.helpers import _redact_response_body

    xml = "<root><api_key>SECRET123</api_key></root>"
    redacted = _redact_response_body(xml, "text")
    assert "SECRET123" not in redacted
    assert SECRET_PLACEHOLDER in redacted


def test_history_entry_xml_body_redacted(
    make_collection_with_request: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """History entry scope redacts XML response bodies using Content-Type."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    _coll, req = make_collection_with_request()
    settings = HistorySettingsManager()
    entry_id = RequestHistoryService.record_send(
        identity={
            "request_id": req.id,
            "request_name": req.name,
            "method": "POST",
            "url": "http://soap",
        },
        response={
            "status_code": 200,
            "elapsed_ms": 1.0,
            "headers": [{"key": "Content-Type", "value": "text/xml"}],
            "body": b"<Envelope><api_key>SOAPSECRET</api_key></Envelope>",
        },
        original_request={"method": "POST", "url": "http://soap"},
        settings=settings,
    )
    text = execute_workspace_query("history_entry", session_id=_session(), target_id=entry_id)
    assert "SOAPSECRET" not in text
    assert SECRET_PLACEHOLDER in text


def test_env_value_truncated() -> None:
    """Environment scope truncates long non-secret variable values."""
    EnvironmentService.create_environment(
        "LongVals",
        values=[{"key": "big", "value": "v" * 500, "enabled": True, "type": "default"}],
    )
    text = execute_workspace_query("environments", session_id=_session())
    assert "truncated" in text
    assert "v" * 500 not in text


def test_search_fetches_bounded_script_set(make_collection_with_request: Any) -> None:
    """Search script scan uses bounded id fetch."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(req.id, scripts={"test": "unique_marker_xyz"})
    with patch.object(
        CollectionService,
        "fetch_request_scripts_for_ids",
        wraps=CollectionService.fetch_request_scripts_for_ids,
    ) as bounded:
        text = execute_workspace_query("search", session_id=_session(), search="unique_marker")
    assert f"postmark://request/{req.id}" in text
    bounded.assert_called_once()
    ordered_ids = bounded.call_args[0][0]
    assert req.id in ordered_ids
    assert len(ordered_ids) <= 200


def test_active_response_masks_set_cookie(make_collection_with_request: Any) -> None:
    """Live response masks Set-Cookie headers."""
    _coll, req = make_collection_with_request()
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": req.name,
                    "request_id": req.id,
                    "is_active": True,
                }
            ],
            "active_response": {
                "code": 200,
                "status": "OK",
                "headers": [{"key": "Set-Cookie", "value": "session=abc123"}],
                "body": "{}",
                "preview_language": "json",
            },
        },
    )
    text = execute_workspace_query("active_response", session_id=session_id)
    assert REDACTED_PLACEHOLDER in text
    assert "abc123" not in text


def test_request_scope_masks_x_auth_token(make_collection_with_request: Any) -> None:
    """Request scope redacts X-Auth-Token headers."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        headers=[{"key": "X-Auth-Token", "value": "tok_secret"}],
    )
    text = execute_workspace_query("request", session_id=_session(), target_id=req.id)
    assert REDACTED_PLACEHOLDER in text
    assert "tok_secret" not in text


def test_active_response_masks_body_secret(make_collection_with_request: Any) -> None:
    """JSON live response bodies mask secret keys."""
    _coll, req = make_collection_with_request()
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": req.name,
                    "request_id": req.id,
                    "is_active": True,
                }
            ],
            "active_response": {
                "code": 200,
                "body": '{"access_token":"sekrit","id":"u_1"}',
                "preview_language": "json",
            },
        },
    )
    text = execute_workspace_query("active_response", session_id=session_id)
    assert SECRET_PLACEHOLDER in text
    assert "sekrit" not in text
    assert "u_1" in text


def test_request_scope_shows_body(make_collection_with_request: Any) -> None:
    """Request scope includes the saved body."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        body='{"hello":"world"}',
        body_mode="raw",
        body_options={"raw": {"language": "json"}},
    )
    text = execute_workspace_query("request", session_id=_session(), target_id=req.id)
    assert "hello" in text
    assert "Body" in text


def test_runs_scope_caps_failures(make_collection_with_request: Any) -> None:
    """Run failure list is capped at 20 rows."""
    coll, _req = make_collection_with_request()
    run = RunHistoryService.create_run(collection_id=coll.id, total_requests=30)
    for i in range(30):
        RunHistoryService.add_result(
            run["id"],
            request_name=f"Fail {i}",
            request_method="GET",
            status_code=500,
            test_failed=1,
            error=f"err-{i}",
        )
    RunHistoryService.finish_run(
        run["id"],
        status="completed",
        total_tests=30,
        passed=0,
        failed=30,
    )
    text = execute_workspace_query("runs", session_id=_session(), target_id=coll.id)
    failure_lines = [line for line in text.splitlines() if line.strip().startswith("failed:")]
    assert len(failure_lines) == 20
    assert "[partial]" in text
    assert "run failures" in text


def test_runs_scope_running_run(make_collection_with_request: Any) -> None:
    """An unfinished run shows running status without crashing."""
    coll, _req = make_collection_with_request()
    RunHistoryService.create_run(collection_id=coll.id, total_requests=1)
    text = execute_workspace_query("runs", session_id=_session(), target_id=coll.id)
    assert "running" in text.lower()
    assert "avg 0 ms" in text
    assert "Latest run failures" not in text


def test_saved_responses_capped(make_collection_with_request: Any) -> None:
    """Saved examples and assertions are capped."""
    _coll, req = make_collection_with_request()
    for i in range(60):
        CollectionService.save_response(req.id, f"Ex {i}", "OK", 200, [], "{}")
    rows: list[AssertionDict] = [
        {
            "subject": "status",
            "operator": "equals",
            "expected": "x" * 300,
            "enabled": True,
            "order_index": i,
        }
        for i in range(60)
    ]
    AssertionService.save_for_request(req.id, rows)
    text = execute_workspace_query("saved_responses", session_id=_session(), target_id=req.id)
    assert "[partial]" in text
    assert "saved examples" in text
    assert "of 60 assertions" in text or "assertions" in text.split("[partial]")[-1]


def test_header_value_truncated(make_collection_with_request: Any) -> None:
    """Long non-sensitive header values are truncated."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        headers=[{"key": "X-Custom", "value": "v" * 500}],
    )
    text = execute_workspace_query("request", session_id=_session(), target_id=req.id)
    assert "truncated" in text
    assert "v" * 500 not in text


def test_search_scans_scripts_single_query(make_collection_with_request: Any) -> None:
    """Search uses batch script fetch instead of per-request get_request."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(req.id, scripts={"test": "unique_marker_xyz"})
    session_id = _session()
    with patch.object(CollectionService, "get_request") as mock_get:
        execute_workspace_query("search", session_id=session_id, search="unique_marker")
        mock_get.assert_not_called()


def test_collection_tree_caps_rows(make_collection_with_request: Any) -> None:
    """Collection tree caps at 50 request link lines."""
    coll, _req = make_collection_with_request()
    for i in range(59):
        create_new_request(coll.id, "GET", f"http://x/{i}", f"Req {i}")
    text = execute_workspace_query("collection_tree", session_id=_session())
    link_lines = [line for line in text.splitlines() if line.lstrip().startswith("- [")]
    assert len(link_lines) == 50
    assert "[partial]" in text
    assert "rows" in text


def test_environments_key_cap() -> None:
    """Environment variable lists are capped per env."""
    env = EnvironmentService.create_environment(
        "Cap Env",
        values=[
            {"key": f"k{i}", "value": f"v{i}", "enabled": True, "type": "default"}
            for i in range(50)
        ],
    )
    _ = env.id
    text = execute_workspace_query("environments", session_id=_session())
    assert "…and 10 more" in text


def test_environments_shows_values() -> None:
    """Non-secret environment values are shown; secrets masked."""
    env = EnvironmentService.create_environment(
        "Prod",
        values=[
            {
                "key": "base_url",
                "value": "https://api.example.com",
                "enabled": True,
                "type": "default",
            },
            {"key": "api_key", "value": "sekrit", "enabled": True, "type": "secret"},
        ],
    )
    _ = env.id
    text = execute_workspace_query("environments", session_id=_session())
    assert "base_url = https://api.example.com" in text
    assert SECRET_PLACEHOLDER in text
    assert "sekrit" not in text


def test_request_history_error_truncated(
    make_collection_with_request: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """Long history error strings are truncated."""
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
        response={"error": "E" * 500, "elapsed_ms": 0.0},
        original_request={"method": "GET", "url": "http://x"},
        settings=settings,
    )
    text = execute_workspace_query("request_history", session_id=_session(), target_id=req.id)
    assert "truncated" in text
    assert "E" * 500 not in text


def test_request_scope_inherited_auth_and_vars(make_collection_with_request: Any) -> None:
    """Inherited auth and collection variable keys appear when request inherits."""
    coll, req = make_collection_with_request()
    CollectionService.update_collection(
        coll.id,
        auth={
            "type": "bearer",
            "bearer": [{"key": "token", "value": "parent_tok", "type": "string"}],
        },
        variables=[{"key": "tenant_id", "value": "t1", "enabled": True}],
    )
    CollectionService.update_request(req.id, auth=None)
    text = execute_workspace_query("request", session_id=_session(), target_id=req.id)
    assert "Inherited auth:" in text
    assert "parent_tok" not in text
    assert "tenant_id" in text


def test_active_tab_local_script() -> None:
    """Local script tab falls back to DB content when snapshot omits it."""
    folder = LocalScriptService.create_folder("lib")
    script = LocalScriptService.create_script(
        folder.id,
        "helper",
        language="javascript",
        content="console.log('hi');",
    )
    script_id = script.id
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "local_script",
                    "name": "helper",
                    "local_script_id": script_id,
                    "local_script_content": None,
                    "local_script_language": None,
                    "is_active": True,
                }
            ],
        },
    )
    text = execute_workspace_query("active_tab", session_id=session_id)
    assert "console.log('hi')" in text
    assert "javascript" in text


def test_history_entry_scope(
    make_collection_with_request: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """history_entry scope renders stored send details."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    _coll, req = make_collection_with_request()
    settings = HistorySettingsManager()
    entry_id = RequestHistoryService.record_send(
        identity={
            "request_id": req.id,
            "request_name": req.name,
            "method": "GET",
            "url": "http://x",
        },
        response={
            "status_code": 200,
            "elapsed_ms": 12.0,
            "headers": [{"key": "Content-Type", "value": "application/json"}],
            "body": b'{"access_token":"hidden","ok":true}',
        },
        original_request={"method": "GET", "url": "http://x"},
        settings=settings,
    )
    text = execute_workspace_query("history_entry", session_id=_session(), target_id=entry_id)
    assert f"target_id={entry_id}" in text
    assert "[id=" not in text
    assert SECRET_PLACEHOLDER in text
    assert "hidden" not in text

    missing = execute_workspace_query("history_entry", session_id=_session(), target_id=999999)
    assert "not found" in missing


def test_saved_response_scope(make_collection_with_request: Any) -> None:
    """saved_response scope renders one example."""
    _coll, req = make_collection_with_request()
    sr_id = CollectionService.save_response(
        req.id,
        "Login OK",
        "OK",
        200,
        [{"key": "Set-Cookie", "value": "s=1"}],
        '{"token":"x"}',
    )
    list_text = execute_workspace_query("saved_responses", session_id=_session(), target_id=req.id)
    assert f"target_id={sr_id}" in list_text
    assert f"postmark://saved_response/{sr_id}" in list_text
    assert "[id=" not in list_text
    detail = execute_workspace_query("saved_response", session_id=_session(), target_id=sr_id)
    assert "Login OK" in detail
    assert f"postmark://saved_response/{sr_id}" in detail
    assert REDACTED_PLACEHOLDER in detail

    missing = execute_workspace_query("saved_response", session_id=_session(), target_id=999999)
    assert "not found" in missing


def test_run_scope(make_collection_with_request: Any) -> None:
    """Run scope lists per-request results."""
    coll, _req = make_collection_with_request()
    run = RunHistoryService.create_run(collection_id=coll.id, total_requests=1)
    RunHistoryService.add_result(
        run["id"],
        request_name="One",
        request_method="POST",
        status_code=201,
        test_passed=2,
        test_failed=0,
    )
    RunHistoryService.finish_run(run["id"], status="completed", total_tests=2, passed=2, failed=0)
    runs_text = execute_workspace_query("runs", session_id=_session(), target_id=coll.id)
    assert f"target_id={run['id']}" in runs_text
    assert f"run #{run['id']}" not in runs_text
    detail = execute_workspace_query("run", session_id=_session(), target_id=run["id"])
    assert "POST One" in detail


def test_history_entry_dict_shaped_headers() -> None:
    """Dict-shaped stored response headers render as key/value rows."""
    fake = {
        "id": 1,
        "method": "GET",
        "url": "http://x",
        "status_code": 200,
        "elapsed_ms": 5.0,
        "response_headers": {"X-Test": "yes", "Authorization": "secret"},
        "body": None,
        "body_truncated": False,
        "original_request": {},
        "error": None,
    }
    with patch.object(RequestHistoryService, "get_entry", return_value=fake):
        text = execute_workspace_query("history_entry", session_id=_session(), target_id=1)
    assert "Header: X-Test: yes" in text
    assert REDACTED_PLACEHOLDER in text
    assert "secret" not in text


def test_saved_response_dict_shaped_headers(make_collection_with_request: Any) -> None:
    """Dict-shaped saved-example headers render as key/value rows."""
    _coll, req = make_collection_with_request()
    with patch.object(
        CollectionService,
        "get_saved_response",
        return_value={
            "id": 99,
            "request_id": req.id,
            "name": "Dict headers",
            "status": "OK",
            "code": 200,
            "headers": {"Set-Cookie": "s=1", "X-Trace": "abc"},
            "body": "{}",
            "preview_language": "json",
            "original_request": None,
            "created_at": None,
            "body_size": 2,
        },
    ):
        detail = execute_workspace_query("saved_response", session_id=_session(), target_id=99)
    assert "Header: Set-Cookie:" in detail
    assert REDACTED_PLACEHOLDER in detail
    assert "Header: X-Trace: abc" in detail


def test_run_scope_elapsed_ms_integer_format(make_collection_with_request: Any) -> None:
    """Run scope formats elapsed_ms as an integer like other scopes."""
    coll, _req = make_collection_with_request()
    run = RunHistoryService.create_run(collection_id=coll.id, total_requests=1)
    RunHistoryService.add_result(
        run["id"],
        request_name="Timed",
        request_method="GET",
        status_code=200,
        elapsed_ms=142.7,
        test_passed=0,
        test_failed=0,
    )
    RunHistoryService.finish_run(run["id"], status="completed", total_tests=0, passed=0, failed=0)
    detail = execute_workspace_query("run", session_id=_session(), target_id=run["id"])
    assert "· 142 ms" in detail
    assert "142.7" not in detail


def test_target_id_defaults_and_fallbacks(make_collection_with_request: Any) -> None:
    """Default target_id resolution and missing-id fallbacks."""
    coll, req = make_collection_with_request()
    folder = LocalScriptService.create_folder("f")
    script = LocalScriptService.create_script(folder.id, "s", language="javascript", content="")
    script_id = script.id
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "active_collection_id": coll.id,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": req.name,
                    "request_id": req.id,
                    "collection_id": coll.id,
                    "local_script_id": script_id,
                    "is_active": True,
                }
            ],
        },
    )
    assert "not found" not in execute_workspace_query("request", session_id=session_id).lower()
    assert execute_workspace_query("history_entry", session_id=session_id).startswith(
        "Set target_id"
    )
    assert execute_workspace_query("saved_response", session_id=session_id).startswith(
        "Set target_id"
    )
    assert execute_workspace_query("run", session_id=session_id).startswith("Set target_id")

    empty = _session()
    assert "No request id" in execute_workspace_query("request", session_id=empty)
    assert "No collection id" in execute_workspace_query("runs", session_id=empty)
    assert "No script id" in execute_workspace_query("script", session_id=empty)


def test_output_capped_to_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Oversized scope output is truncated below the OpenHands TextContent limit."""
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "active_collection_id": None,
            "current_env_id": None,
            "active_response": None,
            "tabs": [],
        },
    )
    monkeypatch.setattr(
        "services.ai.chat.tools.workspace_query.executor._render_overview",
        lambda snap: "x" * 60000,
    )
    out = execute_workspace_query("overview", session_id=session_id)
    assert len(out) <= _MAX_OUTPUT_CHARS
    assert out.rstrip().endswith("narrow with a more specific scope, target_id, or search.)")


def test_local_scripts_scope() -> None:
    """local_scripts scope lists script links from the local-script tree."""
    folder = LocalScriptService.create_folder("ws_lib")
    script = LocalScriptService.create_script(
        folder.id,
        "ws_helper",
        language="python",
        module_format="esm",
        content="print('x')",
    )
    text = execute_workspace_query("local_scripts", session_id=_session())
    assert f"postmark://script/{script.id}" in text
    assert "python/esm" in text


def test_collection_scope(make_collection_with_request: Any) -> None:
    """Collection scope renders folder config and child links."""
    coll, req = make_collection_with_request()
    CollectionService.update_collection(
        coll.id,
        description="Folder docs",
        variables=[{"key": "host", "value": "localhost", "enabled": True, "type": "default"}],
    )
    text = execute_workspace_query("collection", session_id=_session(), target_id=coll.id)
    assert f"postmark://collection/{coll.id}" in text
    assert f"postmark://request/{req.id}" in text
    assert "Folder docs" in text
    assert "host = localhost" in text
    missing = execute_workspace_query("collection", session_id=_session(), target_id=999999)
    assert "not found" in missing


def test_recent_history_scope(
    make_collection_with_request: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """recent_history lists workspace-wide sends with request links."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    _coll, req = make_collection_with_request()
    settings = HistorySettingsManager()
    entry_id = RequestHistoryService.record_send(
        identity={
            "request_id": req.id,
            "request_name": req.name,
            "method": "GET",
            "url": "http://hist.example/",
        },
        response={"status_code": 200, "elapsed_ms": 5.0},
        original_request={"method": "GET", "url": "http://hist.example/"},
        settings=settings,
    )
    assert entry_id is not None
    text = execute_workspace_query("recent_history", session_id=_session())
    assert f"postmark://request/{req.id}" in text
    assert f"postmark://history/{entry_id}" in text
    assert f"target_id={entry_id}" in text
    assert "[id=" not in text
    follow_block = text.split("Ids for follow-up calls")[-1]
    assert "postmark://" not in follow_block


def test_active_response_console_logs() -> None:
    """active_response renders bounded, redacted console log lines from the snapshot."""
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [{"index": 0, "tab_type": "request", "name": "R", "is_active": True}],
            "active_response": {
                "code": 200,
                "status": "OK",
                "console_logs": [
                    {"level": "log", "message": "hello from script"},
                    {"level": "error", "message": "boom"},
                    {"level": "log", "message": "token=CONSOLESECRET"},
                    {"level": "log", "message": '{"access_token":"LOGSECRET"}'},
                ],
            },
        },
    )
    text = execute_workspace_query("active_response", session_id=session_id)
    assert "Console:" in text
    assert "log: hello from script" in text
    assert "error: boom" in text
    assert "CONSOLESECRET" not in text
    assert "LOGSECRET" not in text
    assert REDACTED_PLACEHOLDER in text


def test_search_matches_body(make_collection_with_request: Any) -> None:
    """Search matches redacted request bodies and descriptions."""
    _coll, req = make_collection_with_request(
        req_name="BodyHit",
        url="http://x",
    )
    CollectionService.update_request(
        req.id,
        body='{"checkout_id": "abc123"}',
        body_mode="raw",
        description="Handles checkout_id lookup",
    )
    text = execute_workspace_query("search", session_id=_session(), search="checkout_id")
    assert f"postmark://request/{req.id}" in text
    assert "body/description match" in text


def test_active_response_variable_changes() -> None:
    """active_response masks camelCase secrets in pre/post variable changes."""
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [{"index": 0, "tab_type": "request", "name": "R", "is_active": True}],
            "active_response": {
                "code": 200,
                "status": "OK",
                "pre_request_variable_changes": {
                    "api_key": "sekrit",
                    "authToken": "VARSECRET",
                    "host": "localhost",
                },
                "variable_changes": {
                    "token": "tok_secret",
                    "accessToken": "ACCSECRET",
                    "sessionSecret": "SESSSECRET",
                    "count": "3",
                },
            },
        },
    )
    text = execute_workspace_query("active_response", session_id=session_id)
    assert "Pre-request variable changes:" in text
    assert "Variable changes:" in text
    for secret in ("sekrit", "tok_secret", "VARSECRET", "ACCSECRET", "SESSSECRET"):
        assert secret not in text
    assert "***masked***" in text
    assert "localhost" in text
    assert "count" in text


def test_active_response_timing() -> None:
    """active_response renders a compact non-zero timing line."""
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [{"index": 0, "tab_type": "request", "name": "R", "is_active": True}],
            "active_response": {
                "code": 200,
                "timing": {
                    "dns_ms": 12.0,
                    "tcp_ms": 0.0,
                    "tls_ms": 5.0,
                    "ttfb_ms": 100.0,
                    "download_ms": 0.0,
                    "process_ms": 2.0,
                },
            },
        },
    )
    text = execute_workspace_query("active_response", session_id=session_id)
    assert "Timing: dns 12 ms · tls 5 ms · ttfb 100 ms · process 2 ms" in text
    assert "tcp" not in text


def test_active_response_passing_tests() -> None:
    """active_response lists passing test names outside the failure block."""
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [{"index": 0, "tab_type": "request", "name": "R", "is_active": True}],
            "active_response": {
                "code": 200,
                "test_summary": {"passed": 2, "failed": 1},
                "test_results": [
                    {"name": "ok one", "passed": True},
                    {"name": "ok two", "passed": True},
                    {"name": "bad one", "passed": False, "error": "nope"},
                ],
            },
        },
    )
    text = execute_workspace_query("active_response", session_id=session_id)
    assert "Passing tests:" in text
    assert "passed: ok one" in text
    assert "failed: bad one" in text


def test_active_response_network() -> None:
    """active_response renders a compact network line."""
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [{"index": 0, "tab_type": "request", "name": "R", "is_active": True}],
            "active_response": {
                "code": 200,
                "network": {
                    "http_version": "HTTP/1.1",
                    "remote_address": "203.0.113.10:443",
                    "tls_protocol": "TLSv1.3",
                    "cipher_name": "TLS_AES_128_GCM_SHA256",
                },
                "request_headers_size": 120,
                "response_headers_size": 80,
                "size_bytes": 512,
            },
        },
    )
    text = execute_workspace_query("active_response", session_id=session_id)
    assert "Network: HTTP/1.1 · 203.0.113.10:443 · TLS TLSv1.3" in text
    assert "Sizes: req hdr 120 B · resp hdr 80 B" in text


def test_globals_scope(tmp_path: Any, monkeypatch: Any) -> None:
    """Globals scope lists persisted pm.globals with secrets masked."""
    globals_path = tmp_path / "globals.json"
    globals_path.write_text(
        '{"api_key": "sekrit", "region": "eu-west"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "services.scripting.context._GLOBALS_PATH",
        globals_path,
    )
    text = execute_workspace_query("globals", session_id=_session())
    assert "api_key" in text
    assert "region = eu-west" in text
    assert "sekrit" not in text
    assert "***masked***" in text


def test_snippets_scope() -> None:
    """Snippets scope lists user snippets."""
    sid = SnippetService.create(
        name="Auth helper",
        language="javascript",
        body="pm.test('auth', () => {});",
        category="Tests",
        context="test",
    )
    text = execute_workspace_query("snippets", session_id=_session())
    assert f"target_id={sid}" in text
    assert "[id=" not in text
    assert "Auth helper" in text
    assert "javascript / Tests" in text
    assert "pm.test('auth'" in text


def test_snippet_scope() -> None:
    """Snippet scope renders one user snippet body."""
    sid = SnippetService.create(
        name="Ping",
        language="python",
        body="print('pong')",
        category="Helpers",
    )
    text = execute_workspace_query("snippet", session_id=_session(), target_id=sid)
    assert "Ping" in text
    assert "print('pong')" in text


def test_search_matches_folder_scripts(make_collection_with_request: Any) -> None:
    """Search matches collection folder pre-request scripts."""
    coll, _req = make_collection_with_request()
    CollectionService.update_collection(
        coll.id,
        events=[{"listen": "prerequest", "script": {"exec": ["folder_marker_xyz"]}}],
    )
    text = execute_workspace_query("search", session_id=_session(), search="folder_marker")
    assert f"postmark://collection/{coll.id}" in text
    assert "folder script match" in text


def test_search_matches_local_scripts() -> None:
    """Search matches local script names and bodies."""
    folder = LocalScriptService.create_folder("search_lib")
    script = LocalScriptService.create_script(
        folder.id,
        "search_target",
        language="javascript",
        content="const marker_local_xyz = 1;",
    )
    text = execute_workspace_query("search", session_id=_session(), search="marker_local_xyz")
    assert f"postmark://script/{script.id}" in text
    assert "local script match" in text


def test_request_history_rollup(
    make_collection_with_request: Any,
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    """request_history includes a send summary rollup."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    _coll, req = make_collection_with_request()
    settings = HistorySettingsManager()
    for code in (200, 200, 500):
        RequestHistoryService.record_send(
            identity={
                "request_id": req.id,
                "request_name": req.name,
                "method": "GET",
                "url": "http://rollup.example/",
            },
            response={"status_code": code, "elapsed_ms": 10.0},
            original_request={"method": "GET", "url": "http://rollup.example/"},
            settings=settings,
        )
    text = execute_workspace_query("request_history", session_id=_session(), target_id=req.id)
    assert "Summary: 3 sends · 2 succeeded · 1 failed" in text
    assert "error rate" in text
    assert "median" in text
    assert "p95" in text
    assert "statuses:" in text


def test_search_matches_headers(make_collection_with_request: Any) -> None:
    """Search matches request headers and auth configuration."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        headers=[{"key": "X-Custom-Trace", "value": "trace_marker_abc"}],
        auth={"type": "bearer", "bearer": [{"key": "token", "value": "x", "type": "string"}]},
    )
    header_text = execute_workspace_query(
        "search", session_id=_session(), search="trace_marker_abc"
    )
    assert f"postmark://request/{req.id}" in header_text
    assert "header match" in header_text
    auth_text = execute_workspace_query("search", session_id=_session(), search="bearer")
    assert f"postmark://request/{req.id}" in auth_text
    assert "auth match" in auth_text


def test_script_versions_scope() -> None:
    """script_versions scope lists local script snapshots."""
    from services.script_version_service import ScriptVersionService

    folder = LocalScriptService.create_folder("ver_lib")
    script = LocalScriptService.create_script(
        folder.id,
        "versioned",
        language="javascript",
        content="console.log(1);",
    )
    captured = ScriptVersionService.capture(
        local_script_id=script.id,
        script_type="local_script",
        content="console.log(1);",
        language="javascript",
    )
    assert captured is not None
    text = execute_workspace_query("script_versions", session_id=_session(), target_id=script.id)
    assert f"postmark://script/{script.id}" in text
    assert f"target_id={captured['id']}" in text
    assert "[id=" not in text


def test_script_version_scope() -> None:
    """script_version scope renders one snapshot body."""
    from services.script_version_service import ScriptVersionService

    folder = LocalScriptService.create_folder("ver_one")
    script = LocalScriptService.create_script(
        folder.id,
        "snap",
        language="python",
        content="print('old')",
    )
    captured = ScriptVersionService.capture(
        local_script_id=script.id,
        script_type="local_script",
        content="print('snap_body')",
        language="python",
    )
    assert captured is not None
    text = execute_workspace_query(
        "script_version", session_id=_session(), target_id=captured["id"]
    )
    assert "print('snap_body')" in text


def test_script_scope_shows_path_and_module_format() -> None:
    """Script scope includes breadcrumb path and module format."""
    folder = LocalScriptService.create_folder("lib")
    script = LocalScriptService.create_script(
        folder.id,
        "helper",
        language="typescript",
        module_format="esm",
        content="export const x = 1;",
    )
    text = execute_workspace_query("script", session_id=_session(), target_id=script.id)
    assert "lib / helper" in text
    assert "typescript/esm" in text


def test_runs_scope_includes_iteration_metadata(make_collection_with_request: Any) -> None:
    """Runs scope shows iterations, skipped, and duration_ms when non-default."""
    coll, _req = make_collection_with_request()
    run = RunHistoryService.create_run(collection_id=coll.id, total_requests=2, iterations=3)
    RunHistoryService.finish_run(
        run["id"],
        status="completed",
        total_tests=0,
        passed=0,
        failed=0,
        skipped=1,
        duration_ms=1500,
    )
    text = execute_workspace_query("runs", session_id=_session(), target_id=coll.id)
    assert "3 iter" in text
    assert "1 skipped" in text
    assert "1500 ms total" in text


def test_runs_scope_hides_default_iteration_noise(make_collection_with_request: Any) -> None:
    """Runs scope omits 1 iter and 0 skipped on the common case."""
    coll, _req = make_collection_with_request()
    run = RunHistoryService.create_run(collection_id=coll.id, total_requests=1, iterations=1)
    RunHistoryService.finish_run(
        run["id"],
        status="completed",
        total_tests=0,
        passed=0,
        failed=0,
        skipped=0,
        duration_ms=100,
    )
    text = execute_workspace_query("runs", session_id=_session(), target_id=coll.id)
    assert "1 iter" not in text
    assert "0 skipped" not in text


def test_insights_missing_tests(make_collection_with_request: Any) -> None:
    """Insights scope lists requests without tests or assertions."""
    _coll, req = make_collection_with_request(req_name="Untested")
    text = execute_workspace_query("insights", session_id=_session())
    assert f"postmark://request/{req.id}" in text
    assert "no test script or assertions" in text


def test_request_unresolved_variables(make_collection_with_request: Any) -> None:
    """Request scope lists unresolved {{variables}} after substitution."""
    _coll, req = make_collection_with_request(url="http://{{missing_host}}/path")
    text = execute_workspace_query("request", session_id=_session(), target_id=req.id)
    assert "Unresolved: missing_host" in text


def test_request_script_set_variable_not_unresolved(make_collection_with_request: Any) -> None:
    """Pre-request script assignments are excluded from unresolved {{var}} warnings."""
    _coll, req = make_collection_with_request(url="http://{{dynamic_host}}/path")
    CollectionService.update_request(
        req.id,
        scripts={"pre_request": "pm.environment.set('dynamic_host', 'api.example.com');"},
    )
    text = execute_workspace_query("request", session_id=_session(), target_id=req.id)
    assert "Unresolved:" not in text


def test_search_auth_match_does_not_probe_secrets(make_collection_with_request: Any) -> None:
    """Search auth matching uses redacted auth, not raw secret values."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        auth={
            "type": "bearer",
            "bearer": [{"key": "token", "value": "super_secret_probe_xyz", "type": "string"}],
        },
    )
    text = execute_workspace_query("search", session_id=_session(), search="super_secret_probe_xyz")
    assert "auth match" not in text


def test_request_scope_masks_collection_secret_variables(
    make_collection_with_request: Any,
) -> None:
    """Collection secret-typed variables mask on scope=request like scope=collection."""
    coll, req = make_collection_with_request()
    CollectionService.update_collection(
        coll.id,
        variables=[
            {
                "key": "apiToken",
                "value": "sk-live-secret",
                "type": "secret",
                "enabled": True,
            }
        ],
    )
    request_text = execute_workspace_query("request", session_id=_session(), target_id=req.id)
    assert "sk-live-secret" not in request_text
    assert SECRET_PLACEHOLDER in request_text
    collection_text = execute_workspace_query(
        "collection", session_id=_session(), target_id=coll.id
    )
    assert SECRET_PLACEHOLDER in collection_text


def test_active_tab_masks_collection_secret_variables(
    make_collection_with_request: Any,
) -> None:
    """Active tab variable rows mask collection secret-typed variables."""
    coll, req = make_collection_with_request()
    CollectionService.update_collection(
        coll.id,
        variables=[
            {
                "key": "apiToken",
                "value": "sk-live-secret",
                "type": "secret",
                "enabled": True,
            }
        ],
    )
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": req.name,
                    "request_id": req.id,
                    "is_active": True,
                }
            ],
        },
    )
    text = execute_workspace_query("active_tab", session_id=session_id)
    assert "sk-live-secret" not in text
    assert SECRET_PLACEHOLDER in text


def test_snapshot_active_response_test_counts_before_truncate() -> None:
    """Test summary counts the full result list, not the capped copy."""
    from types import SimpleNamespace

    from ui.main_window.ai_chat_runs import _AiChatRunsMixin

    results = [{"name": f"t{i}", "passed": i != 20} for i in range(21)]
    viewer = SimpleNamespace(
        has_live_response=lambda: True,
        get_save_response_data=lambda: {"code": 200, "status": "OK"},
        _last_live_response={"test_results": results},
        _test_results=None,
    )
    ctx = SimpleNamespace(response_viewer=viewer)
    data = _AiChatRunsMixin()._snapshot_active_response(ctx)
    assert data is not None
    assert data["test_summary"] == {"passed": 20, "failed": 1}
    assert any(not row.get("passed") for row in data["test_results"])


def test_active_response_late_failure_in_rendered_block() -> None:
    """A failure beyond the copied cap still appears in the failing-tests block."""
    session_id = _session()
    failure = {"name": "late fail", "passed": False, "error": "boom"}
    passes = [{"name": f"ok{i}", "passed": True} for i in range(20)]
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [{"index": 0, "tab_type": "request", "name": "R", "is_active": True}],
            "active_response": {
                "code": 200,
                "status": "OK",
                "test_summary": {"passed": 20, "failed": 1},
                "test_results": [failure, *passes],
            },
        },
    )
    text = execute_workspace_query("active_response", session_id=session_id)
    assert "Tests: 20 passed, 1 failed" in text
    assert "failed: late fail" in text


def test_search_deep_body_match_warns_partial_not_authoritative(
    make_collection_with_request: Any,
) -> None:
    """A body match beyond the scan cap must not claim an authoritative negative."""
    coll, _req0 = make_collection_with_request(req_name="z000", url="http://z000.example/")
    for i in range(1, 249):
        create_new_request(coll.id, "GET", f"http://z{i:03d}.example/", f"z{i:03d}")
    last = create_new_request(coll.id, "GET", "http://z249.example/", "z249")
    CollectionService.update_request(
        last.id,
        body="DEEP_ONLY_BODY_MARKER_XYZ",
        body_mode="raw",
    )
    text = execute_workspace_query(
        "search", session_id=_session(), search="DEEP_ONLY_BODY_MARKER_XYZ"
    )
    assert "do not retry" not in text
    assert "limited to the first" in text


def test_search_deep_local_script_match_warns_partial(
    make_collection_with_request: Any,
) -> None:
    """A local-script match beyond the scan cap must not claim an authoritative negative."""
    make_collection_with_request(req_name="OnlyReq", url="http://only.example/")
    folder = LocalScriptService.create_folder("bulk_scripts")
    for i in range(249):
        LocalScriptService.create_script(
            folder.id,
            f"z{i:03d}",
            language="javascript",
            content="// filler",
        )
    LocalScriptService.create_script(
        folder.id,
        "z249",
        language="javascript",
        content="const DEEP_LOCAL_MARKER_XYZ = 1;",
    )
    text = execute_workspace_query("search", session_id=_session(), search="DEEP_LOCAL_MARKER_XYZ")
    assert "do not retry" not in text
    assert "limited to the first" in text


def test_redact_env_values_skips_malformed_rows() -> None:
    """Malformed env variable rows do not crash redaction."""
    from services.ai.chat.tools.workspace_query.helpers import _redact_env_values

    rows = _redact_env_values(["oops", None, {"type": "secret", "key": "k", "value": "x"}])
    assert len(rows) == 1
    assert rows[0]["value"] == SECRET_PLACEHOLDER


def test_search_header_match_uses_masked_value(make_collection_with_request: Any) -> None:
    """Header search must not match raw secret header values."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        headers=[{"key": "Authorization", "value": "Bearer SECRET_PROBE_XYZ"}],
    )
    secret_text = execute_workspace_query(
        "search", session_id=_session(), search="SECRET_PROBE_XYZ"
    )
    assert "header match" not in secret_text
    CollectionService.update_request(
        req.id,
        headers=[{"key": "X-Custom-Trace", "value": "trace_marker_abc"}],
    )
    trace_text = execute_workspace_query("search", session_id=_session(), search="trace_marker_abc")
    assert "header match" in trace_text


def test_search_header_and_auth_match_deduped(make_collection_with_request: Any) -> None:
    """A request matching both header and auth appears once in the header/auth section."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        headers=[{"key": "X-Auth-Kind", "value": "bearer-ish"}],
        auth={"type": "bearer", "bearer": [{"key": "token", "value": "x", "type": "string"}]},
    )
    text = execute_workspace_query("search", session_id=_session(), search="bearer")
    section = text.split("Header/auth matches:", 1)[1].split("\n\n", 1)[0]
    assert section.count(f"postmark://request/{req.id}") == 1


def test_scope_variable_lines_uses_get_environment_not_fetch_all(
    make_collection_with_request: Any,
) -> None:
    """In-scope variable rendering loads one environment row, not the full table."""
    _coll, req = make_collection_with_request()
    env = EnvironmentService.create_environment(
        "MaskEnv",
        values=[{"key": "api_key", "value": "sekrit", "type": "secret", "enabled": True}],
    )
    session_id = _session()
    set_workspace_snapshot(session_id, {"current_env_id": env.id})
    with patch.object(
        EnvironmentService,
        "fetch_all",
        side_effect=AssertionError("fetch_all should not be called"),
    ):
        text = execute_workspace_query(
            "request",
            session_id=session_id,
            target_id=req.id,
        )
    assert "sekrit" not in text
    assert SECRET_PLACEHOLDER in text


def test_render_request_resolves_variable_map_once(
    make_collection_with_request: Any,
) -> None:
    """Request scope builds the combined variable detail map once per render."""
    _coll, req = make_collection_with_request()
    with patch.object(
        EnvironmentService,
        "build_combined_variable_detail_map",
        wraps=EnvironmentService.build_combined_variable_detail_map,
    ) as detail_mock:
        execute_workspace_query("request", session_id=_session(), target_id=req.id)
    assert detail_mock.call_count == 1


def test_recent_history_uses_sidebar_limit_25(
    make_collection_with_request: Any,
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    """Recent history asks the service for 25 rows instead of slicing 500."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    _coll, req = make_collection_with_request()
    captured: dict[str, int] = {}

    def _spy_list_entries_for_sidebar(**kwargs: Any) -> list[Any]:
        captured["limit"] = int(kwargs.get("limit", 0))
        return []

    monkeypatch.setattr(
        "services.request_history_service.request_history_repository.list_entries_for_sidebar",
        _spy_list_entries_for_sidebar,
    )
    execute_workspace_query("recent_history", session_id=_session())
    assert captured.get("limit") == 25


def test_snippets_scope_caps_row_count(monkeypatch: Any) -> None:
    """Snippets list applies the standard result-row cap with overflow note."""
    rows = [
        {
            "id": i,
            "name": f"Snippet {i}",
            "category": "Helpers",
            "context": "both",
            "body": f"body {i}",
        }
        for i in range(60)
    ]

    def _fake_list_all(language: str) -> list[dict[str, Any]]:
        return rows if language == "javascript" else []

    monkeypatch.setattr(
        "services.ai.chat.tools.workspace_query.render.scripts.SnippetService.list_all",
        _fake_list_all,
    )
    text = execute_workspace_query("snippets", session_id=_session())
    assert "[partial]" in text
    assert "of 60 snippets" in text


# --- Round 2 inspection tests ---


def test_redact_auth_v20_dict_masked() -> None:
    """Postman v2.0 dict-shaped auth masks credential values."""
    from services.ai.chat.tools.workspace_query.helpers import _redact_auth

    out = _redact_auth({"type": "basic", "basic": {"username": "u", "password": "p"}})
    assert out is not None
    assert out["basic"]["password"] == REDACTED_PLACEHOLDER
    templated = _redact_auth({"type": "basic", "basic": {"username": "{{user}}", "password": "p"}})
    assert templated is not None
    assert templated["basic"]["username"] == "{{user}}"


def test_redact_url_userinfo_masked() -> None:
    """URL userinfo is redacted unless it uses template variables."""
    from services.ai.chat.tools.workspace_query.helpers import _redact_url

    masked = _redact_url("https://u:p@x.io/a?k=1")
    assert "u:p" not in masked
    assert REDACTED_PLACEHOLDER in masked
    templated = _redact_url("https://{{user}}:{{pw}}@x.io")
    assert templated == "https://{{user}}:{{pw}}@x.io"


def test_secret_key_matching_compound_names() -> None:
    """Compound secret key names are masked in headers, params, and bodies."""
    from services.ai.chat.tools.workspace_query.helpers import (
        _mask_header_value,
        _mask_param_value,
        _redact_request_body,
    )

    assert _mask_header_value("X-Stripe-Secret-Key", "sk-1") == REDACTED_PLACEHOLDER
    assert _mask_param_value("client_secret", "s") == REDACTED_PLACEHOLDER
    body = _redact_request_body(
        '{"user_password":"x","author":"a","monkey":"m"}',
        {"body_mode": "raw", "body_options": {"raw": {"language": "json"}}},
    )
    parsed = json.loads(body)
    assert parsed["user_password"] == SECRET_PLACEHOLDER
    assert parsed["author"] == "a"


def test_search_body_match_beyond_preview(make_collection_with_request: Any) -> None:
    """Search matches body content beyond the 800-char preview window."""
    _coll, req = make_collection_with_request()
    needle = "ZZZNEEDLE999"
    padding = "x" * 900
    CollectionService.update_request(
        req.id,
        body=json.dumps({"data": padding + needle}),
        body_mode="raw",
        body_options={"raw": {"language": "json"}},
    )
    text = execute_workspace_query("search", session_id=_session(), search=needle)
    assert "body/description match" in text


def test_collection_tree_nesting_and_path(make_collection_with_request: Any) -> None:
    """Collection tree indents children and shows path when filtered."""
    coll, _req = make_collection_with_request(name="Parent")
    child = CollectionService.create_collection("Child", parent_id=coll.id)
    create_new_request(child.id, "GET", "http://x/a", "Dup")
    create_new_request(coll.id, "GET", "http://x/b", "Dup")
    unfiltered = execute_workspace_query("collection_tree", session_id=_session())
    assert "  - [Dup]" in unfiltered or "  - [" in unfiltered
    filtered = execute_workspace_query(
        "collection_tree",
        session_id=_session(),
        search="Dup",
    )
    assert filtered.count(" · in ") >= 2


def test_format_ts_local() -> None:
    """Timestamps format to local wall time or pass through garbage."""
    from datetime import UTC, datetime

    from services.ai.chat.tools.workspace_query.helpers import _format_ts

    dt = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    assert _format_ts(dt) == dt.astimezone().strftime("%Y-%m-%d %H:%M")
    assert _format_ts("not-a-date") == "not-a-date"


def test_truncate_output_no_severed_link() -> None:
    """Truncation avoids severing postmark:// links mid-URL."""
    from services.ai.chat.tools.workspace_query.executor import _truncate_output

    link = "[Req](postmark://request/12345)"
    filler = "y" * 47000
    text = filler + "\n" + link + "z" * 2000
    out = _truncate_output(text)
    assert "](postmark://" not in out or link in out


def test_active_response_send_error_masked() -> None:
    """Failed sends surface as masked Last send FAILED lines."""
    from services.ai.chat.tools.workspace_query.render.live import _render_active_response

    snap = {"active_response": {"send_error": "Connection refused token=sk-live-1"}, "tabs": []}
    text = _render_active_response(snap)
    assert "Last send FAILED" in text
    assert "sk-live-1" not in text


def test_active_response_stored_pointer() -> None:
    """Stored history viewing points to history_entry scope."""
    from services.ai.chat.tools.workspace_query.render.live import _render_active_response

    snap = {"active_response": {"viewing_stored_entry_id": 7}, "tabs": []}
    text = _render_active_response(snap)
    assert "history_entry" in text
    assert "target_id=7" in text


def test_snapshot_missing_live_scope() -> None:
    """Missing snapshot reports unavailable for live scopes only."""
    from services.ai.chat.tools.workspace_query.executor import _dispatch_workspace_query

    assert "snapshot unavailable" in _dispatch_workspace_query(
        "open_tabs",
        session_id="missing-session",
    )
    assert "No collections" in _dispatch_workspace_query(
        "collection_tree",
        session_id="missing-session",
    )


def test_env_named_in_variables_header(make_collection_with_request: Any) -> None:
    """Request scope names the active environment in the variables header."""
    coll, req = make_collection_with_request()
    env = EnvironmentService.create_environment(
        "Staging",
        values=[{"key": "host", "value": "localhost", "enabled": True, "type": "default"}],
    )
    session_id = _session()
    set_workspace_snapshot(session_id, {"current_env_id": env.id, "tabs": []})
    text = execute_workspace_query("request", session_id=session_id, target_id=req.id)
    assert "Variables in scope (environment: Staging):" in text


def test_test_error_masked(monkeypatch: Any) -> None:
    """Failing test error strings are masked in active response and run output."""
    from services.ai.chat.tools.workspace_query.render.collections import _render_run
    from services.ai.chat.tools.workspace_query.render.live import _render_active_response

    snap = {
        "active_response": {
            "code": 200,
            "status": "OK",
            "test_summary": {"passed": 0, "failed": 1},
            "test_results": [
                {
                    "name": "token check",
                    "passed": False,
                    "error": "expected token=sk-live-1 to equal ok",
                }
            ],
        },
        "tabs": [{"index": 0, "is_active": True, "tab_type": "request", "name": "R"}],
    }
    live_text = _render_active_response(snap)
    assert "sk-live-1" not in live_text
    assert "failed:" in live_text

    results = [
        {
            "request_method": "GET",
            "request_name": "R",
            "status_code": 500,
            "test_passed": 0,
            "test_failed": 1,
            "test_results": [
                {"name": "t", "passed": False, "error": "token=sk-live-1"},
            ],
        }
    ]
    monkeypatch.setattr(
        "services.ai.chat.tools.workspace_query.render.collections.examples.RunHistoryService.get_run_results",
        lambda _rid: results,
    )
    run_out = _render_run(1)
    assert "sk-live-1" not in run_out
    assert "test_results:" not in run_out


def test_assertion_redaction(make_collection_with_request: Any) -> None:
    """Declarative assertion expected values mask credential literals."""
    _coll, req = make_collection_with_request()
    AssertionService.save_for_request(
        req.id,
        [
            AssertionDict(
                subject="header Authorization",
                operator="equals",
                expected="Bearer sk-1",
                enabled=True,
                order_index=0,
            ),
            AssertionDict(
                subject="status code",
                operator="equals",
                expected="200",
                enabled=True,
                order_index=1,
            ),
        ],
    )
    text = execute_workspace_query("request", session_id=_session(), target_id=req.id)
    assert "sk-1" not in text
    assert "'200'" in text or "200" in text


def test_deferred_tab_uses_db(make_collection_with_request: Any) -> None:
    """Deferred request tabs load method/URL from the database."""
    _coll, req = make_collection_with_request(
        method="POST",
        url="http://deferred.example/path",
        req_name="Deferred",
    )
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": "Deferred",
                    "request_id": req.id,
                    "request_data": None,
                    "is_dirty": False,
                    "is_active": True,
                }
            ],
        },
    )
    text = execute_workspace_query("open_tabs", session_id=session_id)
    assert "POST" in text
    assert "deferred.example" in text
    assert "— GET " not in text


def test_capped_summary_wording(make_collection_with_request: Any, monkeypatch: Any) -> None:
    """Request history summary says 'latest 200 sends' when the list is capped."""
    _coll, req = make_collection_with_request()

    def _fake_list(_rid: int, search: str = "", **kwargs: Any) -> list[dict[str, Any]]:
        _ = search, kwargs
        return [
            {
                "id": i,
                "status_code": 200,
                "elapsed_ms": 10,
                "executed_at": "2026-07-01T00:00:00Z",
            }
            for i in range(200)
        ]

    monkeypatch.setattr(
        "services.ai.chat.tools.workspace_query.render.collections.history.RequestHistoryService.list_for_request",
        _fake_list,
    )
    text = execute_workspace_query(
        "request_history",
        session_id=_session(),
        target_id=req.id,
    )
    assert "latest 200 sends" in text


def test_iteration_prefix(monkeypatch: Any) -> None:
    """Multi-iteration run rows carry iter N prefixes."""
    from services.ai.chat.tools.workspace_query.render.collections import _render_run

    results = [
        {
            "request_method": "GET",
            "request_name": "Loop",
            "status_code": 200,
            "iteration": 0,
            "test_passed": 1,
            "test_failed": 0,
        },
        {
            "request_method": "GET",
            "request_name": "Loop",
            "status_code": 200,
            "iteration": 1,
            "test_passed": 1,
            "test_failed": 0,
        },
    ]
    monkeypatch.setattr(
        "services.ai.chat.tools.workspace_query.render.collections.examples.RunHistoryService.get_run_results",
        lambda _rid: results,
    )
    text = _render_run(1)
    assert "iter 1:" in text
    assert "iter 2:" in text


def test_sent_request_rendered(monkeypatch: Any) -> None:
    """History entry scope renders the sent request with masked headers."""
    detail = {
        "method": "GET",
        "url": "http://x",
        "headers": [],
        "original_request": {
            "method": "POST",
            "url": "http://sent.example/x",
            "sent_headers": [
                {"key": "Authorization", "value": "Bearer sk-1", "enabled": True},
            ],
        },
    }
    monkeypatch.setattr(
        "services.ai.chat.tools.workspace_query.render.collections.history.RequestHistoryService.get_entry",
        lambda _eid: {"id": 1},
    )
    monkeypatch.setattr(
        "services.ai.chat.tools.workspace_query.render.collections.history.RequestHistoryService.entry_to_detail_snapshot",
        lambda _entry: detail,
    )
    text = execute_workspace_query("history_entry", session_id=_session(), target_id=1)
    assert "Sent request" in text
    assert "sk-1" not in text


def test_effective_chain(make_collection_with_request: Any) -> None:
    """Request scope shows effective script chain and disabled inherited lines."""
    from database.database import get_session
    from database.models.collections.model.collection_model import CollectionModel
    from database.models.collections.model.request_model import RequestModel

    coll, req = make_collection_with_request()
    with get_session() as session:
        c = session.get(CollectionModel, coll.id)
        assert c is not None
        c.events = {"pre_request": "// coll pre", "test": "// coll test"}
        r = session.get(RequestModel, req.id)
        assert r is not None
        r.scripts = {
            "disabled_inherited": [
                {"collection_id": coll.id, "script_type": "pre_request"},
            ],
        }
        session.commit()

    text = execute_workspace_query("request", session_id=_session(), target_id=req.id)
    assert "Effective script chain" in text
    assert "disabled for this request" in text
    assert f"postmark://collection/{coll.id}" in text


def test_resolved_url_match(make_collection_with_request: Any) -> None:
    """Resolved-URL search matches env-substituted URLs without duplicate rows."""
    _coll, req = make_collection_with_request(
        req_name="stripe-pay",
        url="{{base}}/pay",
    )
    env = EnvironmentService.create_environment(
        "API",
        values=[
            {"key": "base", "value": "https://api.stripe.com", "enabled": True, "type": "default"},
        ],
    )
    session_id = _session()
    set_workspace_snapshot(session_id, {"current_env_id": env.id, "tabs": []})
    text = execute_workspace_query("search", session_id=session_id, search="stripe")
    assert text.count(f"postmark://request/{req.id}") == 1
    assert "partial" in text


def test_environments_drilldown_full_list() -> None:
    """Environment drill-down lists all variables, not the 40-key summary cap."""
    values = [
        {"key": f"k{i}", "value": f"v{i}", "enabled": True, "type": "default"} for i in range(60)
    ]
    values[30] = {"key": "api_key", "value": "secret-val", "enabled": True, "type": "secret"}
    env = EnvironmentService.create_environment("Big Env", values=values)
    text = execute_workspace_query("environments", session_id=_session(), target_id=env.id)
    assert "k45 = v45" in text
    assert "…and 20 more" not in text
    assert SECRET_PLACEHOLDER in text
    assert "secret-val" not in text


def test_tab_scope_background_tab(make_collection_with_request: Any) -> None:
    """scope=tab renders a non-active background tab by 1-based index."""
    _coll, req = make_collection_with_request(method="PATCH", url="http://bg/tab")
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 1,
            "current_env_id": None,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": "Background",
                    "request_id": req.id,
                    "request_data": {
                        "method": "PATCH",
                        "url": "http://bg/tab",
                        "headers": [],
                        "auth": None,
                        "request_parameters": [],
                        "body": None,
                        "body_mode": "none",
                    },
                    "is_dirty": True,
                    "is_active": False,
                },
                {
                    "index": 1,
                    "tab_type": "request",
                    "name": "Active",
                    "request_id": None,
                    "request_data": {"method": "GET", "url": "http://active"},
                    "is_dirty": False,
                    "is_active": True,
                },
            ],
        },
    )
    text = execute_workspace_query("tab", session_id=session_id, target_id=1)
    assert "PATCH" in text
    assert "http://bg/tab" in text
    assert "Unsaved edits: yes" in text


def test_open_tabs_last_response_summary() -> None:
    """Open tabs show last-response status summaries from the snapshot."""
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": "Sent",
                    "request_id": 1,
                    "is_dirty": False,
                    "is_active": True,
                    "last_response": {"status_code": 201, "elapsed_ms": 42},
                }
            ],
        },
    )
    text = execute_workspace_query("open_tabs", session_id=session_id)
    assert "last: 201 (42 ms)" in text


def test_active_tab_local_overrides(make_collection_with_request: Any) -> None:
    """Active tab lists per-tab local variable overrides."""
    _coll, req = make_collection_with_request()
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "current_env_id": None,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": req.name,
                    "request_id": req.id,
                    "request_data": {"method": "GET", "url": "http://x", "headers": []},
                    "is_dirty": False,
                    "is_active": True,
                    "local_overrides": {"base_url": "http://override.example"},
                }
            ],
        },
    )
    text = execute_workspace_query("active_tab", session_id=session_id)
    assert "Local variable overrides" in text
    assert "base_url = http://override.example" in text


def test_settings_safe_subset() -> None:
    """Settings scope exposes runtime/history prefs but never AI secrets."""
    text = execute_workspace_query("settings", session_id=_session())
    assert "retention" in text.casefold()
    assert "ai/" not in text


def test_request_script_versions_scope(make_collection_with_request: Any) -> None:
    """request_script_versions lists pre_request and test version rows."""
    from services.script_version_service import ScriptVersionService

    _coll, req = make_collection_with_request()
    ScriptVersionService.capture(
        request_id=req.id,
        script_type="pre_request",
        content="// pre v1",
        language="javascript",
    )
    ScriptVersionService.capture(
        request_id=req.id,
        script_type="test",
        content="// test v1",
        language="javascript",
    )
    text = execute_workspace_query(
        "request_script_versions",
        session_id=_session(),
        target_id=req.id,
    )
    assert "pre_request" in text
    assert "test" in text
    assert "target_id=" in text
    assert "[id=" not in text


def test_list_rows_do_not_prime_bare_id_tags(
    make_collection_with_request: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """History/snippet/run/env list rows stay free of ``[id=N]`` priming tags."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    coll, req = make_collection_with_request()
    settings = HistorySettingsManager()
    entry_id = RequestHistoryService.record_send(
        identity={
            "request_id": req.id,
            "request_name": req.name,
            "method": "GET",
            "url": "http://x",
        },
        response={"status_code": 200, "elapsed_ms": 1.0},
        original_request={"method": "GET", "url": "http://x"},
        settings=settings,
    )
    assert entry_id is not None
    hist = execute_workspace_query("request_history", session_id=_session(), target_id=req.id)
    list_body = hist.split("Ids for follow-up calls")[0]
    assert "[id=" not in list_body
    assert f"postmark://history/{entry_id}" in hist
    assert f"target_id={entry_id}" in hist
    assert "tool arguments only" in hist

    run = RunHistoryService.create_run(collection_id=coll.id, total_requests=1)
    RunHistoryService.add_result(
        run["id"], request_name="One", request_method="GET", status_code=200
    )
    RunHistoryService.finish_run(run["id"], status="completed")
    runs = execute_workspace_query("runs", session_id=_session(), target_id=coll.id)
    runs_body = runs.split("Ids for follow-up calls")[0]
    assert "[id=" not in runs_body
    assert f"run #{run['id']}" not in runs_body
    assert f"target_id={run['id']}" in runs

    sid = SnippetService.create(
        name="Helper",
        language="javascript",
        body="// x",
        category="Utils",
    )
    snippets = execute_workspace_query("snippets", session_id=_session())
    snip_body = snippets.split("Ids for follow-up calls")[0]
    assert "[id=" not in snip_body
    assert f"target_id={sid}" in snippets

    env = EnvironmentService.create_environment("Staging", values=[])
    envs = execute_workspace_query("environments", session_id=_session())
    env_body = envs.split("Ids for follow-up calls")[0]
    assert f"(id={env.id})" not in env_body
    assert f"postmark://environment/{env.id}" in envs
    assert f"target_id={env.id}" in envs


def test_run_results_link_request_when_request_id_present(
    make_collection_with_request: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run result rows use named request deep-links when ``request_id`` is set."""
    _coll, req = make_collection_with_request(req_name="LinkedReq")
    run = RunHistoryService.create_run(collection_id=_coll.id, total_requests=1)
    RunHistoryService.add_result(
        run["id"],
        request_name="LinkedReq",
        request_method="GET",
        status_code=200,
    )
    RunHistoryService.finish_run(run["id"], status="completed")

    real_get = RunHistoryService.get_run_results

    def _patched(run_id: int) -> list[dict[str, Any]]:
        rows = real_get(run_id)
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["request_id"] = req.id
            out.append(item)
        return out

    monkeypatch.setattr(RunHistoryService, "get_run_results", staticmethod(_patched))
    text = execute_workspace_query("run", session_id=_session(), target_id=run["id"])
    assert f"postmark://request/{req.id}" in text
    assert "LinkedReq" in text


def test_search_partial_marker_appears_before_body(
    make_collection_with_request: Any,
) -> None:
    """Partial/authoritative markers are placed above search result body text."""
    coll, _req0 = make_collection_with_request(req_name="z000", url="http://z000.example/")
    for i in range(1, 249):
        create_new_request(coll.id, "GET", f"http://z{i:03d}.example/", f"z{i:03d}")
    text = execute_workspace_query("search", session_id=_session(), search="nonexistent-deep-xyz")
    partial_at = text.find("[partial]")
    auth_at = text.find("[authoritative]")
    body_at = text.find("Search results for")
    assert body_at >= 0
    marker_at = partial_at if partial_at >= 0 else auth_at
    assert marker_at >= 0
    assert marker_at < body_at
    assert "Request params tables" in text or "params tables" in text.casefold()


def test_overview_active_tab_is_named_link(make_collection_with_request: Any) -> None:
    """Overview active-tab line uses a deep-link, not a bare name or env id tag."""
    _coll, req = make_collection_with_request(req_name="ActiveOne")
    env = EnvironmentService.create_environment("Staging", values=[])
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "current_env_id": env.id,
            "active_tab_index": 0,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": "ActiveOne",
                    "request_id": req.id,
                    "is_active": True,
                }
            ],
        },
    )
    text = execute_workspace_query("overview", session_id=session_id)
    assert f"postmark://request/{req.id}" in text
    assert f"(id={env.id})" not in text
    assert f"postmark://environment/{env.id}" in text
    assert "Staging" in text


def test_runs_partial_marker_when_limit_binds(
    make_collection_with_request: Any,
    monkeypatch: Any,
) -> None:
    """Runs scope leads with [partial] when the latest-10 limit is saturated."""
    coll, _req = make_collection_with_request()
    fake_runs = [
        {
            "id": i,
            "status": "completed",
            "total_requests": 1,
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "avg_response_ms": 10,
            "iterations": 1,
            "skipped": 0,
            "duration_ms": 10,
            "started_at": "2026-07-01T12:00:00+00:00",
            "finished_at": "2026-07-01T12:00:01+00:00",
        }
        for i in range(1, 11)
    ]
    monkeypatch.setattr(
        RunHistoryService,
        "get_runs",
        lambda _cid, *, limit=50: fake_runs[:limit],
    )
    text = execute_workspace_query("runs", session_id=_session(), target_id=coll.id)
    assert text.startswith("[partial]")
    assert "Showing latest 10" in text


def test_recent_history_partial_marker_when_limit_binds(monkeypatch: Any) -> None:
    """Recent history leads with [partial] when the latest-25 limit is saturated."""
    fake = [
        {
            "id": i,
            "executed_at": "2026-07-01T12:00:00+00:00",
            "status_code": 200,
            "elapsed_ms": 12,
            "error": None,
            "request_id": None,
            "request_name": None,
            "source_label": f"draft {i}",
        }
        for i in range(1, 26)
    ]
    monkeypatch.setattr(
        RequestHistoryService,
        "list_for_sidebar",
        lambda *_a, **_k: fake,
    )
    text = execute_workspace_query("recent_history", session_id=_session())
    assert text.startswith("[partial]")
    assert "Showing latest 25" in text


def test_form_credential_param_redacted() -> None:
    """Form bodies redact credential= values via sensitive-key heuristics."""
    from services.ai.chat.tools.workspace_query.helpers import _redact_form_urlencoded_body

    out = _redact_form_urlencoded_body("grant_type=password&credential=super-secret")
    assert "super-secret" not in out
    assert "credential=" in out
    assert REDACTED_PLACEHOLDER in out
    assert "grant_type=password" in out


def test_env_sensitive_key_default_type_masked() -> None:
    """Env vars named like secrets are masked even when type is default."""
    from services.ai.chat.tools.workspace_query.helpers import _redact_env_values

    rows = _redact_env_values(
        [
            {"key": "api_key", "value": "live-secret", "type": "default", "enabled": True},
            {"key": "region", "value": "eu-west", "type": "default", "enabled": True},
        ]
    )
    by_key = {r["key"]: r["value"] for r in rows}
    assert by_key["api_key"] == SECRET_PLACEHOLDER
    assert by_key["region"] == "eu-west"


def test_opaque_body_kv_masking() -> None:
    """Opaque text bodies mask key=value credential pairs."""
    from services.ai.chat.tools.workspace_query.helpers import _redact_response_body

    out = _redact_response_body("debug dump token=sk-live-abc password=hunter2 ok", "text")
    assert "sk-live-abc" not in out
    assert "hunter2" not in out
    assert REDACTED_PLACEHOLDER in out
    assert "ok" in out


def test_overview_dirty_and_deferred_labels(make_collection_with_request: Any) -> None:
    """Overview shows dirty/method/URL; open_tabs marks deferred chips."""
    _coll, req = make_collection_with_request(req_name="DirtyTab")
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "captured_at": "2026-07-08 12:00:00",
            "current_env_id": None,
            "active_tab_index": 0,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": "DirtyTab",
                    "request_id": req.id,
                    "is_dirty": True,
                    "is_active": True,
                    "request_data": {
                        "method": "POST",
                        "url": "https://example.test/v1",
                    },
                },
                {
                    "index": 1,
                    "tab_type": "request",
                    "name": "Lazy",
                    "request_id": req.id,
                    "is_dirty": False,
                    "is_deferred": True,
                    "is_active": False,
                    "request_data": None,
                },
            ],
        },
    )
    overview = execute_workspace_query("overview", session_id=session_id)
    assert "dirty" in overview
    assert "POST" in overview
    assert "example.test" in overview
    assert "Snapshot captured at:" in overview
    tabs = execute_workspace_query("open_tabs", session_id=session_id)
    assert "[deferred]" in tabs
    assert "turn-start bar indices" in tabs


def test_truncate_output_leading_truncated_marker() -> None:
    """Char-capped output prepends [truncated] as well as the trailing footer."""
    from services.ai.chat.tools.workspace_query.executor import _truncate_output

    out = _truncate_output("x" * 60000)
    assert out.startswith("[truncated]")
    assert "narrow with a more specific scope" in out
    assert len(out) <= _MAX_OUTPUT_CHARS


def test_search_secret_like_needle_message() -> None:
    """Secret-like search needles get a partial redaction warning, not authoritative-empty."""
    text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="password=hunter2-secret",
    )
    assert "[authoritative]" not in text
    assert "secret-like" in text.casefold() or "redacted" in text.casefold()
    assert "[partial]" in text


def test_search_within_ids_refines_prior_list(make_collection_with_request: Any) -> None:
    """within_ids keeps only prior-list request hits for a second search needle."""
    coll = CollectionService.create_collection("RefineRoot")
    checkout_expedia = create_new_request(
        coll.id,
        "GET",
        "https://api.example.com/checkout?partner=expedia",
        "Checkout Expedia",
    )
    checkout_other = create_new_request(
        coll.id,
        "GET",
        "https://api.example.com/checkout?partner=other",
        "Checkout Other",
    )
    expedia_only = create_new_request(
        coll.id,
        "GET",
        "https://api.example.com/expedia/status",
        "Expedia Only",
    )
    first = execute_workspace_query("search", session_id=_session(), search="checkout")
    assert f"postmark://request/{checkout_expedia.id}" in first
    assert f"postmark://request/{checkout_other.id}" in first
    assert f"postmark://request/{expedia_only.id}" not in first

    refined = execute_workspace_query(
        "search",
        session_id=_session(),
        search="expedia",
        within_ids=[checkout_expedia.id, checkout_other.id],
    )
    assert "Restricted to 2 prior request ids" in refined
    assert f"postmark://request/{checkout_expedia.id}" in refined
    assert f"postmark://request/{checkout_other.id}" not in refined
    assert f"postmark://request/{expedia_only.id}" not in refined
    assert "[authoritative]" not in refined


def test_search_within_ids_empty_is_partial_not_authoritative(
    make_collection_with_request: Any,
) -> None:
    """Empty refine within a prior set is partial, not whole-workspace authoritative."""
    _coll, req = make_collection_with_request(req_name="NoExpedia")
    CollectionService.update_request(req.id, url="https://api.example.com/checkout")
    text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="expedia",
        within_ids=[req.id],
    )
    assert "[partial]" in text
    assert "[authoritative]" not in text
    assert "prior request" in text.casefold()


def test_request_history_search_url_fragment_and_empty_honesty(
    make_collection_with_request: Any,
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    """History search matches URL fragments; empty filter explains coverage."""
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
            "url": "https://api.example.com/v1?checkout=abc",
        },
        response={"status_code": 200, "elapsed_ms": 1.0},
        original_request={"method": "GET", "url": "https://api.example.com/v1?checkout=abc"},
        settings=settings,
    )
    hit = execute_workspace_query(
        "request_history",
        session_id=_session(),
        target_id=req.id,
        search="checkout=abc",
    )
    assert "postmark://history/" in hit
    miss = execute_workspace_query(
        "request_history",
        session_id=_session(),
        target_id=req.id,
        search="no-such-fragment-xyz",
    )
    assert "No send history matches" in miss
    assert "URL, name, method, and status only" in miss
    assert "[partial]" in miss


def test_search_within_ids_invalid_errors_not_unrestricted(
    make_collection_with_request: Any,
) -> None:
    """Junk within_ids must error — never fall through to full-workspace search."""
    _coll, req = make_collection_with_request(req_name="VisibleEverywhere")
    CollectionService.update_request(req.id, url="https://api.example.com/visible-everywhere")
    for bad in ([0], [], [-5, 0]):
        text = execute_workspace_query(
            "search",
            session_id=_session(),
            search="visible-everywhere",
            within_ids=bad,
        )
        assert "Refusing to run an unrestricted search" in text
        assert f"postmark://request/{req.id}" not in text


def test_search_within_ids_non_request_ids_error(
    make_collection_with_request: Any,
) -> None:
    """History/script/collection ids in within_ids error when none are requests."""
    _coll, req = make_collection_with_request(req_name="RealRequest")
    bogus = req.id + 9_999_999
    text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="RealRequest",
        within_ids=[bogus],
    )
    assert "did not match any requests" in text
    assert f"postmark://request/{req.id}" not in text


def test_search_within_ids_last_sentinel_reuses_hits(
    make_collection_with_request: Any,
) -> None:
    """within_ids=[-1] reuses the last search hit set after a discovery search."""
    coll = CollectionService.create_collection("LastHitsRoot")
    a = create_new_request(coll.id, "GET", "https://api.example.com/checkout-a", "Checkout A")
    b = create_new_request(coll.id, "GET", "https://api.example.com/checkout-b", "Checkout B")
    outsider = create_new_request(
        coll.id, "GET", "https://api.example.com/expedia-only", "Expedia Only"
    )
    session_id = _session()
    first = execute_workspace_query("search", session_id=session_id, search="checkout")
    assert f"postmark://request/{a.id}" in first
    assert f"postmark://request/{b.id}" in first

    refined = execute_workspace_query(
        "search",
        session_id=session_id,
        search="expedia",
        within_ids=[-1],
    )
    assert "Restricted to" in refined
    assert f"postmark://request/{outsider.id}" not in refined
    # Neither checkout URL contains expedia — empty refine within last hits.
    assert "[partial]" in refined
    assert "[authoritative]" not in refined


def test_search_within_ids_last_sentinel_without_hits_errors() -> None:
    """within_ids=[-1] with no prior search asks the model to re-run discovery."""
    text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="anything",
        within_ids=[-1],
    )
    assert "none is stored" in text.casefold() or "Re-run scope=search" in text


def test_search_matches_params_table_only(make_collection_with_request: Any) -> None:
    """Params-table-only needles match via the deep field scan."""
    _coll, req = make_collection_with_request(req_name="ParamsOnly")
    CollectionService.update_request(
        req.id,
        url="https://api.example.com/items",
        request_parameters=[
            {"key": "partner", "value": "expedia-unique-param", "enabled": True},
        ],
    )
    text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="expedia-unique-param",
    )
    assert "params match" in text.casefold()
    assert f"postmark://request/{req.id}" in text


def test_request_scope_merges_dirty_tab_overlay(
    make_collection_with_request: Any,
) -> None:
    """Dirty open-tab request_data overrides DB fields with a [partial] banner."""
    _coll, req = make_collection_with_request(req_name="Saved Name")
    CollectionService.update_request(req.id, url="https://api.example.com/saved")
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "current_env_id": None,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": "Saved Name",
                    "request_id": req.id,
                    "collection_id": _coll.id,
                    "local_script_id": None,
                    "is_dirty": True,
                    "is_active": True,
                    "request_data": {
                        "method": "POST",
                        "url": "https://api.example.com/unsaved-dirty-url",
                        "body": '{"draft":true}',
                        "body_mode": "raw",
                        "body_options": {"raw": {"language": "json"}},
                        "headers": None,
                        "request_parameters": None,
                        "description": None,
                        "scripts": None,
                        "auth": None,
                    },
                }
            ],
        },
    )
    text = execute_workspace_query(
        "request",
        session_id=session_id,
        target_id=req.id,
    )
    assert "[partial]" in text
    assert "unsaved editor state" in text.casefold()
    assert "unsaved-dirty-url" in text
    assert "https://api.example.com/saved" not in text
    assert "POST" in text


# --- Part A: tokenized search, breadcrumbs, env/global ---


def test_search_multi_token_any_order(make_collection_with_request: Any) -> None:
    """Multi-token search matches name tokens in any order."""
    _coll, req = make_collection_with_request(req_name="Login User")
    text = execute_workspace_query("search", session_id=_session(), search="user login")
    assert f"postmark://request/{req.id}" in text
    assert "[authoritative]" not in text


def test_search_multi_token_across_name_and_url(make_collection_with_request: Any) -> None:
    """Tokens may span request name and URL fields."""
    _coll, req = make_collection_with_request(
        req_name="Auth Gate",
        url="https://api.example.com/v1/login",
    )
    text = execute_workspace_query("search", session_id=_session(), search="auth login")
    assert f"postmark://request/{req.id}" in text


def test_search_multi_token_empty_is_partial_not_authoritative(
    make_collection_with_request: Any,
) -> None:
    """Multi-token empties are partial with a longest-token retry hint."""
    make_collection_with_request(req_name="Users list")
    text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="aa bb distinctiveword",
    )
    assert "[partial]" in text
    assert "[authoritative]" not in text
    assert "Do not retry" not in text
    assert 'search="distinctiveword"' in text


def test_search_multi_token_deep_body_match(make_collection_with_request: Any) -> None:
    """Multi-token AND matching applies to body content."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        body='{"message": "welcome aboard traveler"}',
        body_mode="raw",
        body_options={"raw": {"language": "json"}},
    )
    text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="aboard welcome",
    )
    assert f"postmark://request/{req.id}" in text
    assert "body/description match" in text


def test_search_token_matching_on_masked_values_cannot_hit_secret(
    make_collection_with_request: Any,
) -> None:
    """Secret header values stay masked; tokens cannot match the raw secret."""
    _coll, req = make_collection_with_request()
    CollectionService.update_request(
        req.id,
        headers=[{"key": "Authorization", "value": "Bearer SUPERSECRETKOKORO123", "enabled": True}],
    )
    text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="SUPERSECRETKOKORO123",
    )
    assert "(header match)" not in text
    # Needle is echoed in the title; the raw header value must not appear as a hit.
    assert "Authorization" not in text or "header match" not in text


def test_search_deep_rows_include_breadcrumb(make_collection_with_request: Any) -> None:
    """Deep body matches append a nested folder path breadcrumb."""
    parent = CollectionService.create_collection("ParentCrumb")
    child = CollectionService.create_collection("ChildCrumb", parent_id=parent.id)
    req = CollectionService.create_request(child.id, "GET", "http://x", "BodyHit")
    CollectionService.update_request(
        req.id,
        body="unique_body_crumb_xyz",
        body_mode="raw",
        body_options={"raw": {"language": "text"}},
    )
    text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="unique_body_crumb_xyz",
    )
    assert "body/description match" in text
    assert " · in ParentCrumb/ChildCrumb/BodyHit" in text
    assert f"postmark://request/{req.id}" in text


def test_search_folder_and_local_script_breadcrumbs(
    make_collection_with_request: Any,
) -> None:
    """Folder-script and local-script matches include path breadcrumbs."""
    coll, _req = make_collection_with_request(name="FolderCrumbRoot")
    CollectionService.update_collection(
        coll.id,
        events=[{"listen": "prerequest", "script": {"exec": ["folder_crumb_marker"]}}],
    )
    folder = LocalScriptService.create_folder("Utils")
    script = LocalScriptService.create_script(
        folder.id,
        "helper",
        language="javascript",
        content="// local_crumb_marker here",
    )
    text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="folder_crumb_marker",
    )
    assert "folder script match" in text
    assert f" · in {coll.name}" in text
    local_text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="local_crumb_marker",
    )
    assert f"postmark://script/{script.id}" in local_text
    assert " · in Utils/" in local_text or " · in Utils" in local_text


def test_search_resolved_url_breadcrumb(make_collection_with_request: Any) -> None:
    """Resolved-URL hits include a path breadcrumb."""
    env = EnvironmentService.create_environment(
        "Prod",
        values=[{"key": "host", "value": "resolved-host.example", "enabled": True}],
    )
    coll, req = make_collection_with_request(
        name="ResolvedCrumbRoot",
        req_name="Hosted",
        url="https://{{host}}/api",
    )
    session_id = _session()
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "active_collection_id": None,
            "current_env_id": env.id,
            "active_response": None,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": req.name,
                    "request_id": req.id,
                    "collection_id": None,
                    "local_script_id": None,
                    "is_dirty": False,
                    "is_active": True,
                    "request_data": None,
                }
            ],
        },
    )
    text = execute_workspace_query(
        "search",
        session_id=session_id,
        search="resolved-host",
    )
    assert "resolved URL match" in text
    assert f" · in {coll.name}/Hosted" in text


def test_search_env_name_and_value_match() -> None:
    """Search matches environment names and non-secret variable values."""
    env = EnvironmentService.create_environment(
        "Staging West",
        values=[{"key": "region", "value": "eu-west-1", "enabled": True}],
    )
    text = execute_workspace_query("search", session_id=_session(), search="Staging")
    assert f"postmark://environment/{env.id}" in text
    value_text = execute_workspace_query("search", session_id=_session(), search="eu-west")
    assert f"postmark://environment/{env.id}" in value_text
    multi = execute_workspace_query(
        "search",
        session_id=_session(),
        search="Staging region",
    )
    assert f"postmark://environment/{env.id}" in multi


def test_search_env_secret_value_cannot_match_but_key_can() -> None:
    """Secret env values are excluded from hay; keys remain searchable."""
    env = EnvironmentService.create_environment(
        "Secrets",
        values=[
            {"key": "api_token", "value": "RAWENVSECRET99", "enabled": True, "type": "secret"},
        ],
    )
    miss = execute_workspace_query("search", session_id=_session(), search="RAWENVSECRET99")
    assert f"postmark://environment/{env.id}" not in miss
    hit = execute_workspace_query("search", session_id=_session(), search="api_token")
    assert f"postmark://environment/{env.id}" in hit


def test_search_global_key_value_and_secret(
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    """Globals match on key/non-secret value; secret globals never match by value."""
    globals_path = tmp_path / "globals.json"
    globals_path.write_text(
        '{"region": "eu-central", "api_key": "GLOBALSEKRIT"}',
        encoding="utf-8",
    )
    monkeypatch.setattr("services.scripting.context._GLOBALS_PATH", globals_path)
    key_hit = execute_workspace_query("search", session_id=_session(), search="region")
    assert "Globals · region" in key_hit
    value_hit = execute_workspace_query("search", session_id=_session(), search="eu-central")
    assert "Globals · region" in value_hit
    secret_miss = execute_workspace_query("search", session_id=_session(), search="GLOBALSEKRIT")
    assert "Globals · api_key" not in secret_miss
    assert "(global variable match)" not in secret_miss or "api_key" not in secret_miss


def test_search_coverage_note_includes_env_globals() -> None:
    """Unrestricted coverage note claims enabled env/global keys are matched."""
    text = execute_workspace_query("search", session_id=_session(), search="zzz-no-hit")
    note = text.split("Search coverage note:", 1)[1].split("\n", 1)[0]
    assert "enabled environment/global variable keys" in note.casefold()
    assert "globals/env values" not in note.casefold()
    assert "[authoritative]" in text
    assert "globals, environments" in text.casefold()


def test_search_coverage_note_omits_env_under_within_ids(
    make_collection_with_request: Any,
) -> None:
    """within_ids refine must not claim environment/global keys are scanned."""
    _coll, req = make_collection_with_request(req_name="WithinCov")
    text = execute_workspace_query(
        "search",
        session_id=_session(),
        search="zzz-no-hit-within",
        within_ids=[req.id],
    )
    note = next(line for line in text.splitlines() if line.startswith("Search coverage note:"))
    assert "environment/global" in note.casefold()
    assert "not scanned under within_ids" in note.casefold()
    assert "enabled environment/global variable keys are matched" not in note.casefold()


# --- Part D: insights duplicates ---


def test_insights_duplicate_method_url_groups(make_collection_with_request: Any) -> None:
    """Insights groups duplicate method+URL pairs with slash/case normalization."""
    coll, req_a = make_collection_with_request(
        req_name="Alpha",
        url="https://API.example.com/users/",
    )
    req_b = create_new_request(coll.id, "GET", "https://api.example.com/users", "Beta")
    text = execute_workspace_query("insights", session_id=_session())
    assert "Duplicate requests (same method + URL):" in text
    assert f"postmark://request/{req_a.id}" in text
    assert f"postmark://request/{req_b.id}" in text
    # Both ids appear on the same duplicate group line.
    dupe_section = text.split("Duplicate requests (same method + URL):", 1)[1]
    dupe_line = next(
        line
        for line in dupe_section.splitlines()
        if f"postmark://request/{req_a.id}" in line and f"postmark://request/{req_b.id}" in line
    )
    assert "GET" in dupe_line
    assert "api.example.com/users" in dupe_line.casefold()


def test_insights_unique_request_absent_from_duplicates(
    make_collection_with_request: Any,
) -> None:
    """A unique method+URL is not listed under duplicate groups."""
    _coll, req = make_collection_with_request(
        req_name="OnlyOne",
        url="https://unique.example.com/path",
    )
    text = execute_workspace_query("insights", session_id=_session())
    assert "Duplicate requests (same method + URL):" not in text
    assert f"postmark://request/{req.id}" in text or "All scanned requests" in text


def test_insights_duplicate_urls_are_redacted(make_collection_with_request: Any) -> None:
    """Duplicate group display redacts basic-auth and sensitive query values."""
    coll, req_a = make_collection_with_request(
        req_name="CredA",
        url="https://user:hunter2pass@api.example.com/v1?api_key=live_sk_secret123",
    )
    req_b = create_new_request(
        coll.id,
        "GET",
        "https://user:hunter2pass@api.example.com/v1?api_key=live_sk_secret123",
        "CredB",
    )
    text = execute_workspace_query("insights", session_id=_session())
    assert "Duplicate requests (same method + URL):" in text
    assert f"postmark://request/{req_a.id}" in text
    assert f"postmark://request/{req_b.id}" in text
    assert "hunter2pass" not in text
    assert "live_sk_secret123" not in text
    assert REDACTED_PLACEHOLDER in text


def test_insights_empty_urls_are_not_duplicates(make_collection_with_request: Any) -> None:
    """Blank draft URLs must not form a duplicate group."""
    coll, req_a = make_collection_with_request(req_name="DraftA", url="")
    req_b = create_new_request(coll.id, "GET", "", "DraftB")
    text = execute_workspace_query("insights", session_id=_session())
    assert "Duplicate requests (same method + URL):" not in text
    # Both blank drafts still appear under missing-tests (or coverage all-scanned).
    assert (
        f"postmark://request/{req_a.id}" in text
        or f"postmark://request/{req_b.id}" in text
        or "All scanned requests" in text
    )
