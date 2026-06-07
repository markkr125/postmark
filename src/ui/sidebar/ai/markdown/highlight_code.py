"""Themed Pygments HTML for fenced code blocks in chat markdown."""

from __future__ import annotations

from collections import OrderedDict
from html import escape as html_escape

from pygments import token as T

from ui.styling.theme import ThemePalette
from ui.widgets.code_editor.highlighter import get_lexer_for_language, token_color_for_type

_HIGHLIGHT_CACHE_MAX_ENTRIES = 256
_code_html_cache: OrderedDict[tuple[str, str, tuple[str, ...]], str] = OrderedDict()


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


def normalize_language(lang: str) -> str:
    """Map fence info strings to Pygments lexer names."""
    key = lang.strip().lower()
    if not key:
        return "text"
    return _LANGUAGE_ALIASES.get(key, key)


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


def _line_number_cell(number: int, *, palette: ThemePalette, width_ch: int) -> str:
    """Return a muted gutter cell for line *number*."""
    label = str(number).rjust(width_ch)
    color = palette["editor_gutter_text"]
    return (
        f'<td style="color:{html_escape(color)};'
        f"vertical-align:top;text-align:right;"
        f"padding:0 8px 0 0;font-family:monospace;"
        f'user-select:none;">{html_escape(label)}</td>'
    )


def _code_block_chrome(
    *,
    palette: ThemePalette,
    display_lang: str,
    inner_html: str,
) -> str:
    """Wrap *inner_html* in the shared fenced-code block chrome."""
    bg = palette["bg_alt"]
    border = palette["border"]
    muted = palette["text_muted"]
    return (
        f'<div style="margin:8px 0;border:1px solid {html_escape(border)};'
        f'border-radius:6px;overflow:hidden;background:{html_escape(bg)};">'
        f'<div style="padding:4px 10px;font-size:11px;color:{html_escape(muted)};'
        f"border-bottom:1px solid {html_escape(border)};"
        f'font-family:sans-serif;">{html_escape(display_lang)}</div>'
        f"{inner_html}</div>"
    )


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
    pre_style = (
        "margin:0;padding:6px;white-space:pre-wrap;word-break:break-all;"
        "overflow-wrap:anywhere;font-family:monospace;"
        f"color:{html_escape(text)};background:{html_escape(bg)};"
    )
    inner = f'<pre style="{pre_style}">{html_escape(code)}</pre>'
    return _code_block_chrome(palette=palette, display_lang=display_lang, inner_html=inner)


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

    width_ch = max(2, len(str(len(lines) if lines else 1)))
    bg = palette["bg_alt"]
    text = palette["text"]

    code_style = (
        "white-space:pre-wrap;word-break:break-all;overflow-wrap:anywhere;"
        "font-family:monospace;vertical-align:top;padding:0;"
    )

    rows: list[str] = []
    for index, line in enumerate(lines, start=1):
        highlighted = _highlight_line(line, palette, lexer_lang)
        if line_numbers:
            rows.append(
                "<tr>"
                f"{_line_number_cell(index, palette=palette, width_ch=width_ch)}"
                f'<td style="{code_style}color:{html_escape(text)};">{highlighted}</td>'
                "</tr>"
            )
        else:
            rows.append(
                f'<tr><td style="{code_style}color:{html_escape(text)};">{highlighted}</td></tr>'
            )

    table_body = "".join(rows)
    inner = (
        f'<table cellspacing="0" cellpadding="6" style="width:100%;border:none;'
        f'background:{html_escape(bg)};">{table_body}</table>'
    )
    html = _code_block_chrome(palette=palette, display_lang=display_lang, inner_html=inner)
    _cache_put(cache_key, html)
    return html
