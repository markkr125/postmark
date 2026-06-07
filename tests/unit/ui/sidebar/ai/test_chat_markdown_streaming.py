"""Tests for streaming vs finalized markdown rendering."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from ui.sidebar.ai.message_bubble import ChatMessageBubble, _MarkdownContent


@pytest.fixture
def _qapp_for_markdown(qapp: QApplication) -> QApplication:
    """Ensure a QApplication exists for widget tests."""
    return qapp


class TestMarkdownContentStreaming:
    """Tests for :class:`_MarkdownContent` streaming mode."""

    def test_streaming_renders_markdown_html(self, _qapp_for_markdown: QApplication, qtbot) -> None:
        """While streaming, append re-renders rich HTML on each update."""
        body = _MarkdownContent()
        qtbot.addWidget(body)
        body.resize(360, 480)
        body.begin_streaming()
        body.append_markdown("**Hello**")
        assert body.is_streaming()
        assert body.markdown() == "**Hello**"
        html = body.toHtml().lower()
        assert "font-weight:600" in html or "font-weight:700" in html

    def test_end_streaming_clears_stream_flag(
        self, _qapp_for_markdown: QApplication, qtbot
    ) -> None:
        """Finalize clears the streaming flag."""
        body = _MarkdownContent()
        qtbot.addWidget(body)
        body.resize(360, 480)
        body.begin_streaming()
        body.append_markdown("**Hello**")
        body.end_streaming(render=True)
        assert not body.is_streaming()
        html = body.toHtml().lower()
        assert "font-weight:600" in html or "font-weight:700" in html

    def test_closed_fence_highlights_during_streaming(
        self, _qapp_for_markdown: QApplication, qtbot
    ) -> None:
        """Closed fenced code is highlighted while the stream remains open."""
        body = _MarkdownContent("```python\nprint(1)\n```")
        qtbot.addWidget(body)
        body.resize(360, 480)
        body.begin_streaming()
        body.append_markdown("\n")
        html = body.toHtml().lower()
        assert "python" in html
        assert "<table" in html
        assert "```python" not in html


class TestChatMessageBubbleStreaming:
    """Tests for :class:`ChatMessageBubble` streaming lifecycle."""

    def test_begin_and_end_streaming(self, _qapp_for_markdown: QApplication, qtbot) -> None:
        """Bubble enters and leaves content streaming mode."""
        bubble = ChatMessageBubble("assistant", "")
        qtbot.addWidget(bubble)
        bubble.begin_streaming()
        assert bubble.is_content_streaming()
        bubble.append_content("Hi")
        bubble.end_streaming(render=False)
        assert not bubble.is_content_streaming()

    def test_theme_change_rerenders_markdown_during_streaming(
        self, _qapp_for_markdown: QApplication, qtbot
    ) -> None:
        """Theme re-render keeps rich markdown while a stream is open."""
        from ui.sidebar.ai.message_bubble import rerender_all_markdown_browsers

        body = _MarkdownContent()
        qtbot.addWidget(body)
        body.resize(360, 480)
        body.begin_streaming()
        body.append_markdown("**Hello**")
        assert body.is_streaming()
        rerender_all_markdown_browsers()
        assert body.is_streaming()
        html = body.toHtml().lower()
        assert "font-weight:600" in html or "font-weight:700" in html
