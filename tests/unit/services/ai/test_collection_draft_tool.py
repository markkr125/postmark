"""Tests for the incremental collection draft tool."""

from __future__ import annotations

from typing import Any, cast

import pytest
from pydantic import ValidationError

from openhands.sdk.security import SecurityRisk
from services.ai.chat.mutation.auto_approve import (
    draft_operation_is_write,
    is_mutate_or_execute_tool,
    kind_from_tool_args,
)
from services.ai.chat.mutation.security import PostmarkWorkspaceSecurityAnalyzer
from services.ai.chat.tools.collection_draft.build import build_parsed_collection
from services.ai.chat.tools.collection_draft.state import (
    CollectionDraft,
    DraftRequest,
    clear_draft,
    get_draft,
)
from services.ai.chat.tools.collection_draft.ops import MAX_BODY_CHARS
from services.ai.chat.tools.collection_draft.tool import (
    COLLECTION_DRAFT_TOOL_NAME,
    CollectionDraftAction,
    CollectionDraftExecutor,
)
from services.collection_service import CollectionService

_SESSION = "00000000-0000-4000-8000-00000000d1a1"


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


def _run(executor: CollectionDraftExecutor, **kwargs: Any) -> str:
    """Invoke the executor and return the observation text."""
    action = CollectionDraftAction(**kwargs)
    obs = executor(action, cast(Any, _Conversation(_SESSION)))
    return obs.text


def test_requests_accumulate_across_calls(executor: CollectionDraftExecutor) -> None:
    """Bounded batches accumulate while the full structure stays outside context."""
    assert "ok: true" in _run(executor, operation="start", name="Agoda Spec")
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "booking",
                "method": "POST",
                "url": "{{baseUrl}}/booking",
                "folder": "Bookings",
                "body": {"hotel": "1"},
            }
        ],
    )
    body = _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "cancelBooking",
                "method": "POST",
                "url": "{{baseUrl}}/cancel",
                "folder": "Bookings",
                "body": {"referenceId": "1"},
            }
        ],
    )
    assert "requests: 2" in body

    draft = get_draft(_SESSION)
    assert draft is not None
    assert [r.name for r in draft.requests] == ["booking", "cancelBooking"]


def test_document_chunk_requests_are_added_in_one_batch(
    executor: CollectionDraftExecutor,
) -> None:
    """One chunk should cost one draft round-trip, not one per endpoint."""
    _run(executor, operation="start", name="Spec")
    body = _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Search",
                "method": "POST",
                "url": "{{baseUrl}}/search",
                "body": {"q": "x"},
            },
            {
                "name": "Precheck",
                "method": "POST",
                "url": "{{baseUrl}}/precheck",
                "body": {"hotel": "1"},
            },
        ],
    )
    assert "requests: 2" in body
    draft = get_draft(_SESSION)
    assert draft is not None
    assert [request.name for request in draft.requests] == ["Search", "Precheck"]


def test_empty_add_requests_is_soft_noop(executor: CollectionDraftExecutor) -> None:
    """TOC/prose chunks may call add_requests with [] without a red failure."""
    _run(executor, operation="start", name="Spec")
    _run(
        executor,
        operation="add_requests",
        requests=[{"name": "Search", "method": "GET", "url": "/search"}],
    )
    empty = _run(executor, operation="add_requests", requests=[])
    assert "ok: true" in empty
    assert "added: []" in empty
    assert "No endpoints in this chunk" in empty
    draft = get_draft(_SESSION)
    assert draft is not None
    assert len(draft.requests) == 1

    omitted = _run(executor, operation="add_requests")
    assert "ok: true" in omitted
    assert "added: []" in omitted
    assert draft is get_draft(_SESSION)
    assert len(draft.requests) == 1


def test_non_list_requests_is_still_rejected(executor: CollectionDraftExecutor) -> None:
    """A malformed requests value stays a recoverable structural error."""
    from services.ai.chat.tools.collection_draft.ops.dispatch import op_add_requests

    _run(executor, operation="start", name="Spec")
    body = op_add_requests(_SESSION, {"requests": "oops"})
    assert "ok: false" in body
    assert "requests_required" in body


def test_start_observation_names_only_the_batch_operation(
    executor: CollectionDraftExecutor,
) -> None:
    """The tool must not contradict its schema with legacy workflow advice."""
    body = _run(executor, operation="start", name="Spec")
    assert "operation=add_requests" in body
    assert "operation=add_request," not in body


def test_json_body_object_is_stored_as_json(executor: CollectionDraftExecutor) -> None:
    """Models should send objects directly instead of fragile escaped JSON strings."""
    _run(executor, operation="start", name="Spec")
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Search",
                "method": "POST",
                "url": "/search",
                "body": {"hotels": ["123"], "occupancy": {"rooms": 1}},
            }
        ],
    )
    draft = get_draft(_SESSION)
    assert draft is not None
    assert draft.requests[0].body == (
        '{\n  "hotels": [\n    "123"\n  ],\n  "occupancy": {\n    "rooms": 1\n  }\n}'
    )


def test_post_without_body_is_kept_with_warning(executor: CollectionDraftExecutor) -> None:
    """Table-only POSTs must keep the request AND its saved responses, with a warning.

    Regression: skipping these wiped whole batches (and saved responses) when the
    model re-issued the same batch and finished with an empty collection.
    """
    _run(executor, operation="start", name="Spec")
    body = _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Booking IDs",
                "method": "POST",
                "url": "/bookingIds",
                "description": (
                    "### Request parameters\n\n"
                    "| Parameter | Type | Required |\n"
                    "| from | string | Y |\n"
                ),
                "responses": [{"name": "OK", "code": 200, "body": {"status": "OK"}}],
            },
            {
                "name": "Ping",
                "method": "GET",
                "url": "/ping",
            },
        ],
    )
    assert "ok: true" in body
    assert "NO request body/params" in body
    assert "Booking IDs" in body
    assert "body_required" not in body
    draft = get_draft(_SESSION)
    assert draft is not None
    assert len(draft.requests) == 2
    booking = draft.requests[0]
    assert booking.name == "Booking IDs"
    assert booking.body == ""
    # Saved responses survive — they must not be dropped with the missing body.
    assert len(booking.responses) == 1
    assert booking.responses[0].code == 200
    assert "OK" in booking.responses[0].body


def test_post_with_query_params_only_is_accepted(
    executor: CollectionDraftExecutor,
) -> None:
    """Query-only POST/PUT/PATCH need params, not a body — no warning either."""
    _run(executor, operation="start", name="Spec")
    body = _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Search",
                "method": "POST",
                "url": "/search",
                "params": [
                    {"key": "q", "value": "paris", "description": "Query text"},
                    {"key": "limit", "value": "10"},
                ],
            }
        ],
    )
    assert "ok: true" in body
    assert "NO request body/params" not in body
    draft = get_draft(_SESSION)
    assert draft is not None
    assert draft.requests[0].body == ""
    assert len(draft.requests[0].params) == 2
    assert draft.requests[0].params[0]["key"] == "q"


def test_table_only_batch_persists_saved_responses_end_to_end(
    executor: CollectionDraftExecutor,
) -> None:
    """Exact broken-726 shape: table-only POSTs with responses must finish with data.

    This replays what the Agoda run actually sent (description table + responses,
    no body). The whole point of the warning-over-skip rule: finish must still
    create the collection with requests AND saved responses, not an empty one.
    """
    import re

    from database.database import get_session
    from database.models.collections.model.request_model import RequestModel
    from sqlalchemy import select

    _run(executor, operation="start", name="Agoda-like Spec")
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Hotel Search / Availability Check",
                "method": "POST",
                "url": "/{{version}}/hotelSearch",
                "description": (
                    "### Request parameters\n\n"
                    "| Parameter | Type | Required |\n"
                    "| hotels | array of string | Y |\n"
                    "| checkIn | string | Y |\n"
                ),
                "responses": [
                    {
                        "name": "Successful response",
                        "status": "200",
                        "code": 200,
                        "headers": [{"key": "Content-Type", "value": "application/json"}],
                        "body": {"responseStatus": "SUCCESS", "hotels": []},
                    }
                ],
            },
            {
                "name": "Booking IDs",
                "method": "POST",
                "url": "/{{version}}/bookingIds",
                "description": (
                    "### Request parameters\n\n"
                    "| Parameter | Type | Required |\n"
                    "| from | string | Y |\n"
                ),
                "responses": [
                    {
                        "name": "Successful response with no bookings",
                        "status": "OK",
                        "code": 200,
                        "body": {"status": "OK", "bookingIds": []},
                    }
                ],
            },
        ],
    )
    finish = _run(executor, operation="finish")
    assert "ok: true" in finish
    match = re.search(r"'id': (\d+)", finish)
    assert match is not None
    with get_session() as session:
        requests = list(
            session.execute(
                select(RequestModel).where(RequestModel.collection_id == int(match.group(1)))
            )
            .scalars()
            .all()
        )
    assert len(requests) == 2
    by_name = {r.name: r for r in requests}
    search = by_name["Hotel Search / Availability Check"]
    saved = list(search.saved_responses or [])
    assert len(saved) == 1
    assert "SUCCESS" in (saved[0].body or "")
    ids = by_name["Booking IDs"]
    saved_ids = list(ids.saved_responses or [])
    assert len(saved_ids) == 1
    assert "bookingIds" in (saved_ids[0].body or "")


def test_body_recovered_from_description_json_fence(
    executor: CollectionDraftExecutor,
) -> None:
    """A fenced JSON example in description can fill a missing body field."""
    _run(executor, operation="start", name="Spec")
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Search",
                "method": "POST",
                "url": "/search",
                "description": (
                    'Search hotels.\n\n```json\n{"hotels": ["123"], "checkIn": "2018-12-23"}\n```\n'
                ),
            }
        ],
    )
    draft = get_draft(_SESSION)
    assert draft is not None
    assert "hotels" in draft.requests[0].body
    assert "123" in draft.requests[0].body


def test_xml_body_string_persists_and_snapshots(
    executor: CollectionDraftExecutor,
) -> None:
    """XML request bodies are stored as raw text and mirrored on saved examples."""
    import re

    from database.database import get_session
    from database.models.collections.model.request_model import RequestModel
    from sqlalchemy import select

    xml = '<?xml version="1.0"?><SearchRequest><Hotel>123</Hotel></SearchRequest>'
    _run(executor, operation="start", name="XML API")
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Search",
                "method": "POST",
                "url": "/search",
                "body": xml,
                "responses": [
                    {
                        "name": "200 OK",
                        "code": 200,
                        "body": '<?xml version="1.0"?><OK/>',
                    }
                ],
            }
        ],
    )
    finish = _run(executor, operation="finish")
    match = re.search(r"'id': (\d+)", finish)
    assert match is not None
    with get_session() as session:
        request = session.execute(
            select(RequestModel).where(RequestModel.collection_id == int(match.group(1)))
        ).scalar_one()
    assert request.body_mode == "raw"
    assert request.body == xml
    assert (request.body_options or {}).get("raw", {}).get("language") == "xml"
    saved = next(iter(request.saved_responses or []), None)
    assert saved is not None
    snap = saved.original_request or {}
    assert (snap.get("body") or {}).get("raw") == xml
    assert (snap.get("body") or {}).get("options", {}).get("raw", {}).get("language") == "xml"


def test_body_recovered_from_description_xml_fence(
    executor: CollectionDraftExecutor,
) -> None:
    """A fenced XML example in description can fill a missing body field."""
    _run(executor, operation="start", name="Spec")
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Search",
                "method": "POST",
                "url": "/search",
                "description": (
                    "SOAP search.\n\n```xml\n"
                    "<SearchRequest><Hotel>123</Hotel></SearchRequest>\n"
                    "```\n"
                ),
            }
        ],
    )
    draft = get_draft(_SESSION)
    assert draft is not None
    assert "<SearchRequest>" in draft.requests[0].body
    assert "123" in draft.requests[0].body


def test_finish_persists_request_body_and_saved_snapshot(
    executor: CollectionDraftExecutor,
) -> None:
    """Finish must store the request body and mirror it on saved-response snapshots."""
    import re

    from database.database import get_session
    from database.models.collections.model.request_model import RequestModel
    from sqlalchemy import select

    _run(executor, operation="start", name="Body Persist API")
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Booking IDs",
                "method": "POST",
                "url": "/{{version}}/bookingIds",
                "body": {"from": "2022-01-01T10:30:00+08:00", "to": "2022-01-02T10:30:00+08:00"},
                "responses": [
                    {
                        "name": "200 Successful response with no bookings",
                        "status": "OK",
                        "code": 200,
                        "body": {"status": "OK", "bookingIds": []},
                    }
                ],
            }
        ],
    )
    finish = _run(executor, operation="finish")
    match = re.search(r"'id': (\d+)", finish)
    assert match is not None
    collection_id = int(match.group(1))
    with get_session() as session:
        request = session.execute(
            select(RequestModel).where(RequestModel.collection_id == collection_id)
        ).scalar_one()
    assert request.body_mode == "raw"
    assert "2022-01-01" in (request.body or "")
    saved = list(request.saved_responses or [])
    assert len(saved) == 1
    snap = saved[0].original_request or {}
    assert (snap.get("body") or {}).get("mode") == "raw"
    assert "2022-01-01" in str((snap.get("body") or {}).get("raw"))


def test_batch_tolerates_path_header_object_and_extra_fields(
    executor: CollectionDraftExecutor,
) -> None:
    """A well-formed batch must not be rejected over natural field variations.

    This is the exact shape a model emitted that previously produced a 13-error
    Pydantic dump: ``path`` instead of ``url``, a header object instead of rows,
    and a stray ``target_id`` copied from other tools.
    """
    _run(executor, operation="start", name="Spec")
    action = CollectionDraftAction.model_validate(
        {
            "operation": "add_requests",
            "target_id": 0,
            "requests": [
                {
                    "name": "Search",
                    "method": "POST",
                    "path": "/{version}/hotelSearch",
                    "headers": {"Content-Type": "application/json"},
                    "body": {"hotels": ["123"]},
                }
            ],
        }
    )
    obs = executor(action, cast(Any, _Conversation(_SESSION)))
    assert "ok: true" in obs.text
    draft = get_draft(_SESSION)
    assert draft is not None
    request = draft.requests[0]
    assert request.url == "/{version}/hotelSearch"
    assert request.headers == [{"key": "Content-Type", "value": "application/json"}]


def test_oversized_body_is_truncated_not_rejected(executor: CollectionDraftExecutor) -> None:
    """A huge body is soft-truncated so sibling requests in the batch still land.

    Soft-accept keeps the tool card green; the warning tells the model to keep
    request payloads under the cap next time.
    """
    _run(executor, operation="start", name="Spec")
    huge = {"blob": "x" * (MAX_BODY_CHARS + 100)}
    body = _run(
        executor,
        operation="add_requests",
        requests=[
            {"name": "Search", "method": "POST", "url": "/search", "body": {"q": 1}},
            {"name": "Response Example", "method": "GET", "url": "/ex", "body": huge},
        ],
    )
    assert "ok: true" in body
    assert "body truncated" in body
    draft = get_draft(_SESSION)
    assert draft is not None
    assert len(draft.requests) == 2
    assert len(draft.requests[1].body) == MAX_BODY_CHARS


def test_normal_request_body_is_accepted(executor: CollectionDraftExecutor) -> None:
    """A realistic request example stays well under the cap and is stored."""
    _run(executor, operation="start", name="Spec")
    body = _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "Search",
                "method": "POST",
                "url": "/search",
                "body": {"hotels": ["123", "124"], "checkIn": "2018-12-23"},
            }
        ],
    )
    assert "ok: true" in body
    draft = get_draft(_SESSION)
    assert draft is not None and len(draft.requests) == 1


def test_legacy_single_request_operation_is_not_in_the_schema() -> None:
    """One-request calls caused repeated context and must not remain discoverable."""
    with pytest.raises(ValidationError):
        CollectionDraftAction.model_validate(
            {
                "operation": "add_request",
                "name": "Search",
                "method": "POST",
                "url": "/search",
            }
        )


def test_document_chunk_batch_soft_skips_bad_items(executor: CollectionDraftExecutor) -> None:
    """One malformed endpoint is skipped; valid siblings still append."""
    _run(executor, operation="start", name="Spec")
    body = _run(
        executor,
        operation="add_requests",
        requests=[
            {"name": "Search", "method": "POST", "url": "/search", "body": {"q": 1}},
            {"name": "Broken", "method": "FETCH", "url": "/broken"},
        ],
    )
    assert "ok: true" in body
    assert "skipped:" in body
    assert "Broken" in body
    draft = get_draft(_SESSION)
    assert draft is not None
    assert len(draft.requests) == 1
    assert draft.requests[0].name == "Search"


def test_status_lets_a_drifting_agent_resume(executor: CollectionDraftExecutor) -> None:
    """A model that loses track must be able to see what it already added."""
    _run(executor, operation="start", name="Spec")
    _run(
        executor,
        operation="add_requests",
        requests=[{"name": "search", "method": "POST", "url": "/search", "body": {"q": 1}}],
    )
    status = _run(executor, operation="status")
    assert "POST search" in status
    assert "requests: 1" in status


def test_add_requests_before_start_is_rejected(executor: CollectionDraftExecutor) -> None:
    """Adding without a draft must fail loudly rather than silently no-op."""
    body = _run(
        executor,
        operation="add_requests",
        requests=[{"name": "x", "method": "GET", "url": "/x"}],
    )
    assert "ok: false" in body
    assert "no_draft" in body


def test_finish_persists_and_returns_a_real_id(executor: CollectionDraftExecutor) -> None:
    """``finish`` is the only step that writes, and it supplies the true id."""
    _run(executor, operation="start", name="Agoda Standard Pull Spec")
    _run(
        executor,
        operation="add_requests",
        requests=[
            {
                "name": "booking",
                "method": "POST",
                "url": "{{baseUrl}}/booking",
                "folder": "Hotel Booking API",
                "body": {"hotel": "123"},
            }
        ],
    )
    body = _run(executor, operation="finish")

    assert "ok: true" in body
    assert "requests_imported: 1" in body
    assert "Agoda Standard Pull Spec" in body
    assert "postmark://collection/" in body
    assert CollectionService.count_all_collections() > 0
    assert get_draft(_SESSION) is None


def test_finish_on_empty_draft_does_not_create_anything(
    executor: CollectionDraftExecutor,
) -> None:
    """An empty draft must not produce a hollow collection."""
    _run(executor, operation="start", name="Empty")
    before = CollectionService.count_all_collections()
    body = _run(executor, operation="finish")
    assert "draft_empty" in body
    assert CollectionService.count_all_collections() == before


def test_discard_drops_the_draft(executor: CollectionDraftExecutor) -> None:
    """Discarding leaves no state behind."""
    _run(executor, operation="start", name="Spec")
    assert "ok: true" in _run(executor, operation="discard")
    assert get_draft(_SESSION) is None


def test_bad_method_is_rejected(executor: CollectionDraftExecutor) -> None:
    """An invalid verb must not reach the import layer."""
    _run(executor, operation="start", name="Spec")
    body = _run(
        executor,
        operation="add_requests",
        requests=[{"name": "x", "method": "FETCH", "url": "/x"}],
    )
    assert "bad_method" in body


def test_build_nests_requests_under_their_folders() -> None:
    """Folder paths become a real tree, including levels never declared."""
    draft = CollectionDraft(name="Spec")
    draft.requests = [
        DraftRequest(name="a", method="GET", url="/a", folder_path=("API", "Read")),
        DraftRequest(name="b", method="POST", url="/b"),
    ]
    parsed = build_parsed_collection(draft)

    api = cast(Any, parsed["items"][0])
    assert api["name"] == "API"
    read = api["children"][0]
    assert read["name"] == "Read"
    assert read["children"][0]["name"] == "a"
    assert parsed["items"][1]["name"] == "b"


class _Action:
    """Stub action carrying only the draft operation."""

    def __init__(self, operation: str) -> None:
        self.operation = operation


class _ActionEvent:
    """Stub ActionEvent for the security analyzer."""

    def __init__(self, operation: str) -> None:
        self.tool_name = COLLECTION_DRAFT_TOOL_NAME
        self.action = _Action(operation)


def test_only_finish_asks_for_approval() -> None:
    """Approving every added request would make the builder unusable."""
    analyzer = PostmarkWorkspaceSecurityAnalyzer()
    for operation in ("start", "add_requests", "status", "discard"):
        risk = analyzer.security_risk(cast(Any, _ActionEvent(operation)))
        assert risk == SecurityRisk.LOW, operation
    assert analyzer.security_risk(cast(Any, _ActionEvent("finish"))) == SecurityRisk.HIGH


def test_draft_tool_maps_to_the_import_auto_approve_kind() -> None:
    """Users who trust imports should not face a second unrelated toggle."""
    assert draft_operation_is_write("finish") is True
    assert draft_operation_is_write("add_requests") is False
    assert kind_from_tool_args(COLLECTION_DRAFT_TOOL_NAME) == "mutate:create:import"
    assert is_mutate_or_execute_tool(COLLECTION_DRAFT_TOOL_NAME) is True
