"""Session history popover for the AI assistant flyout header."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import ClassVar, cast

from PySide6.QtCore import QDateTime, QEvent, QModelIndex, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QInputDialog,
    QLineEdit,
    QListView,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import Shiboken

from services.ai.chat.session_service import AiChatSessionDict, AiChatSessionService
from ui.sidebar.ai.chat_sessions.history.actions_popup import SessionHistoryActionsPopup
from ui.sidebar.ai.chat_sessions.history.delegate import (
    SessionHistoryRowDelegate,
    session_row_menu_rect,
)
from ui.sidebar.ai.chat_sessions.history.model import FULL_TITLE_ROLE, SessionHistoryListModel
from ui.sidebar.ai.chat_sessions.history.worker import SessionListLoader
from ui.styling.theme import AI_SESSION_HISTORY_POPUP_WIDTH_EM

_SHOW_GRACE_MS = 200
_SEARCH_DEBOUNCE_MS = 200
_RUNNING_SPINNER_MS = 90
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
        self._running_spinner_timer = QTimer(self)
        self._running_spinner_timer.setInterval(_RUNNING_SPINNER_MS)
        self._actions_popup = SessionHistoryActionsPopup.instance()

        self._active_session_id: str | None = None
        self._on_select: Callable[[str], None] | None = None
        self._on_active_session_deleted: Callable[[], None] | None = None
        self._on_sessions_changed: Callable[[], None] | None = None
        self._anchor: QWidget | None = None
        self._opened_at_ms = 0
        self._load_generation = 0
        self._sync_sessions: list[AiChatSessionDict] | None = None
        self._row_activation_generation = 0
        self._menu_open_generation = 0
        self._app_filter_installed = False

        self._list.viewport().installEventFilter(self)

        self._search.textChanged.connect(self._schedule_search)
        self._search_timer.timeout.connect(self._run_search)
        self._running_spinner_timer.timeout.connect(self._tick_running_spinner)
        self._delegate.menu_requested.connect(self._on_menu_requested)
        self._delegate.row_activated.connect(self._on_row_activated)
        self._loader.finished.connect(self._on_sessions_loaded)
        self._actions_popup.hidden.connect(self._on_actions_popup_hidden)

        def _clear_singleton_ref(*_args: object) -> None:
            if AiSessionHistoryPopup._instance is self:
                AiSessionHistoryPopup._instance = None

        def _hide_actions_on_destroy(*_args: object) -> None:
            if Shiboken.isValid(self._actions_popup):
                self._actions_popup.hide_popup()

        self.destroyed.connect(_clear_singleton_ref)
        self.destroyed.connect(lambda *_args: self._loader.shutdown())
        self.destroyed.connect(_hide_actions_on_destroy)
        self.destroyed.connect(lambda *_args: self._detach_app_event_filter())

    def open_for(
        self,
        anchor: QWidget,
        on_select: Callable[[str], None],
        *,
        active_session_id: str | None = None,
        on_active_session_deleted: Callable[[], None] | None = None,
        on_sessions_changed: Callable[[], None] | None = None,
    ) -> None:
        """Show the popover and load sessions asynchronously."""
        self._begin_open(
            anchor,
            on_select,
            active_session_id=active_session_id,
            sync_sessions=None,
            on_active_session_deleted=on_active_session_deleted,
            on_sessions_changed=on_sessions_changed,
        )
        self._model.set_loading()
        self._load_generation = self._loader.load("")

    def show_for(
        self,
        anchor: QWidget,
        sessions: list[AiChatSessionDict],
        on_select: Callable[[str], None],
        *,
        active_session_id: str | None = None,
        on_active_session_deleted: Callable[[], None] | None = None,
        on_sessions_changed: Callable[[], None] | None = None,
    ) -> None:
        """Populate synchronously (tests and callers with preloaded rows)."""
        self._begin_open(
            anchor,
            on_select,
            active_session_id=active_session_id,
            sync_sessions=list(sessions),
            on_active_session_deleted=on_active_session_deleted,
            on_sessions_changed=on_sessions_changed,
        )
        self._apply_sessions(sessions)

    def set_running_session_ids(self, running_ids: frozenset[str]) -> None:
        """Update per-row running indicators while the popover is open."""
        self._model.set_running_session_ids(running_ids)
        self._sync_running_spinner_timer()

    def _sync_running_spinner_timer(self) -> None:
        """Start or stop the running-row spinner animation."""
        if self.isVisible() and self._model.has_running_sessions():
            if not self._running_spinner_timer.isActive():
                self._running_spinner_timer.start()
            return
        self._running_spinner_timer.stop()

    def _tick_running_spinner(self) -> None:
        """Advance the running-row spinner and repaint visible rows."""
        if not self.isVisible() or not self._model.has_running_sessions():
            self._running_spinner_timer.stop()
            return
        self._delegate.advance_spin_frame()
        viewport = self._list.viewport()
        if Shiboken.isValid(viewport):
            viewport.update()

    def hide_popup(self) -> None:
        """Hide and clear callbacks."""
        self._row_activation_generation += 1
        self._menu_open_generation += 1
        if Shiboken.isValid(self._actions_popup):
            self._actions_popup.hide_popup()
        self._delegate.set_menu_open_row(-1)
        self._loader.cancel()
        self._search_timer.stop()
        self._running_spinner_timer.stop()
        self._detach_app_event_filter()
        anchor = self._anchor
        self.hide()
        self._anchor = None
        self._active_session_id = None
        self._on_select = None
        self._on_active_session_deleted = None
        self._on_sessions_changed = None
        self._sync_sessions = None
        if anchor is not None:
            self._set_anchor_checked(anchor, False)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Dismiss on Escape when the actions flyout is not handling it."""
        if event.key() == Qt.Key.Key_Escape:
            actions = self._actions_popup
            if Shiboken.isValid(actions) and actions.isVisible():
                actions.hide_popup()
                return
            self.hide_popup()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Close on outside click after grace window; hand cursor on session rows."""
        if not isinstance(obj, QObject) or not Shiboken.isValid(self) or not self.isVisible():
            return False
        viewport = self._list.viewport()
        if not Shiboken.isValid(viewport):
            return False
        if obj is viewport:
            if event.type() == QEvent.Type.MouseMove and isinstance(event, QMouseEvent):
                index = self._list.indexAt(event.position().toPoint())
                if index.isValid() and not self._model.is_placeholder_row(index.row()):
                    viewport.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    viewport.setCursor(Qt.CursorShape.ArrowCursor)
            elif event.type() == QEvent.Type.Leave:
                viewport.setCursor(Qt.CursorShape.ArrowCursor)
            return False
        is_press = event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent)
        past_grace = QDateTime.currentMSecsSinceEpoch() - self._opened_at_ms >= _SHOW_GRACE_MS
        if is_press and past_grace:
            mouse = event
            global_pos = mouse.globalPosition().toPoint()  # type: ignore[attr-defined]
            if self.geometry().contains(global_pos):
                return False
            actions = self._actions_popup
            if (
                Shiboken.isValid(actions)
                and actions.isVisible()
                and actions.geometry().contains(global_pos)
            ):
                return False
            if self._click_hits_anchor(global_pos):
                return False
            self.hide_popup()
        return False

    def _begin_open(
        self,
        anchor: QWidget,
        on_select: Callable[[str], None],
        *,
        active_session_id: str | None,
        sync_sessions: list[AiChatSessionDict] | None,
        on_active_session_deleted: Callable[[], None] | None = None,
        on_sessions_changed: Callable[[], None] | None = None,
    ) -> None:
        """Shared setup for sync and async open paths."""
        app = QGuiApplication.instance()
        if app is not None and self.isVisible():
            self._detach_app_event_filter()
        if Shiboken.isValid(self._actions_popup):
            self._actions_popup.hide_popup()
        self._delegate.set_menu_open_row(-1)
        self._loader.cancel()
        self._search_timer.stop()
        self._anchor = anchor
        self._active_session_id = active_session_id
        self._on_select = on_select
        self._on_active_session_deleted = on_active_session_deleted
        self._on_sessions_changed = on_sessions_changed
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
            self._detach_app_event_filter()
            app.installEventFilter(self)
            self._app_filter_installed = True

    def _detach_app_event_filter(self) -> None:
        """Remove the app-wide click-away filter when it is still installed."""
        if not self._app_filter_installed:
            return
        app = QGuiApplication.instance()
        if app is not None and Shiboken.isValid(self):
            with contextlib.suppress(RuntimeError):
                app.removeEventFilter(self)
        self._app_filter_installed = False

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
        self._sync_running_spinner_timer()

    def _on_menu_requested(self, index: QModelIndex) -> None:
        """Open the rename/delete flyout for *index* (deferred out of delegate input handling)."""
        if not index.isValid() or self._model.is_placeholder_row(index.row()):
            return
        session_id = self._model.session_id_at(index.row())
        if not session_id:
            return
        title = str(self._model.data(index, FULL_TITLE_ROLE) or "")
        row = index.row()
        self._menu_open_generation += 1
        generation = self._menu_open_generation

        def _open() -> None:
            if generation != self._menu_open_generation or not self.isVisible():
                return
            menu_index = self._model.index(row, 0)
            if not menu_index.isValid():
                return
            row_rect = self._list.visualRect(menu_index)
            menu_rect = session_row_menu_rect(row_rect)
            global_top_left = self._list.viewport().mapToGlobal(menu_rect.topLeft())
            global_rect = QRect(global_top_left, menu_rect.size())
            self._delegate.set_menu_open_row(row)
            viewport = self._list.viewport()
            if Shiboken.isValid(viewport):
                viewport.update()
            self._actions_popup.show_for_rect(
                global_rect,
                on_rename=lambda: self._rename_session(session_id, title),
                on_delete=lambda: self._delete_session(session_id, title),
            )

        QTimer.singleShot(0, _open)

    def _on_actions_popup_hidden(self) -> None:
        """Clear ⋯ highlight when the actions flyout closes."""
        if not Shiboken.isValid(self) or not self.isVisible():
            return
        self._delegate.set_menu_open_row(-1)
        viewport = self._list.viewport()
        if Shiboken.isValid(viewport):
            viewport.update()

    def _on_row_activated(self, index: QModelIndex) -> None:
        """Select a session and close (deferred out of delegate input handling)."""
        if not index.isValid():
            return
        if self._model.is_placeholder_row(index.row()):
            return
        session_id = self._model.session_id_at(index.row())
        if not session_id:
            return
        self._row_activation_generation += 1
        generation = self._row_activation_generation
        QTimer.singleShot(
            0,
            lambda sid=session_id, gen=generation: self._finish_row_activation(sid, gen),
        )

    def _finish_row_activation(self, session_id: str, generation: int) -> None:
        """Hide the popover and load *session_id* after the list finishes the click event."""
        if generation != self._row_activation_generation:
            return
        cb = self._on_select
        self.hide_popup()
        if cb is not None:
            QTimer.singleShot(0, lambda sid=session_id: cb(sid))

    def _rename_session(self, session_id: str, current_title: str) -> None:
        """Rename *session_id* via dialog and refresh the list."""
        new_title, accepted = QInputDialog.getText(
            self,
            "Rename session",
            "Session name:",
            text=current_title,
        )
        if not accepted:
            return
        cleaned = new_title.strip()
        if not cleaned or cleaned == current_title:
            return
        AiChatSessionService.rename_session(session_id, cleaned)
        if session_id in {row["id"] for row in self._sync_sessions or []}:
            for row in self._sync_sessions or []:
                if row["id"] == session_id:
                    row["title"] = cleaned
        self._reload_sessions()
        changed = self._on_sessions_changed
        if changed is not None:
            changed()

    def _delete_session(self, session_id: str, title: str) -> None:
        """Delete *session_id* after confirmation and refresh the list."""
        reply = QMessageBox.question(
            self,
            "Delete session",
            f'Delete "{title}"? This cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        AiChatSessionService.delete_session(session_id)
        if session_id == self._active_session_id:
            deleted_cb = self._on_active_session_deleted
            if deleted_cb is not None:
                deleted_cb()
            self._active_session_id = None
        if self._sync_sessions is not None:
            self._sync_sessions = [row for row in self._sync_sessions if row["id"] != session_id]
        self._reload_sessions()

    def _reload_sessions(self) -> None:
        """Refresh rows after rename or delete."""
        if self._sync_sessions is not None:
            needle = self._search.text().strip().lower()
            if needle:
                filtered = [row for row in self._sync_sessions if needle in row["title"].lower()]
                self._apply_sessions(filtered)
            else:
                self._apply_sessions(self._sync_sessions)
            return
        self._model.set_loading()
        self._load_generation = self._loader.load(self._search.text())

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
