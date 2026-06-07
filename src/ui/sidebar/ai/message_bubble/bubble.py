"""Chat message row widget for the AI assistant transcript."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QResizeEvent
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.sidebar.ai.chat_sessions.time_format import format_message_sent_at

from ui.sidebar.ai.message_bubble.activity_row import AssistantActivityRow
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent
from ui.sidebar.ai.message_bubble.thought_section import ThoughtSection
from ui.sidebar.ai.message_bubble.wrapping_label import _WrappingLabel
from ui.styling.theme import current_palette

ChatRole = Literal["user", "assistant"]

_USER_MESSAGE_FADE_HEIGHT_PX = 28


class _UserMessageBottomFade(QWidget):
    """Gradient fade at the bottom of a height-clamped user message bubble."""

    def __init__(self, parent: QWidget) -> None:
        """Build a mouse-transparent fade strip over the user bubble frame."""
        super().__init__(parent)
        self.setObjectName("aiChatUserMessageFade")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedHeight(_USER_MESSAGE_FADE_HEIGHT_PX)

    def paintEvent(self, _event: object) -> None:
        """Paint a vertical fade from transparent to the user bubble background."""
        palette = current_palette()
        base = QColor(palette["bg_alt"])
        gradient = QLinearGradient(0.0, 0.0, 0.0, float(self.height()))
        gradient.setColorAt(0.0, QColor(base.red(), base.green(), base.blue(), 0))
        gradient.setColorAt(1.0, base)
        painter = QPainter(self)
        painter.fillRect(self.rect(), gradient)


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
        self._user_message_fade: _UserMessageBottomFade | None = None
        self._user_label: _WrappingLabel | None = None
        self._user_timestamp: QLabel | None = None
        self._sent_at: datetime | None = sent_at if role == "user" else None
        self._markdown_body: MarkdownContent | None = None
        self._answer_visible = bool(text.strip())
        self._answer_started = bool(text.strip())
        self._stream_row_floor_px = 0
        self._defer_layout_height_changed = False
        self._layout_height_pending = False

        if role == "user":
            frame = QFrame()
            frame.setObjectName("aiChatMessageUser")
            frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            frame.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            )
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(12, 10, 12, 10)
            frame_layout.setSpacing(0)
            self._user_label = _WrappingLabel(text)
            self._user_label.setObjectName("aiChatUserMessageText")
            frame_layout.addWidget(self._user_label)
            self._user_timestamp = QLabel()
            self._user_timestamp.setObjectName("aiChatUserMessageTime")
            self._user_timestamp.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            if sent_at is not None:
                self._user_timestamp.setText(format_message_sent_at(sent_at))
                frame_layout.addWidget(self._user_timestamp)
            else:
                self._user_timestamp.hide()
            self._user_frame = frame
            self._user_message_fade = _UserMessageBottomFade(frame)
            self._user_message_fade.hide()
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

            self._markdown_body = MarkdownContent(text)
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
        if self._user_label is not None:
            return self._user_label.text()
        return ""

    def sent_at(self) -> datetime | None:
        """Return the user-message send time, if any."""
        return self._sent_at

    def thinking_text(self) -> str:
        """Return the thinking text, if any."""
        if self._thought_section is None:
            return ""
        return self._thought_section.text()

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
        self.layout_height_changed.emit()

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

    def _position_user_message_fade(self) -> None:
        """Place the bottom fade strip over the user bubble frame."""
        fade = self._user_message_fade
        frame = self._user_frame
        if fade is None or frame is None or not fade.isVisible():
            return
        fade.setFixedWidth(frame.width())
        fade.move(0, max(0, frame.height() - fade.height()))

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Reposition the user-message fade when the row is resized."""
        super().resizeEvent(event)
        self._position_user_message_fade()

    def set_user_message_max_height(self, max_height: int | None) -> None:
        """Clamp user-message row height (sticky prompt overlay)."""
        if self._role != "user":
            return
        if max_height is None or max_height <= 0:
            self.setMaximumHeight(16777215)
            if self._user_message_fade is not None:
                self._user_message_fade.hide()
            return
        self.setMaximumHeight(max_height)
        if self._user_message_fade is not None:
            self._user_message_fade.show()
            self._position_user_message_fade()

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
        elif self._user_label is not None:
            self._user_label.setText(content)
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
        elif self._user_label is not None:
            self._user_label.setText(text)
        if text.strip():
            self._answer_started = True
            self._ensure_answer_visible()
        self.updateGeometry()
