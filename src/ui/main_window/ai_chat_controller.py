"""AI chat controller mixin for the main window."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QObject, QThread, Qt, Slot

from services.ai.ai_config import AiConfig
from services.ai.chat.agent_registry import DEFAULT_AGENT_ID
from services.ai.chat.response_text import pick_richest_text
from services.ai.chat.session_service import AiChatSessionService, ComposerRunContext
from ui.sidebar.ai.chat_sessions.history_popup import AiSessionHistoryPopup
from ui.sidebar.ai.workers.chat_worker import AiChatWorker
from ui.sidebar.ai.workers.title_worker import AiChatTitleWorker

if TYPE_CHECKING:
    from ui.sidebar import RightSidebar

logger = logging.getLogger(__name__)


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

    def _init_ai_chat_controller(self) -> None:
        """Connect sidebar signals and initialise chat state."""
        self._ai_chat_thread = None
        self._ai_chat_worker = None
        self._ai_title_thread = None
        self._ai_title_worker = None
        self._active_ai_session_id = None
        self._pending_title_session_id = None
        self._title_run_session_id = None

        panel = self._right_sidebar.ai_chat_panel
        # Synchronous on the GUI thread: begin_assistant_stream runs before _on_send
        # returns so turn-boundary scroll sees both user and assistant bubbles.
        panel.message_submitted.connect(self._on_ai_message_submitted)
        panel.stop_requested.connect(self._on_ai_chat_stop)
        self._right_sidebar.ai_new_chat_requested.connect(self._on_ai_new_chat)
        self._right_sidebar.ai_session_history_requested.connect(self._on_ai_session_history)
        self_q = cast(QObject, self)
        queued = Qt.ConnectionType.QueuedConnection
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
        self._restore_active_chat_session()

    def _on_ai_new_chat(self) -> None:
        """Clear transcript UI; next send creates a fresh session."""
        self._active_ai_session_id = None
        AiConfig.set_chat_session_id("")
        self._right_sidebar.ai_chat_panel.clear()

    def _on_ai_session_history(self) -> None:
        """Open the session history popover."""
        popup = AiSessionHistoryPopup.instance()
        if popup.isVisible():
            popup.hide_popup()
            return
        sessions = AiChatSessionService.list_sessions()
        popup.show_for(
            self._right_sidebar.ai_history_button,
            sessions,
            self._on_ai_session_selected,
        )

    def _on_ai_session_selected(self, session_id: str) -> None:
        """Load a session transcript into the panel."""
        self._activate_chat_session(session_id)

    def _activate_chat_session(self, session_id: str) -> None:
        """Load *session_id* into the panel and persist it as the active chat."""
        session = AiChatSessionService.get_session(session_id)
        if session is None:
            return
        self._active_ai_session_id = session_id
        AiConfig.set_chat_session_id(session_id)
        panel = self._right_sidebar.ai_chat_panel
        panel.load_transcript(AiChatSessionService.get_messages(session_id))
        model_id = session.get("model_id")
        if isinstance(model_id, str) and model_id:
            panel.select_model_if_available(model_id)
        mode = session.get("mode")
        if isinstance(mode, str) and mode.strip():
            panel.set_mode(mode.strip())

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

        AiChatSessionService.record_user_message(session_id, text)
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
        session_id = self._active_ai_session_id
        if session_id is None:
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
        session_id = self._active_ai_session_id
        if session_id is None:
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
        AiChatSessionService.record_assistant_message(
            session_id,
            content,
            thinking=thinking,
            thinking_duration_seconds=thinking_duration,
        )
        panel.set_run_busy(False)
        self._pending_title_session_id = session_id

    def _on_ai_chat_stop(self) -> None:
        """Interrupt the in-flight chat worker."""
        worker = self._ai_chat_worker
        if worker is not None:
            worker.cancel()

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
        AiChatSessionService.record_assistant_message(
            session_id,
            display,
            thinking=thinking,
            thinking_duration_seconds=thinking_duration,
        )
        panel.set_run_busy(False)

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
        AiChatSessionService.rename_session(session_id, title)

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
