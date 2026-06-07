"""Tests for chat markdown fence splitting."""

from __future__ import annotations

from ui.sidebar.ai.markdown.fence_split import CodeSegment, ProseSegment, split_fenced_blocks


class TestSplitFencedBlocks:
    """Tests for :func:`split_fenced_blocks`."""

    def test_closed_fence(self) -> None:
        source = "Before\n\n```python\nprint(1)\n```\n\nAfter"
        segments = split_fenced_blocks(source)
        assert len(segments) == 3
        assert isinstance(segments[0], ProseSegment)
        assert segments[0].text == "Before\n\n"
        assert isinstance(segments[1], CodeSegment)
        assert segments[1].lang == "python"
        assert segments[1].code == "print(1)\n"
        assert segments[1].provisional is False
        assert isinstance(segments[2], ProseSegment)
        assert segments[2].text == "\nAfter"

    def test_open_streaming_tail(self) -> None:
        source = "```py\nimport os\npartial"
        segments = split_fenced_blocks(source)
        assert len(segments) == 1
        assert isinstance(segments[0], CodeSegment)
        assert segments[0].lang == "py"
        assert segments[0].code == "import os\npartial"
        assert segments[0].provisional is True

    def test_inline_backticks_not_fences(self) -> None:
        source = "Use `inline` and not a fence."
        segments = split_fenced_blocks(source)
        assert len(segments) == 1
        assert isinstance(segments[0], ProseSegment)
        assert segments[0].text == source

    def test_empty_string(self) -> None:
        segments = split_fenced_blocks("")
        assert len(segments) == 1
        assert isinstance(segments[0], ProseSegment)
        assert segments[0].text == ""
