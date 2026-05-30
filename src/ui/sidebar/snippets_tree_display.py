"""Shared labels and layout metrics for the snippets sidebar tree."""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontMetrics

TREE_ICON_SIZE = 16
TREE_LEFT_PADDING = 2
ICON_NAME_GAP = 6
TITLE_COUNT_GAP = 8
ROW_RIGHT_PAD = 8

_CONTEXT_LABELS: dict[str, str] = {
    "pre": "Pre-request",
    "test": "Post-response",
    "both": "Any",
}


def snippet_context_label(context: str) -> str:
    """Return a short tree label for stored snippet context *context*."""
    key = (context or "both").lower().strip()
    return _CONTEXT_LABELS.get(key, key)


def language_snippet_count_label(count: int) -> str:
    """Return a muted suffix for a language root (e.g. ``3 snippets``)."""
    if count <= 0:
        return "0 snippets"
    if count == 1:
        return "1 snippet"
    return f"{count} snippets"


def snippet_name_start_x(row_left: int) -> int:
    """X coordinate where the snippet/category title begins."""
    return row_left + TREE_LEFT_PADDING + TREE_ICON_SIZE + ICON_NAME_GAP


def tree_item_depth(item) -> int:
    """Return nesting depth of *item* (0 for top-level language roots)."""
    depth = 0
    parent = item.parent()
    while parent is not None:
        depth += 1
        parent = parent.parent()
    return depth


def folder_label_rect(tree, item, row_rect: QRect) -> QRect:
    """Return label bounds for a folder/category row (branch + folder icon)."""
    from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

    if not isinstance(tree, QTreeWidget) or not isinstance(item, QTreeWidgetItem):
        return row_rect
    depth = tree_item_depth(item)
    left = row_rect.left() + 8 + depth * tree.indentation()
    return QRect(left, row_rect.top(), max(40, row_rect.right() - left - 8), row_rect.height())


def snippet_name_rect(row_rect: QRect) -> QRect:
    """Return the QRect for the snippet basename (matches local-script rename overlay)."""
    x = snippet_name_start_x(row_rect.left())
    return QRect(x, row_rect.top(), row_rect.right() - x + 1, row_rect.height())


def snippet_row_text_rects(
    row_rect: QRect,
    *,
    context: str,
    name_font: QFont,
    context_font: QFont,
) -> tuple[QRect, QRect]:
    """Return ``(name_rect, context_rect)`` with context aligned to the row's right edge."""
    ctx_text = snippet_context_label(context)
    ctx_fm = QFontMetrics(context_font)
    ctx_w = ctx_fm.horizontalAdvance(ctx_text)
    ctx_left = row_rect.right() - ROW_RIGHT_PAD - ctx_w
    name_left = snippet_name_start_x(row_rect.left())
    name_w = max(0, ctx_left - TITLE_COUNT_GAP - name_left)
    name_rect = QRect(name_left, row_rect.top(), name_w, row_rect.height())
    context_rect = QRect(ctx_left, row_rect.top(), ctx_w, row_rect.height())
    return name_rect, context_rect


def language_row_text_rects(
    row_rect: QRect,
    *,
    title: str,
    count: int,
    title_font: QFont,
    count_font: QFont,
) -> tuple[QRect, QRect]:
    """Return ``(title_rect, count_rect)`` for a language root row."""
    count_text = language_snippet_count_label(count)
    count_fm = QFontMetrics(count_font)
    count_w = count_fm.horizontalAdvance(count_text)
    count_left = row_rect.right() - ROW_RIGHT_PAD - count_w
    title_left = snippet_name_start_x(row_rect.left())
    title_w = max(0, count_left - TITLE_COUNT_GAP - title_left)
    title_rect = QRect(title_left, row_rect.top(), title_w, row_rect.height())
    count_rect = QRect(count_left, row_rect.top(), count_w, row_rect.height())
    return title_rect, count_rect
