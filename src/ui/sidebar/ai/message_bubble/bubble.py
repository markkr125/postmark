"""Chat message row widget for the AI assistant transcript."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, NamedTuple

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.sidebar.ai.message_bubble.activity_row import AssistantActivityRow
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent
from ui.sidebar.ai.message_bubble.thought_section import ThoughtSection
from ui.sidebar.ai.message_bubble.user_message import (UserMessageFooterRow,
                                                       UserMessageSection)

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
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 6)
        outer.setSpacing(0)

        self._thought_section: ThoughtSection | None = None
        self._activity_row: AssistantActivityRow | None = None
        self._user_frame: QFrame | None = None
        self._user_section: UserMessageSection | None = None
        self._user_footer: UserMessageFooterRow | None = None
        self._sent_at: datetime | None = sent_at if role == "user" else None
        self._markdown_body: MarkdownContent | None = None
        self._answer_visible = bool(text.strip())
        self._answer_started = bool(text.strip())
        self._stream_row_floor_px = 0
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
                QSizePolicy.Policy.Minimum,
            )
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(12, 6, 12, 6)
            frame_layout.setSpacing(0)
            self._user_section = UserMessageSection(text, frame)
            self._user_section.layout_height_changed.connect(self._on_user_message_layout_changed)
            frame_layout.addWidget(self._user_section)
            self._user_footer = UserMessageFooterRow(frame)
            self._user_footer.set_sent_at(sent_at)
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
        self._stream_row_floor_px = 0
        self.setMinimumHeight(0)
        self._commit_stream_row_layout()

    @property
    def role(self) -> ChatRole:
        """Return the message role."""
        return self._role

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

    def begin_streaming(self) -> None:
        """Mark the answer body as receiving streamed markdown."""
        self._stream_row_floor_px = 0
        if self._markdown_body is not None:
            self._markdown_body.begin_streaming()

    def end_streaming(self, *, render: bool = True) -> None:
        """Mark streaming complete on the answer body."""
        if self._markdown_body is not None:
            self._markdown_body.end_streaming(render=render)

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
        """Keep total assistant row height monotonic while streaming."""
        if not self.is_content_streaming():
            return
        self.updateGeometry()
        natural_h = self.sizeHint().height()
        self._stream_row_floor_px = max(self._stream_row_floor_px, natural_h)
        target_min = max(self._stream_row_floor_px, self.minimumHeight())
        if self.minimumHeight() != target_min:
            self.setMinimumHeight(target_min)

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
        anchor_y = block.mapTo(messages, QPoint(0, block.height())).y()
        self._scroll_compensation_capture = (anchor_y, block.sizeHint().height())
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
        delta_px = block.sizeHint().height() - before_h
        if delta_px == 0:
            return None
        return anchor_y, delta_px

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

    def _on_thought_layout_changed(self) -> None:
        """Propagate thought expand/collapse to the transcript scroll layer."""
        if self._defer_layout_height_changed:
            self._layout_height_pending = True
            return
        if not self.is_content_streaming():
            self.clear_stream_layout_floor()
        else:
            self._commit_stream_row_layout()
        self.updateGeometry()
        self._apply_row_scroll_compensation()
        self.layout_height_changed.emit()

    def _on_user_message_layout_changed(self) -> None:
        """Propagate user prompt expand/collapse to the transcript scroll layer."""
        if self._defer_layout_height_changed:
            self._layout_height_pending = True
            return
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
        """Release monotonic row height constraints after streaming ends."""
        self._stream_row_floor_px = 0
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

    def _user_message_label_width(self, content_width: int) -> int:
        """Return inner label column width for a proposed bubble width."""
        frame = self._user_frame
        if frame is None:
            return max(1, content_width)
        margins = frame.contentsMargins()
        return max(1, content_width - margins.left() - margins.right())

    def _user_message_chrome_height(self, label_width: int) -> int:
        """Return non-label chrome height for sticky sizing at *label_width*."""
        chrome = 0
        frame = self._user_frame
        if frame is None:
            return chrome
        margins = frame.contentsMargins()
        chrome += margins.top() + margins.bottom()
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
