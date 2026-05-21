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

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, cast

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QHelpEvent,
    QKeyEvent,
    QKeySequence,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QToolTip, QWidget

if TYPE_CHECKING:
    from services.environment_service import VariableDetail
    from ui.styling.theme import ThemePalette
    from ui.widgets.code_editor.lsp_integration import EditorLspAdapter

from ui.widgets.code_editor.completion.engine import CompletionEngine
from ui.widgets.code_editor.completion.mixin import _CompletionMixin
from ui.widgets.code_editor.editor_ident import _IdentMixin
from ui.widgets.code_editor.editor_keyboard import _KeyboardMixin
from ui.widgets.code_editor.editor_breakpoints import (
    _BP_HOVER_TOOLTIP_DELAY_MS,
    _BreakpointMixin,
)
from ui.widgets.code_editor.editor_formatting import _FormattingMixin
from ui.widgets.code_editor.editor_language import _LanguageMixin
from ui.widgets.code_editor.editor_snippets import _SnippetMixin
from ui.widgets.code_editor.editor_test_gutter import _TestGutterMixin
from ui.widgets.code_editor.editor_variables import _VariableMixin
from ui.widgets.code_editor.folding import _FoldingMixin
from ui.widgets.code_editor.gutter import (
    _CURSOR_DEBOUNCE_MS,
    _DEFAULT_INDENT_WIDTH,
    _FOLD_DEBOUNCE_MS,
    _VALIDATE_DEBOUNCE_MS,
    SyntaxError_,
    _BreakpointGutterArea,
    _FoldGutterArea,
    _LineNumberArea,
    _MinimapArea,
    _TestGutterArea,
)
from ui.widgets.code_editor.highlighter import PygmentsHighlighter
from ui.widgets.code_editor.painting import _PaintingMixin
from ui.widgets.code_editor import editor_lsp_glue as _lsp


class CodeEditorWidget(
    _FormattingMixin,
    _SnippetMixin,
    _TestGutterMixin,
    _VariableMixin,
    _LanguageMixin,
    _CompletionMixin,
    _KeyboardMixin,
    _IdentMixin,
    _PaintingMixin,
    _BreakpointMixin,
    _FoldingMixin,
    QPlainTextEdit,
):
    """Rich code editor with syntax highlighting, folding, and validation.

    Class-level :meth:`set_open_local_script_handler` is wired once from
    :class:`ui.main_window.window.MainWindow` so Ctrl+click on ``local:`` imports
    can open the target script tab.

    Parameters:
        read_only: If ``True``, the editor is not editable and uses
            full-document caching for perfect highlighting accuracy.
        parent: Optional parent widget.

    Signals:
        validation_changed: Emitted when validation errors change,
            carrying the list of ``SyntaxError_`` items.
        lsp_diagnostics_changed: Emitted when the language server publishes
            diagnostics for this editor's virtual document (list of
            :class:`services.lsp.client.Diagnostic`). Empty when LSP detaches
            or the buffer is swapped.
    """

    validation_changed = Signal(list)
    lsp_diagnostics_changed = Signal(object)
    breakpoints_changed = Signal()
    diff_fold_toggled = Signal(int)
    cursor_position_changed = Signal(int, int)  # (1-based line, 1-based col)
    run_single_test_requested = Signal(str)
    debug_single_test_requested = Signal(str)

    _open_local_script_handler: ClassVar[Callable[[int], None] | None] = None

    @classmethod
    def set_open_local_script_handler(cls, handler: Callable[[int], None] | None) -> None:
        """Register callback to open a local script tab by database id."""
        cls._open_local_script_handler = handler

    @classmethod
    def _invoke_open_local_script(cls, script_id: int) -> bool:
        """Open *script_id* via the registered handler; return whether handled."""
        handler = cls._open_local_script_handler
        if handler is None:
            return False
        handler(script_id)
        return True

    def __init__(self, *, read_only: bool = False, parent: QWidget | None = None) -> None:
        """Initialise the code editor with gutter, highlighter, and timers."""
        super().__init__(parent)
        self.setObjectName("codeEditor")

        self._read_only = read_only
        self._snippet_script_type: str | None = None
        self._snippet_collection_id: int | None = None
        self._snippet_local_script_id: int | None = None
        # Light “paper” reader chrome in dark-themed modals (inherited script chain, etc.)
        self._inherited_read_preview: bool = False
        self._language = "text"
        self._script_module_format = "esm"
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

        # Optional language-server adapter for script modes (see :meth:`attach_lsp`).
        self._lsp_adapter: EditorLspAdapter | None = None

        # Completion engine (kept per-editor — holds language + variable map).
        self._completion_engine = CompletionEngine("javascript")
        self._completion_prefix: str = ""
        self._symbol_hover_path: str | None = None
        self._symbol_hover_global_pos = QPoint()
        self._symbol_hover_timer = QTimer(self)
        self._symbol_hover_timer.setSingleShot(True)
        self._symbol_hover_timer.timeout.connect(self._show_symbol_doc_popup)
        self._lsp_def_hover_timer = QTimer(self)
        self._lsp_def_hover_timer.setSingleShot(True)
        self._lsp_def_hover_timer.timeout.connect(self._on_lsp_def_hover_timeout)
        self._lsp_def_hover_pending = False

        # Collapsed-fold badge rectangles for click hit-testing.
        self._fold_badge_rects: dict[int, QRect] = {}

        # Cache for the active (innermost) fold region at the cursor.
        self._active_fold_start: int = -1

        # Breakpoint and debug state.
        self._breakpoints: dict[int, str | None] = {}
        self._top_level_lines: set[int] = set()
        self._debug_line: int | None = None
        self._debug_locals: dict[str, Any] = {}
        self._debug_root_values: dict[str, Any] = {}
        self._show_breakpoint_gutter = False
        self._breakpoint_hover_line: int | None = None
        # Per-test gutter (``pm.test`` line markers) — enabled by script hosts.
        self._test_gutter_enabled = False
        self._pm_tests: list[dict[str, Any]] = []
        self._inline_log_annotations: dict[int, str] = {}

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

        self._format_in_progress = False
        self._skip_format_on_idle = False
        self._format_on_idle_timer = QTimer(self)
        self._format_on_idle_timer.setSingleShot(True)
        self._format_on_idle_timer.setInterval(500)
        self._format_on_idle_timer.timeout.connect(self._on_format_on_idle_timeout)

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
            self.document().contentsChanged.connect(self._schedule_format_on_idle)

        self._install_layout_independent_shortcuts()
        if not read_only:
            self._install_format_shortcuts()

        self._update_gutter_width()

    def _install_layout_independent_shortcuts(self) -> None:
        """Register Ctrl+Q / Ctrl+P / Ctrl+/ via :class:`QShortcut`.

        ``QKeyEvent.key()`` follows the active keyboard layout, so a Hebrew
        layout maps physical ``Q`` to ``Key_Slash`` and pressing Ctrl+Q
        toggles the line comment instead of opening the quick-doc popup.
        ``QShortcut`` matches against the portable ``Ctrl+Q`` sequence
        regardless of layout.
        """
        ctx = Qt.ShortcutContext.WidgetShortcut
        quick_doc_sc = QShortcut(QKeySequence("Ctrl+Q"), self)
        quick_doc_sc.setContext(ctx)
        quick_doc_sc.activated.connect(self._activate_quick_doc)

        param_hint_sc = QShortcut(QKeySequence("Ctrl+P"), self)
        param_hint_sc.setContext(ctx)
        param_hint_sc.activated.connect(self.trigger_parameter_hint)

        comment_sc = QShortcut(QKeySequence("Ctrl+/"), self)
        comment_sc.setContext(ctx)
        comment_sc.activated.connect(self._activate_line_comment_toggle)

    def _activate_quick_doc(self) -> None:
        """Show the quick-doc popup for the symbol at the text cursor."""
        hit = self._ident_at_text_cursor()
        if hit is None:
            return
        path, _start, _end = hit
        adapter = getattr(self, "_lsp_adapter", None)
        if adapter is not None:
            future = adapter.request_hover()
            if future is not None:
                future.add_done_callback(
                    lambda f, _path=path: _lsp.on_lsp_hover_response(self, f, _path)
                )
                return
        sym = self._completion_engine.resolve_symbol(path, self.toPlainText())
        if sym is None:
            return
        cr = self.cursorRect()
        gp = self.mapToGlobal(cr.bottomLeft())
        self._symbol_hover_global_pos = gp
        self._symbol_doc_popup.show_for(gp, sym)

    def _activate_line_comment_toggle(self) -> None:
        """Toggle line comment unless the editor is read-only."""
        if self._read_only:
            return
        self._toggle_line_comment()

    def _should_skip_script_validation(self) -> bool:
        """Skip ``ScriptLinter`` only after the LSP handshake completes."""
        return _lsp.should_skip_script_validation(self)

    def _on_lsp_ready(self) -> None:
        """Adapter hook when the language server finishes initialising."""
        _lsp.on_lsp_ready(self)

    def attach_lsp(self, language: str) -> None:
        """Attach to the shared language server for *language* (script modes only)."""
        _lsp.attach_lsp(self, language)

    def detach_lsp(self) -> None:
        """Disconnect from the language server and restore legacy validation."""
        _lsp.detach_lsp(self)

    def notify_lsp_diagnostics(self, diags: list[Any]) -> None:
        """Emit :attr:`lsp_diagnostics_changed` for UI surfaces (e.g. Problems tab)."""
        _lsp.notify_lsp_diagnostics(self, diags)

    def trigger_parameter_hint(self) -> None:
        """Show parameter-info for the call surrounding the cursor (Ctrl+P)."""
        _lsp.trigger_parameter_hint(self)

    def set_minimap_visible(self, visible: bool) -> None:
        """Show or hide the right-side minimap."""
        self._show_minimap = visible
        self._minimap.setVisible(visible)
        self._update_gutter_width()

    def contextMenuEvent(self, event: Any) -> None:
        """Standard context menu plus format actions and optional snippet capture."""
        menu = self.createStandardContextMenu()
        self._add_format_menu_actions(menu)
        self._add_snippet_menu_action(menu)
        menu.exec(event.globalPos())

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

    def set_inline_log_annotations(self, annotations: dict[int, str]) -> None:
        """Set faint trailing text for inline ``console.log`` / ``print`` output.

        Keys are 0-based line numbers; values are display strings (already
        elided in the paint pass when wider than the cap).
        """
        self._inline_log_annotations = dict(annotations)
        self.viewport().update()

    def clear_inline_log_annotations(self) -> None:
        """Remove inline console annotations (e.g. on edit or new run)."""
        if not self._inline_log_annotations:
            return
        self._inline_log_annotations = {}
        self.viewport().update()

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

    def event(self, event: QEvent) -> bool:
        """Show tooltip for error messages on hover; suppress for variables."""
        if event.type() == QEvent.Type.ShortcutOverride:
            from ui.widgets.code_editor.editor_keyboard import _is_quick_doc_shortcut

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

    # -- Fold badge / completion / mouse — see _CompletionMixin ---------
