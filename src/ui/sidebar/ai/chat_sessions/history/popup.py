"""Session history popover for the AI assistant flyout header."""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar, cast

from PySide6.QtCore import QDateTime, QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QLineEdit,
    QListView,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import Shiboken

from services.ai.chat.session_service import AiChatSessionDict
from ui.sidebar.ai.chat_sessions.history.delegate import SessionHistoryRowDelegate
from ui.sidebar.ai.chat_sessions.history.model import SessionHistoryListModel
from ui.sidebar.ai.chat_sessions.history.worker import SessionListLoader
from ui.styling.theme import AI_SESSION_HISTORY_POPUP_WIDTH_EM

_SHOW_GRACE_MS = 200
_SEARCH_DEBOUNCE_MS = 200
_POPUP_MIN_HEIGHT_PX = 460
_LIST_MIN_HEIGHT_PX = 380


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
        """Build search field and virtualized session list."""
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

        self._model = SessionHistoryListModel(self)
        self._delegate = SessionHistoryRowDelegate(self)
        self._list = QListView()
        self._list.setObjectName("aiSessionHistoryList")
        self._list.setModel(self._model)
        self._list.setItemDelegate(self._delegate)
        self._list.setMinimumHeight(_LIST_MIN_HEIGHT_PX)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setUniformItemSizes(True)
        self._list.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._list.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self._list.setMouseTracking(True)
        self._list.viewport().setMouseTracking(True)
        layout.addWidget(self._list, 1)

        self._loader = SessionListLoader(self)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(_SEARCH_DEBOUNCE_MS)

        self._active_session_id: str | None = None
        self._on_select: Callable[[str], None] | None = None
        self._anchor: QWidget | None = None
        self._opened_at_ms = 0
        self._load_generation = 0
        self._sync_sessions: list[AiChatSessionDict] | None = None

        self._list.viewport().installEventFilter(self)

        self._search.textChanged.connect(self._schedule_search)
        self._search_timer.timeout.connect(self._run_search)
        self._list.clicked.connect(self._on_row_clicked)
        self._loader.finished.connect(self._on_sessions_loaded)

        def _clear_singleton_ref(*_args: object) -> None:
            if AiSessionHistoryPopup._instance is self:
                AiSessionHistoryPopup._instance = None

        self.destroyed.connect(_clear_singleton_ref)
        self.destroyed.connect(lambda *_args: self._loader.shutdown())

    def open_for(
        self,
        anchor: QWidget,
        on_select: Callable[[str], None],
        *,
        active_session_id: str | None = None,
    ) -> None:
        """Show the popover and load sessions asynchronously."""
        self._begin_open(anchor, on_select, active_session_id=active_session_id, sync_sessions=None)
        self._model.set_loading()
        self._load_generation = self._loader.load("")

    def show_for(
        self,
        anchor: QWidget,
        sessions: list[AiChatSessionDict],
        on_select: Callable[[str], None],
        *,
        active_session_id: str | None = None,
    ) -> None:
        """Populate synchronously (tests and callers with preloaded rows)."""
        self._begin_open(
            anchor,
            on_select,
            active_session_id=active_session_id,
            sync_sessions=list(sessions),
        )
        self._apply_sessions(sessions)

    def hide_popup(self) -> None:
        """Hide and clear callbacks."""
        self._loader.cancel()
        self._search_timer.stop()
        app = QGuiApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        anchor = self._anchor
        self.hide()
        self._anchor = None
        self._active_session_id = None
        self._on_select = None
        self._sync_sessions = None
        if anchor is not None:
            self._set_anchor_checked(anchor, False)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Dismiss on Escape."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide_popup()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Close on outside click after grace window; hand cursor on session rows."""
        if not Shiboken.isValid(self):
            return False
        viewport = self._list.viewport()
        if obj is viewport and Shiboken.isValid(viewport):
            if event.type() == QEvent.Type.MouseMove and isinstance(event, QMouseEvent):
                index = self._list.indexAt(event.position().toPoint())
                if index.isValid() and not self._model.is_placeholder_row(index.row()):
                    viewport.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    viewport.setCursor(Qt.CursorShape.ArrowCursor)
            elif event.type() == QEvent.Type.Leave:
                viewport.setCursor(Qt.CursorShape.ArrowCursor)
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

    def _begin_open(
        self,
        anchor: QWidget,
        on_select: Callable[[str], None],
        *,
        active_session_id: str | None,
        sync_sessions: list[AiChatSessionDict] | None,
    ) -> None:
        """Shared setup for sync and async open paths."""
        app = QGuiApplication.instance()
        if app is not None and self.isVisible():
            app.removeEventFilter(self)
        self._loader.cancel()
        self._search_timer.stop()
        self._anchor = anchor
        self._active_session_id = active_session_id
        self._on_select = on_select
        self._sync_sessions = sync_sessions
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)
        self.setFixedWidth(self._width_for_anchor(anchor))
        self._position_for(anchor)
        self._set_anchor_checked(anchor, True)
        self.show()
        self.raise_()
        self.activateWindow()
        self._search.setFocus()
        self._opened_at_ms = QDateTime.currentMSecsSinceEpoch()
        if app is not None:
            app.installEventFilter(self)

    def _schedule_search(self, _text: str) -> None:
        """Debounce SQL-backed session search while typing."""
        if self._sync_sessions is not None:
            needle = self._search.text().strip().lower()
            if not needle:
                self._apply_sessions(self._sync_sessions)
                return
            filtered = [row for row in self._sync_sessions if needle in row["title"].lower()]
            self._apply_sessions(filtered)
            return
        self._search_timer.start()

    def _run_search(self) -> None:
        """Load sessions matching the current search field."""
        self._model.set_loading()
        self._load_generation = self._loader.load(self._search.text())

    def _on_sessions_loaded(self, generation: int, payload: object) -> None:
        """Apply worker results when the request is still current."""
        if generation != self._load_generation or not self.isVisible():
            return
        sessions = cast(list[AiChatSessionDict], payload) if isinstance(payload, list) else []
        if not sessions:
            self._model.set_empty()
            return
        self._apply_sessions(sessions)

    def _apply_sessions(self, sessions: list[AiChatSessionDict]) -> None:
        """Bind *sessions* to the list model and select the active row."""
        self._model.set_sessions(sessions, active_session_id=self._active_session_id)
        active_row = self._model.active_row()
        if active_row >= 0:
            index = self._model.index(active_row, 0)
            self._list.setCurrentIndex(index)

    def _on_row_clicked(self, index: object) -> None:
        """Select a session and close."""
        from PySide6.QtCore import QModelIndex

        if not isinstance(index, QModelIndex) or not index.isValid():
            return
        if self._model.is_placeholder_row(index.row()):
            return
        session_id = self._model.session_id_at(index.row())
        if not session_id:
            return
        cb = self._on_select
        self.hide_popup()
        if cb is not None:
            cb(session_id)

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


__all__ = ["AiSessionHistoryPopup"]
