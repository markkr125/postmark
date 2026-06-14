"""AI chat controller mixin for the main window."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Literal, NamedTuple, cast

from PySide6.QtCore import QObject, Qt, QThread, Slot

from services.ai.ai_config import AiConfig
from services.ai.chat.agent_registry import DEFAULT_AGENT_ID
from services.ai.chat.response_text import pick_richest_text
from services.ai.chat.session_service import (
    AiChatSessionDict,
    AiChatSessionService,
    AiChatSessionTailLoadDict,
    AiChatTranscriptPageDict,
    ComposerRunContext,
)
from ui.sidebar.ai.chat_sessions.history_popup import AiSessionHistoryPopup
from ui.sidebar.ai.workers.chat_worker import AiChatWorker
from ui.sidebar.ai.workers.session_load_worker import AiChatSessionLoader
from ui.sidebar.ai.workers.title_worker import AiChatTitleWorker

if TYPE_CHECKING:
    from ui.sidebar import RightSidebar

logger = logging.getLogger(__name__)

_StopMode = Literal["pre_stream", "post_stream"]


class _AiChatRunContext(NamedTuple):
    """Snapshot of one in-flight user send for stop/finalize handling."""

    session_id: str
    user_message_id: int
    user_text: str
    run_generation: int


class _AiChatControllerMixin:
    """Wire AI chat panel, session service, and background workers."""

    _right_sidebar: RightSidebar
    _ai_chat_thread: QThread | None
    _ai_chat_worker: AiChatWorker | None
    _ai_title_thread: QThread | None
    _ai_title_worker: AiChatTitleWorker | None
    _active_ai_session_id: str | None
    _pending_title_session_id: str | None
    _title_run_session_id: str | None
    _session_load_generation: int
    _session_loader: AiChatSessionLoader
    _manual_ai_session_titles: set[str]
    _chat_run_generation: int
    _active_run_context: _AiChatRunContext | None
    _stopped_generations: dict[int, _StopMode]

    def _init_ai_chat_controller(self) -> None:
        """Connect sidebar signals and initialise chat state."""
        self._ai_chat_thread = None
        self._ai_chat_worker = None
        self._ai_title_thread = None
        self._ai_title_worker = None
        self._active_ai_session_id = None
        self._pending_title_session_id = None
        self._title_run_session_id = None
        self._session_load_generation = 0
        self._manual_ai_session_titles = set()
        self._chat_run_generation = 0
        self._active_run_context = None
        self._stopped_generations = {}

        self_q = cast(QObject, self)
        self._session_loader = AiChatSessionLoader(self_q)
        queued = Qt.ConnectionType.QueuedConnection
        self._session_loader.finished.connect(self._on_session_load_finished, queued)

        panel = self._right_sidebar.ai_chat_panel
        panel.set_window_load_callback(self._on_transcript_window_load_requested)
        # Synchronous on the GUI thread: begin_assistant_stream runs before _on_send
        # returns so turn-boundary scroll sees both user and assistant bubbles.
        panel.message_submitted.connect(self._on_ai_message_submitted)
        panel.stop_requested.connect(self._on_ai_chat_stop)
        self._right_sidebar.ai_new_chat_requested.connect(self._on_ai_new_chat)
        self._right_sidebar.ai_session_history_requested.connect(self._on_ai_session_history)
        self._right_sidebar.ai_session_title_renamed.connect(self._on_ai_session_title_renamed)
        self_q._ai_assistant_finish_requested.connect(  # type: ignore[attr-defined]
            self._apply_ai_worker_assistant_finished,
            queued,
        )
        self_q._ai_chat_fail_requested.connect(  # type: ignore[attr-defined]
            self._apply_ai_worker_failed,
            queued,
        )
        self_q._ai_title_ready_requested.connect(  # type: ignore[attr-defined]
            self._apply_ai_title_worker_ready,
            queued,
        )

    def _sync_ai_session_title(self, session: AiChatSessionDict | None = None) -> None:
        """Refresh the flyout conversation title for the active session."""
        if session is not None:
            self._right_sidebar.set_ai_session_title(session["title"])
            self._right_sidebar.set_ai_session_title_rename_enabled(True)
            return
        session_id = self._active_ai_session_id
        if session_id is None:
            self._right_sidebar.set_ai_session_title("New chat")
            self._right_sidebar.set_ai_session_title_rename_enabled(False)
            return
        session = AiChatSessionService.get_session(session_id)
        if session is None:
            self._right_sidebar.set_ai_session_title("New chat")
            self._right_sidebar.set_ai_session_title_rename_enabled(False)
            return
        self._right_sidebar.set_ai_session_title(session["title"])
        self._right_sidebar.set_ai_session_title_rename_enabled(True)

    def _on_ai_session_title_renamed(self, title: str) -> None:
        """Persist a user-edited session title from the flyout chrome."""
        session_id = self._active_ai_session_id
        if session_id is None:
            return
        cleaned = title.strip()
        if not cleaned:
            self._sync_ai_session_title()
            return
        AiChatSessionService.rename_session(session_id, cleaned)
        self._manual_ai_session_titles.add(session_id)
        self._sync_ai_session_title()

    def _on_ai_new_chat(self) -> None:
        """Clear transcript UI; next send creates a fresh session."""
        self._cancel_active_chat_run()
        self._session_load_generation += 1
        self._session_loader.cancel()
        self._right_sidebar.ai_chat_panel.cancel_transcript_load()
        self._active_ai_session_id = None
        AiConfig.set_chat_session_id("")
        self._right_sidebar.ai_chat_panel.clear()
        self._sync_ai_session_title()

    def _on_ai_session_history(self) -> None:
        """Toggle the session history popover."""
        popup = AiSessionHistoryPopup.instance()
        if popup.isVisible():
            popup.hide_popup()
            return
        sessions = AiChatSessionService.list_sessions()
        popup.show_for(
            self._right_sidebar.ai_history_button,
            sessions,
            self._on_ai_session_selected,
            active_session_id=self._active_ai_session_id,
        )

    def _on_ai_session_selected(self, session_id: str) -> None:
        """Load a session transcript into the panel."""
        self._activate_chat_session(session_id)

    def _activate_chat_session(self, session_id: str) -> None:
        """Load *session_id* into the panel and persist it as the active chat."""
        if session_id == self._active_ai_session_id:
            return
        self._cancel_active_chat_run()
        self._session_load_generation += 1
        generation = self._session_load_generation
        panel = self._right_sidebar.ai_chat_panel
        panel.prepare_transcript_load(lazy_markdown=True)
        self._session_loader.load_tail(session_id, generation)

    def _on_transcript_window_load_requested(
        self,
        kind: str,
        session_id: str,
        cursor_id: int,
        generation: int,
    ) -> None:
        """Dispatch silent older/newer transcript page loads."""
        if kind == "older":
            self._session_loader.load_older(session_id, cursor_id, generation)
        elif kind == "newer":
            self._session_loader.load_newer(session_id, cursor_id, generation)

    def _apply_session_chrome(self, session: AiChatSessionDict) -> None:
        """Update flyout title and composer model/mode for *session*."""
        self._sync_ai_session_title(session)
        panel = self._right_sidebar.ai_chat_panel
        model_id = session.get("model_id")
        if isinstance(model_id, str) and model_id:
            panel.select_model_if_available(model_id)
        mode = session.get("mode")
        if isinstance(mode, str) and mode.strip():
            panel.set_mode(mode.strip())

    @Slot(int, object)
    def _on_session_load_finished(self, generation: int, payload: object) -> None:
        """Apply a background session read and start incremental transcript build."""
        if isinstance(payload, tuple) and len(payload) == 2:
            kind, page_payload = payload
            if kind == "older" and isinstance(page_payload, dict):
                panel = self._right_sidebar.ai_chat_panel
                panel.apply_older_page(
                    cast(AiChatTranscriptPageDict, page_payload),
                    generation=generation,
                )
                return
            if kind == "newer" and isinstance(page_payload, dict):
                panel = self._right_sidebar.ai_chat_panel
                panel.apply_newer_page(
                    cast(AiChatTranscriptPageDict, page_payload),
                    generation=generation,
                )
                return
        if generation != self._session_load_generation:
            return
        panel = self._right_sidebar.ai_chat_panel
        if not isinstance(payload, tuple) or len(payload) != 2:
            panel.cancel_transcript_load()
            panel._clear_transcript_widgets()
            return
        kind, load_payload = payload
        if kind != "tail" or not isinstance(load_payload, dict):
            panel.cancel_transcript_load()
            panel._clear_transcript_widgets()
            return
        if load_payload is None:
            panel.cancel_transcript_load()
            panel._clear_transcript_widgets()
            return
        load = cast(AiChatSessionTailLoadDict, load_payload)
        session = load["session"]
        page = load["page"]
        self._active_ai_session_id = session["id"]
        AiConfig.set_chat_session_id(session["id"])
        self._apply_session_chrome(session)
        panel.begin_virtual_session(session["id"], page)
        panel.load_transcript_async(
            page["messages"],
            generation=generation,
            lazy_markdown=True,
            page=page,
        )

    def _restore_active_chat_session(self) -> None:
        """Reload the last active chat transcript after startup."""
        session_id = AiChatSessionService.resolve_restore_session_id()
        if session_id is None:
            return
        self._activate_chat_session(session_id)

    def _on_ai_message_submitted(self, text: str) -> None:
        """Handle a user message: persist, stream assistant reply."""
        if self._ai_chat_thread is not None and self._ai_chat_thread.isRunning():
            return

        panel = self._right_sidebar.ai_chat_panel
        entry = panel.current_model_entry()
        if entry is None:
            return

        session_id = self._active_ai_session_id
        if session_id is None:
            session = AiChatSessionService.new_session(
                entry,
                panel.current_mode(),
                first_message=text,
            )
            session_id = session["id"]
            self._active_ai_session_id = session_id
            self._sync_ai_session_title()
            panel.begin_virtual_session(
                session_id,
                AiChatTranscriptPageDict(
                    messages=[],
                    has_older=False,
                    has_newer=False,
                    oldest_id=None,
                    newest_id=None,
                ),
            )

        user_row = AiChatSessionService.record_user_message(session_id, text)
        panel.attach_last_user_message_id(user_row["id"])
        self._chat_run_generation += 1
        run_generation = self._chat_run_generation
        self._active_run_context = _AiChatRunContext(
            session_id=session_id,
            user_message_id=user_row["id"],
            user_text=text,
            run_generation=run_generation,
        )
        panel.set_run_busy(True)
        panel.begin_assistant_stream()

        composer = ComposerRunContext(
            reasoning_effort=panel.current_reasoning_effort(),
            thinking_enabled=panel.current_thinking_enabled(),
            run_context_tokens=panel.current_run_context_tokens(),
        )
        worker = AiChatWorker()
        session_row = AiChatSessionService.get_session(session_id)
        agent_id = session_row["agent_id"] if session_row else DEFAULT_AGENT_ID
        worker.set_run(
            session_id=session_id,
            entry=entry,
            agent_id=agent_id,
            text=text,
            composer=composer,
        )
        thread = QThread(cast(QObject, self))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        queued = Qt.ConnectionType.QueuedConnection
        worker.chunk_received.connect(panel.deliver_assistant_chunk, queued)
        worker.status_changed.connect(panel.deliver_activity_status, queued)
        worker.assistant_finished.connect(self._deliver_ai_worker_assistant_finished, queued)
        worker.failed.connect(self._deliver_ai_worker_failed, queued)
        worker.assistant_finished.connect(thread.quit, queued)
        worker.failed.connect(thread.quit, queued)
        thread.finished.connect(self._on_ai_chat_thread_finished)

        self._ai_chat_thread = thread
        self._ai_chat_worker = worker
        thread.start()

    @Slot(str, str)
    def _deliver_ai_worker_assistant_finished(self, thinking: str, content: str) -> None:
        """Marshal assistant finish onto the GUI thread before updating UI."""
        self_q = cast(QObject, self)
        if QThread.currentThread() != self_q.thread():
            self_q._ai_assistant_finish_requested.emit(thinking, content)  # type: ignore[attr-defined]
            return
        self._apply_ai_worker_assistant_finished(thinking, content)

    @Slot(str, str)
    def _apply_ai_worker_assistant_finished(self, thinking: str, content: str) -> None:
        """Finalize assistant text on the GUI thread."""
        panel = self._right_sidebar.ai_chat_panel
        ctx = self._active_run_context
        if ctx is not None and ctx.run_generation in self._stopped_generations:
            panel.set_run_busy(False)
            return
        session_id = self._active_ai_session_id
        if session_id is None:
            panel.set_run_busy(False)
            return
        self._on_ai_assistant_finished(session_id, thinking, content)

    @Slot(str, str, str)
    def _deliver_ai_worker_failed(self, message: str, thinking: str, content: str) -> None:
        """Marshal chat failure onto the GUI thread before updating UI."""
        self_q = cast(QObject, self)
        if QThread.currentThread() != self_q.thread():
            self_q._ai_chat_fail_requested.emit(message, thinking, content)  # type: ignore[attr-defined]
            return
        self._apply_ai_worker_failed(message, thinking, content)

    @Slot(str, str, str)
    def _apply_ai_worker_failed(self, message: str, thinking: str, content: str) -> None:
        """Show chat failure on the GUI thread."""
        panel = self._right_sidebar.ai_chat_panel
        ctx = self._active_run_context
        if ctx is None:
            panel.set_run_busy(False)
            return

        stopped = message.strip().lower() == "stopped"
        stop_mode = self._stopped_generations.get(ctx.run_generation)
        if stopped and stop_mode == "pre_stream":
            panel.set_run_busy(False)
            self._stopped_generations.pop(ctx.run_generation, None)
            return

        session_id = ctx.session_id
        if self._active_ai_session_id != session_id:
            panel.set_run_busy(False)
            return

        if stopped and stop_mode == "post_stream":
            self._persist_stopped_assistant(session_id, thinking, content)
            panel.set_run_busy(False)
            self._stopped_generations.pop(ctx.run_generation, None)
            return

        self._on_ai_chat_failed(session_id, message, thinking, content)

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
        thinking = pick_richest_text(thinking, panel.streaming_assistant_thinking())
        content = pick_richest_text(content, panel.streaming_assistant_text())
        panel.end_assistant_stream(content, thinking=thinking)
        thinking_duration = panel.last_assistant_thinking_duration_seconds()
        assistant_row = AiChatSessionService.record_assistant_message(
            session_id,
            content,
            thinking=thinking,
            thinking_duration_seconds=thinking_duration,
        )
        panel.attach_streaming_assistant_message_id(assistant_row["id"])
        panel.set_run_busy(False)
        self._pending_title_session_id = session_id

    def _on_ai_chat_stop(self) -> None:
        """Interrupt the in-flight chat worker and reset UI immediately."""
        self._handle_chat_stop()

    def _handle_chat_stop(self) -> None:
        """Optimistically finalize stop UI, then interrupt the worker."""
        panel = self._right_sidebar.ai_chat_panel
        ctx = self._active_run_context
        if ctx is None:
            panel.set_run_busy(False)
            worker = self._ai_chat_worker
            if worker is not None:
                worker.cancel()
            return

        if panel.is_pre_stream_cancel():
            self._rollback_pre_stream_stop(ctx)
            self._mark_run_stopped(ctx.run_generation, pre_stream=True)
        else:
            self._finalize_stream_stop_optimistic(ctx)
            self._mark_run_stopped(ctx.run_generation, pre_stream=False)

        worker = self._ai_chat_worker
        if worker is not None:
            worker.cancel()

    def _mark_run_stopped(self, run_generation: int, *, pre_stream: bool) -> None:
        """Record that *run_generation* was stopped so late worker signals no-op."""
        mode: _StopMode = "pre_stream" if pre_stream else "post_stream"
        self._stopped_generations[run_generation] = mode

    def _rollback_pre_stream_stop(self, ctx: _AiChatRunContext) -> None:
        """Rewind an activity-only send back into the composer."""
        panel = self._right_sidebar.ai_chat_panel
        panel.rollback_pre_stream_turn(ctx.user_text)
        AiChatSessionService.delete_message(ctx.session_id, ctx.user_message_id)
        panel.set_run_busy(False)

    def _finalize_stream_stop_optimistic(self, ctx: _AiChatRunContext) -> None:
        """Finalize partial assistant text with a Stopped footer on the GUI thread."""
        _ = ctx
        panel = self._right_sidebar.ai_chat_panel
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
        assistant_row = AiChatSessionService.record_assistant_message(
            session_id,
            display,
            thinking=thinking,
            thinking_duration_seconds=thinking_duration,
        )
        panel.attach_streaming_assistant_message_id(assistant_row["id"])

    def _cancel_active_chat_run(self) -> None:
        """Request stop on any in-flight worker without optimistic UI rollback."""
        worker = getattr(self, "_ai_chat_worker", None)
        if worker is not None:
            worker.cancel()
        panel = self._right_sidebar.ai_chat_panel
        panel.set_run_busy(False)

    def _on_ai_chat_failed(
        self,
        session_id: str,
        message: str,
        thinking_partial: str,
        content_partial: str,
    ) -> None:
        """Show thinking and answer (if any) plus the error, and persist them."""
        panel = self._right_sidebar.ai_chat_panel
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
        assistant_row = AiChatSessionService.record_assistant_message(
            session_id,
            display,
            thinking=thinking,
            thinking_duration_seconds=thinking_duration,
        )
        panel.attach_streaming_assistant_message_id(assistant_row["id"])
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

    def _maybe_generate_session_title(self, session_id: str) -> None:
        """Generate a title off-GUI after the first user/assistant exchange."""
        messages = AiChatSessionService.get_messages(session_id)
        if len(messages) != 2:
            return

        session = AiChatSessionService.get_session(session_id)
        if session is None:
            return

        entry = self._right_sidebar.ai_chat_panel.current_model_entry()
        if entry is None:
            return
        if self._ai_title_thread is not None and self._ai_title_thread.isRunning():
            return

        self._title_run_session_id = session_id
        worker = AiChatTitleWorker()
        worker.set_run(
            session_id=session_id,
            entry=entry,
            agent_id=session["agent_id"],
        )
        thread = QThread(cast(QObject, self))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        queued = Qt.ConnectionType.QueuedConnection
        worker.title_ready.connect(self._deliver_ai_title_worker_ready, queued)
        worker.title_ready.connect(thread.quit, queued)
        worker.failed.connect(thread.quit, queued)
        thread.finished.connect(self._on_ai_title_thread_finished)

        self._ai_title_thread = thread
        self._ai_title_worker = worker
        thread.start()

    @Slot(str)
    def _deliver_ai_title_worker_ready(self, title: str) -> None:
        """Marshal generated title onto the GUI thread."""
        self_q = cast(QObject, self)
        if QThread.currentThread() != self_q.thread():
            self_q._ai_title_ready_requested.emit(title)  # type: ignore[attr-defined]
            return
        self._apply_ai_title_worker_ready(title)

    @Slot(str)
    def _apply_ai_title_worker_ready(self, title: str) -> None:
        """Apply a generated session title on the GUI thread."""
        session_id = self._title_run_session_id
        if session_id is None:
            return
        self._on_ai_title_ready(session_id, title)

    def _on_ai_title_ready(self, session_id: str, title: str) -> None:
        """Apply a generated title to the session row."""
        if session_id != self._active_ai_session_id:
            return
        if session_id in self._manual_ai_session_titles:
            return
        AiChatSessionService.rename_session(session_id, title)
        self._sync_ai_session_title()

    def _on_ai_chat_thread_finished(self) -> None:
        """Release chat worker/thread after the QThread has fully stopped."""
        worker = self._ai_chat_worker
        thread = self._ai_chat_thread
        panel = self._right_sidebar.ai_chat_panel
        if worker is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                worker.chunk_received.disconnect(panel.deliver_assistant_chunk)
                worker.status_changed.disconnect(panel.deliver_activity_status)
            worker.deleteLater()
        if thread is not None:
            thread.deleteLater()
        self._ai_chat_thread = None
        self._ai_chat_worker = None
        pending = self._pending_title_session_id
        self._pending_title_session_id = None
        if pending:
            self._maybe_generate_session_title(pending)

    def _on_ai_title_thread_finished(self) -> None:
        """Release title worker/thread after the QThread has fully stopped."""
        worker = self._ai_title_worker
        thread = self._ai_title_thread
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            thread.deleteLater()
        self._ai_title_thread = None
        self._ai_title_worker = None
        self._title_run_session_id = None

    def _cleanup_ai_chat_threads(self) -> None:
        """Stop AI chat/title worker threads during window teardown."""
        self._pending_title_session_id = None
        self._session_loader.shutdown()
        for attr in ("_ai_chat_thread", "_ai_title_thread"):
            thread = getattr(self, attr)
            if thread is None:
                continue
            if thread.isRunning():
                thread.quit()
                thread.wait(5000)
            setattr(self, attr, None)
        self._ai_chat_worker = None
        self._ai_title_worker = None
