"""Tests for enriched collection-draft imports (params, variables, scripts, caps)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, cast

import pytest
from PySide6.QtCore import QSettings

from services.ai.chat.tools.collection_draft.build import (
    build_parsed_collection,
    collect_variable_rows,
    normalize_url_variables,
)
from services.ai.chat.tools.collection_draft.config import (
    DEFAULT_DRAFT_SCRIPT_LANGUAGE,
    draft_script_language,
    set_draft_script_language,
)
from services.ai.chat.tools.collection_draft.ops import (
    MAX_DESCRIPTION_CHARS,
    MAX_PARAMS_PER_REQUEST,
    MAX_SCRIPT_CHARS,
)
from services.ai.chat.tools.collection_draft.state import (
    CollectionDraft,
    DraftRequest,
    clear_draft,
    get_draft,
)
from services.ai.chat.tools.collection_draft.tool import (
    CollectionDraftAction,
    CollectionDraftExecutor,
    PostmarkCollectionDraftTool,
)
from services.collection_service import CollectionService
from database.database import get_session
from database.models.collections.model.request_model import RequestModel
from sqlalchemy import select

_SESSION = "00000000-0000-4000-8000-00000000e2b2"


class _State:
    """Minimal conversation state exposing the session id."""

    def __init__(self, session_id: str) -> None:
        self.id = session_id
        self.persistence_dir = None


class _Conversation:
    """Minimal conversation stub for the executor."""

    def __init__(self, session_id: str) -> None:
        self.state = _State(session_id)


@pytest.fixture
def executor() -> Any:
    """Return a fresh executor with no draft carried over."""
    clear_draft(_SESSION)
    yield CollectionDraftExecutor()
    clear_draft(_SESSION)


@pytest.fixture(autouse=True)
def _reset_draft_script_language() -> Iterator[None]:
    """Isolate the draft script language setting."""
    settings = QSettings("Postmark", "Postmark")
    settings.remove("ai/draft_script_language")
    settings.sync()
    yield
    settings.remove("ai/draft_script_language")
    settings.sync()


def _run(executor: CollectionDraftExecutor, **kwargs: Any) -> str:
    """Invoke the executor and return the observation text."""
    action = CollectionDraftAction(**kwargs)
    obs = executor(action, cast(Any, _Conversation(_SESSION)))
    return obs.text


def _collection_id(body: str) -> int:
    """Parse the created collection id from a finish observation."""
    match = re.search(r"imported_collections: \[\{'id': (\d+),", body)
    assert match is not None, body
    return int(match.group(1))


def test_start_stores_description_and_scripts(executor: CollectionDraftExecutor) -> None:
    """Front-matter description and collection scripts are kept on the draft."""
    body = _run(
        executor,
        operation="start",
        name="Spec",
        description="## Auth\n\nBasic auth.",
        pre_script="pm.variables.set('ts', '1')",
        test_script="pm.test('ok', lambda: None)",
        variables=[{"key": "baseUrl", "value": "https://example.com"}],
    )
    assert "ok: true" in body
    assert "description: yes" in body
    assert "scripts: pre,test" in body
    draft = get_draft(_SESSION)
    assert draft is not None
    assert draft.description.startswith("## Auth")
    assert draft.pre_script.startswith("pm.variables")
    assert draft.test_script.startswith("pm.test")
    assert draft.variables[0]["key"] == "baseUrl"


def test_params_rows_with_descriptions_persist(executor: CollectionDraftExecutor) -> None:
    """Query params carry per-row descriptions through finish into the DB."""
    _run(executor, operation="start", name="Items API")
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "List",
                "method": "GET",
                "url": "{{baseUrl}}/items",
                "params": [
                    {
                        "key": "page",
                        "value": "1",
                        "description": "Page number (1-based)",
                    }
                ],
                "description": "List items.\n\n| Parameter | Type |\n| page | int |",
            }
        ],
    )
    body = _run(executor, operation="finish")
    assert "ok: true" in body
    assert "enrichment:" in body
    collection_id = _collection_id(body)
    collection = CollectionService.get_collection(collection_id)
    assert collection is not None
    assert "Items API" in (collection.name or "")
    with get_session() as session:
        requests = list(
            session.execute(select(RequestModel).where(RequestModel.collection_id == collection_id))
            .scalars()
            .all()
        )
    assert len(requests) == 1
    params = requests[0].request_parameters or []
    assert params[0]["key"] == "page"
    assert params[0]["description"] == "Page number (1-based)"
    assert "List items" in (requests[0].description or "")


def test_params_object_is_normalized(executor: CollectionDraftExecutor) -> None:
    """A params object is folded into key/value rows like headers."""
    _run(executor, operation="start", name="Spec")
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Search",
                "method": "GET",
                "url": "/search",
                "params": {"q": "hotel", "limit": "10"},
            }
        ],
    )
    draft = get_draft(_SESSION)
    assert draft is not None
    keys = {row["key"] for row in draft.requests[0].params}
    assert keys == {"q", "limit"}


def test_too_many_params_is_trimmed(executor: CollectionDraftExecutor) -> None:
    """Param over-cap is trimmed with a warning; the request still lands."""
    _run(executor, operation="start", name="Spec")
    params = {f"p{i}": str(i) for i in range(MAX_PARAMS_PER_REQUEST + 1)}
    body = _run(
        executor,
        operation="add_requests",
        requests=[{"name": "X", "method": "GET", "url": "/x", "params": params}],
    )
    assert "ok: true" in body
    assert "params trimmed" in body
    draft = get_draft(_SESSION)
    assert draft is not None
    assert len(draft.requests) == 1
    assert len(draft.requests[0].params) == MAX_PARAMS_PER_REQUEST


def test_description_and_script_truncation_warns(executor: CollectionDraftExecutor) -> None:
    """Over-cap description/script are truncated with a warnings line."""
    body = _run(
        executor,
        operation="start",
        name="Spec",
        description="D" * (MAX_DESCRIPTION_CHARS + 50),
        test_script="T" * (MAX_SCRIPT_CHARS + 50),
    )
    assert "ok: true" in body
    assert "warnings:" in body
    draft = get_draft(_SESSION)
    assert draft is not None
    assert len(draft.description) == MAX_DESCRIPTION_CHARS
    assert len(draft.test_script) == MAX_SCRIPT_CHARS


def test_status_shows_enrichment_flags(executor: CollectionDraftExecutor) -> None:
    """Status exposes description/scripts/params so a drifting agent can resume."""
    _run(
        executor,
        operation="start",
        name="Spec",
        description="Notes",
        test_script="pm.test('x', lambda: None)",
    )
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Get",
                "method": "GET",
                "url": "/x",
                "params": {"id": "1"},
                "pre_script": "x = 1",
            }
        ],
    )
    status = _run(executor, operation="status")
    assert "description: yes" in status
    assert "scripts: test" in status
    assert "params: 1" in status
    assert "scripts: pre" in status


def test_finish_persists_scripts_with_language_keys(
    executor: CollectionDraftExecutor,
) -> None:
    """Scripts open in the configured language (default python)."""
    assert draft_script_language() == "python"
    _run(
        executor,
        operation="start",
        name="Scripted Spec",
        test_script="pm.test('status', lambda: None)",
    )
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Ping",
                "method": "GET",
                "url": "/ping",
                "pre_script": "pm.variables.set('a', '1')",
            }
        ],
    )
    body = _run(executor, operation="finish")
    assert "ok: true" in body
    collection = CollectionService.get_collection(_collection_id(body))
    assert collection is not None
    events = collection.events or {}
    assert events.get("test", "").startswith("pm.test")
    assert events.get("language") == "python"
    assert events.get("test_language") == "python"
    collection_id = collection.id
    with get_session() as session:
        requests = list(
            session.execute(select(RequestModel).where(RequestModel.collection_id == collection_id))
            .scalars()
            .all()
        )
    scripts = requests[0].scripts or {}
    assert scripts.get("pre_request", "").startswith("pm.variables")
    assert scripts.get("pre_language") == "python"


def test_javascript_setting_emits_javascript_keys(
    executor: CollectionDraftExecutor,
) -> None:
    """Changing the setting switches the language keys on finish."""
    set_draft_script_language("javascript")
    _run(
        executor,
        operation="start",
        name="Js Spec",
        test_script="pm.test('ok', function () {});",
    )
    _run(
        executor,
        operation="add_requests",
        requests=[{"name": "A", "method": "GET", "url": "/a"}],
    )
    body = _run(executor, operation="finish")
    assert "ok: true" in body
    collection = CollectionService.get_collection(_collection_id(body))
    assert collection is not None
    events = collection.events or {}
    assert events.get("language") == "javascript"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/{version}/precheck", "/{{version}}/precheck"),
        (
            "/hotels/:hotelId/rooms/:roomId",
            "/hotels/{{hotelId}}/rooms/{{roomId}}",
        ),
        ("/items/<itemId>", "/items/{{itemId}}"),
        ("{{baseURL}}/v1/x", "{{baseURL}}/v1/x"),
        ("https://api.example.com:8443/v1/x", "https://api.example.com:8443/v1/x"),
        ("https://user:pass@host/x", "https://user:pass@host/x"),
        ("/search?filter=status:active", "/search?filter=status:active"),
        ("/{version}/x?id=:id", "/{{version}}/x?id=:id"),
    ],
)
def test_normalize_url_variables(raw: str, expected: str) -> None:
    """All placeholder conventions become ``{{var}}``; false positives stay literal."""
    assert normalize_url_variables(raw) == expected


def test_auto_variable_rows_from_urls_and_headers() -> None:
    """Finish collects explicit + detected variables; dynamics and bodies are skipped."""
    draft = CollectionDraft(
        name="Spec",
        variables=[{"key": "baseURL", "value": "https://example.com"}],
    )
    draft.requests = [
        DraftRequest(
            name="Precheck",
            method="POST",
            url="/{version}/precheck",
            headers=[{"key": "X-Trace", "value": "{{traceId}}"}],
            body='{"a": {"b": 1}, "version": "{version}"}',
        ),
        DraftRequest(
            name="Stamp",
            method="GET",
            url="/stamp/{{$timestamp}}",
        ),
    ]
    rows = collect_variable_rows(draft)
    keys = {row["key"] for row in rows}
    assert "baseURL" in keys
    assert "version" in keys
    assert "traceId" in keys
    assert "$timestamp" not in keys
    parsed = build_parsed_collection(draft)
    first = parsed["items"][0]
    assert first["type"] == "request"
    assert cast(Any, first)["url"] == "/{{version}}/precheck"
    assert "version" in {row["key"] for row in (parsed.get("variables") or [])}


def test_body_braces_are_not_scanned_for_variables() -> None:
    """JSON braces in bodies must never become collection variables."""
    draft = CollectionDraft(name="Spec")
    draft.requests = [
        DraftRequest(
            name="Post",
            method="POST",
            url="/x",
            body='{"nested": {"version": 1}}',
        )
    ]
    assert collect_variable_rows(draft) == []


def test_draft_script_language_defaults_and_round_trips() -> None:
    """Config helper defaults to python and rejects unknown values."""
    assert draft_script_language() == DEFAULT_DRAFT_SCRIPT_LANGUAGE
    set_draft_script_language("typescript")
    assert draft_script_language() == "typescript"
    set_draft_script_language("nope")
    assert draft_script_language() == "python"


def test_tool_description_interpolates_language() -> None:
    """Tool.create embeds the configured language in the description."""
    set_draft_script_language("javascript")
    tools = PostmarkCollectionDraftTool.create()
    assert "javascript" in tools[0].description
    set_draft_script_language("python")
    tools = PostmarkCollectionDraftTool.create()
    assert "python" in tools[0].description


def test_finish_enrichment_summary_in_observation(executor: CollectionDraftExecutor) -> None:
    """Finish reports what was enriched so the assistant can summarize it."""
    _run(
        executor,
        operation="start",
        name="Rich Spec",
        description="Conventions",
        test_script="pm.test('x', lambda: None)",
    )
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Get",
                "method": "GET",
                "url": "/{version}/items",
                "params": {"page": "1"},
            }
        ],
    )
    body = _run(executor, operation="finish")
    assert "enrichment:" in body
    assert "description" in body
    assert "variable" in body
    assert "collection scripts" in body
    assert "pm.require" in body


def test_auth_persisted_on_finish(executor: CollectionDraftExecutor) -> None:
    """Collection auth and credential variables survive finish."""
    _run(
        executor,
        operation="start",
        name="Authed API",
        auth={
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{bearerToken}}", "type": "string"}],
        },
    )
    _run(
        executor,
        operation="add_requests",
        requests=[{"name": "Me", "method": "GET", "url": "/me"}],
    )
    body = _run(executor, operation="finish")
    assert "auth" in body
    collection = CollectionService.get_collection(_collection_id(body))
    assert collection is not None
    assert (collection.auth or {}).get("type") == "bearer"
    keys = {str(row.get("key")) for row in (collection.variables or []) if isinstance(row, dict)}
    assert "bearerToken" in keys


def test_basic_auth_kv_rows_and_document_variables_persist(
    executor: CollectionDraftExecutor,
) -> None:
    """Basic auth in the key/value-row shape models emit must survive finish.

    Regression cover for the Agoda-style start payload: basic auth given as
    username/password rows, plus document-defined variables with values
    (endpoint convention ``https://myendpoint.com/v1.32/{operation}``).
    """
    _run(
        executor,
        operation="start",
        name="Agoda-like API",
        variables=[
            {"key": "baseURL", "value": "https://myendpoint.com"},
            {"key": "version", "value": "v1.32"},
            {"key": "username", "value": ""},
            {"key": "password", "value": ""},
        ],
        auth={
            "type": "basic",
            "basic": [
                {"key": "username", "value": "{{username}}"},
                {"key": "password", "value": "{{password}}"},
            ],
        },
        default_headers={"Content-Type": "application/json"},
    )
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Search",
                "method": "POST",
                "url": "{{baseURL}}/{{version}}/hotelSearch",
                "body": {"hotels": ["123"]},
            }
        ],
    )
    body = _run(executor, operation="finish")
    assert "ok: true" in body
    collection = CollectionService.get_collection(_collection_id(body))
    assert collection is not None
    auth = collection.auth or {}
    assert auth.get("type") == "basic"
    basic = auth.get("basic") or []
    assert {"key": "username", "value": "{{username}}"} in [
        {k: row.get(k) for k in ("key", "value")} for row in basic if isinstance(row, dict)
    ]
    variables = {
        str(row.get("key")): str(row.get("value"))
        for row in (collection.variables or [])
        if isinstance(row, dict)
    }
    assert variables.get("version") == "v1.32"
    assert variables.get("baseURL") == "https://myendpoint.com"
    # Credentials stay empty — the user fills them once.
    assert variables.get("username") == ""
    assert variables.get("password") == ""


def test_saved_responses_persisted(executor: CollectionDraftExecutor) -> None:
    """Request response examples are stored as saved responses."""
    _run(executor, operation="start", name="Examples API")
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Get item",
                "method": "GET",
                "url": "/items/1",
                "responses": [
                    {
                        "name": "200 OK",
                        "status": "OK",
                        "code": 200,
                        "body": {"id": 1, "name": "Widget"},
                    }
                ],
            }
        ],
    )
    body = _run(executor, operation="finish")
    assert "saved response" in body
    collection = CollectionService.get_collection(_collection_id(body))
    assert collection is not None
    with get_session() as session:
        requests = list(
            session.execute(select(RequestModel).where(RequestModel.collection_id == collection.id))
            .scalars()
            .all()
        )
    assert len(requests) == 1
    saved = list(requests[0].saved_responses or [])
    assert len(saved) == 1
    assert saved[0].name == "200 OK"
    assert saved[0].code == 200
    assert "Widget" in (saved[0].body or "")
    assert saved[0].preview_language == "json"
    snap = saved[0].original_request or {}
    assert snap.get("method") == "GET"
    assert snap.get("url", {}).get("raw") == "/items/1"
    assert "body" not in snap


def test_saved_response_snapshot_includes_request_body(executor: CollectionDraftExecutor) -> None:
    """Saved examples carry the parent request body for the Request Body tab."""
    _run(executor, operation="start", name="Search API")
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Hotel Search",
                "method": "POST",
                "url": "/HotelSearch",
                "body": {"hotels": ["123"], "checkIn": "2018-12-23"},
                "responses": [
                    {
                        "name": "200 Successful response",
                        "status": "OK",
                        "code": 200,
                        "body": {"status": "OK", "hotels": []},
                    }
                ],
            }
        ],
    )
    body = _run(executor, operation="finish")
    collection = CollectionService.get_collection(_collection_id(body))
    assert collection is not None
    with get_session() as session:
        requests = list(
            session.execute(select(RequestModel).where(RequestModel.collection_id == collection.id))
            .scalars()
            .all()
        )
    saved = list(requests[0].saved_responses or [])
    assert len(saved) == 1
    assert saved[0].preview_language == "json"
    snap = saved[0].original_request or {}
    req_body = snap.get("body") or {}
    assert req_body.get("mode") == "raw"
    assert "hotels" in str(req_body.get("raw"))
    assert (req_body.get("options") or {}).get("raw", {}).get("language") == "json"


def test_default_headers_merge_request_wins(executor: CollectionDraftExecutor) -> None:
    """Collection default headers apply; request headers override same keys."""
    _run(
        executor,
        operation="start",
        name="Headers API",
        default_headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Create",
                "method": "POST",
                "url": "/items",
                "headers": {"Accept": "application/xml"},
                "body": {"name": "x"},
            }
        ],
    )
    body = _run(executor, operation="finish")
    assert "default header" in body
    collection = CollectionService.get_collection(_collection_id(body))
    assert collection is not None
    with get_session() as session:
        requests = list(
            session.execute(select(RequestModel).where(RequestModel.collection_id == collection.id))
            .scalars()
            .all()
        )
    headers = requests[0].headers or []
    by_key = {
        str(row.get("key")).lower(): str(row.get("value"))
        for row in headers
        if isinstance(row, dict)
    }
    assert by_key.get("content-type") == "application/json"
    assert by_key.get("accept") == "application/xml"


def test_too_many_saved_responses_are_trimmed(executor: CollectionDraftExecutor) -> None:
    """More than MAX_SAVED_RESPONSES examples are trimmed with a warning."""
    from services.ai.chat.tools.collection_draft.state import MAX_SAVED_RESPONSES

    _run(executor, operation="start", name="Too many")
    responses = [
        {"name": f"Ex {i}", "code": 200, "body": "{}"} for i in range(MAX_SAVED_RESPONSES + 1)
    ]
    body = _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Get",
                "method": "GET",
                "url": "/x",
                "responses": responses,
            }
        ],
    )
    assert "ok: true" in body
    assert "saved responses trimmed" in body
    draft = get_draft(_SESSION)
    assert draft is not None
    assert len(draft.requests[0].responses) == MAX_SAVED_RESPONSES
