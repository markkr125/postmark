"""Concurrent AI chat run orchestration for :class:`_AiChatControllerMixin`."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal, cast

from PySide6.QtCore import QObject, QThread, Qt, Slot
from PySide6.QtWidgets import QMessageBox

from services.ai.ai_config import AiModelEntry
from services.ai.chat.response_text import pick_richest_text
from services.ai.chat.chat_run_limits import max_concurrent_chat_runs
from services.ai.chat.run_registry import AiChatRunContext, ChatRunRegistry
from services.ai.chat.session_service import ComposerRunContext

from ui.main_window.ai_chat_host_protocol import _AiChatHostProtocol

if TYPE_CHECKING:
    from ui.sidebar import RightSidebar

logger = logging.getLogger(__name__)

_StopMode = Literal["pre_stream", "post_stream"]


class _AiChatRunsMixin:
    """Start, route, and finalize concurrent per-session chat workers."""

    _right_sidebar: RightSidebar
    _chat_run_registry: ChatRunRegistry
    _active_run_context: AiChatRunContext | None
    _stopped_generations: dict[int, _StopMode]
    _pending_title_session_id: str | None
    _active_ai_session_id: str | None
    _concurrency_warned_at_count: int

    @staticmethod
    def _host(obj: object) -> _AiChatHostProtocol:
        """Cast composed controller mixins for cross-mixin calls."""
        return cast(_AiChatHostProtocol, obj)

    def _init_chat_run_registry(self) -> None:
        """Create the run registry and connect worker fan-out signals."""
        self_q = cast(QObject, self)
        self._chat_run_registry = ChatRunRegistry(self_q)
        queued = Qt.ConnectionType.QueuedConnection
        self._chat_run_registry.chunk_received.connect(self._on_registry_chunk_received, queued)
        self._chat_run_registry.status_changed.connect(self._on_registry_status_changed, queued)
        self._chat_run_registry.usage_updated.connect(self._on_registry_usage_updated, queued)
        self._chat_run_registry.context_compacted.connect(
            self._on_registry_context_compacted,
            queued,
        )
        self._chat_run_registry.assistant_finished.connect(
            self._on_registry_assistant_finished,
            queued,
        )
        self._chat_run_registry.failed.connect(self._on_registry_failed, queued)
        self._chat_run_registry.run_finished.connect(self._on_registry_run_finished, queued)
        self._chat_run_registry.running_sessions_changed.connect(self._sync_running_chrome, queued)
        self._concurrency_warned_at_count = -1

    def _sync_running_chrome(self) -> None:
        """Refresh header badge and history running indicators."""
        count = self._chat_run_registry.count_running()
        self._right_sidebar.set_ai_active_run_count(count)
        popup = self._session_history_popup_if_visible()
        if popup is not None:
            popup.set_running_session_ids(self._chat_run_registry.running_session_ids())

    @staticmethod
    def _session_history_popup_if_visible():
        """Return the session history popover when it is open."""
        from ui.sidebar.ai.chat_sessions.history_popup import AiSessionHistoryPopup

        popup = AiSessionHistoryPopup.instance()
        if popup.isVisible():
            return popup
        return None

    def _update_active_session_busy_state(self) -> None:
        """Sync composer busy chrome with the visible session's run state."""
        panel = self._right_sidebar.ai_chat_panel
        session_id = self._active_ai_session_id
        registry = getattr(self, "_chat_run_registry", None)
        if registry is None:
            return
        panel.set_run_busy(registry.is_running(session_id))

    def _maybe_warn_concurrent_load(self) -> None:
        """Advise when concurrent runs meet or exceed the Settings threshold."""
        limit = max_concurrent_chat_runs()
        count = self._chat_run_registry.count_running()
        if count < limit:
            self._concurrency_warned_at_count = -1
            return
        if count == self._concurrency_warned_at_count:
            return
        self._concurrency_warned_at_count = count
        QMessageBox.warning(
            self._right_sidebar,
            "High concurrent chat load",
            f"You have {count} chats running (advisory limit: {limit}). "
            "Additional sends are allowed, but many parallel agents can increase "
            "cost and load. Adjust the limit under Settings → AI → Agents, or stop runs "
            "from session history.",
        )

    def _start_chat_run(
        self,
        *,
        session_id: str,
        user_message_id: int,
        user_text: str,
        entry: AiModelEntry,
        agent_id: str,
        text: str,
        composer: ComposerRunContext | None,
    ) -> bool:
        """Persist UI state and spawn a worker for one assistant turn."""
        if self._chat_run_registry.is_running(session_id):
            return False
        self._maybe_warn_concurrent_load()

        run_generation = self._chat_run_registry.next_run_generation()
        if session_id == self._active_ai_session_id:
            self._active_run_context = AiChatRunContext(
                session_id=session_id,
                user_message_id=user_message_id,
                user_text=user_text,
                run_generation=run_generation,
                model_id=str(entry["id"]),
            )

        panel = self._right_sidebar.ai_chat_panel
        if session_id == self._active_ai_session_id:
            panel.set_run_busy(True)
            panel.begin_assistant_stream()

        handle = self._chat_run_registry.start_run(
            session_id=session_id,
            run_generation=run_generation,
            user_message_id=user_message_id,
            user_text=user_text,
            model_id=str(entry["id"]),
            entry=entry,
            agent_id=agent_id,
            text=text,
            composer=composer,
        )
        if handle is None:
            if session_id == self._active_ai_session_id:
                self._active_run_context = None
                panel.set_run_busy(False)
            return False
        return True

    def _reattach_session_run_if_needed(self, session_id: str) -> None:
        """Resume streaming UI when switching back to a running session."""
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or session_id != self._active_ai_session_id:
            return
        panel = self._right_sidebar.ai_chat_panel
        panel.set_run_busy(True)
        panel.resume_assistant_stream(
            handle.thinking_buffer,
            handle.content_buffer,
            status=handle.status_text,
        )
        metrics = handle.pending_sdk_metrics
        if metrics is not None:
            panel.deliver_context_usage_metrics(metrics)

    @Slot(str, int, str, str)
    def _on_registry_chunk_received(
        self,
        session_id: str,
        run_generation: int,
        thinking_delta: str,
        content_delta: str,
    ) -> None:
        """Deliver chunks only to the visible session's panel."""
        if session_id != self._active_ai_session_id:
            return
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        panel = self._right_sidebar.ai_chat_panel
        panel.deliver_assistant_chunk(thinking_delta, content_delta)

    @Slot(str, int, str)
    def _on_registry_status_changed(
        self,
        session_id: str,
        run_generation: int,
        status: str,
    ) -> None:
        """Update the activity row for the visible session only."""
        if session_id != self._active_ai_session_id:
            return
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        self._right_sidebar.ai_chat_panel.deliver_activity_status(status)

    @Slot(str, int, object)
    def _on_registry_usage_updated(
        self,
        session_id: str,
        run_generation: int,
        metrics: object,
    ) -> None:
        """Refresh context usage for the visible session only."""
        if session_id != self._active_ai_session_id:
            return
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        panel = self._right_sidebar.ai_chat_panel
        panel.deliver_context_usage_metrics(metrics)
        panel.deliver_context_usage_refresh()

    @Slot(str, int)
    def _on_registry_context_compacted(self, session_id: str, run_generation: int) -> None:
        """Show compaction notice for the visible session only."""
        if session_id != self._active_ai_session_id:
            return
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        panel = self._right_sidebar.ai_chat_panel
        panel.on_context_compacted()
        panel.deliver_context_usage_refresh()

    @Slot(str, int, str, str)
    def _on_registry_assistant_finished(
        self,
        session_id: str,
        run_generation: int,
        thinking: str,
        content: str,
    ) -> None:
        """Marshal assistant finish onto the GUI thread."""
        self_q = cast(QObject, self)
        if QThread.currentThread() != self_q.thread():
            self_q._ai_assistant_finish_requested.emit(  # type: ignore[attr-defined]
                session_id,
                run_generation,
                thinking,
                content,
            )
            return
        self._apply_registry_assistant_finished(session_id, run_generation, thinking, content)

    @Slot(str, int, str, str)
    def _apply_registry_assistant_finished(
        self,
        session_id: str,
        run_generation: int,
        thinking: str,
        content: str,
    ) -> None:
        """Finalize a successful assistant turn on the GUI thread."""
        if run_generation in self._stopped_generations:
            self._clear_visible_busy_if_needed(session_id)
            return
        if session_id == self._active_ai_session_id:
            self._host(self)._on_ai_assistant_finished(session_id, thinking, content)
        else:
            self._finalize_background_turn(
                session_id, run_generation, thinking, content, failed=False
            )

    @Slot(str, int, str, str, str)
    def _on_registry_failed(
        self,
        session_id: str,
        run_generation: int,
        message: str,
        thinking: str,
        content: str,
    ) -> None:
        """Marshal chat failure onto the GUI thread."""
        self_q = cast(QObject, self)
        if QThread.currentThread() != self_q.thread():
            self_q._ai_chat_fail_requested.emit(  # type: ignore[attr-defined]
                session_id,
                run_generation,
                message,
                thinking,
                content,
            )
            return
        self._apply_registry_failed(session_id, run_generation, message, thinking, content)

    @Slot(str, int, str, str, str)
    def _apply_registry_failed(
        self,
        session_id: str,
        run_generation: int,
        message: str,
        thinking: str,
        content: str,
    ) -> None:
        """Apply worker failure or user stop on the GUI thread."""
        handle = self._chat_run_registry.run_for(session_id)
        ctx = handle.context if handle is not None else None
        if ctx is None or ctx.run_generation != run_generation:
            self._clear_visible_busy_if_needed(session_id)
            return

        stopped = message.strip().lower() == "stopped"
        stop_mode = self._stopped_generations.get(run_generation)
        if stopped and stop_mode == "pre_stream":
            if session_id == self._active_ai_session_id:
                self._host(self)._rollback_pre_stream_stop(ctx)
            self._stopped_generations.pop(run_generation, None)
            return

        visible = session_id == self._active_ai_session_id
        if stopped and stop_mode == "post_stream":
            if visible:
                self._host(self)._persist_stopped_assistant(session_id, thinking, content)
                panel = self._right_sidebar.ai_chat_panel
                panel.set_run_busy(False)
            else:
                self._finalize_background_turn(
                    session_id,
                    run_generation,
                    thinking,
                    content,
                    failed=True,
                    footer="Stopped.",
                )
            self._stopped_generations.pop(run_generation, None)
            return

        if visible:
            self._host(self)._on_ai_chat_failed(session_id, message, thinking, content)
        else:
            footer = "Stopped." if stopped else self._host(self)._format_chat_error(message)
            self._finalize_background_turn(
                session_id,
                run_generation,
                thinking,
                content,
                failed=True,
                footer=footer,
            )

    def _finalize_background_turn(
        self,
        session_id: str,
        run_generation: int,
        thinking: str,
        content: str,
        *,
        failed: bool,
        footer: str = "",
    ) -> None:
        """Persist a completed background assistant turn without panel streaming."""
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        thinking_text = pick_richest_text(thinking, handle.thinking_buffer)
        body = pick_richest_text(content, handle.content_buffer)
        host = self._host(self)
        if failed:
            display = host._compose_failure_transcript(body, footer)
        else:
            if not thinking_text.strip() and not body.strip():
                display = host._compose_failure_transcript("", "No response from model")
            else:
                display = body
        host._persist_assistant_turn(
            session_id,
            display,
            thinking=thinking_text,
            thinking_duration_seconds=None,
            model_id=handle.context.model_id,
            usage=handle.pending_sdk_metrics,
            update_panel=False,
        )
        self._pending_title_session_id = session_id
        if session_id == self._active_ai_session_id:
            self._update_active_session_busy_state()

    def _clear_visible_busy_if_needed(self, session_id: str) -> None:
        """Clear composer busy when a stale signal targets the visible session."""
        if session_id == self._active_ai_session_id:
            self._right_sidebar.ai_chat_panel.set_run_busy(False)

    @Slot(str, int)
    def _on_registry_run_finished(self, session_id: str, run_generation: int) -> None:
        """Clear active context and schedule title generation after thread exit."""
        ctx = self._active_run_context
        if (
            ctx is not None
            and ctx.session_id == session_id
            and ctx.run_generation == run_generation
        ):
            self._active_run_context = None
        if session_id == self._active_ai_session_id:
            self._update_active_session_busy_state()
        pending = self._pending_title_session_id
        if pending == session_id:
            self._pending_title_session_id = None
            self._host(self)._maybe_generate_session_title(session_id)

    def _cancel_session_run(self, session_id: str | None) -> None:
        """Interrupt one session worker without optimistic UI rollback."""
        if session_id is None:
            return
        self._chat_run_registry.cancel(session_id)
        if session_id == self._active_ai_session_id:
            self._right_sidebar.ai_chat_panel.set_run_busy(False)

    def _handle_chat_stop(self) -> None:
        """Optimistically finalize stop UI, then interrupt the visible session worker."""
        panel = self._right_sidebar.ai_chat_panel
        session_id = self._active_ai_session_id
        if session_id is None:
            panel.set_run_busy(False)
            return
        handle = self._chat_run_registry.run_for(session_id)
        ctx = handle.context if handle is not None else None
        if ctx is None:
            active_ctx = self._active_run_context
            if active_ctx is not None and active_ctx.session_id == session_id:
                ctx = active_ctx
        if ctx is None:
            panel.set_run_busy(False)
            return

        host = self._host(self)
        if panel.is_pre_stream_cancel():
            host._rollback_pre_stream_stop(ctx)
            host._mark_run_stopped(ctx.run_generation, pre_stream=True)
        else:
            host._finalize_stream_stop_optimistic(ctx)
            host._mark_run_stopped(ctx.run_generation, pre_stream=False)

        self._chat_run_registry.cancel(ctx.session_id)


__all__ = ["_AiChatRunsMixin"]
