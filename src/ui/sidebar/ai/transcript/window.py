"""Virtualized transcript window — silent paging and widget eviction."""

from __future__ import annotations

from typing import Any, cast

from PySide6.QtCore import QEventLoop, QPoint, QTimer
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from services.ai.chat.session_service import AiChatMessageDict, AiChatTranscriptPageDict
from services.ai.chat.transcript_window import (
    BOTTOM_PREFETCH_MARGIN_PX,
    EVICTION_BUFFER_TURNS,
    TOP_PREFETCH_MARGIN_PX,
)
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.transcript.load import _ChatPanelTranscriptLoadMixin

_BOTTOM_PREFETCH_MARGIN_PX = BOTTOM_PREFETCH_MARGIN_PX
_VIRTUAL_PASS_MS = 32
_ESTIMATED_BUBBLE_HEIGHT_PX = 96


class _VirtualTranscriptSpacer(QWidget):
    """Invisible height placeholder for evicted transcript rows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create a zero-height spacer row."""
        super().__init__(parent)
        self.setObjectName("aiChatVirtualSpacer")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(0)


class _ChatPanelTranscriptWindowMixin(_ChatPanelTranscriptLoadMixin):
    """Tail-first transcript paging with silent prepend/append and eviction."""

    _streaming_bubble: ChatMessageBubble | None
    _open_stream_generation: int
    _turn_scroll_anchor: ChatMessageBubble | None
    _virtual_session_id: str | None = None
    _oldest_loaded_id: int | None = None
    _newest_loaded_id: int | None = None
    _has_older: bool = False
    _has_newer: bool = False
    _loading_window_page: bool = False
    _window_page_generation: int = 0
    _bubble_by_message_id: dict[int, ChatMessageBubble]
    _bubble_height_by_id: dict[int, int]
    _top_virtual_spacer: _VirtualTranscriptSpacer | None = None
    _bottom_virtual_spacer: _VirtualTranscriptSpacer | None = None
    _virtual_pass_pending: bool = False
    _window_load_callback: Any = None

    def _init_transcript_window_state(self) -> None:
        """Reset virtual transcript bookkeeping (call from panel streaming init)."""
        self._bubble_by_message_id = {}
        self._bubble_height_by_id = {}
        self._virtual_session_id = None
        self._oldest_loaded_id = None
        self._newest_loaded_id = None
        self._has_older = False
        self._has_newer = False
        self._loading_window_page = False
        self._window_page_generation = 0
        self._virtual_pass_pending = False
        self._window_load_callback = None

    def set_window_load_callback(self, callback: Any) -> None:
        """Register ``(kind, session_id, cursor_id, generation)`` for background paging."""
        self._window_load_callback = callback

    def _ensure_virtual_spacers(self) -> None:
        """Insert top/bottom virtual spacers after the empty-state label."""
        if self._top_virtual_spacer is None:
            self._top_virtual_spacer = _VirtualTranscriptSpacer(self._messages)
            index = self._messages_layout.indexOf(self._empty_label) + 1
            self._messages_layout.insertWidget(index, self._top_virtual_spacer)
        if self._bottom_virtual_spacer is None:
            self._bottom_virtual_spacer = _VirtualTranscriptSpacer(self._messages)
            self._messages_layout.addWidget(self._bottom_virtual_spacer)

    def _reset_virtual_spacers(self) -> None:
        """Zero virtual spacer heights without removing widgets."""
        self._ensure_virtual_spacers()
        assert self._top_virtual_spacer is not None
        assert self._bottom_virtual_spacer is not None
        self._top_virtual_spacer.setFixedHeight(0)
        self._bottom_virtual_spacer.setFixedHeight(0)

    def _apply_virtual_page_state(self, page: AiChatTranscriptPageDict) -> None:
        """Record window cursors after a tail or page load."""
        messages = page["messages"]
        self._has_older = page["has_older"]
        self._has_newer = page["has_newer"]
        self._oldest_loaded_id = page["oldest_id"]
        self._newest_loaded_id = page["newest_id"]
        if messages:
            self._empty_label.hide()

    def begin_virtual_session(self, session_id: str, page: AiChatTranscriptPageDict) -> None:
        """Bind *session_id* and initial tail page before incremental widget build."""
        self._virtual_session_id = session_id
        self._bubble_by_message_id.clear()
        self._bubble_height_by_id.clear()
        self._reset_virtual_spacers()
        self._apply_virtual_page_state(page)

    def attach_message_id(self, bubble: ChatMessageBubble, message_id: int) -> None:
        """Associate a rendered bubble with its SQLite row id."""
        bubble.set_message_id(message_id)
        self._bubble_by_message_id[message_id] = bubble
        if self._oldest_loaded_id is None or message_id < self._oldest_loaded_id:
            self._oldest_loaded_id = message_id
        if self._newest_loaded_id is None or message_id > self._newest_loaded_id:
            self._newest_loaded_id = message_id

    def attach_last_user_message_id(self, message_id: int) -> None:
        """Set the id on the latest user bubble after persistence."""
        bubble = cast(Any, self)._find_last_user_bubble()
        if bubble is None:
            return
        self.attach_message_id(bubble, message_id)

    def attach_streaming_assistant_message_id(self, message_id: int) -> None:
        """Set the id on the active assistant bubble after persistence."""
        bubble = self._streaming_bubble
        if bubble is None:
            return
        self.attach_message_id(bubble, message_id)

    def _first_bubble_layout_index(self) -> int:
        """Return the layout index where transcript bubbles begin."""
        self._ensure_virtual_spacers()
        assert self._top_virtual_spacer is not None
        return int(self._messages_layout.indexOf(self._top_virtual_spacer) + 1)

    def _first_loaded_bubble(self) -> ChatMessageBubble | None:
        """Return the chronologically first rendered bubble."""
        for index in range(self._first_bubble_layout_index(), self._messages_layout.count()):
            item = self._messages_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, ChatMessageBubble):
                return widget
            if widget is self._bottom_virtual_spacer:
                break
        return None

    def _last_loaded_bubble(self) -> ChatMessageBubble | None:
        """Return the chronologically last rendered bubble."""
        last: ChatMessageBubble | None = None
        for index in range(self._first_bubble_layout_index(), self._messages_layout.count()):
            item = self._messages_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, ChatMessageBubble):
                last = widget
        return last

    def _widget_top_in_viewport(self, widget: QWidget) -> int:
        """Return widget top edge Y relative to the viewport (negative = above)."""
        bar = self._scroll.verticalScrollBar()
        top = widget.mapTo(self._messages, QPoint(0, 0)).y()
        return int(top - bar.value())

    def _schedule_virtual_transcript_pass(self) -> None:
        """Coalesce prefetch and eviction work after scroll or layout."""
        if self._virtual_pass_pending:
            return
        self._virtual_pass_pending = True
        QTimer.singleShot(_VIRTUAL_PASS_MS, self._run_virtual_transcript_pass)

    def _run_virtual_transcript_pass(self) -> None:
        """Prefetch older/newer pages and evict off-screen widgets."""
        self._virtual_pass_pending = False
        if self._loading_window_page or self._virtual_session_id is None:
            return
        if self._open_stream_generation > 0 and self._loading_window_page:
            return
        self._maybe_prefetch_older_page()
        self._maybe_prefetch_newer_page()
        self._maybe_evict_transcript_widgets()

    def _maybe_prefetch_older_page(self) -> None:
        """Silently request older messages when the first bubble nears the top."""
        if not self._has_older or self._loading_window_page:
            return
        if self.is_transcript_load_active():
            return
        if cast(Any, self)._is_pinned_to_bottom():
            return
        if self._oldest_loaded_id is None:
            return
        first = self._first_loaded_bubble()
        if first is None:
            return
        top_y = self._widget_top_in_viewport(first)
        # Negative means the first row is still above the viewport (user near bottom).
        if top_y < 0 or top_y > TOP_PREFETCH_MARGIN_PX:
            return
        callback = self._window_load_callback
        session_id = self._virtual_session_id
        if callback is None or session_id is None:
            return
        self._loading_window_page = True
        self._window_page_generation += 1
        generation = self._window_page_generation
        callback("older", session_id, self._oldest_loaded_id, generation)

    def _maybe_prefetch_newer_page(self) -> None:
        """Silently request newer messages when scrolling down into evicted range."""
        if not self._has_newer or self._loading_window_page:
            return
        if self.is_transcript_load_active():
            return
        if self._newest_loaded_id is None:
            return
        last = self._last_loaded_bubble()
        if last is None:
            return
        bar = self._scroll.verticalScrollBar()
        viewport_h = self._scroll.viewport().height()
        bottom_y = last.mapTo(self._messages, QPoint(0, 0)).y() + last.height()
        viewport_bottom = bar.value() + viewport_h
        # Positive distance means the last row is still below the viewport.
        if bottom_y > viewport_bottom + _BOTTOM_PREFETCH_MARGIN_PX:
            return
        if bottom_y < viewport_bottom - _BOTTOM_PREFETCH_MARGIN_PX:
            return
        callback = self._window_load_callback
        session_id = self._virtual_session_id
        if callback is None or session_id is None:
            return
        self._loading_window_page = True
        self._window_page_generation += 1
        generation = self._window_page_generation
        callback("newer", session_id, self._newest_loaded_id, generation)

    def apply_older_page(self, page: AiChatTranscriptPageDict, *, generation: int) -> None:
        """Prepend an older page fetched off the GUI thread."""
        self._loading_window_page = False
        if generation != self._window_page_generation:
            return
        messages = page["messages"]
        if not messages:
            self._has_older = page["has_older"]
            return
        self._prepend_older_messages(messages)
        self._has_older = page["has_older"]
        self._oldest_loaded_id = page["oldest_id"]
        self._schedule_virtual_transcript_pass()

    def apply_newer_page(self, page: AiChatTranscriptPageDict, *, generation: int) -> None:
        """Append a newer page after downward scroll into evicted content."""
        self._loading_window_page = False
        if generation != self._window_page_generation:
            return
        messages = page["messages"]
        if not messages:
            self._has_newer = page["has_newer"]
            return
        self._append_newer_messages(messages)
        self._has_newer = page["has_newer"]
        self._newest_loaded_id = page["newest_id"]
        self._schedule_virtual_transcript_pass()

    def _prepend_older_messages(self, messages: list[AiChatMessageDict]) -> None:
        """Insert older rows above the first bubble with scroll anchoring."""
        anchor = self._first_loaded_bubble()
        anchor_viewport_y = self._widget_top_in_viewport(anchor) if anchor is not None else 0
        self._loading_window_page = True
        self._messages.setUpdatesEnabled(False)
        try:
            insert_index = self._first_bubble_layout_index()
            for message in messages:
                bubble = self._message_from_dict(message, force_render=True)
                self._messages_layout.insertWidget(insert_index, bubble)
                insert_index += 1
            self._messages.updateGeometry()
            self._scroll.updateGeometry()
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            if anchor is not None and anchor.isVisible():
                delta = self._widget_top_in_viewport(anchor) - anchor_viewport_y
                if delta != 0:
                    bar = self._scroll.verticalScrollBar()
                    self._set_bar_value(  # type: ignore[attr-defined]
                        bar,
                        max(bar.minimum(), min(bar.maximum(), bar.value() + delta)),
                    )
        finally:
            self._messages.setUpdatesEnabled(True)
            self._loading_window_page = False
        cast(Any, self)._invalidate_sticky_turn_pairs()

    def _append_newer_messages(self, messages: list[AiChatMessageDict]) -> None:
        """Insert newer rows before the bottom virtual spacer."""
        self._ensure_virtual_spacers()
        assert self._bottom_virtual_spacer is not None
        insert_index = self._messages_layout.indexOf(self._bottom_virtual_spacer)
        self._messages.setUpdatesEnabled(False)
        try:
            for offset, message in enumerate(messages):
                bubble = self._message_from_dict(message, force_render=False)
                self._messages_layout.insertWidget(insert_index + offset, bubble)
        finally:
            self._messages.setUpdatesEnabled(True)
        cast(Any, self)._invalidate_sticky_turn_pairs()

    def _protected_message_ids(self) -> set[int]:
        """Return message ids that must not be evicted."""
        protected: set[int] = set()
        if self._streaming_bubble is not None and self._streaming_bubble.message_id is not None:
            protected.add(self._streaming_bubble.message_id)
        anchor = self._turn_scroll_anchor
        if anchor is not None and anchor.message_id is not None:
            protected.add(anchor.message_id)
            assistant = cast(Any, self)._assistant_bubble_for_turn(anchor)
            if assistant is not None and assistant.message_id is not None:
                protected.add(assistant.message_id)
        prev_user = self._previous_user_bubble()
        if prev_user is not None and prev_user.message_id is not None:
            protected.add(prev_user.message_id)
        sticky_anchor = getattr(self, "_sticky_turn_anchor", None)
        if isinstance(sticky_anchor, ChatMessageBubble) and sticky_anchor.message_id is not None:
            protected.add(sticky_anchor.message_id)
        for user, assistant in cast(Any, self)._iter_chat_turns():
            if cast(Any, self)._bubble_intersects_viewport(user) or cast(
                Any, self
            )._bubble_intersects_viewport(assistant):
                if user.message_id is not None:
                    protected.add(user.message_id)
                if assistant.message_id is not None:
                    protected.add(assistant.message_id)
        buffer_turns = self._buffer_turn_ids(EVICTION_BUFFER_TURNS)
        protected.update(buffer_turns)
        return protected

    def _previous_user_bubble(self) -> ChatMessageBubble | None:
        """Return the user bubble immediately before the active turn anchor."""
        anchor = self._turn_scroll_anchor
        if anchor is None:
            return None
        previous: ChatMessageBubble | None = None
        for index in range(self._messages_layout.count()):
            item = self._messages_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if not isinstance(widget, ChatMessageBubble):
                continue
            if widget is anchor:
                return previous if previous is not None and previous.role == "user" else None
            if widget.role == "user":
                previous = widget
        return None

    def _buffer_turn_ids(self, turns: int) -> set[int]:
        """Collect message ids for the first/last *turns* around the viewport."""
        turn_pairs = list(cast(Any, self)._iter_chat_turns())
        if not turn_pairs:
            return set()
        visible_indices = [
            index
            for index, (user, assistant) in enumerate(turn_pairs)
            if cast(Any, self)._bubble_intersects_viewport(user)
            or cast(Any, self)._bubble_intersects_viewport(assistant)
        ]
        if not visible_indices:
            return set()
        start = max(0, min(visible_indices) - turns)
        end = min(len(turn_pairs), max(visible_indices) + turns + 1)
        ids: set[int] = set()
        for user, assistant in turn_pairs[start:end]:
            if user.message_id is not None:
                ids.add(user.message_id)
            if assistant.message_id is not None:
                ids.add(assistant.message_id)
        return ids

    def _maybe_evict_transcript_widgets(self) -> None:
        """Destroy bubbles outside the protected band and fold height into spacers."""
        if self.is_transcript_load_active():
            return
        protected = self._protected_message_ids()
        bubbles = [
            widget
            for index in range(self._first_bubble_layout_index(), self._messages_layout.count())
            if (item := self._messages_layout.itemAt(index)) is not None
            and isinstance(widget := item.widget(), ChatMessageBubble)
        ]
        max_widgets = EVICTION_BUFFER_TURNS * 4 + 8
        if len(bubbles) <= max_widgets:
            return
        self._ensure_virtual_spacers()
        assert self._top_virtual_spacer is not None
        assert self._bottom_virtual_spacer is not None
        midpoint = len(bubbles) // 2
        evicted_any = False
        for bubble in bubbles:
            if len(bubbles) <= max_widgets:
                break
            msg_id = bubble.message_id
            if msg_id is not None and msg_id in protected:
                continue
            if msg_id is None and (
                bubble is self._streaming_bubble or bubble is self._turn_scroll_anchor
            ):
                continue
            index = bubbles.index(bubble)
            height = self._measure_bubble_height(bubble)
            if index < midpoint:
                self._top_virtual_spacer.setFixedHeight(self._top_virtual_spacer.height() + height)
            else:
                self._bottom_virtual_spacer.setFixedHeight(
                    self._bottom_virtual_spacer.height() + height
                )
            self._destroy_virtual_bubble(bubble)
            bubbles.remove(bubble)
            evicted_any = True
        if evicted_any:
            self._recompute_loaded_id_bounds()
            self._has_newer = self._has_newer or bool(self._bottom_virtual_spacer.height())
            cast(Any, self)._invalidate_sticky_turn_pairs()

    def _measure_bubble_height(self, bubble: ChatMessageBubble) -> int:
        """Return cached or live height for spacer accounting."""
        message_id = bubble.message_id
        height = max(bubble.sizeHint().height(), bubble.height(), _ESTIMATED_BUBBLE_HEIGHT_PX)
        if message_id is not None:
            self._bubble_height_by_id[message_id] = height
            return self._bubble_height_by_id[message_id]
        return height

    def _destroy_virtual_bubble(self, bubble: ChatMessageBubble) -> None:
        """Remove one bubble widget from the layout and id map."""
        message_id = bubble.message_id
        if message_id is not None:
            self._bubble_by_message_id.pop(message_id, None)
        bubble.end_streaming(render=False)
        self._messages_layout.removeWidget(bubble)
        bubble.setParent(None)
        bubble.deleteLater()

    def _recompute_loaded_id_bounds(self) -> None:
        """Refresh oldest/newest ids from remaining rendered bubbles."""
        ids = [
            bubble.message_id
            for bubble in self._bubble_by_message_id.values()
            if bubble.message_id is not None
        ]
        if not ids:
            self._oldest_loaded_id = None
            self._newest_loaded_id = None
            return
        self._oldest_loaded_id = min(ids)
        self._newest_loaded_id = max(ids)

    def reset_transcript_window(self) -> None:
        """Clear virtual window state during transcript teardown."""
        self._bubble_by_message_id.clear()
        self._bubble_height_by_id.clear()
        self._virtual_session_id = None
        self._oldest_loaded_id = None
        self._newest_loaded_id = None
        self._has_older = False
        self._has_newer = False
        self._loading_window_page = False
        self._reset_virtual_spacers()

    def on_transcript_scroll_activity(self) -> None:
        """Hook from scrollbar movement to drive silent paging and eviction."""
        self._schedule_virtual_transcript_pass()
