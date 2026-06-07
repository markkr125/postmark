"""Sticky auto-scroll helpers for the AI chat transcript."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from PySide6.QtCore import QEventLoop, QPoint, QSignalBlocker, QTimer
from shiboken6 import isValid
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QSizePolicy,
    QWidget,
)

from ui.sidebar.ai.chat_panel.sticky_prompt import _ChatPanelStickyPromptMixin
from ui.sidebar.ai.message_bubble import ChatMessageBubble

_FOLLOW_THRESHOLD_PX = 2
_TURN_SCROLL_MARGIN_PX = 8


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
    _streaming_bubble: ChatMessageBubble | None = None

    def _init_scroll_controller(self) -> None:
        """Connect scrollbar signals for scroll-lock follow (call from panel ``__init__``)."""
        bar = self._scroll.verticalScrollBar()
        self._last_scroll_value = bar.value()
        self._last_scroll_maximum = bar.maximum()
        bar.valueChanged.connect(self._on_scrollbar_value_changed)
        bar.rangeChanged.connect(self._on_scrollbar_range_changed)

    def _set_bar_value(self, bar: QScrollBar, value: int) -> None:
        """Programmatically set scrollbar value without updating scroll-lock state."""
        self._programmatic_scroll = True
        try:
            with QSignalBlocker(bar):
                bar.setValue(value)
            self._last_scroll_value = value
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
        y = anchor.mapTo(self._messages, QPoint(0, 0)).y()
        return max(0, min(y - _TURN_SCROLL_MARGIN_PX, bar.maximum()))

    def _streaming_turn_extent_px(self) -> int:
        """Return height from the turn anchor top to the bottom of the assistant row."""
        anchor = self._turn_scroll_anchor
        bubble = self._streaming_bubble
        if anchor is None or bubble is None:
            return 0
        top = anchor.mapTo(self._messages, QPoint(0, 0)).y()
        bottom = bubble.mapTo(self._messages, QPoint(0, bubble.height())).y()
        return max(0, bottom - top)

    def _request_turn_bottom_scroll(self) -> None:
        """Schedule a single coalesced scroll to the start of a new user turn."""
        self._arm_scroll_lock()
        if self._turn_scroll_pending:
            return
        self._turn_scroll_pending = True
        QTimer.singleShot(0, self._flush_turn_bottom_scroll)

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
        target = self._scroll_value_for_turn_start()
        self._set_bar_value(bar, target)
        if self._turn_scroll_anchor is not None and target == 0 and bar.maximum() > 100:
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            target = self._scroll_value_for_turn_start()
            self._set_bar_value(bar, target)
        self._turn_scroll_pending = False
        self._invalidate_sticky_extents()
        self._sync_sticky_turn_prompt()

    def _widget_top_in_viewport(self, widget: QWidget) -> int:
        """Return *widget* top edge Y in viewport coordinates (scroll-offset aware)."""
        y_messages = widget.mapTo(self._messages, QPoint(0, 0)).y()
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
                if clamped_by_range_shrink or self._scroll_range_shrunk_recent:
                    self._scroll_range_shrunk_recent = False
                else:
                    self._scroll_lock_enabled = False
            elif at_bottom:
                self._scroll_lock_enabled = True
        else:
            self._scroll_lock_enabled = at_bottom
        self._update_scroll_down_button_visibility()
        self._schedule_sticky_sync()

    def _stream_follow_target(self) -> int:
        """Return the scroll offset to follow while streaming with lock on."""
        bar = self._scroll.verticalScrollBar()
        viewport_h = self._scroll.viewport().height()
        if viewport_h > 0 and self._streaming_turn_extent_px() < viewport_h:
            return min(bar.maximum(), self._scroll_value_for_turn_start())
        return bar.maximum()

    def _on_scrollbar_range_changed(self, _min: int, _max_val: int) -> None:
        """Follow bottom on content growth while streaming and scroll-lock is on."""
        if self._programmatic_scroll:
            return
        if _max_val < self._last_scroll_maximum:
            self._scroll_range_shrunk_recent = True
        self._last_scroll_maximum = _max_val
        if self._turn_scroll_pending:
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

    def _flush_stream_follow_retry(self) -> None:
        """Apply one late follow pass when range or height grew after the frame pass."""
        self._stream_follow_retry_pending = False
        if not isValid(self._scroll):
            return
        if self._open_stream_generation == 0 or not self._scroll_lock_enabled:
            return
        self._apply_stream_follow()

    def _apply_stream_follow(self) -> None:
        """Pin the viewport to the active stream follow target (synchronous)."""
        if not isValid(self._scroll):
            return
        if self._open_stream_generation == 0 or not self._scroll_lock_enabled:
            return
        bar = self._scroll.verticalScrollBar()
        target = self._stream_follow_target()
        if abs(bar.value() - target) <= _FOLLOW_THRESHOLD_PX:
            return
        self._set_bar_value(bar, target)
        self._sync_sticky_turn_prompt()

    def _scroll_to_bottom(self, *, force: bool = False) -> None:
        """Scroll the transcript to the bottom (forced paths only)."""
        if not force:
            return
        bar = self._scroll.verticalScrollBar()
        self._set_bar_value(bar, bar.maximum())
        self._arm_scroll_lock()
        self._sync_sticky_turn_prompt()

    def _scroll_to_turn_start(self, *, force: bool = False) -> None:
        """Scroll the transcript to the active turn anchor (forced paths only)."""
        if not force:
            return
        bar = self._scroll.verticalScrollBar()
        self._set_bar_value(bar, self._scroll_value_for_turn_start())
        self._arm_scroll_lock()
        self._sync_sticky_turn_prompt()

    def _apply_streaming_viewport_spacer(self) -> None:
        """Reserve space so the turn anchor can sit at the viewport top while streaming."""
        viewport_h = self._scroll.viewport().height()
        if viewport_h <= 0:
            return
        target_h = max(0, viewport_h - self._streaming_turn_extent_px())
        if self._streaming_viewport_spacer is None:
            spacer = QWidget(self._messages)
            spacer.setObjectName("aiChatStreamingViewportSpacer")
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            spacer.setFixedHeight(target_h)
            self._messages_layout.addWidget(spacer)
            self._streaming_viewport_spacer = spacer
        else:
            self._streaming_viewport_spacer.setFixedHeight(target_h)

    def _clear_streaming_viewport_spacer(self) -> None:
        """Remove the streaming viewport spacer from the transcript layout."""
        spacer = self._streaming_viewport_spacer
        if spacer is None:
            return
        self._messages_layout.removeWidget(spacer)
        spacer.setParent(None)
        spacer.deleteLater()
        self._streaming_viewport_spacer = None

    def _update_scroll_down_button_visibility(self) -> None:
        """Show the scroll-down affordance when the user has scrolled away."""
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
