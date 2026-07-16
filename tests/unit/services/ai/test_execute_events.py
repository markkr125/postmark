"""Tests for agent-execute EventLog / observation card parsing."""

from __future__ import annotations

from services.ai.chat.execute_events import (
    record_from_bridge_event,
    records_for_turn_events,
    records_from_observation_text,
)
from services.ai.chat.mutation.bridge import MutationBridgeEvent


def test_records_from_observation_text_parses_history_link() -> None:
    """Observation body yields a clickable history-backed card."""
    text = (
        "ok: true\n"
        "execution_id: abc123\n"
        "operation: send_request\n"
        "summary: Sent GET Ping\n"
        "status_code: 200\n"
        "url: https://example.com/ping\n"
        "ids: {'request_id': 7, 'history_entry_id': 42}\n"
        "history_entry_id: 42\n"
        "deep_links: ['postmark://history/42?focus=response', "
        "'postmark://request/7']\n"
    )
    record = records_from_observation_text(text)
    assert record is not None
    assert record["id"] == "abc123"
    assert record["operation"] == "send_request"
    assert record["history_entry_id"] == 42
    assert record["request_id"] == 7
    assert record["status_code"] == 200
    assert record["status"] == "completed"


def test_record_from_bridge_event() -> None:
    """Drained executed bridge events become execute cards."""
    event: MutationBridgeEvent = {
        "type": "executed",
        "action": "send_request",
        "ids": {"request_id": 3, "history_entry_id": 9},
        "payload": {
            "execution_id": "ex1",
            "summary": "Sent GET Health",
            "status_code": 201,
            "url": "https://api.example/health",
            "ok": True,
        },
    }
    record = record_from_bridge_event(event)
    assert record is not None
    assert record["id"] == "ex1"
    assert record["history_entry_id"] == 9
    assert record["status_code"] == 201
    assert record["local_script_id"] is None
    assert record["script_phase"] is None


def test_record_from_bridge_event_run_scripts_phase() -> None:
    """run_scripts bridge payload carries script_phase onto the card."""
    event: MutationBridgeEvent = {
        "type": "executed",
        "action": "run_scripts",
        "ids": {"request_id": 12},
        "payload": {
            "execution_id": "ex2",
            "summary": "Ran scripts",
            "ok": True,
            "script_phase": "pre",
            "test_results": [],
            "console_logs": [],
        },
    }
    record = record_from_bridge_event(event)
    assert record is not None
    assert record["operation"] == "run_scripts"
    assert record["script_phase"] == "pre"
    assert record["request_id"] == 12


class ObservationEvent:
    """Minimal ObservationEvent stand-in."""

    def __init__(self, tool_name: str, text: str, tool_call_id: str = "") -> None:
        """Store tool metadata used by execute event parsing."""
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id
        self.observation = type("Obs", (), {"text": text})()


def test_records_for_turn_events_filters_execute_tool() -> None:
    """Only postmark_workspace_execute observations become cards."""
    text = (
        "ok: true\nexecution_id: e1\noperation: send_draft\n"
        "summary: Sent draft\nhistory_entry_id: 5\n"
    )
    events = [
        ObservationEvent("postmark_wiki_query", "ok: true\n"),
        ObservationEvent("postmark_workspace_execute", text, tool_call_id="tc1"),
    ]
    records = records_for_turn_events(events)
    assert len(records) == 1
    assert records[0]["operation"] == "send_draft"
    assert records[0]["history_entry_id"] == 5
