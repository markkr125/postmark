"""Tests for AI chat response text extraction."""

from __future__ import annotations

import types

from services.ai.chat.response_text import (
    AssistantParts,
    chunk_parts_from_stream,
    chunk_text_from_stream,
    extract_final_parts,
    extract_final_text,
    extract_latest_turn_parts,
    extract_richest_parts,
    merge_stream_text,
    message_display_parts,
    message_display_text,
    pick_richest_text,
    resolve_assistant_parts,
    resolve_assistant_text,
)


def test_message_display_parts_splits_reasoning_and_answer() -> None:
    """Reasoning and answer text are returned separately."""
    from openhands.sdk import TextContent
    from openhands.sdk.llm import Message

    msg = Message(
        role="assistant",
        content=[TextContent(text="Answer body")],
        reasoning_content="Thinking trace",
    )
    parts = message_display_parts(msg)
    assert parts == AssistantParts("Thinking trace", "Answer body")
    assert message_display_text(msg) == "Thinking traceAnswer body"


def test_chunk_parts_from_stream_splits_reasoning_and_content() -> None:
    """Streaming chunks split reasoning and answer deltas."""
    chunk = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                delta=types.SimpleNamespace(
                    reasoning_content="think",
                    content=" ans",
                )
            )
        ]
    )
    assert chunk_parts_from_stream(chunk) == AssistantParts("think", " ans")  # type: ignore[arg-type]
    assert chunk_text_from_stream(chunk) == "think ans"  # type: ignore[arg-type]


def test_merge_stream_text_handles_deltas_and_cumulative_snapshots() -> None:
    """Ollama may send incremental deltas or full cumulative thinking text."""
    assert merge_stream_text("The user", " just says") == "The user just says"
    assert merge_stream_text("The user", "The user just says") == "The user just says"
    assert merge_stream_text("The user just says", "The user") == "The user just says"


def test_pick_richest_text_prefers_longer_compatible_text() -> None:
    """The richest helper keeps the longest prefix-compatible snapshot."""
    assert pick_richest_text("The user", "The user just says") == "The user just says"
    assert pick_richest_text("The user just says", "The user") == "The user just says"
    assert pick_richest_text("short", "much longer unrelated") == "much longer unrelated"


def test_chunk_parts_from_stream_reads_delta_thinking_field() -> None:
    """Ollama may expose thinking on the delta before reasoning_content."""
    chunk = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                delta=types.SimpleNamespace(
                    reasoning_content=None,
                    thinking="trace",
                    content=None,
                )
            )
        ]
    )
    assert chunk_parts_from_stream(chunk) == AssistantParts("trace", "")  # type: ignore[arg-type]


def test_chunk_parts_from_stream_reads_openai_reasoning_items() -> None:
    """OpenAI Responses API streams reasoning summaries via reasoning_items."""
    summary_block = types.SimpleNamespace(type="summary_text", text="Planning the answer")
    reasoning_item = types.SimpleNamespace(
        type="reasoning",
        id="rs_1",
        summary=[summary_block],
        content=None,
    )
    chunk = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                delta=types.SimpleNamespace(
                    reasoning_content=None,
                    thinking=None,
                    content="Hello",
                    reasoning_items=[reasoning_item],
                )
            )
        ]
    )
    assert chunk_parts_from_stream(chunk) == AssistantParts("Planning the answer", "Hello")  # type: ignore[arg-type]


def test_message_display_parts_reads_responses_reasoning_item() -> None:
    """Finalized Responses messages expose reasoning via responses_reasoning_item."""
    from openhands.sdk import TextContent
    from openhands.sdk.llm import Message, ReasoningItemModel

    msg = Message(
        role="assistant",
        content=[TextContent(text="Answer body")],
        responses_reasoning_item=ReasoningItemModel(
            id="rs_1",
            summary=["Step one", "Step two"],
        ),
    )
    parts = message_display_parts(msg)
    assert parts == AssistantParts("Step oneStep two", "Answer body")


def test_extract_richest_parts_scopes_to_current_turn() -> None:
    """Only the latest turn's agent events contribute, not earlier longer thinking."""
    from openhands.sdk import TextContent
    from openhands.sdk.event.llm_convertible.message import MessageEvent
    from openhands.sdk.llm import Message

    old_user = Message(role="user", content=[TextContent(text="what was my first message?")])
    old_agent = Message(
        role="assistant",
        content=[TextContent(text="hello!")],
        reasoning_content=(
            "We need to comply with instructions. The user asks 'what was my first message?' "
            "They said 'hello!' which is the first message."
        ),
    )
    new_user = Message(role="user", content=[TextContent(text="what is an http request?")])
    new_agent = Message(
        role="assistant",
        content=[TextContent(text="An HTTP request is a message sent to a server.")],
        reasoning_content="The user asks about HTTP requests. Give a concise technical answer.",
    )
    events = [
        MessageEvent(source="user", llm_message=old_user),
        MessageEvent(source="agent", llm_message=old_agent),
        MessageEvent(source="user", llm_message=new_user),
        MessageEvent(source="agent", llm_message=new_agent),
    ]

    class _Conv:
        state = types.SimpleNamespace(events=events)

    assert extract_richest_parts(_Conv()) == AssistantParts(  # type: ignore[arg-type]
        "The user asks about HTTP requests. Give a concise technical answer.",
        "An HTTP request is a message sent to a server.",
    )
    assert extract_latest_turn_parts(_Conv()) == extract_richest_parts(_Conv())  # type: ignore[arg-type]
    assert extract_final_parts(_Conv()) == extract_richest_parts(_Conv())  # type: ignore[arg-type]


def test_resolve_assistant_parts_ignores_prior_turn_thinking() -> None:
    """Worker finalization must not resurrect a longer thinking trace from an earlier turn."""
    from openhands.sdk import TextContent
    from openhands.sdk.event.llm_convertible.message import MessageEvent
    from openhands.sdk.llm import Message

    old_user = Message(role="user", content=[TextContent(text="first")])
    old_agent = Message(
        role="assistant",
        content=[TextContent(text="old answer")],
        reasoning_content="Very long unrelated thinking from the first turn in this session.",
    )
    new_user = Message(role="user", content=[TextContent(text="second")])
    new_agent = Message(
        role="assistant",
        content=[TextContent(text="new answer")],
        reasoning_content="short",
    )
    events = [
        MessageEvent(source="user", llm_message=old_user),
        MessageEvent(source="agent", llm_message=old_agent),
        MessageEvent(source="user", llm_message=new_user),
        MessageEvent(source="agent", llm_message=new_agent),
    ]

    class _Conv:
        state = types.SimpleNamespace(events=events)

    assert resolve_assistant_parts(
        _Conv(),  # type: ignore[arg-type]
        "short",
        "new answer",
    ) == AssistantParts("short", "new answer")


def test_extract_latest_turn_parts_fallback_without_user_boundary() -> None:
    """When no user boundary exists, only the last agent message is used."""
    from openhands.sdk import TextContent
    from openhands.sdk.event.llm_convertible.message import MessageEvent
    from openhands.sdk.llm import Message

    first = Message(
        role="assistant",
        content=[TextContent(text="first answer")],
        reasoning_content="Long thinking from an earlier agent message without a user boundary.",
    )
    last = Message(
        role="assistant",
        content=[TextContent(text="last answer")],
        reasoning_content="current",
    )
    events = [
        MessageEvent(source="agent", llm_message=first),
        MessageEvent(source="agent", llm_message=last),
    ]

    class _Conv:
        state = types.SimpleNamespace(events=events)

    assert extract_latest_turn_parts(_Conv()) == AssistantParts("current", "last answer")  # type: ignore[arg-type]


def test_resolve_assistant_parts_merges_events_and_buffers() -> None:
    """Events and stream buffers are merged, not replaced by the shorter one."""

    class _Conv:
        state = types.SimpleNamespace(events=[])

    assert resolve_assistant_parts(_Conv(), "long-think", "short") == AssistantParts(  # type: ignore[arg-type]
        "long-think",
        "short",
    )
    from openhands.sdk import TextContent
    from openhands.sdk.event.llm_convertible.message import MessageEvent
    from openhands.sdk.llm import Message

    msg = Message(
        role="assistant",
        content=[TextContent(text="Answer")],
        reasoning_content="The user",
    )
    events = [MessageEvent(source="agent", llm_message=msg)]

    class _ConvWithEvents:
        state = types.SimpleNamespace(events=events)

    assert resolve_assistant_parts(
        _ConvWithEvents(),  # type: ignore[arg-type]
        "The user just says",
        "Answer",
    ) == AssistantParts(
        "The user just says",
        "Answer",
    )
    assert resolve_assistant_parts(None, "", "buffer-only") == AssistantParts("", "buffer-only")


def test_resolve_assistant_text_combines_parts() -> None:
    """Legacy combined helper joins thinking and answer."""

    class _Conv:
        state = types.SimpleNamespace(events=[])

    assert resolve_assistant_text(_Conv(), "streamed-longer") == "streamed-longer"  # type: ignore[arg-type]
    assert resolve_assistant_text(None, "buffer-only") == "buffer-only"


def test_extract_final_parts_reads_latest_agent_message(
    monkeypatch,
) -> None:
    """``extract_final_parts`` scans events for the latest agent message."""
    from openhands.sdk import TextContent
    from openhands.sdk.event.llm_convertible.message import MessageEvent
    from openhands.sdk.llm import Message

    msg = Message(
        role="assistant",
        content=[TextContent(text="final answer")],
        reasoning_content="trace",
    )
    events = [
        MessageEvent(source="user", llm_message=Message(role="user", content=[])),
        MessageEvent(source="agent", llm_message=msg),
    ]

    class _Conv:
        state = types.SimpleNamespace(events=events)

    assert extract_final_parts(_Conv()) == AssistantParts("trace", "final answer")  # type: ignore[arg-type]
    assert extract_final_text(_Conv()) == "final answer"  # type: ignore[arg-type]
