"""Custom delegate for the saved responses list widget.

Paints a coloured status-code badge followed by the response name on the
first line, with muted metadata text on the second line.  This replaces
the default two-line plain-text rendering with a richer painted layout.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from ui.styling import theme
from ui.styling.theme import BADGE_BORDER_RADIUS, BADGE_FONT_SIZE, status_color

# -- Data roles stored on each QListWidgetItem -------------------------
ROLE_RESPONSE_CODE = Qt.ItemDataRole.UserRole + 1
ROLE_RESPONSE_NAME = Qt.ItemDataRole.UserRole + 2
ROLE_RESPONSE_META = Qt.ItemDataRole.UserRole + 3

# -- Badge / row geometry (px) -----------------------------------------
_BADGE_WIDTH = 36
_BADGE_HEIGHT = 16
_BADGE_NAME_SPACING = 6
_LEFT_PADDING = 6
_TOP_PADDING = 6
_LINE_SPACING = 2
_ROW_HEIGHT = 44


class SavedResponseDelegate(QStyledItemDelegate):
    """Paint a status badge, name, and metadata line for saved responses."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint the list row with a coloured badge and two text lines."""
        # 1. Let the style draw selection / hover background.
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

        code = index.data(ROLE_RESPONSE_CODE)
        name = index.data(ROLE_RESPONSE_NAME) or ""
        meta = index.data(ROLE_RESPONSE_META) or ""
        rect: QRect = option.rect  # type: ignore[assignment]

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 2. Status-code badge
        badge_x = rect.left() + _LEFT_PADDING
        badge_y = rect.top() + _TOP_PADDING + 1
        badge_rect = QRect(badge_x, badge_y, _BADGE_WIDTH, _BADGE_HEIGHT)

        bg_colour = QColor(status_color(code))
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

        # 3. Response name (right of badge, first line)
        name_x = badge_rect.right() + _BADGE_NAME_SPACING
        available_w = rect.right() - name_x - _LEFT_PADDING
        name_rect = QRect(name_x, rect.top() + _TOP_PADDING - 1, available_w, 20)

        name_font = QFont(painter.font())
        name_font.setPixelSize(12)
        name_font.setBold(True)

        state = option.state  # type: ignore[assignment]
        palette = option.palette  # type: ignore[assignment]
        if state & QStyle.StateFlag.State_Selected:
            text_color = palette.highlightedText().color()
        else:
            text_color = palette.text().color()

        painter.setPen(QPen(text_color))
        painter.setFont(name_font)
        fm = QFontMetrics(name_font)
        elided = fm.elidedText(name, Qt.TextElideMode.ElideRight, available_w)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, elided)

        # 4. Metadata (second line, full width, muted)
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
        if state & QStyle.StateFlag.State_Selected:
            meta_color = palette.highlightedText().color()
        else:
            meta_color = QColor(theme.COLOR_TEXT_MUTED)
        painter.setPen(QPen(meta_color))
        painter.setFont(meta_font)
        fm_meta = QFontMetrics(meta_font)
        elided_meta = fm_meta.elidedText(
            meta,
            Qt.TextElideMode.ElideRight,
            meta_rect.width(),
        )
        painter.drawText(meta_rect, Qt.AlignmentFlag.AlignVCenter, elided_meta)

        painter.restore()

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        """Return a fixed row height for all items."""
        return QSize(option.rect.width(), _ROW_HEIGHT)
