"""AI chat controller mixin for the main window."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from PySide6.QtCore import QObject, Qt, QThread, Slot

from services.ai.ai_config import AiConfig
from services.ai.chat.agent_registry import DEFAULT_AGENT_ID
from services.ai.chat.budget_status import connection_budget_status
from services.ai.chat.run_registry import AiChatRunContext
from services.ai.chat.session_service import (
    AiChatSessionDict,
    AiChatSessionService,
    AiChatSessionTailLoadDict,
    AiChatTranscriptPageDict,
    ComposerRunContext,
    UserMessageSendSnapshot,
)
from ui.main_window.ai_chat_runs import _AiChatRunsMixin
from ui.main_window.ai_chat_title import _AiChatTitleMixin
from ui.main_window.ai_chat_turn_finalize import _AiChatTurnFinalizeMixin
from ui.sidebar.ai.chat_sessions.history_popup import AiSessionHistoryPopup
from ui.sidebar.ai.workers.session_load_worker import AiChatSessionLoader
from ui.sidebar.ai.workers.title_worker import AiChatTitleWorker

if TYPE_CHECKING:
    from ui.sidebar import RightSidebar

_StopMode = Literal["pre_stream", "post_stream"]

# Backward-compatible alias for tests.
_AiChatRunContext = AiChatRunContext


class _AiChatControllerMixin(_AiChatRunsMixin, _AiChatTurnFinalizeMixin, _AiChatTitleMixin):
    """Wire AI chat panel, session service, and background workers."""

    _right_sidebar: RightSidebar
    _ai_title_thread: QThread | None
    _ai_title_worker: AiChatTitleWorker | None
    _active_ai_session_id: str | None
    _pending_title_session_id: str | None
    _pending_fork_composer: tuple[str, str] | None
    _title_run_session_id: str | None
    _session_load_generation: int
    _session_loader: AiChatSessionLoader
    _manual_ai_session_titles: set[str]
    _ai_title_thread_generation: int
    _active_run_context: AiChatRunContext | None
    _stopped_generations: dict[int, _StopMode]

    def _init_ai_chat_controller(self) -> None:
        """Connect sidebar signals and initialise chat state."""
        self._ai_title_thread = None
        self._ai_title_worker = None
        self._active_ai_session_id = None
        self._pending_title_session_id = None
        self._pending_fork_composer = None
        self._title_run_session_id = None
        self._session_load_generation = 0
        self._manual_ai_session_titles = set()
        self._ai_title_thread_generation = 0
        self._active_run_context = None
        self._stopped_generations = {}
        self._init_chat_run_registry()

        self_q = cast(QObject, self)
        self._session_loader = AiChatSessionLoader(self_q)
        queued = Qt.ConnectionType.QueuedConnection
        self._session_loader.finished.connect(self._on_session_load_finished, queued)

        panel = self._right_sidebar.ai_chat_panel
        panel.set_window_load_callback(self._on_transcript_window_load_requested)
        panel.transcript_load_finished.connect(self._on_ai_transcript_load_finished)
        # Synchronous on the GUI thread: begin_assistant_stream runs before _on_send
        # returns so turn-boundary scroll sees both user and assistant bubbles.
        panel.message_submitted.connect(self._on_ai_message_submitted)
        panel.stop_requested.connect(self._on_ai_chat_stop)
        panel.assistant_fork_requested.connect(self._on_assistant_fork_requested)
        panel.user_fork_requested.connect(self._on_user_fork_requested)
        panel.user_edit_requested.connect(self._on_user_edit_requested)
        panel.user_edit_submitted.connect(self._on_user_edit_submitted)
        self._right_sidebar.ai_new_chat_requested.connect(self._on_ai_new_chat)
        self._right_sidebar.ai_session_history_requested.connect(self._on_ai_session_history)
        self._right_sidebar.ai_session_title_renamed.connect(self._on_ai_session_title_renamed)
        self_q._ai_assistant_finish_requested.connect(  # type: ignore[attr-defined]
            self._apply_registry_assistant_finished,
            queued,
        )
        self_q._ai_chat_fail_requested.connect(  # type: ignore[attr-defined]
            self._apply_registry_failed,
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

    def _on_ai_transcript_load_finished(self) -> None:
        """Refresh context usage and apply pending fork composer draft after load."""
        panel = self._right_sidebar.ai_chat_panel
        pending = self._pending_fork_composer
        if pending is not None and pending[0] == self._active_ai_session_id:
            self._pending_fork_composer = None
            panel.restore_composer_text(pending[1])
        panel.refresh_context_usage()
        session_id = self._active_ai_session_id
        if session_id is not None:
            self._reattach_session_run_if_needed(session_id)
        self._update_active_session_busy_state()

    def _on_ai_new_chat(self) -> None:
        """Clear transcript UI; next send creates a fresh session."""
        self._session_load_generation += 1
        self._session_loader.cancel()
        panel = self._right_sidebar.ai_chat_panel
        panel._cancel_inline_edit_if_active()
        panel.cancel_transcript_load()
        self._active_ai_session_id = None
        AiConfig.set_chat_session_id("")
        self._right_sidebar.ai_chat_panel.clear()
        self._right_sidebar.ai_chat_panel._reset_context_usage_chrome()
        self._sync_ai_session_title()
        self._update_active_session_busy_state()

    def _on_ai_session_history(self) -> None:
        """Toggle the session history popover."""
        popup = AiSessionHistoryPopup.instance()
        if popup.isVisible():
            popup.hide_popup()
            return
        self._right_sidebar.ai_chat_panel._hide_context_popup()
        popup.open_for(
            self._right_sidebar.ai_history_button,
            self._on_ai_session_selected,
            active_session_id=self._active_ai_session_id,
            on_active_session_deleted=self._on_ai_new_chat,
            on_sessions_changed=self._sync_ai_session_title,
        )
        registry = getattr(self, "_chat_run_registry", None)
        if registry is not None:
            popup.set_running_session_ids(registry.running_session_ids())

    def _on_ai_session_selected(self, session_id: str) -> None:
        """Load a session transcript into the panel."""
        self._activate_chat_session(session_id)

    def _activate_chat_session(self, session_id: str) -> None:
        """Load *session_id* into the panel and persist it as the active chat."""
        if session_id == self._active_ai_session_id:
            return
        self._session_loader.cancel()
        self._session_load_generation += 1
        generation = self._session_load_generation
        panel = self._right_sidebar.ai_chat_panel
        panel._cancel_inline_edit_if_active()
        panel._reset_context_usage_chrome()
        registry = getattr(self, "_chat_run_registry", None)
        panel.set_run_busy(registry.is_running(session_id) if registry is not None else False)
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
        stored_id = AiConfig.get_chat_model_id()
        enabled_ids = {entry["id"] for entry in panel._models}
        if stored_id in enabled_ids:
            panel.select_model_if_available(stored_id)
        else:
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
        panel.begin_virtual_session(session["id"], page, session_model_id=session.get("model_id"))
        panel.load_transcript_async(
            page["messages"],
            generation=generation,
            lazy_markdown=True,
            page=page,
        )
        self._update_active_session_busy_state()

    def _restore_active_chat_session(self) -> None:
        """Reload the last active chat transcript after startup."""
        session_id = AiChatSessionService.resolve_restore_session_id()
        if session_id is None:
            return
        self._activate_chat_session(session_id)

    def _on_ai_message_submitted(self, text: str) -> None:
        """Handle a user message: persist, stream assistant reply."""
        panel = self._right_sidebar.ai_chat_panel
        entry = panel.current_model_entry()
        if entry is None:
            return
        if self._budget_blocks_send(panel, entry):
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
                session_model_id=str(entry["id"]),
            )

        if self._chat_run_registry.is_running(session_id):
            return

        user_row = AiChatSessionService.record_user_message(
            session_id,
            text,
            send_snapshot=self._send_snapshot_from_panel(panel),
        )
        panel.attach_last_user_message_id(user_row["id"])

        composer = ComposerRunContext(
            reasoning_effort=panel.current_reasoning_effort(),
            thinking_enabled=panel.current_thinking_enabled(),
            run_context_tokens=panel.current_run_context_tokens(),
        )
        session_row = AiChatSessionService.get_session(session_id)
        agent_id = session_row["agent_id"] if session_row else DEFAULT_AGENT_ID
        self._start_chat_run(
            session_id=session_id,
            user_message_id=user_row["id"],
            user_text=text,
            entry=entry,
            agent_id=agent_id,
            text=text,
            composer=composer,
        )

    def _send_snapshot_from_panel(self, panel) -> UserMessageSendSnapshot:
        """Build a per-send snapshot from the docked composer and session agent."""
        snapshot = panel._docked_composer.read_send_snapshot()
        session_id = self._active_ai_session_id
        if session_id:
            session_row = AiChatSessionService.get_session(session_id)
            if session_row is not None:
                snapshot["send_agent_id"] = str(session_row.get("agent_id") or DEFAULT_AGENT_ID)
        return cast(UserMessageSendSnapshot, snapshot)

    def _budget_blocks_send(self, panel, entry) -> bool:
        """Refresh budget chrome and return True when hard cap blocks a new send."""
        status = connection_budget_status(entry)
        panel.refresh_connection_budget(status)
        return status["state"] == "hard_exceeded"

    @Slot(int)
    def _on_user_edit_requested(self, message_id: int) -> None:
        """Begin inline edit when the panel signals a user-message edit."""
        panel = self._right_sidebar.ai_chat_panel
        if panel._run_busy:
            return
        panel.begin_inline_edit(message_id)

    @Slot(int, str)
    def _on_user_edit_submitted(self, message_id: int, text: str) -> None:
        """Confirm truncate, persist edit, and resubmit the assistant turn."""
        from PySide6.QtWidgets import QMessageBox

        panel = self._right_sidebar.ai_chat_panel
        session_id = self._active_ai_session_id
        if session_id is None:
            return
        if self._chat_run_registry.is_running(session_id):
            return

        later_count = AiChatSessionService.count_messages_after(session_id, message_id)
        if later_count > 0:
            box = QMessageBox(self._right_sidebar)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Edit message")
            noun = "message" if later_count == 1 else "messages"
            box.setText(
                f"Editing will delete {later_count} later {noun} "
                "and regenerate the assistant reply."
            )
            box.setStandardButtons(
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok
            )
            box.button(QMessageBox.StandardButton.Ok).setText("Continue")
            if box.exec() != QMessageBox.StandardButton.Ok:
                return

        inline = panel._inline_edit
        composer = inline.composer if inline is not None else panel._docked_composer
        send_snapshot = composer.read_send_snapshot()
        session_row = AiChatSessionService.get_session(session_id)
        if session_row is not None:
            send_snapshot["send_agent_id"] = str(session_row.get("agent_id") or DEFAULT_AGENT_ID)

        if not AiChatSessionService.edit_user_message_and_rewind(
            session_id,
            message_id,
            text,
            send_snapshot,
        ):
            return

        panel.truncate_transcript_after(message_id)
        panel._refresh_session_spend_breakdown()
        panel.refresh_context_usage()
        panel._docked_composer.apply_send_snapshot(send_snapshot)
        panel.select_model_if_available(str(send_snapshot.get("send_model_id") or ""))
        mode = send_snapshot.get("send_mode")
        if isinstance(mode, str) and mode.strip():
            panel.set_mode(mode.strip())

        entry = composer.current_model_entry() or panel.current_model_entry()
        if entry is None:
            return
        if self._budget_blocks_send(panel, entry):
            return

        user_bubble = panel._bubble_by_message_id.get(message_id)
        if user_bubble is not None:
            panel._turn_scroll_anchor = user_bubble
            panel._streaming_turn_user_bubble = user_bubble

        self._start_chat_run(
            session_id=session_id,
            user_message_id=message_id,
            user_text=text,
            entry=entry,
            agent_id=str(send_snapshot.get("send_agent_id") or DEFAULT_AGENT_ID),
            text=text,
            composer=ComposerRunContext(
                reasoning_effort=composer.current_reasoning_effort(),
                thinking_enabled=composer.current_thinking_enabled(),
                run_context_tokens=composer.current_run_context_tokens(),
            ),
        )

    def _on_assistant_fork_requested(self, message_id: int) -> None:
        """Fork the active session at *message_id* and switch to the new chat."""
        session_id = self._active_ai_session_id
        if session_id is None or message_id <= 0:
            return
        forked = AiChatSessionService.fork_session_at_message(session_id, message_id)
        if forked is None:
            return
        self._activate_chat_session(forked["id"])

    def _on_user_fork_requested(self, message_id: int) -> None:
        """Fork before *message_id* and pre-fill the composer with that user text."""
        session_id = self._active_ai_session_id
        if session_id is None or message_id <= 0:
            return
        result = AiChatSessionService.fork_session_at_user_message(session_id, message_id)
        if result is None:
            return
        forked = result["session"]
        self._pending_fork_composer = (forked["id"], result["composer_draft"])
        self._activate_chat_session(forked["id"])

    def _on_ai_chat_stop(self) -> None:
        """Interrupt the in-flight chat worker and reset UI immediately."""
        self._handle_chat_stop()

    def _cleanup_ai_chat_threads(self) -> None:
        """Stop AI chat/title worker threads during window teardown."""
        self._pending_title_session_id = None
        self._session_loader.shutdown()
        self._chat_run_registry.cancel_all()
        self._cleanup_ai_title_thread()
