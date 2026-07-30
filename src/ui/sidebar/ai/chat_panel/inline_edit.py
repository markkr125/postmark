"""Inline transcript edit mixin for :class:`AiChatPanel`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QPoint, QTimer
from shiboken6 import isValid

from services.ai.chat.session_service import (
    AiChatSessionService,
    UserMessageSendSnapshot,
)
from ui.sidebar.ai.chat_panel.composer import AiChatComposer
from ui.sidebar.ai.chat_panel.scroll.sticky_prompt import (
    _MIN_STICKY_HEIGHT_ESTIMATE_PX,
    _STICKY_PROMPT_TOP_PX,
)
from ui.sidebar.ai.message_bubble import ChatMessageBubble

if TYPE_CHECKING:
    from ui.sidebar.ai.chat_panel.panel import AiChatPanel


@dataclass
class _InlineEditState:
    """Active inline edit session state."""

    message_id: int
    bubble: ChatMessageBubble
    composer: AiChatComposer
    saved_text: str
    saved_snapshot: UserMessageSendSnapshot


class _ChatPanelInlineEditMixin:  # type: ignore[misc]
    """Swap a user bubble for an inline composer during message edit."""

    _inline_edit: _InlineEditState | None

    def _init_inline_edit_state(self) -> None:
        """Initialise inline-edit flags (call from panel ``__init__``)."""
        self._inline_edit = None

    def _active_composer(self) -> AiChatComposer:
        """Return the inline composer when editing, else the docked composer."""
        if self._inline_edit is not None:
            return self._inline_edit.composer
        return cast(AiChatComposer, self._docked_composer)  # type: ignore[attr-defined]

    def _cancel_inline_edit_if_active(self) -> None:
        """End inline edit without persisting changes."""
        if self._inline_edit is not None:
            self.end_inline_edit(restore_bubble=True)

    def _release_inline_composer_to_bubble(self, state: _InlineEditState) -> None:
        """Ensure the inline composer lives in the transcript bubble before teardown."""
        panel = cast("AiChatPanel", self)
        sticky = panel._sticky_turn_prompt  # type: ignore[attr-defined]
        if sticky is not None and sticky.hosts_inline_composer():
            released = sticky.release_inline_composer()
            if released is not None and state.bubble._inline_composer is None:
                state.bubble.reattach_inline_composer(released)
        elif state.bubble._inline_composer is None:
            state.bubble.reattach_inline_composer(state.composer)

    def _edited_turn_qualifies_for_sticky_host(self, state: _InlineEditState) -> bool:
        """Return whether the edited turn should host its composer in sticky."""
        panel = cast("AiChatPanel", self)
        bubble = state.bubble
        composer = state.composer
        assistant = panel._assistant_bubble_for_turn(bubble)  # type: ignore[attr-defined]
        if assistant is None:
            return False

        scroll_val = panel._scroll.verticalScrollBar().value()  # type: ignore[attr-defined]
        user_top = bubble.mapTo(panel._messages, QPoint(0, 0)).y()  # type: ignore[attr-defined]
        if panel._user_prompt_visible_near_viewport_top(user_top - scroll_val):  # type: ignore[attr-defined]
            return False

        assistant_top = assistant.mapTo(panel._messages, QPoint(0, 0)).y()  # type: ignore[attr-defined]
        assistant_bottom = assistant.mapTo(  # type: ignore[attr-defined]
            panel._messages,
            QPoint(0, assistant.height()),
        ).y()
        assistant_bottom_y = assistant_bottom - scroll_val
        assistant_top_y = assistant_top - scroll_val

        if not panel._assistant_intersects_viewport(assistant_top_y, assistant_bottom_y):  # type: ignore[attr-defined]
            return False

        if assistant_bottom_y <= _STICKY_PROMPT_TOP_PX + _MIN_STICKY_HEIGHT_ESTIMATE_PX:
            return False

        viewport = panel._scroll.viewport()  # type: ignore[attr-defined]
        _, content_w = panel._sticky_content_geometry(bubble, viewport)  # type: ignore[attr-defined]
        cap = panel._sticky_prompt_height_cap()  # type: ignore[attr-defined]
        available_h = max(1, assistant_bottom_y - _STICKY_PROMPT_TOP_PX)
        height_cap = min(cap, available_h)
        sticky = panel._sticky_turn_prompt  # type: ignore[attr-defined]
        if sticky is None:
            sticky = panel._ensure_sticky_edit_prompt(bubble)  # type: ignore[attr-defined]
        metrics = sticky.measure_edit_for_width(content_w, height_cap, composer)
        sticky_h = min(metrics.total_height, height_cap)
        return bool(assistant_bottom_y > sticky_h + _STICKY_PROMPT_TOP_PX)

    def _focus_inline_edit_composer(self) -> None:
        """Return keyboard focus to the inline composer after reparenting."""
        state = self._inline_edit
        if state is None:
            return
        QTimer.singleShot(0, state.composer.input_widget().setFocus)

    def _on_inline_edit_composer_layout_changed(self) -> None:
        """Reflow transcript and sticky host when the inline composer resizes."""
        state = self._inline_edit
        if state is None:
            return
        # Grow the in-bubble row with the auto-growing prompt input; sticky
        # hosting measures the composer separately in overlay_edit_host.
        if state.bubble._inline_composer is not None:
            state.bubble.sync_user_message_height_constraint()
        state.bubble.layout_height_changed.emit()
        cast("AiChatPanel", self)._sync_sticky_turn_prompt()  # type: ignore[attr-defined]

    def _sync_inline_edit_sticky_host(self, state: _InlineEditState) -> bool:
        """Reparent the inline composer between bubble and sticky overlay.

        Returns ``True`` when this path fully handled sticky for the edited turn.
        Returns ``False`` so read-only sticky can run for other viewport turns.
        """
        panel = cast("AiChatPanel", self)
        if not isValid(panel._scroll):  # type: ignore[attr-defined]
            return True

        if not self._edited_turn_qualifies_for_sticky_host(state):
            self._release_inline_composer_to_bubble(state)
            return False

        bubble = state.bubble
        composer = state.composer
        assistant = panel._assistant_bubble_for_turn(bubble)  # type: ignore[attr-defined]
        assert assistant is not None

        scroll_val = panel._scroll.verticalScrollBar().value()  # type: ignore[attr-defined]
        assistant_bottom = assistant.mapTo(  # type: ignore[attr-defined]
            panel._messages,
            QPoint(0, assistant.height()),
        ).y()
        assistant_bottom_y = assistant_bottom - scroll_val

        if bubble._inline_composer is not None:
            bubble.detach_inline_composer()

        viewport = panel._scroll.viewport()  # type: ignore[attr-defined]
        sticky = panel._ensure_sticky_edit_prompt(bubble)  # type: ignore[attr-defined]
        if not sticky.hosts_inline_composer():
            sticky.host_inline_composer(composer)
            self._focus_inline_edit_composer()

        sticky_x, content_w = panel._sticky_content_geometry(bubble, viewport)  # type: ignore[attr-defined]
        cap = panel._sticky_prompt_height_cap()  # type: ignore[attr-defined]
        available_h = max(1, assistant_bottom_y - _STICKY_PROMPT_TOP_PX)
        height_cap = min(cap, available_h)
        metrics = sticky.measure_edit_for_width(content_w, height_cap, composer)
        sticky_h = min(metrics.total_height, height_cap)
        metrics = sticky.measure_edit_for_width(content_w, sticky_h, composer)
        sticky.apply_edit_geometry(content_w, sticky_h, metrics, composer)

        target_geom = (sticky_x, _STICKY_PROMPT_TOP_PX, content_w, sticky_h)
        assistant_id = assistant.message_id
        unchanged = (
            panel._sticky_applied_visible  # type: ignore[attr-defined]
            and panel._sticky_applied_anchor is bubble  # type: ignore[attr-defined]
            and panel._sticky_applied_assistant_id == assistant_id  # type: ignore[attr-defined]
            and panel._sticky_applied_geom == target_geom
            and sticky.hosts_inline_composer()
        )
        if not unchanged:
            sticky.move(target_geom[0], target_geom[1])
            sticky.show()
            panel._sticky_turn_anchor = bubble  # type: ignore[attr-defined]
            panel._sticky_applied_anchor = bubble  # type: ignore[attr-defined]
            panel._sticky_applied_assistant_id = assistant_id  # type: ignore[attr-defined]
            panel._sticky_applied_prompt_text = composer.plain_text()
            panel._sticky_applied_visible = True  # type: ignore[attr-defined]
            panel._sticky_applied_geom = target_geom  # type: ignore[attr-defined]
            panel._sticky_applied_height_cap = cap  # type: ignore[attr-defined]
            panel._raise_sticky_layers()  # type: ignore[attr-defined]
        return True

    def _sticky_visible_for_bubble(self, bubble: ChatMessageBubble) -> bool:
        """Return whether the sticky overlay is showing this user row."""
        panel = cast("AiChatPanel", self)
        sticky = panel._sticky_turn_prompt  # type: ignore[attr-defined]
        return (
            sticky is not None
            and sticky.isVisible()
            and panel._sticky_turn_anchor is bubble  # type: ignore[attr-defined]
            and not sticky.hosts_inline_composer()
        )

    def begin_inline_edit(self, message_id: int, *, prefer_sticky_host: bool = False) -> bool:
        """Open an inline composer on the user row for *message_id*."""
        panel = cast("AiChatPanel", self)
        if panel._run_busy or self._inline_edit is not None:
            return False
        bubble = panel._bubble_by_message_id.get(message_id)  # type: ignore[attr-defined]
        if bubble is None or bubble.role != "user":
            if not panel.ensure_message_bubble_loaded(message_id):
                return False
            bubble = panel._bubble_by_message_id.get(message_id)
        if bubble is None:
            return False
        session_id = getattr(panel, "_virtual_session_id", None) or panel._context_session_id
        snapshot: UserMessageSendSnapshot
        if session_id:
            row = next(
                (m for m in AiChatSessionService.get_messages(session_id) if m["id"] == message_id),
                None,
            )
            if row is not None:
                msg = AiChatSessionService._cast_message(dict(row))
                snapshot = AiChatSessionService.send_snapshot_from_message(msg)
                if not snapshot.get("send_model_id"):
                    snapshot = AiChatSessionService.infer_send_snapshot_fallback(
                        session_id,
                        message_id,
                        extra_entries=panel._models,  # type: ignore[attr-defined]
                    )
            else:
                snapshot = UserMessageSendSnapshot()
        else:
            snapshot = UserMessageSendSnapshot()

        panel._hide_context_popup()
        panel._picker_popup.hidePopup()  # type: ignore[attr-defined]
        panel._mode_popup.hide_popup()  # type: ignore[attr-defined]

        saved_text = bubble.user_message_text()
        host_in_sticky = prefer_sticky_host and self._sticky_visible_for_bubble(bubble)
        sticky = None
        inline_parent = bubble.user_message_host()
        if host_in_sticky:
            sticky = panel._ensure_sticky_edit_prompt(bubble)  # type: ignore[attr-defined]
            inline_parent = sticky._frame

        inline = AiChatComposer(inline_parent)
        inline.set_models(panel._models)  # type: ignore[attr-defined]
        inline.set_embedded(True)
        inline.set_compact(True)
        inline.set_edit_mode(True)
        inline.apply_send_snapshot(snapshot)
        inline.restore_text(saved_text)
        inline.model_picker_requested.connect(panel._open_model_picker)
        inline.mode_picker_requested.connect(panel._open_mode_picker)
        inline.submit_requested.connect(lambda: panel._on_inline_edit_submit())
        inline.cancel_requested.connect(lambda: panel.end_inline_edit(restore_bubble=True))
        inline.layout_height_changed.connect(self._on_inline_edit_composer_layout_changed)

        if host_in_sticky:
            assert sticky is not None
            if not bubble.begin_inline_edit_chrome():
                inline.setParent(None)
                inline.deleteLater()
                return False
            sticky.host_inline_composer(inline)
            self._inline_edit = _InlineEditState(
                message_id=message_id,
                bubble=bubble,
                composer=inline,
                saved_text=saved_text,
                saved_snapshot=snapshot,
            )
            self._focus_inline_edit_composer()
            panel._invalidate_sticky_extents()  # type: ignore[attr-defined]
            panel._sync_sticky_turn_prompt()  # type: ignore[attr-defined]
            return True

        if not bubble.begin_inline_composer(inline):
            inline.setParent(None)
            inline.deleteLater()
            return False

        self._inline_edit = _InlineEditState(
            message_id=message_id,
            bubble=bubble,
            composer=inline,
            saved_text=saved_text,
            saved_snapshot=snapshot,
        )
        panel._request_scroll_to_user_bubble(bubble)  # type: ignore[attr-defined]
        self._focus_inline_edit_composer()
        panel._invalidate_sticky_extents()  # type: ignore[attr-defined]
        panel._sync_sticky_turn_prompt()  # type: ignore[attr-defined]
        return True

    def end_inline_edit(self, *, restore_bubble: bool) -> None:
        """Tear down inline edit and optionally restore the read-only bubble."""
        panel = cast("AiChatPanel", self)
        state = self._inline_edit
        if state is None:
            return
        self._release_inline_composer_to_bubble(state)
        state.bubble.end_inline_composer(restore_text=state.saved_text if restore_bubble else None)
        state.composer.setParent(None)
        state.composer.deleteLater()
        self._inline_edit = None
        panel._invalidate_sticky_extents()  # type: ignore[attr-defined]
        panel._sync_sticky_turn_prompt()  # type: ignore[attr-defined]

    def _on_inline_edit_submit(self) -> None:
        """Validate inline text and emit edit submit to the controller."""
        panel = cast("AiChatPanel", self)
        state = self._inline_edit
        if state is None:
            return
        text = state.composer.composed_prompt()
        if not text:
            return
        panel.user_edit_submitted.emit(state.message_id, text)  # type: ignore[attr-defined]

    def truncate_transcript_after(self, message_id: int) -> None:
        """Remove transcript bubbles for rows deleted after *message_id*."""
        panel = cast("AiChatPanel", self)
        if self._inline_edit is not None and self._inline_edit.message_id == message_id:
            state = self._inline_edit
            state.bubble.set_user_message_text(state.composer.composed_prompt())
            self.end_inline_edit(restore_bubble=False)
        to_remove: list[ChatMessageBubble] = []
        for bubble in list(panel._bubble_by_message_id.values()):  # type: ignore[attr-defined]
            mid = bubble.message_id
            if mid is not None and mid > message_id:
                to_remove.append(bubble)
        for bubble in to_remove:
            panel.remove_transcript_bubble(bubble)
        from ui.sidebar.ai.transcript.summarized_notice import find_summarized_notice

        notice = find_summarized_notice(panel._messages)  # type: ignore[attr-defined]
        if notice is not None:
            for bubble in to_remove:
                if bubble.message_id is not None and bubble.message_id <= message_id:
                    continue
            # Remove summarized notice when truncating — compaction state may be stale.
            if to_remove:
                panel._messages_layout.removeWidget(notice)  # type: ignore[attr-defined]
                notice.setParent(None)
                notice.deleteLater()
                panel._summarized_notice_session_id = None  # type: ignore[attr-defined]
        panel._recompute_transcript_bounds_after_truncation(message_id)  # type: ignore[attr-defined]
        panel._invalidate_sticky_turn_pairs()  # type: ignore[attr-defined]
        panel._sync_sticky_turn_prompt()  # type: ignore[attr-defined]


__all__ = ["_ChatPanelInlineEditMixin"]
