"""Custom markdown rendering for AI chat assistant answers."""

from __future__ import annotations

from ui.sidebar.ai.markdown.fence_split import (
    CodeSegment,
    MarkdownSegment,
    ProseSegment,
    split_fenced_blocks,
)
from ui.sidebar.ai.markdown.highlight_code import (
    clear_highlight_cache,
    highlight_code_to_html,
    normalize_language,
    provisional_code_to_html,
)
from ui.sidebar.ai.markdown.render import (
    render_chat_markdown_html,
    render_markdown_body_html,
    render_segment_html,
)
from ui.sidebar.ai.markdown.streaming_render import StreamingMarkdownCache

__all__ = [
    "CodeSegment",
    "MarkdownSegment",
    "ProseSegment",
    "StreamingMarkdownCache",
    "clear_highlight_cache",
    "highlight_code_to_html",
    "normalize_language",
    "provisional_code_to_html",
    "render_chat_markdown_html",
    "render_markdown_body_html",
    "render_segment_html",
    "split_fenced_blocks",
]
