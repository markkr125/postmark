"""Paint delegate for AI session history rows."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from ui.sidebar.ai.chat_sessions.history.model import (
    ACTIVE_SESSION_ROLE,
    FULL_TITLE_ROLE,
    RELATIVE_TIME_ROLE,
    SESSION_ID_ROLE,
)
from ui.styling import theme

_ROW_HEIGHT_PX = 44
_H_PADDING_PX = 8
_V_PADDING_PX = 6
_LINE_GAP_PX = 2
_TITLE_FONT_PX = 12
_TIME_FONT_PX = 10


class SessionHistoryRowDelegate(QStyledItemDelegate):
    """Paint elided title and relative time for one session row."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Draw hover/selection background, title, time, and active-session highlight."""
        rect: QRect = option.rect  # type: ignore[assignment]
        title = str(index.data(FULL_TITLE_ROLE) or index.data(Qt.ItemDataRole.DisplayRole) or "")
        time_text = str(index.data(RELATIVE_TIME_ROLE) or "")
        is_active = bool(index.data(ACTIVE_SESSION_ROLE))
        is_placeholder = not index.data(SESSION_ID_ROLE) or title in {"Loading…", "No sessions yet"}

        self.initStyleOption(option, index)
        state = option.state  # type: ignore[assignment]

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not is_placeholder:
            if is_active:
                state |= QStyle.StateFlag.State_Selected
                option.state = state  # type: ignore[attr-defined]
            style = option.widget.style() if option.widget else None
            if style is not None:
                bg_opt = QStyleOptionViewItem(option)
                bg_opt.text = ""
                bg_opt.icon = QIcon()
                style.drawControl(
                    QStyle.ControlElement.CE_ItemViewItem,
                    bg_opt,
                    painter,
                    option.widget,
                )

        if is_placeholder:
            painter.setPen(QPen(QColor(theme.COLOR_TEXT_MUTED)))
            painter.drawText(
                rect.adjusted(_H_PADDING_PX, 0, -_H_PADDING_PX, 0),
                Qt.AlignmentFlag.AlignVCenter,
                title,
            )
            painter.restore()
            return

        text_left = rect.left() + _H_PADDING_PX
        text_right = rect.right() - _H_PADDING_PX
        text_width = max(0, text_right - text_left)

        title_font = QFont(painter.font())
        title_font.setPixelSize(_TITLE_FONT_PX)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor(theme.COLOR_TEXT)))
        title_rect = QRect(
            text_left,
            rect.top() + _V_PADDING_PX,
            text_width,
            18,
        )
        elided_title = QFontMetrics(title_font).elidedText(
            title,
            Qt.TextElideMode.ElideRight,
            text_width,
        )
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter, elided_title)

        time_font = QFont(painter.font())
        time_font.setPixelSize(_TIME_FONT_PX)
        painter.setFont(time_font)
        painter.setPen(QPen(QColor(theme.COLOR_TEXT_MUTED)))
        time_rect = QRect(
            text_left,
            title_rect.bottom() + _LINE_GAP_PX,
            text_width,
            14,
        )
        painter.drawText(time_rect, Qt.AlignmentFlag.AlignVCenter, time_text)
        painter.restore()

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        """Return a fixed row height for virtualized scrolling."""
        width = option.rect.width() if option.rect.width() > 0 else 200
        return QSize(width, _ROW_HEIGHT_PX)


__all__ = ["_ROW_HEIGHT_PX", "SessionHistoryRowDelegate"]
