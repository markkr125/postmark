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


def test_end_streaming_remeasures_height_at_unchanged_width(
    qapp: QApplication,
    qtbot,
) -> None:
    """Final full render must resize the body even when pane width is unchanged."""
    browser = MarkdownContent()
    qtbot.addWidget(browser)
    browser.resize(360, 400)
    browser.show()
    qtbot.waitExposed(browser)

    markdown = (
        "| OS | Notes |\n| --- | --- |\n| macOS | Unix-like |\n| Linux | Free |\n\n"
        + ("Wrap paragraph text. " * 30)
        + "primary target platform—and the tail sentence must fit."
    )
    browser.begin_streaming()
    browser.append_markdown(markdown)
    height_streaming = browser.height()
    browser.setFixedHeight(max(1, height_streaming - 40))

    browser.end_streaming()

    layout = browser.document().documentLayout()
    doc_h = layout.documentSize().height()
    max_bottom = doc_h
    block = browser.document().begin()
    while block != browser.document().end():
        max_bottom = max(max_bottom, layout.blockBoundingRect(block).bottom())
        block = block.next()
    assert browser.height() >= int(max_bottom)
    assert browser.height() >= height_streaming - 40


def test_resync_height_for_footer_bypasses_deferred_reflow(
    qapp: QApplication,
    qtbot,
) -> None:
    """Footer resync must measure even when reflow was deferred."""
    browser = MarkdownContent("Line one\n\nLine two with more text at the end.")
    qtbot.addWidget(browser)
    browser.resize(280, 120)
    browser.show()
    qtbot.waitExposed(browser)
    short_height = max(1, browser.height() - 30)
    browser.setFixedHeight(short_height)
    browser.set_reflow_deferred(True)

    browser.resync_height_for_footer()

    layout = browser.document().documentLayout()
    max_bottom = layout.documentSize().height()
    block = browser.document().begin()
    while block != browser.document().end():
        max_bottom = max(max_bottom, layout.blockBoundingRect(block).bottom())
        block = block.next()
    assert browser.height() >= int(max_bottom)
    assert not browser._reflow_deferred


def test_lazy_render_measures_full_height_during_resize_coalescing(
    qapp: QApplication,
    qtbot,
) -> None:
    """Lazy materialisation must not keep the placeholder height while coalescing."""
    markdown = (
        "| OS | Notes |\n| --- | --- |\n| macOS | Unix-like |\n\n"
        + ("Wrap paragraph text. " * 24)
        + "platform—and the tail sentence must fit."
    )

    class _CoalescingHost(QWidget):
        """Stand-in chat panel reporting an active resize pass."""

        def is_resize_coalescing(self) -> bool:
            return True

    host = _CoalescingHost()
    layout = QVBoxLayout(host)
    browser = MarkdownContent()
    layout.addWidget(browser)
    qtbot.addWidget(host)
    host.resize(360, 800)
    host.show()
    qtbot.waitExposed(host)

    browser.set_markdown_lazy(markdown)
    placeholder_height = browser.height()
    browser.ensure_rendered()

    doc_layout = browser.document().documentLayout()
    max_bottom = doc_layout.documentSize().height()
    block = browser.document().begin()
    while block != browser.document().end():
        max_bottom = max(max_bottom, doc_layout.blockBoundingRect(block).bottom())
        block = block.next()

    assert browser.height() > placeholder_height
    assert browser.height() >= int(max_bottom)
