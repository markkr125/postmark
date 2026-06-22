"""Themed Pygments HTML for fenced code blocks in chat markdown."""

from __future__ import annotations

from collections import OrderedDict
from html import escape as html_escape

from pygments import token as T
from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QTextBlock,
    QTextCursor,
    QTextDocument,
    QTextFragment,
)

from ui.styling.theme import ThemePalette
from ui.widgets.code_editor.highlighter import get_lexer_for_language, token_color_for_type

_HIGHLIGHT_CACHE_MAX_ENTRIES = 256
_code_html_cache: OrderedDict[tuple[str, str, bool, int, tuple[str, ...]], str] = OrderedDict()

CODE_COPY_URL_PREFIX = "postmark-code-copy:"
COPY_LINK_FONT_PX = 11
_CODE_TABLE_COLS = 3


def code_copy_href(block_index: int) -> str:
    """Return the anchor href for copying fenced block *block_index*."""
    return f"{CODE_COPY_URL_PREFIX}{block_index}"


def parse_code_copy_block_index(anchor: str) -> int | None:
    """Return the fenced-block index encoded in a copy anchor, if any."""
    if not anchor.startswith(CODE_COPY_URL_PREFIX):
        return None
    suffix = anchor[len(CODE_COPY_URL_PREFIX) :]
    if not suffix.isdigit():
        return None
    return int(suffix)


COPY_HIT_PAD_PX = 8.0
_COPY_HIT_PAD_PX = COPY_HIT_PAD_PX


def _copy_anchor_hit_rect(
    layout: QAbstractTextDocumentLayout,
    block: QTextBlock,
    block_layout: object,
    fragment: QTextFragment,
    *,
    pad_px: float,
) -> tuple[int, QRectF] | None:
    """Return ``(block_index, padded_rect)`` for a copy-link fragment, if any."""
    char_format = fragment.charFormat()
    if not char_format.isAnchor():
        return None
    block_index = parse_code_copy_block_index(char_format.anchorHref())
    if block_index is None:
        return None
    block_rect = layout.blockBoundingRect(block)
    pos_in_block = fragment.position() - block.position()
    line = block_layout.lineForTextPosition(pos_in_block)  # type: ignore[attr-defined]
    line_rect = line.naturalTextRect()
    hit_rect = QRectF(
        block_rect.left() + line_rect.left(),
        block_rect.top() + line_rect.top(),
        line_rect.width(),
        line_rect.height(),
    ).adjusted(-pad_px, -pad_px, pad_px, pad_px)
    return block_index, hit_rect


def copy_block_header_hit_rects(
    document: QTextDocument,
    *,
    pad_px: float = _COPY_HIT_PAD_PX,
) -> dict[int, QRectF]:
    """Return document-local padded hit rectangles for fenced-code Copy links."""
    layout = document.documentLayout()
    rects: dict[int, QRectF] = {}
    block = document.firstBlock()
    while block.isValid():
        block_layout = block.layout()
        if block_layout is not None:
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid():
                    hit = _copy_anchor_hit_rect(
                        layout,
                        block,
                        block_layout,
                        fragment,
                        pad_px=pad_px,
                    )
                    if hit is not None:
                        rects[hit[0]] = hit[1]
                iterator += 1
        block = block.next()
    return rects


def copy_anchor_spans(document: QTextDocument) -> dict[int, tuple[int, int]]:
    """Return document character spans ``(start, end)`` for each Copy anchor."""
    spans: dict[int, tuple[int, int]] = {}
    block = document.firstBlock()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                char_format = fragment.charFormat()
                if char_format.isAnchor():
                    block_index = parse_code_copy_block_index(char_format.anchorHref())
                    if block_index is not None:
                        start = fragment.position()
                        spans[block_index] = (start, start + fragment.length())
            iterator += 1
        block = block.next()
    return spans


def copy_block_index_at_document_pos(
    document: QTextDocument,
    pos: QPointF,
    *,
    pad_px: float = _COPY_HIT_PAD_PX,
) -> int | None:
    """Return the fenced-code Copy index under document-local *pos*, if any."""
    layout = document.documentLayout()
    anchor = layout.anchorAt(pos)
    if anchor:
        block_index = parse_code_copy_block_index(anchor)
        if block_index is not None:
            return block_index
    hit = layout.hitTest(pos, Qt.HitTestAccuracy.ExactHit)
    if hit < 0:
        hit = layout.hitTest(pos, Qt.HitTestAccuracy.FuzzyHit)
    if hit >= 0:
        cursor = QTextCursor(document)
        cursor.setPosition(hit)
        char_format = cursor.charFormat()
        if char_format.isAnchor():
            block_index = parse_code_copy_block_index(char_format.anchorHref())
            if block_index is not None:
                return block_index
    for block_index, hit_rect in copy_block_header_hit_rects(document, pad_px=pad_px).items():
        if hit_rect.contains(pos):
            return block_index
    return None


_NO_BORDER = (
    "border-top-width:0;border-top-style:none;"
    "border-bottom-width:0;border-bottom-style:none;"
    "border-left-width:0;border-left-style:none;"
    "border-right-width:0;border-right-style:none;"
)

_LANGUAGE_ALIASES: dict[str, str] = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "sh": "bash",
    "shell": "bash",
    "yml": "yaml",
    "md": "markdown",
    "json": "json",
    "c++": "cpp",
    "h": "c",
}


def clear_highlight_cache() -> None:
    """Clear cached fenced-code HTML (call on theme change)."""
    _code_html_cache.clear()


def _palette_fingerprint(palette: ThemePalette) -> tuple[str, ...]:
    """Return colour slots that affect fenced-code HTML output."""
    return (
        palette["bg"],
        palette["chat_code_bg"],
        palette["text"],
        palette["text_muted"],
        palette["border"],
        palette["editor_gutter_text"],
        palette["accent"],
    )


def _cache_get(key: tuple[str, str, bool, int, tuple[str, ...]]) -> str | None:
    """Return cached HTML and mark the entry recently used."""
    cached = _code_html_cache.get(key)
    if cached is not None:
        _code_html_cache.move_to_end(key)
    return cached


def _cache_put(key: tuple[str, str, bool, int, tuple[str, ...]], html: str) -> None:
    """Store HTML and evict the oldest entry when over capacity."""
    _code_html_cache[key] = html
    _code_html_cache.move_to_end(key)
    while len(_code_html_cache) > _HIGHLIGHT_CACHE_MAX_ENTRIES:
        _code_html_cache.popitem(last=False)


def normalize_language(lang: str) -> str:
    """Map fence info strings to Pygments lexer names."""
    key = lang.strip().lower()
    if not key:
        return "text"
    return _LANGUAGE_ALIASES.get(key, key)


def _solid_border(palette: ThemePalette) -> str:
    """Return a 1px solid border colour declaration for inline CSS."""
    return f"1px solid {html_escape(palette['border'])}"


def _perimeter_cell_style(
    *,
    palette: ThemePalette,
    role: str,
    is_last_row: bool = False,
    extra: str = "",
) -> str:
    """Return inline CSS for a fenced-code table cell border perimeter.

    *role* is one of ``header_lang``, ``header_spacer``, ``header_action``,
    ``gutter``, ``code``, or ``full_width``.
    """
    solid = _solid_border(palette)
    parts = [_NO_BORDER]
    if role == "header_lang":
        parts.extend(
            (
                f"border-top:{solid};",
                f"border-left:{solid};",
                f"border-bottom:{solid};",
            )
        )
    elif role == "header_spacer":
        parts.extend(
            (
                f"border-top:{solid};",
                f"border-bottom:{solid};",
            )
        )
    elif role == "header_action":
        parts.extend(
            (
                f"border-top:{solid};",
                f"border-right:{solid};",
                f"border-bottom:{solid};",
            )
        )
    elif role == "gutter":
        parts.append(f"border-left:{solid};")
        if is_last_row:
            parts.append(f"border-bottom:{solid};")
    elif role == "code":
        parts.append(f"border-right:{solid};")
        if is_last_row:
            parts.append(f"border-bottom:{solid};")
    elif role == "full_width":
        parts.extend(
            (
                f"border-left:{solid};",
                f"border-right:{solid};",
            )
        )
        if is_last_row:
            parts.append(f"border-bottom:{solid};")
    return f"{''.join(parts)}{extra}"


def _copy_link_html(copy_href: str, *, palette: ThemePalette) -> str:
    """Return the static Copy anchor for the fenced-code header row."""
    href = html_escape(copy_href, quote=True)
    color = html_escape(palette["text_muted"])
    return (
        f'<a href="{href}" style="color:{color};text-decoration:none;'
        f'font-family:sans-serif;font-size:{COPY_LINK_FONT_PX}px;">'
        "Copy</a>"
    )


def _render_code_block_table(
    *,
    palette: ThemePalette,
    display_lang: str,
    body_rows_html: str,
    copy_href: str,
) -> str:
    """Wrap *body_rows_html* in a single flat table chrome (no nested tables)."""
    bg = palette["chat_code_bg"]
    muted = palette["text_muted"]
    lang_style = _perimeter_cell_style(
        palette=palette,
        role="header_lang",
        extra=(
            f"padding:4px 6px 4px 10px;font-size:11px;color:{html_escape(muted)};"
            "font-family:sans-serif;white-space:nowrap;"
        ),
    )
    spacer_style = _perimeter_cell_style(
        palette=palette,
        role="header_spacer",
        extra="padding:0;",
    )
    copy_style = _perimeter_cell_style(
        palette=palette,
        role="header_action",
        extra=("padding:4px 10px 4px 6px;white-space:nowrap;font-family:sans-serif;"),
    )
    header_row = (
        f"<tr>"
        f'<td style="{lang_style}">{html_escape(display_lang)}</td>'
        f'<td width="99%" style="{spacer_style}"></td>'
        f'<td align="right" width="1%" style="{copy_style}">'
        f"{_copy_link_html(copy_href, palette=palette)}"
        f"</td>"
        f"</tr>"
    )
    return (
        f'<table cellspacing="0" cellpadding="0" style="width:100%;margin:8px 0;'
        f"border-collapse:separate;border-spacing:0;"
        f'background:{html_escape(bg)};">'
        f"{header_row}{body_rows_html}"
        f"</table>"
    )


def _token_span(text: str, token_type: T._TokenType, palette: ThemePalette) -> str:
    """Wrap escaped *text* in a coloured span for *token_type*."""
    if not text:
        return ""
    color = token_color_for_type(token_type, palette)
    return f'<span style="color:{html_escape(color)};">{html_escape(text)}</span>'


def _highlight_line(line: str, palette: ThemePalette, lexer_lang: str) -> str:
    """Return HTML for one line of syntax-highlighted code."""
    lexer = get_lexer_for_language(lexer_lang)
    parts: list[str] = []
    for token_type, value in lexer.get_tokens(line):
        parts.append(_token_span(value, token_type, palette))
    return "".join(parts) if parts else html_escape(line)


def _code_row_padding(*, is_first_row: bool, is_last_row: bool) -> str:
    """Return vertical padding for one code line (tight between rows, inset at edges)."""
    top = "4px" if is_first_row else "0"
    bottom = "4px" if is_last_row else "0"
    return f"padding:{top} 0 {bottom} 0;"


def _line_number_cell(
    number: int,
    *,
    palette: ThemePalette,
    width_ch: int,
    is_first_row: bool,
    is_last_row: bool,
) -> str:
    """Return a muted gutter cell for line *number*."""
    label = str(number).rjust(width_ch)
    color = palette["editor_gutter_text"]
    row_pad = _code_row_padding(is_first_row=is_first_row, is_last_row=is_last_row)
    style = _perimeter_cell_style(
        palette=palette,
        role="gutter",
        is_last_row=is_last_row,
        extra=(
            f"color:{html_escape(color)};vertical-align:top;text-align:right;"
            f"{row_pad}padding-left:6px;padding-right:8px;"
            "font-family:monospace;user-select:none;"
        ),
    )
    return f'<td style="{style}">{html_escape(label)}</td>'


def _code_cell(
    highlighted: str,
    *,
    palette: ThemePalette,
    is_first_row: bool,
    is_last_row: bool,
    colspan: int = 1,
) -> str:
    """Return a code column cell with wrap styles and optional perimeter borders."""
    text = palette["text"]
    row_pad = _code_row_padding(is_first_row=is_first_row, is_last_row=is_last_row)
    style = _perimeter_cell_style(
        palette=palette,
        role="code",
        is_last_row=is_last_row,
        extra=(
            "white-space:pre-wrap;word-break:break-all;overflow-wrap:anywhere;"
            f"font-family:monospace;vertical-align:top;{row_pad}padding-right:6px;"
            f"color:{html_escape(text)};"
        ),
    )
    span = f' colspan="{colspan}"' if colspan > 1 else ""
    return f'<td{span} style="{style}">{highlighted}</td>'


def provisional_code_to_html(
    code: str,
    lang: str,
    *,
    palette: ThemePalette,
    block_index: int = 0,
) -> str:
    """Render a growing fenced block without Pygments (streaming-safe)."""
    lexer_lang = normalize_language(lang)
    display_lang = lexer_lang if lexer_lang != "text" else (lang.strip() or "text")
    text = palette["text"]
    bg = palette["chat_code_bg"]
    body_style = _perimeter_cell_style(
        palette=palette,
        role="full_width",
        is_last_row=True,
        extra="padding:0;",
    )
    pre_style = (
        "margin:0;padding:4px 6px;white-space:pre-wrap;word-break:break-all;"
        "overflow-wrap:anywhere;font-family:monospace;"
        f"color:{html_escape(text)};background:{html_escape(bg)};"
    )
    body_row = (
        f'<tr><td colspan="{_CODE_TABLE_COLS}" style="{body_style}">'
        f'<pre style="{pre_style}">{html_escape(code)}</pre></td></tr>'
    )
    return _render_code_block_table(
        palette=palette,
        display_lang=display_lang,
        body_rows_html=body_row,
        copy_href=code_copy_href(block_index),
    )


def highlight_code_to_html(
    code: str,
    lang: str,
    *,
    palette: ThemePalette,
    line_numbers: bool = False,
    block_index: int = 0,
) -> str:
    """Render *code* as a themed HTML table with optional line numbers."""
    lexer_lang = normalize_language(lang)
    cache_key = (
        lexer_lang,
        code,
        line_numbers,
        block_index,
        _palette_fingerprint(palette),
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    display_lang = lexer_lang if lexer_lang != "text" else (lang.strip() or "text")
    lines = code.split("\n") if code else [""]

    line_count = len(lines) if lines else 1
    width_ch = max(2, len(str(line_count)))

    rows: list[str] = []
    for index, line in enumerate(lines, start=1):
        highlighted = _highlight_line(line, palette, lexer_lang)
        is_first_row = index == 1
        is_last_row = index == line_count
        if line_numbers:
            rows.append(
                "<tr>"
                f"{_line_number_cell(index, palette=palette, width_ch=width_ch, is_first_row=is_first_row, is_last_row=is_last_row)}"
                f"{_code_cell(highlighted, palette=palette, is_first_row=is_first_row, is_last_row=is_last_row, colspan=_CODE_TABLE_COLS - 1)}"
                "</tr>"
            )
        else:
            row_pad = _code_row_padding(is_first_row=is_first_row, is_last_row=is_last_row)
            style = _perimeter_cell_style(
                palette=palette,
                role="full_width",
                is_last_row=is_last_row,
                extra=(
                    "white-space:pre-wrap;word-break:break-all;overflow-wrap:anywhere;"
                    f"font-family:monospace;vertical-align:top;{row_pad}padding-left:6px;padding-right:6px;"
                    f"color:{html_escape(palette['text'])};"
                ),
            )
            rows.append(
                f'<tr><td colspan="{_CODE_TABLE_COLS}" style="{style}">{highlighted}</td></tr>'
            )

    html = _render_code_block_table(
        palette=palette,
        display_lang=display_lang,
        body_rows_html="".join(rows),
        copy_href=code_copy_href(block_index),
    )
    _cache_put(cache_key, html)
    return html
