"""Unit tests for AI chat timestamp formatting."""

from __future__ import annotations

from datetime import UTC, datetime

from ui.sidebar.ai.chat_sessions.time_format import format_message_sent_at


def test_format_message_sent_at_includes_date_and_clock() -> None:
    """User message timestamps always include month, day, and local clock."""
    sent = datetime(2026, 1, 15, 14, 30, tzinfo=UTC)
    label = format_message_sent_at(sent)
    assert "Jan" in label
    assert "15" in label
    assert "2:30 PM" in label or "4:30 PM" in label
