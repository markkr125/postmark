"""Sticky user-prompt overlay for the AI chat transcript viewport."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, NamedTuple

from PySide6.QtCore import QPoint, QTimer, Qt
from shiboken6 import isValid
from PySide6.QtWidgets import QPushButton, QScrollArea, QWidget

from ui.sidebar.ai.message_bubble import ChatMessageBubble

_STICKY_PROMPT_TOP_PX = 0
_STICKY_PROMPT_MAX_VIEWPORT_RATIO = 0.35
_STICKY_PROMPT_MARGIN_PX = 4
_STICKY_PROMPT_HYSTERESIS_PX = 4


class StickyTurnExtent(NamedTuple):
    """Scroll-independent Y extents for one user/assistant turn pair."""

    user: ChatMessageBubble
    assistant: ChatMessageBubble
    user_top_messages: int
    assistant_bottom_messages: int


class _ChatPanelStickyPromptMixin:  # type: ignore[misc]
    """Cached turn selection and viewport overlay for the sticky user prompt."""

    _scroll: QScrollArea
    _messages: QWidget
    _messages_layout: Any = None
    _scroll_down_btn: QPushButton
    _sticky_turn_anchor: ChatMessageBubble | None = None
    _sticky_turn_prompt: ChatMessageBubble | None = None
    _sticky_turn_pairs: list[tuple[ChatMessageBubble, ChatMessageBubble]]
    _sticky_turn_pairs_dirty: bool = True
    _sticky_turn_extents: list[StickyTurnExtent]
    _sticky_extent_by_pair: dict[tuple[int, int], StickyTurnExtent]
    _sticky_extents_dirty: bool = True
    _sticky_applied_anchor: ChatMessageBubble | None = None
    _sticky_applied_visible: bool = False
    _sticky_applied_geom: tuple[int, int, int, int] = (0, 0, 0, 0)
    _sticky_applied_height_cap: int = 0
    _sticky_sync_pending: bool = False
    _sticky_sync_frame_pending: bool = False

    def _iter_chat_turns(self) -> Iterator[tuple[ChatMessageBubble, ChatMessageBubble]]:
        """Yield transcript turn pairs (implemented by :class:`_ChatPanelScrollMixin`)."""
        raise NotImplementedError

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

    def _rebuild_sticky_turn_extents(self) -> None:
        """Recompute scroll-independent Y extents for every cached turn pair."""
        extents: list[StickyTurnExtent] = []
        extent_by_pair: dict[tuple[int, int], StickyTurnExtent] = {}
        for user, assistant in self._ensure_sticky_turn_pairs():
            if not isValid(user) or not isValid(assistant):
                continue
            user_top = user.mapTo(self._messages, QPoint(0, 0)).y()
            assistant_bottom = assistant.mapTo(self._messages, QPoint(0, assistant.height())).y()
            extent = StickyTurnExtent(user, assistant, user_top, assistant_bottom)
            extents.append(extent)
            extent_by_pair[(id(user), id(assistant))] = extent
        self._sticky_turn_extents = extents
        self._sticky_extent_by_pair = extent_by_pair
        self._sticky_extents_dirty = False

    def _ensure_sticky_turn_extents(self) -> list[StickyTurnExtent]:
        """Return cached turn extents, rebuilding them when marked dirty."""
        if self._sticky_extents_dirty:
            self._rebuild_sticky_turn_extents()
        return self._sticky_turn_extents

    def _messages_y_for_turn(
        self,
        anchor: ChatMessageBubble,
        assistant: ChatMessageBubble,
    ) -> tuple[int, int] | None:
        """Return cached ``(user_top, assistant_bottom)`` in messages coordinates."""
        extent = self._sticky_extent_by_pair.get((id(anchor), id(assistant)))
        if extent is None:
            self._ensure_sticky_turn_extents()
            extent = self._sticky_extent_by_pair.get((id(anchor), id(assistant)))
        if extent is None:
            return None
        return extent.user_top_messages, extent.assistant_bottom_messages

    def _reset_sticky_applied_state(self) -> None:
        """Clear last-applied sticky overlay geometry and visibility."""
        self._sticky_applied_anchor = None
        self._sticky_applied_visible = False
        self._sticky_applied_geom = (0, 0, 0, 0)
        self._sticky_applied_height_cap = 0

    def _schedule_sticky_sync(self) -> None:
        """Coalesce sticky overlay updates to one pass per event-loop frame."""
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
        ratio_cap = int(viewport_h * _STICKY_PROMPT_MAX_VIEWPORT_RATIO)
        # Keep typical 2-line prompts + timestamp uncropped; still clamp very tall turns.
        return max(ratio_cap, min(viewport_h - 16, 120))

    def _sticky_turn_for_viewport(
        self,
        sticky_h_estimate: int,
    ) -> tuple[ChatMessageBubble, ChatMessageBubble] | None:
        """Return the closest eligible user/assistant turn for the current viewport."""
        scroll_val = self._scroll.verticalScrollBar().value()
        best: tuple[ChatMessageBubble, ChatMessageBubble] | None = None
        best_user_y = -(10**9)
        for extent in self._ensure_sticky_turn_extents():
            user_y = extent.user_top_messages - scroll_val
            assistant_bottom_y = extent.assistant_bottom_messages - scroll_val
            if assistant_bottom_y <= 0:
                continue
            if assistant_bottom_y <= sticky_h_estimate + _STICKY_PROMPT_TOP_PX:
                continue
            if user_y >= -_STICKY_PROMPT_MARGIN_PX:
                continue
            if user_y > best_user_y:
                best_user_y = user_y
                best = (extent.user, extent.assistant)
        return best

    def _clear_sticky_turn_prompt(self) -> None:
        """Remove the sticky turn prompt overlay from the viewport."""
        sticky = self._sticky_turn_prompt
        self._sticky_turn_prompt = None
        self._sticky_turn_anchor = None
        self._reset_sticky_applied_state()
        if sticky is None:
            return
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
        anchor: ChatMessageBubble,
        viewport: QWidget,
    ) -> tuple[int, int]:
        """Return ``(x, width)`` aligned with the real user bubble column."""
        content_w = anchor.width()
        if content_w <= 0:
            content_w = max(1, self._messages.width())
        sticky_x = self._messages.mapTo(viewport, QPoint(0, 0)).x()
        return sticky_x, content_w

    def _sticky_overlay_height(
        self,
        sticky: ChatMessageBubble,
        *,
        content_w: int,
        cap: int,
        anchor_h: int,
        available_h: int,
    ) -> int:
        """Size the sticky overlay to match the anchor bubble when it fits."""
        sticky.setFixedWidth(content_w)
        sticky.set_user_message_max_height(None)
        natural_h = max(1, anchor_h)
        sticky_h = min(cap, available_h) if natural_h > cap else min(natural_h, available_h)
        if natural_h > sticky_h:
            sticky.set_user_message_max_height(sticky_h)
            sticky.setFixedHeight(sticky_h)
        else:
            sticky.setFixedHeight(sticky_h)
        return sticky_h

    def _ensure_sticky_turn_prompt(self, anchor: ChatMessageBubble) -> ChatMessageBubble:
        """Create or refresh the read-only sticky clone for *anchor*."""
        text = anchor.text()
        sent_at = anchor.sent_at()
        sticky = self._sticky_turn_prompt
        if (
            sticky is not None
            and self._sticky_turn_anchor is anchor
            and sticky.text() == text
            and sticky.sent_at() == sent_at
        ):
            return sticky
        self._clear_sticky_turn_prompt()
        self._sticky_turn_anchor = anchor
        viewport = self._scroll.viewport()
        sticky = ChatMessageBubble("user", text, sent_at=sent_at, parent=viewport)
        sticky.setObjectName("aiChatStickyTurnPrompt")
        sticky.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._sticky_turn_prompt = sticky
        return sticky

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

        viewport = self._scroll.viewport()
        viewport_w = viewport.width()
        if viewport_w <= 0:
            return

        cap = self._sticky_prompt_height_cap()
        selected = self._sticky_turn_for_viewport(cap)
        if selected is None:
            self._hide_sticky_unless_already_hidden()
            return

        anchor, assistant = selected
        messages_y = self._messages_y_for_turn(anchor, assistant)
        if messages_y is None:
            self._hide_sticky_unless_already_hidden()
            return

        user_top, assistant_bottom = messages_y
        scroll_val = self._scroll.verticalScrollBar().value()
        assistant_bottom_y = assistant_bottom - scroll_val
        anchor_y = user_top - scroll_val

        if assistant_bottom_y <= 0:
            self._hide_sticky_unless_already_hidden()
            return

        if anchor_y >= _STICKY_PROMPT_HYSTERESIS_PX:
            self._hide_sticky_unless_already_hidden()
            return

        if anchor_y >= -_STICKY_PROMPT_MARGIN_PX:
            self._hide_sticky_unless_already_hidden()
            return

        sticky = self._ensure_sticky_turn_prompt(anchor)
        sticky_x, content_w = self._sticky_content_geometry(anchor, viewport)
        anchor_h = max(1, anchor.height())
        available_h = max(1, assistant_bottom_y - _STICKY_PROMPT_TOP_PX)
        sticky_h = self._sticky_overlay_height(
            sticky,
            content_w=content_w,
            cap=cap,
            anchor_h=anchor_h,
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

        if (
            self._sticky_applied_visible
            and self._sticky_applied_anchor is anchor
            and self._sticky_applied_geom == target_geom
            and self._sticky_applied_height_cap == cap
        ):
            return

        sticky.move(target_geom[0], target_geom[1])
        sticky.show()
        self._sticky_applied_anchor = anchor
        self._sticky_applied_visible = True
        self._sticky_applied_geom = target_geom
        self._sticky_applied_height_cap = cap
        self._raise_sticky_layers()
