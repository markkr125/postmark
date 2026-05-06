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
import re
import sys
import xml.dom.minidom
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFocusEvent,
    QFont,
    QHelpEvent,
    QKeyEvent,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QPlainTextEdit,
    QTextEdit,
    QToolTip,
    QWidget,
)

if TYPE_CHECKING:
    from services.environment_service import VariableDetail
    from ui.styling.theme import ThemePalette

from ui.widgets.code_editor.completion.engine import CompletionEngine
from ui.widgets.code_editor.completion.mixin import _CompletionMixin
from ui.widgets.code_editor.completion.parameter_hint import ParameterHintPopup
from ui.widgets.code_editor.completion.popup import CompletionPopup
from ui.widgets.code_editor.completion.symbol_doc_popup import SymbolDocPopup
from ui.widgets.code_editor.debug_hover_popup import DebugValuePopup
from ui.widgets.code_editor.folding import _FoldingMixin
from ui.widgets.code_editor.gutter import (
    _AUTO_CLOSE_PAIRS,
    _CLOSE_TO_OPEN,
    _CURSOR_DEBOUNCE_MS,
    _DEFAULT_INDENT_WIDTH,
    _FOLD_DEBOUNCE_MS,
    _TEST_GUTTER_WIDTH,
    _VALIDATE_DEBOUNCE_MS,
    _VAR_RE,
    SyntaxError_,
    _BreakpointGutterArea,
    _FoldGutterArea,
    _LineNumberArea,
    _MinimapArea,
    _TestGutterArea,
)
from ui.widgets.code_editor.highlighter import PygmentsHighlighter
from ui.widgets.code_editor.painting import _PaintingMixin

# CDP scope rows often use the RemoteObject description alone (``Object``);
# :meth:`set_debug_locals` may also carry richer ``root_values`` for ``pm`` / ``console``.
_DEBUG_HOVER_PLACEHOLDER_OBJECT: frozenset[str] = frozenset({"Object", "Console", "[object]"})
_BP_HOVER_TOOLTIP_DELAY_MS = 1000
_BP_HOVER_TOOLTIP_TEXT = "Click to add breakpoint"


def _is_quick_doc_shortcut(event: QKeyEvent) -> bool:
    """Return True for Ctrl+Q (do not bind macOS Cmd+Q — that is OS quit)."""
    if event.key() != Qt.Key.Key_Q:
        return False
    chord = (
        Qt.KeyboardModifier.ShiftModifier
        | Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.MetaModifier
    )
    masked = event.modifiers() & chord
    return masked == Qt.KeyboardModifier.ControlModifier


def _is_parameter_hint_shortcut(event: QKeyEvent) -> bool:
    """Return True for Ctrl+P (Cmd+P on macOS), ignoring benign modifier bits.

    ``QKeyEvent.modifiers()`` may include ``GroupSwitchModifier`` or
    ``KeypadModifier`` alongside ``ControlModifier``; equality against
    ``ControlModifier`` alone then fails and the shortcut is never handled.
    """
    if event.key() != Qt.Key.Key_P:
        return False
    m = event.modifiers()
    if m & Qt.KeyboardModifier.AltModifier:
        return False
    chord = (
        Qt.KeyboardModifier.ShiftModifier
        | Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.MetaModifier
    )
    masked = m & chord
    if sys.platform == "darwin" and masked == Qt.KeyboardModifier.MetaModifier:
        return True
    return masked == Qt.KeyboardModifier.ControlModifier


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
    run_single_test_requested = Signal(str)
    debug_single_test_requested = Signal(str)

    def __init__(self, *, read_only: bool = False, parent: QWidget | None = None) -> None:
        """Initialise the code editor with gutter, highlighter, and timers."""
        super().__init__(parent)
        self.setObjectName("codeEditor")

        self._read_only = read_only
        # Light “paper” reader chrome in dark-themed modals (inherited script chain, etc.)
        self._inherited_read_preview: bool = False
        self._language = "text"
        self._word_wrap = True
        self._errors: list[SyntaxError_] = []
        self._fold_regions: dict[int, int] = {}  # start_line -> end_line
        # Sorted cache for fast viewport-clipped painting.
        self._sorted_folds: list[tuple[int, int, int]] = []
        self._collapsed_folds: set[int] = set()
        self._search_selections: list[QTextEdit.ExtraSelection] = []
        self._diff_selections: list[QTextEdit.ExtraSelection] = []
        self._symbol_link_selections: list[QTextEdit.ExtraSelection] = []
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
        self._parameter_hint_popup = ParameterHintPopup(self)
        self._symbol_doc_popup = SymbolDocPopup(self)
        self._symbol_hover_path: str | None = None
        self._symbol_hover_global_pos = QPoint()
        self._symbol_hover_timer = QTimer(self)
        self._symbol_hover_timer.setSingleShot(True)
        self._symbol_hover_timer.timeout.connect(self._show_symbol_doc_popup)

        # Collapsed-fold badge rectangles for click hit-testing.
        self._fold_badge_rects: dict[int, QRect] = {}

        # Cache for the active (innermost) fold region at the cursor.
        self._active_fold_start: int = -1

        # Breakpoint and debug state.
        self._breakpoints: set[int] = set()
        self._top_level_lines: set[int] = set()
        self._debug_line: int | None = None
        self._debug_locals: dict[str, Any] = {}
        self._debug_root_values: dict[str, Any] = {}
        self._debug_popup = DebugValuePopup(self)
        self._show_breakpoint_gutter = False
        self._breakpoint_hover_line: int | None = None
        # Per-test gutter (``pm.test`` line markers) — enabled by script hosts.
        self._test_gutter_enabled = False
        self._pm_tests: list[dict[str, Any]] = []

        if read_only:
            self.setReadOnly(True)

        # Highlighter
        self._highlighter = PygmentsHighlighter(self.document(), read_only=read_only)

        # Gutter widgets
        self._line_number_area = _LineNumberArea(self)
        self._fold_gutter_area = _FoldGutterArea(self)
        self._bp_gutter_area = _BreakpointGutterArea(self)
        self._bp_gutter_area.setVisible(False)
        self._test_gutter_area = _TestGutterArea(self)
        self._test_gutter_area.setVisible(False)

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

        self._bp_hover_tip_timer = QTimer(self)
        self._bp_hover_tip_timer.setSingleShot(True)
        self._bp_hover_tip_timer.setInterval(_BP_HOVER_TOOLTIP_DELAY_MS)
        self._bp_hover_tip_timer.timeout.connect(self._show_bp_hover_tooltip_if_valid)
        self._bp_hover_tip_target_line: int | None = None

        # Connect signals
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutters)
        self.cursorPositionChanged.connect(self._cursor_timer.start)
        self.cursorPositionChanged.connect(self._emit_cursor_position)
        self.cursorPositionChanged.connect(self._on_cursor_moved_parameter_hint)

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

    def trigger_parameter_hint(self) -> None:
        """Show parameter-info for the call surrounding the cursor (used by Ctrl+P shortcuts)."""
        self._try_show_parameter_hint()

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
        if not visible:
            self._set_breakpoint_hover_line(None)
        self._update_gutter_width()

    def set_test_gutter_enabled(self, enabled: bool) -> None:
        """Show or hide the per-``pm.test`` gutter column."""
        self._test_gutter_enabled = enabled
        self._test_gutter_area.setVisible(enabled)
        self._update_gutter_width()

    def test_gutter_width(self) -> int:
        """Return width of the per-test gutter in pixels (0 when disabled)."""
        return _TEST_GUTTER_WIDTH if self._test_gutter_enabled else 0

    def set_pm_tests(self, tests: list[dict[str, Any]]) -> None:
        """Set ``pm.test`` call sites as ``{name, line}`` (1-based lines)."""
        self._pm_tests = list(tests)
        self._test_gutter_area.update()

    def _schedule_clear_breakpoint_hover_if_left_gutters(self) -> None:
        """After leaving a gutter, clear hover preview once the pointer settles."""
        QTimer.singleShot(0, self._deferred_clear_breakpoint_hover_if_left_gutters)

    def _deferred_clear_breakpoint_hover_if_left_gutters(self) -> None:
        """Clear breakpoint hover if the cursor is no longer over any gutter column."""
        w = QApplication.widgetAt(QCursor.pos())
        gutters = (
            self._line_number_area,
            self._bp_gutter_area,
            self._test_gutter_area,
            self._fold_gutter_area,
        )
        if w is None:
            self._set_breakpoint_hover_line(None)
            return
        for g in gutters:
            if w is g or g.isAncestorOf(w):
                return
        self._set_breakpoint_hover_line(None)

    def _breakpoint_add_preview_active(self) -> bool:
        """True when the hollow breakpoint hover ring is shown for the hover line."""
        line = self._breakpoint_hover_line
        if line is None or not self._show_breakpoint_gutter or self._read_only:
            return False
        if line in self._breakpoints:
            return False
        return self._debug_line is None or line != self._debug_line

    def _schedule_breakpoint_hover_tooltip(self) -> None:
        """After 1s on a row that can add a breakpoint, show a one-shot tooltip."""
        self._bp_hover_tip_timer.stop()
        QToolTip.hideText()
        if not self._breakpoint_add_preview_active():
            self._bp_hover_tip_target_line = None
            return
        self._bp_hover_tip_target_line = self._breakpoint_hover_line
        self._bp_hover_tip_timer.start()

    def _show_bp_hover_tooltip_if_valid(self) -> None:
        """Show gutter tooltip if the pointer is still over a gutter and preview applies."""
        target = self._bp_hover_tip_target_line
        if target is None or self._breakpoint_hover_line != target:
            return
        if not self._breakpoint_add_preview_active():
            return
        w = QApplication.widgetAt(QCursor.pos())
        gutters = (
            self._line_number_area,
            self._bp_gutter_area,
            self._test_gutter_area,
            self._fold_gutter_area,
        )
        if w is None or not any(w is g or g.isAncestorOf(w) for g in gutters):
            return
        QToolTip.showText(QCursor.pos(), _BP_HOVER_TOOLTIP_TEXT, self)

    def _line_has_pm_test_at_gutter_y(self, y: float) -> bool:
        """Return True if *y* (test-gutter coords) lies on a line with a ``pm.test`` marker."""
        if not self._test_gutter_enabled or self.test_gutter_width() <= 0:
            return False
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        while block.isValid():
            bottom = top + self.blockBoundingRect(block).height()
            if top <= y < bottom:
                line_1 = block.blockNumber() + 1
                return any(int(t.get("line", 0)) == line_1 for t in self._pm_tests)
            block = block.next()
            top = bottom
        return False

    def test_gutter_clicked(self, y: float, global_pos: QPoint) -> None:
        """Handle click in the per-test gutter at viewport y *y* (widget coords)."""
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        while block.isValid():
            bottom = top + self.blockBoundingRect(block).height()
            if top <= y < bottom:
                line_1 = block.blockNumber() + 1
                for t in self._pm_tests:
                    if int(t.get("line", 0)) == line_1:
                        self._show_test_menu(global_pos, str(t.get("name", "")))
                        return
                return
            block = block.next()
            top = bottom

    def _show_test_menu(self, global_pos: QPoint, name: str) -> None:
        """Show Run/Debug actions for a single named ``pm.test``."""
        menu = QMenu(self)
        run_act = menu.addAction(f"Run test '{name}'")
        debug_act = menu.addAction(f"Debug test '{name}'")
        chosen = menu.exec(global_pos)
        if chosen is run_act:
            self.run_single_test_requested.emit(name)
        elif chosen is debug_act:
            self.debug_single_test_requested.emit(name)

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
        self._refresh_extra_selections()
        self.breakpoints_changed.emit()
        self._schedule_breakpoint_hover_tooltip()
        return result

    @property
    def breakpoints(self) -> set[int]:
        """Return a copy of the current breakpoint set."""
        return set(self._breakpoints)

    def set_top_level_lines(self, lines: set[int]) -> None:
        """Set lines (0-based) where the step-debugger can pause; empty means style all breakpoints as reachable."""
        self._top_level_lines = set(lines)
        self._bp_gutter_area.update()

    def set_debug_line(self, line: int | None) -> None:
        """Set the highlighted debug line (0-based), or None to clear."""
        self._debug_line = line
        self._bp_gutter_area.update()
        self.viewport().update()
        self._refresh_extra_selections()
        self._schedule_breakpoint_hover_tooltip()

    def set_debug_locals(
        self,
        locals_dict: dict[str, Any],
        *,
        root_values: dict[str, Any] | None = None,
    ) -> None:
        """Store flat debug names and optional whole-object roots (e.g. ``pm``).

        When ``globals``/``pm`` snapshots are merged into a flat map, ``pm`` is
        not a key in *locals_dict*; *root_values* keeps the full ``pm`` object
        for identifier hover. Passing only an empty *locals_dict* clears both
        maps. When *root_values* is omitted and *locals_dict* is non-empty,
        existing roots are left unchanged (callers should pass roots whenever
        they update locals during a pause).
        """
        self._debug_locals = dict(locals_dict)
        if root_values is not None:
            self._debug_root_values = dict(root_values)
        elif not locals_dict:
            self._debug_root_values = {}
        if not self._debug_locals and not self._debug_root_values:
            self._debug_popup.hide()

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

    def set_symbol_link_range(self, start: int | None, end: int | None) -> None:
        """Underline the document range ``[start, end)`` as a Ctrl+hover link.

        Pass ``None`` for either bound to clear the underline.
        """
        if start is None or end is None or end <= start:
            if not self._symbol_link_selections:
                return
            self._symbol_link_selections = []
            self._refresh_extra_selections()
            return
        sel = QTextEdit.ExtraSelection()
        cur = QTextCursor(self.document())
        cur.setPosition(start)
        cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setFontUnderline(True)
        sel.cursor = cur
        sel.format = fmt
        self._symbol_link_selections = [sel]
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

    def _editor_palette(self) -> ThemePalette:
        """Colours for editor chrome: light paper when :meth:`set_inherited_read_preview` is on."""
        if getattr(self, "_inherited_read_preview", False):
            from ui.styling.theme import LIGHT_PALETTE

            return LIGHT_PALETTE
        from ui.styling.theme import current_palette

        return current_palette()

    def set_inherited_read_preview(self, enabled: bool) -> None:
        """Use a light, paper-style surface and syntax colours (for read-only modals in a dark app)."""
        self._inherited_read_preview = bool(enabled and self._read_only)
        self.setObjectName(
            "codeEditorInheritedRead" if self._inherited_read_preview else "codeEditor"
        )
        if self._inherited_read_preview:
            from ui.styling.theme import LIGHT_PALETTE

            self._highlighter.set_token_palette(LIGHT_PALETTE)
        else:
            self._highlighter.set_token_palette(None)
        self._line_number_area.update()
        self._fold_gutter_area.update()
        self._bp_gutter_area.update()
        self._test_gutter_area.update()
        self.viewport().update()

    # -- Rebuild on theme change ----------------------------------------

    def rebuild_highlight_formats(self) -> None:
        """Rebuild syntax colours from the current theme palette."""
        if getattr(self, "_inherited_read_preview", False):
            from ui.styling.theme import LIGHT_PALETTE

            self._highlighter.set_token_palette(LIGHT_PALETTE)
        else:
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

    # -- Line comment ---------------------------------------------------

    def _line_comment_token(self) -> str:
        """Return the line-comment marker for the current language."""
        lang = self._language
        if lang in ("python",):
            return "#"
        return "//"

    def _toggle_line_comment(self) -> None:
        """Toggle line-comment marker on the selected lines (or current line).

        Comments out every selected line if any line is uncommented;
        otherwise removes the marker from each. Indent of the marker
        matches the smallest leading-whitespace of the affected lines.
        """
        token = self._line_comment_token()
        prefix = token + " "
        cursor = self.textCursor()
        doc = self.document()

        if cursor.hasSelection():
            start = min(cursor.selectionStart(), cursor.selectionEnd())
            end = max(cursor.selectionStart(), cursor.selectionEnd())
        else:
            start = cursor.position()
            end = cursor.position()

        first_block = doc.findBlock(start).blockNumber()
        last_block_blk = doc.findBlock(end)
        # If selection ends right at start of a block, exclude that block.
        if (
            cursor.hasSelection()
            and last_block_blk.position() == end
            and last_block_blk.blockNumber() > first_block
        ):
            last_block = last_block_blk.blockNumber() - 1
        else:
            last_block = last_block_blk.blockNumber()

        # Pass 1: decide add vs remove. Add if any non-blank line lacks the marker.
        any_uncommented = False
        min_indent = None
        for bn in range(first_block, last_block + 1):
            blk = doc.findBlockByNumber(bn)
            text = blk.text()
            stripped = text.lstrip()
            if not stripped:
                continue
            indent = len(text) - len(stripped)
            min_indent = indent if min_indent is None else min(min_indent, indent)
            if not stripped.startswith(token):
                any_uncommented = True
        if min_indent is None:
            min_indent = 0

        cursor.beginEditBlock()
        for bn in range(first_block, last_block + 1):
            blk = doc.findBlockByNumber(bn)
            text = blk.text()
            stripped = text.lstrip()
            if not stripped:
                continue
            block_pos = blk.position()
            indent = len(text) - len(stripped)
            if any_uncommented:
                # Insert marker at the shared indent column.
                col = min(min_indent, indent)
                ins_cursor = QTextCursor(doc)
                ins_cursor.setPosition(block_pos + col)
                ins_cursor.insertText(prefix)
            else:
                # Remove marker (and one optional trailing space) from this line.
                idx = text.find(token)
                if idx == -1:
                    continue
                rm_cursor = QTextCursor(doc)
                rm_cursor.setPosition(block_pos + idx)
                rm_len = len(token)
                if text[idx + rm_len : idx + rm_len + 1] == " ":
                    rm_len += 1
                rm_cursor.setPosition(block_pos + idx + rm_len, QTextCursor.MoveMode.KeepAnchor)
                rm_cursor.removeSelectedText()
        cursor.endEditBlock()

    # -- Auto-close brackets --------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle Tab-to-spaces, auto-closing brackets, and completions."""
        if event.key() == Qt.Key.Key_Escape:
            if self._completion_popup.is_active():
                self._completion_popup.dismiss()
                event.accept()
                return
            if self._parameter_hint_popup.isVisible():
                self._dismiss_parameter_hint()
                event.accept()
                return
            if self._symbol_doc_popup.isVisible():
                self._dismiss_symbol_doc()
                event.accept()
                return
            if self._debug_popup.isVisible():
                self._hide_debug_value_popup()
                event.accept()
                return

        # Ctrl+P / Cmd+P — parameter info (before read-only branch so hints work everywhere)
        if _is_parameter_hint_shortcut(event):
            self.trigger_parameter_hint()
            event.accept()
            return

        # Ctrl+Q — quick documentation for the symbol at the text cursor.
        if _is_quick_doc_shortcut(event):
            hit = self._ident_at_text_cursor()
            if hit is not None:
                path, _start, _end = hit
                sym = self._completion_engine.resolve_symbol(path, self.toPlainText())
                if sym is not None:
                    cr = self.cursorRect()
                    gp = self.mapToGlobal(cr.bottomLeft())
                    self._symbol_hover_global_pos = gp
                    self._symbol_doc_popup.show_for(gp, sym)
            event.accept()
            return

        if self._read_only:
            super().keyPressEvent(event)
            return

        # Ctrl+/ — toggle line comment for the selection or current line.
        if (
            event.key() == Qt.Key.Key_Slash
            and (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            and not (event.modifiers() & Qt.KeyboardModifier.AltModifier)
        ):
            self._toggle_line_comment()
            event.accept()
            return

        # Shift+Enter / Shift+Return — insert a normal newline (paragraph break).
        # Qt's default would insert U+2028 line-separator instead, which round-trips
        # poorly through save/load and some highlighters.
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() == Qt.KeyboardModifier.ShiftModifier
            and not self._completion_popup.is_active()
        ):
            self.textCursor().insertText("\n")
            return

        # -- Completion popup navigation (when active) --
        if self._completion_popup.is_active():
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                self._completion_popup.accept_current()
                return
            if key == Qt.Key.Key_Down:
                self._completion_popup.select_next()
                return
            if key == Qt.Key.Key_Up:
                self._completion_popup.select_previous()
                return

        # Ctrl+Space — manual completion trigger
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
                if text == "(":
                    self._try_show_parameter_hint()
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
        if text == "," and self._parameter_hint_popup.isVisible():
            self._refresh_parameter_hint_from_cursor()
        elif text == ")":
            if (
                self._completion_engine.resolve_call_signature(self._text_before_cursor_document())
                is None
            ):
                self._dismiss_parameter_hint()
            else:
                self._refresh_parameter_hint_from_cursor()
        if text == ".":
            self._trigger_completion()
        elif text == "{":
            line_text = self.textCursor().block().text()
            col = self.textCursor().positionInBlock()
            if col >= 2 and line_text[col - 2 : col] == "{{":
                self._trigger_completion()
        elif self._completion_popup.is_active():
            self._filter_completion()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        """Hide the parameter hint only when focus genuinely leaves our window.

        Showing a ``Qt.Tool`` popup briefly shifts the active window on Linux,
        which would otherwise dismiss the hint immediately.
        """
        reason = event.reason()
        new_active = QApplication.activeWindow()
        same_window = new_active is not None and (
            new_active is self.window()
            or new_active is self._parameter_hint_popup
            or new_active is self._symbol_doc_popup
        )
        transient = reason in (
            Qt.FocusReason.PopupFocusReason,
            Qt.FocusReason.ActiveWindowFocusReason,
        )
        if not (same_window or transient):
            self._dismiss_parameter_hint()
            self._dismiss_symbol_doc()
        super().focusOutEvent(event)

    # -- Tooltip for errors ---------------------------------------------

    def _ident_at_pos(self, pos: QPoint) -> tuple[str, int, int] | None:
        """Return ``(dot_path, start_doc_pos, end_doc_pos)`` for an identifier.

        Resolves the JS/Python identifier under viewport position *pos*,
        walking left over ``.`` joins.  Returns ``None`` when the position is
        not on an identifier or is inside a string literal.
        """
        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        block_text = block.text()
        col = cursor.positionInBlock()
        if col > 0 and col >= len(block_text):
            col = len(block_text) - 1
        if col < 0 or col >= len(block_text):
            return None
        if not (block_text[col].isalnum() or block_text[col] in "_$."):
            return None
        # Walk right to end of identifier run.
        end = col
        while end < len(block_text) and (block_text[end].isalnum() or block_text[end] in "_$"):
            end += 1
        # Walk left over identifier + dot chains.
        start = col
        while start > 0 and (
            block_text[start - 1].isalnum()
            or block_text[start - 1] in "_$"
            or (
                block_text[start - 1] == "."
                and start - 2 >= 0
                and (block_text[start - 2].isalnum() or block_text[start - 2] in "_$")
            )
        ):
            start -= 1
        token = block_text[start:end]
        if not token or token[0].isdigit():
            return None
        # Reject when inside a string literal. Track template-literal
        # interpolation (`${ ... }`) so identifiers inside `${expr}` are
        # treated as code, not string content.
        prefix = block_text[:start]
        state = "code"  # code | sq | dq | tpl | tpl_expr
        expr_depth = 0
        i = 0
        while i < len(prefix):
            ch = prefix[i]
            if state in ("sq", "dq", "tpl") and ch == "\\":
                i += 2
                continue
            if state == "code":
                if ch == "'":
                    state = "sq"
                elif ch == '"':
                    state = "dq"
                elif ch == "`":
                    state = "tpl"
            elif state == "sq":
                if ch == "'":
                    state = "code"
            elif state == "dq":
                if ch == '"':
                    state = "code"
            elif state == "tpl":
                if ch == "`":
                    state = "code"
                elif ch == "$" and i + 1 < len(prefix) and prefix[i + 1] == "{":
                    state = "tpl_expr"
                    expr_depth = 1
                    i += 2
                    continue
            else:  # tpl_expr — JS code inside `${...}`
                if ch == "{":
                    expr_depth += 1
                elif ch == "}":
                    expr_depth -= 1
                    if expr_depth == 0:
                        state = "tpl"
                elif ch in ("'", '"'):
                    end_q = prefix.find(ch, i + 1)
                    if end_q == -1:
                        return None
                    i = end_q + 1
                    continue
            i += 1
        if state in ("sq", "dq", "tpl"):
            return None
        if not re.match(r"[A-Za-z_$][\w$.]*", token):
            return None
        # Segment range = only the identifier segment directly under the cursor,
        # so Ctrl+hover underlines just `set` in `pm.variables.set`.
        seg_start = col
        while seg_start > 0 and (
            block_text[seg_start - 1].isalnum() or block_text[seg_start - 1] in "_$"
        ):
            seg_start -= 1
        return token, block.position() + seg_start, block.position() + end

    def _ident_at_text_cursor(self) -> tuple[str, int, int] | None:
        """Same as :meth:`_ident_at_pos` but driven by the current text cursor."""
        return self._ident_at_pos(self.cursorRect().center())

    def _var_at_cursor(self, pos: QPoint) -> str | None:
        """Return ``{{name}}`` or a debug identifier at *pos*, or ``None``."""
        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        block_text = block.text()
        if "{{" in block_text:
            pos_in_block = cursor.positionInBlock()
            for match in _VAR_RE.finditer(block_text):
                if match.start() <= pos_in_block <= match.end():
                    return match.group(1)
        if self._debug_locals or self._debug_root_values:
            cur = self.cursorForPosition(pos)
            cur.select(QTextCursor.SelectionType.WordUnderCursor)
            word = cur.selectedText()
            if (
                word
                and re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", word)
                and (word in self._debug_locals or word in self._debug_root_values)
            ):
                return word
        return None

    def event(self, event: QEvent) -> bool:
        """Show tooltip for error messages on hover; suppress for variables."""
        if event.type() == QEvent.Type.ShortcutOverride:
            ke = cast("QKeyEvent", event)
            if _is_quick_doc_shortcut(ke):
                event.accept()
                return True
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

    def _debug_hover_resolved_value(self, name: str) -> Any | None:
        """Return the richest value for debug identifier hover."""
        if name in ("pm", "console"):
            local_v = self._debug_locals.get(name)
            root_v = self._debug_root_values.get(name)
            if isinstance(local_v, dict) and local_v:
                return local_v
            if isinstance(local_v, str) and local_v in _DEBUG_HOVER_PLACEHOLDER_OBJECT:
                return root_v if root_v is not None else local_v
            if root_v is not None:
                return root_v
            return local_v
        if name in self._debug_root_values:
            return self._debug_root_values[name]
        return self._debug_locals.get(name)

    def _show_symbol_doc_popup(self) -> None:
        """Resolve the hovered/focused symbol and show the quick-doc popup."""
        if self._symbol_hover_path is None:
            return
        sym = self._completion_engine.resolve_symbol(self._symbol_hover_path, self.toPlainText())
        if sym is None:
            return
        self._symbol_doc_popup.show_for(self._symbol_hover_global_pos, sym)

    def _dismiss_symbol_doc(self) -> None:
        """Hide the symbol-doc popup and stop the hover timer."""
        self._symbol_doc_popup.hide_popup()
        self._symbol_hover_path = None
        self._symbol_hover_timer.stop()

    # -- Variable hover popup ------------------------------------------

    def _show_var_hover_popup(self) -> None:
        """Show the variable popup for the currently hovered variable."""
        if self._var_hover_name is None:
            return
        name = self._var_hover_name
        if name in self._debug_locals or name in self._debug_root_values:
            resolved = self._debug_hover_resolved_value(name)
            if resolved is not None:
                self._show_debug_value_popup(name, resolved)
            return
        from ui.widgets.variable_popup import VariablePopup

        self._debug_popup.hide()
        detail = self._variable_map.get(self._var_hover_name)
        VariablePopup.show_variable(self._var_hover_name, detail, self._var_hover_global_pos, self)

    def _show_debug_value_popup(self, name: str, value: Any) -> None:
        """Show a styled popup for a paused-debug value (tree or text)."""
        self._debug_popup.show_value(name, value, self._var_hover_global_pos)

    def _hide_debug_value_popup(self) -> None:
        """Hide the debug hover popup if visible."""
        self._debug_popup.hide()

    # -- Fold badge / completion / mouse — see _CompletionMixin ---------
