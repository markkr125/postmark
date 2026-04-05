"""Gutter widgets and data structures for the code editor.

Provides:

* ``SyntaxError_`` — named-tuple for validation errors.
* ``_FoldData`` — per-block user data for code folding state.
* ``_LineNumberArea`` / ``_FoldGutterArea`` — gutter ``QWidget``
  sub-classes that delegate painting back to the editor.

Also hosts shared constants and regexes used across the sub-package.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPaintEvent, QTextBlockUserData
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from ui.widgets.code_editor.editor_widget import CodeEditorWidget

# Regex for {{variable}} references
_VAR_RE = re.compile(r"\{\{(.+?)\}\}")


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
_BREAKPOINT_GUTTER_WIDTH = 14  # px — breakpoint indicator column

# Regex for XML/HTML fold detection
_XML_OPEN_TAG = re.compile(r"<(\w[\w.\-:]*)(?:\s[^>]*)?\s*>")
_XML_CLOSE_TAG = re.compile(r"</(\w[\w.\-:]*)\s*>")
_XML_SELF_CLOSE = re.compile(r"<\w[\w.\-:]*(?:\s[^>]*)?\s*/>")

# Languages that support validation
_VALIDATABLE_LANGUAGES = {"json", "xml", "graphql", "javascript", "python"}

# Languages that support folding
_FOLDABLE_LANGUAGES = {"json", "xml", "html", "graphql"}


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


class _BreakpointGutterArea(QWidget):
    """Breakpoint indicator gutter for the code editor.

    Displays red circles for set breakpoints and a yellow arrow for
    the current debug line.  Click to toggle breakpoints.
    """

    def __init__(self, editor: CodeEditorWidget) -> None:
        """Initialise the breakpoint gutter area."""
        super().__init__(editor)
        self._editor = editor
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        """Return the fixed breakpoint gutter width."""
        return QSize(_BREAKPOINT_GUTTER_WIDTH, 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Delegate painting to the editor."""
        self._editor.paint_breakpoint_area(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Toggle breakpoint on click."""
        self._editor.breakpoint_gutter_clicked(event.position().toPoint().y())


# -- Minimap -----------------------------------------------------------

# Width and rendering constants for the minimap widget.
_MINIMAP_WIDTH = 60
_MINIMAP_LINE_ALPHA = 120
_MINIMAP_VIEWPORT_ALPHA = 40


class _MinimapArea(QWidget):
    """Compact bird's-eye view of the parent editor's document.

    Draws each line as a thin coloured bar.  A semi-transparent overlay
    indicates the visible viewport.  Click or drag to scroll.
    """

    def __init__(self, editor: CodeEditorWidget) -> None:
        """Initialise the minimap."""
        super().__init__(editor)
        self._editor = editor
        self.setFixedWidth(_MINIMAP_WIDTH)
        self._editor.verticalScrollBar().valueChanged.connect(self.update)
        self._editor.document().contentsChanged.connect(self.update)
        self.setMouseTracking(True)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Render the minimap lines and viewport indicator."""
        from PySide6.QtGui import QPainter

        painter = QPainter(self)
        doc = self._editor.document()
        total_lines = doc.blockCount()
        if total_lines == 0:
            painter.end()
            return

        h = self.height()
        w = self.width()
        line_h = max(1.0, h / total_lines)

        # Draw code lines as thin bars
        line_color = QColor(180, 180, 180, _MINIMAP_LINE_ALPHA)
        block = doc.begin()
        y = 0.0
        while block.isValid():
            text = block.text()
            if text.strip():
                indent = len(text) - len(text.lstrip())
                bar_w = min(w - 4, max(4, int((len(text.rstrip()) - indent) * 0.5)))
                x = min(indent * 2, w - 4)
                painter.fillRect(int(x), int(y), bar_w, max(1, int(line_h)), line_color)
            y += line_h
            block = block.next()

        # Draw viewport indicator
        sb = self._editor.verticalScrollBar()
        max_scroll = sb.maximum() + sb.pageStep()
        if max_scroll > 0:
            visible_start = sb.value() / max_scroll * h
            visible_h = sb.pageStep() / max_scroll * h
            painter.fillRect(
                0,
                int(visible_start),
                w,
                max(4, int(visible_h)),
                QColor(100, 100, 255, _MINIMAP_VIEWPORT_ALPHA),
            )
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Scroll the editor to the clicked position."""
        self._scroll_to(event.position().toPoint().y())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Scroll while dragging."""
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._scroll_to(event.position().toPoint().y())

    def _scroll_to(self, y: int) -> None:
        """Scroll the editor so the viewport is centred on *y*."""
        h = self.height()
        if h <= 0:
            return
        ratio = y / h
        sb = self._editor.verticalScrollBar()
        sb.setValue(int(ratio * sb.maximum()))
