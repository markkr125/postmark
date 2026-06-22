"""Ensure inject prefix is not persisted in SQLite user messages."""

from __future__ import annotations

from database.models.ai_chat.ai_chat_repository import create_session
from services.ai.chat.session_service import AiChatSessionService


def test_record_user_message_stores_clean_text(qapp, _fresh_db) -> None:
    """User message persistence does not include inject prefix."""
    session_id = create_session(
        session_id="sess-inject-test",
        title="Test",
        model_id="m1",
        mode="agent",
    )["id"]
    row = AiChatSessionService.record_user_message(
        session_id,
        "Hello assistant",
        send_snapshot={
            "send_model_id": None,
            "send_mode": "agent",
            "send_agent_id": "postmark-assistant",
            "send_reasoning_effort": None,
            "send_thinking_enabled": None,
            "send_run_context_tokens": None,
        },
    )
    assert row["content"] == "Hello assistant"
    assert "<postmark_app_context" not in row["content"]
