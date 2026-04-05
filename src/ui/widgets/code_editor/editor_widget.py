"""Core ``CodeEditorWidget``.

A ``QPlainTextEdit`` subclass with syntax highlighting, line-number gutter,
code folding, bracket matching, inline validation, prettify, word-wrap,
and ``{{variable}}`` hover popups.

The widget is used by the request body editor, response viewer, code
snippet dialog, and folder script editors.

Performance notes
-----------------
Large responses (5 000+ lines) must remain smooth.  Hot paths are:

* **paintEvent** — runs every frame during scroll.  Only fold regions
  overlapping the visible viewport are processed.
* **_find_matching_bracket** — bounded by ``_BRACKET_SEARCH_LIMIT``.
* **cursorPositionChanged** — debounced to avoid redundant work.
"""

from __future__ import annotations

import json
import xml.dom.minidom
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QHelpEvent, QKeyEvent, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QToolTip, QWidget

if TYPE_CHECKING:
    from services.environment_service import VariableDetail

from ui.widgets.code_editor.completion.engine import CompletionEngine
from ui.widgets.code_editor.completion.mixin import _CompletionMixin
from ui.widgets.code_editor.completion.popup import CompletionPopup
from ui.widgets.code_editor.folding import _FoldingMixin
from ui.widgets.code_editor.gutter import (
    _AUTO_CLOSE_PAIRS,
    _CLOSE_TO_OPEN,
    _CURSOR_DEBOUNCE_MS,
    _DEFAULT_INDENT_WIDTH,
    _FOLD_DEBOUNCE_MS,
    _VALIDATE_DEBOUNCE_MS,
    _VAR_RE,
    SyntaxError_,
    _BreakpointGutterArea,
    _FoldGutterArea,
    _LineNumberArea,
    _MinimapArea,
)
from ui.widgets.code_editor.highlighter import PygmentsHighlighter
from ui.widgets.code_editor.painting import _PaintingMixin


class CodeEditorWidget(_CompletionMixin, _PaintingMixin, _FoldingMixin, QPlainTextEdit):
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
    breakpoints_changed = Signal()
    diff_fold_toggled = Signal(int)
    cursor_position_changed = Signal(int, int)  # (1-based line, 1-based col)

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
        self._sorted_folds: list[tuple[int, int, int]] = []
        self._collapsed_folds: set[int] = set()
        self._search_selections: list[QTextEdit.ExtraSelection] = []
        self._diff_selections: list[QTextEdit.ExtraSelection] = []
        self._diff_line_colors: dict[int, QColor] = {}
        self._diff_fold_ranges: list[tuple[int, int]] = []
        self._collapsed_diff_folds: set[int] = set()
        self._variable_map: dict[str, VariableDetail] = {}

        # Hover tracking for fast variable popup display
        self._var_hover_name: str | None = None
        self._var_hover_timer = QTimer(self)
        self._var_hover_timer.setSingleShot(True)
        self._var_hover_timer.timeout.connect(self._show_var_hover_popup)
        self._var_hover_global_pos = QPoint()

        # Detected indent width for this document.
        self._detected_indent: int = _DEFAULT_INDENT_WIDTH

        # Completion popup and engine
        self._completion_popup = CompletionPopup(self)
        self._completion_engine = CompletionEngine("javascript")
        self._completion_popup.item_selected.connect(self._accept_completion)
        self._completion_popup.dismissed.connect(self._on_completion_dismissed)
        self._completion_prefix: str = ""

        # Collapsed-fold badge rectangles for click hit-testing.
        self._fold_badge_rects: dict[int, QRect] = {}

        # Cache for the active (innermost) fold region at the cursor.
        self._active_fold_start: int = -1

        # Breakpoint and debug state.
        self._breakpoints: set[int] = set()
        self._debug_line: int | None = None
        self._show_breakpoint_gutter = False

        if read_only:
            self.setReadOnly(True)

        # Highlighter
        self._highlighter = PygmentsHighlighter(self.document(), read_only=read_only)

        # Gutter widgets
        self._line_number_area = _LineNumberArea(self)
        self._fold_gutter_area = _FoldGutterArea(self)
        self._bp_gutter_area = _BreakpointGutterArea(self)
        self._bp_gutter_area.setVisible(False)

        # Minimap (right-side viewport overview)
        self._minimap = _MinimapArea(self)
        self._minimap.setVisible(False)
        self._show_minimap = False

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

        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.setInterval(_CURSOR_DEBOUNCE_MS)
        self._cursor_timer.timeout.connect(self._on_cursor_idle)

        # Connect signals
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutters)
        self.cursorPositionChanged.connect(self._cursor_timer.start)
        self.cursorPositionChanged.connect(self._emit_cursor_position)

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
        self._completion_engine.set_language(lang)
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

    def set_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Update the variable resolution map and rehighlight."""
        self._variable_map = variables
        self._highlighter.set_variable_map(variables)
        self._highlighter.rehighlight()
        self._completion_engine.set_variable_map(variables)

    # -- Breakpoints & debug -------------------------------------------

    def set_breakpoint_gutter_visible(self, visible: bool) -> None:
        """Show or hide the breakpoint gutter column."""
        self._show_breakpoint_gutter = visible
        self._bp_gutter_area.setVisible(visible)
        self._update_gutter_width()

    def set_minimap_visible(self, visible: bool) -> None:
        """Show or hide the right-side minimap."""
        self._show_minimap = visible
        self._minimap.setVisible(visible)
        self._update_gutter_width()

    def toggle_breakpoint(self, line: int) -> bool:
        """Toggle a breakpoint on *line* (0-based). Return True if now set."""
        if line in self._breakpoints:
            self._breakpoints.discard(line)
            result = False
        else:
            self._breakpoints.add(line)
            result = True
        self._bp_gutter_area.update()
        self.breakpoints_changed.emit()
        return result

    @property
    def breakpoints(self) -> set[int]:
        """Return a copy of the current breakpoint set."""
        return set(self._breakpoints)

    def set_debug_line(self, line: int | None) -> None:
        """Set the highlighted debug line (0-based), or None to clear."""
        self._debug_line = line
        self._bp_gutter_area.update()
        self.viewport().update()

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

    def set_diff_selections(self, selections: list[QTextEdit.ExtraSelection]) -> None:
        """Store diff highlight selections and refresh extra selections."""
        self._diff_selections = selections
        self._refresh_extra_selections()

    def set_diff_line_colors(self, line_colors: dict[int, QColor]) -> None:
        """Set per-line gutter stripe colours for diff highlighting."""
        self._diff_line_colors = line_colors
        self._line_number_area.update()

    def set_diff_fold_ranges(self, ranges: list[tuple[int, int]]) -> None:
        """Set foldable unchanged-region ranges for diff mode."""
        self._diff_fold_ranges = ranges
        self._collapsed_diff_folds = set(range(len(ranges)))

    def toggle_diff_fold(self, idx: int, *, emit: bool = True) -> None:
        """Toggle a diff fold region open/closed."""
        if idx < 0 or idx >= len(self._diff_fold_ranges):
            return
        if idx in self._collapsed_diff_folds:
            self._collapsed_diff_folds.discard(idx)
        else:
            self._collapsed_diff_folds.add(idx)
        if emit:
            self.diff_fold_toggled.emit(idx)

    # -- Rebuild on theme change ----------------------------------------

    def rebuild_highlight_formats(self) -> None:
        """Rebuild syntax colours from the current theme palette."""
        self._highlighter.rebuild_formats()

    # -- Cursor-idle handler (debounced) --------------------------------

    def _on_cursor_idle(self) -> None:
        """Handle bracket matching and active-guide update after cursor settles."""
        self._highlight_matching_bracket()
        self._update_active_fold()

    def _emit_cursor_position(self) -> None:
        """Emit the cursor_position_changed signal with 1-based line and column."""
        cursor = self.textCursor()
        self.cursor_position_changed.emit(
            cursor.blockNumber() + 1,
            cursor.positionInBlock() + 1,
        )

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

    # -- Block indent / outdent -----------------------------------------

    @staticmethod
    def _indent_selection(cursor: QTextCursor, indent_width: int) -> None:
        """Prepend *indent_width* spaces to every line touched by *cursor*."""
        indent = " " * indent_width
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
            cursor.setPosition(blk.position())
            cursor.insertText(indent)
            blk = blk.next()

        cursor.endEditBlock()

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

        new_start = cursor.document().findBlockByNumber(first_block).position()
        end_block = cursor.document().findBlockByNumber(last_block)
        new_end = end_block.position() + len(end_block.text())
        cursor.setPosition(new_start)
        cursor.setPosition(new_end, QTextCursor.MoveMode.KeepAnchor)

    # -- Auto-close brackets --------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle Tab-to-spaces, auto-closing brackets, and completions."""
        if self._read_only:
            super().keyPressEvent(event)
            return

        # -- Completion popup navigation (when active) --
        if self._completion_popup.is_active():
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                self._completion_popup.accept_current()
                return
            if key == Qt.Key.Key_Escape:
                self._completion_popup.dismiss()
                return
            if key == Qt.Key.Key_Down:
                self._completion_popup.select_next()
                return
            if key == Qt.Key.Key_Up:
                self._completion_popup.select_previous()
                return

        # Ctrl+Space — manual trigger
        if (
            event.key() == Qt.Key.Key_Space
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self._trigger_completion()
            return

        iw = self._detected_indent

        # Tab — block indent or insert spaces
        if event.key() == Qt.Key.Key_Tab and not event.modifiers():
            cursor = self.textCursor()
            if cursor.hasSelection():
                self._indent_selection(cursor, iw)
            else:
                cursor.insertText(" " * iw)
            return

        # Shift+Tab — block outdent
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

            block_text = cursor.block().text()
            pos_in_block = cursor.positionInBlock()
            if text == closing and pos_in_block < len(block_text):
                next_char = block_text[pos_in_block]
                if next_char == closing:
                    cursor.movePosition(
                        QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor
                    )
                    self.setTextCursor(cursor)
                    return

            if cursor.hasSelection():
                selected = cursor.selectedText()
                cursor.insertText(text + selected + closing)
            else:
                cursor.insertText(text + closing)
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor)
                self.setTextCursor(cursor)
            return

        # Skip over closing bracket
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

        # -- Post-insert completion triggers --
        if text == ".":
            self._trigger_completion()
        elif text == "{":
            line_text = self.textCursor().block().text()
            col = self.textCursor().positionInBlock()
            if col >= 2 and line_text[col - 2 : col] == "{{":
                self._trigger_completion()
        elif self._completion_popup.is_active():
            self._filter_completion()

    # -- Tooltip for errors ---------------------------------------------

    def _var_at_cursor(self, pos: QPoint) -> str | None:
        """Return the variable name at pixel *pos*, or ``None``."""
        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        block_text = block.text()
        if "{{" not in block_text:
            return None
        pos_in_block = cursor.positionInBlock()
        for match in _VAR_RE.finditer(block_text):
            if match.start() <= pos_in_block <= match.end():
                return match.group(1)
        return None

    def event(self, event: QEvent) -> bool:
        """Show tooltip for error messages on hover; suppress for variables."""
        if event.type() == QEvent.Type.ToolTip:
            help_event = cast("QHelpEvent", event)
            cursor = self.cursorForPosition(help_event.pos())
            line = cursor.blockNumber() + 1

            for error in self._errors:
                if error.line == line:
                    QToolTip.showText(
                        help_event.globalPos(),
                        f"Line {error.line}: {error.message}",
                        self,
                    )
                    return True

            QToolTip.hideText()
            return True
        return super().event(event)

    # -- Variable hover popup ------------------------------------------

    def _show_var_hover_popup(self) -> None:
        """Show the variable popup for the currently hovered variable."""
        if self._var_hover_name is None:
            return
        from ui.widgets.variable_popup import VariablePopup

        detail = self._variable_map.get(self._var_hover_name)
        VariablePopup.show_variable(self._var_hover_name, detail, self._var_hover_global_pos, self)

    # -- Fold badge / completion / mouse — see _CompletionMixin ---------
