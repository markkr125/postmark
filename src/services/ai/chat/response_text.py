"""Extract displayable assistant text from OpenHands messages and stream chunks."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from openhands.sdk import BaseConversation
    from openhands.sdk.llm import Message
    from openhands.sdk.llm.streaming import LLMStreamChunk


class AssistantParts(NamedTuple):
    """Assistant output split into internal thinking and user-visible answer."""

    thinking: str
    content: str


def merge_stream_text(previous: str, incoming: str) -> str:
    """Merge streamed text that may arrive as deltas or cumulative snapshots."""
    if not incoming:
        return previous
    if not previous:
        return incoming
    if incoming.startswith(previous):
        return incoming
    if previous.startswith(incoming):
        return previous
    return previous + incoming


def pick_richest_text(*parts: str) -> str:
    """Return the longest compatible thinking or answer string from *parts*."""
    best = ""
    for part in parts:
        if not part:
            continue
        if not best:
            best = part
            continue
        if part.startswith(best) or best.startswith(part):
            best = part if len(part) >= len(best) else best
            continue
        if len(part) > len(best):
            best = part
    return best


def _text_from_reasoning_blocks(blocks: object) -> str:
    """Extract plaintext from Responses reasoning summary/content blocks."""
    if not isinstance(blocks, list):
        return ""
    parts: list[str] = []
    for block in blocks:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text:
            parts.append(text)
            continue
        if isinstance(block, str) and block:
            parts.append(block)
            continue
        if isinstance(block, dict):
            raw = block.get("text")
            if isinstance(raw, str) and raw:
                parts.append(raw)
    return "".join(parts)


def _text_from_reasoning_items(items: object) -> str:
    """Extract plaintext from LiteLLM ``reasoning_items`` stream deltas."""
    if not isinstance(items, list):
        return ""
    parts: list[str] = []
    for item in items:
        summary = _text_from_reasoning_blocks(getattr(item, "summary", None))
        if summary:
            parts.append(summary)
        content = _text_from_reasoning_blocks(getattr(item, "content", None))
        if content:
            parts.append(content)
    return "".join(parts)


def _thinking_from_responses_reasoning_item(item: object) -> str:
    """Collect visible reasoning text from an OpenHands ``ReasoningItemModel``."""
    if item is None:
        return ""
    parts: list[str] = []
    summary = getattr(item, "summary", None)
    if isinstance(summary, list):
        parts.append(_text_from_reasoning_blocks(summary))
    content = getattr(item, "content", None)
    if isinstance(content, list):
        parts.append(_text_from_reasoning_blocks(content))
    return "".join(parts)


def _thinking_from_message(message: Message) -> str:
    """Collect reasoning / thinking text from an SDK message."""
    parts: list[str] = []

    reasoning = getattr(message, "reasoning_content", None)
    if isinstance(reasoning, str) and reasoning:
        parts.append(reasoning)

    for block in getattr(message, "thinking_blocks", ()) or ():
        thinking = getattr(block, "thinking", None)
        if isinstance(thinking, str) and thinking:
            parts.append(thinking)
            continue
        data = getattr(block, "data", None)
        if isinstance(data, str) and data:
            parts.append(data)

    responses_item = getattr(message, "responses_reasoning_item", None)
    if responses_item is not None:
        item_text = _thinking_from_responses_reasoning_item(responses_item)
        if item_text:
            parts.append(item_text)

    return "".join(parts)


def _content_from_message(message: Message) -> str:
    """Collect the user-visible answer text from an SDK message."""
    parts: list[str] = []
    for item in message.content:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _thinking_from_stream_delta(delta: object) -> str:
    """Collect thinking text from one streaming delta."""
    parts: list[str] = []

    reasoning = getattr(delta, "reasoning_content", None)
    if isinstance(reasoning, str) and reasoning:
        parts.append(reasoning)

    thinking = getattr(delta, "thinking", None)
    if isinstance(thinking, str) and thinking:
        parts.append(thinking)

    for block in getattr(delta, "thinking_blocks", ()) or ():
        text = getattr(block, "thinking", None)
        if isinstance(text, str) and text:
            parts.append(text)
            continue
        data = getattr(block, "data", None)
        if isinstance(data, str) and data:
            parts.append(data)

    items_text = _text_from_reasoning_items(getattr(delta, "reasoning_items", None))
    if items_text:
        parts.append(items_text)

    return "".join(parts)


def chunk_parts_from_stream(chunk: LLMStreamChunk) -> AssistantParts:
    """Return thinking and answer deltas from a streaming LLM chunk."""
    choices = getattr(chunk, "choices", None) or []
    thinking_parts: list[str] = []
    content_parts: list[str] = []
    for choice in choices:
        delta = getattr(choice, "delta", None)
        if delta is None:
            continue
        thinking = _thinking_from_stream_delta(delta)
        if thinking:
            thinking_parts.append(thinking)
        content = getattr(delta, "content", None)
        if isinstance(content, str) and content:
            content_parts.append(content)
    return AssistantParts("".join(thinking_parts), "".join(content_parts))


def message_display_parts(message: Message | None) -> AssistantParts:
    """Split an SDK message into thinking trace and answer text."""
    if message is None:
        return AssistantParts("", "")
    return AssistantParts(
        _thinking_from_message(message),
        _content_from_message(message),
    )


def message_display_text(message: Message | None) -> str:
    """Serialize thinking + answer into one string (legacy callers)."""
    parts = message_display_parts(message)
    return parts.thinking + parts.content


def chunk_text_from_stream(chunk: LLMStreamChunk) -> str:
    """Return all text deltas from a streaming chunk (legacy combined form)."""
    parts = chunk_parts_from_stream(chunk)
    return parts.thinking + parts.content


def _fold_agent_event(thinking: str, content: str, event: object) -> AssistantParts:
    """Merge one agent ``MessageEvent`` or ``ActionEvent`` into *thinking* / *content*."""
    from openhands.sdk.event.llm_convertible.action import ActionEvent
    from openhands.sdk.event.llm_convertible.message import MessageEvent

    if isinstance(event, MessageEvent) and event.source == "agent":
        parts = message_display_parts(event.llm_message)
        return AssistantParts(
            pick_richest_text(thinking, parts.thinking),
            pick_richest_text(content, parts.content),
        )
    if isinstance(event, ActionEvent) and event.source == "agent":
        reasoning = getattr(event, "reasoning_content", None)
        if isinstance(reasoning, str) and reasoning:
            thinking = pick_richest_text(thinking, reasoning)
        for block in getattr(event, "thinking_blocks", ()) or ():
            block_text = getattr(block, "thinking", None)
            if isinstance(block_text, str) and block_text:
                thinking = pick_richest_text(thinking, block_text)
        for item in getattr(event, "thought", ()) or ():
            text = getattr(item, "text", None)
            if isinstance(text, str) and text:
                content = pick_richest_text(content, text)
    return AssistantParts(thinking, content)


def _extract_last_agent_turn_parts(events: Sequence[object]) -> AssistantParts:
    """Fallback when no user ``MessageEvent`` marks the current turn boundary."""
    from openhands.sdk.event.llm_convertible.message import MessageEvent

    last_agent_idx = -1
    for index, event in enumerate(events):
        if isinstance(event, MessageEvent) and event.source == "agent":
            last_agent_idx = index
    if last_agent_idx < 0:
        thinking = ""
        content = ""
        for event in events:
            folded = _fold_agent_event(thinking, content, event)
            thinking, content = folded.thinking, folded.content
        return AssistantParts(thinking, content)

    thinking = ""
    content = ""
    for event in events[last_agent_idx:]:
        folded = _fold_agent_event(thinking, content, event)
        thinking, content = folded.thinking, folded.content
    return AssistantParts(thinking, content)


def extract_latest_turn_parts(conversation: BaseConversation) -> AssistantParts:
    """Return thinking and answer from agent events in the current turn only."""
    from openhands.sdk.event.llm_convertible.message import MessageEvent

    events = list(conversation.state.events)
    thinking = ""
    content = ""
    found_user_boundary = False
    for event in reversed(events):
        if isinstance(event, MessageEvent) and event.source == "user":
            found_user_boundary = True
            break
        folded = _fold_agent_event(thinking, content, event)
        thinking, content = folded.thinking, folded.content
    if found_user_boundary:
        return AssistantParts(thinking, content)
    return _extract_last_agent_turn_parts(events)


def extract_final_parts(conversation: BaseConversation) -> AssistantParts:
    """Return the current turn's agent message split into thinking and answer."""
    return extract_richest_parts(conversation)


def extract_richest_parts(conversation: BaseConversation) -> AssistantParts:
    """Return the richest thinking and answer text from the current turn's agent events."""
    return extract_latest_turn_parts(conversation)


def extract_final_text(conversation: BaseConversation) -> str:
    """Return the latest agent answer text from conversation events."""
    return extract_final_parts(conversation).content


def resolve_assistant_parts(
    conversation: BaseConversation | None,
    thinking_buffer: str,
    content_buffer: str,
) -> AssistantParts:
    """Prefer the richest thinking and answer from the current turn's events or stream buffers."""
    from_events = AssistantParts("", "")
    if conversation is not None:
        from_events = extract_richest_parts(conversation)

    thinking = pick_richest_text(from_events.thinking, thinking_buffer)
    content = pick_richest_text(from_events.content, content_buffer)
    if not thinking and not content:
        combined = pick_richest_text(thinking_buffer, content_buffer)
        return AssistantParts("", combined)
    return AssistantParts(thinking, content)


def resolve_assistant_text(conversation: BaseConversation | None, stream_buffer: str) -> str:
    """Prefer the richest combined assistant text (legacy callers)."""
    parts = resolve_assistant_parts(conversation, "", stream_buffer)
    combined = parts.thinking + parts.content
    return combined or stream_buffer


__all__ = [
    "AssistantParts",
    "chunk_parts_from_stream",
    "chunk_text_from_stream",
    "extract_final_parts",
    "extract_final_text",
    "extract_latest_turn_parts",
    "extract_richest_parts",
    "merge_stream_text",
    "message_display_parts",
    "message_display_text",
    "pick_richest_text",
    "resolve_assistant_parts",
    "resolve_assistant_text",
]
