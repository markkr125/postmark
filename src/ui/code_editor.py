"""Reusable code editor widget with Pygments syntax highlighting.

Provides ``CodeEditorWidget`` — a ``QPlainTextEdit`` subclass with:
- Pygments-backed syntax highlighting for JSON, XML, HTML, GraphQL, and
  plain text.
- Line-number gutter with fold indicators.
- Code folding (collapsible JSON objects/arrays and XML elements).
- Bracket matching and auto-closing.
- Inline validation errors (wave underline + gutter marker + tooltip).
- Prettify (auto-format) and word-wrap toggle.

The widget is used by the request body editor, response viewer, code
snippet dialog, and folder script editors.

Performance notes
-----------------
Large responses (5 000+ lines) must remain smooth.  Hot paths are:

* **paintEvent** — runs every frame during scroll.  Only fold regions
  overlapping the visible viewport are processed.  A sorted list of
  ``(start_line, end_line, leading_spaces)`` tuples is cached so the
  paint loop can skip regions that end above the viewport and break
  early once past it.
* **_find_matching_bracket** — bounded by ``_BRACKET_SEARCH_LIMIT``
  characters to avoid O(n) scans.
* **cursorPositionChanged** — bracket-match + active-guide repaint are
  debounced to avoid redundant work during rapid scrolling.
* **Fold gutter** — the Phosphor ``QFont`` is created once and reused.
"""

from __future__ import annotations

import json
import re
import xml.dom.minidom
import xml.etree.ElementTree as ET
from typing import NamedTuple, cast

from pygments import token as T
from pygments.lexer import Lexer
from pygments.lexers import TextLexer, get_lexer_by_name
from PySide6.QtCore import QEvent, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QHelpEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QSyntaxHighlighter,
    QTextBlock,
    QTextBlockUserData,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QToolTip, QWidget

from ui.icons import font_family, glyph_char
from ui.theme import (
    COLOR_EDITOR_ACTIVE_INDENT_GUIDE,
    COLOR_EDITOR_BRACKET_MATCH,
    COLOR_EDITOR_ERROR_GUTTER_BG,
    COLOR_EDITOR_ERROR_UNDERLINE,
    COLOR_EDITOR_FOLD_BADGE_BG,
    COLOR_EDITOR_FOLD_BADGE_TEXT,
    COLOR_EDITOR_FOLD_HIGHLIGHT,
    COLOR_EDITOR_FOLD_INDICATOR,
    COLOR_EDITOR_GUTTER_BG,
    COLOR_EDITOR_GUTTER_TEXT,
    COLOR_EDITOR_INDENT_GUIDE,
    COLOR_EDITOR_WHITESPACE_DOT,
    COLOR_VARIABLE_HIGHLIGHT,
    COLOR_WARNING,
    current_palette,
)

# Regex for {{variable}} references
_VAR_RE = re.compile(r"\{\{(.+?)\}\}")

# -- Data structures ---------------------------------------------------


class SyntaxError_(NamedTuple):
    """A validation error at a specific location in the document."""

    line: int
    column: int
    message: str


class _FoldData(QTextBlockUserData):
    """Per-block metadata for code folding."""

    __slots__ = ("depth", "fold_end", "fold_start")

    def __init__(self, *, fold_start: bool = False, fold_end: bool = False, depth: int = 0) -> None:
        """Initialise fold data for a text block."""
        super().__init__()
        self.fold_start = fold_start
        self.fold_end = fold_end
        self.depth = depth


# -- Constants ---------------------------------------------------------

_BRACKET_PAIRS = {"(": ")", "[": "]", "{": "}"}
_CLOSE_TO_OPEN = {v: k for k, v in _BRACKET_PAIRS.items()}
_ALL_BRACKETS = set(_BRACKET_PAIRS) | set(_CLOSE_TO_OPEN)
_AUTO_CLOSE_PAIRS = {"{": "}", "[": "]", "(": ")", '"': '"', "'": "'"}

_FOLD_DEBOUNCE_MS = 150
_VALIDATE_DEBOUNCE_MS = 300
_CURSOR_DEBOUNCE_MS = 16  # ~1 frame at 60fps — coalesce rapid cursor moves
_DEFAULT_INDENT_WIDTH = 2  # fallback indent width when detection fails
_BRACKET_SEARCH_LIMIT = 50_000  # max characters to scan for bracket match
_INDENT_SCAN_LINES = 100  # max lines to scan for indent detection

_GUTTER_PADDING = 10
_FOLD_GUTTER_WIDTH = 14
_FOLD_BADGE_LABEL = " \u2026 "  # " … " — ellipsis with padding
_FOLD_BADGE_H_PAD = 4  # horizontal padding inside the badge
_FOLD_BADGE_V_PAD = 1  # vertical padding inside the badge
_FOLD_BADGE_RADIUS = 3  # corner radius of the badge pill
_FOLD_BADGE_GAP = 6  # gap between end of line text and badge
_WHITESPACE_DOT_RADIUS = 1.5  # px — small centered dot on selected spaces

# Regex for XML/HTML fold detection
_XML_OPEN_TAG = re.compile(r"<(\w[\w.\-:]*)(?:\s[^>]*)?\s*>")
_XML_CLOSE_TAG = re.compile(r"</(\w[\w.\-:]*)\s*>")
_XML_SELF_CLOSE = re.compile(r"<\w[\w.\-:]*(?:\s[^>]*)?\s*/>")

# Languages that support validation
_VALIDATABLE_LANGUAGES = {"json", "xml", "graphql"}

# Languages that support folding
_FOLDABLE_LANGUAGES = {"json", "xml", "html", "graphql"}


# -- Pygments Highlighter ----------------------------------------------


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
        try:
            self._lexer = get_lexer_by_name(lang, stripnl=False, ensurenl=False)
        except Exception:
            self._lexer = TextLexer(stripnl=False, ensurenl=False)
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
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(COLOR_VARIABLE_HIGHLIGHT))
        fmt.setForeground(QColor(COLOR_WARNING))
        for match in _VAR_RE.finditer(text):
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


# -- Gutter widgets ----------------------------------------------------


class _LineNumberArea(QWidget):
    """Line-number gutter for the code editor."""

    def __init__(self, editor: CodeEditorWidget) -> None:
        """Initialise the line-number area."""
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        """Return the preferred width based on digit count."""
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Delegate painting to the editor."""
        self._editor.paint_line_number_area(event)


class _FoldGutterArea(QWidget):
    """Fold indicator gutter for the code editor."""

    def __init__(self, editor: CodeEditorWidget) -> None:
        """Initialise the fold gutter area."""
        super().__init__(editor)
        self._editor = editor
        self.setMouseTracking(True)

    def sizeHint(self) -> QSize:
        """Return the fixed fold gutter width."""
        return QSize(_FOLD_GUTTER_WIDTH, 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Delegate painting to the editor."""
        self._editor.paint_fold_gutter_area(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle click on fold indicator."""
        self._editor.fold_gutter_clicked(event.position().toPoint().y())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Show hand cursor when hovering over a foldable line."""
        y = event.position().toPoint().y()
        if self._editor.is_fold_line_at(y):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)


# -- Code Editor Widget ------------------------------------------------


class CodeEditorWidget(QPlainTextEdit):
    """Rich code editor with syntax highlighting, folding, and validation.

    Parameters:
        read_only: If ``True``, the editor is not editable and uses
            full-document caching for perfect highlighting accuracy.
        parent: Optional parent widget.

    Signals:
        validation_changed: Emitted when validation errors change,
            carrying the list of ``SyntaxError_`` items.
    """

    validation_changed = Signal(list)

    def __init__(self, *, read_only: bool = False, parent: QWidget | None = None) -> None:
        """Initialise the code editor with gutter, highlighter, and timers."""
        super().__init__(parent)
        self.setObjectName("codeEditor")

        self._read_only = read_only
        self._language = "text"
        self._word_wrap = True
        self._errors: list[SyntaxError_] = []
        self._fold_regions: dict[int, int] = {}  # start_line -> end_line
        # Sorted cache for fast viewport-clipped painting.
        # Each tuple: (start_line, end_line, leading_spaces).
        self._sorted_folds: list[tuple[int, int, int]] = []
        self._collapsed_folds: set[int] = set()
        self._search_selections: list[QTextEdit.ExtraSelection] = []
        # Variable map for tooltip resolution
        self._variable_map: dict[str, str] = {}

        # Detected indent width for this document (auto-detected or default).
        self._detected_indent: int = _DEFAULT_INDENT_WIDTH

        # Collapsed-fold badge rectangles for click hit-testing.
        # Rebuilt each paintEvent; maps fold start-line -> viewport QRect.
        self._fold_badge_rects: dict[int, QRect] = {}

        # Cache for the active (innermost) fold region at the cursor.
        self._active_fold_start: int = -1

        if read_only:
            self.setReadOnly(True)

        # Highlighter
        self._highlighter = PygmentsHighlighter(self.document(), read_only=read_only)

        # Gutter widgets
        self._line_number_area = _LineNumberArea(self)
        self._fold_gutter_area = _FoldGutterArea(self)

        # Pre-built Phosphor fold font (avoids per-line allocation).
        self._fold_font: QFont | None = None

        # Debounce timers
        self._fold_timer = QTimer(self)
        self._fold_timer.setSingleShot(True)
        self._fold_timer.setInterval(_FOLD_DEBOUNCE_MS)
        self._fold_timer.timeout.connect(self._recompute_folds)

        self._validate_timer = QTimer(self)
        self._validate_timer.setSingleShot(True)
        self._validate_timer.setInterval(_VALIDATE_DEBOUNCE_MS)
        self._validate_timer.timeout.connect(self._validate)

        # Cursor-move debounce — coalesces bracket-match + active-guide
        # refresh so a 60fps scroll doesn't trigger them every frame.
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.setInterval(_CURSOR_DEBOUNCE_MS)
        self._cursor_timer.timeout.connect(self._on_cursor_idle)

        # Connect signals
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutters)
        self.cursorPositionChanged.connect(self._cursor_timer.start)

        # Enable mouse tracking so mouseMoveEvent fires for badge hover.
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        if not read_only:
            self.document().contentsChanged.connect(self._on_contents_changed)

        self._update_gutter_width()

    # -- Language -------------------------------------------------------

    @property
    def language(self) -> str:
        """Return the active language."""
        return self._language

    def set_language(self, language: str) -> None:
        """Switch syntax highlighting, folding, and validation language."""
        lang = language.lower()
        if lang == self._language:
            return
        self._language = lang
        self._highlighter.set_language(lang)
        self._errors = []
        self._fold_regions = {}
        self._collapsed_folds = set()
        self._sorted_folds = []
        self._active_fold_start = -1
        self.validation_changed.emit([])
        if not self._read_only:
            self._fold_timer.start()
            self._validate_timer.start()
        else:
            self._recompute_folds()

    # -- Content helpers ------------------------------------------------

    def set_variable_map(self, variables: dict[str, str]) -> None:
        """Update the variable resolution map and rehighlight."""
        self._variable_map = variables
        self._highlighter.rehighlight()

    def setPlainText(self, text: str) -> None:
        """Override to re-detect indent width whenever content is replaced."""
        super().setPlainText(text)
        self._detect_indent_width()

    def set_text(self, text: str) -> None:
        """Set the editor content and recache if read-only."""
        self.setPlainText(text)
        if self._read_only:
            self._highlighter.cache_full_document()
            self._highlighter.rehighlight()
        self._recompute_folds()
        self._validate()

    # -- Prettify -------------------------------------------------------

    def prettify(self) -> bool:
        """Auto-format the current content. Return True if formatting changed."""
        text = self.toPlainText()
        if not text.strip():
            return False

        if self._language == "json":
            try:
                parsed = json.loads(text)
                pretty = json.dumps(parsed, indent=4, ensure_ascii=False)
                if pretty != text:
                    self.setPlainText(pretty)
                    return True
            except (json.JSONDecodeError, TypeError):
                pass
        elif self._language in ("xml", "html"):
            try:
                dom = xml.dom.minidom.parseString(text)
                pretty = dom.toprettyxml(indent="    ")
                if pretty != text:
                    self.setPlainText(pretty)
                    return True
            except Exception:
                pass
        return False

    # -- Word wrap ------------------------------------------------------

    def is_word_wrap(self) -> bool:
        """Return whether word wrap is enabled."""
        return self._word_wrap

    def set_word_wrap(self, enabled: bool) -> None:
        """Toggle word wrapping."""
        self._word_wrap = enabled
        if enabled:
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        else:
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    # -- Search selections (for external find-in-body) ------------------

    def set_search_selections(self, selections: list[QTextEdit.ExtraSelection]) -> None:
        """Store search highlight selections and refresh extra selections."""
        self._search_selections = selections
        self._refresh_extra_selections()

    # -- Rebuild on theme change ----------------------------------------

    def rebuild_highlight_formats(self) -> None:
        """Rebuild syntax colours from the current theme palette."""
        self._highlighter.rebuild_formats()

    # -- Cursor-idle handler (debounced) --------------------------------

    def _on_cursor_idle(self) -> None:
        """Handle bracket matching and active-guide update after cursor settles."""
        self._highlight_matching_bracket()
        self._update_active_fold()

    @staticmethod
    def _effective_indent(block: QTextBlock) -> int:
        """Return the effective indent (in spaces) for *block*.

        For non-blank lines this is just the leading whitespace count.
        For blank lines, scan both forward and backward for the nearest
        non-blank neighbour and return the **maximum** of their indents
        so that guides stay continuous across empty stretches.
        """
        txt = block.text()
        if txt.strip():
            return len(txt) - len(txt.lstrip())
        # Blank line — use the max indent of nearest non-blank neighbours
        # so guides continue through empty lines within indented blocks.
        fwd = 0
        blk = block.next()
        while blk.isValid():
            t = blk.text()
            if t.strip():
                fwd = len(t) - len(t.lstrip())
                break
            blk = blk.next()
        bwd = 0
        blk = block.previous()
        while blk.isValid():
            t = blk.text()
            if t.strip():
                bwd = len(t) - len(t.lstrip())
                break
            blk = blk.previous()
        return max(fwd, bwd)

    def _active_indent_col(self, cursor_line: int) -> tuple[int, int, int]:
        """Return the active guide info for the cursor's innermost fold.

        Returns ``(column, fold_start_line, fold_end_line)``.
        The guide should only be highlighted between ``fold_start_line``
        and ``fold_end_line`` — not across the entire document.

        The column equals the fold opener's leading whitespace snapped to
        the indent grid (scope-opener position, not content position).

        Returns ``(-1, -1, -1)`` when the cursor is not inside any fold.
        """
        iw = self._detected_indent
        best_col = -1
        best_start = -1
        best_end = -1
        best_span = float("inf")
        for start_line, end_line, leading in self._sorted_folds:
            if start_line <= cursor_line <= end_line:
                span = end_line - start_line
                if span < best_span:
                    best_span = span
                    # Guide sits at the fold opener's column, snapped
                    # to the indent grid — NOT at content column.
                    best_col = leading - (leading % iw) if iw else 0
                    best_start = start_line
                    best_end = end_line
        return (best_col, best_start, best_end)

    def _update_active_fold(self) -> None:
        """Recompute the innermost fold region at the cursor and repaint if changed."""
        cursor_line = self.textCursor().blockNumber()
        best_start = -1
        best_span = float("inf")
        for start_line, end_line, _leading in self._sorted_folds:
            if start_line <= cursor_line <= end_line:
                span = end_line - start_line
                if span < best_span:
                    best_span = span
                    best_start = start_line
        if best_start != self._active_fold_start:
            self._active_fold_start = best_start
            self.viewport().update()

    # -- Selection whitespace dots --------------------------------------

    def _paint_selection_whitespace(self, cursor: QTextCursor) -> None:
        """Draw small dots at each space character inside the current selection.

        Called from ``paintEvent`` when the cursor has an active selection.
        The dots are small filled circles centred within each space glyph,
        similar to Postman's selection whitespace indicator.
        """
        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()

        fm = self.fontMetrics()
        space_px = fm.horizontalAdvance(" ")
        if space_px <= 0:
            return

        content_offset = self.contentOffset()
        vp_top = self.viewport().rect().top()
        vp_bottom = self.viewport().rect().bottom()

        dot_color = QColor(COLOR_EDITOR_WHITESPACE_DOT)
        radius = _WHITESPACE_DOT_RADIUS

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot_color)

        # Iterate only visible blocks that overlap the selection.
        block = self.firstVisibleBlock()
        while block.isValid():
            geom = self.blockBoundingGeometry(block).translated(content_offset)
            if geom.top() > vp_bottom:
                break
            block_pos = block.position()
            block_len = block.length() - 1  # exclude trailing newline
            block_end = block_pos + block_len

            # Skip blocks entirely outside the selection.
            if block_end < sel_start or block_pos > sel_end:
                block = block.next()
                continue

            if block.isVisible() and geom.bottom() >= vp_top:
                text = block.text()
                layout = block.layout()
                # Local character range that is selected in this block.
                local_start = max(0, sel_start - block_pos)
                local_end = min(len(text), sel_end - block_pos)

                for i in range(local_start, local_end):
                    if text[i] != " ":
                        continue
                    line = layout.lineForTextPosition(i)
                    if not line.isValid():
                        continue
                    x_tuple: tuple[float, int] = line.cursorToX(i)  # type: ignore[assignment]
                    x = content_offset.x() + x_tuple[0]
                    cx = x + space_px / 2.0
                    cy = geom.top() + line.y() + line.height() / 2.0
                    painter.drawEllipse(
                        QRectF(
                            cx - radius,
                            cy - radius,
                            radius * 2,
                            radius * 2,
                        )
                    )

            block = block.next()

        painter.end()

    # -- Gutter geometry ------------------------------------------------

    def line_number_area_width(self) -> int:
        """Calculate the width needed for line numbers."""
        digits = max(1, len(str(self.blockCount())))
        return _GUTTER_PADDING + self.fontMetrics().horizontalAdvance("9") * digits + 4

    def _total_gutter_width(self) -> int:
        """Return total width of line-number + fold gutters."""
        fold_w = _FOLD_GUTTER_WIDTH if self._language in _FOLDABLE_LANGUAGES else 0
        return self.line_number_area_width() + fold_w

    def _update_gutter_width(self) -> None:
        """Update the left margin to accommodate gutters."""
        self.setViewportMargins(self._total_gutter_width(), 0, 0, 0)

    def _update_gutters(self, rect: QRect, dy: int) -> None:
        """Scroll and repaint gutters when the viewport changes."""
        if dy:
            self._line_number_area.scroll(0, dy)
            self._fold_gutter_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(), self._line_number_area.width(), rect.height()
            )
            self._fold_gutter_area.update(
                0, rect.y(), self._fold_gutter_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event) -> None:
        """Reposition gutter widgets on resize."""
        super().resizeEvent(event)
        cr = self.contentsRect()
        ln_w = self.line_number_area_width()
        self._line_number_area.setGeometry(QRect(cr.left(), cr.top(), ln_w, cr.height()))
        fold_w = _FOLD_GUTTER_WIDTH if self._language in _FOLDABLE_LANGUAGES else 0
        self._fold_gutter_area.setGeometry(QRect(cr.left() + ln_w, cr.top(), fold_w, cr.height()))

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint indent guides and collapsed-fold badges.

        Indent guides are drawn per visible line at each indent-level
        column that falls within the line's leading whitespace.  Blank
        lines inherit the indent depth of the nearest non-blank
        neighbour so guides stay continuous.

        After indent guides, a small ``...`` pill badge is drawn at the
        end of each visible collapsed-fold header line.  Badge rectangles
        are cached in ``_fold_badge_rects`` for click hit-testing.
        """
        super().paintEvent(event)

        # 0. Whitespace dots — small centered circles at each space
        #    character within the current text selection (all languages).
        cursor = self.textCursor()
        if cursor.hasSelection():
            self._paint_selection_whitespace(cursor)

        if self._language not in _FOLDABLE_LANGUAGES:
            self._fold_badge_rects = {}
            return

        fm = self.fontMetrics()
        space_px = fm.horizontalAdvance(" ")
        if space_px <= 0:
            self._fold_badge_rects = {}
            return

        content_offset = self.contentOffset()
        base_x = self.document().documentMargin() + content_offset.x()
        doc = self.document()
        vp_top = self.viewport().rect().top()
        vp_bottom = self.viewport().rect().bottom()

        normal_pen = QPen(QColor(COLOR_EDITOR_INDENT_GUIDE))
        normal_pen.setWidth(1)
        active_pen = QPen(QColor(COLOR_EDITOR_ACTIVE_INDENT_GUIDE))
        active_pen.setWidth(1)

        painter = QPainter(self.viewport())

        # 1. Indent guides — draw a short vertical segment at each
        #    *scope-opener* column for every visible line whose leading
        #    whitespace reaches that depth.
        #
        #    The loop iterates indent levels (level=1, 2, ...) while
        #    level * iw < indent.  Each guide is drawn at (level-1)*iw
        #    — shifted left by one indent width — so guides sit at the
        #    enclosing brace / bracket column, not the content column.
        #
        #    Example (4-space JSON, line at indent 12 = 3 levels deep):
        #      level=1 -> draw at col 0  (root '{')
        #      level=2 -> draw at col 4  (nested '{')
        #      level=3 -> 12 < 12 false  -> stop, no guide at content col 12
        #
        #    Blank lines inherit the indent depth of the nearest non-blank
        #    neighbour so guides stay continuous.
        #    X-positions are computed via QTextLayout.cursorToX() so they
        #    align pixel-perfectly with the rendered text.
        cursor_line = self.textCursor().blockNumber()
        active_col, active_start, active_end = self._active_indent_col(cursor_line)
        iw = self._detected_indent

        block = self.firstVisibleBlock()
        while block.isValid():
            geom = self.blockBoundingGeometry(block).translated(content_offset)
            if geom.top() > vp_bottom:
                break
            if block.isVisible() and geom.bottom() >= vp_top:
                indent = self._effective_indent(block)
                layout = block.layout()
                line0 = layout.lineAt(0) if layout.lineCount() > 0 else None
                block_line = block.blockNumber()
                level = 1
                while level * iw <= indent:
                    # Draw at (level-1)*iw — one indent width to the left
                    # of the content column — so the guide marks the
                    # scope opener, not the content.
                    draw_col = (level - 1) * iw
                    if line0 is not None:
                        cursor_x: tuple[float, int] = line0.cursorToX(draw_col)  # type: ignore[assignment]
                        x = round(content_offset.x() + cursor_x[0])
                    else:
                        x = round(base_x + draw_col * space_px)
                    top_y = round(geom.top())
                    bot_y = round(geom.bottom())
                    # Only highlight the active guide within its fold range.
                    is_active = draw_col == active_col and active_start <= block_line <= active_end
                    painter.setPen(active_pen if is_active else normal_pen)
                    painter.drawLine(x, top_y, x, bot_y)
                    level += 1
            block = block.next()

        # 2. Collapsed-fold "..." badges
        badge_rects: dict[int, QRect] = {}
        if self._collapsed_folds:
            badge_bg = QColor(COLOR_EDITOR_FOLD_BADGE_BG)
            badge_fg = QColor(COLOR_EDITOR_FOLD_BADGE_TEXT)
            badge_w = fm.horizontalAdvance(_FOLD_BADGE_LABEL) + _FOLD_BADGE_H_PAD * 2
            badge_h = fm.height() - 2

            for start_line in self._collapsed_folds:
                block = doc.findBlockByNumber(start_line)
                if not block.isValid() or not block.isVisible():
                    continue

                geom = self.blockBoundingGeometry(block).translated(content_offset)
                if geom.bottom() < vp_top or geom.top() > vp_bottom:
                    continue

                # Position badge right after the line text
                text_width = fm.horizontalAdvance(block.text())
                bx = round(base_x + text_width + _FOLD_BADGE_GAP)
                by = round(geom.top() + (geom.height() - badge_h) / 2)
                rect = QRect(bx, by, badge_w, badge_h)

                # Draw rounded pill background
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(badge_bg)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.drawRoundedRect(QRectF(rect), _FOLD_BADGE_RADIUS, _FOLD_BADGE_RADIUS)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

                # Draw label text
                painter.setPen(badge_fg)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, _FOLD_BADGE_LABEL)

                badge_rects[start_line] = rect

        self._fold_badge_rects = badge_rects
        painter.end()

    # -- Line number painting -------------------------------------------

    def paint_line_number_area(self, event: QPaintEvent) -> None:
        """Paint line numbers and error markers in the gutter."""
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor(COLOR_EDITOR_GUTTER_BG))

        error_lines = {e.line for e in self._errors}

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        width = self._line_number_area.width()
        line_height = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                is_error = block_number + 1 in error_lines

                if is_error:
                    # Red background wash across gutter row
                    painter.fillRect(
                        0,
                        top,
                        width,
                        bottom - top,
                        QColor(COLOR_EDITOR_ERROR_GUTTER_BG),
                    )
                    painter.setPen(QColor(COLOR_EDITOR_ERROR_UNDERLINE))
                else:
                    painter.setPen(QColor(COLOR_EDITOR_GUTTER_TEXT))

                painter.drawText(
                    0,
                    top,
                    width - 4,
                    line_height,
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

        painter.end()

    # -- Fold gutter painting -------------------------------------------

    def paint_fold_gutter_area(self, event: QPaintEvent) -> None:
        """Paint fold indicators (Phosphor chevrons) in the fold gutter."""
        if self._language not in _FOLDABLE_LANGUAGES:
            return

        painter = QPainter(self._fold_gutter_area)
        painter.fillRect(event.rect(), QColor(COLOR_EDITOR_GUTTER_BG))

        # Phosphor font for glyph rendering (lazy-init once, reused).
        caret_right = glyph_char("caret-right-light")
        caret_down = glyph_char("caret-down-light")
        if self._fold_font is None:
            phi_family = font_family()
            if phi_family:
                f = QFont(phi_family)
                f.setPixelSize(16)
                self._fold_font = f
        if self._fold_font is not None:
            painter.setFont(self._fold_font)

        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line = block.blockNumber()
                if line in self._fold_regions:
                    is_collapsed = line in self._collapsed_folds
                    glyph = caret_right if is_collapsed else caret_down

                    if self._fold_font is not None and glyph:
                        painter.setPen(QColor(COLOR_EDITOR_FOLD_INDICATOR))
                        painter.drawText(
                            0,
                            top,
                            _FOLD_GUTTER_WIDTH,
                            bottom - top,
                            Qt.AlignmentFlag.AlignCenter,
                            glyph,
                        )
                    else:
                        # Fallback to simple text chevrons
                        painter.setPen(QColor(COLOR_EDITOR_FOLD_INDICATOR))
                        fallback = "\u203a" if is_collapsed else "\u2304"
                        painter.drawText(
                            0,
                            top,
                            _FOLD_GUTTER_WIDTH,
                            bottom - top,
                            Qt.AlignmentFlag.AlignCenter,
                            fallback,
                        )

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())

        painter.end()

    def is_fold_line_at(self, y: int) -> bool:
        """Return True if the viewport y-coordinate *y* is on a foldable line."""
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid():
            if top <= y <= bottom:
                return block.blockNumber() in self._fold_regions
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
        return False

    def fold_gutter_clicked(self, y: int) -> None:
        """Toggle fold for the block at viewport y-coordinate *y*."""
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid():
            if top <= y <= bottom:
                line = block.blockNumber()
                if line in self._fold_regions:
                    self.toggle_fold(line)
                return
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())

    # -- Fold logic -----------------------------------------------------

    def toggle_fold(self, line: int) -> None:
        """Collapse or expand the fold region starting at *line*."""
        if line not in self._fold_regions:
            return

        end_line = self._fold_regions[line]
        doc = self.document()

        if line in self._collapsed_folds:
            # Expand
            self._collapsed_folds.discard(line)
            block = doc.findBlockByNumber(line + 1)
            while block.isValid() and block.blockNumber() <= end_line:
                bn = block.blockNumber()
                # Only show if not inside another collapsed fold
                if not self._is_inside_collapsed_fold(bn, exclude=line):
                    block.setVisible(True)
                block = block.next()
        else:
            # Collapse — move cursor out first if needed
            cursor = self.textCursor()
            cursor_line = cursor.blockNumber()
            if line < cursor_line <= end_line:
                cursor.movePosition(
                    QTextCursor.MoveOperation.Start, QTextCursor.MoveMode.MoveAnchor
                )
                block_target = doc.findBlockByNumber(line)
                cursor.setPosition(block_target.position())
                self.setTextCursor(cursor)

            self._collapsed_folds.add(line)
            block = doc.findBlockByNumber(line + 1)
            while block.isValid() and block.blockNumber() <= end_line:
                block.setVisible(False)
                block = block.next()

        # Invalidate layout
        start_block = doc.findBlockByNumber(line)
        end_block = doc.findBlockByNumber(end_line)
        start_pos = start_block.position()
        length = end_block.position() + end_block.length() - start_pos
        doc.markContentsDirty(start_pos, length)
        self.viewport().update()
        self._line_number_area.update()
        self._fold_gutter_area.update()
        self._refresh_extra_selections()

    def _is_inside_collapsed_fold(self, line: int, *, exclude: int = -1) -> bool:
        """Check if *line* is inside any collapsed fold (except *exclude*)."""
        for start in self._collapsed_folds:
            if start == exclude:
                continue
            end = self._fold_regions.get(start, -1)
            if start < line <= end:
                return True
        return False

    def fold_all(self) -> None:
        """Collapse all foldable regions (batched for performance)."""
        if not self._fold_regions:
            return
        doc = self.document()
        for start_line, end_line in self._fold_regions.items():
            if start_line in self._collapsed_folds:
                continue
            self._collapsed_folds.add(start_line)
            block = doc.findBlockByNumber(start_line + 1)
            while block.isValid() and block.blockNumber() <= end_line:
                block.setVisible(False)
                block = block.next()
        # Single layout invalidation for the whole document
        doc.markContentsDirty(0, doc.characterCount())
        self.viewport().update()
        self._line_number_area.update()
        self._fold_gutter_area.update()

    def unfold_all(self) -> None:
        """Expand all collapsed regions (batched for performance)."""
        if not self._collapsed_folds:
            return
        doc = self.document()
        self._collapsed_folds.clear()
        block = doc.begin()
        while block.isValid():
            if not block.isVisible():
                block.setVisible(True)
            block = block.next()
        doc.markContentsDirty(0, doc.characterCount())
        self.viewport().update()
        self._line_number_area.update()
        self._fold_gutter_area.update()

    # -- Fold detection -------------------------------------------------

    def _on_contents_changed(self) -> None:
        """Schedule fold recomputation and validation after content change."""
        self._fold_timer.start()
        if self._language in _VALIDATABLE_LANGUAGES:
            self._validate_timer.start()

    def _detect_indent_width(self) -> None:
        """Scan up to ``_INDENT_SCAN_LINES`` lines and detect the indent unit.

        Counts the most common non-zero leading-space run and picks the
        smallest that appears at least twice.  Falls back to
        ``_DEFAULT_INDENT_WIDTH``.
        """
        counts: dict[int, int] = {}
        block = self.document().begin()
        scanned = 0
        while block.isValid() and scanned < _INDENT_SCAN_LINES:
            txt = block.text()
            if txt and txt[0] == " ":
                leading = len(txt) - len(txt.lstrip(" "))
                if leading > 0:
                    counts[leading] = counts.get(leading, 0) + 1
            block = block.next()
            scanned += 1

        if not counts:
            self._detected_indent = _DEFAULT_INDENT_WIDTH
            return

        # Look at differences between indent levels to find the step.
        # For example with indents of 2,4,6 the GCD-like step is 2.
        levels = sorted(counts)
        diffs: dict[int, int] = {}
        # Count the indent values themselves as candidates
        for lv in levels:
            diffs[lv] = diffs.get(lv, 0) + counts[lv]
        # Count differences between consecutive observed levels
        for i in range(1, len(levels)):
            d = levels[i] - levels[i - 1]
            if d > 0:
                diffs[d] = diffs.get(d, 0) + min(counts[levels[i]], counts[levels[i - 1]])

        # Pick the smallest candidate that appears meaningfully
        for candidate in (2, 4, 8, 3, 6):
            if diffs.get(candidate, 0) >= 1:
                self._detected_indent = candidate
                return

        self._detected_indent = _DEFAULT_INDENT_WIDTH

    def _recompute_folds(self) -> None:
        """Detect foldable regions based on the active language."""
        if self._language not in _FOLDABLE_LANGUAGES:
            self._fold_regions = {}
            self._collapsed_folds = set()
            self._sorted_folds = []
            self._active_fold_start = -1
            self._update_gutter_width()
            return

        doc = self.document()
        if self._language in ("json", "graphql"):
            folds = self._detect_bracket_folds(doc)
        elif self._language in ("xml", "html"):
            folds = self._detect_xml_folds(doc)
        else:
            folds = {}

        # Preserve collapsed state for regions that still exist
        new_collapsed = self._collapsed_folds & set(folds)
        self._fold_regions = folds
        self._collapsed_folds = new_collapsed

        # Rebuild the sorted fold cache used by paintEvent.
        doc = self.document()
        sorted_folds: list[tuple[int, int, int]] = []
        for start, end in sorted(folds.items()):
            blk = doc.findBlockByNumber(start)
            if blk.isValid():
                txt = blk.text()
                leading = len(txt) - len(txt.lstrip())
            else:
                leading = 0
            sorted_folds.append((start, end, leading))
        self._sorted_folds = sorted_folds

        self._update_gutter_width()
        self._fold_gutter_area.update()
        # Indent guides are painted in the viewport's paintEvent, so we
        # must schedule a viewport repaint whenever fold regions change.
        self._update_active_fold()
        self.viewport().update()

    @staticmethod
    def _detect_bracket_folds(doc: QTextDocument) -> dict[int, int]:
        """Detect JSON/GraphQL fold regions from bracket pairs."""
        stack: list[int] = []
        folds: dict[int, int] = {}
        block = doc.begin()
        while block.isValid():
            text = block.text()
            in_string = False
            escape = False
            for ch in text:
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch in ("{", "["):
                    stack.append(block.blockNumber())
                elif ch in ("}", "]") and stack:
                    start = stack.pop()
                    if block.blockNumber() > start:
                        folds[start] = block.blockNumber()
            block = block.next()
        return folds

    @staticmethod
    def _detect_xml_folds(doc: QTextDocument) -> dict[int, int]:
        """Detect XML/HTML fold regions from tag pairs."""
        stack: list[tuple[str, int]] = []
        folds: dict[int, int] = {}
        block = doc.begin()
        while block.isValid():
            text = block.text()
            # Remove self-closing tags first
            cleaned = _XML_SELF_CLOSE.sub("", text)
            for m in _XML_OPEN_TAG.finditer(cleaned):
                stack.append((m.group(1), block.blockNumber()))
            for m in _XML_CLOSE_TAG.finditer(cleaned):
                tag = m.group(1)
                for i in range(len(stack) - 1, -1, -1):
                    if stack[i][0] == tag:
                        start = stack[i][1]
                        if block.blockNumber() > start:
                            folds[start] = block.blockNumber()
                        stack.pop(i)
                        break
            block = block.next()
        return folds

    # -- Bracket matching -----------------------------------------------

    def _highlight_matching_bracket(self) -> None:
        """Highlight the bracket pair at the cursor position."""
        self._refresh_extra_selections()

    def _refresh_extra_selections(self) -> None:
        """Combine bracket-match, error, and search extra selections."""
        selections: list[QTextEdit.ExtraSelection] = []

        # 1. Bracket matching
        cursor = self.textCursor()
        block = cursor.block()
        pos_in_block = cursor.positionInBlock()
        text = block.text()

        for offset in (0, -1):
            check_pos = pos_in_block + offset
            if check_pos < 0 or check_pos >= len(text):
                continue
            ch = text[check_pos]
            if ch not in _ALL_BRACKETS:
                continue

            abs_pos = block.position() + check_pos
            match_pos = self._find_matching_bracket(abs_pos, ch)
            if match_pos >= 0:
                fmt = QTextCharFormat()
                fmt.setBackground(QColor(COLOR_EDITOR_BRACKET_MATCH))

                sel1 = QTextEdit.ExtraSelection()
                cur1 = QTextCursor(self.document())
                cur1.setPosition(abs_pos)
                cur1.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
                sel1.cursor = cur1
                sel1.format = fmt
                selections.append(sel1)

                sel2 = QTextEdit.ExtraSelection()
                cur2 = QTextCursor(self.document())
                cur2.setPosition(match_pos)
                cur2.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
                sel2.cursor = cur2
                sel2.format = fmt
                selections.append(sel2)
                break

        # 2. Collapsed-fold highlight
        selections.extend(self._collapsed_fold_selections())

        # 3. Error underline selections
        selections.extend(self._error_selections())

        # 4. External search selections
        selections.extend(self._search_selections)

        self.setExtraSelections(selections)

    def _find_matching_bracket(self, pos: int, bracket: str) -> int:
        """Find the position of the matching bracket. Return -1 if not found.

        The search is capped at ``_BRACKET_SEARCH_LIMIT`` characters in
        either direction to keep the operation fast on large documents.
        """
        doc = self.document()
        if bracket in _BRACKET_PAIRS:
            # Search forward
            target = _BRACKET_PAIRS[bracket]
            depth = 1
            i = pos + 1
            limit = min(doc.characterCount(), pos + 1 + _BRACKET_SEARCH_LIMIT)
            while i < limit:
                ch = doc.characterAt(i)
                if ch == bracket:
                    depth += 1
                elif ch == target:
                    depth -= 1
                    if depth == 0:
                        return i
                i += 1
        elif bracket in _CLOSE_TO_OPEN:
            # Search backward
            target = _CLOSE_TO_OPEN[bracket]
            depth = 1
            i = pos - 1
            limit = max(0, pos - _BRACKET_SEARCH_LIMIT)
            while i >= limit:
                ch = doc.characterAt(i)
                if ch == bracket:
                    depth += 1
                elif ch == target:
                    depth -= 1
                    if depth == 0:
                        return i
                i -= 1
        return -1

    # -- Block indent / outdent -----------------------------------------

    @staticmethod
    def _indent_selection(cursor: QTextCursor, indent_width: int) -> None:
        """Prepend *indent_width* spaces to every line touched by *cursor*.

        The selection is extended afterward so it still covers the same
        logical text, shifted right.
        """
        indent = " " * indent_width
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        cursor.beginEditBlock()

        # Move to the first line of the selection
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        first_block = cursor.blockNumber()

        cursor.setPosition(end, QTextCursor.MoveMode.MoveAnchor)
        if cursor.positionInBlock() == 0 and cursor.blockNumber() > first_block:
            # Selection ends at col 0 of a new line — don't indent that line
            cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
        last_block = cursor.blockNumber()

        # Walk each line and prepend the indent string
        blk = cursor.document().findBlockByNumber(first_block)
        while blk.isValid() and blk.blockNumber() <= last_block:
            cursor.setPosition(blk.position())
            cursor.insertText(indent)
            blk = blk.next()

        cursor.endEditBlock()

        # Restore selection covering the indented range
        new_start = cursor.document().findBlockByNumber(first_block).position()
        end_block = cursor.document().findBlockByNumber(last_block)
        new_end = end_block.position() + len(end_block.text())
        cursor.setPosition(new_start)
        cursor.setPosition(new_end, QTextCursor.MoveMode.KeepAnchor)

    @staticmethod
    def _outdent_selection(cursor: QTextCursor, indent_width: int) -> None:
        """Remove up to *indent_width* leading spaces from every selected line."""
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        cursor.beginEditBlock()

        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        first_block = cursor.blockNumber()

        cursor.setPosition(end, QTextCursor.MoveMode.MoveAnchor)
        if cursor.positionInBlock() == 0 and cursor.blockNumber() > first_block:
            cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
        last_block = cursor.blockNumber()

        blk = cursor.document().findBlockByNumber(first_block)
        while blk.isValid() and blk.blockNumber() <= last_block:
            txt = blk.text()
            leading = len(txt) - len(txt.lstrip(" "))
            remove = min(indent_width, leading)
            if remove > 0:
                cursor.setPosition(blk.position())
                for _ in range(remove):
                    cursor.deleteChar()
            blk = blk.next()

        cursor.endEditBlock()

        # Restore selection covering the outdented range
        new_start = cursor.document().findBlockByNumber(first_block).position()
        end_block = cursor.document().findBlockByNumber(last_block)
        new_end = end_block.position() + len(end_block.text())
        cursor.setPosition(new_start)
        cursor.setPosition(new_end, QTextCursor.MoveMode.KeepAnchor)

    # -- Auto-close brackets --------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle Tab-to-spaces, auto-closing brackets and quotes."""
        if self._read_only:
            super().keyPressEvent(event)
            return

        iw = self._detected_indent

        # Tab — block indent when a multi-line selection exists,
        # otherwise insert spaces at the cursor.
        if event.key() == Qt.Key.Key_Tab and not event.modifiers():
            cursor = self.textCursor()
            if cursor.hasSelection():
                self._indent_selection(cursor, iw)
            else:
                cursor.insertText(" " * iw)
            return

        # Shift+Tab — block outdent for selection, or remove leading
        # spaces on the current line.
        if event.key() == Qt.Key.Key_Backtab:
            cursor = self.textCursor()
            if cursor.hasSelection():
                self._outdent_selection(cursor, iw)
            else:
                block_text = cursor.block().text()
                leading = len(block_text) - len(block_text.lstrip(" "))
                remove = min(iw, leading)
                if remove > 0:
                    cursor.movePosition(
                        QTextCursor.MoveOperation.StartOfBlock,
                        QTextCursor.MoveMode.MoveAnchor,
                    )
                    for _ in range(remove):
                        cursor.deleteChar()
                    self.setTextCursor(cursor)
            return

        text = event.text()
        cursor = self.textCursor()

        # Auto-close pairs
        if text in _AUTO_CLOSE_PAIRS:
            closing = _AUTO_CLOSE_PAIRS[text]

            # Skip if the closing char matches what's next
            block_text = cursor.block().text()
            pos_in_block = cursor.positionInBlock()
            if text == closing and pos_in_block < len(block_text):
                next_char = block_text[pos_in_block]
                if next_char == closing:
                    # Just move past it
                    cursor.movePosition(
                        QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor
                    )
                    self.setTextCursor(cursor)
                    return

            if cursor.hasSelection():
                # Wrap selection
                selected = cursor.selectedText()
                cursor.insertText(text + selected + closing)
            else:
                cursor.insertText(text + closing)
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor)
                self.setTextCursor(cursor)
            return

        # Skip over closing bracket if typed and matches next char
        if text in _CLOSE_TO_OPEN or text in (")", "]", "}"):
            block_text = cursor.block().text()
            pos_in_block = cursor.positionInBlock()
            if pos_in_block < len(block_text) and block_text[pos_in_block] == text:
                cursor.movePosition(
                    QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor
                )
                self.setTextCursor(cursor)
                return

        super().keyPressEvent(event)

    # -- Validation -----------------------------------------------------

    @property
    def errors(self) -> list[SyntaxError_]:
        """Return current validation errors."""
        return list(self._errors)

    def _validate(self) -> None:
        """Run syntax validation on the current content."""
        text = self.toPlainText()
        errors: list[SyntaxError_] = []

        if self._language == "json" and text.strip():
            try:
                json.loads(text)
            except json.JSONDecodeError as e:
                errors.append(SyntaxError_(line=e.lineno, column=e.colno, message=e.msg))

        elif self._language == "xml" and text.strip():
            try:
                ET.fromstring(text)
            except ET.ParseError as e:
                line, col = e.position if hasattr(e, "position") else (1, 0)
                errors.append(SyntaxError_(line=line, column=col, message=str(e)))

        elif self._language == "graphql" and text.strip():
            errors.extend(self._validate_graphql_braces(text))

        old_has_errors = bool(self._errors)
        new_has_errors = bool(errors)
        self._errors = errors
        self.validation_changed.emit(errors)

        # Refresh extra selections if error state changed
        if old_has_errors or new_has_errors:
            self._highlight_matching_bracket()
            self._line_number_area.update()

    @staticmethod
    def _validate_graphql_braces(text: str) -> list[SyntaxError_]:
        """Check that braces and parentheses are balanced in a GraphQL body.

        This is a best-effort heuristic — a full GraphQL parser would
        require an additional dependency.  Brace-balance catches the most
        common structural errors (missing closing brace, extra paren, etc.).
        """
        errors: list[SyntaxError_] = []
        stack: list[tuple[str, int]] = []
        openers = {"{": "}", "(": ")"}
        closers = {"}": "{", ")": "("}

        for line_idx, line in enumerate(text.splitlines(), start=1):
            for col_idx, ch in enumerate(line, start=1):
                if ch in openers:
                    stack.append((ch, line_idx))
                elif ch in closers:
                    if not stack or stack[-1][0] != closers[ch]:
                        errors.append(
                            SyntaxError_(
                                line=line_idx,
                                column=col_idx,
                                message=f"Unexpected '{ch}'",
                            )
                        )
                        return errors
                    stack.pop()

        if stack:
            opener, open_line = stack[-1]
            errors.append(
                SyntaxError_(
                    line=open_line,
                    column=1,
                    message=f"Unclosed '{opener}'",
                )
            )

        return errors

    def _collapsed_fold_selections(self) -> list[QTextEdit.ExtraSelection]:
        """Build ExtraSelections to highlight collapsed fold-header lines."""
        selections: list[QTextEdit.ExtraSelection] = []
        if not self._collapsed_folds:
            return selections

        doc = self.document()
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(COLOR_EDITOR_FOLD_HIGHLIGHT))
        fmt.setProperty(QTextCharFormat.Property.FullWidthSelection, True)

        for start_line in self._collapsed_folds:
            block = doc.findBlockByNumber(start_line)
            if not block.isValid():
                continue
            sel = QTextEdit.ExtraSelection()
            cur = QTextCursor(block)
            cur.clearSelection()
            sel.cursor = cur
            sel.format = fmt
            selections.append(sel)

        return selections

    def _error_selections(self) -> list[QTextEdit.ExtraSelection]:
        """Build ExtraSelections for validation errors (wave underline)."""
        selections: list[QTextEdit.ExtraSelection] = []
        doc = self.document()

        for error in self._errors:
            block = doc.findBlockByNumber(error.line - 1)
            if not block.isValid():
                continue

            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            fmt.setUnderlineColor(QColor(COLOR_EDITOR_ERROR_UNDERLINE))

            sel = QTextEdit.ExtraSelection()
            cur = QTextCursor(block)
            # Underline from error column to end of line
            col = max(0, error.column - 1)
            cur.movePosition(
                QTextCursor.MoveOperation.Right,
                QTextCursor.MoveMode.MoveAnchor,
                col,
            )
            cur.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            sel.cursor = cur
            sel.format = fmt
            selections.append(sel)

        return selections

    # -- Tooltip for errors ---------------------------------------------

    def event(self, event: QEvent) -> bool:
        """Show tooltip for error messages and variable references on hover."""
        if event.type() == QEvent.Type.ToolTip:
            help_event = cast("QHelpEvent", event)
            cursor = self.cursorForPosition(help_event.pos())
            line = cursor.blockNumber() + 1

            # 1. Check for error tooltip
            for error in self._errors:
                if error.line == line:
                    QToolTip.showText(
                        help_event.globalPos(),
                        f"Line {error.line}: {error.message}",
                        self,
                    )
                    return True

            # 2. Check for variable tooltip
            block = cursor.block()
            block_text = block.text()
            pos_in_block = cursor.positionInBlock()
            if "{{" in block_text:
                for match in _VAR_RE.finditer(block_text):
                    if match.start() <= pos_in_block <= match.end():
                        var_name = match.group(1)
                        resolved = self._variable_map.get(var_name)
                        if resolved is not None:
                            QToolTip.showText(
                                help_event.globalPos(),
                                f"{var_name} = {resolved}",
                                self,
                            )
                        else:
                            QToolTip.showText(
                                help_event.globalPos(),
                                f"{var_name} (unresolved)",
                                self,
                            )
                        return True

            QToolTip.hideText()
            return True
        return super().event(event)

    # -- Fold badge interaction -----------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Expand a collapsed fold when its ``...`` badge is clicked."""
        if event.button() == Qt.MouseButton.LeftButton and self._fold_badge_rects:
            pos = event.position().toPoint()
            for start_line, rect in self._fold_badge_rects.items():
                if rect.contains(pos):
                    self.toggle_fold(start_line)
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Show a hand cursor when hovering over a collapsed-fold badge."""
        if self._fold_badge_rects:
            pos = event.position().toPoint()
            for rect in self._fold_badge_rects.values():
                if rect.contains(pos):
                    self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
                    super().mouseMoveEvent(event)
                    return
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(event)
