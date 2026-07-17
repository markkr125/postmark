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
    ) -> None:
        """Initialize stand-in action event fields."""
        self.tool_name = tool_name
        self.action = action
        self.tool_call_id = tool_call_id


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
