"""Sticky auto-scroll helpers for the AI chat transcript."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from PySide6.QtCore import QEventLoop, QPoint, QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QLayout,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QSizePolicy,
    QWidget,
)
from shiboken6 import isValid

from ui.sidebar.ai.chat_panel.scroll.widget_coords import (
    map_widget_point_to_ancestor,
    map_widget_y_to_ancestor,
)
from ui.sidebar.ai.chat_panel.scroll.smooth_scroll import SmoothScroller
from ui.sidebar.ai.chat_panel.scroll.sticky_prompt import _ChatPanelStickyPromptMixin
from ui.sidebar.ai.message_bubble import ChatMessageBubble

_FOLLOW_THRESHOLD_PX = 2
_TURN_SCROLL_MARGIN_PX = 8
_STICKY_ABOVE_VIEWPORT_SCROLL_SLACK_PX = 32
_RESIZE_SETTLE_MS = 75
_STREAMING_SPACER_MIN_DELTA_PX = 12


class _ChatPanelScrollMixin(_ChatPanelStickyPromptMixin):  # type: ignore[misc]
    """Scroll-lock follow during assistant streaming and turn-boundary scroll."""

    _scroll: QScrollArea
    _messages: QWidget
    _messages_layout: Any = None
    _open_stream_generation: int = 0
    _scroll_lock_enabled: bool = False
    _programmatic_scroll: bool = False
    _last_scroll_value: int = 0
    _stream_follow_dirty: bool = False
    _stream_follow_frame_pending: bool = False
    _stream_follow_retry_pending: bool = False
    _scroll_range_shrunk_recent: bool = False
    _last_scroll_maximum: int = 0
    _turn_scroll_pending: bool = False
    _scroll_down_btn: QPushButton
    _streaming_viewport_spacer: QWidget | None = None
    _turn_scroll_anchor: ChatMessageBubble | None = None
    _stream_content_started: bool = False
    _stream_thinking_bottom_follow: bool = False
    _streaming_bubble: ChatMessageBubble | None = None
    _smooth_scroller: SmoothScroller
    _smooth_scroll_active: bool = False
    _sticky_sync_deferred_during_smooth: bool = False
    _resize_active: bool = False
    _resize_settle_timer: QTimer
    _resize_settle_generation: int = 0
    _resize_settle_due_generation: int = 0
    _sticky_sync_deferred_during_resize: bool = False
    _edit_scroll_pending: bool = False
    _pending_edit_scroll_bubble: ChatMessageBubble | None = None
    _messages_bottom_stretch_index: int = -1
    _short_turn_spacer_reconcile_generation: int = 0

    def _clamp_messages_to_viewport_width(self) -> None:
        """Keep ``_messages`` exactly within the viewport column."""
        hbar = self._scroll.horizontalScrollBar()
        viewport = self._scroll.viewport()
        vp_w = viewport.width()
        if vp_w <= 0:
            return
        messages = self._messages
        messages.setMinimumWidth(vp_w)
        messages.setMaximumWidth(vp_w)
        if messages.width() != vp_w:
            messages.resize(vp_w, messages.height())
        messages.updateGeometry()
        if hbar.maximum() > 0:
            hbar.setValue(0)

    def _init_scroll_controller(self) -> None:
        """Connect scrollbar signals for scroll-lock follow (call from panel ``__init__``)."""
        self._resize_active = False
        self._resize_settle_generation = 0
        self._resize_settle_due_generation = 0
        self._sticky_sync_deferred_during_resize = False
        self._edit_scroll_pending = False
        self._pending_edit_scroll_bubble = None
        self._resize_settle_timer = QTimer(self)  # type: ignore[arg-type]
        self._resize_settle_timer.setSingleShot(True)
        self._resize_settle_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._resize_settle_timer.setInterval(_RESIZE_SETTLE_MS)
        self._resize_settle_timer.timeout.connect(self._on_resize_settle_timer_fired)
        bar = self._scroll.verticalScrollBar()
        self._last_scroll_value = bar.value()
        self._last_scroll_maximum = bar.maximum()
        bar.valueChanged.connect(self._on_scrollbar_value_changed)
        bar.sliderPressed.connect(self._on_scrollbar_slider_pressed)
        bar.sliderReleased.connect(self._on_scrollbar_slider_released)
        bar.rangeChanged.connect(self._on_scrollbar_range_changed)
        bar.valueChanged.connect(self._on_transcript_scroll_for_lazy_markdown)
        self._smooth_scroller = SmoothScroller(
            self._scroll,
            on_wheel_delta=self._on_smooth_wheel_delta,
            on_animation_started=self._on_smooth_scroll_started,
            on_animation_finished=self._on_smooth_scroll_finished,
            parent=self,  # type: ignore[arg-type]
        )

    def _on_smooth_scroll_started(self) -> None:
        """Mark smooth scrolling active so sticky sync can defer until settle."""
        self._smooth_scroll_active = True

    def _on_smooth_scroll_finished(self) -> None:
        """Flush deferred sticky sync after smooth scrolling settles."""
        self._smooth_scroll_active = False
        self._schedule_sticky_sync()

    def _detach_stream_follow_for_user_scroll(self) -> None:
        """Disable streaming auto-follow after explicit user scroll input."""
        if self._open_stream_generation == 0:
            return
        self._scroll_lock_enabled = False
        self._stream_follow_dirty = False
        self._stream_follow_frame_pending = False
        self._stream_follow_retry_pending = False
        self._scroll_range_shrunk_recent = False
        self._stream_thinking_bottom_follow = False
        self._update_scroll_down_button_visibility()

    def _on_smooth_wheel_delta(self, delta_px: int) -> None:
        """Detach follow immediately when wheel input moves upward during a stream."""
        if delta_px < 0:
            self._detach_stream_follow_for_user_scroll()

    def _set_bar_value(self, bar: QScrollBar, value: int) -> None:
        """Programmatically set scrollbar value without updating scroll-lock state."""
        self._smooth_scroller.cancel(sync_value=value)
        self._programmatic_scroll = True
        try:
            with QSignalBlocker(bar):
                bar.setValue(value)
            self._last_scroll_value = bar.value()
        finally:
            self._programmatic_scroll = False

    def _arm_scroll_lock(self) -> None:
        """Re-enable auto-follow on content growth."""
        self._scroll_lock_enabled = True
        self._update_scroll_down_button_visibility()

    def _is_pinned_to_bottom(self) -> bool:
        """Return whether the transcript scrollbar is near the bottom."""
        bar = self._scroll.verticalScrollBar()
        return bar.value() >= bar.maximum() - _FOLLOW_THRESHOLD_PX

    def _scroll_value_for_turn_start(self) -> int:
        """Return scroll offset that places the turn anchor near the viewport top."""
        anchor = self._turn_scroll_anchor
        bar = self._scroll.verticalScrollBar()
        if anchor is None:
            return bar.maximum()
        y = map_widget_y_to_ancestor(anchor, self._messages)
        if y is None:
            return bar.maximum()
        return max(0, min(y - _TURN_SCROLL_MARGIN_PX, bar.maximum()))

    def _scroll_value_for_bubble_top(self, bubble: ChatMessageBubble) -> int:
        """Return scroll offset that places *bubble* near the viewport top."""
        bar = self._scroll.verticalScrollBar()
        anchor = bubble.user_message_host() or bubble
        y = map_widget_y_to_ancestor(anchor, self._messages)
        if y is None:
            return bar.maximum()
        return max(0, min(y - _TURN_SCROLL_MARGIN_PX, bar.maximum()))

    def _scroll_to_user_bubble(self, bubble: ChatMessageBubble) -> None:
        """Scroll so *bubble* is near the top of the transcript viewport."""
        bar = self._scroll.verticalScrollBar()
        target = self._scroll_value_for_bubble_top(bubble)
        self._set_bar_value(bar, target)

    def _request_scroll_to_user_bubble(self, bubble: ChatMessageBubble) -> None:
        """Defer scroll until inline-edit layout has settled."""
        self._pending_edit_scroll_bubble = bubble
        if self._edit_scroll_pending:
            return
        self._edit_scroll_pending = True
        QTimer.singleShot(0, self._flush_scroll_to_user_bubble)

    def _flush_scroll_to_user_bubble(self) -> None:
        """Scroll to the user row after geometry updates from inline edit."""
        bubble = getattr(self, "_pending_edit_scroll_bubble", None)
        self._edit_scroll_pending = False
        if bubble is None or not isValid(bubble):
            return
        self._messages.updateGeometry()
        self._scroll.updateGeometry()
        for _ in range(2):
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        bar = self._scroll.verticalScrollBar()
        target = self._scroll_value_for_bubble_top(bubble)
        self._set_bar_value(bar, target)
        if target == 0 and bar.maximum() > 100:
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            target = self._scroll_value_for_bubble_top(bubble)
            self._set_bar_value(bar, target)

    def _messages_top_stretch_index(self) -> int:
        """Return the layout index of the leading transcript slack stretch."""
        layout = self._messages_layout
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item is not None and item.spacerItem() is not None:
                return index
        return -1

    def _set_messages_top_stretch_factor(self, _factor: int) -> None:
        """Keep the leading spacer fixed so row positions are content-driven."""
        index = self._messages_top_stretch_index()
        if index < 0:
            return
        item = self._messages_layout.itemAt(index)
        if item is None:
            return
        spacer = item.spacerItem()
        if spacer is None:
            return
        spacer.changeSize(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Minimum,
        )
        self._messages_layout.setStretch(index, 0)
        self._messages_layout.invalidate()

    def _ensure_messages_bottom_stretch(self) -> int:
        """Return the layout index of the trailing slack stretch (always the last item)."""
        layout = self._messages_layout
        if layout.count() > 0:
            last_index = int(layout.count() - 1)
            item = layout.itemAt(last_index)
            if item is not None and item.spacerItem() is not None:
                for index in range(last_index - 1, 0, -1):
                    stray = layout.itemAt(index)
                    if stray is not None and stray.spacerItem() is not None:
                        layout.takeAt(index)
                last_index = int(layout.count() - 1)
                self._messages_bottom_stretch_index = last_index
                return last_index
        layout.addStretch(0)
        for stray_index in range(layout.count() - 2, 0, -1):
            stray = layout.itemAt(stray_index)
            if stray is not None and stray.spacerItem() is not None:
                layout.takeAt(stray_index)
        index = int(layout.count() - 1)
        self._messages_bottom_stretch_index = index
        return index

    def _set_messages_bottom_stretch_factor(self, factor: int) -> None:
        """Let only the trailing spacer absorb viewport slack below transcript rows."""
        index = self._ensure_messages_bottom_stretch()
        item = self._messages_layout.itemAt(index)
        if item is None:
            return
        spacer = item.spacerItem()
        if spacer is None:
            return
        policy = QSizePolicy.Policy.Expanding if factor > 0 else QSizePolicy.Policy.Minimum
        spacer.changeSize(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            policy,
        )
        self._messages_layout.setStretch(index, max(0, factor))
        self._messages_layout.invalidate()

    def _reset_messages_bottom_stretch_index(self) -> None:
        """Drop cached bottom-stretch index after transcript layout teardown."""
        self._messages_bottom_stretch_index = -1

    def _use_turn_anchor_layout(self) -> bool:
        """Return whether the transcript should pack turns from the top."""
        if self._turn_scroll_anchor is None:
            return False
        if self._open_stream_generation > 0:
            return True
        return self._streaming_viewport_spacer is not None

    def _sync_messages_top_stretch(self) -> None:
        """Pack transcript rows at the top and leave slack after the transcript."""
        self._set_messages_top_stretch_factor(0)
        self._set_messages_bottom_stretch_factor(1)

    def _assistant_row_extent_height(self, bubble: ChatMessageBubble) -> int:
        """Return the laid-out assistant row height used for turn-extent math."""
        laid_out = bubble.height()
        hint = bubble.sizeHint().height()
        if laid_out > 0:
            return laid_out
        return hint

    def _turn_bottom_y_in_messages(self, assistant: ChatMessageBubble) -> int | None:
        """Return the assistant row bottom edge Y in ``_messages`` coordinates."""
        bubble_height = self._assistant_row_extent_height(assistant)
        return map_widget_y_to_ancestor(assistant, self._messages, offset_y=bubble_height)

    def _turn_scroll_headroom_px(self) -> int:
        """Return extra layout height so the turn anchor can scroll to the viewport top."""
        anchor = self._turn_scroll_anchor
        if anchor is None:
            return 0
        y = map_widget_y_to_ancestor(anchor, self._messages)
        if y is None:
            return 0
        return max(0, y - _TURN_SCROLL_MARGIN_PX) + (
            _STICKY_ABOVE_VIEWPORT_SCROLL_SLACK_PX if y > _TURN_SCROLL_MARGIN_PX else 0
        )

    def _target_streaming_spacer_height(
        self,
        assistant: ChatMessageBubble | None = None,
    ) -> int:
        """Return spacer height so transcript minimum height matches one viewport."""
        viewport_h = self._scroll.viewport().height()
        if viewport_h <= 0:
            return 0
        bubble = assistant if assistant is not None else self._streaming_bubble
        if bubble is None:
            return 0
        self._messages_layout.activate()
        content_min = self._messages.minimumSizeHint().height()
        if self._streaming_viewport_spacer is not None:
            content_min -= self._streaming_viewport_spacer.height()
        headroom = self._turn_scroll_headroom_px()
        if headroom <= 0:
            return 0
        target = max(0, viewport_h - content_min + headroom)
        if self._streaming_viewport_spacer is None and target > 0:
            layout = self._messages_layout
            target = max(0, target - layout.spacing())
        return target

    def _streaming_turn_extent_px(self, assistant: ChatMessageBubble | None = None) -> int:
        """Return height from the turn anchor top to the bottom of the assistant row."""
        anchor = self._turn_scroll_anchor
        bubble = assistant if assistant is not None else self._streaming_bubble
        if anchor is None or bubble is None:
            return 0
        top = map_widget_y_to_ancestor(anchor, self._messages)
        bubble_height = self._assistant_row_extent_height(bubble)
        bottom = map_widget_y_to_ancestor(bubble, self._messages, offset_y=bubble_height)
        if top is None or bottom is None:
            return 0
        return max(0, bottom - top)

    def _request_turn_bottom_scroll(self) -> None:
        """Scroll to the start of a new user turn after layout settles."""
        self._arm_scroll_lock()
        if self._turn_scroll_pending:
            return
        self._turn_scroll_pending = True
        self._flush_turn_bottom_scroll()

    def _flush_turn_bottom_scroll(self) -> None:
        """Scroll to the turn anchor after user + assistant bubbles are laid out."""
        self._messages.updateGeometry()
        self._scroll.updateGeometry()
        for _ in range(2):
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        # mapTo-based spacer height needs settled bubble geometry (see _streaming_turn_extent_px).
        self._apply_streaming_viewport_spacer()
        self._messages.updateGeometry()
        self._scroll.updateGeometry()
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        bar = self._scroll.verticalScrollBar()
        target = self._stream_follow_target()
        self._set_bar_value(bar, target)
        if self._turn_scroll_anchor is not None:
            anchor_top = self._widget_top_in_viewport(self._turn_scroll_anchor)
            if anchor_top < 0 or anchor_top > _TURN_SCROLL_MARGIN_PX + 6:
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
                self._apply_streaming_viewport_spacer()
                self._messages.updateGeometry()
                self._scroll.updateGeometry()
                target = self._stream_follow_target()
                self._set_bar_value(bar, target)
        if self._turn_scroll_anchor is not None and target == 0 and bar.maximum() > 100:
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            target = self._stream_follow_target()
            self._set_bar_value(bar, target)
        self._turn_scroll_pending = False
        self._reconcile_streaming_viewport_overflow()
        self._clamp_messages_to_viewport_width()
        self._invalidate_sticky_extents()
        self._sync_sticky_turn_prompt()
        self._reconcile_short_turn_spacer_after_layout(self._short_turn_spacer_reconcile_generation)
        self._reconcile_streaming_viewport_overflow()

    def _schedule_short_turn_spacer_reconcile(self) -> None:
        """Re-trim the viewport spacer after a deferred layout pass settles."""
        if self._open_stream_generation == 0 and self._streaming_viewport_spacer is None:
            return
        self._short_turn_spacer_reconcile_generation += 1
        generation = self._short_turn_spacer_reconcile_generation
        QTimer.singleShot(0, lambda g=generation: self._reconcile_short_turn_spacer_after_layout(g))

    def _reconcile_short_turn_spacer_after_layout(self, generation: int | None = None) -> None:
        """Refresh spacer height once row geometry catches up with turn scroll."""
        if generation is not None and generation != self._short_turn_spacer_reconcile_generation:
            return
        if not isValid(self._scroll):
            return
        if self._streaming_viewport_spacer is None and self._open_stream_generation == 0:
            return
        self._apply_streaming_viewport_spacer()
        self._reconcile_streaming_viewport_overflow()
        self._clamp_messages_to_viewport_width()

    def _widget_top_in_viewport(self, widget: QWidget) -> int:
        """Return *widget* top edge Y in viewport coordinates (scroll-offset aware)."""
        y_messages = map_widget_y_to_ancestor(widget, self._messages)
        if y_messages is None:
            return 0
        return y_messages - self._scroll.verticalScrollBar().value()

    def _widget_bottom_in_viewport(self, widget: QWidget) -> int:
        """Return *widget* bottom edge Y in viewport coordinates."""
        top = self._widget_top_in_viewport(widget)
        return top + widget.height()

    def _assistant_bubble_for_turn(self, anchor: ChatMessageBubble) -> ChatMessageBubble | None:
        """Return the assistant row for the turn anchored by *anchor*."""
        found_anchor = False
        for index in range(self._messages_layout.count()):
            item = self._messages_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is anchor:
                found_anchor = True
                continue
            if (
                found_anchor
                and isinstance(widget, ChatMessageBubble)
                and widget.role == "assistant"
            ):
                return widget
        return None

    def _iter_chat_turns(self) -> Iterator[tuple[ChatMessageBubble, ChatMessageBubble]]:
        """Yield ``(user, assistant)`` pairs in transcript layout order."""
        pending_user: ChatMessageBubble | None = None
        for index in range(self._messages_layout.count()):
            item = self._messages_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if not isinstance(widget, ChatMessageBubble):
                continue
            if widget.role == "user":
                pending_user = widget
            elif widget.role == "assistant" and pending_user is not None:
                yield pending_user, widget
                pending_user = None

    def _on_scrollbar_slider_released(self) -> None:
        """Run transcript paging when the user finishes dragging the scrollbar."""
        if self._programmatic_scroll:
            return
        timer = getattr(self, "_virtual_pass_timer", None)
        if timer is not None:
            timer.stop()
        if hasattr(self, "_run_virtual_transcript_pass"):
            self._run_virtual_transcript_pass()

    def _on_scrollbar_slider_pressed(self) -> None:
        """Detach streaming follow when the user grabs the scrollbar."""
        if self._programmatic_scroll:
            return
        self._detach_stream_follow_for_user_scroll()

    def _on_scrollbar_value_changed(self, value: int) -> None:
        """Update scroll-lock from user-driven scrollbar movement."""
        if self._programmatic_scroll:
            return
        bar = self._scroll.verticalScrollBar()
        previous = self._last_scroll_value
        self._last_scroll_value = value
        at_bottom = value >= bar.maximum() - _FOLLOW_THRESHOLD_PX
        if self._open_stream_generation > 0:
            if value < previous:
                clamped_by_range_shrink = previous > bar.maximum()
                if clamped_by_range_shrink:
                    self._scroll_range_shrunk_recent = False
                else:
                    self._scroll_range_shrunk_recent = False
                    self._scroll_lock_enabled = False
                    self._stream_thinking_bottom_follow = False
            elif at_bottom:
                self._scroll_lock_enabled = True
                if not self._stream_content_started:
                    self._stream_thinking_bottom_follow = True
        else:
            self._scroll_lock_enabled = at_bottom
        self._update_scroll_down_button_visibility()
        self._schedule_sticky_sync()
        if hasattr(self, "on_transcript_scroll_activity"):
            self.on_transcript_scroll_activity()

    def _stream_follow_target(self) -> int:
        """Return the scroll offset to follow while streaming with lock on."""
        bar = self._scroll.verticalScrollBar()
        if self._turn_scroll_anchor is None or self._open_stream_generation == 0:
            return bar.maximum()
        if not self._stream_content_started and self._stream_thinking_bottom_follow:
            return bar.maximum()
        viewport_h = self._scroll.viewport().height()
        extent = self._streaming_turn_extent_px()
        if viewport_h > 0 and extent >= viewport_h:
            return bar.maximum()
        return min(bar.maximum(), self._scroll_value_for_turn_start())

    def _on_scrollbar_range_changed(self, _min: int, _max_val: int) -> None:
        """Follow bottom on content growth while streaming and scroll-lock is on."""
        if self._programmatic_scroll:
            return
        prev_max = self._last_scroll_maximum
        if _max_val < prev_max:
            self._scroll_range_shrunk_recent = True
        self._last_scroll_maximum = _max_val
        if self._turn_scroll_pending:
            return
        if (
            getattr(self, "is_transcript_load_active", lambda: False)()
            and self._scroll_lock_enabled
        ):
            self._pin_transcript_to_bottom()
            return
        if getattr(self, "_pending_transcript_bottom_scroll", False) and self._scroll_lock_enabled:
            self._pin_transcript_to_bottom()
            return
        if self._open_stream_generation > 0 and self._scroll_lock_enabled:
            self._queue_stream_follow_passes()
        self._schedule_sticky_sync()

    def _queue_stream_follow_passes(self) -> None:
        """Schedule one coalesced frame follow pass (no synchronous scroll)."""
        if self._open_stream_generation == 0 or not self._scroll_lock_enabled:
            return
        self._stream_follow_dirty = True
        if not self._stream_follow_frame_pending:
            self._stream_follow_frame_pending = True
            QTimer.singleShot(0, self._flush_stream_follow_frame)

    def _flush_stream_follow_frame(self) -> None:
        """Apply one frame-deferred follow pass after layout settles."""
        self._stream_follow_frame_pending = False
        if not isValid(self._scroll):
            self._stream_follow_dirty = False
            return
        if self._open_stream_generation == 0 or not self._scroll_lock_enabled:
            self._stream_follow_dirty = False
            return
        if not self._stream_follow_dirty:
            return
        bar = self._scroll.verticalScrollBar()
        max_before = bar.maximum()
        self._apply_stream_follow()
        self._stream_follow_dirty = False
        target = self._stream_follow_target()
        still_off_target = abs(bar.value() - target) > _FOLLOW_THRESHOLD_PX
        range_grew = bar.maximum() > max_before
        if (still_off_target or range_grew) and not self._stream_follow_retry_pending:
            self._stream_follow_retry_pending = True
            QTimer.singleShot(16, self._flush_stream_follow_retry)
        if not (not self._stream_content_started and self._stream_thinking_bottom_follow):
            self._reconcile_short_turn_height_when_fits()

    def _flush_stream_follow_retry(self) -> None:
        """Apply one late follow pass when range or height grew after the frame pass."""
        self._stream_follow_retry_pending = False
        if not isValid(self._scroll):
            return
        if self._open_stream_generation == 0 or not self._scroll_lock_enabled:
            return
        self._apply_stream_follow()
        if not (not self._stream_content_started and self._stream_thinking_bottom_follow):
            self._reconcile_short_turn_height_when_fits()

    def _apply_stream_follow(self) -> None:
        """Pin the viewport to the active stream follow target (synchronous)."""
        if not isValid(self._scroll):
            return
        if self._open_stream_generation == 0 or not self._scroll_lock_enabled:
            return
        bar = self._scroll.verticalScrollBar()
        target = self._stream_follow_target()
        if not self._stream_content_started and self._stream_thinking_bottom_follow:
            target = max(target, bar.value())
        if abs(bar.value() - target) <= _FOLLOW_THRESHOLD_PX:
            return
        self._set_bar_value(bar, target)
        self._sync_sticky_turn_prompt()

    def _follow_streaming_turn_layout(self) -> None:
        """Refresh spacer height and scroll after in-turn layout shrink or growth."""
        if self._open_stream_generation == 0 or not self._scroll_lock_enabled:
            return
        if not self._stream_content_started and self._stream_thinking_bottom_follow:
            self._queue_stream_follow_passes()
            return
        anchor = self._turn_scroll_anchor
        anchor_vp_before = self._widget_top_in_viewport(anchor) if anchor is not None else 0
        self._apply_streaming_viewport_spacer()
        self._messages.updateGeometry()
        self._scroll.updateGeometry()
        self._reconcile_streaming_viewport_overflow()
        self._apply_stream_follow()
        if anchor is not None and getattr(self, "_stream_content_started", False):
            anchor_vp_after = self._widget_top_in_viewport(anchor)
            delta = anchor_vp_after - anchor_vp_before
            if abs(delta) > _FOLLOW_THRESHOLD_PX:
                bar = self._scroll.verticalScrollBar()
                self._set_bar_value(
                    bar,
                    max(bar.minimum(), min(bar.maximum(), bar.value() + delta)),
                )
        self._queue_stream_follow_passes()
        self._reconcile_short_turn_height_when_fits()

    def _scroll_to_bottom(self, *, force: bool = False) -> None:
        """Scroll the transcript to the bottom (forced paths only)."""
        if not force:
            return
        bar = self._scroll.verticalScrollBar()
        self._set_bar_value(bar, bar.maximum())
        self._arm_scroll_lock()
        self._sync_sticky_turn_prompt()

    def _pin_transcript_to_bottom(self) -> None:
        """Scroll to the current transcript bottom after layout updates."""
        self._messages.updateGeometry()
        self._scroll.updateGeometry()
        self._scroll_to_bottom(force=True)

    def _scroll_to_bottom_settled(self) -> None:
        """Scroll to the transcript bottom after layout and lazy markdown settle."""
        self._messages.updateGeometry()
        self._scroll.updateGeometry()
        if self._is_pinned_to_bottom() and not self._has_visible_deferred_markdown():
            self._sync_sticky_turn_prompt()
            return
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        self._render_visible_lazy_markdown(force=True)
        self._messages.updateGeometry()
        self._scroll.updateGeometry()
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        bar = self._scroll.verticalScrollBar()
        max_before = bar.maximum()
        self._set_bar_value(bar, bar.maximum())
        self._arm_scroll_lock()
        self._messages.updateGeometry()
        self._scroll.updateGeometry()
        if bar.maximum() > max_before:
            self._set_bar_value(bar, bar.maximum())
        self._sync_sticky_turn_prompt()

    def _has_visible_deferred_markdown(self) -> bool:
        """Return whether any visible assistant body still has deferred markdown."""
        for index in range(self._messages_layout.count()):
            item = self._messages_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if not isinstance(widget, ChatMessageBubble) or widget.role != "assistant":
                continue
            body = widget._markdown_body
            if body is None or not body.is_render_deferred():
                continue
            if self.markdown_body_intersects_viewport(body):
                return True
        return False

    def _scroll_to_turn_start(self, *, force: bool = False) -> None:
        """Scroll the transcript to the active turn anchor (forced paths only)."""
        if not force:
            return
        bar = self._scroll.verticalScrollBar()
        self._set_bar_value(bar, self._scroll_value_for_turn_start())
        self._arm_scroll_lock()
        self._sync_sticky_turn_prompt()

    def _completed_turn_assistant(self) -> ChatMessageBubble | None:
        """Return the assistant row paired with the active turn anchor."""
        anchor = self._turn_scroll_anchor
        if anchor is None:
            return None
        return self._assistant_bubble_for_turn(anchor)

    def _is_short_turn_extent(self, assistant: ChatMessageBubble) -> bool:
        """Return whether *assistant* and its user anchor fit within one viewport."""
        viewport_h = self._scroll.viewport().height()
        if viewport_h <= 0:
            return False
        extent = self._streaming_turn_extent_px(assistant)
        return extent > 0 and extent < viewport_h

    def _reconcile_completed_turn_viewport_spacer(
        self,
        assistant: ChatMessageBubble | None = None,
    ) -> bool:
        """Refresh or remove the completed-turn spacer after late layout growth."""
        if self._open_stream_generation > 0:
            return False
        bubble = assistant if assistant is not None else self._completed_turn_assistant()
        if bubble is None or self._turn_scroll_anchor is None:
            self._clear_streaming_viewport_spacer()
            return False
        if self._is_short_turn_extent(bubble):
            self._apply_streaming_viewport_spacer(bubble)
            return True
        self._clear_streaming_viewport_spacer()
        return False

    def _settle_completed_short_turn_scroll(
        self,
        assistant: ChatMessageBubble | None = None,
    ) -> bool:
        """Recompute the completed-turn spacer and re-anchor short turns after layout."""
        self._messages.updateGeometry()
        self._scroll.updateGeometry()
        for _ in range(2):
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        short_turn = self._reconcile_completed_turn_viewport_spacer(assistant)
        self._messages.updateGeometry()
        self._scroll.updateGeometry()
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        if short_turn:
            self._trim_completed_turn_spacer_overflow()
            self._reconcile_short_turn_transcript_height()
        self._messages.updateGeometry()
        self._scroll.updateGeometry()
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        if short_turn and self._scroll_lock_enabled:
            bar = self._scroll.verticalScrollBar()
            self._set_bar_value(bar, self._scroll_value_for_turn_start())
            self._arm_scroll_lock()
        self._sync_sticky_turn_prompt()
        if short_turn:
            self._reconcile_short_turn_transcript_height()
        return short_turn

    def _max_transcript_min_height_px(self) -> int:
        """Return the largest allowed ``_messages`` minimum height for the viewport."""
        viewport_h = self._scroll.viewport().height()
        if viewport_h <= 0:
            return 0
        return viewport_h + self._turn_scroll_headroom_px()

    def _reconcile_short_turn_transcript_height(self) -> None:
        """Clamp tiny short-turn layout slack without persisting into later turns."""
        bubble = self._streaming_bubble or self._completed_turn_assistant()
        viewport_h = self._scroll.viewport().height()
        if (
            bubble is not None
            and isValid(bubble)
            and viewport_h > 0
            and self._is_short_turn_extent(bubble)
        ):
            self._messages_layout.activate()
            overflow = self._messages.minimumSizeHint().height() - viewport_h
            layout = self._messages_layout
            spacing = layout.spacing() if layout is not None else 0
            slack = spacing + _TURN_SCROLL_MARGIN_PX
            bar = self._scroll.verticalScrollBar()
            if overflow <= slack or bar.maximum() <= slack:
                self._messages_layout.setSizeConstraints(
                    QLayout.SizeConstraint.SetNoConstraint,
                    QLayout.SizeConstraint.SetFixedSize,
                )
                self._messages.setFixedHeight(viewport_h)
                self._messages.setMinimumHeight(viewport_h)
                self._messages.setMaximumHeight(viewport_h)
                self._messages.updateGeometry()
                self._scroll.updateGeometry()
                if self._turn_scroll_headroom_px() <= 0:
                    bar.setRange(0, 0)
                self._clamp_messages_to_viewport_width()
                return
        self._restore_messages_auto_height()
        self._clamp_messages_to_viewport_width()

    def _restore_messages_auto_height(self) -> None:
        """Return the transcript host to normal scroll-area managed height."""
        self._messages_layout.setSizeConstraints(
            QLayout.SizeConstraint.SetNoConstraint,
            QLayout.SizeConstraint.SetMinAndMaxSize,
        )
        self._messages.setMinimumHeight(0)
        self._messages.setMaximumHeight(16777215)
        self._messages.updateGeometry()
        self._scroll.updateGeometry()

    def _reconcile_short_turn_height_when_fits(self) -> None:
        """Clamp transcript height when a short turn only has layout slack overflow."""
        bubble = self._streaming_bubble
        if bubble is None or not self._is_short_turn_extent(bubble):
            return
        viewport_h = self._scroll.viewport().height()
        if viewport_h <= 0:
            return
        self._messages_layout.activate()
        overflow = self._messages.minimumSizeHint().height() - viewport_h
        layout = self._messages_layout
        spacing = layout.spacing() if layout is not None else 0
        slack = spacing + _TURN_SCROLL_MARGIN_PX
        bar = self._scroll.verticalScrollBar()
        if overflow <= slack or bar.maximum() <= slack:
            self._reconcile_short_turn_transcript_height()
            self._clamp_messages_to_viewport_width()

    def _trim_viewport_spacer_overflow(self) -> None:
        """Shrink the viewport spacer when layout minimum exceeds the viewport."""
        spacer = self._streaming_viewport_spacer
        if spacer is None:
            return
        max_min = self._max_transcript_min_height_px()
        if max_min <= 0:
            return
        self._messages_layout.activate()
        overflow = self._messages.minimumSizeHint().height() - max_min
        if overflow <= 0:
            return
        if overflow > spacer.height():
            if spacer.height() > 0:
                spacer.setFixedHeight(0)
                self._messages.adjustSize()
                self._messages.updateGeometry()
                self._scroll.updateGeometry()
                return
            self._apply_streaming_viewport_spacer()
            return
        spacer.setFixedHeight(spacer.height() - overflow)
        self._messages.adjustSize()
        self._messages.updateGeometry()
        self._scroll.updateGeometry()

    def _reconcile_streaming_viewport_overflow(self) -> None:
        """Shrink the viewport spacer until the transcript fits one viewport."""
        for _ in range(4):
            before = (
                self._streaming_viewport_spacer.height() if self._streaming_viewport_spacer else 0
            )
            self._trim_viewport_spacer_overflow()
            if self._streaming_viewport_spacer is None:
                self._reconcile_short_turn_transcript_height()
                return
            if self._streaming_viewport_spacer.height() == before:
                break
            max_min = self._max_transcript_min_height_px()
            if self._messages.minimumSizeHint().height() <= max_min:
                break
        self._reconcile_short_turn_transcript_height()
        bubble = self._streaming_bubble or self._completed_turn_assistant()
        if bubble is not None and self._is_short_turn_extent(bubble):
            layout = self._messages_layout
            spacing = layout.spacing() if layout is not None else 0
            slack = spacing + _TURN_SCROLL_MARGIN_PX
            bar = self._scroll.verticalScrollBar()
            if 0 < bar.maximum() <= slack:
                self._reconcile_short_turn_transcript_height()

    def _trim_completed_turn_spacer_overflow(self) -> None:
        """Shrink the retained short-turn spacer when layout minimum exceeds the viewport."""
        self._trim_viewport_spacer_overflow()

    def _apply_streaming_viewport_spacer(
        self,
        assistant: ChatMessageBubble | None = None,
    ) -> None:
        """Reserve space so the turn anchor can sit at the viewport top while streaming."""
        viewport_h = self._scroll.viewport().height()
        if viewport_h <= 0:
            return
        bar = self._scroll.verticalScrollBar()
        preserve_anchor = (
            self._open_stream_generation > 0
            and self._scroll_lock_enabled
            and self._turn_scroll_anchor is not None
        )
        blocker: QSignalBlocker | None = None
        old_programmatic = self._programmatic_scroll
        if preserve_anchor:
            self._smooth_scroller.cancel(sync_value=bar.value())
            self._programmatic_scroll = True
            blocker = QSignalBlocker(bar)
        try:
            self._apply_streaming_viewport_spacer_unblocked(assistant, viewport_h)
        finally:
            if blocker is not None:
                if self._open_stream_generation > 0 and self._scroll_lock_enabled:
                    target = self._stream_follow_target()
                    bar.setValue(target)
                    self._last_scroll_value = bar.value()
                self._programmatic_scroll = old_programmatic
                del blocker

    def _apply_streaming_viewport_spacer_unblocked(
        self,
        assistant: ChatMessageBubble | None,
        viewport_h: int,
    ) -> None:
        """Apply streaming spacer geometry within the caller's scroll transaction."""
        bubble = assistant if assistant is not None else self._streaming_bubble
        if self._turn_scroll_anchor is None or bubble is None:
            self._clear_streaming_viewport_spacer()
            return
        self._sync_messages_top_stretch()
        extent = self._streaming_turn_extent_px(bubble)
        turn_bottom = self._turn_bottom_y_in_messages(bubble)
        if extent <= 0 or turn_bottom is None:
            if self._streaming_viewport_spacer is not None and self._open_stream_generation > 0:
                return
            self._clear_streaming_viewport_spacer()
            return
        if extent >= viewport_h:
            self._clear_streaming_viewport_spacer()
            return
        target_h = self._target_streaming_spacer_height(bubble)
        if target_h <= 2:
            self._clear_streaming_viewport_spacer()
            self._reconcile_short_turn_transcript_height()
            return
        if self._streaming_viewport_spacer is not None:
            current_h = self._streaming_viewport_spacer.height()
            exact_active_stream = self._open_stream_generation > 0 and self._scroll_lock_enabled
            if (
                exact_active_stream is False
                and self._open_stream_generation > 0
                and abs(target_h - current_h) < _STREAMING_SPACER_MIN_DELTA_PX
            ):
                self._reconcile_streaming_viewport_overflow()
                return
        if self._streaming_viewport_spacer is None:
            spacer = QWidget(self._messages)
            spacer.setObjectName("aiChatStreamingViewportSpacer")
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            spacer.setFixedHeight(target_h)
            insert_index = self._ensure_messages_bottom_stretch()
            self._messages_layout.insertWidget(insert_index, spacer)
            self._streaming_viewport_spacer = spacer
            self._messages_bottom_stretch_index = -1
            if self._use_turn_anchor_layout():
                self._set_messages_bottom_stretch_factor(1)
        else:
            self._streaming_viewport_spacer.setFixedHeight(target_h)
        self._reconcile_streaming_viewport_overflow()

    def _clear_streaming_viewport_spacer(self) -> None:
        """Remove the streaming viewport spacer from the transcript layout."""
        spacer = self._streaming_viewport_spacer
        if spacer is None:
            if self._open_stream_generation == 0:
                self._restore_messages_auto_height()
            self._sync_messages_top_stretch()
            return
        self._messages_layout.removeWidget(spacer)
        spacer.setParent(None)
        spacer.deleteLater()
        self._streaming_viewport_spacer = None
        if self._open_stream_generation == 0:
            self._restore_messages_auto_height()
        self._sync_messages_top_stretch()

    def _update_scroll_down_button_visibility(self) -> None:
        """Show the scroll-down affordance when the user has scrolled away."""
        if self._open_stream_generation > 0 and self._scroll_lock_enabled:
            self._scroll_down_btn.hide()
            return
        show = not self._scroll_lock_enabled and not self._is_pinned_to_bottom()
        self._scroll_down_btn.setVisible(show)
        if show:
            self._reposition_scroll_down_button()

    def _reposition_scroll_down_button(self) -> None:
        """Place the scroll-down button at the bottom-right of the transcript viewport."""
        viewport = self._scroll.viewport()
        btn = self._scroll_down_btn
        margin = 12
        btn.adjustSize()
        x = max(margin, viewport.width() - btn.width() - margin)
        y = max(margin, viewport.height() - btn.height() - margin)
        btn.move(x, y)
        if btn.isVisible():
            btn.raise_()

    def is_resize_coalescing(self) -> bool:
        """Return whether continuous pane resize is deferring heavy transcript reflow."""
        return self._resize_active

    def _mark_resize_active(self) -> None:
        """Mark an active resize drag so markdown/sticky work can coalesce."""
        self._resize_active = True

    def _schedule_resize_settle(self) -> None:
        """Restart the settle timer after another resize step during a drag."""
        self._resize_settle_due_generation = self._resize_settle_generation
        self._resize_settle_timer.start(_RESIZE_SETTLE_MS)

    def _bubble_intersects_viewport(self, bubble: ChatMessageBubble) -> bool:
        """Return whether *bubble* overlaps the transcript viewport."""
        bar = self._scroll.verticalScrollBar()
        vp_top = bar.value()
        vp_bottom = vp_top + self._scroll.viewport().height()
        top = map_widget_y_to_ancestor(bubble, self._messages)
        if top is None:
            return False
        bottom = top + bubble.height()
        return bottom > vp_top and top < vp_bottom

    def _compensate_scroll_for_messages_growth(
        self,
        bubble: ChatMessageBubble,
        _anchor_messages_y: int,
        delta_px: int,
    ) -> None:
        """Keep on-screen content stable when a visible row grows."""
        if delta_px == 0 or not isValid(self._scroll):
            return
        if not self._bubble_intersects_viewport(bubble):
            return
        bar = self._scroll.verticalScrollBar()
        scroll_val = bar.value()
        self._set_bar_value(
            bar,
            max(bar.minimum(), min(bar.maximum(), scroll_val + delta_px)),
        )

    def _apply_visible_rows_reflow_during_resize(self) -> None:
        """Enter resize coalescing without walking every transcript row."""
        self._prepare_panel_resize_coalescing()

    def _prepare_panel_resize_coalescing(self) -> None:
        """Mark resize active before child resize events reach transcript rows."""
        self._resize_settle_timer.stop()
        self._resize_settle_generation += 1
        self._mark_resize_active()

    def _reconcile_visible_rows_after_resize(self) -> None:
        """No-op hook kept for tests and future viewport-specific policy."""

    def _finish_panel_resize_coalescing(self) -> None:
        """Run cheap resize follow-ups and schedule the settle flush."""
        if self._open_stream_generation > 0 and self._streaming_bubble is not None:
            self._apply_streaming_viewport_spacer()
            self._reflow_streaming_bubble_during_resize()
        self._invalidate_sticky_extents()
        self._reposition_scroll_down_button()
        self._schedule_resize_settle()

    def _reflow_streaming_bubble_during_resize(self) -> None:
        """Keep the active streaming assistant row height accurate during pane resize."""
        bubble = self._streaming_bubble
        if bubble is None:
            return
        bubble.set_reflow_deferred(False)
        body = bubble._markdown_body
        if body is not None:
            body.flush_deferred_reflow()
            body._sync_height()

    def _on_resize_settle_timer_fired(self) -> None:
        """Ignore stale settle timers superseded by a newer resize step."""
        if self._resize_settle_due_generation != self._resize_settle_generation:
            return
        self._on_resize_settled()

    def _on_resize_settled(self) -> None:
        """Flush deferred row reflow and sticky sync after resize input quiets."""
        self._resize_active = False
        self._scroll.setUpdatesEnabled(False)
        try:
            for index in range(self._messages_layout.count()):
                item = self._messages_layout.itemAt(index)
                widget = item.widget() if item is not None else None
                if isinstance(widget, ChatMessageBubble):
                    widget.flush_deferred_reflow()
            self._messages.updateGeometry()
            self._scroll.updateGeometry()
        finally:
            self._scroll.setUpdatesEnabled(True)
        if self._sticky_sync_deferred_during_resize:
            self._sticky_sync_deferred_during_resize = False
        self._schedule_sticky_sync()

    def markdown_body_intersects_viewport(self, body: QWidget) -> bool:
        """Return whether *body* intersects the transcript scroll viewport."""
        viewport = self._scroll.viewport()
        top_left = map_widget_point_to_ancestor(body, viewport, QPoint(0, 0))
        if top_left is None:
            return False
        bottom_y = top_left.y() + body.height()
        return bottom_y > 0 and top_left.y() < viewport.height()

    def _on_transcript_scroll_for_lazy_markdown(self, _value: int) -> None:
        """Render deferred markdown for rows that scroll into view."""
        if getattr(self, "_transcript_loading_visible", False):
            return
        self._render_visible_lazy_markdown()

    def _render_visible_lazy_markdown(self, *, force: bool = False) -> None:
        """Materialise lazy assistant bodies currently visible in the viewport."""
        if not force and getattr(self, "_transcript_loading_visible", False):
            return
        for index in range(self._messages_layout.count()):
            item = self._messages_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if not isinstance(widget, ChatMessageBubble) or widget.role != "assistant":
                continue
            body = widget._markdown_body
            if body is None or not body.is_render_deferred():
                continue
            if self.markdown_body_intersects_viewport(body):
                body.ensure_rendered()
                if widget.is_turn_complete():
                    widget._sync_assistant_footer_visibility()
