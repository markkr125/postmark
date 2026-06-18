"""Incremental session transcript loading for :class:`AiChatPanel`."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication

from services.ai.chat.session_service import AiChatMessageDict, AiChatTranscriptPageDict
from ui.sidebar.ai.message_bubble import ChatMessageBubble, ChatRole

_TRANSCRIPT_LOAD_TICK_MS = 0
_TRANSCRIPT_LOAD_MESSAGES_PER_TICK = 4
_TRANSCRIPT_LOADING_MESSAGE = "Loading conversation…"


def parse_message_sent_at(raw: object) -> datetime | None:
    """Parse an ISO ``created_at`` value for transcript user timestamps."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


class _ChatPanelTranscriptLoadMixin:
    """Chunked transcript rebuild and lazy-markdown session switches."""

    _messages: Any = None
    _messages_layout: Any = None
    _empty_label: Any = None
    _transcript_loading: Any = None
    _transcript_loading_visible: bool = False
    _scroll: Any = None
    _defer_transcript_hooks: bool = False
    _transcript_load_lazy_markdown: bool = False
    _transcript_load_generation: int = 0
    _transcript_load_active_generation: int = 0
    _transcript_load_messages: list[AiChatMessageDict]
    _transcript_load_index: int = 0
    _transcript_load_timer: QTimer
    _pending_transcript_bottom_scroll: bool = False
    _post_load_bottom_settle_active: bool = False

    def _init_transcript_load_state(self) -> None:
        """Create the incremental load timer (call from panel streaming init)."""
        self._transcript_load_timer = QTimer(self)  # type: ignore[arg-type]
        self._transcript_load_timer.setSingleShot(True)
        self._transcript_load_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._transcript_load_timer.timeout.connect(self._transcript_load_tick)
        self._transcript_load_messages = []
        self._transcript_load_index = 0
        self._transcript_load_generation = 0
        self._transcript_load_active_generation = 0
        self._pending_transcript_bottom_scroll = False
        self._post_load_bottom_settle_active = False

    def _transcript_viewport_can_pin_bottom(self) -> bool:
        """Return whether the scroll viewport is large enough to pin the bottom."""
        viewport_h = self._scroll.viewport().height()
        bar = self._scroll.verticalScrollBar()
        return bool(viewport_h > 0 and bar.maximum() > 0)

    def _transcript_ready_for_bottom_pin(self) -> bool:
        """Return whether the panel is visible with a usable transcript viewport."""
        return bool(self.isVisible()) and self._scroll.viewport().height() > 0  # type: ignore[attr-defined]

    def _finish_transcript_bottom_scroll(self) -> None:
        """Pin the transcript bottom when the viewport is ready, else defer."""
        if not self._transcript_ready_for_bottom_pin():
            self._pending_transcript_bottom_scroll = True
            self._schedule_pending_transcript_bottom_retries()
            return
        for _ in range(3):
            cast(Any, self)._scroll_to_bottom_settled()
            if cast(Any, self)._is_pinned_to_bottom():
                if not self._post_load_bottom_settle_active:
                    self._pending_transcript_bottom_scroll = False
                return
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        self._pending_transcript_bottom_scroll = True
        self._schedule_pending_transcript_bottom_retries()

    def _end_post_load_bottom_settle(self) -> None:
        """Finish the post-load bottom settle window."""
        self._post_load_bottom_settle_active = False
        if cast(Any, self)._is_pinned_to_bottom():
            self._pending_transcript_bottom_scroll = False
            return
        self._finish_transcript_bottom_scroll()

    def _maybe_flush_pending_transcript_bottom_scroll(self) -> None:
        """Scroll to the bottom once the transcript viewport has a real size."""
        if not self._pending_transcript_bottom_scroll:
            return
        if not self._transcript_ready_for_bottom_pin():
            return
        if not cast(Any, self)._scroll_lock_enabled:
            self._pending_transcript_bottom_scroll = False
            return
        self._finish_transcript_bottom_scroll()

    def _schedule_pending_transcript_bottom_retries(self) -> None:
        """Retry bottom pinning while the flyout or viewport is still settling."""
        if not self._pending_transcript_bottom_scroll:
            return
        for delay_ms in (0, 50, 150, 400):
            QTimer.singleShot(delay_ms, self._maybe_flush_pending_transcript_bottom_scroll)

    def _schedule_transcript_bottom_settle(self) -> None:
        """Keep pinning the bottom while post-load layout and lazy markdown settle."""
        self._post_load_bottom_settle_active = True
        self._pending_transcript_bottom_scroll = True
        self._schedule_pending_transcript_bottom_retries()
        for delay_ms in (80, 200, 500, 1200):
            QTimer.singleShot(delay_ms, self._maybe_flush_pending_transcript_bottom_scroll)
        QTimer.singleShot(1500, self._end_post_load_bottom_settle)

    def _show_transcript_loading(self) -> None:
        """Show the panel-level loading overlay while a session transcript loads."""
        self._empty_label.hide()
        self._transcript_loading_visible = True
        self._transcript_loading.show_loading(_TRANSCRIPT_LOADING_MESSAGE)
        self._reposition_transcript_loading()

    def _hide_transcript_loading(self) -> None:
        """Hide the panel-level loading overlay."""
        if not self._transcript_loading_visible:
            return
        self._transcript_loading_visible = False
        self._transcript_loading.hide_loading()

    def _reposition_transcript_loading(self) -> None:
        """Keep the loading overlay centred above the composer."""
        if not self._transcript_loading_visible:
            return
        self._transcript_loading.reposition(self._scroll.viewport())

    def cancel_transcript_load(self) -> None:
        """Stop an in-flight incremental transcript build."""
        cancel_sticky = getattr(self, "_cancel_sticky_sync", None)
        if callable(cancel_sticky):
            cancel_sticky()
        self._transcript_load_generation += 1
        if self._transcript_load_timer.isActive():
            self._transcript_load_timer.stop()
        self._transcript_load_messages = []
        self._transcript_load_index = 0
        self._defer_transcript_hooks = False
        self._transcript_load_lazy_markdown = False
        self._pending_transcript_bottom_scroll = False
        self._post_load_bottom_settle_active = False
        self._hide_transcript_loading()

    def is_transcript_load_active(self) -> bool:
        """Return whether an incremental transcript build is in progress."""
        return (
            self._transcript_loading_visible
            or self._transcript_load_timer.isActive()
            or (self._transcript_load_index < len(self._transcript_load_messages))
        )

    def prepare_transcript_load(self, *, lazy_markdown: bool = True) -> None:
        """Clear the transcript and show the loading row for a session switch."""
        self.cancel_transcript_load()
        self._clear_transcript_widgets()  # type: ignore[attr-defined]
        self._transcript_load_lazy_markdown = lazy_markdown
        self._show_transcript_loading()

    def _message_from_dict(
        self,
        msg: AiChatMessageDict,
        *,
        force_render: bool = False,
    ) -> ChatMessageBubble:
        """Build one transcript row from a persisted message dict."""
        role: ChatRole = "user" if msg["role"] == "user" else "assistant"
        thinking = str(msg.get("thinking") or "")
        duration = msg.get("thinking_duration_seconds")
        duration_seconds = int(duration) if isinstance(duration, int) and duration > 0 else None
        sent_at = parse_message_sent_at(msg.get("created_at"))
        lazy = self._transcript_load_lazy_markdown and role == "assistant" and not force_render
        bubble = self.add_message(  # type: ignore[attr-defined,no-any-return]
            role,
            msg["content"],
            thinking=thinking,
            thinking_duration_seconds=duration_seconds,
            sent_at=sent_at if role == "user" else None,
            lazy_markdown=lazy,
            message_id=msg["id"],
        )
        if role == "assistant":
            from services.ai.chat.message_usage import (
                effective_assistant_model_id,
                entry_for_model_id,
                model_display_name_from_entry,
            )

            session_model_id = getattr(self, "_transcript_session_model_id", None)
            model_id = effective_assistant_model_id(msg.get("model_id"), session_model_id)
            entry = entry_for_model_id(model_id, extra_entries=self._models)  # type: ignore[attr-defined]
            model_label = msg.get("model_label") or model_display_name_from_entry(entry)
            bubble.set_usage_metadata(
                model_id=model_id,
                model_label=model_label,
                prompt_tokens=msg.get("prompt_tokens"),
                completion_tokens=msg.get("completion_tokens"),
                reasoning_tokens=msg.get("reasoning_tokens"),
                entry=entry,
                extra_entries=self._models,  # type: ignore[attr-defined]
            )
        return cast(ChatMessageBubble, bubble)

    def load_transcript_async(
        self,
        messages: list[AiChatMessageDict],
        *,
        generation: int,
        lazy_markdown: bool = True,
        page: AiChatTranscriptPageDict | None = None,
    ) -> None:
        """Replace the transcript incrementally without blocking the GUI thread."""
        self._transcript_load_generation = generation
        self._transcript_load_active_generation = generation
        self._transcript_load_messages = list(messages)
        self._transcript_load_index = 0
        self._transcript_load_lazy_markdown = lazy_markdown
        self._defer_transcript_hooks = True
        if page is not None:
            self._apply_virtual_page_state(page)  # type: ignore[attr-defined]
        cast(Any, self)._arm_scroll_lock()
        if not messages:
            self._hide_transcript_loading()
            self._empty_label.show()
            self._defer_transcript_hooks = False
            self.transcript_load_finished.emit()  # type: ignore[attr-defined]
            return
        self._transcript_load_timer.start(_TRANSCRIPT_LOAD_TICK_MS)

    def _transcript_load_tick(self) -> None:
        """Append the next chunk of persisted messages."""
        if self._transcript_load_active_generation != self._transcript_load_generation:
            return
        if self._transcript_load_index >= len(self._transcript_load_messages):
            return
        self._messages.setUpdatesEnabled(False)
        try:
            end = min(
                self._transcript_load_index + _TRANSCRIPT_LOAD_MESSAGES_PER_TICK,
                len(self._transcript_load_messages),
            )
            while self._transcript_load_index < end:
                self._message_from_dict(self._transcript_load_messages[self._transcript_load_index])
                self._transcript_load_index += 1
        finally:
            self._messages.setUpdatesEnabled(True)
        if self._transcript_ready_for_bottom_pin():
            cast(Any, self)._pin_transcript_to_bottom()
        self._reposition_transcript_loading()
        if self._transcript_load_index >= len(self._transcript_load_messages):
            self._complete_transcript_load()
            return
        self._transcript_load_timer.start(_TRANSCRIPT_LOAD_TICK_MS)

    def _complete_transcript_load(self) -> None:
        """Finalize hooks and layout after the last transcript chunk."""
        self._defer_transcript_hooks = False
        self._transcript_load_messages = []
        self._transcript_load_index = 0
        self._turn_scroll_anchor = cast(Any, self)._find_last_turn_user_bubble()
        generation = self._transcript_load_generation
        QTimer.singleShot(0, lambda g=generation: self._finish_transcript_load_and_signal(g))

    def flush_transcript_load(self) -> None:
        """Drain incremental transcript load synchronously (for tests)."""
        app = QApplication.instance()
        for _ in range(5000):
            if self._transcript_load_timer.isActive():
                self._transcript_load_timer.stop()
            if self._transcript_load_index < len(self._transcript_load_messages):
                self._transcript_load_tick()
                continue
            if app is not None:
                app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
            if not self.is_transcript_load_active():
                return
        msg = "flush_transcript_load exceeded iteration limit"
        raise RuntimeError(msg)

    def _finish_transcript_load_and_signal(self, generation: int) -> None:
        """Run post-load layout and notify listeners."""
        if generation != self._transcript_load_generation:
            return
        if self._transcript_load_active_generation != generation:
            return
        self._finish_load_transcript_layout()  # type: ignore[attr-defined]
        self._hide_transcript_loading()
        cast(Any, self)._schedule_virtual_transcript_pass()
        self._schedule_transcript_bottom_settle()
        self.transcript_load_finished.emit()  # type: ignore[attr-defined]
        refresh = getattr(self, "refresh_context_usage", None)
        if callable(refresh):
            refresh()

    def load_transcript(self, messages: list[AiChatMessageDict]) -> None:
        """Replace the transcript with persisted *messages* (async chunked build)."""
        self._transcript_load_generation += 1
        generation = self._transcript_load_generation
        self.prepare_transcript_load(lazy_markdown=False)
        self.load_transcript_async(messages, generation=generation, lazy_markdown=False)
