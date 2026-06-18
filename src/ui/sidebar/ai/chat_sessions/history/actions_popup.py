"""Actions flyout for session history rows (rename / delete)."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import ClassVar

from PySide6.QtCore import QDateTime, QEvent, QObject, QRect, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget
from shiboken6 import Shiboken

from ui.sidebar.ai.message_bubble.assistant_message.action_option_row import ActionOptionRow

_SHOW_GRACE_MS = 200


class SessionHistoryActionsPopup(QFrame):
    """Small flyout listing rename and delete actions for one session row."""

    hidden = Signal()
    _instance: ClassVar[SessionHistoryActionsPopup | None] = None

    @classmethod
    def instance(cls) -> SessionHistoryActionsPopup:
        """Return the shared session-history actions flyout."""
        if cls._instance is not None and not Shiboken.isValid(cls._instance):
            cls._instance = None
        if cls._instance is None:
            cls._instance = SessionHistoryActionsPopup()
        return cls._instance

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an empty panel; rows are filled in :meth:`show_for_rect`."""
        super().__init__(parent)
        self.setObjectName("aiSessionHistoryActionsPopup")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(0)
        self._anchor_rect: QRect | None = None
        self._opened_at_ms = 0
        self._rename_callback: Callable[[], None] | None = None
        self._delete_callback: Callable[[], None] | None = None
        self._app_filter_installed = False

        self.destroyed.connect(lambda *_args: self._detach_app_event_filter())

    def _detach_app_event_filter(self) -> None:
        """Remove the app-wide click-away filter when it is still installed."""
        if not self._app_filter_installed:
            return
        app = QGuiApplication.instance()
        if app is not None and Shiboken.isValid(self):
            with contextlib.suppress(RuntimeError):
                app.removeEventFilter(self)
        self._app_filter_installed = False

    def show_for_rect(
        self,
        anchor_rect: QRect,
        *,
        on_rename: Callable[[], None] | None = None,
        on_delete: Callable[[], None] | None = None,
    ) -> None:
        """Populate rows and position near *anchor_rect* (global coordinates)."""
        app = QGuiApplication.instance()
        if app is not None and self.isVisible():
            self._detach_app_event_filter()
        self._anchor_rect = anchor_rect
        self._rename_callback = on_rename
        self._delete_callback = on_delete
        self._rebuild()
        self.adjustSize()
        self._position_near_rect(anchor_rect)
        self.show()
        self.raise_()
        self._opened_at_ms = QDateTime.currentMSecsSinceEpoch()
        if app is not None:
            self._detach_app_event_filter()
            app.installEventFilter(self)
            self._app_filter_installed = True

    def hide_popup(self) -> None:
        """Hide the flyout and remove the click-away filter."""
        if not self.isVisible():
            return
        self._detach_app_event_filter()
        self.hide()
        self._anchor_rect = None
        self._rename_callback = None
        self._delete_callback = None
        self.hidden.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Dismiss on Escape."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide_popup()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Close on outside click after grace window."""
        if not isinstance(obj, QObject) or not Shiboken.isValid(self) or not self.isVisible():
            return False
        is_press = event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent)
        past_grace = QDateTime.currentMSecsSinceEpoch() - self._opened_at_ms >= _SHOW_GRACE_MS
        if is_press and past_grace:
            mouse = event
            global_pos = mouse.globalPosition().toPoint()  # type: ignore[attr-defined]
            if self.geometry().contains(global_pos):
                return False
            self.hide_popup()
        return False

    def _position_near_rect(self, anchor_rect: QRect) -> None:
        """Place the flyout just below the ⋯ icon, clamped to the screen."""
        self.adjustSize()
        hint = self.sizeHint()
        x = anchor_rect.right() - hint.width()
        y = anchor_rect.bottom() + 4
        screen = QGuiApplication.screenAt(anchor_rect.bottomLeft())
        if screen is not None:
            sr = screen.availableGeometry()
            if x + hint.width() > sr.right():
                x = sr.right() - hint.width()
            if x < sr.left():
                x = sr.left()
            if y + hint.height() > sr.bottom():
                y = anchor_rect.top() - hint.height() - 4
            y = max(sr.top(), min(y, sr.bottom() - hint.height()))
        self.move(x, y)

    def _rebuild(self) -> None:
        """Fill the flyout with rename and delete action rows."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        rename_row = ActionOptionRow(
            "Rename",
            row_object_name="aiSessionHistoryActionRow",
            label_object_name="aiSessionHistoryActionLabel",
            parent=self,
        )
        rename_row.clicked.connect(self._on_rename)
        self._layout.addWidget(rename_row)
        delete_row = ActionOptionRow(
            "Delete",
            row_object_name="aiSessionHistoryActionRow",
            label_object_name="aiSessionHistoryActionLabel",
            parent=self,
        )
        delete_row.clicked.connect(self._on_delete)
        self._layout.addWidget(delete_row)

    def _on_rename(self) -> None:
        """Run the rename callback and dismiss."""
        callback = self._rename_callback
        self.hide_popup()
        if callback is not None:
            callback()

    def _on_delete(self) -> None:
        """Run the delete callback and dismiss."""
        callback = self._delete_callback
        self.hide_popup()
        if callback is not None:
            callback()


__all__ = ["SessionHistoryActionsPopup"]
