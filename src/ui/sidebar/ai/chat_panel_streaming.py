"""Streaming transcript orchestration for :class:`AiChatPanel`.

Mixin methods use attributes defined on :class:`ui.sidebar.ai.chat_panel.panel.AiChatPanel`.
"""

from __future__ import annotations

import contextlib
import re
from datetime import datetime
from typing import Any

from PySide6.QtCore import QEventLoop, Qt, QTimer, Slot
from PySide6.QtWidgets import QApplication, QWidget

from ui.sidebar.ai.chat_panel.scroll import _ChatPanelScrollMixin
from ui.sidebar.ai.transcript.window import _ChatPanelTranscriptWindowMixin
from ui.sidebar.ai.message_bubble import ChatMessageBubble, ChatRole

_ACTIVITY_DEFAULT_MESSAGE = "Thinking…"
_ACTIVITY_LONG_WAIT_MESSAGE = "Taking longer than expected…"
_ACTIVITY_LONG_WAIT_MS = 15_000
_CHUNK_COALESCE_MS = 50


# Reject enum-like SDK noise (e.g. AgentState.RUNNING, <Status.foo: 1>).
_STATUS_NOISE_RE = re.compile(
    r"^(?:<.+>|.+\.|AgentState\.|ConversationState\.|None)$",
    re.IGNORECASE,
)

_STATUS_LABEL_MAP: dict[str, str] = {
    "running": "Working…",
    "thinking": "Thinking…",
    "planning": "Planning…",
    "waiting": "Waiting…",
    "loading": "Loading…",
}


def format_activity_status(raw: str) -> str | None:
    """Return a human-readable activity label for SDK status text, or ``None``."""
    text = raw.strip()
    if not text or text.lower() == "none":
        return None
    if _STATUS_NOISE_RE.match(text):
        return None
    if "." in text and text[0].isupper() and " " not in text:
        return None
    mapped = _STATUS_LABEL_MAP.get(text.lower())
    if mapped is not None:
        return mapped
    if len(text) > 80:
        return None
    if text.endswith("..."):
        return text
    if text.endswith("…"):
        return text
    return f"{text}…"


class _ChatPanelStreamingMixin(_ChatPanelTranscriptWindowMixin, _ChatPanelScrollMixin):  # type: ignore[misc]
    """Activity row + timer orchestration for assistant streaming."""

    _streaming_bubble: ChatMessageBubble | None = None
    _streaming_turn_user_bubble: ChatMessageBubble | None = None
    _stream_generation: int = 0
    _open_stream_generation: int = 0
    _messages_layout: Any = None
    _empty_label: Any = None
    _pending_thinking_delta: str = ""
    _pending_content_delta: str = ""
    _stream_bubble_height_hook: ChatMessageBubble | None = None
    _transcript_layout_hooks: list[ChatMessageBubble]
    _stream_layout_flush_in_progress: bool = False

    def _init_chat_streaming_state(self) -> None:
        """Create streaming timers (call from panel ``__init__``)."""
        self._init_transcript_load_state()
        self._init_transcript_window_state()
        self._activity_timer = QTimer(self)  # type: ignore[arg-type]
        self._activity_timer.setSingleShot(True)
        self._activity_timer.timeout.connect(self._on_activity_long_wait)

        self._chunk_coalesce_timer = QTimer(self)  # type: ignore[arg-type]
        self._chunk_coalesce_timer.setSingleShot(True)
        self._chunk_coalesce_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._chunk_coalesce_timer.setInterval(_CHUNK_COALESCE_MS)
        self._chunk_coalesce_timer.timeout.connect(self._flush_pending_chunks)

        self._pending_thinking_delta = ""
        self._pending_content_delta = ""
        self._streaming_turn_user_bubble = None

    def _deactivate_streaming_turn_user_footer(self) -> None:
        """Restore the active turn user bubble footer to message actions."""
        bubble = self._streaming_turn_user_bubble
        if bubble is None:
            return
        bubble.set_user_footer_mode("actions")
        self._streaming_turn_user_bubble = None

    def _activate_streaming_turn_user_footer(self, bubble: ChatMessageBubble | None) -> None:
        """Show turn-scoped stop on the user bubble that started the current run."""
        self._deactivate_streaming_turn_user_footer()
        if bubble is None or bubble.role != "user":
            return
        self._streaming_turn_user_bubble = bubble
        bubble.set_user_footer_mode("stop")

    def _reset_pending_chunks(self) -> None:
        """Clear coalesced chunk buffers and disarm the flush timer."""
        self._pending_thinking_delta = ""
        self._pending_content_delta = ""
        if self._chunk_coalesce_timer.isActive():
            self._chunk_coalesce_timer.stop()

    def _start_activity_timer(self) -> None:
        """Arm the long-wait escalation timer."""
        self._activity_timer.start(_ACTIVITY_LONG_WAIT_MS)

    def _cancel_activity_timer(self) -> None:
        """Disarm the long-wait escalation timer."""
        if self._activity_timer.isActive():
            self._activity_timer.stop()

    def _hide_stream_activity(self) -> None:
        """Hide activity on the active streaming bubble, if any."""
        bubble = self._resolve_streaming_bubble()
        if bubble is not None:
            bubble.hide_activity()

    def _find_last_user_bubble(self) -> ChatMessageBubble | None:
        """Return the newest user bubble in the transcript, if any."""
        for index in range(self._messages_layout.count() - 1, -1, -1):
            item = self._messages_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, ChatMessageBubble) and widget.role == "user":
                return widget
        return None

    def _find_last_turn_user_bubble(self) -> ChatMessageBubble | None:
        """Return the user bubble paired with the newest assistant reply."""
        last_assistant = self._last_assistant_bubble()
        if last_assistant is None:
            return self._find_last_user_bubble()
        for index in range(self._messages_layout.count()):
            item = self._messages_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is last_assistant:
                for prev in range(index - 1, -1, -1):
                    prev_item = self._messages_layout.itemAt(prev)
                    prev_widget = prev_item.widget() if prev_item is not None else None
                    if isinstance(prev_widget, ChatMessageBubble) and prev_widget.role == "user":
                        return prev_widget
                return None
        return self._find_last_user_bubble()

    def _detach_transcript_layout_hooks(self) -> None:
        """Disconnect sticky sync from all transcript assistant rows."""
        for hook in self._transcript_layout_hooks:
            with contextlib.suppress(TypeError, RuntimeError):
                hook.layout_height_changed.disconnect(self._on_transcript_bubble_layout_changed)
        self._transcript_layout_hooks = []

    def _ensure_assistant_layout_hook(self, bubble: ChatMessageBubble) -> None:
        """Connect one assistant row for transcript relayout and scroll compensation."""
        if bubble in self._transcript_layout_hooks:
            return
        bubble.layout_height_changed.connect(self._on_transcript_bubble_layout_changed)
        self._transcript_layout_hooks.append(bubble)

    def _attach_transcript_layout_hooks(self) -> None:
        """Follow markdown height changes on every assistant row in the transcript."""
        self._detach_transcript_layout_hooks()
        for index in range(self._messages_layout.count()):
            item = self._messages_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if not isinstance(widget, ChatMessageBubble) or widget.role != "assistant":
                continue
            self._ensure_assistant_layout_hook(widget)

    def _on_transcript_bubble_layout_changed(self) -> None:
        """Refresh sticky overlay after any transcript row layout settles."""
        if self._stream_layout_flush_in_progress:
            return
        if getattr(self, "_resize_active", False):
            return
        self._invalidate_sticky_extents()  # type: ignore[attr-defined]
        self._schedule_sticky_sync()  # type: ignore[attr-defined]

    def _finish_load_transcript_layout(self) -> None:
        """Reconcile streaming anchor and sticky overlay after transcript widgets settle."""
        self._messages.updateGeometry()
        self._scroll.updateGeometry()  # type: ignore[attr-defined]
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        self._turn_scroll_anchor = self._find_last_turn_user_bubble()
        self._rebuild_sticky_turn_pairs()  # type: ignore[attr-defined]
        self._rebuild_sticky_turn_extents()  # type: ignore[attr-defined]
        self._attach_transcript_layout_hooks()
        self._finish_transcript_bottom_scroll()  # type: ignore[attr-defined]

    def _attach_streaming_bubble_height_hook(self, bubble: ChatMessageBubble) -> None:
        """Connect one layout-height hook for the active streaming assistant row."""
        if self._stream_bubble_height_hook is bubble:
            return
        self._stream_bubble_height_hook = bubble
        bubble.layout_height_changed.connect(self._on_streaming_bubble_layout_changed)

    def _on_streaming_bubble_layout_changed(self) -> None:
        """Follow after deferred markdown/bubble height settles."""
        if self._stream_layout_flush_in_progress:
            return
        if self._open_stream_generation > 0 and self._scroll_lock_enabled:  # type: ignore[attr-defined]
            self._apply_streaming_viewport_spacer()  # type: ignore[attr-defined]
            self._messages.updateGeometry()
            self._scroll.updateGeometry()  # type: ignore[attr-defined]
            self._queue_stream_follow_passes()  # type: ignore[attr-defined]
        self._invalidate_sticky_extents()  # type: ignore[attr-defined]
        self._schedule_sticky_sync()  # type: ignore[attr-defined]

    def _ensure_streaming_turn_widgets(self) -> ChatMessageBubble:
        """Ensure assistant bubble, turn anchor, and viewport spacer exist."""
        if self._streaming_bubble is None:
            self._streaming_bubble = self.add_message("assistant", "", thinking="")
            self._streaming_bubble.begin_streaming()
        self._attach_streaming_bubble_height_hook(self._streaming_bubble)
        if self._turn_scroll_anchor is None:
            self._turn_scroll_anchor = self._find_last_user_bubble()
        self._apply_streaming_viewport_spacer()  # type: ignore[attr-defined]
        return self._streaming_bubble

    def _last_assistant_bubble(self) -> ChatMessageBubble | None:
        """Return the newest assistant bubble in the transcript, if any."""
        for index in range(self._messages_layout.count() - 1, -1, -1):
            item = self._messages_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, ChatMessageBubble) and widget.role == "assistant":
                return widget
        return None

    def _resolve_streaming_bubble(self) -> ChatMessageBubble | None:
        """Return the active stream bubble, falling back to the latest assistant row."""
        if self._streaming_bubble is not None:
            return self._streaming_bubble
        return self._last_assistant_bubble()

    def add_message(
        self,
        role: ChatRole,
        text: str,
        *,
        thinking: str = "",
        thinking_duration_seconds: int | None = None,
        sent_at: datetime | None = None,
        lazy_markdown: bool = False,
        message_id: int | None = None,
    ) -> ChatMessageBubble:
        """Append a message bubble to the transcript."""
        self._empty_label.hide()
        bubble = ChatMessageBubble(
            role,
            text,
            thinking=thinking,
            thinking_duration_seconds=thinking_duration_seconds,
            sent_at=sent_at,
            lazy_markdown=lazy_markdown,
        )
        self._ensure_virtual_spacers()
        assert self._bottom_virtual_spacer is not None
        insert_index = self._messages_layout.indexOf(self._bottom_virtual_spacer)
        self._messages_layout.insertWidget(insert_index, bubble)
        if message_id is not None:
            self.attach_message_id(bubble, message_id)
        if role == "user" and bubble._user_footer is not None:
            bubble._user_footer.stop_requested.connect(self.stop_requested.emit)  # type: ignore[attr-defined]
        if not self._defer_transcript_hooks:
            self._invalidate_sticky_turn_pairs()  # type: ignore[attr-defined]
            if role == "assistant":
                self._ensure_assistant_layout_hook(bubble)
            schedule = getattr(self, "_schedule_context_usage_refresh", None)
            if callable(schedule):
                schedule()
        return bubble

    def last_assistant_thinking_duration_seconds(self) -> int | None:
        """Return the thinking duration on the latest assistant bubble."""
        bubble = self._last_assistant_bubble()
        if bubble is None:
            return None
        return bubble.thinking_duration_seconds()

    def _clear_transcript_widgets(self) -> None:
        """Remove message bubbles without touching load-generation state."""
        self._deactivate_streaming_turn_user_footer()
        self._reset_pending_chunks()
        self._cancel_activity_timer()
        self._clear_sticky_turn_prompt()  # type: ignore[attr-defined]
        self._invalidate_sticky_turn_pairs()  # type: ignore[attr-defined]
        self._clear_streaming_viewport_spacer()  # type: ignore[attr-defined]
        self._detach_transcript_layout_hooks()
        self._streaming_bubble = None
        self._stream_bubble_height_hook = None
        self._turn_scroll_anchor = None
        self._stream_content_started = False
        self._stream_generation = 0
        self._open_stream_generation = 0
        self.reset_transcript_window()
        for i in reversed(range(self._messages_layout.count())):
            item = self._messages_layout.itemAt(i)
            widget = item.widget() if item is not None else None
            if isinstance(widget, ChatMessageBubble):
                widget.end_streaming(render=False)
                widget.setParent(None)
                widget.deleteLater()
            elif isinstance(widget, QWidget) and widget.objectName() == "aiChatSummarizedNotice":
                widget.setParent(None)
                widget.deleteLater()
        self._empty_label.show()

    def clear_streaming_transcript(self) -> None:
        """Remove all message bubbles and restore the empty state."""
        self.cancel_transcript_load()
        self._clear_transcript_widgets()

    def begin_assistant_stream(self) -> None:
        """Create one empty assistant bubble for streaming."""
        self._reset_pending_chunks()
        self._clear_sticky_turn_prompt()  # type: ignore[attr-defined]
        self._invalidate_sticky_turn_pairs()  # type: ignore[attr-defined]
        self._stream_generation += 1
        self._open_stream_generation = self._stream_generation
        self._stream_content_started = False
        self._turn_scroll_anchor = self._find_last_user_bubble()
        self._activate_streaming_turn_user_footer(self._turn_scroll_anchor)
        self._streaming_bubble = self.add_message("assistant", "", thinking="")
        self._streaming_bubble.begin_streaming()
        self._attach_streaming_bubble_height_hook(self._streaming_bubble)
        self._apply_streaming_viewport_spacer()  # type: ignore[attr-defined]
        self._streaming_bubble.show_activity(_ACTIVITY_DEFAULT_MESSAGE)
        self._start_activity_timer()
        self._request_turn_bottom_scroll()  # type: ignore[attr-defined]

    @Slot(str, str)
    def append_assistant_chunk(self, thinking_delta: str, content_delta: str) -> None:
        """Queue streaming thinking and/or answer text for batched delivery."""
        if self._open_stream_generation == 0:
            return
        if not thinking_delta and not content_delta:
            return
        self._pending_thinking_delta += thinking_delta
        self._pending_content_delta += content_delta
        if not self._chunk_coalesce_timer.isActive():
            self._chunk_coalesce_timer.start()

    @Slot()
    def _flush_pending_chunks(self) -> None:
        """Apply buffered thinking and answer deltas to the active bubble."""
        thinking_delta = self._pending_thinking_delta
        content_delta = self._pending_content_delta
        self._pending_thinking_delta = ""
        self._pending_content_delta = ""

        if self._open_stream_generation == 0:
            return
        if not thinking_delta and not content_delta:
            return

        bubble = self._resolve_streaming_bubble()
        if bubble is None:
            bubble = self._ensure_streaming_turn_widgets()
        else:
            self._streaming_bubble = bubble

        self._cancel_activity_timer()
        if thinking_delta or content_delta:
            bubble.hide_activity()

        bubble.set_defer_layout_height_changed(True)
        if bubble._markdown_body is not None:
            bubble._markdown_body.set_defer_height_changed(True)

        self._stream_layout_flush_in_progress = True
        self._messages.setUpdatesEnabled(False)
        try:
            if thinking_delta:
                bubble.append_thinking(thinking_delta, defer_geometry=True)
            if content_delta:
                self._stream_content_started = True
                bubble.append_content(content_delta, defer_geometry=True)
        finally:
            self._messages.setUpdatesEnabled(True)

        bubble.set_defer_layout_height_changed(False)
        self._stream_layout_flush_in_progress = False
        self._messages.updateGeometry()
        self._scroll.updateGeometry()  # type: ignore[attr-defined]
        self._apply_streaming_viewport_spacer()  # type: ignore[attr-defined]

        if self._open_stream_generation > 0 and self._scroll_lock_enabled:  # type: ignore[attr-defined]
            self._queue_stream_follow_passes()  # type: ignore[attr-defined]
        self._invalidate_sticky_extents()  # type: ignore[attr-defined]
        self._sync_sticky_turn_prompt()  # type: ignore[attr-defined]
        schedule = getattr(self, "_schedule_context_usage_refresh", None)
        if callable(schedule):
            schedule()

    def streaming_assistant_thinking(self) -> str:
        """Return thinking text accumulated in the active assistant bubble."""
        if self._streaming_bubble is None:
            return ""
        return self._streaming_bubble.thinking_text()

    def streaming_assistant_text(self) -> str:
        """Return answer text accumulated in the active assistant bubble."""
        if self._streaming_bubble is None:
            return ""
        return self._streaming_bubble.text()

    def is_pre_stream_cancel(self) -> bool:
        """Return whether stop should rewind the send (activity-only, no tokens yet)."""
        if self._open_stream_generation == 0:
            return False
        if self.streaming_assistant_thinking().strip():
            return False
        if self.streaming_assistant_text().strip():
            return False
        return not self._stream_content_started

    def discard_active_stream_turn(self) -> None:
        """Remove the in-flight assistant bubble without persisting a reply."""
        self._reset_pending_chunks()
        self._cancel_activity_timer()
        self._deactivate_streaming_turn_user_footer()
        bubble = self._resolve_streaming_bubble()
        if bubble is not None:
            self.remove_transcript_bubble(bubble)
        self._clear_streaming_viewport_spacer()  # type: ignore[attr-defined]
        self._streaming_bubble = None
        self._stream_bubble_height_hook = None
        self._stream_content_started = False
        self._open_stream_generation = 0
        self._turn_scroll_anchor = None
        self._streaming_turn_user_bubble = None
        self._invalidate_sticky_turn_pairs()  # type: ignore[attr-defined]
        self._invalidate_sticky_extents()  # type: ignore[attr-defined]
        self._sync_sticky_turn_prompt()  # type: ignore[attr-defined]

    def rollback_pre_stream_turn(self, user_text: str) -> None:
        """Discard the active stream and restore *user_text* to the composer."""
        user_bubble = self._streaming_turn_user_bubble or self._find_last_user_bubble()
        self.discard_active_stream_turn()
        if user_bubble is not None:
            self.remove_transcript_bubble(user_bubble)
        self.restore_composer_text(user_text)  # type: ignore[attr-defined]
        self._sync_transcript_empty_state()

    def _sync_transcript_empty_state(self) -> None:
        """Show or hide the empty-state label based on rendered bubbles."""
        if self._first_loaded_bubble() is None:
            self._empty_label.show()
        else:
            self._empty_label.hide()

    def apply_assistant_final(self, content: str, *, thinking: str = "") -> None:
        """Replace the latest assistant bubble with the final thinking and answer."""
        bubble = self._resolve_streaming_bubble() or self._last_assistant_bubble()
        if bubble is None:
            return
        current_thinking = bubble.thinking_text()
        current_content = bubble.text()
        final_thinking = thinking or current_thinking
        final_content = content or current_content
        if len(final_thinking) < len(current_thinking):
            final_thinking = current_thinking
        if len(final_content) < len(current_content):
            final_content = current_content
        bubble.set_parts(
            thinking=final_thinking,
            content=final_content,
        )

    def end_assistant_stream(
        self,
        content: str | None = None,
        *,
        thinking: str | None = None,
    ) -> None:
        """Finalize the streaming bubble and clear the handle."""
        self._flush_pending_chunks()

        bubble = self._resolve_streaming_bubble()

        if thinking is not None or content is not None:
            self.apply_assistant_final(
                content if content is not None else "",
                thinking=thinking if thinking is not None else "",
            )
        elif bubble is not None and bubble.is_content_streaming():
            bubble.end_streaming(render=True)

        self._cancel_activity_timer()
        self._hide_stream_activity()
        self._deactivate_streaming_turn_user_footer()

        content_started = self._stream_content_started
        if bubble is not None:
            bubble.clear_stream_layout_floor()
        self._clear_streaming_viewport_spacer()  # type: ignore[attr-defined]
        self._messages.updateGeometry()
        self._scroll.updateGeometry()  # type: ignore[attr-defined]
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

        self._streaming_bubble = None
        self._stream_bubble_height_hook = None
        self._stream_content_started = False
        self._open_stream_generation = 0
        self._invalidate_sticky_turn_pairs()  # type: ignore[attr-defined]
        self._invalidate_sticky_extents()  # type: ignore[attr-defined]

        self._attach_transcript_layout_hooks()
        self._update_scroll_down_button_visibility()  # type: ignore[attr-defined]
        self._sync_sticky_turn_prompt()  # type: ignore[attr-defined]
        self._schedule_virtual_transcript_pass()
        if self._scroll_lock_enabled:  # type: ignore[attr-defined]
            if content_started:
                QTimer.singleShot(0, lambda: self._scroll_to_bottom(force=True))
            else:
                QTimer.singleShot(0, lambda: self._scroll_to_turn_start(force=True))
        refresh = getattr(self, "refresh_context_usage", None)
        if callable(refresh):
            refresh()

    @Slot()
    def _on_activity_long_wait(self) -> None:
        """Escalate the activity caption when the first token is slow to arrive."""
        bubble = self._resolve_streaming_bubble()
        if bubble is None or not bubble.is_activity_visible():
            return
        bubble.set_activity_message(_ACTIVITY_LONG_WAIT_MESSAGE)

    @Slot(str)
    def set_activity_status(self, raw_status: str) -> None:
        """Update the activity caption from an SDK status event."""
        bubble = self._resolve_streaming_bubble()
        if bubble is None or not bubble.is_activity_visible():
            return
        label = format_activity_status(raw_status)
        if label is not None:
            bubble.set_activity_message(label)
