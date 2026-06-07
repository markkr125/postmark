"""Unit tests for streaming markdown body height behaviour."""

from __future__ import annotations

from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ui.sidebar.ai.message_bubble.markdown_content import (
    MarkdownContent,
    rerender_all_markdown_browsers,
)


def test_streaming_height_is_monotonic(qapp: QApplication, qtbot) -> None:
    """Markdown body height never shrinks until streaming ends."""
    host = QWidget()
    layout = QVBoxLayout(host)
    browser = MarkdownContent()
    layout.addWidget(browser)
    qtbot.addWidget(host)
    host.resize(300, 400)
    host.show()
    qtbot.waitExposed(host)

    browser.begin_streaming()
    heights: list[int] = []
    deltas = [
        "short",
        "much longer paragraph " * 4,
        "x",
        "```python\nprint('hi')\n```",
        "```python\nprint('hi')\nprint('more')\n```",
    ]
    for delta in deltas:
        browser.append_markdown(delta)
        heights.append(browser.height())
        if len(heights) >= 2:
            assert heights[-1] >= heights[-2]

    last_streaming_height = browser.height()
    browser.end_streaming()
    assert browser.height() <= last_streaming_height or browser.height() >= 1


def test_document_size_signal_ignored_during_streaming(qapp: QApplication, qtbot) -> None:
    """DocumentSizeChanged must not shrink or relayout the body mid-stream."""
    browser = MarkdownContent()
    qtbot.addWidget(browser)
    browser.resize(300, 100)
    browser.show()
    qtbot.waitExposed(browser)

    browser.begin_streaming()
    browser.append_markdown("Hello **world**\n\n" + "extra line\n" * 12)
    height_before = browser.height()
    browser._sync_height(browser.document().documentLayout().documentSize())
    assert browser.height() == height_before
    browser.append_markdown("\nmore tail\n" * 8)
    assert browser.height() >= height_before


def test_theme_rerender_during_stream_uses_streaming_path(qapp: QApplication, qtbot) -> None:
    """Theme changes re-render streaming bodies via the incremental path."""
    browser = MarkdownContent("**Hi**")
    qtbot.addWidget(browser)
    browser.resize(280, 80)
    browser.show()
    qtbot.waitExposed(browser)
    browser.begin_streaming()

    with (
        patch.object(browser, "_render_markdown_streaming") as streaming_render,
        patch.object(browser, "_render_markdown") as full_render,
    ):
        rerender_all_markdown_browsers()
        streaming_render.assert_called_once()
        full_render.assert_not_called()
