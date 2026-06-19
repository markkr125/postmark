"""List model for the AI session history popover."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QPersistentModelIndex,
    QObject,
    Qt,
)

from services.ai.chat.session_service import AiChatSessionDict
from ui.sidebar.ai.chat_sessions.time_format import format_relative_time

SESSION_ID_ROLE = Qt.ItemDataRole.UserRole + 1
RELATIVE_TIME_ROLE = Qt.ItemDataRole.UserRole + 2
ACTIVE_SESSION_ROLE = Qt.ItemDataRole.UserRole + 3
FULL_TITLE_ROLE = Qt.ItemDataRole.UserRole + 4
RUNNING_ROLE = Qt.ItemDataRole.UserRole + 5

_LOADING_ROW_ID = "__loading__"
_EMPTY_ROW_ID = "__empty__"


class SessionHistoryListModel(QAbstractListModel):
    """Virtualized session rows for :class:`AiSessionHistoryPopup`."""

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialise an empty session list model."""
        super().__init__(parent)
        self._sessions: list[AiChatSessionDict] = []
        self._active_session_id: str | None = None
        self._running_session_ids: frozenset[str] = frozenset()
        self._placeholder: str | None = None

    def rowCount(
        self,
        parent: QModelIndex | QPersistentModelIndex | None = None,
    ) -> int:
        """Return the number of rows (placeholder or session count)."""
        if parent is None:
            parent = QModelIndex()
        if parent.isValid():
            return 0
        if self._placeholder is not None:
            return 1
        return len(self._sessions)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object | None:
        """Return display data for *index*."""
        if not index.isValid():
            return None
        if self._placeholder is not None:
            if role in {Qt.ItemDataRole.DisplayRole, FULL_TITLE_ROLE}:
                return self._placeholder
            if role == SESSION_ID_ROLE:
                return _LOADING_ROW_ID if self._placeholder == "Loading…" else _EMPTY_ROW_ID
            return None
        row = index.row()
        if row < 0 or row >= len(self._sessions):
            return None
        session = self._sessions[row]
        if role == Qt.ItemDataRole.DisplayRole:
            return session.get("title") or ""
        if role == Qt.ItemDataRole.ToolTipRole:
            return session.get("title") or ""
        if role == SESSION_ID_ROLE:
            return session["id"]
        if role == FULL_TITLE_ROLE:
            return session.get("title") or ""
        if role == RELATIVE_TIME_ROLE:
            updated_raw = session.get("updated_at")
            if not isinstance(updated_raw, str) or not updated_raw:
                return ""
            return format_relative_time(datetime.fromisoformat(updated_raw))
        if role == RUNNING_ROLE:
            return session["id"] in self._running_session_ids
        if role == ACTIVE_SESSION_ROLE:
            active_id = self._active_session_id
            return active_id is not None and session["id"] == active_id
        return None

    def set_running_session_ids(self, running_ids: frozenset[str]) -> None:
        """Refresh which rows show the running spinner."""
        self._running_session_ids = frozenset(running_ids)
        if self._placeholder is not None or not self._sessions:
            return
        top_left = self.index(0, 0)
        bottom_right = self.index(len(self._sessions) - 1, 0)
        self.dataChanged.emit(
            top_left,
            bottom_right,
            [RELATIVE_TIME_ROLE, RUNNING_ROLE],
        )

    def has_running_sessions(self) -> bool:
        """Return whether any visible row has an in-flight agent run."""
        if self._placeholder is not None or not self._sessions:
            return False
        return any(session["id"] in self._running_session_ids for session in self._sessions)

    def set_loading(self) -> None:
        """Show a single non-selectable loading row."""
        self.beginResetModel()
        self._sessions = []
        self._placeholder = "Loading…"
        self.endResetModel()

    def set_empty(self, message: str = "No sessions yet") -> None:
        """Show a single non-selectable empty-state row."""
        self.beginResetModel()
        self._sessions = []
        self._placeholder = message
        self.endResetModel()

    def set_sessions(
        self,
        sessions: list[AiChatSessionDict],
        *,
        active_session_id: str | None,
    ) -> None:
        """Replace all session rows."""
        self.beginResetModel()
        self._sessions = list(sessions)
        self._active_session_id = active_session_id
        self._placeholder = None
        self.endResetModel()

    def session_id_at(self, row: int) -> str | None:
        """Return the session id at *row*, or ``None`` for placeholders."""
        if self._placeholder is not None or row < 0 or row >= len(self._sessions):
            return None
        return self._sessions[row]["id"]

    def active_row(self) -> int:
        """Return the row index of the active session, or ``-1``."""
        if self._active_session_id is None or self._placeholder is not None:
            return -1
        for index, session in enumerate(self._sessions):
            if session["id"] == self._active_session_id:
                return index
        return -1

    def is_placeholder_row(self, row: int) -> bool:
        """Return whether *row* is a loading or empty placeholder."""
        return self._placeholder is not None and row == 0


__all__ = [
    "ACTIVE_SESSION_ROLE",
    "FULL_TITLE_ROLE",
    "RELATIVE_TIME_ROLE",
    "RUNNING_ROLE",
    "SESSION_ID_ROLE",
    "SessionHistoryListModel",
]
