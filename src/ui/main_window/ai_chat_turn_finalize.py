"""Assistant turn finalize helpers for :class:`_AiChatControllerMixin`."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast, Literal

from services.ai.chat.context_usage import ContextUsageSdkMetrics
from services.ai.chat.response_text import pick_richest_text
from services.ai.chat.run_registry import AiChatRunContext
from services.ai.chat.session_service import AiChatSessionService

if TYPE_CHECKING:
    from ui.sidebar import RightSidebar

logger = logging.getLogger(__name__)

_StopMode = Literal["pre_stream", "post_stream"]


class _AiChatTurnFinalizeMixin:
    """Persist and display completed, failed, or stopped assistant turns."""

    _right_sidebar: RightSidebar
    _active_run_context: AiChatRunContext | None
    _stopped_generations: dict[int, _StopMode]
    _pending_title_session_id: str | None

    def _on_ai_assistant_finished(
        self,
        session_id: str,
        thinking: str,
        content: str,
    ) -> None:
        """Persist assistant text and re-enable send."""
        if not thinking.strip() and not content.strip():
            self._on_ai_chat_failed(session_id, "No response from model", "", "")
            return
        panel = self._right_sidebar.ai_chat_panel
        panel.flush_pending_assistant_chunks()
        panel_content = panel.streaming_assistant_text()
        panel_thinking = panel.streaming_assistant_thinking()
        thinking = pick_richest_text(thinking, panel_thinking)
        content = pick_richest_text(content, panel_content)
        panel.end_assistant_stream(content, thinking=thinking)
        thinking_duration = panel.last_assistant_thinking_duration_seconds()
        self._persist_assistant_turn(
            session_id,
            content,
            thinking=thinking,
            thinking_duration_seconds=thinking_duration,
        )
        panel.set_run_busy(False)
        panel.refresh_context_usage()
        self._pending_title_session_id = session_id

    def _persist_assistant_turn(
        self,
        session_id: str,
        content: str,
        *,
        thinking: str = "",
        thinking_duration_seconds: int | None = None,
        model_id: str | None = None,
        usage: object | None = None,
        update_panel: bool = True,
    ) -> None:
        """Persist one assistant row with SDK usage and optionally update the bubble."""
        from services.ai.chat.message_usage import entry_for_model_id, model_display_name_from_entry

        panel = self._right_sidebar.ai_chat_panel
        ctx = self._active_run_context
        resolved_model_id = model_id or (
            ctx.model_id if ctx is not None else panel.current_model_id()
        )
        resolved_usage: ContextUsageSdkMetrics | None
        if usage is None and update_panel:
            resolved_usage = panel.take_pending_turn_sdk_metrics()
        else:
            resolved_usage = cast(ContextUsageSdkMetrics | None, usage)
        entry = (
            entry_for_model_id(resolved_model_id, extra_entries=panel._models)
            or panel.current_model_entry()
        )
        model_label = model_display_name_from_entry(entry)
        assistant_row = AiChatSessionService.record_assistant_message(
            session_id,
            content,
            thinking=thinking,
            thinking_duration_seconds=thinking_duration_seconds,
            model_id=resolved_model_id,
            model_label=model_label,
            usage=resolved_usage,
        )
        if update_panel:
            panel.apply_assistant_usage_metadata(assistant_row, entry=entry)
            panel.attach_streaming_assistant_message_id(assistant_row["id"])

    def _mark_run_stopped(self, run_generation: int, *, pre_stream: bool) -> None:
        """Record that *run_generation* was stopped so late worker signals no-op."""
        mode: _StopMode = "pre_stream" if pre_stream else "post_stream"
        self._stopped_generations[run_generation] = mode

    def _rollback_pre_stream_stop(self, ctx: AiChatRunContext) -> None:
        """Rewind an activity-only send back into the composer."""
        panel = self._right_sidebar.ai_chat_panel
        panel.rollback_pre_stream_turn(ctx.user_text)
        AiChatSessionService.delete_message(ctx.session_id, ctx.user_message_id)
        panel.set_run_busy(False)

    def _finalize_stream_stop_optimistic(self, ctx: AiChatRunContext) -> None:
        """Finalize partial assistant text with a Stopped footer on the GUI thread."""
        _ = ctx
        panel = self._right_sidebar.ai_chat_panel
        panel.flush_pending_assistant_chunks()
        thinking = panel.streaming_assistant_thinking()
        body = panel.streaming_assistant_text()
        display = self._compose_failure_transcript(body, "Stopped.")
        panel.end_assistant_stream(display, thinking=thinking)
        panel.set_run_busy(False)

    def _persist_stopped_assistant(
        self,
        session_id: str,
        thinking_partial: str,
        content_partial: str,
    ) -> None:
        """Persist a user-stopped assistant row after optimistic UI finalize."""
        panel = self._right_sidebar.ai_chat_panel
        thinking = pick_richest_text(
            thinking_partial.strip(),
            panel.streaming_assistant_thinking().strip(),
        )
        body = pick_richest_text(
            content_partial.strip(),
            panel.streaming_assistant_text().strip(),
        )
        display = self._compose_failure_transcript(body, "Stopped.")
        thinking_duration = panel.last_assistant_thinking_duration_seconds()
        self._persist_assistant_turn(
            session_id,
            display,
            thinking=thinking,
            thinking_duration_seconds=thinking_duration,
        )

    def _on_ai_chat_failed(
        self,
        session_id: str,
        message: str,
        thinking_partial: str,
        content_partial: str,
    ) -> None:
        """Show thinking and answer (if any) plus the error, and persist them."""
        panel = self._right_sidebar.ai_chat_panel
        panel.flush_pending_assistant_chunks()
        thinking = pick_richest_text(
            thinking_partial.strip(),
            panel.streaming_assistant_thinking().strip(),
        )
        body = pick_richest_text(
            content_partial.strip(),
            panel.streaming_assistant_text().strip(),
        )
        stopped = message.strip().lower() == "stopped"
        if stopped:
            logger.info("AI chat stopped by user")
            display = self._compose_failure_transcript(body, "Stopped.")
        else:
            logger.warning("AI chat failed: %s", message)
            display = self._compose_failure_transcript(body, self._format_chat_error(message))
        panel.end_assistant_stream(display, thinking=thinking)
        thinking_duration = panel.last_assistant_thinking_duration_seconds()
        self._persist_assistant_turn(
            session_id,
            display,
            thinking=thinking,
            thinking_duration_seconds=thinking_duration,
        )
        panel.set_run_busy(False)
        self._stopped_generations.pop(
            self._active_run_context.run_generation if self._active_run_context else -1,
            None,
        )
        self._pending_title_session_id = session_id

    @staticmethod
    def _compose_failure_transcript(assistant_text: str, footer: str) -> str:
        """Join streamed assistant text with a failure footer."""
        body = assistant_text.strip()
        footer = footer.strip()
        if body and footer:
            return f"{body}\n\n---\n{footer}"
        return body or footer

    @staticmethod
    def _format_chat_error(message: str) -> str:
        """Format a provider error for the chat bubble."""
        text = message.strip()
        return f"Error: {text}" if text else "Error: Unknown error"


__all__ = ["_AiChatTurnFinalizeMixin"]
