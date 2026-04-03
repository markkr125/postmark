"""Side-by-side diff viewer with folding and navigation."""

from __future__ import annotations

import difflib

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import QLabel, QSplitter, QVBoxLayout, QWidget

from ui.styling.theme import (
    COLOR_DIFF_ADDED_BG,
    COLOR_DIFF_ADDED_GUTTER,
    COLOR_DIFF_REMOVED_BG,
    COLOR_DIFF_REMOVED_GUTTER,
)
from ui.widgets.code_editor import CodeEditorWidget

from .helpers import (
    _add_inline_selections,
    _build_line_selections,
    _line_format,
    compute_fold_ranges,
)
from .toolbar import WS_DO_NOT_IGNORE, WS_IGNORE_ALL, WS_TRIM

# Editor border stylesheet (no top border — the column header provides it).
_EDITOR_CSS = "QPlainTextEdit { border: none; }"


class _DiffViewer(QWidget):
    """Side-by-side diff viewer with syntax highlighting and inline diffs."""

    diff_count_changed = Signal(int)

    def __init__(
        self,
        *,
        language: str = "javascript",
        parent: QWidget | None = None,
    ) -> None:
        """Build the diff viewer layout."""
        super().__init__(parent)
        self._language = language
        self._old_text = ""
        self._new_text = ""
        self._diff_hunks: list[tuple[int, int]] = []
        self._current_hunk_idx = -1
        self._ws_mode = WS_DO_NOT_IGNORE

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Editor splitter — each side is a column: header + editor
        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        # -- Left column ------------------------------------------------
        left_col = QWidget()
        left_lay = QVBoxLayout(left_col)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        self._left_label = QLabel("Selected Version")
        self._left_label.setObjectName("diffColumnHeader")
        left_lay.addWidget(self._left_label)

        self._left_editor = CodeEditorWidget()
        self._left_editor.setReadOnly(True)
        self._left_editor.set_language(language)
        self._left_editor.setStyleSheet(_EDITOR_CSS)
        left_lay.addWidget(self._left_editor, 1)
        self._splitter.addWidget(left_col)

        # -- Right column -----------------------------------------------
        self._right_col = QWidget()
        right_lay = QVBoxLayout(self._right_col)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        self._right_label = QLabel("Current")
        self._right_label.setObjectName("diffColumnHeader")
        right_lay.addWidget(self._right_label)

        self._right_editor = CodeEditorWidget()
        self._right_editor.setReadOnly(True)
        self._right_editor.set_language(language)
        self._right_editor.setStyleSheet(_EDITOR_CSS)
        right_lay.addWidget(self._right_editor, 1)
        self._splitter.addWidget(self._right_col)

        self._splitter.setHandleWidth(1)
        root.addWidget(self._splitter, 1)

        # Synchronise scrolling (vertical + horizontal)
        left_vbar = self._left_editor.verticalScrollBar()
        right_vbar = self._right_editor.verticalScrollBar()
        left_vbar.valueChanged.connect(right_vbar.setValue)
        right_vbar.valueChanged.connect(left_vbar.setValue)
        left_hbar = self._left_editor.horizontalScrollBar()
        right_hbar = self._right_editor.horizontalScrollBar()
        left_hbar.valueChanged.connect(right_hbar.setValue)
        right_hbar.valueChanged.connect(left_hbar.setValue)

        # Sync diff fold toggles between the two editors
        self._left_editor.diff_fold_toggled.connect(self._on_left_fold_toggled)
        self._right_editor.diff_fold_toggled.connect(self._on_right_fold_toggled)

    def set_version_info(self, text: str) -> None:
        """Update the left column header with version info."""
        self._left_label.setText(text)

    # -- Display --------------------------------------------------------

    def show_single(self, content: str) -> None:
        """Show a single version full-width (no diff highlighting)."""
        self._left_editor.set_diff_selections([])
        self._left_editor.set_diff_line_colors({})
        self._left_editor.set_diff_fold_ranges([])
        self._right_editor.set_diff_selections([])
        self._right_editor.set_diff_line_colors({})
        self._right_editor.set_diff_fold_ranges([])
        self._left_editor.setPlainText(content)
        self._right_editor.setPlainText("")
        self._left_label.setText("Current")
        self._right_label.setText("")
        self._diff_hunks = []
        self._current_hunk_idx = -1
        self.diff_count_changed.emit(0)
        # Hide right column so the left editor spans the full width
        self._right_col.hide()

    def show_diff(self, old_text: str, new_text: str) -> None:
        """Show two versions side-by-side with full diff highlighting."""
        # Ensure both columns are visible
        self._right_col.show()

        self._old_text = old_text
        self._new_text = new_text
        self._left_editor.setPlainText(old_text)
        self._right_editor.setPlainText(new_text)
        self._left_label.setText("Selected Version")
        self._right_label.setText("Current")

        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()

        # Pre-process for whitespace mode (comparison only)
        cmp_old, cmp_new = self._preprocess_ws(old_lines, new_lines)
        sm = difflib.SequenceMatcher(None, cmp_old, cmp_new)
        opcodes = sm.get_opcodes()

        removed_lines: set[int] = set()
        added_lines: set[int] = set()
        replace_pairs: list[tuple[range, range]] = []
        hunks: list[tuple[int, int]] = []

        for tag, i1, i2, j1, j2 in opcodes:
            if tag == "replace":
                removed_lines.update(range(i1, i2))
                added_lines.update(range(j1, j2))
                replace_pairs.append((range(i1, i2), range(j1, j2)))
                hunks.append((i1, j1))
            elif tag == "delete":
                removed_lines.update(range(i1, i2))
                hunks.append((i1, j1))
            elif tag == "insert":
                added_lines.update(range(j1, j2))
                hunks.append((i1, j1))

        self._diff_hunks = hunks
        self._current_hunk_idx = 0 if hunks else -1
        self.diff_count_changed.emit(len(hunks))

        # 1. Full-line background highlights
        removed_fmt = _line_format(COLOR_DIFF_REMOVED_BG)
        added_fmt = _line_format(COLOR_DIFF_ADDED_BG)
        left_sels = _build_line_selections(self._left_editor, removed_lines, removed_fmt)
        right_sels = _build_line_selections(self._right_editor, added_lines, added_fmt)

        # 2. Character-level inline diffs
        _add_inline_selections(
            self._left_editor,
            self._right_editor,
            old_lines,
            new_lines,
            replace_pairs,
            left_sels,
            right_sels,
        )

        self._left_editor.set_diff_selections(left_sels)
        self._right_editor.set_diff_selections(right_sels)

        # 3. Gutter stripes
        removed_color = QColor(COLOR_DIFF_REMOVED_GUTTER)
        added_color = QColor(COLOR_DIFF_ADDED_GUTTER)
        self._left_editor.set_diff_line_colors(
            {ln: removed_color for ln in removed_lines},
        )
        self._right_editor.set_diff_line_colors(
            {ln: added_color for ln in added_lines},
        )

        # 4. Fold unchanged regions
        fold_ranges = compute_fold_ranges(opcodes, len(old_lines), len(new_lines))
        left_folds = [(r[0], r[1]) for r in fold_ranges]
        right_folds = [(r[2], r[3]) for r in fold_ranges]
        self._left_editor.set_diff_fold_ranges(left_folds)
        self._right_editor.set_diff_fold_ranges(right_folds)

    # -- Whitespace mode ------------------------------------------------

    def _preprocess_ws(
        self,
        old_lines: list[str],
        new_lines: list[str],
    ) -> tuple[list[str], list[str]]:
        """Pre-process lines based on the current whitespace mode."""
        if self._ws_mode == WS_TRIM:
            return [line.strip() for line in old_lines], [line.strip() for line in new_lines]
        if self._ws_mode == WS_IGNORE_ALL:
            return (
                [line.replace(" ", "").replace("\t", "") for line in old_lines],
                [line.replace(" ", "").replace("\t", "") for line in new_lines],
            )
        return old_lines, new_lines

    # -- Navigation (public API for toolbar) ----------------------------

    def navigate_prev(self) -> None:
        """Jump to the previous diff hunk (wraps around)."""
        if not self._diff_hunks:
            return
        self._current_hunk_idx = (self._current_hunk_idx - 1) % len(self._diff_hunks)
        self._scroll_to_hunk(self._current_hunk_idx)

    def navigate_next(self) -> None:
        """Jump to the next diff hunk (wraps around)."""
        if not self._diff_hunks:
            return
        self._current_hunk_idx = (self._current_hunk_idx + 1) % len(self._diff_hunks)
        self._scroll_to_hunk(self._current_hunk_idx)

    def _scroll_to_hunk(self, idx: int) -> None:
        """Scroll both editors to centre the given hunk."""
        left_line, right_line = self._diff_hunks[idx]
        self._scroll_editor_to_line(self._left_editor, left_line)
        self._scroll_editor_to_line(self._right_editor, right_line)

    @staticmethod
    def _scroll_editor_to_line(editor: CodeEditorWidget, line: int) -> None:
        """Scroll *editor* to centre the given 0-based line number."""
        block = editor.document().findBlockByNumber(line)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        editor.setTextCursor(cursor)
        editor.centerCursor()

    # -- Copy (public API for toolbar) ----------------------------------

    def copy_content(self) -> None:
        """Copy the left (selected version) editor content to clipboard."""
        from PySide6.QtGui import QGuiApplication

        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._left_editor.toPlainText())

    # -- Whitespace toggle (public API for toolbar) ---------------------

    def set_whitespace_mode(self, mode: str) -> None:
        """Re-run diff with the new whitespace mode."""
        self._ws_mode = mode
        if self._old_text or self._new_text:
            self.show_diff(self._old_text, self._new_text)

    # -- Fold synchronisation -------------------------------------------

    def _on_left_fold_toggled(self, idx: int) -> None:
        """Mirror a fold toggle from the left editor to the right."""
        self._right_editor.toggle_diff_fold(idx, emit=False)

    def _on_right_fold_toggled(self, idx: int) -> None:
        """Mirror a fold toggle from the right editor to the left."""
        self._left_editor.toggle_diff_fold(idx, emit=False)
