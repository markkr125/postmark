"""Paint delegate for AI session history rows."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractItemModel,
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QAbstractItemView

from ui.sidebar.ai.chat_sessions.history.model import (
    ACTIVE_SESSION_ROLE,
    FULL_TITLE_ROLE,
    RELATIVE_TIME_ROLE,
    RUNNING_ROLE,
    SESSION_ID_ROLE,
)
from ui.styling import theme
from ui.styling.icons import phi
from ui.styling.theme import COLOR_ACCENT, COLOR_BORDER, COLOR_TEXT

_ROW_HEIGHT_PX = 44
_H_PADDING_PX = 8
_V_PADDING_PX = 6
_LINE_GAP_PX = 2
_TITLE_FONT_PX = 12
_TIME_FONT_PX = 10
_MENU_ICON_PX = 16
_MENU_RIGHT_GAP_PX = 6
_MENU_HIT_PAD_PX = 4
_MENU_GUTTER_PX = _MENU_RIGHT_GAP_PX + _MENU_ICON_PX + _MENU_HIT_PAD_PX
_SPINNER_PX = 12
_SPINNER_GAP_PX = 6
_SPINNER_ARC_SPAN = 90 * 16
_SPINNER_FRAME_COUNT = 8


def _paint_running_spinner(painter: QPainter, rect: QRect, frame: int) -> None:
    """Paint a small indeterminate accent arc for in-flight session rows."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    inner = rect.adjusted(1, 1, -1, -1)
    track = QPen(QColor(COLOR_BORDER), 1.5)
    track.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(track)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(inner)
    arc_pen = QPen(QColor(COLOR_ACCENT), 1.5)
    arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(arc_pen)
    start_angle = (90 - (frame % _SPINNER_FRAME_COUNT) * (360 // _SPINNER_FRAME_COUNT)) * 16
    painter.drawArc(inner, start_angle, -_SPINNER_ARC_SPAN)
    painter.restore()


def session_row_viewport_rect(row_rect: QRect, viewport_width: int) -> QRect:
    """Return *row_rect* clipped to the list viewport (exclude scrollbar gutter)."""
    if viewport_width <= 0:
        return row_rect
    width = min(row_rect.width(), viewport_width)
    return QRect(row_rect.left(), row_rect.top(), width, row_rect.height())


def session_row_menu_rect(row_rect: QRect, *, viewport_width: int = 0) -> QRect:
    """Return the ⋯ icon bounds at the trailing edge of *row_rect*."""
    content = session_row_viewport_rect(row_rect, viewport_width)
    x = content.right() - _MENU_RIGHT_GAP_PX - _MENU_ICON_PX
    y = content.top() + (content.height() - _MENU_ICON_PX) // 2
    return QRect(x, y, _MENU_ICON_PX, _MENU_ICON_PX)


def session_row_menu_hit(row_rect: QRect, pos: QPoint, *, viewport_width: int = 0) -> bool:
    """Return whether *pos* (viewport-local) is on the ⋯ control."""
    hit = session_row_menu_rect(row_rect, viewport_width=viewport_width)
    hit = hit.adjusted(
        -_MENU_HIT_PAD_PX,
        -_MENU_HIT_PAD_PX,
        _MENU_HIT_PAD_PX,
        _MENU_HIT_PAD_PX,
    )
    return hit.contains(pos)


def session_row_title_right(row_rect: QRect, *, viewport_width: int = 0) -> int:
    """Return the right edge for elided title text before the ⋯ gutter."""
    content = session_row_viewport_rect(row_rect, viewport_width)
    return session_row_menu_rect(content, viewport_width=0).left() - 4


def _list_viewport_width(option: QStyleOptionViewItem) -> int:
    """Return the QListView viewport width for row layout, when available."""
    widget = option.widget
    if not isinstance(widget, QAbstractItemView):
        return 0
    return widget.viewport().width()


class SessionHistoryRowDelegate(QStyledItemDelegate):
    """Paint elided title, relative time, hover ⋯, and route row vs menu clicks."""

    menu_requested = Signal(QModelIndex)
    row_activated = Signal(QModelIndex)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialise delegate with no menu row highlighted."""
        super().__init__(parent)
        self._menu_open_row = -1
        self._spin_frame = 0

    def spin_frame(self) -> int:
        """Return the current running-row spinner animation frame."""
        return self._spin_frame

    def advance_spin_frame(self) -> None:
        """Advance the running-row spinner animation frame."""
        self._spin_frame = (self._spin_frame + 1) % _SPINNER_FRAME_COUNT

    def set_menu_open_row(self, row: int) -> None:
        """Highlight ⋯ on *row* while the actions flyout is open."""
        self._menu_open_row = row

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Draw hover/selection background, title, time, and optional ⋯ menu."""
        rect: QRect = option.rect  # type: ignore[assignment]
        viewport_w = _list_viewport_width(option)
        content_rect = session_row_viewport_rect(rect, viewport_w)
        title = str(index.data(FULL_TITLE_ROLE) or index.data(Qt.ItemDataRole.DisplayRole) or "")
        time_text = str(index.data(RELATIVE_TIME_ROLE) or "")
        is_active = bool(index.data(ACTIVE_SESSION_ROLE))
        is_running = bool(index.data(RUNNING_ROLE))
        is_placeholder = not index.data(SESSION_ID_ROLE) or title in {"Loading…", "No sessions yet"}

        self.initStyleOption(option, index)
        state = option.state  # type: ignore[assignment]
        show_menu = not is_placeholder and (
            bool(state & QStyle.StateFlag.State_MouseOver) or index.row() == self._menu_open_row
        )

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

        text_left = content_rect.left() + _H_PADDING_PX
        if is_running:
            spinner_top = content_rect.top() + (content_rect.height() - _SPINNER_PX) // 2
            spinner_rect = QRect(text_left, spinner_top, _SPINNER_PX, _SPINNER_PX)
            _paint_running_spinner(painter, spinner_rect, self._spin_frame)
            text_left += _SPINNER_PX + _SPINNER_GAP_PX
        text_right = (
            session_row_title_right(content_rect, viewport_width=0)
            if show_menu
            else content_rect.right() - _MENU_GUTTER_PX
        )
        text_width = max(0, text_right - text_left)

        title_font = QFont(painter.font())
        title_font.setPixelSize(_TITLE_FONT_PX)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor(theme.COLOR_TEXT)))
        title_rect = QRect(
            text_left,
            content_rect.top() + _V_PADDING_PX,
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

        if show_menu:
            menu_rect = session_row_menu_rect(content_rect, viewport_width=0)
            icon = phi("dots-three-bold", size=_MENU_ICON_PX, color=COLOR_TEXT)
            painter.drawPixmap(
                menu_rect,
                icon.pixmap(_MENU_ICON_PX, _MENU_ICON_PX),
            )

        painter.restore()

    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """Route ⋯ menu vs row-body clicks; consume releases so row open does not fire."""
        if not index.isValid():
            return super().editorEvent(event, model, option, index)
        title = str(index.data(FULL_TITLE_ROLE) or index.data(Qt.ItemDataRole.DisplayRole) or "")
        is_placeholder = not index.data(SESSION_ID_ROLE) or title in {"Loading…", "No sessions yet"}
        if is_placeholder:
            return super().editorEvent(event, model, option, index)
        if event.type() != QEvent.Type.MouseButtonRelease:
            return super().editorEvent(event, model, option, index)
        mouse = event
        if not isinstance(mouse, QMouseEvent):
            return super().editorEvent(event, model, option, index)
        if mouse.button() != Qt.MouseButton.LeftButton:
            return super().editorEvent(event, model, option, index)

        pos = mouse.position().toPoint()
        row_rect: QRect = option.rect  # type: ignore[assignment]
        viewport_w = _list_viewport_width(option)
        content_rect = session_row_viewport_rect(row_rect, viewport_w)

        if session_row_menu_hit(content_rect, pos, viewport_width=0):
            self.menu_requested.emit(index)  # type: ignore[arg-type]
            return True

        if content_rect.contains(pos):
            self.row_activated.emit(index)  # type: ignore[arg-type]
            return True

        return super().editorEvent(event, model, option, index)

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        """Return a fixed row height for virtualized scrolling."""
        width = option.rect.width() if option.rect.width() > 0 else 200
        return QSize(width, _ROW_HEIGHT_PX)


__all__ = [
    "_ROW_HEIGHT_PX",
    "SessionHistoryRowDelegate",
    "session_row_menu_hit",
    "session_row_menu_rect",
    "session_row_title_right",
    "session_row_viewport_rect",
]
