"""Chat message row widget for the AI assistant transcript."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, NamedTuple

from PySide6.QtCore import Qt, QTimer, QSize, Signal
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from services.ai.ai_config import AiModelEntry
from services.ai.chat.message_usage import format_assistant_footer_label
from services.ai.chat.session_service import AiChatMessageDict
from ui.sidebar.ai.chat_panel.scroll.widget_coords import map_widget_y_to_ancestor
from ui.sidebar.ai.message_bubble.activity_row import AssistantActivityRow
from ui.sidebar.ai.message_bubble.assistant_message.footer import AssistantMessageFooterRow
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent
from ui.sidebar.ai.message_bubble.thought_section import ThoughtSection
from ui.sidebar.ai.message_bubble.user_message import UserMessageFooterRow, UserMessageSection
from ui.sidebar.ai.message_bubble.user_message.footer import UserMessageFooterMode

ChatRole = Literal["user", "assistant"]
_QWIDGET_MAX_HEIGHT = 16777215


class UserMessageStickyMetrics(NamedTuple):
    """Explicit sticky-overlay height parts for a user message row."""

    label_height: int
    chrome_height: int
    total_height: int
    clamped: bool


class ChatMessageBubble(QWidget):
    """One chat transcript row.

    User messages render as a full-width bubble. Assistant messages render
    markdown on the panel background with an optional collapsible thought block
    above the answer.
    """

    layout_height_changed = Signal()
    fork_requested = Signal()
    copy_requested = Signal()
    user_fork_requested = Signal()
    user_edit_requested = Signal()

    def __init__(
        self,
        role: ChatRole,
        text: str,
        *,
        thinking: str = "",
        thinking_duration_seconds: int | None = None,
        sent_at: datetime | None = None,
        lazy_markdown: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Build a row for *role* showing *text* and optional *thinking*."""
        super().__init__(parent)
        self._role: ChatRole = role
        self._message_id: int | None = None
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 6)
        outer.setSpacing(0)

        self._thought_section: ThoughtSection | None = None
        self._activity_row: AssistantActivityRow | None = None
        self._user_frame: QFrame | None = None
        self._user_section: UserMessageSection | None = None
        self._user_footer: UserMessageFooterRow | None = None
        self._inline_composer: QWidget | None = None
        self._sent_at: datetime | None = sent_at if role == "user" else None
        self._markdown_body: MarkdownContent | None = None
        self._assistant_footer: AssistantMessageFooterRow | None = None
        self._assistant_turn_complete = False
        self._usage_model_id: str | None = None
        self._usage_prompt_tokens: int | None = None
        self._usage_completion_tokens: int | None = None
        self._usage_reasoning_tokens: int | None = None
        self._usage_entry: AiModelEntry | None = None
        self._answer_visible = bool(text.strip())
        self._answer_started = bool(text.strip())
        self._defer_layout_height_changed = False
        self._layout_height_pending = False
        self._scroll_compensation_capture: tuple[int, int] | None = None
        self._scroll_compensation_block: QWidget | None = None

        if role == "user":
            frame = QFrame()
            frame.setObjectName("aiChatMessageUser")
            frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            frame.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(12, 6, 12, 6)
            frame_layout.setSpacing(0)
            self._user_section = UserMessageSection(text, frame)
            self._user_section.layout_height_changed.connect(self._on_user_message_layout_changed)
            frame_layout.addWidget(self._user_section)
            self._user_footer = UserMessageFooterRow(frame)
            self._user_footer.set_sent_at(sent_at)
            self._user_footer.fork_requested.connect(self.user_fork_requested.emit)
            self._user_footer.edit_requested.connect(self.user_edit_requested.emit)
            frame_layout.addWidget(self._user_footer)
            self._user_frame = frame
            outer.addWidget(frame)
        else:
            self.setObjectName("aiChatAssistantRow")
            self._activity_row = AssistantActivityRow(self)
            outer.addWidget(self._activity_row)

            self._thought_section = ThoughtSection(self)
            self._thought_section.layout_height_changed.connect(self._on_thought_layout_changed)
            self._thought_section.set_text(thinking)
            if thinking_duration_seconds is not None:
                self._thought_section.set_duration_seconds(thinking_duration_seconds)
            if thinking.strip():
                self._thought_section.set_collapsed(True)
            outer.addWidget(self._thought_section)

            self._markdown_body = MarkdownContent("")
            if lazy_markdown and text.strip():
                self._markdown_body.set_markdown_lazy(text)
            elif text.strip():
                self._markdown_body.set_markdown(text)
            self._markdown_body.height_changed.connect(self._on_markdown_height_changed)
            outer.addWidget(self._markdown_body)
            if not self._answer_visible:
                self._markdown_body.hide()

            self._assistant_footer = AssistantMessageFooterRow(self)
            self._assistant_footer.fork_requested.connect(self.fork_requested.emit)
            self._assistant_footer.copy_requested.connect(self.copy_requested.emit)
            outer.addWidget(self._assistant_footer)
            if text.strip() or thinking.strip():
                self._assistant_turn_complete = True
            if self._assistant_turn_complete:
                self._sync_assistant_footer_visibility()

    def _ensure_answer_visible(self) -> None:
        """Show the answer body once any non-thinking text exists."""
        if not self._answer_visible:
            self._answer_visible = True
            if self._markdown_body is not None:
                self._markdown_body.show()

    def _on_answer_stream_start(self) -> None:
        """Collapse the thought block when the answer begins streaming."""
        if self._answer_started or self._thought_section is None:
            return
        self._answer_started = True
        if self._thought_section.has_text():
            self._thought_section.finalize_thinking(collapse=True)

    @property
    def role(self) -> ChatRole:
        """Return the message role."""
        return self._role

    def sizeHint(self) -> QSize:
        """Return the preferred row height."""
        if self._role == "user":
            return self._user_message_layout_hint()
        return super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        """Return the minimum row height."""
        if self._role == "user":
            return self._user_message_layout_hint()
        return super().minimumSizeHint()

    def _transcript_row_layout_width(self) -> int:
        """Return the horizontal layout budget for this row inside ``_messages``."""
        parent = self.parentWidget()
        width = 0
        if parent is not None and parent.width() > 0:
            width = parent.width()
            layout = parent.layout()
            if layout is not None:
                margins = layout.contentsMargins()
                width = max(1, width - margins.left() - margins.right())
        if self.width() > 0:
            width = min(width, self.width()) if width > 0 else self.width()
        if width <= 0:
            width = max(1, super().sizeHint().width())
        return max(1, width)

    def _user_message_layout_hint(self) -> QSize:
        """Return measured user-row size from wrapped text, not slack-inflated layout."""
        width = self._transcript_row_layout_width()
        label_width = self._user_message_label_width(width)
        if self._user_section is None:
            return QSize(max(1, width), 1)
        label_h = self._user_section.natural_label_height_for_width(label_width)
        chrome = self._user_message_chrome_height(label_width)
        outer = self.layout()
        if outer is None:
            return QSize(max(1, width), chrome + label_h)
        margins = outer.contentsMargins()
        height = chrome + label_h + margins.top() + margins.bottom()
        laid_out = self.height()
        if laid_out > 0 and laid_out <= height + 24:
            height = laid_out
        return QSize(max(1, width), height)

    def sync_user_message_height_constraint(self) -> None:
        """Clamp transcript user rows to their measured content height."""
        if self._role != "user":
            return
        self.setMinimumHeight(0)
        self.setMaximumHeight(_QWIDGET_MAX_HEIGHT)
        hint = self._user_message_layout_hint()
        self.setFixedHeight(hint.height())
        self.updateGeometry()
        panel = self._ancestor_chat_panel()
        if (
            panel is not None
            and getattr(panel, "_pending_transcript_bottom_scroll", False)
            and getattr(panel, "_scroll_lock_enabled", False)
            and hasattr(panel, "_maybe_flush_pending_transcript_bottom_scroll")
        ):
            QTimer.singleShot(0, panel._maybe_flush_pending_transcript_bottom_scroll)  # type: ignore[attr-defined]

    @property
    def message_id(self) -> int | None:
        """Return the persisted SQLite message id, if assigned."""
        return self._message_id

    def set_message_id(self, message_id: int) -> None:
        """Bind this bubble to a persisted message row."""
        self._message_id = message_id
        if self._assistant_footer is not None:
            self._assistant_footer.set_fork_enabled(True)
        if self._user_footer is not None:
            self._user_footer.set_fork_enabled(True)
            self._user_footer.set_edit_enabled(True)

    def text(self) -> str:
        """Return the answer text (markdown source for assistant rows)."""
        if self._markdown_body is not None:
            return self._markdown_body.markdown()
        if self._user_section is not None:
            return self._user_section.text()
        return ""

    @property
    def _user_timestamp(self) -> QLabel | None:
        """Legacy accessor for tests that locate the send-time label."""
        if self._user_footer is None:
            return None
        return self._user_footer.timestamp_label()

    def user_message_text(self) -> str:
        """Return the user prompt text."""
        if self._user_section is None:
            return ""
        return self._user_section.text()

    def set_user_message_text(self, text: str) -> None:
        """Replace user prompt text in the read-only section."""
        if self._user_section is None:
            return
        self._user_section.set_text(text)

    def user_message_host(self) -> QFrame | None:
        """Return the user message frame for inline composer embedding."""
        return self._user_frame

    def begin_inline_edit_chrome(self) -> bool:
        """Hide read-only user UI for inline edit without embedding a composer."""
        if self._user_section is None or self._user_footer is None:
            return False
        self._user_section.hide()
        self._user_footer.hide()
        self.layout_height_changed.emit()
        return True

    def begin_inline_composer(self, composer: QWidget) -> bool:
        """Hide read-only body and embed *composer* in the user frame."""
        if self._user_frame is None or self._user_section is None or self._user_footer is None:
            return False
        self._user_section.hide()
        self._user_footer.hide()
        frame_layout = self._user_frame.layout()
        if frame_layout is None:
            return False
        frame_layout.addWidget(composer)
        self._inline_composer = composer
        self.layout_height_changed.emit()
        return True

    def detach_inline_composer(self) -> QWidget | None:
        """Remove the inline composer from the frame without restoring read-only UI."""
        composer = self._inline_composer
        if composer is None or self._user_frame is None:
            return None
        frame_layout = self._user_frame.layout()
        if frame_layout is not None:
            frame_layout.removeWidget(composer)
        composer.setParent(None)
        self._inline_composer = None
        self.layout_height_changed.emit()
        return composer

    def reattach_inline_composer(self, composer: QWidget) -> None:
        """Re-embed *composer* in the user frame during inline edit."""
        if self._user_frame is None or self._user_section is None or self._user_footer is None:
            return
        frame_layout = self._user_frame.layout()
        if frame_layout is None:
            return
        frame_layout.addWidget(composer)
        self._inline_composer = composer
        self.layout_height_changed.emit()

    def end_inline_composer(self, *, restore_text: str | None) -> None:
        """Remove inline composer and restore the read-only user section."""
        if self._user_frame is None or self._user_section is None or self._user_footer is None:
            return
        composer = self._inline_composer
        if composer is not None:
            frame_layout = self._user_frame.layout()
            if frame_layout is not None:
                frame_layout.removeWidget(composer)
            composer.setParent(None)
            self._inline_composer = None
        if restore_text is not None:
            self._user_section.set_text(restore_text)
        self._user_section.show()
        self._user_footer.show()
        self.layout_height_changed.emit()

    def sent_at(self) -> datetime | None:
        """Return the user-message send time, if any."""
        return self._sent_at

    def thinking_text(self) -> str:
        """Return the thinking text, if any."""
        if self._thought_section is None:
            return ""
        return self._thought_section.text()

    def is_user_message_expanded(self) -> bool:
        """Return whether the user prompt is fully expanded."""
        if self._user_section is None:
            return True
        return self._user_section.is_expanded()

    def user_message_collapsed_cap_height(self) -> int | None:
        """Return the collapsed user-label cap height when applicable."""
        if self._user_section is None:
            return None
        return self._user_section.collapsed_cap_height()

    def set_user_footer_mode(self, mode: UserMessageFooterMode) -> None:
        """Switch the user footer between actions menu and turn-scoped stop."""
        if self._user_footer is None:
            return
        self._user_footer.set_footer_mode(mode)
        self.sync_user_message_height_constraint()

    def user_footer_mode(self) -> UserMessageFooterMode:
        """Return the user footer mode, or ``actions`` for non-user rows."""
        if self._user_footer is None:
            return "actions"
        return self._user_footer.footer_mode()

    def begin_streaming(self) -> None:
        """Mark the answer body as receiving streamed markdown."""
        if self._role == "assistant":
            self.set_assistant_turn_complete(False)
        if self._markdown_body is not None:
            self._markdown_body.begin_streaming()

    def full_markdown_for_copy(self) -> str:
        """Return the assistant answer markdown for clipboard copy."""
        return self.text()

    def set_usage_metadata(
        self,
        *,
        model_id: str | None,
        model_label: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        entry: AiModelEntry | None = None,
        extra_entries: list[AiModelEntry] | None = None,
        message: AiChatMessageDict | None = None,
        messages: list[AiChatMessageDict] | None = None,
        msg_index: int | None = None,
        session_model_id: str | None = None,
    ) -> None:
        """Apply persisted or live usage metadata to the assistant footer."""
        if self._role != "assistant" or self._assistant_footer is None:
            return
        self._usage_model_id = model_id
        self._usage_prompt_tokens = prompt_tokens
        self._usage_completion_tokens = completion_tokens
        self._usage_reasoning_tokens = reasoning_tokens
        if entry is not None:
            self._usage_entry = entry
        label = format_assistant_footer_label(
            entry if entry is not None else self._usage_entry,
            model_id,
            model_label=model_label,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens,
            extra_entries=extra_entries,
            message=message,
            messages=messages,
            msg_index=msg_index,
            session_model_id=session_model_id,
        )
        self._assistant_footer.set_usage_text(label)
        self._assistant_footer.set_fork_enabled(self._message_id is not None)
        self._sync_assistant_footer_visibility()

    def set_assistant_turn_complete(self, complete: bool) -> None:
        """Mark whether the assistant turn is finished (shows the footer)."""
        if self._role != "assistant":
            return
        self._assistant_turn_complete = complete
        self._sync_assistant_footer_visibility()

    def is_turn_complete(self) -> bool:
        """Return whether this assistant row may show the footer."""
        if self._role != "assistant":
            return False
        if not self._assistant_turn_complete:
            return False
        if self.is_content_streaming():
            return False
        return not self.is_activity_visible()

    def _sync_assistant_footer_visibility(self) -> None:
        """Show or hide the assistant footer based on turn completion state."""
        footer = self._assistant_footer
        if footer is None:
            return
        body = self._markdown_body
        complete = self.is_turn_complete()
        was_visible = footer.isVisible()
        if body is not None:
            body.set_paint_footer_rule(complete)
        if complete:
            footer.show()
        else:
            footer.hide()
        self.updateGeometry()
        if footer.isVisible() != was_visible:
            self.layout_height_changed.emit()

    def end_streaming(self, *, render: bool = True) -> None:
        """Mark streaming complete on the answer body."""
        if self._markdown_body is not None:
            self._markdown_body.end_streaming(render=render)
        if self._role == "assistant":
            self.clear_stream_layout_floor()
            self.set_assistant_turn_complete(True)

    def is_content_streaming(self) -> bool:
        """Return whether the answer body is still receiving stream updates."""
        if self._markdown_body is None:
            return False
        return self._markdown_body.is_streaming()

    def append_thinking(self, text: str, *, defer_geometry: bool = False) -> None:
        """Append streaming thinking text (assistant only)."""
        if not text or self._thought_section is None:
            return
        if not self._answer_started:
            self._thought_section.set_collapsed(False)
        self._thought_section.append_text(text, defer_geometry=defer_geometry)
        if defer_geometry:
            return
        self.updateGeometry()
        self._commit_stream_row_layout()

    def is_thinking_expanded(self) -> bool:
        """Return whether the thinking body is expanded."""
        if self._thought_section is None:
            return False
        return self._thought_section.is_expanded()

    def thought_header_text(self) -> str:
        """Return the thought toggle label (e.g. ``Thought for 2s``)."""
        if self._thought_section is None:
            return ""
        return self._thought_section.header_text()

    def thinking_duration_seconds(self) -> int | None:
        """Return the frozen thinking duration for this row, if any."""
        if self._thought_section is None:
            return None
        return self._thought_section.duration_seconds()

    def show_activity(self, message: str) -> None:
        """Show the waiting spinner and status caption (assistant only)."""
        if self._activity_row is not None:
            self.set_assistant_turn_complete(False)
            self._activity_row.show_activity(message)
            self.updateGeometry()
            self._commit_stream_row_layout()

    def set_activity_message(self, message: str) -> None:
        """Update the waiting status caption without changing visibility."""
        if self._activity_row is not None:
            self._activity_row.set_message(message)

    def hide_activity(self) -> None:
        """Hide the waiting spinner row (assistant only)."""
        if self._activity_row is not None:
            self._activity_row.hide_activity()
            self.updateGeometry()
            self._commit_stream_row_layout()

    def is_activity_visible(self) -> bool:
        """Return whether the waiting activity row is visible."""
        if self._activity_row is None:
            return False
        return self._activity_row.is_activity_visible()

    def activity_message(self) -> str:
        """Return the current waiting status caption."""
        if self._activity_row is None:
            return ""
        return self._activity_row.message()

    def append_content(self, text: str, *, defer_geometry: bool = False) -> None:
        """Append streaming answer text below the thought block."""
        if not text:
            return
        self._on_answer_stream_start()
        self._ensure_answer_visible()
        if self._markdown_body is not None:
            self._markdown_body.append_markdown(text)
        if defer_geometry:
            return
        self.updateGeometry()
        self._commit_stream_row_layout()

    def _commit_stream_row_layout(self) -> None:
        """Refresh assistant row geometry during streaming."""
        if not self.is_content_streaming():
            return
        self.updateGeometry()

    def set_defer_layout_height_changed(self, defer: bool) -> None:
        """Batch ``layout_height_changed`` emissions during a stream flush."""
        self._defer_layout_height_changed = defer
        if not defer:
            if self._markdown_body is not None:
                self._markdown_body.set_defer_height_changed(False)
            self.flush_stream_layout()

    def flush_stream_layout(self) -> None:
        """Commit deferred row geometry and emit one layout-height notification."""
        self._commit_stream_row_layout()
        self.updateGeometry()
        height_pending = False
        if self._markdown_body is not None:
            height_pending = self._markdown_body.take_deferred_height_pending()
        layout_pending = self._layout_height_pending
        self._layout_height_pending = False
        if layout_pending or height_pending:
            self.layout_height_changed.emit()

    def begin_scroll_compensation_capture(self, block: QWidget) -> None:
        """Record block height before an expand/collapse changes layout."""
        messages = self.parentWidget()
        if messages is None:
            self._scroll_compensation_capture = None
            self._scroll_compensation_block = None
            return
        anchor_y = map_widget_y_to_ancestor(block, messages, offset_y=block.height())
        if anchor_y is None:
            self._scroll_compensation_capture = None
            self._scroll_compensation_block = None
            return
        self._scroll_compensation_capture = (anchor_y, self._block_layout_height(block))
        self._scroll_compensation_block = block

    def consume_scroll_compensation(self) -> tuple[int, int] | None:
        """Return ``(anchor_messages_y, delta_px)`` after a layout toggle, if any."""
        capture = self._scroll_compensation_capture
        block = self._scroll_compensation_block
        self._scroll_compensation_capture = None
        self._scroll_compensation_block = None
        if capture is None or block is None:
            return None
        anchor_y, before_h = capture
        delta_px = self._block_layout_height(block) - before_h
        if delta_px == 0:
            return None
        return anchor_y, delta_px

    def _block_layout_height(self, block: QWidget) -> int:
        """Return *block* height using laid-out or hint geometry only."""
        laid_out = block.height()
        if laid_out > 0:
            return laid_out
        hint_fn = getattr(block, "layout_height_hint", None)
        if callable(hint_fn):
            return max(1, int(hint_fn()))
        return max(1, block.sizeHint().height())

    def _ancestor_chat_panel(self) -> QWidget | None:
        """Return the enclosing ``AiChatPanel``, if this row lives in one."""
        widget: QWidget | None = self
        while widget is not None:
            if widget.objectName() == "aiChatPanel":
                return widget
            widget = widget.parentWidget()
        return None

    def _chat_panel_for_sticky_sync(self) -> QWidget | None:
        """Return ``AiChatPanel`` for transcript rows and viewport sticky clones."""
        return self._ancestor_chat_panel()

    def _apply_row_scroll_compensation(self) -> None:
        """Keep viewport content stable after a row block expands or collapses."""
        compensation = self.consume_scroll_compensation()
        if compensation is None:
            return
        panel = self._ancestor_chat_panel()
        if panel is None or not hasattr(panel, "_compensate_scroll_for_messages_growth"):
            return
        anchor_y, delta_px = compensation
        panel._compensate_scroll_for_messages_growth(self, anchor_y, delta_px)  # type: ignore[attr-defined]

    def _scroll_locked_stream_active(self) -> bool:
        """Return whether auto-follow is driving the viewport for an active stream."""
        panel = self._ancestor_chat_panel()
        if panel is None:
            return False
        return bool(
            self.is_content_streaming()
            and getattr(panel, "_scroll_lock_enabled", False)
            and getattr(panel, "_open_stream_generation", 0) > 0
        )

    def _on_thought_layout_changed(self) -> None:
        """Propagate thought expand/collapse to the transcript scroll layer."""
        deferred = self._defer_layout_height_changed
        if deferred:
            self._layout_height_pending = True
        if not self.is_content_streaming():
            self.clear_stream_layout_floor()
        else:
            self._commit_stream_row_layout()
        self.updateGeometry()
        if self._scroll_locked_stream_active():
            panel = self._ancestor_chat_panel()
            if panel is not None and hasattr(panel, "_follow_streaming_turn_layout"):
                panel._follow_streaming_turn_layout()  # type: ignore[attr-defined]
        elif not deferred:
            self._apply_row_scroll_compensation()
        if not deferred:
            self.layout_height_changed.emit()

    def _on_user_message_layout_changed(self) -> None:
        """Propagate user prompt expand/collapse to the transcript scroll layer."""
        if self._defer_layout_height_changed:
            self._layout_height_pending = True
            return
        self.sync_user_message_height_constraint()
        self.updateGeometry()
        self._apply_row_scroll_compensation()
        self._sync_transcript_user_toggle_to_sticky()
        self.layout_height_changed.emit()

    def _sync_transcript_user_toggle_to_sticky(self) -> None:
        """Refresh the sticky clone when the anchor user prompt toggles."""
        panel = self._chat_panel_for_sticky_sync()
        if panel is None or not hasattr(panel, "_sticky_turn_anchor"):
            return
        if panel._sticky_turn_anchor is not self:  # type: ignore[attr-defined]
            return
        sticky = panel._sticky_turn_prompt  # type: ignore[attr-defined]
        if sticky is None:
            return
        if hasattr(sticky, "sync_expanded_from_anchor"):
            sticky.sync_expanded_from_anchor(self)
        else:
            sticky.sync_user_message_collapse_from(self)
        if hasattr(panel, "_reset_sticky_applied_state"):
            panel._reset_sticky_applied_state()  # type: ignore[attr-defined]
        if hasattr(panel, "_invalidate_sticky_extents"):
            panel._invalidate_sticky_extents()  # type: ignore[attr-defined]
        if hasattr(panel, "_schedule_sticky_sync"):
            panel._schedule_sticky_sync()  # type: ignore[attr-defined]

    def _on_markdown_height_changed(self) -> None:
        """Propagate markdown body height changes to the transcript scroll layer."""
        if self._defer_layout_height_changed:
            self._layout_height_pending = True
            return
        self._commit_stream_row_layout()
        self.updateGeometry()
        self.layout_height_changed.emit()

    def clear_stream_layout_floor(self) -> None:
        """Release any streaming row height constraints after streaming ends."""
        self.setMinimumHeight(0)

    def user_message_frame_height(self) -> int:
        """Return the painted user-bubble frame height (excludes row outer margins)."""
        if self._user_frame is None:
            return max(1, self.height())
        return max(1, self._user_frame.height())

    def set_reflow_deferred(self, deferred: bool) -> None:
        """Defer or resume width reflow for this row during an active pane resize."""
        if self._markdown_body is not None:
            self._markdown_body.set_reflow_deferred(deferred)
        if self._user_section is not None:
            self._user_section.set_reflow_deferred(deferred)

    def flush_deferred_reflow(self) -> None:
        """Flush deferred reflow on child text widgets and refresh row geometry."""
        if self._markdown_body is not None:
            self._markdown_body.flush_deferred_reflow()
        if self._user_section is not None:
            self._user_section.flush_deferred_reflow()
            self.sync_user_message_height_constraint()
        self.updateGeometry()

    def prepare_sticky_overlay(self) -> None:
        """Compact row chrome so a viewport sticky clone can pin flush to the top."""
        if self._role != "user":
            return
        outer = self.layout()
        if outer is not None:
            outer.setContentsMargins(0, 0, 0, 0)
        frame = self._user_frame
        if frame is not None:
            frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            frame.setMaximumHeight(16777215)
        if self._user_section is not None:
            self._user_section._refresh_collapse_layout(force=True)

    def sync_user_message_collapse_from(self, anchor: ChatMessageBubble) -> None:
        """Mirror another user row's expand/collapse state (sticky clone)."""
        anchor_section = anchor._user_section
        if self._user_section is None or anchor_section is None:
            return
        if anchor_section.is_collapsible() or self._user_section.is_collapsible():
            self._user_section.set_expanded(anchor_section._expanded)
        else:
            self._user_section.set_expanded(True)

    def set_user_message_max_height(
        self,
        max_height: int | None,
        *,
        content_width: int | None = None,
    ) -> None:
        """Clamp user-message row height (sticky prompt overlay)."""
        if self._role != "user" or self._user_section is None:
            return
        if max_height is None or max_height <= 0:
            self.setMaximumHeight(_QWIDGET_MAX_HEIGHT)
            self._user_section.apply_viewport_clamp(None)
            return
        width = content_width if content_width is not None else max(1, self.width())
        metrics = self.user_message_sticky_metrics(
            bubble_max_h=max_height,
            content_width=width,
        )
        self.setMaximumHeight(max_height)
        self._user_section.apply_viewport_clamp(metrics.label_height)

    def user_message_sticky_metrics(
        self,
        *,
        bubble_max_h: int,
        content_width: int,
        force_expanded: bool | None = None,
    ) -> UserMessageStickyMetrics:
        """Return explicit sticky-overlay height parts without mutating layout."""
        if self._role != "user" or self._user_section is None or self._user_frame is None:
            return UserMessageStickyMetrics(1, 0, 1, False)

        section = self._user_section
        label_width = self._user_message_label_width(content_width)
        chrome_height = self._user_message_chrome_height(label_width)
        label_budget = max(1, bubble_max_h - chrome_height)
        natural_label_h = section.natural_label_height_for_width(label_width)

        expanded = (
            force_expanded
            if force_expanded is not None
            else (section._expanded or not section.needs_collapse_for_width(label_width))
        )
        collapsible = section.needs_collapse_for_width(label_width)
        if collapsible and not expanded:
            collapsed_cap = section.collapsed_label_height_for_width(label_width)
            cap = collapsed_cap if collapsed_cap is not None else natural_label_h
            label_height = min(natural_label_h, cap, label_budget)
        else:
            label_height = min(natural_label_h, label_budget)

        clamped = label_height < natural_label_h
        total_height = chrome_height + label_height
        return UserMessageStickyMetrics(label_height, chrome_height, total_height, clamped)

    def _user_frame_layout_margins(self) -> tuple[int, int, int, int]:
        """Return ``(left, top, right, bottom)`` margins on the user bubble frame layout."""
        frame = self._user_frame
        if frame is None:
            return (0, 0, 0, 0)
        layout = frame.layout()
        if layout is not None:
            margins = layout.contentsMargins()
            return (
                margins.left(),
                margins.top(),
                margins.right(),
                margins.bottom(),
            )
        margins = frame.contentsMargins()
        return (
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        )

    def _user_message_label_width(self, content_width: int) -> int:
        """Return inner label column width for a proposed bubble width."""
        left, _, right, _ = self._user_frame_layout_margins()
        return max(1, content_width - left - right)

    def _user_message_chrome_height(self, label_width: int) -> int:
        """Return non-label chrome height for sticky sizing at *label_width*."""
        chrome = 0
        frame = self._user_frame
        if frame is None:
            return chrome
        _, top, _, bottom = self._user_frame_layout_margins()
        chrome += top + bottom
        visible_rows = 1
        if self._user_footer is not None:
            chrome += self._user_footer.sizeHint().height()
            visible_rows += 1
        frame_layout = frame.layout()
        if frame_layout is not None and visible_rows > 1:
            chrome += frame_layout.spacing() * (visible_rows - 1)
        if self._user_section is not None:
            chrome += self._user_section.toggle_row_height_for_width(label_width)
        return chrome

    def append_text(self, text: str) -> None:
        """Append answer text (legacy alias for content-only streaming)."""
        self.append_content(text)

    def set_parts(self, *, thinking: str, content: str, collapse_thinking: bool = True) -> None:
        """Replace thinking and answer text."""
        if self._thought_section is not None:
            self._thought_section.set_text(thinking)
            if thinking.strip():
                self._thought_section.finalize_thinking(collapse=collapse_thinking)
            else:
                self._thought_section.setVisible(False)
        if self._markdown_body is not None:
            self._markdown_body.set_markdown(content)
        elif self._user_section is not None:
            self._user_section.set_text(content)
        if content.strip():
            self._answer_started = True
            self._ensure_answer_visible()
        elif not thinking.strip() and not self._answer_visible and self._markdown_body is not None:
            self._markdown_body.hide()
        self.updateGeometry()

    def set_text(self, text: str) -> None:
        """Replace the answer text only."""
        if self._markdown_body is not None:
            self._markdown_body.set_markdown(text)
        elif self._user_section is not None:
            self._user_section.set_text(text)
        if text.strip():
            self._answer_started = True
            self._ensure_answer_visible()
        self.updateGeometry()
