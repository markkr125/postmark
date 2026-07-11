"""Tests for subagent disk transcript parsing."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.ai.chat.subagent_events import SubagentRunRecord
from services.ai.chat.subagent_transcript import (
    load_subagent_disk_snapshot,
    parse_subagent_activity_steps,
    parse_subagent_transcript_events,
    steps_for_subagent_record,
)


class _TextBlock:
    """Minimal content block stand-in."""

    def __init__(self, text: str) -> None:
        """Store block text."""
        self.text = text


class _Message:
    """Minimal llm_message stand-in."""

    def __init__(self, role: str, content: str | list[_TextBlock]) -> None:
        """Store role and content."""
        self.role = role
        self.content = content


class MessageEvent:
    """Minimal MessageEvent stand-in."""

    def __init__(self, role: str, text: str, *, thinking: str = "") -> None:
        """Build a message event with string content."""
        self.llm_message = _Message(role, [_TextBlock(text)])
        self.reasoning_content = thinking


class WikiQueryAction:
    """Minimal wiki query action stand-in."""

    def __init__(self, query: str) -> None:
        """Store the query string."""
        self.query = query


class WikiQueryObservation:
    """Minimal wiki query observation stand-in."""

    def __init__(self, *, text: str = "") -> None:
        """Store observation text."""
        self.text = text
        self.content: list[object] = []


class ActionEvent:
    """Minimal ActionEvent stand-in."""

    def __init__(self, tool_name: str, action: object, tool_call_id: str = "tc1") -> None:
        """Initialize stand-in action event fields."""
        self.tool_name = tool_name
        self.action = action
        self.tool_call_id = tool_call_id


class ObservationEvent:
    """Minimal ObservationEvent stand-in."""

    def __init__(self, tool_name: str, observation: object, tool_call_id: str = "tc1") -> None:
        """Initialize stand-in observation event fields."""
        self.tool_name = tool_name
        self.observation = observation
        self.tool_call_id = tool_call_id


def test_parse_subagent_transcript_events_extracts_task_and_answer() -> None:
    """First user message is the task; last assistant message is the answer."""
    events = [
        MessageEvent("user", "Find TypeScript scripting docs"),
        MessageEvent("assistant", "Searching the wiki…"),
        MessageEvent("assistant", "## TypeScript docs\n\nUse `pm.require` for modules."),
    ]
    view = parse_subagent_transcript_events(events)
    assert view["task_prompt"] == "Find TypeScript scripting docs"
    assert "## TypeScript docs" in view["answer_markdown"]
    assert view["event_count"] == 3


def test_parse_subagent_transcript_events_uses_fallback_task() -> None:
    """When disk has no user row yet, fall back to the record task_prompt."""
    events = [MessageEvent("assistant", "Working on it…")]
    view = parse_subagent_transcript_events(
        events,
        fallback_task_prompt="Find Python scripting docs",
    )
    assert view["task_prompt"] == "Find Python scripting docs"
    assert view["answer_markdown"] == "Working on it…"


def test_parse_subagent_transcript_events_skips_thinking() -> None:
    """Reasoning-only message events stay out of the answer but feed thinking."""
    events = [
        MessageEvent("user", "Query"),
        MessageEvent("assistant", "", thinking="internal deliberation"),
        MessageEvent("assistant", "Final answer"),
    ]
    view = parse_subagent_transcript_events(events)
    assert view["answer_markdown"] == "Final answer"
    assert view["thinking_markdown"] == "internal deliberation"


def test_parse_subagent_transcript_events_thinking_and_content_same_message() -> None:
    """A message carrying both reasoning and answer keeps both."""
    events = [
        MessageEvent("user", "Query"),
        MessageEvent("assistant", "Final answer", thinking="my reasoning"),
    ]
    view = parse_subagent_transcript_events(events)
    assert view["answer_markdown"] == "Final answer"
    assert view["thinking_markdown"] == "my reasoning"


def test_parse_subagent_transcript_events_no_thinking_is_empty() -> None:
    """No reasoning anywhere yields an empty thinking string."""
    events = [MessageEvent("assistant", "Just an answer")]
    view = parse_subagent_transcript_events(events)
    assert view["thinking_markdown"] == ""


def _minimal_record(**overrides: object) -> SubagentRunRecord:
    """Build a minimal subagent record for step fallback tests."""
    base: SubagentRunRecord = {
        "id": "sub-1",
        "kind": "delegate",
        "label": "Find docs",
        "subagent_type": "general-purpose",
        "status": "running",
    }
    for key, value in overrides.items():
        base[key] = value  # type: ignore[literal-required]
    return base


def test_steps_for_subagent_record_warming() -> None:
    """Warming status shows Starting… fallback."""
    steps = steps_for_subagent_record(_minimal_record(status="warming"))
    assert len(steps) == 1
    assert steps[0]["summary"] == "Starting…"


def test_steps_for_subagent_record_running() -> None:
    """Running status shows Working… fallback."""
    steps = steps_for_subagent_record(_minimal_record(status="running"))
    assert len(steps) == 1
    assert steps[0]["summary"] == "Working…"


def test_steps_for_subagent_record_wiki_completed_with_preview() -> None:
    """Wiki kind adds search row and Read tool output when completed."""
    steps = steps_for_subagent_record(
        _minimal_record(
            kind="wiki",
            label='Searched wiki for "typescript"',
            status="completed",
            result_preview="Quickref excerpt.",
        )
    )
    assert steps[0]["summary"] == 'Searched wiki for "typescript"'
    assert steps[1]["summary"] == "Read tool output"
    assert steps[1].get("detail") == "Quickref excerpt."


def test_steps_for_subagent_record_completed_with_preview() -> None:
    """Completed delegate with preview shows Read tool output."""
    steps = steps_for_subagent_record(
        _minimal_record(
            status="completed",
            result_preview="Delegation result text.",
        )
    )
    assert len(steps) == 1
    assert steps[0]["summary"] == "Read tool output"
    assert steps[0].get("detail") == "Delegation result text."


def test_parse_subagent_activity_steps_wiki_search_and_responded() -> None:
    """Disk-parsed steps include wiki search, tool output, and assistant reply."""
    events = [
        MessageEvent("user", "Find TypeScript scripting docs"),
        ActionEvent("postmark_wiki_query", WikiQueryAction("typescript pm.require")),
        ObservationEvent(
            "postmark_wiki_query",
            WikiQueryObservation(text="Quickref: use pm.require for modules."),
        ),
        MessageEvent("assistant", "TypeScript docs live under scripting."),
    ]
    steps = parse_subagent_activity_steps(events)
    summaries = [step["summary"] for step in steps]
    assert 'Searched wiki for "typescript pm.require"' in summaries
    assert "Read tool output" in summaries
    assert "Responded" in summaries
    output_row = next(step for step in steps if step["summary"] == "Read tool output")
    assert "Quickref" in output_row.get("detail", "")


def test_parse_subagent_activity_steps_thought_briefly() -> None:
    """Reasoning-only message events become Thought briefly rows."""
    events = [
        MessageEvent("user", "Query"),
        MessageEvent("assistant", "", thinking="planning next search"),
    ]
    steps = parse_subagent_activity_steps(events)
    assert len(steps) == 1
    assert steps[0]["summary"] == "Thought briefly"
    assert steps[0].get("detail") == "planning next search"


def test_parse_subagent_activity_steps_collapses_multiple_searches() -> None:
    """Multiple wiki searches collapse into one aggregate row."""
    events = [
        ActionEvent("postmark_wiki_query", WikiQueryAction("typescript"), tool_call_id="a"),
        ObservationEvent(
            "postmark_wiki_query",
            WikiQueryObservation(text="ts hit"),
            tool_call_id="a",
        ),
        ActionEvent("postmark_wiki_query", WikiQueryAction("python"), tool_call_id="b"),
        ObservationEvent(
            "postmark_wiki_query",
            WikiQueryObservation(text="py hit"),
            tool_call_id="b",
        ),
    ]
    steps = parse_subagent_activity_steps(events)
    search_rows = [step for step in steps if step.get("icon") == "magnifying-glass"]
    assert len(search_rows) == 1
    assert search_rows[0]["summary"] == "Explored 2 searches"


def test_load_subagent_disk_snapshot_reads_event_log_once(tmp_path) -> None:
    """Snapshot loads transcript view and steps with a single disk read."""
    events = [
        MessageEvent("user", "Find docs"),
        ActionEvent("postmark_wiki_query", WikiQueryAction("scripting")),
        MessageEvent("assistant", "Done."),
    ]
    read_calls = 0

    def fake_read(_disk: str) -> list[object]:
        nonlocal read_calls
        read_calls += 1
        return events

    with patch(
        "services.ai.chat.subagent_transcript._read_subagent_events",
        side_effect=fake_read,
    ):
        snapshot = load_subagent_disk_snapshot(str(tmp_path))

    assert read_calls == 1
    assert snapshot["view"]["task_prompt"] == "Find docs"
    assert snapshot["view"]["answer_markdown"] == "Done."
    assert "thinking_markdown" in snapshot["view"]
    assert any(step["summary"] == 'Searched wiki for "scripting"' for step in snapshot["steps"])


def test_count_session_subagent_context_tokens_sums_answers(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Session subagent folders contribute answer tokens to the context bucket."""
    from pathlib import Path

    from services.ai.chat.subagent_transcript import count_session_subagent_context_tokens

    root = tmp_path / "subagents"
    root.mkdir()
    (root / "a").mkdir()
    (root / "b").mkdir()
    monkeypatch.setattr(
        "services.ai.chat.subagent_disk_registry.session_subagents_root",
        lambda _session_id: root,
    )

    def _fake_view(path: str, **_kw: object) -> dict[str, object]:
        name = Path(path).name
        if name == "a":
            return {
                "task_prompt": "task",
                "answer_markdown": "answer-aaaa",
                "thinking_markdown": "",
                "event_count": 1,
            }
        return {
            "task_prompt": "task",
            "answer_markdown": "",
            "thinking_markdown": "",
            "event_count": 1,
        }

    monkeypatch.setattr(
        "services.ai.chat.subagent_transcript.load_subagent_transcript_view",
        _fake_view,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.estimate_text_tokens",
        lambda text, _model, **_kw: len(text),
    )

    total = count_session_subagent_context_tokens("sess-1", "gpt-4o", char_only=True)
    # Folder a → answer; folder b falls back to task prompt.
    assert total == len("answer-aaaa") + len("task")
