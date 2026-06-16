"""Inline transcript edit mixin for :class:`AiChatPanel`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QTimer

from services.ai.chat.session_service import (
    AiChatSessionService,
    UserMessageSendSnapshot,
)
from ui.sidebar.ai.chat_panel.composer import AiChatComposer
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
    _sticky_edit_suppressed: bool

    def _init_inline_edit_state(self) -> None:
        """Initialise inline-edit flags (call from panel ``__init__``)."""
        self._inline_edit = None
        self._sticky_edit_suppressed = False

    def _active_composer(self) -> AiChatComposer:
        """Return the inline composer when editing, else the docked composer."""
        if self._inline_edit is not None:
            return self._inline_edit.composer
        return cast(AiChatComposer, self._docked_composer)  # type: ignore[attr-defined]

    def _cancel_inline_edit_if_active(self) -> None:
        """End inline edit without persisting changes."""
        if self._inline_edit is not None:
            self.end_inline_edit(restore_bubble=True)

    def begin_inline_edit(self, message_id: int) -> bool:
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

        self._sticky_edit_suppressed = True
        panel._hide_context_popup()
        panel._picker_popup.hidePopup()  # type: ignore[attr-defined]
        panel._mode_popup.hide_popup()  # type: ignore[attr-defined]

        saved_text = bubble.user_message_text()
        inline = AiChatComposer(bubble.user_message_host())
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
        inline.layout_height_changed.connect(bubble.layout_height_changed.emit)

        if not bubble.begin_inline_composer(inline):
            inline.setParent(None)
            inline.deleteLater()
            self._sticky_edit_suppressed = False
            return False

        self._inline_edit = _InlineEditState(
            message_id=message_id,
            bubble=bubble,
            composer=inline,
            saved_text=saved_text,
            saved_snapshot=snapshot,
        )
        panel._docked_composer.hide()
        panel._request_scroll_to_user_bubble(bubble)  # type: ignore[attr-defined]
        QTimer.singleShot(0, inline.input_widget().setFocus)
        panel._invalidate_sticky_extents()  # type: ignore[attr-defined]
        panel._sync_sticky_turn_prompt()  # type: ignore[attr-defined]
        return True

    def end_inline_edit(self, *, restore_bubble: bool) -> None:
        """Tear down inline edit and optionally restore the read-only bubble."""
        panel = cast("AiChatPanel", self)
        state = self._inline_edit
        if state is None:
            return
        state.bubble.end_inline_composer(restore_text=state.saved_text if restore_bubble else None)
        state.composer.setParent(None)
        state.composer.deleteLater()
        self._inline_edit = None
        self._sticky_edit_suppressed = False
        panel._docked_composer.show()
        panel._invalidate_sticky_extents()  # type: ignore[attr-defined]
        panel._sync_sticky_turn_prompt()  # type: ignore[attr-defined]

    def _on_inline_edit_submit(self) -> None:
        """Validate inline text and emit edit submit to the controller."""
        panel = cast("AiChatPanel", self)
        state = self._inline_edit
        if state is None:
            return
        text = state.composer.plain_text()
        if not text:
            return
        panel.user_edit_submitted.emit(state.message_id, text)  # type: ignore[attr-defined]

    def truncate_transcript_after(self, message_id: int) -> None:
        """Remove transcript bubbles for rows deleted after *message_id*."""
        panel = cast("AiChatPanel", self)
        if self._inline_edit is not None and self._inline_edit.message_id == message_id:
            state = self._inline_edit
            state.bubble.set_user_message_text(state.composer.plain_text())
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
