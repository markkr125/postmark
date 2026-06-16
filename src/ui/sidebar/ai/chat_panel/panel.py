"""AI assistant chat panel — transcript, composer, and model/mode controls."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot, QSize
from PySide6.QtGui import QHideEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services.ai.ai_config import AiConfig, AiModelEntry, model_entry_enabled
from services.ai.chat.session_service import AiChatMessageDict
from services.ai.provider_catalog import effective_run_context_tokens, format_run_context_tokens
from services.ai.reasoning_effort import clamp_effort, default_effort_for, format_reasoning_effort
from ui.sidebar.ai.agent_mode_popup import AgentModeButton, AiAgentModePopup
from ui.sidebar.ai.chat_panel.composer import ModelPickerButton, _ComposerInput
from ui.sidebar.ai.chat_panel.context_ring_button import ContextUsageRingButton
from ui.sidebar.ai.chat_panel.context_usage_panel import _ChatPanelContextUsageMixin
from ui.sidebar.ai.chat_panel_streaming import _ChatPanelStreamingMixin
from ui.sidebar.ai.chat_transcript_loading_row import ChatTranscriptLoadingOverlay
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.model_picker_edit import reasoning_levels_for_entry, thinking_enabled_for_entry
from ui.sidebar.ai.model_picker_popup import AiModelPickerPopup
from ui.styling.icons import CHAT_STOP_ICON_SIZE, chat_stop_icon, phi

_EMPTY_STATE_TEXT = "Ask anything about your API requests."
_NO_MODELS_TEXT = "No models configured"
_CHAT_SCROLL_PADDING_LEFT = 8
_CHAT_SCROLL_PADDING_RIGHT = 8
_CHAT_COMPOSER_MARGIN_H = 8


class AiChatPanel(_ChatPanelStreamingMixin, _ChatPanelContextUsageMixin, QWidget):  # type: ignore[misc]
    """Right-sidebar AI chat skeleton (transcript + composer)."""

    message_submitted = Signal(str)
    stop_requested = Signal()
    assistant_fork_requested = Signal(int)
    user_fork_requested = Signal(int)
    mode_changed = Signal(str)
    attachments_changed = Signal(list)
    manage_models_requested = Signal()
    effort_changed = Signal(str, str)
    context_requested = Signal()
    transcript_load_finished = Signal()
    _assistant_chunk_delivery_requested = Signal(str, str)
    _activity_status_delivery_requested = Signal(str)
    _context_usage_metrics_delivery_requested = Signal(object)
    _context_usage_refresh_delivery_requested = Signal()
    _context_usage_schedule_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the transcript scroll area and the composer."""
        super().__init__(parent)
        self.setObjectName("aiChatPanel")
        self._attachments: list[str] = []
        self._models: list[AiModelEntry] = []
        self._current_model_id: str | None = None
        self._reasoning_effort: str | None = None
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
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self._messages = QWidget()
        self._messages_layout = QVBoxLayout(self._messages)
        self._messages_layout.setContentsMargins(
            _CHAT_SCROLL_PADDING_LEFT,
            0,
            _CHAT_SCROLL_PADDING_RIGHT,
            0,
        )
        self._messages_layout.setSpacing(8)
        self._messages_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
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

        # --- Composer --------------------------------------------------
        composer = QWidget()
        composer.setObjectName("aiChatComposer")
        composer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(_CHAT_COMPOSER_MARGIN_H, 8, _CHAT_COMPOSER_MARGIN_H, 8)
        composer_layout.setSpacing(6)

        # Attachment chips (row hidden until a file is added)
        self._attachments_row = QWidget()
        self._attachments_row.setObjectName("aiChatAttachments")
        self._attachments_layout = QHBoxLayout(self._attachments_row)
        self._attachments_layout.setContentsMargins(0, 0, 0, 0)
        self._attachments_layout.setSpacing(4)
        self._attachments_layout.addStretch(1)
        self._attachments_row.hide()
        composer_layout.addWidget(self._attachments_row)

        self._input = _ComposerInput()
        self._input.setObjectName("aiChatInput")
        self._input.setPlaceholderText("Message the assistant...  (Enter to send)")
        self._input.submit_requested.connect(self._on_send)
        composer_layout.addWidget(self._input)

        # Control strip, left to right: mode, model, context, upload, Send.
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)

        self._mode_btn = AgentModeButton()
        self._mode_btn.clicked.connect(self._open_mode_picker)
        controls.addWidget(self._mode_btn)

        self._model_btn = ModelPickerButton()
        self._model_btn.setToolTip("Select model")
        self._model_btn.clicked.connect(self._open_model_picker)
        controls.addWidget(self._model_btn, 0)
        controls.addStretch(1)

        self._context_ring = ContextUsageRingButton()
        controls.addWidget(self._context_ring)

        self._upload_btn = QPushButton()
        self._upload_btn.setObjectName("iconButton")
        self._upload_btn.setIcon(phi("paperclip", size=16))
        self._upload_btn.setFixedSize(28, 28)
        self._upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._upload_btn.setToolTip("Attach file")
        self._upload_btn.clicked.connect(self._on_attach)
        controls.addWidget(self._upload_btn)

        self._send_btn = QPushButton()
        self._send_btn.setObjectName("smallPrimaryButton")
        self._send_btn.setIcon(phi("paper-plane-right", color="#ffffff"))
        self._send_btn.setFixedSize(28, 28)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setToolTip("Send (Enter)")
        self._send_btn.clicked.connect(self._on_send)
        controls.addWidget(self._send_btn)

        composer_layout.addLayout(controls)
        root.addWidget(composer)

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

        self.set_models([])
        self._reset_context_usage_chrome()

    def hideEvent(self, event: QHideEvent) -> None:
        """Dismiss context popover when the panel is hidden."""
        self._hide_context_popup()
        self._shutdown_context_usage_worker()
        super().hideEvent(event)

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
        ids = {e["id"] for e in self._models}
        self._current_model_id = self._pick_model_id(ids)
        self._sync_model_state(self._current_model_id)
        has_models = bool(self._models)
        self._model_btn.setEnabled(has_models)
        self._send_btn.setEnabled(has_models)
        self._refresh_model_button()
        entry = self._entry_by_id(self._current_model_id) if self._current_model_id else None
        total = effective_run_context_tokens(entry) if entry is not None else 0
        self._context_ring.set_usage(0, total)
        self.refresh_context_usage()

    def _entry_by_id(self, model_id: str) -> AiModelEntry | None:
        """Return the model entry with *model_id*, if present."""
        for entry in self._models:
            if entry["id"] == model_id:
                return entry
        return None

    def _pick_model_id(self, ids: set[str]) -> str | None:
        """Keep the in-memory, persisted, or first enabled model selection."""
        if self._current_model_id in ids:
            return self._current_model_id
        stored = AiConfig.get_chat_model_id()
        if stored in ids:
            return stored
        return self._models[0]["id"] if self._models else None

    def _effective_effort(self, entry: AiModelEntry) -> str | None:
        """Return persisted leveled reasoning effort, if the model supports it."""
        efforts = reasoning_levels_for_entry(entry)
        if not efforts:
            return None
        stored = entry.get("reasoning_effort")
        if isinstance(stored, str) and stored.strip():
            return clamp_effort(
                stored.strip().lower(), efforts, str(entry.get("reasoning_default", ""))
            )
        default = str(entry.get("reasoning_default", ""))
        if default:
            return clamp_effort(default, efforts, default)
        return default_effort_for(efforts)

    def _sync_model_state(self, model_id: str | None) -> None:
        """Refresh derived state for *model_id* from the in-memory model list."""
        self._reasoning_effort = None
        if not model_id:
            return
        entry = self._entry_by_id(model_id)
        if entry is None:
            return
        self._reasoning_effort = self._effective_effort(entry)

    def current_model_id(self) -> str | None:
        """Return the selected model id, or ``None`` when no model is set."""
        return self._current_model_id

    def current_model_entry(self) -> AiModelEntry | None:
        """Return the selected model entry, if any."""
        if self._current_model_id is None:
            return None
        return self._entry_by_id(self._current_model_id)

    def set_run_busy(self, busy: bool) -> None:
        """Toggle send vs stop while a chat run is in flight."""
        self._run_busy = busy
        if busy:
            self._send_btn.setIconSize(QSize(CHAT_STOP_ICON_SIZE, CHAT_STOP_ICON_SIZE))
            self._send_btn.setIcon(chat_stop_icon())
            self._send_btn.setToolTip("Stop")
            self._send_btn.setEnabled(True)
        else:
            self._deactivate_streaming_turn_user_footer()
            self._send_btn.setIcon(phi("paper-plane-right", color="#ffffff"))
            self._send_btn.setToolTip("Send (Enter)")
            self._send_btn.setEnabled(bool(self._models))

    def restore_composer_text(self, text: str) -> None:
        """Put unsent prompt text back into the composer input."""
        self._input.setPlainText(text)
        self._input.setFocus()

    def set_send_enabled(self, enabled: bool) -> None:
        """Enable or disable send when idle (no-op while a run is busy)."""
        if self._run_busy:
            return
        self._send_btn.setEnabled(enabled and bool(self._models))

    def current_reasoning_effort(self) -> str | None:
        """Return the selected reasoning effort for the current model, if any."""
        return self._reasoning_effort

    def current_run_context_tokens(self) -> int:
        """Return the effective run context window for the current model."""
        entry = self._entry_by_id(self._current_model_id) if self._current_model_id else None
        return effective_run_context_tokens(entry) if entry is not None else 0

    def current_thinking_enabled(self) -> str | None:
        """Return ``on``/``off`` when the model supports thinking, else ``None``."""
        entry = self._entry_by_id(self._current_model_id) if self._current_model_id else None
        if entry is None or not entry.get("thinking"):
            return None
        return thinking_enabled_for_entry(entry)

    def current_mode(self) -> str:
        """Return the selected agent mode (``"agent"`` / ``"ask"`` / ``"plan"``)."""
        return self._mode_btn.mode()

    def set_mode(self, mode: str) -> None:
        """Set agent mode without opening the picker (for tests and persistence)."""
        if self.current_mode() == mode:
            return
        self._mode_btn.set_mode(mode)
        self.mode_changed.emit(mode)

    def attachments(self) -> list[str]:
        """Return the list of attached file paths."""
        return list(self._attachments)

    def set_context_usage(self, used_tokens: int, total_tokens: int) -> None:
        """Update the context ring tooltip. ``total_tokens <= 0`` shows a dash."""
        self._context_ring.set_usage(used_tokens, total_tokens)

    def clear(self) -> None:
        """Remove all message bubbles and restore the empty state."""
        self._hide_context_popup()
        self._reset_context_usage_chrome()
        self.clear_streaming_transcript()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _model_button_parts(self) -> tuple[str, str | None, str | None] | None:
        """Return ``(name, context tag, effort tag)`` or ``None`` for the empty state."""
        if not self._models or self._current_model_id is None:
            return None
        entry = self._entry_by_id(self._current_model_id)
        if entry is None:
            return None
        name = entry.get("label") or entry["model"]
        ctx_val: str | None = None
        ctx_tokens = effective_run_context_tokens(entry)
        if ctx_tokens > 0:
            ctx_val = format_run_context_tokens(ctx_tokens)
        effort_val: str | None = None
        effort = self._reasoning_effort or self._effective_effort(entry)
        if effort:
            effort_val = format_reasoning_effort(effort)
        return (name, ctx_val, effort_val)

    def _model_button_label(self) -> str:
        """Plain-text model button label (name · context · effort) for tests."""
        parts = self._model_button_parts()
        if parts is None:
            return _NO_MODELS_TEXT
        bits = [parts[0]]
        if parts[1]:
            bits.append(parts[1])
        if parts[2]:
            bits.append(parts[2])
        return "  ·  ".join(bits)

    def _refresh_model_button(self) -> None:
        """Update the model pill from the current selection."""
        self._model_btn.set_parts(self._model_button_parts())

    def _open_model_picker(self) -> None:
        """Open or close the model picker (toggle when already visible)."""
        self._hide_context_popup()
        if not self._models:
            return
        if self._picker_popup.isVisible():
            self._picker_popup.hidePopup()
            return
        self._picker_popup.show_for(
            self._model_btn,
            self._models,
            self._current_model_id,
            self._on_model_picked,
            self._on_manage_models,
            on_settings_changed=self._on_model_settings_changed,
        )

    def select_model_if_available(self, model_id: str) -> bool:
        """Select *model_id* when it is in the enabled model list."""
        if model_id not in {entry["id"] for entry in self._models}:
            return False
        self._on_model_picked(model_id)
        return True

    def _on_model_picked(self, model_id: str) -> None:
        """Store the picked model id and refresh the button label."""
        self._current_model_id = model_id
        AiConfig.set_chat_model_id(model_id)
        self._sync_model_state(model_id)
        self._refresh_model_button()
        entry = self._entry_by_id(model_id)
        if entry is not None:
            self._context_ring.set_usage(0, effective_run_context_tokens(entry))
            self.refresh_context_usage()

    def _on_model_settings_changed(self, model_id: str) -> None:
        """Reload persisted settings for *model_id* and refresh the composer."""
        persisted = {e["id"]: e for e in AiConfig.get_models()}
        if model_id in persisted:
            for i, row in enumerate(self._models):
                if row["id"] == model_id:
                    self._models[i] = persisted[model_id]
                    break
        if self._current_model_id == model_id:
            self._sync_model_state(model_id)
            self._refresh_model_button()
            entry = self._entry_by_id(model_id)
            if entry is not None:
                self._context_ring.set_usage(0, effective_run_context_tokens(entry))
                self.refresh_context_usage()
        self.effort_changed.emit(model_id, self._reasoning_effort or "")

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

        def on_pick(mode: str) -> None:
            self._mode_btn.set_mode(mode)
            self.mode_changed.emit(mode)

        popup.show_for(self._mode_btn, self._mode_btn.mode(), on_pick)

    def _on_attach(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach file")
        added = False
        for path in paths:
            if path and path not in self._attachments:
                self._attachments.append(path)
                self._add_attachment_chip(path)
                added = True
        if added:
            self._attachments_row.setVisible(bool(self._attachments))
            self.attachments_changed.emit(self.attachments())

    def _add_attachment_chip(self, path: str) -> None:
        chip = QPushButton(f"{Path(path).name}  x")
        chip.setObjectName("aiChatAttachmentChip")
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setToolTip(f"Remove {path}")
        chip.clicked.connect(lambda: self._remove_attachment(path, chip))
        # Insert before the trailing stretch so chips pack left.
        self._attachments_layout.insertWidget(self._attachments_layout.count() - 1, chip)

    def _remove_attachment(self, path: str, chip: QPushButton) -> None:
        if path in self._attachments:
            self._attachments.remove(path)
        chip.setParent(None)
        chip.deleteLater()
        self._attachments_row.setVisible(bool(self._attachments))
        self.attachments_changed.emit(self.attachments())

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
            effective_assistant_model_id,
            entry_for_model_id,
            model_display_name_from_entry,
        )

        bubble = self._streaming_bubble or self._last_assistant_bubble()
        if bubble is None or bubble.role != "assistant":
            return
        session_model_id = getattr(self, "_transcript_session_model_id", None)
        model_id = effective_assistant_model_id(message.get("model_id"), session_model_id)
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
        )

    def _wire_assistant_bubble_actions(self, bubble: ChatMessageBubble) -> None:
        """Connect fork/copy affordances for one assistant transcript row."""
        bubble.fork_requested.connect(self._on_assistant_bubble_fork)
        bubble.copy_requested.connect(self._on_assistant_bubble_copy)

    def _wire_user_bubble_actions(self, bubble: ChatMessageBubble) -> None:
        """Connect fork affordance for one user transcript row."""
        bubble.user_fork_requested.connect(self._on_user_bubble_fork)

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

    def _on_send(self) -> None:
        """Send a message, or request stop while a run is in flight."""
        if self._run_busy:
            self.stop_requested.emit()
            return
        if not self._send_btn.isEnabled():
            return
        text = self._input.toPlainText().strip()
        if not text:
            return
        self.add_message("user", text, sent_at=datetime.now(tz=UTC))
        self._input.clear()
        # TODO: build LLM via AiLlmService.build_llm(entry) using current_model_id(),
        # current_mode(), current_run_context_tokens(), current_thinking_enabled(),
        # current_reasoning_effort(), attachments();
        # stream the reply into add_message("assistant", ...).
        self.message_submitted.emit(text)
