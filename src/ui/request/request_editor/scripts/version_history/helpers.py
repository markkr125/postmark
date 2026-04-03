"""Diff formatting, fold-range computation, and timestamp helpers."""

from __future__ import annotations

import difflib
from collections.abc import Sequence
from datetime import datetime

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

from ui.styling.theme import COLOR_DIFF_ADDED_INLINE, COLOR_DIFF_REMOVED_INLINE
from ui.widgets.code_editor import CodeEditorWidget

# Width (in pixels) of the coloured gutter stripe for changed lines.
_GUTTER_STRIPE_PX = 3

# Number of unchanged context lines shown above/below each diff hunk.
_FOLD_CONTEXT = 3


def _format_timestamp(ts: datetime) -> str:
    """Format a timestamp as a human-readable relative/absolute string."""
    now = datetime.now()
    delta = now - ts
    seconds = int(delta.total_seconds())

    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        mins = seconds // 60
        return f"{mins}m ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    if seconds < 604800:
        days = seconds // 86400
        return f"{days}d ago"
    return ts.strftime("%Y-%m-%d %H:%M")


def _line_format(color_hex: str) -> QTextCharFormat:
    """Return a full-width-selection char format with the given background."""
    fmt = QTextCharFormat()
    fmt.setBackground(QColor(color_hex))
    fmt.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
    return fmt


def _build_line_selections(
    editor: CodeEditorWidget,
    line_numbers: set[int],
    fmt: QTextCharFormat,
) -> list[QTextEdit.ExtraSelection]:
    """Create extra selections for full-line background highlighting."""
    selections: list[QTextEdit.ExtraSelection] = []
    doc = editor.document()
    for line_no in sorted(line_numbers):
        block = doc.findBlockByNumber(line_no)
        if not block.isValid():
            continue
        sel = QTextEdit.ExtraSelection()
        sel.format = QTextCharFormat(fmt)
        cur = QTextCursor(doc)
        cur.setPosition(block.position())
        cur.movePosition(
            QTextCursor.MoveOperation.EndOfBlock,
            QTextCursor.MoveMode.KeepAnchor,
        )
        sel.cursor = cur
        selections.append(sel)
    return selections


def _add_inline_selections(
    left_editor: CodeEditorWidget,
    right_editor: CodeEditorWidget,
    old_lines: list[str],
    new_lines: list[str],
    replace_pairs: list[tuple[range, range]],
    left_sels: list[QTextEdit.ExtraSelection],
    right_sels: list[QTextEdit.ExtraSelection],
) -> None:
    """Add character-level inline diff highlights for replaced lines."""
    removed_inline_fmt = QTextCharFormat()
    removed_inline_fmt.setBackground(QColor(COLOR_DIFF_REMOVED_INLINE))
    added_inline_fmt = QTextCharFormat()
    added_inline_fmt.setBackground(QColor(COLOR_DIFF_ADDED_INLINE))

    for old_range, new_range in replace_pairs:
        old_chunk = "\n".join(old_lines[old_range.start : old_range.stop])
        new_chunk = "\n".join(new_lines[new_range.start : new_range.stop])
        sm = difflib.SequenceMatcher(None, old_chunk, new_chunk)
        for tag, ci1, ci2, cj1, cj2 in sm.get_opcodes():
            if tag == "equal":
                continue
            if tag in ("replace", "delete"):
                _add_char_selection(
                    left_editor,
                    old_range.start,
                    ci1,
                    ci2,
                    old_lines,
                    removed_inline_fmt,
                    left_sels,
                )
            if tag in ("replace", "insert"):
                _add_char_selection(
                    right_editor,
                    new_range.start,
                    cj1,
                    cj2,
                    new_lines,
                    added_inline_fmt,
                    right_sels,
                )


def _add_char_selection(
    editor: CodeEditorWidget,
    block_start: int,
    char_start: int,
    char_end: int,
    lines: list[str],
    fmt: QTextCharFormat,
    selections: list[QTextEdit.ExtraSelection],
) -> None:
    """Add a character-range selection within the editor's document."""
    doc = editor.document()
    block = doc.findBlockByNumber(block_start)
    if not block.isValid():
        return
    doc_offset = block.position()
    sel = QTextEdit.ExtraSelection()
    sel.format = QTextCharFormat(fmt)
    cur = QTextCursor(doc)
    cur.setPosition(doc_offset + char_start)
    cur.setPosition(doc_offset + char_end, QTextCursor.MoveMode.KeepAnchor)
    sel.cursor = cur
    selections.append(sel)


def compute_fold_ranges(
    opcodes: Sequence[tuple[str, int, int, int, int]],
    old_count: int,
    new_count: int,
    context: int = _FOLD_CONTEXT,
) -> list[tuple[int, int, int, int]]:
    """Compute fold ranges for unchanged regions in a diff.

    Returns a list of ``(left_start, left_end, right_start, right_end)``
    tuples (exclusive end) that can be collapsed.
    """
    folds: list[tuple[int, int, int, int]] = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag != "equal":
            continue
        left_len = i2 - i1
        right_len = j2 - j1
        if left_len <= 2 * context or right_len <= 2 * context:
            continue
        folds.append((i1 + context, i2 - context, j1 + context, j2 - context))
    return folds
