"""Typing protocol for composed AI chat controller mixins."""

from __future__ import annotations

from typing import Literal, Protocol

from services.ai.chat.run_registry import AiChatRunContext

_StopMode = Literal["pre_stream", "post_stream"]


class _AiChatHostProtocol(Protocol):
    """Methods and state shared across AI chat controller mixins."""

    _pending_title_session_id: str | None
    _active_run_context: AiChatRunContext | None
    _stopped_generations: dict[int, _StopMode]

    def _sync_ai_session_title(self, session: object | None = None) -> None:
        """Refresh flyout session title chrome."""

    def _on_ai_assistant_finished(
        self,
        session_id: str,
        thinking: str,
        content: str,
    ) -> None:
        """Finalize a visible successful assistant turn."""

    def _persist_assistant_turn(
        self,
        session_id: str,
        content: str,
        *,
        thinking: str = "",
        thinking_duration_seconds: int | None = None,
        post_thinking_duration_seconds: int | None = None,
        model_id: str | None = None,
        usage: object | None = None,
        update_panel: bool = True,
    ) -> None:
        """Persist one assistant message row."""

    def _rollback_pre_stream_stop(self, ctx: AiChatRunContext) -> None:
        """Rewind a pre-stream stop back into the composer."""

    def _persist_stopped_assistant(
        self,
        session_id: str,
        thinking_partial: str,
        content_partial: str,
    ) -> None:
        """Persist a post-stream user stop."""

    def _on_ai_chat_failed(
        self,
        session_id: str,
        message: str,
        thinking_partial: str,
        content_partial: str,
    ) -> None:
        """Finalize a visible failed assistant turn."""

    @staticmethod
    def _format_chat_error(message: str) -> str:
        """Format provider errors for the transcript."""

    @staticmethod
    def _compose_failure_transcript(assistant_text: str, footer: str) -> str:
        """Join assistant body text with a footer line."""

    def _maybe_generate_session_title(self, session_id: str) -> None:
        """Spawn a title worker after the first exchange."""

    def _mark_run_stopped(self, run_generation: int, *, pre_stream: bool) -> None:
        """Record optimistic stop state for one run generation."""

    def _finalize_stream_stop_optimistic(self, ctx: AiChatRunContext) -> None:
        """Optimistically finalize a post-stream stop in the panel."""


__all__ = ["_AiChatHostProtocol"]
