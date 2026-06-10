"""Themed Pygments HTML for fenced code blocks in chat markdown."""

from __future__ import annotations

from collections import OrderedDict
from html import escape as html_escape

from pygments import token as T

from ui.styling.theme import ThemePalette
from ui.widgets.code_editor.highlighter import get_lexer_for_language, token_color_for_type

_HIGHLIGHT_CACHE_MAX_ENTRIES = 256
_code_html_cache: OrderedDict[tuple[str, str, tuple[str, ...]], str] = OrderedDict()

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
        palette["bg_alt"],
        palette["text"],
        palette["text_muted"],
        palette["border"],
        palette["editor_gutter_text"],
    )


def _cache_get(key: tuple[str, str, tuple[str, ...]]) -> str | None:
    """Return cached HTML and mark the entry recently used."""
    cached = _code_html_cache.get(key)
    if cached is not None:
        _code_html_cache.move_to_end(key)
    return cached


def _cache_put(key: tuple[str, str, tuple[str, ...]], html: str) -> None:
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

    *role* is one of ``header``, ``gutter``, ``code``, or ``full_width``.
    """
    solid = _solid_border(palette)
    parts = [_NO_BORDER]
    if role == "header":
        parts.extend(
            (
                f"border-top:{solid};",
                f"border-left:{solid};",
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


def _render_code_block_table(
    *,
    palette: ThemePalette,
    display_lang: str,
    body_rows_html: str,
) -> str:
    """Wrap *body_rows_html* in a single flat table chrome (no nested tables)."""
    bg = palette["bg_alt"]
    muted = palette["text_muted"]
    header_style = _perimeter_cell_style(
        palette=palette,
        role="header",
        extra=(
            f"padding:4px 10px;font-size:11px;color:{html_escape(muted)};font-family:sans-serif;"
        ),
    )
    header_row = f'<tr><td colspan="2" style="{header_style}">{html_escape(display_lang)}</td></tr>'
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


def _line_number_cell(
    number: int,
    *,
    palette: ThemePalette,
    width_ch: int,
    is_last_row: bool,
) -> str:
    """Return a muted gutter cell for line *number*."""
    label = str(number).rjust(width_ch)
    color = palette["editor_gutter_text"]
    style = _perimeter_cell_style(
        palette=palette,
        role="gutter",
        is_last_row=is_last_row,
        extra=(
            f"color:{html_escape(color)};vertical-align:top;text-align:right;"
            "padding:6px 8px 6px 6px;font-family:monospace;user-select:none;"
        ),
    )
    return f'<td style="{style}">{html_escape(label)}</td>'


def _code_cell(
    highlighted: str,
    *,
    palette: ThemePalette,
    is_last_row: bool,
) -> str:
    """Return a code column cell with wrap styles and optional perimeter borders."""
    text = palette["text"]
    style = _perimeter_cell_style(
        palette=palette,
        role="code",
        is_last_row=is_last_row,
        extra=(
            "white-space:pre-wrap;word-break:break-all;overflow-wrap:anywhere;"
            "font-family:monospace;vertical-align:top;padding:6px 6px 6px 0;"
            f"color:{html_escape(text)};"
        ),
    )
    return f'<td style="{style}">{highlighted}</td>'


def provisional_code_to_html(
    code: str,
    lang: str,
    *,
    palette: ThemePalette,
) -> str:
    """Render a growing fenced block without Pygments (streaming-safe)."""
    lexer_lang = normalize_language(lang)
    display_lang = lexer_lang if lexer_lang != "text" else (lang.strip() or "text")
    text = palette["text"]
    bg = palette["bg_alt"]
    body_style = _perimeter_cell_style(
        palette=palette,
        role="full_width",
        is_last_row=True,
        extra="padding:0;",
    )
    pre_style = (
        "margin:0;padding:6px;white-space:pre-wrap;word-break:break-all;"
        "overflow-wrap:anywhere;font-family:monospace;"
        f"color:{html_escape(text)};background:{html_escape(bg)};"
    )
    body_row = (
        f'<tr><td colspan="2" style="{body_style}">'
        f'<pre style="{pre_style}">{html_escape(code)}</pre></td></tr>'
    )
    return _render_code_block_table(
        palette=palette,
        display_lang=display_lang,
        body_rows_html=body_row,
    )


def highlight_code_to_html(
    code: str,
    lang: str,
    *,
    palette: ThemePalette,
    line_numbers: bool = True,
) -> str:
    """Render *code* as a themed HTML table with optional line numbers."""
    lexer_lang = normalize_language(lang)
    cache_key = (lexer_lang, code, _palette_fingerprint(palette))
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    display_lang = lexer_lang if lexer_lang != "text" else (lang.strip() or "text")
    lines = code.split("\n")
    if code.endswith("\n"):
        lines.append("")

    line_count = len(lines) if lines else 1
    width_ch = max(2, len(str(line_count)))

    rows: list[str] = []
    for index, line in enumerate(lines, start=1):
        highlighted = _highlight_line(line, palette, lexer_lang)
        is_last_row = index == line_count
        if line_numbers:
            rows.append(
                "<tr>"
                f"{_line_number_cell(index, palette=palette, width_ch=width_ch, is_last_row=is_last_row)}"
                f"{_code_cell(highlighted, palette=palette, is_last_row=is_last_row)}"
                "</tr>"
            )
        else:
            style = _perimeter_cell_style(
                palette=palette,
                role="full_width",
                is_last_row=is_last_row,
                extra=(
                    "white-space:pre-wrap;word-break:break-all;overflow-wrap:anywhere;"
                    "font-family:monospace;vertical-align:top;padding:6px;"
                    f"color:{html_escape(palette['text'])};"
                ),
            )
            rows.append(f'<tr><td colspan="2" style="{style}">{highlighted}</td></tr>')

    html = _render_code_block_table(
        palette=palette,
        display_lang=display_lang,
        body_rows_html="".join(rows),
    )
    _cache_put(cache_key, html)
    return html
