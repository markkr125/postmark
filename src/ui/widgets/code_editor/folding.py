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
    normalize_validation_severity,
    _FoldGutterArea,
    _LineNumberArea,
)

if TYPE_CHECKING:
    from PySide6.QtCore import QTimer, Signal
    from PySide6.QtWidgets import QPlainTextEdit

    from ui.styling.theme import ThemePalette

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
    _read_only: bool
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
    _diff_selections: list[QTextEdit.ExtraSelection]

    if TYPE_CHECKING:

        def _update_gutter_width(self) -> None: ...

        def _update_active_fold(self) -> None: ...

        def _editor_palette(self) -> ThemePalette: ...

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
        elif self._language in ("javascript", "typescript"):
            folds = self._detect_js_folds(doc)
        elif self._language == "python":
            folds = self._detect_python_folds(doc)
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

    @staticmethod
    def _detect_js_folds(doc: QTextDocument) -> dict[int, int]:
        """Detect JS/TS fold regions from ``{`` / ``[`` pairs.

        Honors single-quote, double-quote, template-literal strings and
        line/block comments so braces inside strings or comments don't
        skew the brace stack.
        """
        stack: list[int] = []
        folds: dict[int, int] = {}
        block = doc.begin()
        in_block_comment = False
        in_template = False
        while block.isValid():
            text = block.text()
            i = 0
            n = len(text)
            in_str: str | None = None
            escape = False
            while i < n:
                ch = text[i]
                if in_block_comment:
                    if ch == "*" and i + 1 < n and text[i + 1] == "/":
                        in_block_comment = False
                        i += 2
                        continue
                    i += 1
                    continue
                if in_template:
                    if escape:
                        escape = False
                        i += 1
                        continue
                    if ch == "\\":
                        escape = True
                        i += 1
                        continue
                    if ch == "`":
                        in_template = False
                        i += 1
                        continue
                    if ch == "$" and i + 1 < n and text[i + 1] == "{":
                        # Enter expression interpolation as normal code; track its `}`
                        # by pushing a marker on stack scoped to the template.
                        stack.append(block.blockNumber())
                        i += 2
                        continue
                    i += 1
                    continue
                if in_str:
                    if escape:
                        escape = False
                        i += 1
                        continue
                    if ch == "\\":
                        escape = True
                        i += 1
                        continue
                    if ch == in_str:
                        in_str = None
                    i += 1
                    continue
                if ch == "/" and i + 1 < n and text[i + 1] == "/":
                    break  # rest of line is line-comment
                if ch == "/" and i + 1 < n and text[i + 1] == "*":
                    in_block_comment = True
                    i += 2
                    continue
                if ch in ("'", '"'):
                    in_str = ch
                    i += 1
                    continue
                if ch == "`":
                    in_template = True
                    i += 1
                    continue
                if ch in ("{", "["):
                    stack.append(block.blockNumber())
                elif ch in ("}", "]") and stack:
                    start = stack.pop()
                    if block.blockNumber() > start:
                        folds[start] = block.blockNumber()
                i += 1
            block = block.next()
        return folds

    @staticmethod
    def _detect_python_folds(doc: QTextDocument) -> dict[int, int]:
        """Detect Python fold regions by indentation.

        A fold opens on a line whose successor is more deeply indented;
        it closes on the last line still at or above the deeper indent
        level. Blank lines and comment-only lines don't break a region.
        """
        # Collect (block_number, indent) for non-blank, non-comment-only lines.
        rows: list[tuple[int, int]] = []
        block = doc.begin()
        while block.isValid():
            text = block.text()
            stripped = text.lstrip()
            if stripped and not stripped.startswith("#"):
                indent = len(text) - len(stripped)
                rows.append((block.blockNumber(), indent))
            block = block.next()

        folds: dict[int, int] = {}
        for idx, (line_no, indent) in enumerate(rows):
            # Look for a successor with strictly greater indent.
            if idx + 1 >= len(rows):
                continue
            next_indent = rows[idx + 1][1]
            if next_indent <= indent:
                continue
            # Find the last line whose indent is still > parent indent.
            end_line = rows[idx + 1][0]
            for j in range(idx + 1, len(rows)):
                if rows[j][1] > indent:
                    end_line = rows[j][0]
                else:
                    break
            if end_line > line_no:
                folds[line_no] = end_line
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
        """Combine current-line, bracket-match, error, search, and fold extra selections."""
        p = self._editor_palette()
        selections: list[QTextEdit.ExtraSelection] = []

        # 0. Current-line highlight (full-width, subtle background)
        cursor = self.textCursor()
        if not self._read_only:
            line_sel = QTextEdit.ExtraSelection()
            line_fmt = QTextCharFormat()
            line_fmt.setBackground(QColor(p["editor_current_line"]))
            line_fmt.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
            line_sel.format = line_fmt
            line_cur = QTextCursor(cursor)
            line_cur.clearSelection()
            line_sel.cursor = line_cur
            selections.append(line_sel)

        selections.extend(self._breakpoint_selections())

        # 0b. Debug execution line (full-width, above current-line when overlapping)
        dbg_line = getattr(self, "_debug_line", None)
        if dbg_line is not None:
            doc = self.document()
            block = doc.findBlockByNumber(dbg_line)
            if block.isValid():
                dbg_sel = QTextEdit.ExtraSelection()
                dbg_fmt = QTextCharFormat()
                dbg_fmt.setBackground(QColor(p["editor_debug_line"]))
                dbg_fmt.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
                dbg_cur = QTextCursor(block)
                dbg_cur.clearSelection()
                dbg_sel.cursor = dbg_cur
                dbg_sel.format = dbg_fmt
                selections.append(dbg_sel)

        # 1. Bracket matching
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
                fmt.setBackground(QColor(p["editor_bracket_match"]))

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

        # 5. Diff highlight selections
        selections.extend(self._diff_selections)

        # 6. Ctrl+hover symbol link underline
        if hasattr(self, "_symbol_link_selections"):
            selections.extend(self._symbol_link_selections)

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

    def _breakpoint_selections(self) -> list[QTextEdit.ExtraSelection]:
        """Full-width tint for each line with a breakpoint (gutter dot)."""
        selections: list[QTextEdit.ExtraSelection] = []
        bps = getattr(self, "_breakpoints", None)
        if not bps:
            return selections

        p = self._editor_palette()
        doc = self.document()
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(p["editor_breakpoint_line"]))
        fmt.setProperty(QTextCharFormat.Property.FullWidthSelection, True)

        for line in sorted(bps):
            block = doc.findBlockByNumber(line)
            if not block.isValid():
                continue
            sel = QTextEdit.ExtraSelection()
            cur = QTextCursor(block)
            cur.clearSelection()
            sel.cursor = cur
            sel.format = fmt
            selections.append(sel)

        return selections

    def _collapsed_fold_selections(self) -> list[QTextEdit.ExtraSelection]:
        """Build ExtraSelections to highlight collapsed fold-header lines."""
        selections: list[QTextEdit.ExtraSelection] = []
        if not self._collapsed_folds:
            return selections

        p = self._editor_palette()
        doc = self.document()
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(p["editor_fold_highlight"]))
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
        p = self._editor_palette()
        doc = self.document()

        for error in self._errors:
            block = doc.findBlockByNumber(error.line - 1)
            if not block.isValid():
                continue

            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            match normalize_validation_severity(error.severity):
                case "warning":
                    uline = p["editor_warning_underline"]
                case "info":
                    uline = p["editor_info_underline"]
                case "hint":
                    uline = p["editor_hint_underline"]
                case _:
                    uline = p["editor_error_underline"]
            fmt.setUnderlineColor(QColor(uline))

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

    def apply_validation_errors(self, errors: list[SyntaxError_]) -> None:
        """Replace validation markers (e.g. from LSP ``publishDiagnostics``)."""
        old_has_errors = bool(self._errors)
        new_has_errors = bool(errors)
        self._errors = errors
        self.validation_changed.emit(errors)
        if old_has_errors or new_has_errors:
            self._highlight_matching_bracket()
            self._line_number_area.update()

    def _should_skip_script_validation(self) -> bool:
        """When ``True``, skip :meth:`_validate_script` (e.g. LSP owns diagnostics)."""
        return False

    def _validate(self) -> None:
        """Run syntax validation on the current content."""
        # When an LSP adapter owns diagnostics for this language, leave
        # ``_errors`` untouched — the adapter publishes its own list via
        # :meth:`apply_validation_errors`. Clobbering with ``[]`` here
        # races with diagnostics that arrive between language switch and
        # the next ``_validate`` tick, blanking real errors.
        text = self.toPlainText()
        if (
            self._language in ("javascript", "typescript", "python")
            and self._should_skip_script_validation()
        ):
            # LSP publishes most diagnostics; still flag ESM/CommonJS mismatch when not CJS.
            if text.strip() and self._language in ("javascript", "typescript"):
                mod_fmt = getattr(self, "_script_module_format", "esm")
                if mod_fmt != "commonjs":
                    esm_errors = self._validate_script(text)
                    self.apply_validation_errors(esm_errors)
            return

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

        elif self._language in ("javascript", "typescript", "python") and text.strip():
            errors.extend(self._validate_script(text))

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

    def _validate_script(self, text: str) -> list[SyntaxError_]:
        """Check syntax + pm API usage for a JavaScript or Python script."""
        from services.scripting.engine import ScriptLinter

        mod_fmt = getattr(self, "_script_module_format", "esm")
        if self._language in ("javascript", "typescript"):
            if mod_fmt == "commonjs":
                diags = ScriptLinter.check_commonjs_local_script(text)
            elif self._should_skip_script_validation():
                diags = ScriptLinter.check_es_module(text, self._language)
            elif not self._should_skip_script_validation():
                diags = ScriptLinter.check(text, self._language)
            else:
                diags = []
        elif not self._should_skip_script_validation():
            diags = ScriptLinter.check(text, self._language)
        else:
            diags = []

        return [
            SyntaxError_(
                line=d["line"],
                column=d["column"],
                message=d["message"],
                severity=d["severity"],
            )
            for d in diags
        ]
