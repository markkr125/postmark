"""Assemble chat markdown into a single HTML document for QTextBrowser."""

from __future__ import annotations

import re
from html import escape as html_escape

from PySide6.QtGui import QTextDocument

from ui.sidebar.ai.markdown.fence_split import (
    CodeSegment,
    MarkdownSegment,
    ProseSegment,
    split_fenced_blocks,
)
from ui.sidebar.ai.markdown.highlight_code import highlight_code_to_html
from ui.styling.theme import ThemePalette, current_palette

_INLINE_CODE_RE = re.compile(r"<code>(.*?)</code>", re.DOTALL | re.IGNORECASE)
_QT_MONO_SPAN_RE = re.compile(
    r'<span style=" font-family:\'monospace\';">(.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)


def _strip_qt_html_wrapper(html: str) -> str:
    """Return the inner body fragment from Qt markdown HTML."""
    lower = html.lower()
    body_start = lower.find("<body")
    if body_start < 0:
        return html
    body_tag_end = html.find(">", body_start)
    if body_tag_end < 0:
        return html
    body_close = lower.rfind("</body>")
    if body_close < 0:
        return html[body_tag_end + 1 :]
    return html[body_tag_end + 1 : body_close]


def _prose_chunk_to_html(chunk: str, *, palette: ThemePalette) -> str:
    """Render a prose markdown chunk via Qt and style inline code pills."""
    if not chunk:
        return ""
    doc = QTextDocument()
    doc.setMarkdown(chunk)
    fragment = _strip_qt_html_wrapper(doc.toHtml())
    return _style_inline_code(fragment, palette=palette)


def _style_inline_code(html_fragment: str, *, palette: ThemePalette) -> str:
    """Wrap Qt inline-code spans with themed pill styles."""
    bg = html_escape(palette["bg_alt"])
    border = html_escape(palette["border"])
    text = html_escape(palette["text"])
    pill_style = (
        f"background:{bg};border:1px solid {border};color:{text};"
        "font-family:monospace;padding:1px 4px;border-radius:4px;"
    )

    def _replace(match: re.Match[str]) -> str:
        inner = match.group(1)
        return f'<span style="{pill_style}">{inner}</span>'

    styled = _INLINE_CODE_RE.sub(_replace, html_fragment)
    return _QT_MONO_SPAN_RE.sub(_replace, styled)


def render_markdown_body_html(markdown: str, *, palette: ThemePalette | None = None) -> str:
    """Render assistant markdown to an HTML body fragment (no document wrapper)."""
    active = palette or current_palette()
    segments = split_fenced_blocks(markdown)
    return "".join(_render_segment(segment, palette=active) for segment in segments)


def render_chat_markdown_html(
    markdown: str,
    *,
    palette: ThemePalette | None = None,
) -> str:
    """Render assistant markdown to HTML with themed fenced code blocks."""
    active = palette or current_palette()
    body = render_markdown_body_html(markdown, palette=active)
    text_color = html_escape(active["text"])
    return (
        f'<html><head></head><body style="color:{text_color};'
        f'margin:0;padding:0;">{body}</body></html>'
    )


def render_segment_html(segment: MarkdownSegment, *, palette: ThemePalette) -> str:
    """Render one prose or code segment."""
    return _render_segment(segment, palette=palette)


def _render_segment(segment: MarkdownSegment, *, palette: ThemePalette) -> str:
    """Render one prose or code segment."""
    if isinstance(segment, ProseSegment):
        return _prose_chunk_to_html(segment.text, palette=palette)
    if isinstance(segment, CodeSegment):
        if segment.provisional:
            from ui.sidebar.ai.markdown.highlight_code import provisional_code_to_html

            return provisional_code_to_html(segment.code, segment.lang, palette=palette)
        return highlight_code_to_html(
            segment.code,
            segment.lang,
            palette=palette,
            line_numbers=True,
        )
    raise TypeError(f"Unsupported segment type: {type(segment)!r}")
