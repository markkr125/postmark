"""Incremental streaming markdown HTML assembly for assistant answers."""

from __future__ import annotations

from html import escape as html_escape

from ui.sidebar.ai.markdown.fence_split import (MarkdownSegment,
                                                split_fenced_blocks)
from ui.sidebar.ai.markdown.render import render_segment_html
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
    ) -> str:
        """Incrementally render *markdown* and return a full QTextBrowser HTML document."""
        active = palette or current_palette()
        segments = split_fenced_blocks(markdown)
        change_at = first_changed_segment_index(self._segments, segments)
        stable_html = self._segment_html[:change_at]

        rendered = list(stable_html)
        for index in range(change_at, len(segments)):
            rendered.append(render_segment_html(segments[index], palette=active))

        self._segments = segments
        self._segment_html = rendered
        body = "".join(rendered)
        return wrap_markdown_body_html(body, palette=active)

    @property
    def segment_count(self) -> int:
        """Return the number of cached rendered segments."""
        return len(self._segment_html)
