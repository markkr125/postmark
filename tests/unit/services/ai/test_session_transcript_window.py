"""Tests for turn-aware transcript window service helpers."""

from __future__ import annotations

import uuid

from database.models.ai_chat.ai_chat_repository import append_message, create_session
from services.ai.chat.session_service import AiChatSessionService
from services.ai.chat.transcript_window import INITIAL_TAIL_TURNS, message_limit_for_turns


def _seed_session(turns: int) -> str:
    """Create a session with *turns* complete user/assistant pairs."""
    session_id = str(uuid.uuid4())
    create_session(session_id=session_id, title="Window", model_id=None, mode="agent")
    for index in range(turns):
        append_message(session_id=session_id, role="user", content=f"u{index}")
        append_message(session_id=session_id, role="assistant", content=f"a{index}")
    return session_id


def test_get_session_tail_message_count_bounded() -> None:
    """Tail API returns a small page for long sessions, not the full transcript."""
    session_id = _seed_session(40)
    load = AiChatSessionService.get_session_tail(session_id, tail_turns=INITIAL_TAIL_TURNS)
    assert load is not None
    page = load["page"]
    assert len(page["messages"]) <= INITIAL_TAIL_TURNS * 2 + 2
    assert len(page["messages"]) < 40
    assert page["has_older"]


def test_get_session_tail_limits_turns() -> None:
    """Tail load returns only the latest user turns for long sessions."""
    session_id = _seed_session(10)
    load = AiChatSessionService.get_session_tail(session_id, tail_turns=INITIAL_TAIL_TURNS)
    assert load is not None
    page = load["page"]
    user_count = sum(1 for message in page["messages"] if message["role"] == "user")
    assert user_count <= INITIAL_TAIL_TURNS
    assert page["has_older"]
    assert page["oldest_id"] is not None
    assert page["newest_id"] is not None


def test_load_older_messages_returns_preceding_turns() -> None:
    """Older page fetch returns rows before the current oldest id."""
    session_id = _seed_session(8)
    tail = AiChatSessionService.get_session_tail(session_id, tail_turns=2)
    assert tail is not None
    oldest_id = tail["page"]["oldest_id"]
    assert oldest_id is not None
    older = AiChatSessionService.load_older_messages(session_id, before_id=oldest_id, page_turns=2)
    assert older["messages"]
    assert older["messages"][-1]["id"] < oldest_id


def test_message_limit_for_turns_scales_with_pairs() -> None:
    """Message cap leaves room for trailing user-only rows."""
    assert message_limit_for_turns(6) >= 14
