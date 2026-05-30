"""Delegate for the snippets sidebar tree (matches local-script leaf rows)."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QWidget,
)

from ui.sidebar.snippets_tree_constants import (
    KIND_LANGUAGE,
    KIND_SNIPPET,
    ROLE_LANG_KEY,
    ROLE_NODE_KIND,
    ROLE_SNIPPET_CONTEXT,
    ROLE_SNIPPET_COUNT,
)
from ui.sidebar.snippets_tree_display import (
    TREE_ICON_SIZE,
    language_row_text_rects,
    language_snippet_count_label,
    snippet_context_label,
    snippet_row_text_rects,
)
from ui.styling.language_icons import language_icon_pixmap
from ui.styling.theme import COLOR_TEXT_MUTED, TREE_ROW_HEIGHT

_TREE_LEFT_PADDING = 2


class SnippetsTreeDelegate(QStyledItemDelegate):
    """Paint language roots, snippet leaves, and folder rows in the snippets tree."""

    def __init__(self, tree: QTreeWidget, parent: QWidget | None = None) -> None:
        """Attach to *tree* for row lookups."""
        super().__init__(parent or tree)
        self._tree = tree

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint custom rows; category folders use the default style."""
        kind = index.data(ROLE_NODE_KIND)
        if kind not in (KIND_LANGUAGE, KIND_SNIPPET):
            super().paint(painter, option, index)
            return

        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else None
        if style:
            opt = QStyleOptionViewItem(option)
            opt.text = ""
            opt.icon = QIcon()
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, option.widget)

        rect: QRect = option.rect  # type: ignore[assignment]
        text_color = option.palette.text().color()  # type: ignore[union-attr]
        muted = QColor(COLOR_TEXT_MUTED)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        lang_key = str(index.data(ROLE_LANG_KEY) or "javascript")
        icon_x = rect.left() + _TREE_LEFT_PADDING
        icon_y = rect.top() + (rect.height() - TREE_ICON_SIZE) // 2
        icon = language_icon_pixmap(lang_key, size=TREE_ICON_SIZE)
        painter.drawPixmap(QRect(icon_x, icon_y, TREE_ICON_SIZE, TREE_ICON_SIZE), icon)

        if kind == KIND_LANGUAGE:
            self._paint_language_row(painter, index, rect, text_color, muted)
        else:
            self._paint_snippet_row(painter, index, rect, text_color, muted)

        painter.restore()

    def _paint_language_row(
        self,
        painter: QPainter,
        index: QModelIndex | QPersistentModelIndex,
        rect: QRect,
        text_color: QColor,
        muted: QColor,
    ) -> None:
        """Draw language title and trailing snippet count."""
        item = self._tree.itemFromIndex(index)
        title = ""
        if item is not None:
            title = item.text(0) or item.text(1) or ""
        raw_count = index.data(ROLE_SNIPPET_COUNT)
        count = int(raw_count) if isinstance(raw_count, int) else 0

        title_font = QFont(painter.font())
        title_font.setPixelSize(12)
        count_font = QFont(painter.font())
        count_font.setPixelSize(11)
        title_rect, count_rect = language_row_text_rects(
            rect,
            title=title,
            count=count,
            title_font=title_font,
            count_font=count_font,
        )
        painter.setFont(title_font)
        painter.setPen(QPen(text_color))
        elided_title = QFontMetrics(title_font).elidedText(
            title, Qt.TextElideMode.ElideRight, title_rect.width()
        )
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter, elided_title)

        painter.setFont(count_font)
        painter.setPen(QPen(muted))
        painter.drawText(
            count_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            language_snippet_count_label(count),
        )

    def _paint_snippet_row(
        self,
        painter: QPainter,
        index: QModelIndex | QPersistentModelIndex,
        rect: QRect,
        text_color: QColor,
        muted: QColor,
    ) -> None:
        """Draw snippet name and a muted context label on the right."""
        item = self._tree.itemFromIndex(index)
        name = ""
        context = "both"
        if item is not None:
            name = item.text(1) or item.text(0) or ""
            context = str(item.data(0, ROLE_SNIPPET_CONTEXT) or "both")

        name_font = QFont(painter.font())
        name_font.setPixelSize(12)
        context_font = QFont(painter.font())
        context_font.setPixelSize(11)
        name_rect, context_rect = snippet_row_text_rects(
            rect,
            context=context,
            name_font=name_font,
            context_font=context_font,
        )

        painter.setFont(name_font)
        painter.setPen(QPen(text_color))
        elided = QFontMetrics(name_font).elidedText(
            name, Qt.TextElideMode.ElideRight, name_rect.width()
        )
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, elided)

        painter.setFont(context_font)
        painter.setPen(QPen(muted))
        ctx_label = snippet_context_label(context)
        painter.drawText(
            context_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            ctx_label,
        )

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        """Fixed row height for language roots and snippet leaves."""
        if index.data(ROLE_NODE_KIND) in (KIND_LANGUAGE, KIND_SNIPPET):
            return QSize(0, TREE_ROW_HEIGHT)
        return super().sizeHint(option, index)

    def createEditor(  # type: ignore[override]
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget | None:
        """Category rename uses the tree editor; snippet leaves use an overlay."""
        if index.data(ROLE_NODE_KIND) == KIND_SNIPPET:
            return None
        return super().createEditor(parent, option, index)
