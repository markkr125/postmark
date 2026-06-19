"""Tests for incremental streaming GFM table rendering."""

from __future__ import annotations

from ui.sidebar.ai.markdown.streaming_table import (
    StreamingTableRenderer,
    is_complete_markdown_table,
    render_inline_markdown,
    split_prose_prefix_and_table,
)
from ui.styling.theme import DARK_PALETTE


def test_split_prose_prefix_and_table_splits_heading() -> None:
    """A markdown heading directly above a table is prose, not a header row."""
    block = (
        "### **Why People Get Confused:**\n"
        "| Mistake | Fix |\n"
        "|---------|-----|\n"
        "| Forgot `chmod +x` | Run `chmod +x script` |"
    )
    prose, table = split_prose_prefix_and_table(block)
    assert "Why People Get Confused" in prose
    assert prose.startswith("###")
    assert table.startswith("| Mistake")
    assert "|---------|" in table


def test_table_after_heading_renders_without_pre_fallback() -> None:
    """Renderer locates the real header row when prose precedes the table."""
    block = "### Heading\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    html = StreamingTableRenderer().render_html(block, palette=DARK_PALETTE).lower()
    assert "<table" in html
    assert "<pre" not in html


def test_header_and_separator_render_table_shell() -> None:
    """Header plus separator produce a themed table without a pre fallback."""
    block = "| Phase | What happens |\n|---|---|\n"
    renderer = StreamingTableRenderer()
    html = renderer.render_html(block, palette=DARK_PALETTE).lower()
    assert "<table" in html
    assert "<thead" in html
    assert "<tbody" in html
    assert "<pre" not in html
    assert renderer.committed_row_count == 0


def test_committed_row_increments_renderer_state() -> None:
    """Each completed data row increases the committed row count."""
    block = (
        "| Phase | What happens |\n"
        "|---|---|\n"
        "| **ClientHello** | Client lists supported TLS versions |\n"
    )
    renderer = StreamingTableRenderer()
    html = renderer.render_html(block, palette=DARK_PALETTE).lower()
    assert renderer.committed_row_count == 1
    assert html.count("<tr>") == 2
    assert "<strong>clienthello</strong>" in html


def test_provisional_row_renders_inside_table() -> None:
    """The in-flight row appears as a muted table row, not monospace pre."""
    block = "| Phase | What happens |\n|---|---|\n| **ClientHello** | Client lists"
    renderer = StreamingTableRenderer()
    html = renderer.render_html(block, palette=DARK_PALETTE).lower()
    assert "<table" in html
    assert "<pre" not in html
    assert "client lists" in html
    assert renderer.committed_row_count == 0


def test_is_complete_requires_no_provisional_tail() -> None:
    """Completeness ignores a trailing partial row."""
    complete = "| A | B |\n|---|---|\n| 1 | 2 |\n"
    incomplete = "| A | B |\n|---|---|\n| 1 | 2"
    assert is_complete_markdown_table(complete)
    assert not is_complete_markdown_table(incomplete)


def test_inline_bold_renders_strong() -> None:
    """Closed bold markers render as strong elements."""
    html = render_inline_markdown("**Opera**", palette=DARK_PALETTE).lower()
    assert "<strong>opera</strong>" in html
    assert "**" not in html


def test_unclosed_bold_stays_literal() -> None:
    """Unclosed bold delimiters remain literal during conservative streaming."""
    html = render_inline_markdown("**Opera", palette=DARK_PALETTE, conservative=True)
    assert "<strong>" not in html.lower()
    assert "**Opera" in html


def test_inline_code_renders_pill() -> None:
    """Inline code uses monospace pill styling."""
    html = render_inline_markdown("Use `GET` here", palette=DARK_PALETTE).lower()
    assert "font-family:monospace" in html
    assert "get" in html
    assert "`" not in html


def test_inline_link_renders_anchor() -> None:
    """Markdown links render escaped anchors."""
    html = render_inline_markdown("[docs](https://example.com)", palette=DARK_PALETTE).lower()
    assert '<a href="https://example.com"' in html
    assert "docs" in html


def test_cell_cache_reuses_unchanged_committed_cells() -> None:
    """Committed cell HTML is cached when the table grows with a provisional row."""
    renderer = StreamingTableRenderer()
    block1 = "| Browser | Notes |\n|---|---|\n| **Opera** | Fast |\n"
    renderer.render_html(block1, palette=DARK_PALETTE)
    calls_after_first = renderer.inline_render_calls

    block2 = "| Browser | Notes |\n|---|---|\n| **Opera** | Fast |\n| **Vivaldi"
    renderer.render_html(block2, palette=DARK_PALETTE)
    assert renderer.inline_render_calls > calls_after_first
    assert renderer.inline_render_calls < calls_after_first + 4
