"""Custom delegate for version list items (two-line rendering)."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from ui.styling.theme import COLOR_TEXT, COLOR_TEXT_MUTED

# Vertical padding inside each list item.
_V_PAD = 5

# Horizontal offset (padding + accent border width).
_H_OFFSET = 11


class _VersionItemDelegate(QStyledItemDelegate):
    """Render version items with a label line and a smaller date line."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the delegate."""
        super().__init__(parent)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint two lines: label on top, date below in muted text."""
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # Draw background only (suppress default text rendering).
        opt.text = ""
        style = opt.widget.style() if opt.widget else None
        if style is not None:
            style.drawControl(
                QStyle.ControlElement.CE_ItemViewItem,
                opt,
                painter,
                opt.widget,
            )

        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        parts = text.split("\n", 1)
        label = parts[0]
        date = parts[1] if len(parts) > 1 else ""

        rect = opt.rect
        left = rect.left() + _H_OFFSET

        painter.save()

        # 1. Label line (normal size).
        label_font = QFont(opt.font)
        label_font.setPixelSize(12)
        painter.setFont(label_font)
        painter.setPen(QColor(COLOR_TEXT))
        label_y = rect.top() + _V_PAD + painter.fontMetrics().ascent()
        painter.drawText(left, label_y, label)

        # 2. Date line (smaller, muted).
        if date:
            date_font = QFont(opt.font)
            date_font.setPixelSize(10)
            painter.setFont(date_font)
            painter.setPen(QColor(COLOR_TEXT_MUTED))
            date_y = label_y + 2 + painter.fontMetrics().ascent()
            painter.drawText(left, date_y, date)

        painter.restore()
