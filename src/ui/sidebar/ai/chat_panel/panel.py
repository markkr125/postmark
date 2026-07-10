"""AI assistant chat panel — transcript, composer, and model/mode controls."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent, QHideEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QLabel, QLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

from services.ai.ai_config import AiModelEntry, model_entry_enabled
from services.ai.chat.session_service import AiChatMessageDict
from services.ai.chat.subagent_events import SubagentRunRecord
from ui.sidebar.ai.agent_mode_popup import AiAgentModePopup
from ui.sidebar.ai.chat_panel.composer import AiChatComposer
from ui.sidebar.ai.chat_panel.composer.budget_banner import AiChatBudgetBanner
from ui.sidebar.ai.chat_panel.context_usage_panel import _ChatPanelContextUsageMixin
from ui.sidebar.ai.chat_panel.inline_edit import _ChatPanelInlineEditMixin
from ui.sidebar.ai.chat_panel_streaming import _ChatPanelStreamingMixin
from ui.sidebar.ai.chat_transcript_loading_row import ChatTranscriptLoadingOverlay
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.model_picker_popup import AiModelPickerPopup
from ui.sidebar.ai.subagent_detail_dialog import SubagentDetailDialog
from ui.styling.icons import phi

_EMPTY_STATE_TEXT = "Ask anything about your API requests."
_CHAT_SCROLL_PADDING_LEFT = 8
_CHAT_SCROLL_PADDING_RIGHT = 8


class _TranscriptMessages(QWidget):
    """Scroll-area content host that never requests a width wider than the viewport."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the transcript layout host."""
        super().__init__(parent)
        self._viewport_resize_filter_installed = False

    def showEvent(self, event: QShowEvent) -> None:
        """Watch viewport width so minimum size stays within the visible column."""
        super().showEvent(event)
        self._ensure_viewport_resize_filter()

    def _ensure_viewport_resize_filter(self) -> None:
        """Install a resize filter on the scroll viewport once parented."""
        viewport = self.parentWidget()
        if viewport is None or self._viewport_resize_filter_installed:
            return
        viewport.installEventFilter(self)
        self._viewport_resize_filter_installed = True
        self._sync_width_to_viewport()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Keep the transcript host width matched to the viewport column."""
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._sync_width_to_viewport()
        return False

    def _sync_width_to_viewport(self) -> None:
        """Pin the transcript host to the current viewport width."""
        viewport = self.parentWidget()
        vp_w = viewport.width() if viewport is not None else 0
        if vp_w <= 0:
            return
        self.setMinimumWidth(vp_w)
        self.setMaximumWidth(vp_w)
        if self.width() != vp_w:
            self.resize(vp_w, self.height())
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        """Cap horizontal minimum so a vertical scrollbar cannot force horizontal scroll."""
        hint = super().minimumSizeHint()
        return self._cap_hint_to_viewport_width(hint)

    def sizeHint(self) -> QSize:
        """Cap preferred width so ``QScrollArea`` does not grow the transcript wider."""
        hint = super().sizeHint()
        return self._cap_hint_to_viewport_width(hint)

    def _cap_hint_to_viewport_width(self, hint: QSize) -> QSize:
        """Return *hint* with width no wider than the scroll viewport."""
        viewport = self.parentWidget()
        if viewport is not None:
            viewport_w = viewport.width()
            if viewport_w > 0:
                return QSize(min(hint.width(), viewport_w), hint.height())
        return hint


class AiChatPanel(
    _ChatPanelInlineEditMixin,
    _ChatPanelStreamingMixin,
    _ChatPanelContextUsageMixin,
    QWidget,
):  # type: ignore[misc]
    """Right-sidebar AI chat skeleton (transcript + composer)."""

    message_submitted = Signal(str)
    stop_requested = Signal()
    assistant_fork_requested = Signal(int)
    workspace_target_requested = Signal(str, int, str)
    user_fork_requested = Signal(int)
    user_edit_requested = Signal(int)
    user_edit_submitted = Signal(int, str)
    mode_changed = Signal(str)
    attachments_changed = Signal(list)
    manage_models_requested = Signal()
    budget_settings_requested = Signal()
    effort_changed = Signal(str, str)
    context_requested = Signal()
    transcript_load_finished = Signal()
    _assistant_chunk_delivery_requested = Signal(str, str)
    _activity_status_delivery_requested = Signal(str)
    _context_usage_metrics_delivery_requested = Signal(object)
    _context_usage_refresh_delivery_requested = Signal()
    _context_usage_schedule_requested = Signal()
    _subagent_update_delivery_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the transcript scroll area and the composer."""
        super().__init__(parent)
        self.setObjectName("aiChatPanel")
        self._attachments: list[str] = []
        self._models: list[AiModelEntry] = []
        self._streaming_bubble: ChatMessageBubble | None = None
        self._stream_generation = 0
        self._open_stream_generation = 0
        self._run_busy = False

        self._picker_popup = AiModelPickerPopup.instance()
        self._mode_popup = AiAgentModePopup.instance()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(8)

        # --- Transcript ------------------------------------------------
        self._scroll = QScrollArea()
        self._scroll.setObjectName("aiChatScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self._messages = _TranscriptMessages()
        self._messages_layout = QVBoxLayout(self._messages)
        self._messages_layout.setContentsMargins(
            _CHAT_SCROLL_PADDING_LEFT,
            0,
            _CHAT_SCROLL_PADDING_RIGHT,
            0,
        )
        self._messages_layout.setSpacing(8)
        self._messages_layout.setSizeConstraints(
            QLayout.SizeConstraint.SetNoConstraint,
            QLayout.SizeConstraint.SetMinAndMaxSize,
        )
        self._messages_layout.addStretch(1)  # pushes bubbles to the bottom

        self._empty_label = QLabel(_EMPTY_STATE_TEXT)
        self._empty_label.setObjectName("emptyStateLabel")
        self._empty_label.setWordWrap(True)
        self._empty_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._messages_layout.addWidget(self._empty_label)

        self._transcript_loading = ChatTranscriptLoadingOverlay(self._scroll.viewport())

        self._scroll.setWidget(self._messages)
        self._scroll_lock_enabled = False
        self._programmatic_scroll = False
        self._turn_scroll_pending = False
        self._streaming_viewport_spacer = None
        self._turn_scroll_anchor = None
        self._sticky_turn_anchor = None
        self._stream_content_started = False
        self._stream_thinking_bottom_follow = False
        self._sticky_turn_prompt = None
        self._sticky_turn_pairs = []
        self._sticky_turn_pairs_dirty = True
        self._sticky_turn_extents = []
        self._sticky_extent_by_assistant = {}
        self._sticky_extents_dirty = True
        self._sticky_applied_anchor = None
        self._sticky_applied_assistant_id = None
        self._sticky_applied_prompt_text = ""
        self._sticky_applied_visible = False
        self._sticky_applied_geom = (0, 0, 0, 0)
        self._sticky_applied_height_cap = 0
        self._sticky_sync_pending = False
        self._sticky_sync_frame_pending = False
        self._smooth_scroll_active = False
        self._sticky_sync_deferred_during_smooth = False
        self._transcript_layout_hooks = []
        self._init_scroll_controller()

        self._scroll_down_btn = QPushButton(self._scroll.viewport())
        self._scroll_down_btn.setObjectName("aiChatScrollDown")
        self._scroll_down_btn.setIcon(phi("caret-down", size=14))
        self._scroll_down_btn.setToolTip("Scroll to bottom")
        self._scroll_down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scroll_down_btn.hide()
        self._scroll_down_btn.clicked.connect(lambda: self._scroll_to_bottom(force=True))

        root.addWidget(self._scroll, 1)

        composer_col = QWidget(self)
        composer_col_layout = QVBoxLayout(composer_col)
        composer_col_layout.setContentsMargins(0, 0, 0, 0)
        composer_col_layout.setSpacing(4)

        self._budget_banner = AiChatBudgetBanner(composer_col)
        self._budget_banner.hide()
        self._budget_banner.open_settings_clicked.connect(self.budget_settings_requested.emit)
        composer_col_layout.addWidget(self._budget_banner)

        self._docked_composer = AiChatComposer(composer_col)
        self._docked_composer.submit_requested.connect(self._on_docked_send)
        self._docked_composer.stop_requested.connect(self.stop_requested.emit)
        self._docked_composer.mode_changed.connect(self.mode_changed.emit)
        self._docked_composer.model_changed.connect(self._on_composer_model_changed)
        self._docked_composer.attachments_changed.connect(self._on_composer_attachments_changed)
        self._docked_composer.model_picker_requested.connect(self._open_model_picker)
        self._docked_composer.mode_picker_requested.connect(self._open_mode_picker)
        composer_col_layout.addWidget(self._docked_composer)
        root.addWidget(composer_col)

        self._init_inline_edit_state()
        self._init_chat_streaming_state()
        self._init_context_usage_state()
        queued = Qt.ConnectionType.QueuedConnection
        self._assistant_chunk_delivery_requested.connect(self._apply_assistant_chunk, queued)
        self._activity_status_delivery_requested.connect(self._apply_activity_status, queued)
        self._context_usage_metrics_delivery_requested.connect(
            self._apply_context_usage_metrics,
            queued,
        )
        self._context_usage_refresh_delivery_requested.connect(
            self._apply_context_usage_refresh,
            queued,
        )
        self._context_usage_schedule_requested.connect(
            self._schedule_context_usage_refresh_on_gui,
            queued,
        )
        self._subagent_update_delivery_requested.connect(
            self._apply_subagent_update,
            queued,
        )

        self._subagent_detail_dialog: SubagentDetailDialog | None = None

        self.set_models([])
        self._reset_context_usage_chrome()

    def hideEvent(self, event: QHideEvent) -> None:
        """Dismiss context popover when the panel is hidden.

        Do **not** tear down the context-usage ``QThread`` here. The AI panel
        starts hidden in the right flyout and is toggled often; shutting the
        worker on every hide races with ``set_models`` / refresh and can abort
        the process (``QThread: Destroyed while thread is still running``).
        """
        self._cancel_inline_edit_if_active()
        self._hide_context_popup()
        super().hideEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop background workers when the panel is permanently closed."""
        self._shutdown_context_usage_worker()
        super().closeEvent(event)

    @property
    def _input(self):
        """Backward-compatible accessor for the docked prompt input."""
        return self._docked_composer.input_widget()

    @property
    def _model_btn(self):
        """Backward-compatible accessor for the docked model pill."""
        return self._docked_composer.model_button()

    @property
    def _mode_btn(self):
        """Backward-compatible accessor for the docked mode pill."""
        return self._docked_composer.mode_button()

    @property
    def _send_btn(self):
        """Backward-compatible accessor for the docked send button."""
        return self._docked_composer.send_button()

    @property
    def _context_ring(self):
        """Backward-compatible accessor for the docked context ring."""
        return self._docked_composer.context_ring()

    @property
    def _attachments_row(self):
        """Backward-compatible accessor for the docked attachments row."""
        return self._docked_composer.findChild(QWidget, "aiChatAttachments")

    def _on_send(self) -> None:
        """Backward-compatible alias for docked composer send."""
        self._on_docked_send()

    def _add_attachment_chip(self, path: str) -> None:
        """Backward-compatible shim — add a chip on the docked composer."""
        composer = self._docked_composer
        if path not in composer._attachments:
            composer._attachments.append(path)
        composer._add_attachment_chip(path)

    def _remove_attachment(self, path: str, chip: QWidget) -> None:
        """Backward-compatible shim — remove a chip from the docked composer."""
        self._docked_composer._remove_attachment(path, chip)  # type: ignore[arg-type]

    @Slot(str, str)
    def deliver_assistant_chunk(self, thinking_delta: str, content_delta: str) -> None:
        """GUI-thread slot for worker ``chunk_received`` (QueuedConnection)."""
        if QThread.currentThread() != self.thread():
            self._assistant_chunk_delivery_requested.emit(thinking_delta, content_delta)
            return
        self._apply_assistant_chunk(thinking_delta, content_delta)

    @Slot(str, str)
    def _apply_assistant_chunk(self, thinking_delta: str, content_delta: str) -> None:
        """Append an assistant chunk after delivery has reached the GUI thread."""
        self.append_assistant_chunk(thinking_delta, content_delta)

    def deliver_subagent_update(self, records: object) -> None:
        """GUI-thread slot for worker ``subagent_updated`` (QueuedConnection)."""
        if QThread.currentThread() != self.thread():
            self._subagent_update_delivery_requested.emit(records)
            return
        self._apply_subagent_update(records)

    @Slot(object)
    def _apply_subagent_update(self, records: object) -> None:
        """Apply subagent card updates to the active streaming bubble."""
        if not isinstance(records, list):
            return
        normalized: list[SubagentRunRecord] = []
        for record in records:
            if isinstance(record, dict) and record.get("id"):
                normalized.append(record)  # type: ignore[arg-type]
        if not normalized:
            return
        bubble = self._resolve_streaming_bubble()  # type: ignore[attr-defined]
        if bubble is None:
            if self._open_stream_generation == 0:  # type: ignore[attr-defined]
                return
            bubble = self._ensure_streaming_turn_widgets()  # type: ignore[attr-defined]
        else:
            self._streaming_bubble = bubble  # type: ignore[attr-defined]
        session_id = getattr(self, "_virtual_session_id", None) or self._context_session_id
        bubble.set_subagent_session_id(session_id)
        bubble.set_subagent_records(normalized)
        dialog = getattr(self, "_subagent_detail_dialog", None)
        if dialog is not None and dialog.isVisible():
            open_id = dialog.record_id()
            if open_id:
                updated = bubble.subagent_record(open_id)
                if updated is not None:
                    dialog.refresh_record(updated)
        self._sync_subagent_poll_timer()  # type: ignore[attr-defined]
        self._request_turn_bottom_scroll()  # type: ignore[attr-defined]
        self._follow_streaming_turn_layout()  # type: ignore[attr-defined]

    @Slot(str)
    def deliver_activity_status(self, raw_status: str) -> None:
        """GUI-thread slot for worker ``status_changed`` (QueuedConnection)."""
        if QThread.currentThread() != self.thread():
            self._activity_status_delivery_requested.emit(raw_status)
            return
        self._apply_activity_status(raw_status)

    @Slot(str)
    def _apply_activity_status(self, raw_status: str) -> None:
        """Apply activity status after delivery has reached the GUI thread."""
        self.set_activity_status(raw_status)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_models(self, entries: list[AiModelEntry]) -> None:
        """Store enabled models, keep/refresh the selection, and toggle Send."""
        self._models = [e for e in entries if model_entry_enabled(e)]
        self._docked_composer.set_models(self._models)
        if self._inline_edit is not None:
            self._inline_edit.composer.set_models(self._models)
        self.refresh_context_usage()
        self.refresh_connection_budget()

    def current_model_id(self) -> str | None:
        """Return the selected model id, or ``None`` when no model is set."""
        return self._docked_composer.current_model_id()

    def current_model_entry(self) -> AiModelEntry | None:
        """Return the selected model entry, if any."""
        return self._docked_composer.current_model_entry()

    def set_run_busy(self, busy: bool) -> None:
        """Toggle send vs stop while a chat run is in flight."""
        self._run_busy = busy
        self._docked_composer.set_run_busy(busy)
        if self._inline_edit is not None:
            self._inline_edit.composer.set_run_busy(busy)
        if not busy:
            self._deactivate_streaming_turn_user_footer()
            self._apply_budget_send_gate()

    def restore_composer_text(self, text: str) -> None:
        """Put unsent prompt text back into the composer input."""
        self._docked_composer.restore_text(text)

    def set_send_enabled(self, enabled: bool) -> None:
        """Enable or disable send when idle (no-op while a run is busy)."""
        self._docked_composer.set_send_enabled(enabled)

    def current_reasoning_effort(self) -> str | None:
        """Return the selected reasoning effort for the current model, if any."""
        return self._docked_composer.current_reasoning_effort()

    def current_run_context_tokens(self) -> int:
        """Return the effective run context window for the current model."""
        return self._docked_composer.current_run_context_tokens()

    def current_thinking_enabled(self) -> str | None:
        """Return ``on``/``off`` when the model supports thinking, else ``None``."""
        return self._docked_composer.current_thinking_enabled()

    def current_mode(self) -> str:
        """Return the selected agent mode (``"agent"`` / ``"ask"`` / ``"plan"``)."""
        return self._docked_composer.current_mode()

    def set_mode(self, mode: str) -> None:
        """Set agent mode without opening the picker (for tests and persistence)."""
        self._docked_composer.set_mode(mode)

    def attachments(self) -> list[str]:
        """Return the list of attached file paths."""
        return self._docked_composer.attachments()

    def set_context_usage(self, used_tokens: int, total_tokens: int) -> None:
        """Update the context ring tooltip. ``total_tokens <= 0`` shows a dash."""
        self._docked_composer.set_context_usage(used_tokens, total_tokens)

    def clear(self) -> None:
        """Remove all message bubbles and restore the empty state."""
        self._cancel_inline_edit_if_active()
        self._hide_context_popup()
        self._reset_context_usage_chrome()
        self.clear_streaming_transcript()

    def _model_button_label(self) -> str:
        """Plain-text model button label (name · context · effort) for tests."""
        return self._docked_composer.model_button_label()

    def _on_composer_model_changed(self, model_id: str) -> None:
        """Refresh context usage after model selection changes."""
        self.refresh_context_usage()
        self.refresh_connection_budget()
        self.effort_changed.emit(model_id, self.current_reasoning_effort() or "")

    def _on_composer_attachments_changed(self, paths: list) -> None:
        """Forward attachment list updates from the docked composer."""
        self._attachments = list(paths)
        self.attachments_changed.emit(self.attachments())

    def _open_model_picker(self) -> None:
        """Open or close the model picker (toggle when already visible)."""
        self._hide_context_popup()
        composer = self._active_composer()
        if not self._models:
            if composer.configured_model_count() > 0:
                self._on_manage_models()
            return
        if self._picker_popup.isVisible():
            self._picker_popup.hidePopup()
            return

        def on_pick(model_id: str) -> None:
            composer.apply_model_pick(model_id)
            if composer is self._docked_composer:
                self._on_composer_model_changed(model_id)
            else:
                self.refresh_context_usage()

        self._picker_popup.show_for(
            composer.model_button(),
            self._models,
            composer.current_model_id(),
            on_pick,
            self._on_manage_models,
            on_settings_changed=self._on_model_settings_changed,
        )

    def select_model_if_available(self, model_id: str) -> bool:
        """Select *model_id* when it is in the enabled model list."""
        return self._docked_composer.select_model_if_available(model_id)

    def _on_model_picked(self, model_id: str) -> None:
        """Backward-compatible shim for tests and callers."""
        self._docked_composer.apply_model_pick(model_id)
        self._on_composer_model_changed(model_id)

    def _on_model_settings_changed(self, model_id: str) -> None:
        """Reload persisted settings for *model_id* and refresh the composer."""
        self._docked_composer.sync_model_settings(model_id)
        if self._inline_edit is not None:
            self._inline_edit.composer.sync_model_settings(model_id)
        self.refresh_context_usage()

    def _on_manage_models(self) -> None:
        """Bubble up a request to open Settings -> AI -> Models."""
        self.manage_models_requested.emit()

    def _open_mode_picker(self) -> None:
        """Open the compact mode picker above the mode pill."""
        popup = self._mode_popup
        if popup.isVisible():
            popup.hide_popup()
            return
        self._hide_context_popup()
        composer = self._active_composer()

        def on_pick(mode: str) -> None:
            composer.set_mode(mode)

        popup.show_for(composer.mode_button(), composer.current_mode(), on_pick)

    def _on_docked_send(self) -> None:
        """Send from the docked composer."""
        if self._run_busy:
            self.stop_requested.emit()
            return
        text = self._docked_composer.plain_text()
        if not text:
            return
        self.add_message("user", text, sent_at=datetime.now(tz=UTC))
        self._docked_composer.clear_input()
        self.message_submitted.emit(text)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Coalesce transcript reflow during continuous pane resize."""
        if self.isVisible():
            self._prepare_panel_resize_coalescing()
        super().resizeEvent(event)
        if self.isVisible():
            self._reconcile_visible_rows_after_resize()
            self._finish_panel_resize_coalescing()
        if getattr(self, "_transcript_loading_visible", False):
            self._reposition_transcript_loading()
        if getattr(self, "_pending_transcript_bottom_scroll", False):
            self._maybe_flush_pending_transcript_bottom_scroll()

    def showEvent(self, event: QShowEvent) -> None:
        """Pin restored transcripts once the panel becomes visible."""
        super().showEvent(event)
        self.refresh_context_usage()
        if getattr(self, "_pending_transcript_bottom_scroll", False):
            self._maybe_flush_pending_transcript_bottom_scroll()
            self._schedule_pending_transcript_bottom_retries()

    def apply_assistant_usage_metadata(
        self,
        message: AiChatMessageDict,
        *,
        entry: AiModelEntry | None = None,
    ) -> None:
        """Apply persisted usage fields to the active or latest assistant bubble."""
        from services.ai.chat.message_usage import (
            entry_for_model_id,
            model_display_name_from_entry,
            pricing_model_id_for_assistant_message,
        )

        bubble = self._streaming_bubble or self._last_assistant_bubble()
        if bubble is None or bubble.role != "assistant":
            return
        session_model_id = getattr(self, "_transcript_session_model_id", None)
        self._refresh_pricing_messages()
        pricing_messages, msg_index = self._pricing_context_for_message(message)
        model_id = pricing_model_id_for_assistant_message(
            message,
            messages=pricing_messages if msg_index is not None else None,
            msg_index=msg_index,
            session_model_id=session_model_id,
        )
        model_label = message.get("model_label")
        if entry is None:
            entry = entry_for_model_id(model_id, extra_entries=self._models)
        if not model_label:
            model_label = model_display_name_from_entry(entry)
        bubble.set_usage_metadata(
            model_id=model_id,
            model_label=model_label,
            prompt_tokens=message.get("prompt_tokens"),
            completion_tokens=message.get("completion_tokens"),
            reasoning_tokens=message.get("reasoning_tokens"),
            entry=entry,
            extra_entries=self._models,
            message=message,
            messages=pricing_messages if msg_index is not None else None,
            msg_index=msg_index,
            session_model_id=session_model_id,
        )

    def _wire_assistant_bubble_actions(self, bubble: ChatMessageBubble) -> None:
        """Connect fork/copy affordances for one assistant transcript row."""
        bubble.fork_requested.connect(self._on_assistant_bubble_fork)
        bubble.copy_requested.connect(self._on_assistant_bubble_copy)
        bubble.subagent_card_clicked.connect(self._on_subagent_card_clicked)
        bubble.workspace_target_requested.connect(self.workspace_target_requested.emit)

    def _ensure_subagent_detail_dialog(self) -> SubagentDetailDialog:
        """Create the subagent detail window on first use."""
        if self._subagent_detail_dialog is None:
            self._subagent_detail_dialog = SubagentDetailDialog(self)
        return self._subagent_detail_dialog

    def _on_subagent_card_clicked(self, record_id: str) -> None:
        """Open the subagent detail window for one card."""
        bubble = self.sender()
        if not isinstance(bubble, ChatMessageBubble):
            return
        record = bubble.subagent_record(record_id)
        if record is None:
            return
        session_id = getattr(self, "_virtual_session_id", None) or self._context_session_id
        self._ensure_subagent_detail_dialog().open_record(record, session_id=session_id)

    def _wire_user_bubble_actions(self, bubble: ChatMessageBubble) -> None:
        """Connect fork/edit affordances for one user transcript row."""
        bubble.user_fork_requested.connect(self._on_user_bubble_fork)
        bubble.user_edit_requested.connect(self._on_user_bubble_edit)

    def _edit_sticky_prompt(self, anchor: ChatMessageBubble) -> None:
        """Begin inline edit in the sticky overlay for the mirrored user row."""
        message_id = anchor.message_id
        if message_id is None:
            return
        self.begin_inline_edit(message_id, prefer_sticky_host=True)

    def _on_user_bubble_edit(self) -> None:
        """Emit an edit request for the user bubble that triggered the action."""
        bubble = self.sender()
        if not isinstance(bubble, ChatMessageBubble):
            return
        message_id = bubble.message_id
        if message_id is None:
            return
        self.user_edit_requested.emit(message_id)

    def _fork_sticky_prompt(self, anchor: ChatMessageBubble) -> None:
        """Fork from the transcript user row mirrored by the sticky overlay."""
        message_id = anchor.message_id
        if message_id is None:
            return
        self.user_fork_requested.emit(message_id)

    def _on_assistant_bubble_fork(self) -> None:
        """Emit a fork request for the assistant bubble that triggered the action."""
        bubble = self.sender()
        if not isinstance(bubble, ChatMessageBubble):
            return
        message_id = bubble.message_id
        if message_id is None:
            return
        self.assistant_fork_requested.emit(message_id)

    def _on_user_bubble_fork(self) -> None:
        """Emit a fork request for the user bubble that triggered the action."""
        bubble = self.sender()
        if not isinstance(bubble, ChatMessageBubble):
            return
        message_id = bubble.message_id
        if message_id is None:
            return
        self.user_fork_requested.emit(message_id)

    def _on_assistant_bubble_copy(self) -> None:
        """Copy the assistant answer markdown for the triggering bubble."""
        from PySide6.QtGui import QGuiApplication

        bubble = self.sender()
        if not isinstance(bubble, ChatMessageBubble):
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(bubble.full_markdown_for_copy())
