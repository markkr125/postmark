"""Sticky user-prompt overlay for the AI chat transcript viewport."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any, NamedTuple

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QPushButton, QScrollArea, QWidget
from shiboken6 import isValid

from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.user_message.overlay import (
    StickyOverlayMetrics,
    StickyUserPromptOverlay,
)

_STICKY_PROMPT_TOP_PX = 0
_STICKY_PROMPT_COLLAPSED_VIEWPORT_RATIO = 0.35
_STICKY_PROMPT_EXPANDED_VIEWPORT_RATIO = 0.6
_STICKY_PROMPT_MARGIN_PX = 4
_STICKY_PROMPT_HYSTERESIS_PX = 4
_STICKY_PROMPT_VIEWPORT_INSET_PX = 3
_STICKY_PROMPT_LEFT_SHIFT_PX = 4
_MIN_STICKY_HEIGHT_ESTIMATE_PX = 48


class StickyTurnExtent(NamedTuple):
    """Scroll-independent Y extents for one user/assistant turn pair."""

    user: ChatMessageBubble | None
    assistant: ChatMessageBubble
    user_top_messages: int
    user_bottom_messages: int
    assistant_top_messages: int
    assistant_bottom_messages: int
    prompt_text: str
    sent_at: datetime | None


class _ChatPanelStickyPromptMixin:  # type: ignore[misc]
    """Cached turn selection and viewport overlay for the sticky user prompt."""

    _scroll: QScrollArea
    _messages: QWidget
    _messages_layout: Any = None
    _scroll_down_btn: QPushButton
    _sticky_turn_anchor: ChatMessageBubble | None = None
    _sticky_turn_prompt: StickyUserPromptOverlay | None = None
    _sticky_turn_pairs: list[tuple[ChatMessageBubble, ChatMessageBubble]]
    _sticky_turn_pairs_dirty: bool = True
    _sticky_turn_extents: list[StickyTurnExtent]
    _sticky_extent_by_assistant: dict[int, StickyTurnExtent]
    _sticky_extents_dirty: bool = True
    _sticky_applied_anchor: ChatMessageBubble | None = None
    _sticky_applied_assistant_id: int | None = None
    _sticky_applied_prompt_text: str = ""
    _sticky_applied_visible: bool = False
    _sticky_applied_geom: tuple[int, int, int, int] = (0, 0, 0, 0)
    _sticky_applied_height_cap: int = 0
    _sticky_sync_pending: bool = False
    _sticky_sync_frame_pending: bool = False

    def _iter_chat_turns(self) -> Iterator[tuple[ChatMessageBubble, ChatMessageBubble]]:
        """Yield transcript turn pairs (implemented by :class:`_ChatPanelScrollMixin`)."""
        raise NotImplementedError

    def _iter_orphan_sticky_turns(self) -> Iterator[tuple[Any, ChatMessageBubble]]:
        """Yield evicted-user turns (optional; virtualized transcript mixin)."""
        return iter(())

    def _invalidate_sticky_turn_pairs(self) -> None:
        """Mark cached user/assistant turn pairs stale after transcript changes."""
        self._sticky_turn_pairs_dirty = True
        self._sticky_extents_dirty = True

    def _invalidate_sticky_extents(self) -> None:
        """Mark cached layout-space turn extents stale after geometry changes."""
        self._sticky_extents_dirty = True

    def _rebuild_sticky_turn_pairs(self) -> None:
        """Rebuild cached user/assistant turn pairs from the transcript layout."""
        self._sticky_turn_pairs = list(self._iter_chat_turns())
        self._sticky_turn_pairs_dirty = False
        self._sticky_extents_dirty = True

    def _ensure_sticky_turn_pairs(self) -> list[tuple[ChatMessageBubble, ChatMessageBubble]]:
        """Return cached turn pairs, rebuilding them when marked dirty."""
        if self._sticky_turn_pairs_dirty:
            self._rebuild_sticky_turn_pairs()
        return self._sticky_turn_pairs

    def _extent_cache_key(self, extent: StickyTurnExtent) -> int:
        """Return the assistant message id used to cache one turn extent."""
        assistant_id = extent.assistant.message_id
        return id(extent.assistant) if assistant_id is None else assistant_id

    def _rebuild_sticky_turn_extents(self) -> None:
        """Recompute scroll-independent Y extents for every cached turn pair."""
        extents: list[StickyTurnExtent] = []
        extent_by_assistant: dict[int, StickyTurnExtent] = {}
        for user, assistant in self._ensure_sticky_turn_pairs():
            if not isValid(user) or not isValid(assistant):
                continue
            user_top = user.mapTo(self._messages, QPoint(0, 0)).y()
            user_bottom = user.mapTo(self._messages, QPoint(0, user.height())).y()
            assistant_top = assistant.mapTo(self._messages, QPoint(0, 0)).y()
            assistant_bottom = assistant.mapTo(self._messages, QPoint(0, assistant.height())).y()
            extent = StickyTurnExtent(
                user,
                assistant,
                user_top,
                user_bottom,
                assistant_top,
                assistant_bottom,
                user.text(),
                user.sent_at(),
            )
            extents.append(extent)
            extent_by_assistant[self._extent_cache_key(extent)] = extent
        for evicted, assistant in self._iter_orphan_sticky_turns():
            if not isValid(assistant):
                continue
            assistant_top = assistant.mapTo(self._messages, QPoint(0, 0)).y()
            assistant_bottom = assistant.mapTo(self._messages, QPoint(0, assistant.height())).y()
            user_bottom = assistant_top
            user_top = user_bottom - max(1, evicted.height_px)
            extent = StickyTurnExtent(
                None,
                assistant,
                user_top,
                user_bottom,
                assistant_top,
                assistant_bottom,
                evicted.text,
                evicted.sent_at,
            )
            extents.append(extent)
            extent_by_assistant[self._extent_cache_key(extent)] = extent
        self._sticky_turn_extents = extents
        self._sticky_extent_by_assistant = extent_by_assistant
        self._sticky_extents_dirty = False

    def _ensure_sticky_turn_extents(self) -> list[StickyTurnExtent]:
        """Return cached turn extents, rebuilding them when marked dirty."""
        if self._sticky_extents_dirty:
            self._rebuild_sticky_turn_extents()
        return self._sticky_turn_extents

    def _extent_for_assistant(self, assistant: ChatMessageBubble) -> StickyTurnExtent | None:
        """Return cached extents for *assistant*, rebuilding when stale."""
        key = assistant.message_id if assistant.message_id is not None else id(assistant)
        extent = self._sticky_extent_by_assistant.get(key)
        if extent is None:
            self._ensure_sticky_turn_extents()
            extent = self._sticky_extent_by_assistant.get(key)
        return extent

    def _reset_sticky_applied_state(self) -> None:
        """Clear last-applied sticky overlay geometry and visibility."""
        self._sticky_applied_anchor = None
        self._sticky_applied_assistant_id = None
        self._sticky_applied_prompt_text = ""
        self._sticky_applied_visible = False
        self._sticky_applied_geom = (0, 0, 0, 0)
        self._sticky_applied_height_cap = 0

    def _schedule_sticky_sync(self) -> None:
        """Coalesce sticky overlay updates to one pass per event-loop frame."""
        if getattr(self, "_resize_active", False):
            self._sticky_sync_deferred_during_resize = True
            return
        self._sticky_sync_pending = True
        if not self._sticky_sync_frame_pending:
            self._sticky_sync_frame_pending = True
            QTimer.singleShot(0, self._flush_sticky_sync)

    def _flush_sticky_sync(self) -> None:
        """Apply one deferred sticky overlay sync after scroll/layout bursts."""
        self._sticky_sync_frame_pending = False
        if not self._sticky_sync_pending:
            return
        self._sticky_sync_pending = False
        self._sync_sticky_turn_prompt()

    def _sticky_prompt_height_cap(self) -> int:
        """Return the maximum sticky overlay height for the current viewport."""
        viewport_h = self._scroll.viewport().height()
        sticky = self._sticky_turn_prompt
        expanded = sticky is not None and sticky.is_user_message_expanded()
        ratio = (
            _STICKY_PROMPT_EXPANDED_VIEWPORT_RATIO
            if expanded
            else _STICKY_PROMPT_COLLAPSED_VIEWPORT_RATIO
        )
        ratio_cap = int(viewport_h * ratio)
        return max(ratio_cap, min(viewport_h - 16, 120))

    def _assistant_intersects_viewport(self, assistant_top_y: int, assistant_bottom_y: int) -> bool:
        """Return whether the assistant row overlaps the transcript viewport."""
        viewport_h = self._scroll.viewport().height()
        return assistant_bottom_y > 0 and assistant_top_y < viewport_h

    def _user_prompt_visible_near_viewport_top(self, user_top_y: int) -> bool:
        """Return whether the user prompt still sits at the top of the viewport."""
        viewport_h = self._scroll.viewport().height()
        return user_top_y >= -_STICKY_PROMPT_MARGIN_PX and user_top_y < viewport_h

    def _sticky_turn_for_viewport(self, sticky_h_estimate: int) -> StickyTurnExtent | None:
        """Return the newest eligible user/assistant turn for the current viewport."""
        scroll_val = self._scroll.verticalScrollBar().value()
        for extent in reversed(self._ensure_sticky_turn_extents()):
            user_y = extent.user_top_messages - scroll_val
            if self._user_prompt_visible_near_viewport_top(user_y):
                return None
            assistant_top_y = extent.assistant_top_messages - scroll_val
            assistant_bottom_y = extent.assistant_bottom_messages - scroll_val
            if not self._assistant_intersects_viewport(assistant_top_y, assistant_bottom_y):
                continue
            if assistant_bottom_y <= sticky_h_estimate + _STICKY_PROMPT_TOP_PX:
                continue
            return extent
        return None

    def _clear_sticky_turn_prompt(self) -> None:
        """Remove the sticky turn prompt overlay from the viewport."""
        sticky = self._sticky_turn_prompt
        self._sticky_turn_prompt = None
        self._sticky_turn_anchor = None
        self._reset_sticky_applied_state()
        if sticky is None:
            return
        if sticky.hosts_inline_composer():
            released = sticky.release_inline_composer()
            state = getattr(self, "_inline_edit", None)
            if released is not None and state is not None and state.bubble._inline_composer is None:
                state.bubble.reattach_inline_composer(released)
        sticky.setParent(None)
        sticky.deleteLater()

    def _hide_sticky_turn_prompt_overlay(self) -> None:
        """Hide the sticky overlay without destroying it."""
        if self._sticky_turn_prompt is not None:
            self._sticky_turn_prompt.hide()
        self._sticky_turn_anchor = None
        self._reset_sticky_applied_state()

    def _hide_sticky_unless_already_hidden(self) -> None:
        """Hide the sticky overlay only when it is currently applied as visible."""
        if not self._sticky_applied_visible:
            return
        self._hide_sticky_turn_prompt_overlay()

    def _sticky_content_geometry(
        self,
        layout_source: ChatMessageBubble,
        viewport: QWidget,
    ) -> tuple[int, int]:
        """Return ``(x, width)`` filling the transcript content column in the viewport."""
        inset = _STICKY_PROMPT_VIEWPORT_INSET_PX
        anchor_x = layout_source.mapTo(viewport, QPoint(0, 0)).x()
        sticky_x = max(inset, anchor_x - _STICKY_PROMPT_LEFT_SHIFT_PX)
        content_w = max(1, viewport.width() - sticky_x - inset)
        return sticky_x, content_w

    def _sticky_overlay_height(
        self,
        sticky: StickyUserPromptOverlay,
        *,
        anchor: ChatMessageBubble | None,
        content_w: int,
        cap: int,
        available_h: int,
    ) -> tuple[int, StickyOverlayMetrics]:
        """Size the sticky overlay from explicit metrics and apply geometry once."""
        if anchor is not None:
            sticky.sync_expanded_from_anchor(anchor)
        height_cap = min(cap, available_h)
        metrics = sticky.measure_for_width(content_w, height_cap)
        sticky_h = min(metrics.total_height, height_cap)
        metrics = sticky.measure_for_width(content_w, sticky_h)
        sticky.apply_geometry(content_w, sticky_h, metrics)
        return sticky_h, metrics

    def _on_sticky_overlay_expanded_changed(self) -> None:
        """Recompute sticky geometry after Show more/less without touching the transcript."""
        if self._sticky_turn_prompt is None:
            return
        self._reset_sticky_applied_state()
        self._schedule_sticky_sync()

    def _ensure_sticky_turn_prompt(
        self,
        *,
        text: str,
        sent_at: datetime | None,
        anchor: ChatMessageBubble | None,
    ) -> StickyUserPromptOverlay:
        """Create or refresh the read-only sticky overlay for one turn prompt."""
        sticky = self._sticky_turn_prompt
        if sticky is not None and sticky.text() == text and sticky.sent_at() == sent_at:
            self._sticky_turn_anchor = anchor
            if anchor is not None:
                sticky.sync_expanded_from_anchor(anchor)
            return sticky
        self._clear_sticky_turn_prompt()
        self._sticky_turn_anchor = anchor
        viewport = self._scroll.viewport()
        sticky = StickyUserPromptOverlay(parent=viewport)
        sticky._footer.stop_requested.connect(self.stop_requested.emit)  # type: ignore[attr-defined]
        if anchor is not None:
            sticky._footer.set_fork_enabled(anchor.message_id is not None)
            sticky._footer.set_edit_enabled(anchor.message_id is not None and not self._run_busy)  # type: ignore[attr-defined]
            sticky._footer.fork_requested.connect(
                lambda a=anchor: self._fork_sticky_prompt(a)  # type: ignore[attr-defined]
            )
            sticky._footer.edit_requested.connect(
                lambda a=anchor: self._edit_sticky_prompt(a)  # type: ignore[attr-defined]
            )
        if anchor is not None:
            sticky.sync_expanded_from_anchor(anchor)
        else:
            sticky.set_anchor_state(text=text, sent_at=sent_at, collapsible=False)
        sticky.expanded_changed.connect(self._on_sticky_overlay_expanded_changed)
        self._sticky_turn_prompt = sticky
        return sticky

    def _ensure_sticky_edit_prompt(self, anchor: ChatMessageBubble) -> StickyUserPromptOverlay:
        """Create or reuse a sticky overlay shell for inline edit hosting."""
        sticky = self._sticky_turn_prompt
        if sticky is not None and self._sticky_turn_anchor is anchor:
            return sticky
        self._clear_sticky_turn_prompt()
        self._sticky_turn_anchor = anchor
        sticky = StickyUserPromptOverlay(parent=self._scroll.viewport())
        sticky.expanded_changed.connect(self._on_sticky_overlay_expanded_changed)
        self._sticky_turn_prompt = sticky
        return sticky

    def _sync_sticky_footer_mode(
        self,
        sticky: StickyUserPromptOverlay,
        assistant: ChatMessageBubble,
    ) -> None:
        """Mirror turn-scoped stop on the sticky clone during an active stream."""
        if self._run_busy and assistant is self._streaming_bubble:  # type: ignore[attr-defined]
            sticky.set_footer_mode("stop")
        else:
            sticky.set_footer_mode("actions")

    def _raise_sticky_layers(self) -> None:
        """Keep transcript under sticky prompt; scroll-down button above sticky."""
        sticky = self._sticky_turn_prompt
        if sticky is not None and sticky.isVisible():
            sticky.raise_()
        if self._scroll_down_btn.isVisible():
            self._scroll_down_btn.raise_()

    def _sync_sticky_turn_prompt(self) -> None:
        """Show, hide, position, and clamp the sticky user prompt overlay."""
        if not isValid(self._scroll):
            return

        inline_edit = getattr(self, "_inline_edit", None)
        if inline_edit is not None and self._sync_inline_edit_sticky_host(inline_edit):  # type: ignore[attr-defined]
            return

        viewport = self._scroll.viewport()
        viewport_w = viewport.width()
        if viewport_w <= 0:
            return

        self._ensure_sticky_turn_pairs()
        self._rebuild_sticky_turn_extents()
        cap = self._sticky_prompt_height_cap()
        selected = self._sticky_turn_for_viewport(_MIN_STICKY_HEIGHT_ESTIMATE_PX)
        if selected is None:
            self._hide_sticky_unless_already_hidden()
            return

        anchor = selected.user
        assistant = selected.assistant
        user_top = selected.user_top_messages
        assistant_bottom = selected.assistant_bottom_messages
        scroll_val = self._scroll.verticalScrollBar().value()
        assistant_bottom_y = assistant_bottom - scroll_val
        anchor_y = user_top - scroll_val

        if assistant_bottom_y <= 0:
            self._hide_sticky_unless_already_hidden()
            return

        if anchor_y >= _STICKY_PROMPT_HYSTERESIS_PX:
            self._hide_sticky_unless_already_hidden()
            return

        if self._user_prompt_visible_near_viewport_top(anchor_y):
            self._hide_sticky_unless_already_hidden()
            return

        layout_source = anchor if anchor is not None else assistant
        sticky = self._ensure_sticky_turn_prompt(
            text=selected.prompt_text,
            sent_at=selected.sent_at,
            anchor=anchor,
        )
        sticky_x, content_w = self._sticky_content_geometry(layout_source, viewport)
        available_h = max(1, assistant_bottom_y - _STICKY_PROMPT_TOP_PX)
        sticky_h, metrics = self._sticky_overlay_height(
            sticky,
            anchor=anchor,
            content_w=content_w,
            cap=cap,
            available_h=available_h,
        )
        target_geom = (
            sticky_x,
            _STICKY_PROMPT_TOP_PX,
            content_w,
            sticky_h,
        )

        if assistant_bottom_y <= sticky_h + _STICKY_PROMPT_TOP_PX:
            self._hide_sticky_unless_already_hidden()
            return

        assistant_id = assistant.message_id
        unchanged = (
            self._sticky_applied_visible
            and self._sticky_applied_anchor is anchor
            and self._sticky_applied_assistant_id == assistant_id
            and self._sticky_applied_prompt_text == selected.prompt_text
            and self._sticky_applied_geom == target_geom
            and self._sticky_applied_height_cap == cap
        )
        if unchanged:
            self._sync_sticky_footer_mode(sticky, selected.assistant)
            sticky.apply_geometry(content_w, sticky_h, metrics)
            sticky.ensure_painted_geometry(metrics)
            return

        self._sync_sticky_footer_mode(sticky, selected.assistant)
        sticky.move(target_geom[0], target_geom[1])
        sticky.apply_geometry(content_w, sticky_h, metrics)
        sticky.show()
        sticky.ensure_painted_geometry(metrics)
        self._sticky_turn_anchor = anchor
        self._sticky_applied_anchor = anchor
        self._sticky_applied_assistant_id = assistant_id
        self._sticky_applied_prompt_text = selected.prompt_text
        self._sticky_applied_visible = True
        self._sticky_applied_geom = target_geom
        self._sticky_applied_height_cap = cap
        self._raise_sticky_layers()
