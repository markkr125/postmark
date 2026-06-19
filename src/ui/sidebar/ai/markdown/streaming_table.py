"""Incremental GFM pipe-table HTML for streaming assistant markdown."""

from __future__ import annotations

import re
from html import escape as html_escape
from typing import NamedTuple

from ui.styling.theme import ThemePalette

_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?$")
_INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_INLINE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_INLINE_STRIKE_RE = re.compile(r"~~(.+?)~~")
_INLINE_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)|(?<!_)_([^_]+)_(?!_)")


class _InlineMatch(NamedTuple):
    """One inline markdown token match inside a table cell."""

    start: int
    end: int
    kind: str
    groups: tuple[str, ...]


def markdown_table_cells(line: str) -> list[str]:
    """Split one pipe-table row into trimmed cell strings."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def is_table_separator_line(line: str) -> bool:
    """Return whether *line* is a GFM table header separator."""
    return bool(_TABLE_SEPARATOR_RE.match(line.strip()))


def is_complete_markdown_table(block: str) -> bool:
    """Return whether *block* is a complete GFM pipe table with no provisional tail."""
    if block and not block.endswith("\n"):
        return False
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    header, separator, *data_rows = lines
    if "|" not in header or not is_table_separator_line(separator):
        return False
    column_count = len(markdown_table_cells(header))
    if column_count < 2 or len(markdown_table_cells(separator)) != column_count:
        return False
    if not data_rows:
        return False
    return all("|" in row and len(markdown_table_cells(row)) == column_count for row in data_rows)


def _looks_like_markdown_table_block(lines: list[str]) -> bool:
    """Return whether *lines* contain markdown pipe-table syntax."""
    if len(lines) < 2:
        return False
    pipe_rows = [line for line in lines if "|" in line]
    if len(pipe_rows) < 2:
        return False
    return any(is_table_separator_line(line) for line in lines)


def split_prose_prefix_and_table(block: str) -> tuple[str, str]:
    """Split one markdown block into optional leading prose and a trailing pipe table.

    Models often emit ``### Heading`` immediately followed by a pipe table with a
    single newline (no blank line). The table must not treat the heading as the
    header row.
    """
    if "|" not in block:
        return block, ""
    lines = block.splitlines()
    nonempty: list[tuple[int, str]] = [
        (index, line.strip()) for index, line in enumerate(lines) if line.strip()
    ]
    for index in range(1, len(nonempty)):
        header_raw_index, header_text = nonempty[index - 1]
        _, separator_text = nonempty[index]
        if "|" not in header_text or not is_table_separator_line(separator_text):
            continue
        prose = "\n".join(lines[:header_raw_index]).strip()
        table = "\n".join(lines[header_raw_index:])
        if block.endswith("\n") and table and not table.endswith("\n"):
            table += "\n"
        return prose, table
    return block, ""


def _inline_code_style(*, palette: ThemePalette) -> str:
    bg = html_escape(palette["bg_alt"])
    border = html_escape(palette["border"])
    text = html_escape(palette["text"])
    return (
        f"background:{bg};border:1px solid {border};color:{text};"
        "font-family:monospace;padding:1px 4px;border-radius:4px;"
    )


def _first_inline_match(text: str) -> _InlineMatch | None:
    """Return the earliest closed inline markdown token in *text*, if any."""
    matches: list[_InlineMatch] = []
    for match in _INLINE_LINK_RE.finditer(text):
        matches.append(_InlineMatch(match.start(), match.end(), "link", match.groups()))
    for match in _INLINE_CODE_RE.finditer(text):
        matches.append(_InlineMatch(match.start(), match.end(), "code", match.groups()))
    for match in _INLINE_BOLD_RE.finditer(text):
        inner = match.group(1) or match.group(2) or ""
        matches.append(_InlineMatch(match.start(), match.end(), "bold", (inner,)))
    for match in _INLINE_STRIKE_RE.finditer(text):
        matches.append(_InlineMatch(match.start(), match.end(), "strike", match.groups()))
    for match in _INLINE_ITALIC_RE.finditer(text):
        inner = match.group(1) or match.group(2) or ""
        matches.append(_InlineMatch(match.start(), match.end(), "italic", (inner,)))
    if not matches:
        return None
    return min(matches, key=lambda item: item.start)


def render_inline_markdown(
    text: str,
    *,
    palette: ThemePalette,
    conservative: bool = False,
) -> str:
    """Render common inline markdown inside one table cell.

    When *conservative* is true, only closed inline spans are upgraded; unclosed
    delimiters remain literal text (used for provisional streaming rows).
    """
    if not text:
        return ""
    if conservative:
        return _render_inline_recursive(text, palette=palette)
    return _render_inline_recursive(text, palette=palette)


def _render_inline_recursive(text: str, *, palette: ThemePalette) -> str:
    """Recursively render closed inline tokens left-to-right."""
    token = _first_inline_match(text)
    if token is None:
        return html_escape(text)
    before = html_escape(text[: token.start])
    after = _render_inline_recursive(text[token.end :], palette=palette)
    if token.kind == "link":
        label, href = token.groups
        accent = html_escape(palette["accent"])
        return (
            f'{before}<a href="{html_escape(href, quote=True)}" '
            f'style="color:{accent};text-decoration:underline;">'
            f"{html_escape(label)}</a>{after}"
        )
    if token.kind == "code":
        (code,) = token.groups
        return (
            f'{before}<span style="{_inline_code_style(palette=palette)}">'
            f"{html_escape(code)}</span>{after}"
        )
    if token.kind == "bold":
        (inner,) = token.groups
        return f"{before}<strong>{_render_inline_recursive(inner, palette=palette)}</strong>{after}"
    if token.kind == "strike":
        (inner,) = token.groups
        return f"{before}<s>{_render_inline_recursive(inner, palette=palette)}</s>{after}"
    (inner,) = token.groups
    return f"{before}<em>{_render_inline_recursive(inner, palette=palette)}</em>{after}"


def _palette_cache_key(palette: ThemePalette) -> tuple[str, ...]:
    """Return a stable palette tuple for cell HTML caching."""
    return (
        palette["text"],
        palette["text_muted"],
        palette["border"],
        palette["bg_alt"],
        palette["accent"],
    )


class StreamingTableRenderer:
    """Build themed table HTML incrementally as pipe-table rows arrive."""

    def __init__(self) -> None:
        """Create an empty renderer."""
        self._committed_row_count = 0
        self._cell_cache: dict[tuple[str, bool, bool, tuple[str, ...]], str] = {}
        self._inline_render_calls = 0

    @property
    def committed_row_count(self) -> int:
        """Return how many data rows were committed on the last render."""
        return self._committed_row_count

    @property
    def inline_render_calls(self) -> int:
        """Return how many inline cell renders ran (for cache tests)."""
        return self._inline_render_calls

    def _cell_html(
        self,
        text: str,
        *,
        muted: bool,
        palette: ThemePalette,
        conservative: bool = False,
    ) -> str:
        """Render one table cell with cached inline markdown."""
        cache_key = (text, muted, conservative, _palette_cache_key(palette))
        cached = self._cell_cache.get(cache_key)
        if cached is not None:
            return cached
        self._inline_render_calls += 1
        color = html_escape(palette["text_muted"] if muted else palette["text"])
        inner = render_inline_markdown(text, palette=palette, conservative=conservative)
        cell = (
            f'<td style="border:1px solid {html_escape(palette["border"])};'
            f'padding:4px 8px;color:{color};">{inner}</td>'
        )
        self._cell_cache[cache_key] = cell
        return cell

    def _row_html(
        self,
        cells: list[str],
        *,
        muted: bool,
        palette: ThemePalette,
        conservative: bool = False,
    ) -> str:
        cells_html = "".join(
            self._cell_html(cell, muted=muted, palette=palette, conservative=conservative)
            for cell in cells
        )
        return f"<tr>{cells_html}</tr>"

    def render_html(self, block: str, *, palette: ThemePalette) -> str:
        """Render *block* as HTML, committing full rows and one provisional tail row."""
        raw_lines = block.splitlines()
        lines = [line.strip() for line in raw_lines if line.strip()]
        if len(lines) < 2 or not _looks_like_markdown_table_block(lines):
            return ""

        border = html_escape(palette["border"])
        bg = html_escape(palette["bg_alt"])
        table_style = (
            f"width:100%;border-collapse:collapse;margin:0 0 8px 0;"
            f"border:1px solid {border};background:{bg};"
        )

        separator_index = -1
        for index in range(1, len(lines)):
            if is_table_separator_line(lines[index]) and "|" in lines[index - 1]:
                separator_index = index
                break
        if separator_index < 1:
            return self._fallback_pre(block, palette=palette)

        header_line = lines[separator_index - 1].strip()
        if "|" not in header_line:
            return self._fallback_pre(block, palette=palette)

        column_count = len(markdown_table_cells(header_line))
        if column_count < 2:
            return self._fallback_pre(block, palette=palette)

        separator_line = lines[separator_index].strip()
        if len(markdown_table_cells(separator_line)) != column_count:
            return self._fallback_pre(block, palette=palette)

        header_cells = markdown_table_cells(header_line)
        thead = "<thead>" + self._row_html(header_cells, muted=False, palette=palette) + "</thead>"

        has_provisional_tail = bool(raw_lines) and not block.endswith("\n")
        provisional_source = raw_lines[-1].strip() if has_provisional_tail else ""

        committed_rows: list[str] = []
        for line in lines[separator_index + 1 :]:
            stripped = line.strip()
            if not stripped or "|" not in stripped:
                continue
            if has_provisional_tail and stripped == provisional_source:
                continue
            cells = markdown_table_cells(stripped)
            if len(cells) == column_count:
                committed_rows.append(self._row_html(cells, muted=False, palette=palette))

        self._committed_row_count = len(committed_rows)
        tbody_parts = list(committed_rows)
        if has_provisional_tail and "|" in provisional_source:
            cells = markdown_table_cells(provisional_source)
            while len(cells) < column_count:
                cells.append("")
            tbody_parts.append(
                self._row_html(
                    cells[:column_count],
                    muted=True,
                    palette=palette,
                    conservative=True,
                )
            )

        tbody = "<tbody>" + "".join(tbody_parts) + "</tbody>"
        return (
            f'<table cellspacing="0" cellpadding="0" style="{table_style}">{thead}{tbody}</table>'
        )

    @staticmethod
    def _fallback_pre(block: str, *, palette: ThemePalette) -> str:
        """Render malformed early table syntax as stable monospace text."""
        border = html_escape(palette["border"])
        bg = html_escape(palette["bg_alt"])
        text = html_escape(palette["text"])
        return (
            f'<pre style="white-space:pre-wrap;margin:0 0 8px 0;padding:6px 8px;'
            f"border:1px solid {border};background:{bg};color:{text};"
            'font-family:monospace;">'
            f"{html_escape(block.rstrip())}</pre>"
        )


__all__ = [
    "StreamingTableRenderer",
    "is_complete_markdown_table",
    "is_table_separator_line",
    "markdown_table_cells",
    "render_inline_markdown",
    "split_prose_prefix_and_table",
]
