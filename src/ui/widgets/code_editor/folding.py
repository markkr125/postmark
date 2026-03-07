"""Code folding engine for the code editor.

Provides fold detection (bracket-based and XML/HTML tag-based), fold
interaction (toggle, fold-all, unfold-all), indent detection, and bracket
matching.  These are implemented as mixin methods on
``CodeEditorWidget`` via ``_FoldingMixin``.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import QTextEdit

from ui.styling.theme import (
    COLOR_EDITOR_BRACKET_MATCH,
    COLOR_EDITOR_ERROR_UNDERLINE,
    COLOR_EDITOR_FOLD_HIGHLIGHT,
)
from ui.widgets.code_editor.gutter import (
    _ALL_BRACKETS,
    _BRACKET_PAIRS,
    _BRACKET_SEARCH_LIMIT,
    _CLOSE_TO_OPEN,
    _FOLDABLE_LANGUAGES,
    _INDENT_SCAN_LINES,
    _VALIDATABLE_LANGUAGES,
    _XML_CLOSE_TAG,
    _XML_OPEN_TAG,
    _XML_SELF_CLOSE,
    SyntaxError_,
    _FoldGutterArea,
    _LineNumberArea,
)

if TYPE_CHECKING:
    from PySide6.QtCore import QTimer, Signal
    from PySide6.QtWidgets import QPlainTextEdit

    _FoldingBase = QPlainTextEdit
else:
    _FoldingBase = object


class _FoldingMixin(_FoldingBase):
    """Mixin providing fold detection, interaction, and bracket matching.

    Must be combined with ``QPlainTextEdit`` (via ``CodeEditorWidget``).
    """

    # -- Attribute stubs (set by CodeEditorWidget.__init__) -------------
    _fold_timer: QTimer
    _language: str
    _validate_timer: QTimer
    _detected_indent: int
    _fold_regions: dict[int, int]
    _sorted_folds: list[tuple[int, int, int]]
    _collapsed_folds: set[int]
    _active_fold_start: int
    _errors: list[SyntaxError_]
    validation_changed: Signal
    _line_number_area: _LineNumberArea
    _fold_gutter_area: _FoldGutterArea
    _search_selections: list[QTextEdit.ExtraSelection]

    if TYPE_CHECKING:

        def _update_gutter_width(self) -> None: ...

        def _update_active_fold(self) -> None: ...

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
            self._detected_indent = 2  # _DEFAULT_INDENT_WIDTH
            return

        # Look at differences between indent levels to find the step.
        levels = sorted(counts)
        diffs: dict[int, int] = {}
        for lv in levels:
            diffs[lv] = diffs.get(lv, 0) + counts[lv]
        for i in range(1, len(levels)):
            d = levels[i] - levels[i - 1]
            if d > 0:
                diffs[d] = diffs.get(d, 0) + min(counts[levels[i]], counts[levels[i - 1]])

        for candidate in (2, 4, 8, 3, 6):
            if diffs.get(candidate, 0) >= 1:
                self._detected_indent = candidate
                return

        self._detected_indent = 2  # _DEFAULT_INDENT_WIDTH

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

    # -- Fold interaction -----------------------------------------------

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

    # -- Bracket matching -----------------------------------------------

    def _highlight_matching_bracket(self) -> None:
        """Highlight the bracket pair at the cursor position."""
        self._refresh_extra_selections()

    def _refresh_extra_selections(self) -> None:
        """Combine bracket-match, error, search, and fold extra selections."""
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

    # -- Extra selections -----------------------------------------------

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

        if old_has_errors or new_has_errors:
            self._highlight_matching_bracket()
            self._line_number_area.update()

    @staticmethod
    def _validate_graphql_braces(text: str) -> list[SyntaxError_]:
        """Check that braces and parentheses are balanced in a GraphQL body.

        This is a best-effort heuristic — a full GraphQL parser would
        require an additional dependency.
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
