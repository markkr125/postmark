"""Virtualized transcript window — silent paging and widget eviction."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import datetime
from typing import Any, NamedTuple, cast

from PySide6.QtCore import QEventLoop, QPoint, QTimer
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from services.ai.chat.session_service import AiChatMessageDict, AiChatTranscriptPageDict
from services.ai.chat.transcript_window import (
    BOTTOM_PREFETCH_MARGIN_PX,
    EVICTION_BUFFER_TURNS,
    SCROLL_TOP_PREFETCH_THRESHOLD_PX,
    SCROLL_TOP_VIEWPORT_FRACTION,
    TOP_PREFETCH_MARGIN_PX,
    TOP_PREFETCH_VIEWPORT_FRACTION,
)
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.transcript.load import _ChatPanelTranscriptLoadMixin
from ui.sidebar.ai.transcript.older_loading_row import TranscriptOlderLoadingRow

_BOTTOM_PREFETCH_MARGIN_PX = BOTTOM_PREFETCH_MARGIN_PX
_VIRTUAL_PASS_MS = 32
_ESTIMATED_BUBBLE_HEIGHT_PX = 96


class _EvictedTurnUser(NamedTuple):
    """Cached user-prompt metadata after the transcript user row is evicted."""

    message_id: int | None
    text: str
    sent_at: datetime | None
    height_px: int


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
    _evicted_turn_users: dict[int, _EvictedTurnUser]
    _top_virtual_spacer: _VirtualTranscriptSpacer | None = None
    _bottom_virtual_spacer: _VirtualTranscriptSpacer | None = None
    _virtual_pass_timer: QTimer | None = None
    _older_page_loading_row: TranscriptOlderLoadingRow | None = None
    _window_load_callback: Any = None

    def _init_transcript_window_state(self) -> None:
        """Reset virtual transcript bookkeeping (call from panel streaming init)."""
        self._bubble_by_message_id = {}
        self._bubble_height_by_id = {}
        self._evicted_turn_users = {}
        self._virtual_session_id = None
        self._oldest_loaded_id = None
        self._newest_loaded_id = None
        self._has_older = False
        self._has_newer = False
        self._loading_window_page = False
        self._window_page_generation = 0
        timer = getattr(self, "_virtual_pass_timer", None)
        if timer is not None:
            timer.stop()
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

    def _ensure_older_page_loading_row(self) -> TranscriptOlderLoadingRow:
        """Create and insert the older-page loading row above transcript bubbles."""
        if self._older_page_loading_row is None:
            self._older_page_loading_row = TranscriptOlderLoadingRow(self._messages)
            self._ensure_virtual_spacers()
            assert self._top_virtual_spacer is not None
            index = self._messages_layout.indexOf(self._top_virtual_spacer)
            self._messages_layout.insertWidget(index, self._older_page_loading_row)
            self._older_page_loading_row.hide()
        return self._older_page_loading_row

    def _show_older_page_loading_row(self) -> None:
        """Show the in-transcript older-page fetch indicator."""
        self._ensure_older_page_loading_row().show_loading()

    def _hide_older_page_loading_row(self) -> None:
        """Hide the in-transcript older-page fetch indicator."""
        row = self._older_page_loading_row
        if row is not None:
            row.hide_loading()

    def _top_prefetch_margin_px(self) -> int:
        """Return the viewport-aware top margin that triggers older prefetch."""
        viewport_h = max(0, self._scroll.viewport().height())
        return max(TOP_PREFETCH_MARGIN_PX, int(viewport_h * TOP_PREFETCH_VIEWPORT_FRACTION))

    def _scroll_top_prefetch_threshold_px(self) -> int:
        """Return how far from scroll minimum still counts as near the top."""
        viewport_h = max(0, self._scroll.viewport().height())
        return max(
            SCROLL_TOP_PREFETCH_THRESHOLD_PX,
            int(viewport_h * SCROLL_TOP_VIEWPORT_FRACTION),
        )

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
            bubble = cast(Any, self)._last_assistant_bubble()
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

    def _init_virtual_pass_timer(self) -> None:
        """Create the trailing debounce timer for scroll-driven virtual passes."""
        if self._virtual_pass_timer is not None:
            return
        self._virtual_pass_timer = QTimer(self)  # type: ignore[arg-type]
        self._virtual_pass_timer.setSingleShot(True)
        self._virtual_pass_timer.setInterval(_VIRTUAL_PASS_MS)
        self._virtual_pass_timer.timeout.connect(self._run_virtual_transcript_pass)

    def _schedule_virtual_transcript_pass(self) -> None:
        """Debounce prefetch and eviction until scroll activity settles."""
        self._init_virtual_pass_timer()
        assert self._virtual_pass_timer is not None
        self._virtual_pass_timer.start()

    def _run_virtual_transcript_pass(self) -> None:
        """Prefetch older/newer pages and evict off-screen widgets."""
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
        bar = self._scroll.verticalScrollBar()
        top_y = self._widget_top_in_viewport(first)
        prefetch_margin = self._top_prefetch_margin_px()
        at_scroll_top = bar.value() <= bar.minimum() + self._scroll_top_prefetch_threshold_px()
        # Negative means the first row is still above the viewport (user near bottom).
        if top_y < 0:
            return
        if not at_scroll_top and top_y > prefetch_margin:
            return
        callback = self._window_load_callback
        session_id = self._virtual_session_id
        if callback is None or session_id is None:
            return
        self._loading_window_page = True
        self._window_page_generation += 1
        generation = self._window_page_generation
        self._show_older_page_loading_row()
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
        if generation != self._window_page_generation:
            return
        self._hide_older_page_loading_row()
        self._loading_window_page = False
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

    def _iter_orphan_sticky_turns(
        self,
    ) -> Iterator[tuple[_EvictedTurnUser, ChatMessageBubble]]:
        """Yield assistant rows whose paired user bubble was evicted."""
        pending_user: ChatMessageBubble | None = None
        for index in range(self._first_bubble_layout_index(), self._messages_layout.count()):
            item = self._messages_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is self._bottom_virtual_spacer:
                break
            if not isinstance(widget, ChatMessageBubble):
                continue
            if widget.role == "user":
                pending_user = widget
                continue
            if widget.role != "assistant":
                continue
            if pending_user is not None:
                pending_user = None
                continue
            assistant_id = widget.message_id
            if assistant_id is None:
                continue
            evicted = self._evicted_turn_users.get(assistant_id)
            if evicted is not None:
                yield evicted, widget

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
        pending_user: ChatMessageBubble | None = None
        for index in range(self._first_bubble_layout_index(), self._messages_layout.count()):
            item = self._messages_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is self._bottom_virtual_spacer:
                break
            if not isinstance(widget, ChatMessageBubble):
                continue
            if widget.role == "user":
                pending_user = widget
                continue
            if widget.role != "assistant" or pending_user is None:
                continue
            if cast(Any, self)._bubble_intersects_viewport(widget):
                if pending_user.message_id is not None:
                    protected.add(pending_user.message_id)
                if widget.message_id is not None:
                    protected.add(widget.message_id)
            pending_user = None
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
            if (
                bubble.role == "user"
                and cast(Any, self)._assistant_bubble_for_turn(bubble) is not None
                and cast(Any, self)._bubble_intersects_viewport(
                    cast(Any, self)._assistant_bubble_for_turn(bubble)
                )
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
        if bubble.role == "user":
            partner = cast(Any, self)._assistant_bubble_for_turn(bubble)
            if partner is not None and partner.message_id is not None:
                self._evicted_turn_users[partner.message_id] = _EvictedTurnUser(
                    message_id=message_id,
                    text=bubble.text(),
                    sent_at=bubble.sent_at(),
                    height_px=self._measure_bubble_height(bubble),
                )
        if message_id is not None:
            self._bubble_by_message_id.pop(message_id, None)
        bubble.end_streaming(render=False)
        self._messages_layout.removeWidget(bubble)
        bubble.setParent(None)
        bubble.deleteLater()

    def remove_transcript_bubble(self, bubble: ChatMessageBubble) -> None:
        """Remove one transcript bubble from the layout and id maps."""
        host = cast(Any, self)
        hooks = host._transcript_layout_hooks
        if bubble in hooks:
            with contextlib.suppress(TypeError, RuntimeError):
                bubble.layout_height_changed.disconnect(host._on_transcript_bubble_layout_changed)
            hooks.remove(bubble)
        self._destroy_virtual_bubble(bubble)
        self._recompute_loaded_id_bounds()

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
        self._hide_older_page_loading_row()
        self._evicted_turn_users.clear()
        self._reset_virtual_spacers()

    def on_transcript_scroll_activity(self) -> None:
        """Hook from scrollbar movement to drive silent paging and eviction."""
        self._schedule_virtual_transcript_pass()
