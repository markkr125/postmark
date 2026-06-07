"""Session history popover for the AI assistant flyout header."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import ClassVar

from PySide6.QtCore import QDateTime, QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import Shiboken

from services.ai.chat.session_service import AiChatSessionDict
from ui.sidebar.ai.chat_sessions.time_format import format_relative_time

_ID_ROLE = Qt.ItemDataRole.UserRole + 1
_SHOW_GRACE_MS = 200


class _SessionRow(QWidget):
    """One session row with title and relative time."""

    def __init__(
        self,
        session: AiChatSessionDict,
        parent: QWidget | None = None,
    ) -> None:
        """Build a row for *session*."""
        super().__init__(parent)
        self.setObjectName("aiSessionHistoryRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        title = QLabel(session["title"])
        title.setObjectName("aiSessionHistoryTitle")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(title, 1)

        updated = datetime.fromisoformat(session["updated_at"])
        time_lbl = QLabel(format_relative_time(updated))
        time_lbl.setObjectName("aiSessionHistoryTime")
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(time_lbl)


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
        self.setFixedWidth(320)
        self.setMinimumHeight(240)

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
        layout.addWidget(self._list, 1)

        self._sessions: list[AiChatSessionDict] = []
        self._on_select: Callable[[str], None] | None = None
        self._anchor: QWidget | None = None
        self._opened_at_ms = 0

        self._search.textChanged.connect(self._apply_filter)
        self._list.itemClicked.connect(self._on_item_clicked)

        def _clear_singleton_ref(*_args: object) -> None:
            if AiSessionHistoryPopup._instance is self:
                AiSessionHistoryPopup._instance = None

        self.destroyed.connect(_clear_singleton_ref)

    def show_for(
        self,
        anchor: QWidget,
        sessions: list[AiChatSessionDict],
        on_select: Callable[[str], None],
    ) -> None:
        """Populate and show anchored to *anchor*."""
        app = QGuiApplication.instance()
        if app is not None and self.isVisible():
            app.removeEventFilter(self)
        self._anchor = anchor
        self._sessions = list(sessions)
        self._on_select = on_select
        self._search.clear()
        self._populate(self._sessions)
        self._position_for(anchor)
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
        self.hide()
        self._anchor = None
        self._on_select = None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Dismiss on Escape."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide_popup()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Close on outside click after grace window."""
        is_press = event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent)
        past_grace = QDateTime.currentMSecsSinceEpoch() - self._opened_at_ms >= _SHOW_GRACE_MS
        if is_press and past_grace and self.isVisible():
            mouse = event
            global_pos = mouse.globalPosition().toPoint()  # type: ignore[attr-defined]
            if self.geometry().contains(global_pos):
                return super().eventFilter(obj, event)
            if self._hits_anchor(global_pos):
                self.hide_popup()
                return super().eventFilter(obj, event)
            self.hide_popup()
        return super().eventFilter(obj, event)

    def _hits_anchor(self, global_pos: QPoint) -> bool:
        if self._anchor is None or not self._anchor.isVisible():
            return False
        local = self._anchor.mapFromGlobal(global_pos)
        return self._anchor.rect().contains(local)

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
            row = _SessionRow(session, parent=self._list)
            item = QListWidgetItem()
            item.setData(_ID_ROLE, session["id"])
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)

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
