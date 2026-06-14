"""Session history popover for the AI assistant flyout header."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import ClassVar

from PySide6.QtCore import QDateTime, QEvent, QObject, QPoint, QSize, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import Shiboken

from services.ai.chat.session_service import AiChatSessionDict
from ui.sidebar.ai.chat_sessions.time_format import format_relative_time
from ui.styling.theme import AI_SESSION_HISTORY_POPUP_WIDTH_EM

_ID_ROLE = Qt.ItemDataRole.UserRole + 1
_SHOW_GRACE_MS = 200
_POPUP_MIN_HEIGHT_PX = 280


class _ElidingSessionTitleLabel(QLabel):
    """Session title that ellipsizes instead of widening the list."""

    def __init__(self, full_text: str, parent: QWidget | None = None) -> None:
        """Build a single-line title label for one session row."""
        super().__init__(parent)
        self.setObjectName("aiSessionHistoryTitle")
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._full_text = full_text.strip()
        self.setToolTip(self._full_text)
        self._apply_elide()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Re-elide when the row width changes."""
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        """Paint truncated title text for the current width."""
        width = max(0, self.width())
        elided = self.fontMetrics().elidedText(
            self._full_text,
            Qt.TextElideMode.ElideRight,
            width,
        )
        self.setText(elided)


class _SessionRow(QWidget):
    """One session row with elided title and relative time beneath it."""

    def __init__(
        self,
        session: AiChatSessionDict,
        *,
        selected: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Build a row for *session*."""
        super().__init__(parent)
        self.setObjectName("aiSessionHistoryRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_selected(selected)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        title = _ElidingSessionTitleLabel(session["title"], self)
        title.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(title)

        updated = datetime.fromisoformat(session["updated_at"])
        time_lbl = QLabel(format_relative_time(updated))
        time_lbl.setObjectName("aiSessionHistoryTime")
        time_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        time_lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout.addWidget(time_lbl)

    def _apply_selected(self, selected: bool) -> None:
        """Toggle the active-session highlight used when the popover opens."""
        self.setProperty("activeSession", selected)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()


class AiSessionHistoryPopup(QFrame):
    """Popover listing prior AI chat sessions (local only in v1)."""

    _instance: ClassVar[AiSessionHistoryPopup | None] = None

    @classmethod
    def instance(cls) -> AiSessionHistoryPopup:
        """Return the singleton popover, creating it if needed."""
        if cls._instance is None or not Shiboken.isValid(cls._instance):
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build search field and session list."""
        super().__init__(parent)
        self.setObjectName("aiSessionHistoryPopup")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumHeight(_POPUP_MIN_HEIGHT_PX)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._search = QLineEdit()
        self._search.setObjectName("aiSessionSearch")
        self._search.setPlaceholderText("Search sessions…")
        self._search.setClearButtonEnabled(True)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setObjectName("aiSessionHistoryList")
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self._list, 1)

        self._sessions: list[AiChatSessionDict] = []
        self._active_session_id: str | None = None
        self._on_select: Callable[[str], None] | None = None
        self._anchor: QWidget | None = None
        self._opened_at_ms = 0

        self._search.textChanged.connect(self._apply_filter)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.viewport().installEventFilter(self)
        self._list.verticalScrollBar().rangeChanged.connect(self._on_list_scroll_range_changed)

        def _clear_singleton_ref(*_args: object) -> None:
            if AiSessionHistoryPopup._instance is self:
                AiSessionHistoryPopup._instance = None

        self.destroyed.connect(_clear_singleton_ref)

    def _on_list_scroll_range_changed(self, _minimum: int, _maximum: int) -> None:
        """Re-sync row widths when the scrollbar appears or disappears."""
        self._sync_item_widths()

    def show_for(
        self,
        anchor: QWidget,
        sessions: list[AiChatSessionDict],
        on_select: Callable[[str], None],
        *,
        active_session_id: str | None = None,
    ) -> None:
        """Populate and show anchored to *anchor*."""
        app = QGuiApplication.instance()
        if app is not None and self.isVisible():
            app.removeEventFilter(self)
        self._anchor = anchor
        self._sessions = list(sessions)
        self._active_session_id = active_session_id
        self._on_select = on_select
        self._search.clear()
        self.setFixedWidth(self._width_for_anchor(anchor))
        self._populate(self._sessions)
        self._position_for(anchor)
        self._set_anchor_checked(anchor, True)
        self.show()
        self.raise_()
        self.activateWindow()
        self._search.setFocus()
        self._opened_at_ms = QDateTime.currentMSecsSinceEpoch()
        if app is not None:
            app.installEventFilter(self)

    def hide_popup(self) -> None:
        """Hide and clear callbacks."""
        app = QGuiApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        anchor = self._anchor
        self.hide()
        self._anchor = None
        self._active_session_id = None
        self._on_select = None
        if anchor is not None:
            self._set_anchor_checked(anchor, False)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Dismiss on Escape."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide_popup()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Close on outside click after grace window; keep row widths in sync."""
        if obj is self._list.viewport() and event.type() == QEvent.Type.Resize:
            self._sync_item_widths()
            return super().eventFilter(obj, event)

        is_press = event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent)
        past_grace = QDateTime.currentMSecsSinceEpoch() - self._opened_at_ms >= _SHOW_GRACE_MS
        if is_press and past_grace and self.isVisible():
            mouse = event
            global_pos = mouse.globalPosition().toPoint()  # type: ignore[attr-defined]
            if self.geometry().contains(global_pos):
                return super().eventFilter(obj, event)
            if self._click_hits_anchor(global_pos):
                return super().eventFilter(obj, event)
            self.hide_popup()
        return super().eventFilter(obj, event)

    def _click_hits_anchor(self, global_pos: QPoint) -> bool:
        """Return whether *global_pos* is on the trigger button (toggle handles close)."""
        if self._anchor is None or not self._anchor.isVisible():
            return False
        local = self._anchor.mapFromGlobal(global_pos)
        return self._anchor.rect().contains(local)

    @staticmethod
    def _set_anchor_checked(anchor: QWidget, checked: bool) -> None:
        """Sync the history trigger button with popover visibility."""
        if isinstance(anchor, QAbstractButton):
            anchor.setChecked(checked)

    def _width_for_anchor(self, _anchor: QWidget) -> int:
        """Return the fixed popover width from theme (independent of flyout width)."""
        em = self.fontMetrics().height()
        return round(AI_SESSION_HISTORY_POPUP_WIDTH_EM * em)

    def _position_for(self, anchor: QWidget) -> None:
        """Place the popover above the anchor, flipping below if clipped."""
        self.adjustSize()
        height = self.sizeHint().height()
        top_left = anchor.mapToGlobal(QPoint(0, 0))
        bottom_left = anchor.mapToGlobal(QPoint(0, anchor.height()))
        screen = QGuiApplication.screenAt(top_left) or QGuiApplication.primaryScreen()
        sr = screen.availableGeometry() if screen else None
        x = top_left.x()
        y = top_left.y() - height - 4
        if y < (sr.top() if sr is not None else 0):
            y = bottom_left.y() + 4
        if sr is not None:
            x = max(sr.left(), min(x, sr.right() - self.width()))
            y = max(sr.top(), min(y, sr.bottom() - height))
        self.move(x, y)

    def _populate(self, sessions: list[AiChatSessionDict]) -> None:
        """Fill the list from *sessions*."""
        self._list.clear()
        if not sessions:
            empty = QListWidgetItem("No sessions yet")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(empty)
            return
        for session in sessions:
            is_active = (
                self._active_session_id is not None and session["id"] == self._active_session_id
            )
            row = _SessionRow(session, selected=is_active, parent=self._list)
            item = QListWidgetItem()
            item.setData(_ID_ROLE, session["id"])
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
            if is_active:
                self._list.setCurrentItem(item)
        self._sync_item_widths()

    def _list_content_width(self) -> int:
        """Return list row width inside the viewport, excluding the vertical scrollbar."""
        viewport_w = max(0, self._list.viewport().width())
        bar = self._list.verticalScrollBar()
        if bar.maximum() > 0:
            viewport_w = max(0, viewport_w - bar.sizeHint().width())
        return viewport_w

    def _sync_item_widths(self) -> None:
        """Clamp row size hints to the list viewport so no horizontal scroll appears."""
        content_w = self._list_content_width()
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item is None:
                continue
            row = self._list.itemWidget(item)
            if row is None:
                continue
            row.setFixedWidth(content_w)
            item.setSizeHint(QSize(content_w, row.sizeHint().height()))

    def _apply_filter(self, text: str) -> None:
        """Filter sessions by title substring."""
        needle = text.strip().lower()
        if not needle:
            self._populate(self._sessions)
            return
        filtered = [s for s in self._sessions if needle in s["title"].lower()]
        self._populate(filtered)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Select a session and close."""
        session_id = item.data(_ID_ROLE)
        if not isinstance(session_id, str) or not session_id:
            return
        cb = self._on_select
        self.hide_popup()
        if cb is not None:
            cb(session_id)
