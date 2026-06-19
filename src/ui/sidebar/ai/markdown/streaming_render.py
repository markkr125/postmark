"""Incremental streaming markdown HTML assembly for assistant answers."""

from __future__ import annotations

from html import escape as html_escape

from ui.sidebar.ai.markdown.copy_chrome import CodeCopyChrome
from ui.sidebar.ai.markdown.fence_split import (
    CodeSegment,
    MarkdownSegment,
    ProseSegment,
    split_fenced_blocks,
)
from ui.sidebar.ai.markdown.render import render_segment_html
from ui.sidebar.ai.markdown.streaming_table import (
    StreamingTableRenderer,
    is_complete_markdown_table,
    is_table_separator_line,
    markdown_table_cells,
    split_prose_prefix_and_table,
)
from ui.styling.theme import ThemePalette, current_palette


def segment_identity(segment: MarkdownSegment) -> tuple[str, ...]:
    """Return a hashable identity for *segment* used to detect changes."""
    from ui.sidebar.ai.markdown.fence_split import CodeSegment, ProseSegment

    if isinstance(segment, ProseSegment):
        return ("prose", segment.text)
    if isinstance(segment, CodeSegment):
        return ("code", segment.lang, segment.code, str(segment.provisional))
    raise TypeError(f"Unsupported segment type: {type(segment)!r}")


def first_changed_segment_index(
    previous: list[MarkdownSegment],
    current: list[MarkdownSegment],
) -> int:
    """Return the first segment index that differs between *previous* and *current*."""
    limit = min(len(previous), len(current))
    for index in range(limit):
        if segment_identity(previous[index]) != segment_identity(current[index]):
            return index
    if len(previous) != len(current):
        return limit
    return len(current)


def wrap_markdown_body_html(body: str, *, palette: ThemePalette) -> str:
    """Wrap a rendered body fragment in the QTextBrowser document envelope."""
    text_color = html_escape(palette["text"])
    return (
        f'<html><head></head><body style="color:{text_color};'
        f'margin:0;padding:0;">{body}</body></html>'
    )


def _looks_like_markdown_table_block(lines: list[str]) -> bool:
    """Return whether *lines* contain markdown pipe-table syntax."""
    if len(lines) < 2:
        return False
    pipe_rows = [line for line in lines if "|" in line]
    if len(pipe_rows) < 2:
        return False
    return any(is_table_separator_line(line) for line in lines)


def _render_streaming_table_html(
    block: str,
    *,
    table_renderer: StreamingTableRenderer,
    palette: ThemePalette,
) -> str:
    """Render one pipe-table block, falling back to monospace pre when malformed."""
    lines = [line for line in block.splitlines() if line.strip()]
    if not _looks_like_markdown_table_block(lines):
        return ""
    table_html = table_renderer.render_html(block, palette=palette)
    if table_html:
        return table_html
    return StreamingTableRenderer._fallback_pre(block, palette=palette)


def _render_streaming_prose_html(text: str, *, palette: ThemePalette) -> str:
    """Render prose for an open stream with incremental pipe-table rows."""
    if "|" not in text:
        return render_segment_html(ProseSegment(text), palette=palette)
    blocks = text.split("\n\n")
    parts: list[str] = []
    table_renderer = StreamingTableRenderer()
    for block in blocks:
        prose_prefix, table_block = split_prose_prefix_and_table(block)
        if prose_prefix:
            parts.append(render_segment_html(ProseSegment(prose_prefix), palette=palette))
        if table_block:
            table_html = _render_streaming_table_html(
                table_block,
                table_renderer=table_renderer,
                palette=palette,
            )
            if table_html:
                parts.append(table_html)
            else:
                parts.append(render_segment_html(ProseSegment(table_block), palette=palette))
        elif not prose_prefix:
            lines = [line for line in block.splitlines() if line.strip()]
            if _looks_like_markdown_table_block(lines):
                parts.append(
                    _render_streaming_table_html(
                        block,
                        table_renderer=table_renderer,
                        palette=palette,
                    )
                )
            else:
                parts.append(render_segment_html(ProseSegment(block), palette=palette))
    return "".join(parts)


class StreamingMarkdownCache:
    """Reuse stable segment HTML while the live tail of a stream changes."""

    def __init__(self) -> None:
        """Create an empty streaming render cache."""
        self._segments: list[MarkdownSegment] = []
        self._segment_html: list[str] = []

    def clear(self) -> None:
        """Drop cached segment HTML."""
        self._segments = []
        self._segment_html = []

    def render_document_html(
        self,
        markdown: str,
        *,
        palette: ThemePalette | None = None,
        copy_chrome: CodeCopyChrome | None = None,
    ) -> str:
        """Incrementally render *markdown* and return a full QTextBrowser HTML document."""
        active = palette or current_palette()
        chrome = copy_chrome or CodeCopyChrome()
        segments = split_fenced_blocks(markdown)
        change_at = first_changed_segment_index(self._segments, segments)
        stable_html = self._segment_html[:change_at]

        rendered = list(stable_html)
        code_index = sum(1 for segment in segments[:change_at] if isinstance(segment, CodeSegment))
        if chrome.confirmed_index is not None or chrome.hover_index is not None:
            change_at = 0
            rendered = []
            code_index = 0
        for index in range(change_at, len(segments)):
            segment = segments[index]
            block_index = code_index if isinstance(segment, CodeSegment) else None
            if isinstance(segment, ProseSegment):
                rendered.append(_render_streaming_prose_html(segment.text, palette=active))
            else:
                rendered.append(
                    render_segment_html(
                        segment,
                        palette=active,
                        block_index=block_index,
                        copy_chrome=chrome,
                    )
                )
            if isinstance(segment, CodeSegment):
                code_index += 1

        self._segments = segments
        self._segment_html = rendered
        body = "".join(rendered)
        return wrap_markdown_body_html(body, palette=active)

    @property
    def segment_count(self) -> int:
        """Return the number of cached rendered segments."""
        return len(self._segment_html)


__all__ = [
    "StreamingMarkdownCache",
    "first_changed_segment_index",
    "is_complete_markdown_table",
    "markdown_table_cells",
    "segment_identity",
    "wrap_markdown_body_html",
]
