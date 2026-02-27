"""Custom delegate that paints method badges for request items in the tree.

Using a ``QStyledItemDelegate`` instead of per-row ``setItemWidget`` avoids
creating thousands of ``QWidget`` / ``QLabel`` objects — saving ~50-60 KB per
request item in memory.
"""

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

from ui.collections.tree.constants import ROLE_ITEM_TYPE, ROLE_METHOD
from ui.theme import (
    BADGE_BORDER_RADIUS,
    BADGE_FONT_SIZE,
    BADGE_HEIGHT,
    BADGE_MIN_WIDTH,
    TREE_ROW_HEIGHT,
    method_color,
    method_short_label,
)

# Horizontal gap between badge and name label (px).
_BADGE_NAME_SPACING = 6

# Left padding before the badge (px).
_LEFT_PADDING = 2


class CollectionTreeDelegate(QStyledItemDelegate):
    """Paint method badge + request name without creating child widgets.

    Folder items fall through to the default ``QStyledItemDelegate``
    implementation so they keep their standard icon + text rendering.
    """

    # ------------------------------------------------------------------
    # QStyledItemDelegate overrides
    # ------------------------------------------------------------------
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint a coloured method badge followed by the request name."""
        item_type = index.data(ROLE_ITEM_TYPE)
        if item_type != "request":
            super().paint(painter, option, index)
            return

        # 1. Let the style draw selection / hover background
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else None
        if style:
            # Draw background only — suppress text and icon.
            opt = QStyleOptionViewItem(option)
            opt.text = ""
            opt.icon = QIcon()
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, option.widget)

        method = index.data(ROLE_METHOD) or "GET"
        # Read the display name from the QTreeWidgetItem's column 1 text
        tree = self.parent()
        name = ""
        if isinstance(tree, QTreeWidget):
            item = tree.itemFromIndex(index)
            if item is not None:
                name = item.text(1) or ""
        rect: QRect = option.rect  # type: ignore[assignment]

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 2. Badge rectangle
        badge_x = rect.left() + _LEFT_PADDING
        badge_y = rect.top() + (rect.height() - BADGE_HEIGHT) // 2
        badge_rect = QRect(badge_x, badge_y, BADGE_MIN_WIDTH, BADGE_HEIGHT)

        bg_colour = QColor(method_color(method))
        painter.setBrush(bg_colour)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge_rect, BADGE_BORDER_RADIUS, BADGE_BORDER_RADIUS)

        # 3. Badge text (centred)
        badge_font = QFont(painter.font())
        badge_font.setPixelSize(BADGE_FONT_SIZE)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.setPen(QPen(QColor("#ffffff")))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, method_short_label(method))

        # 4. Request name
        name_x = badge_rect.right() + _BADGE_NAME_SPACING
        name_rect = QRect(name_x, rect.top(), rect.right() - name_x, rect.height())

        name_font = QFont(painter.font())
        name_font.setPixelSize(12)
        name_font.setBold(False)

        # Use the palette's normal or highlighted text depending on selection
        state = option.state  # type: ignore[assignment]
        palette = option.palette  # type: ignore[assignment]
        if state & QStyle.StateFlag.State_Selected:
            text_color = palette.highlightedText().color()
        else:
            text_color = palette.text().color()
        painter.setPen(QPen(text_color))
        painter.setFont(name_font)

        # Elide text if it exceeds the available width
        fm = QFontMetrics(name_font)
        elided = fm.elidedText(name, Qt.TextElideMode.ElideRight, name_rect.width())
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, elided)

        painter.restore()

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        """Return a fixed row height for request items."""
        item_type = index.data(ROLE_ITEM_TYPE)
        if item_type == "request":
            return QSize(0, TREE_ROW_HEIGHT)
        return super().sizeHint(option, index)

    def createEditor(  # type: ignore[override]
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget | None:
        """Suppress the default editor for request items.

        Request rename is handled by ``CollectionTree._rename_request``
        which creates its own ``QLineEdit`` overlay.
        """
        item_type = index.data(ROLE_ITEM_TYPE)
        if item_type == "request":
            return None
        return super().createEditor(parent, option, index)
