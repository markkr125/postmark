"""Custom delegate for the send-history tree widget."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from ui.styling.theme import (
    BADGE_BORDER_RADIUS,
    BADGE_FONT_SIZE,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    status_color,
)

ROLE_HISTORY_CODE = Qt.ItemDataRole.UserRole + 1
ROLE_HISTORY_NAME = Qt.ItemDataRole.UserRole + 2
ROLE_HISTORY_META = Qt.ItemDataRole.UserRole + 3
ROLE_HISTORY_IS_DATE_GROUP = Qt.ItemDataRole.UserRole + 4

_BADGE_WIDTH = 36
_BADGE_HEIGHT = 16
_BADGE_NAME_SPACING = 6
_LEFT_PADDING = 6
_TOP_PADDING = 6
_LINE_SPACING = 2
_ROW_HEIGHT = 44
_DATE_GROUP_HEIGHT = 28


class HistoryEntryDelegate(QStyledItemDelegate):
    """Paint date group rows like collection folders and sends with status badges."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint a date group or a send-history row."""
        if index.data(ROLE_HISTORY_IS_DATE_GROUP):
            self._paint_date_group(painter, option, index)
            return

        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else None
        if style:
            opt = QStyleOptionViewItem(option)
            opt.text = ""
            opt.icon = QIcon()
            style.drawControl(
                QStyle.ControlElement.CE_ItemViewItem,
                opt,
                painter,
                option.widget,
            )

        code = index.data(ROLE_HISTORY_CODE)
        name = index.data(ROLE_HISTORY_NAME) or ""
        meta = index.data(ROLE_HISTORY_META) or ""
        rect: QRect = option.rect  # type: ignore[assignment]

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        badge_x = rect.left() + _LEFT_PADDING
        badge_y = rect.top() + _TOP_PADDING + 1
        badge_rect = QRect(badge_x, badge_y, _BADGE_WIDTH, _BADGE_HEIGHT)

        bg_colour = QColor(status_color(code if code is not None else 0))
        painter.setBrush(bg_colour)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(
            badge_rect,
            BADGE_BORDER_RADIUS,
            BADGE_BORDER_RADIUS,
        )

        badge_font = QFont(painter.font())
        badge_font.setPixelSize(BADGE_FONT_SIZE)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.setPen(QPen(QColor("#ffffff")))
        badge_text = str(code) if code is not None else "\u2014"
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        name_x = badge_rect.right() + _BADGE_NAME_SPACING
        available_w = rect.right() - name_x - _LEFT_PADDING
        name_rect = QRect(name_x, rect.top() + _TOP_PADDING - 1, available_w, 20)

        name_font = QFont(painter.font())
        name_font.setPixelSize(12)
        name_font.setBold(True)

        text_color = QColor(COLOR_TEXT)

        painter.setPen(QPen(text_color))
        painter.setFont(name_font)
        fm = QFontMetrics(name_font)
        elided = fm.elidedText(name, Qt.TextElideMode.ElideRight, available_w)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, elided)

        meta_y = rect.top() + _TOP_PADDING + _BADGE_HEIGHT + _LINE_SPACING
        meta_rect = QRect(
            rect.left() + _LEFT_PADDING,
            meta_y,
            rect.width() - _LEFT_PADDING * 2,
            16,
        )

        meta_font = QFont(painter.font())
        meta_font.setPixelSize(11)
        meta_font.setBold(False)
        painter.setPen(QPen(QColor(COLOR_TEXT_MUTED)))
        painter.setFont(meta_font)
        fm_meta = QFontMetrics(meta_font)
        elided_meta = fm_meta.elidedText(
            meta,
            Qt.TextElideMode.ElideRight,
            meta_rect.width(),
        )
        painter.drawText(meta_rect, Qt.AlignmentFlag.AlignVCenter, elided_meta)

        painter.restore()

    def _paint_date_group(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint a date group row using standard tree branch + bold label."""
        self.initStyleOption(option, index)
        opt = QStyleOptionViewItem(option)
        label = str(index.data(ROLE_HISTORY_NAME) or index.data(Qt.ItemDataRole.DisplayRole) or "")
        opt.text = label
        font = QFont(opt.font)
        font.setPixelSize(12)
        font.setBold(True)
        opt.font = font
        style = option.widget.style() if option.widget else None
        if style:
            style.drawControl(
                QStyle.ControlElement.CE_ItemViewItem,
                opt,
                painter,
                option.widget,
            )

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        """Return a fixed row height for date groups and send rows."""
        if index.data(ROLE_HISTORY_IS_DATE_GROUP):
            return QSize(option.rect.width(), _DATE_GROUP_HEIGHT)
        return QSize(option.rect.width(), _ROW_HEIGHT)
