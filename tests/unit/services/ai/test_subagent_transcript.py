"""Tests for subagent disk transcript parsing."""

from __future__ import annotations

from services.ai.chat.subagent_transcript import parse_subagent_transcript_events


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
    """Reasoning-only message events must not appear in the answer."""
    events = [
        MessageEvent("user", "Query"),
        MessageEvent("assistant", "", thinking="internal deliberation"),
        MessageEvent("assistant", "Final answer"),
    ]
    view = parse_subagent_transcript_events(events)
    assert view["answer_markdown"] == "Final answer"
