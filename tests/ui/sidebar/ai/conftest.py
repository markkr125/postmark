"""Shared helpers for AI sidebar UI tests."""

from __future__ import annotations

from services.ai.chat.session_service import AiChatMessageDict
from ui.sidebar.ai import AiChatPanel


def load_transcript_sync(
    panel: AiChatPanel,
    messages: list[AiChatMessageDict],
    qtbot,
) -> None:
    """Load a persisted transcript and wait until layout finishes."""
    panel.load_transcript(messages)
    panel.flush_transcript_load()
    qtbot.wait(10)
