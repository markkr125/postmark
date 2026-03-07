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
from PySide6.QtGui import QMouseEvent, QPaintEvent, QTextBlockUserData
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

# Regex for XML/HTML fold detection
_XML_OPEN_TAG = re.compile(r"<(\w[\w.\-:]*)(?:\s[^>]*)?\s*>")
_XML_CLOSE_TAG = re.compile(r"</(\w[\w.\-:]*)\s*>")
_XML_SELF_CLOSE = re.compile(r"<\w[\w.\-:]*(?:\s[^>]*)?\s*/>")

# Languages that support validation
_VALIDATABLE_LANGUAGES = {"json", "xml", "graphql"}

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
