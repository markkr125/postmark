"""Tests for summarizing provider errors shown in the chat transcript."""

from __future__ import annotations

from services.ai.chat.provider_errors import (
    MALFORMED_TOOL_CALL_NOTE,
    summarize_provider_error,
)

_MALFORMED = (
    "Conversation run failed for id=d2404dea-55ba-4371-90ab-6c729ba8afa0: "
    'litellm.APIConnectionError: Ollama_chatException - {"detail":"error parsing tool '
    "call: raw='{\\\"mode\\\":\\\"content\\\"}', err=invalid character '.' looking for "
    'beginning of object key string"}\n\n'
    "Conversation logs are stored at: /home/marik/.local/share/postmark/ai_conversations/x\n\n"
    "To help debug this issue, please file a bug report at:\n"
    "  https://github.com/OpenHands/software-agent-sdk/issues/new\n"
    "and attach the conversation logs from the directory above."
)


def test_malformed_tool_call_gets_an_actionable_line() -> None:
    """The user needs to know to retry or change model, not read a stack trace."""
    assert summarize_provider_error(_MALFORMED) == MALFORMED_TOOL_CALL_NOTE


def test_sdk_bug_report_trailer_is_never_shown() -> None:
    """Upstream log paths and issue links are noise in the transcript."""
    summary = summarize_provider_error(_MALFORMED)
    assert "github.com" not in summary
    assert "ai_conversations" not in summary


def test_unreachable_provider_names_the_endpoint() -> None:
    """Knowing which endpoint refused the connection is the actionable part."""
    summary = summarize_provider_error(
        "APIConnectionError: Connection refused for http://192.168.50.87:3000/ollama/api/chat"
    )
    assert "http://192.168.50.87:3000/ollama/api/chat" in summary
    assert "running" in summary


def test_unknown_error_keeps_its_first_line() -> None:
    """Unrecognised failures still say something specific."""
    summary = summarize_provider_error("Rate limit exceeded for model gpt-oss\nretry later")
    assert summary == "Rate limit exceeded for model gpt-oss"


def test_empty_message_is_handled() -> None:
    """A blank provider message must not render an empty error bubble."""
    assert summarize_provider_error("") == "Unknown error"
