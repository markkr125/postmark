"""Tests for main-agent tool activity event parsing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.ai.chat.tool_activity_events import (
    ToolActivityTracker,
    records_for_turn_events,
    tool_call_ids_from_confirmation_payload,
)


class ActionEvent:
    """Minimal ActionEvent stand-in."""

    def __init__(
        self,
        tool_name: str,
        action: object,
        *,
        tool_call_id: str = "tc1",
        security_risk: str | None = None,
    ) -> None:
        """Initialize stand-in action event fields."""
        self.tool_name = tool_name
        self.action = action
        self.tool_call_id = tool_call_id
        self.security_risk = security_risk


class ObservationEvent:
    """Minimal ObservationEvent stand-in."""

    def __init__(
        self,
        tool_name: str,
        observation: object,
        *,
        tool_call_id: str = "tc1",
    ) -> None:
        """Initialize stand-in observation event fields."""
        self.tool_name = tool_name
        self.observation = observation
        self.tool_call_id = tool_call_id


class TextObservation:
    """Observation with ``text`` and optional ``is_error``."""

    def __init__(self, text: str, *, is_error: bool = False) -> None:
        """Initialize text observation."""
        self.text = text
        self.is_error = is_error


def test_confirm_gated_import_shows_no_card_until_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    """Import ActionEvent stays hidden until the user Approves."""
    monkeypatch.setattr(
        "services.ai.chat.tool_activity_events.is_auto_approved",
        lambda _kind: False,
    )
    action = SimpleNamespace(
        url="https://example.com/openapi.yaml",
        human_preview=lambda: "https://example.com/openapi.yaml",
        summary="",
    )
    tracker = ToolActivityTracker()
    assert tracker.ingest(ActionEvent("postmark_import", action, tool_call_id="import-1")) == []
    assert tracker.records() == []

    changed = tracker.on_confirmation_approved(["import-1"])
    assert len(changed) == 1
    assert changed[0]["status"] == "running"
    assert tracker.records()[0]["status"] == "running"


def test_sdk_import_alias_runs_after_unknown_risk_is_approved() -> None:
    """SDK-emitted workspace-import alias participates in the activity lifecycle."""
    action = SimpleNamespace(
        url="https://example.com/openapi.yaml",
        human_preview=lambda: "https://example.com/openapi.yaml",
        summary="",
    )
    tracker = ToolActivityTracker()
    event = ActionEvent(
        "postmark_workspace_import",
        action,
        tool_call_id="sdk-import",
        security_risk="UNKNOWN",
    )
    assert tracker.ingest(event) == []
    assert tracker.records() == []
    tracker.on_confirmation_approved(["sdk-import"])
    records = tracker.records()
    assert len(records) == 1
    assert records[0]["status"] == "running"
    assert records[0]["title"] == "Import workspace"


def test_low_risk_mutate_runs_without_local_auto_approve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tracker follows SDK LOW risk instead of predicting an approval pause."""
    monkeypatch.setattr(
        "services.ai.chat.tool_activity_events.is_auto_approved",
        lambda _kind: False,
    )
    action = SimpleNamespace(
        action="rename",
        entity="collection",
        fields={"name": "Hotel Booking API 7"},
        human_preview=lambda: "Hotel Booking API 7",
        summary="",
    )
    tracker = ToolActivityTracker()
    changed = tracker.ingest(
        ActionEvent(
            "postmark_workspace_mutate",
            action,
            tool_call_id="low-risk-rename",
            security_risk="LOW",
        )
    )
    assert len(changed) == 1
    assert tracker.records()[0]["status"] == "running"


def test_reject_finalizes_without_running_card(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rejected confirm-gated tools show rejected, not a running spinner."""
    monkeypatch.setattr(
        "services.ai.chat.tool_activity_events.is_auto_approved",
        lambda _kind: False,
    )
    action = SimpleNamespace(
        url="https://example.com/openapi.yaml",
        human_preview=lambda: "https://example.com/openapi.yaml",
        summary="",
    )
    tracker = ToolActivityTracker()
    tracker.ingest(ActionEvent("postmark_import", action, tool_call_id="import-1"))
    changed = tracker.on_confirmation_rejected(["import-1"])
    assert changed[0]["status"] == "rejected"
    visible = tracker.records()
    assert len(visible) == 1
    assert visible[0]["status"] == "rejected"
    assert all(row["status"] != "running" for row in visible)


def test_import_zero_counts_is_error_not_completed() -> None:
    """ok: true with zero import counts maps to an error card."""
    text = (
        "ok: true\n"
        "summary: Imported 0 collection(s), 0 request(s), 0 environment(s)\n"
        "collections_imported: 0\n"
        "requests_imported: 0\n"
        "environments_imported: 0\n"
        "errors: ['Failed to fetch URL']\n"
    )
    tracker = ToolActivityTracker()
    action = SimpleNamespace(
        url="https://bad.example/openapi.yaml",
        human_preview=lambda: "https://bad.example/openapi.yaml",
        summary="",
    )
    tracker.ingest(ActionEvent("postmark_import", action, tool_call_id="import-2"))
    tracker.on_confirmation_approved(["import-2"])
    tracker.ingest(
        ObservationEvent(
            "postmark_import",
            TextObservation(text),
            tool_call_id="import-2",
        )
    )
    assert tracker.records()[0]["status"] == "error"


def test_wiki_query_is_not_tracked_by_tool_activity() -> None:
    """Wiki lookups stay on the subagent/wiki card path only."""
    action = SimpleNamespace(query="how to import")
    tracker = ToolActivityTracker()
    assert tracker.ingest(ActionEvent("postmark_wiki_query", action)) == []
    assert tracker.records() == []


def test_execute_observation_suppresses_tool_card() -> None:
    """Execute tool activity hands off to ExecuteResultCard (suppressed row)."""
    action = SimpleNamespace(
        operation="send_request",
        human_preview=lambda: "GET https://example.com",
        summary="",
    )
    tracker = ToolActivityTracker()
    tracker.ingest(ActionEvent("postmark_workspace_execute", action, tool_call_id="exec-1"))
    tracker.ingest(
        ObservationEvent(
            "postmark_workspace_execute",
            TextObservation("ok: true\noperation: send_request\n"),
            tool_call_id="exec-1",
        )
    )
    assert tracker.records() == []


def test_fast_datetime_is_suppressed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sub-threshold datetime tools do not produce a visible card."""
    times = iter([100.0, 100.1])
    monkeypatch.setattr("services.ai.chat.tool_activity_events.time.time", lambda: next(times))
    action = SimpleNamespace(operation="now", human_preview=lambda: "now", summary="")
    tracker = ToolActivityTracker()
    tracker.ingest(ActionEvent("postmark_datetime", action, tool_call_id="dt-1"))
    tracker.ingest(
        ObservationEvent(
            "postmark_datetime",
            TextObservation("2026-07-16T12:00:00Z"),
            tool_call_id="dt-1",
        )
    )
    assert tracker.records() == []


def test_readonly_query_completes_on_observation() -> None:
    """Workspace query shows running then completed."""
    action = SimpleNamespace(
        scope="overview",
        goals=None,
        human_preview=lambda: "overview",
        summary="",
    )
    tracker = ToolActivityTracker()
    tracker.ingest(ActionEvent("postmark_workspace_query", action, tool_call_id="q-1"))
    assert tracker.records()[0]["status"] == "running"
    tracker.ingest(
        ObservationEvent(
            "postmark_workspace_query",
            TextObservation("collections: 2"),
            tool_call_id="q-1",
        )
    )
    assert tracker.records()[0]["status"] == "completed"


def test_records_are_snapshots_for_queued_gui_delivery() -> None:
    """A queued running payload cannot mutate before the GUI consumes it."""
    action = SimpleNamespace(
        scope="overview",
        goals=None,
        human_preview=lambda: "overview",
        summary="",
    )
    tracker = ToolActivityTracker()
    tracker.ingest(ActionEvent("postmark_workspace_query", action, tool_call_id="q-queued"))
    queued_running = tracker.records()
    tracker.ingest(
        ObservationEvent(
            "postmark_workspace_query",
            TextObservation("collections: 2"),
            tool_call_id="q-queued",
        )
    )
    assert queued_running[0]["status"] == "running"
    assert tracker.records()[0]["status"] == "completed"


def test_tool_call_ids_from_confirmation_payload() -> None:
    """Pending confirmation payload exposes tool_call_id for approve wiring."""
    payload = {
        "actions": [
            {"tool_call_id": "tc-a", "title": "Import"},
            {"title": "missing id"},
        ]
    }
    assert tool_call_ids_from_confirmation_payload(payload) == ["tc-a"]


def test_records_for_turn_events_rebuilds_terminal_states() -> None:
    """Transcript reload rebuilds completed tool cards from event slices."""
    action = SimpleNamespace(
        scope="search",
        goals=None,
        search="payments",
        human_preview=lambda: 'search="payments"',
        summary="",
    )
    events = [
        ActionEvent("postmark_workspace_query", action, tool_call_id="q-2"),
        ObservationEvent(
            "postmark_workspace_query",
            TextObservation("hits: 3"),
            tool_call_id="q-2",
        ),
    ]
    records = records_for_turn_events(events)
    assert len(records) == 1
    assert records[0]["status"] == "completed"


def test_collection_draft_soft_trim_shows_on_card_detail() -> None:
    """Soft body truncation stays completed but surfaces on the tool card detail."""
    action = SimpleNamespace(
        operation="add_requests",
        name="",
        requests=[{}, {}],
        human_preview=lambda: "Add 2 requests",
        summary="",
    )
    tracker = ToolActivityTracker()
    tracker.ingest(ActionEvent("postmark_collection_draft", action, tool_call_id="draft-1"))
    tracker.ingest(
        ObservationEvent(
            "postmark_collection_draft",
            TextObservation(
                "ok: true\n"
                "added: ['POST Search', 'GET Example']\n"
                "requests: 2\n"
                "warnings: [\"body truncated for 'Example'\"]\n"
            ),
            tool_call_id="draft-1",
        )
    )
    record = tracker.records()[0]
    assert record["status"] == "completed"
    assert "Added 2" in record["detail"]
    assert "body truncated" in record["detail"]
    assert "ok: true" in record.get("output", "")
    assert "Example" in record["detail"]


def test_collection_draft_skip_and_failure_details() -> None:
    """Skipped items and hard failures rewrite the card detail for the user."""
    action = SimpleNamespace(
        operation="add_requests",
        name="",
        requests=[{}, {}],
        human_preview=lambda: "Add 2 requests",
        summary="",
    )
    tracker = ToolActivityTracker()
    tracker.ingest(ActionEvent("postmark_collection_draft", action, tool_call_id="draft-2"))
    tracker.ingest(
        ObservationEvent(
            "postmark_collection_draft",
            TextObservation(
                "ok: true\n"
                "added: ['POST Search']\n"
                "requests: 1\n"
                "skipped: ['Broken (bad_method): Use one of: GET, POST']\n"
            ),
            tool_call_id="draft-2",
        )
    )
    soft = tracker.records()[0]
    assert soft["status"] == "completed"
    assert "Added 1" in soft["detail"]
    assert "skipped Broken" in soft["detail"]

    fail_action = SimpleNamespace(
        operation="add_requests",
        name="",
        requests=[{}],
        human_preview=lambda: "Add 1 requests",
        summary="",
    )
    fail_tracker = ToolActivityTracker()
    fail_tracker.ingest(
        ActionEvent("postmark_collection_draft", fail_action, tool_call_id="draft-3")
    )
    fail_tracker.ingest(
        ObservationEvent(
            "postmark_collection_draft",
            TextObservation(
                "ok: false\nerror: all_skipped\nhint: No valid requests in this batch.\n"
            ),
            tool_call_id="draft-3",
        )
    )
    failed = fail_tracker.records()[0]
    assert failed["status"] == "error"
    assert "Failed: all_skipped" in failed["detail"]
    assert "No valid requests" in failed["detail"]


def test_collection_draft_empty_batch_stays_completed() -> None:
    """Empty requests arrays are soft no-ops — green card, clear detail."""
    action = SimpleNamespace(
        operation="add_requests",
        name="",
        requests=[],
        human_preview=lambda: "Add 0 requests",
        summary="",
    )
    tracker = ToolActivityTracker()
    tracker.ingest(ActionEvent("postmark_collection_draft", action, tool_call_id="draft-empty"))
    tracker.ingest(
        ObservationEvent(
            "postmark_collection_draft",
            TextObservation(
                "ok: true\n"
                "added: []\n"
                "requests: 1\n"
                "note: No endpoints in this chunk — draft unchanged.\n"
            ),
            tool_call_id="draft-empty",
        )
    )
    record = tracker.records()[0]
    assert record["status"] == "completed"
    assert "No endpoints in this chunk" in record["detail"]
    assert "Failed" not in record["detail"]


def test_document_import_detail_uses_observation_filename() -> None:
    """Observation rewrites 'attached document' to the real upload name."""
    action = SimpleNamespace(
        uri=None,
        path=None,
        chunk=2,
        human_preview=lambda: "attached document (chunk 2)",
        summary="",
    )
    tracker = ToolActivityTracker()
    tracker.ingest(ActionEvent("postmark_document_import", action, tool_call_id="doc-1"))
    tracker.ingest(
        ObservationEvent(
            "postmark_document_import",
            TextObservation(
                "ok: true\n"
                "document: 1 Hotel Implementation Guide_V12.0.docx\n"
                "uri: postmark://uploaded/1_Hotel_Implementation_Guide_V12.0.md\n"
                "chunk: 2 of 9\n\nbody\n"
            ),
            tool_call_id="doc-1",
        )
    )
    record = tracker.records()[0]
    assert record["status"] == "completed"
    assert record["detail"] == "1 Hotel Implementation Guide_V12.0.docx (chunk 2 of 9)"
