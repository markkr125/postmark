"""Pygments-backed syntax highlighter for the code editor.

Provides ``PygmentsHighlighter`` — a ``QSyntaxHighlighter`` subclass that
delegates tokenisation to Pygments lexers and overlays ``{{variable}}``
highlights.

Also exposes helper utilities used when building token formats:

* ``_get_cached_lexer`` — module-level lexer cache.
* ``_build_format`` / ``_build_token_formats`` — build ``QTextCharFormat``
  objects from the current theme palette.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pygments import token as T
from pygments.lexer import Lexer
from pygments.lexers import TextLexer, get_lexer_by_name
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument

if TYPE_CHECKING:
    from services.environment_service import VariableDetail

from ui.styling.theme import (
    COLOR_VARIABLE_HIGHLIGHT,
    COLOR_VARIABLE_UNRESOLVED_HIGHLIGHT,
    COLOR_VARIABLE_UNRESOLVED_TEXT,
    COLOR_WARNING,
    current_palette,
)
from ui.widgets.code_editor.gutter import _VAR_RE

# Module-level lexer cache — avoids creating a new Pygments lexer (and
# triggering module imports) on every language switch.
_lexer_cache: dict[str, Lexer] = {}


def _get_cached_lexer(language: str) -> Lexer:
    """Return a cached Pygments lexer for *language*.

    Creates the lexer on first access and reuses it thereafter.  Falls
    back to ``TextLexer`` for unknown language names.
    """
    if language not in _lexer_cache:
        try:
            _lexer_cache[language] = get_lexer_by_name(
                language,
                stripnl=False,
                ensurenl=False,
            )
        except Exception:
            _lexer_cache[language] = TextLexer(stripnl=False, ensurenl=False)
    return _lexer_cache[language]


def _build_format(color: str, *, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    """Build a ``QTextCharFormat`` from a hex colour string."""
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


def _build_token_formats() -> dict[T._TokenType, QTextCharFormat]:
    """Build token-type to format mapping from current theme colours."""
    p = current_palette()
    return {
        T.Literal.String: _build_format(p["editor_string"]),
        T.Literal.String.Double: _build_format(p["editor_string"]),
        T.Literal.String.Single: _build_format(p["editor_string"]),
        T.Literal.String.Backtick: _build_format(p["editor_string"]),
        T.Literal.String.Affix: _build_format(p["editor_string"]),
        T.Literal.Number: _build_format(p["editor_number"]),
        T.Literal.Number.Integer: _build_format(p["editor_number"]),
        T.Literal.Number.Float: _build_format(p["editor_number"]),
        T.Keyword: _build_format(p["editor_keyword"], bold=True),
        T.Keyword.Constant: _build_format(p["editor_keyword"], bold=True),
        T.Keyword.Declaration: _build_format(p["editor_keyword"], bold=True),
        T.Keyword.Type: _build_format(p["editor_keyword"]),
        T.Name.Tag: _build_format(p["editor_tag"]),
        T.Name.Attribute: _build_format(p["editor_attribute"]),
        T.Name.Builtin: _build_format(p["editor_keyword"]),
        T.Comment: _build_format(p["editor_comment"], italic=True),
        T.Comment.Single: _build_format(p["editor_comment"], italic=True),
        T.Comment.Multiline: _build_format(p["editor_comment"], italic=True),
        T.Punctuation: _build_format(p["editor_punctuation"]),
        T.Operator: _build_format(p["editor_punctuation"]),
    }


class PygmentsHighlighter(QSyntaxHighlighter):
    """Syntax highlighter backed by a Pygments lexer.

    Operates line-by-line for editable documents and full-document for
    read-only documents. Supports switching the language at runtime.
    """

    def __init__(self, document: QTextDocument, *, read_only: bool = False) -> None:
        """Initialise the highlighter with a document and optional read-only mode."""
        super().__init__(document)
        self._read_only = read_only
        self._lexer: Lexer = TextLexer(stripnl=False, ensurenl=False)
        self._language = "text"
        self._token_formats = _build_token_formats()
        # Full-document token cache for read-only mode:
        # list of (block_number, [(start_in_block, length, token_type), ...])
        self._block_tokens: dict[int, list[tuple[int, int, T._TokenType]]] | None = None
        self._variable_map: dict[str, VariableDetail] = {}

    def set_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Update the variable resolution map for unresolved distinction."""
        self._variable_map = variables

    @property
    def language(self) -> str:
        """Return the active language name."""
        return self._language

    def set_language(self, language: str) -> None:
        """Switch the lexer to a new language and re-highlight."""
        lang = language.lower()
        if lang == self._language:
            return
        self._language = lang
        self._block_tokens = None
        self._lexer = _get_cached_lexer(lang)
        self.rehighlight()

    def rebuild_formats(self) -> None:
        """Rebuild token formats from current theme (call on theme change)."""
        self._token_formats = _build_token_formats()
        self._block_tokens = None
        self.rehighlight()

    def _get_format(self, token_type: T._TokenType) -> QTextCharFormat | None:
        """Walk the token type hierarchy to find a matching format."""
        tt: T._TokenType | None = token_type
        while tt:
            if tt in self._token_formats:
                return self._token_formats[tt]
            tt = tt.parent  # type: ignore[assignment]
        return None

    def highlightBlock(self, text: str) -> None:
        """Apply syntax highlighting to a single text block."""
        if self._language == "text":
            self._apply_variable_highlight(text)
            return

        if self._read_only and self._block_tokens is not None:
            # Use pre-computed tokens for read-only mode
            block_num = self.currentBlock().blockNumber()
            tokens = self._block_tokens.get(block_num, [])
            for start, length, token_type in tokens:
                fmt = self._get_format(token_type)
                if fmt is not None:
                    self.setFormat(start, length, fmt)
            self._apply_variable_highlight(text)
            return

        # Line-by-line mode (editable, or read-only without cache)
        index = 0
        for token_type, value in self._lexer.get_tokens(text):
            length = len(value)
            fmt = self._get_format(token_type)
            if fmt is not None:
                self.setFormat(index, length, fmt)
            index += length

        self._apply_variable_highlight(text)

    def _apply_variable_highlight(self, text: str) -> None:
        """Overlay ``{{variable}}`` highlights on the current block."""
        if "{{" not in text:
            return
        resolved_fmt = QTextCharFormat()
        resolved_fmt.setBackground(QColor(COLOR_VARIABLE_HIGHLIGHT))
        resolved_fmt.setForeground(QColor(COLOR_WARNING))
        unresolved_fmt = QTextCharFormat()
        unresolved_fmt.setBackground(QColor(COLOR_VARIABLE_UNRESOLVED_HIGHLIGHT))
        unresolved_fmt.setForeground(QColor(COLOR_VARIABLE_UNRESOLVED_TEXT))
        for match in _VAR_RE.finditer(text):
            var_name = match.group(1)
            fmt = resolved_fmt if var_name in self._variable_map else unresolved_fmt
            self.setFormat(match.start(), match.end() - match.start(), fmt)

    def cache_full_document(self) -> None:
        """Lex the entire document and cache tokens per block.

        Call this for read-only content to get accurate multi-line
        highlighting.
        """
        doc = self.document()
        if doc is None:
            return
        full_text = doc.toPlainText()
        if not full_text:
            self._block_tokens = {}
            return

        # Build line-start offset map
        lines = full_text.split("\n")
        line_starts: list[int] = []
        offset = 0
        for line in lines:
            line_starts.append(offset)
            offset += len(line) + 1  # +1 for newline

        self._block_tokens = {i: [] for i in range(len(lines))}

        # Lex full document
        pos = 0
        for token_type, value in self._lexer.get_tokens(full_text):
            length = len(value)
            # Map global offset to block(s)
            remaining = length
            cur_pos = pos
            while remaining > 0:
                # Find which line this position belongs to
                line_idx = self._offset_to_line(cur_pos, line_starts)
                if line_idx >= len(lines):
                    break
                col = cur_pos - line_starts[line_idx]
                line_remaining = len(lines[line_idx]) - col
                # Account for the newline character
                chunk = min(remaining, line_remaining + (1 if remaining > line_remaining else 0))
                visible_chunk = min(remaining, line_remaining)
                if visible_chunk > 0 and line_idx in self._block_tokens:
                    self._block_tokens[line_idx].append((col, visible_chunk, token_type))
                cur_pos += chunk
                remaining -= chunk
            pos += length

    @staticmethod
    def _offset_to_line(offset: int, line_starts: list[int]) -> int:
        """Binary search for the line number containing *offset*."""
        lo, hi = 0, len(line_starts) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if line_starts[mid] <= offset:
                lo = mid + 1
            else:
                hi = mid - 1
        return hi
