"""Actions flyout for user message footer menus."""

from __future__ import annotations

from typing import ClassVar

from collections.abc import Callable

from PySide6.QtCore import QDateTime, QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget
from shiboken6 import Shiboken

from ui.sidebar.ai.message_bubble.assistant_message.action_option_row import ActionOptionRow

_SHOW_GRACE_MS = 200


class AiUserMessageActionsPopup(QFrame):
    """Small flyout listing user-message actions."""

    hidden = Signal()
    _instance: ClassVar[AiUserMessageActionsPopup | None] = None

    @classmethod
    def instance(cls) -> AiUserMessageActionsPopup:
        """Return the shared user-message actions flyout."""
        if cls._instance is not None and not Shiboken.isValid(cls._instance):
            cls._instance = None
        if cls._instance is None:
            cls._instance = AiUserMessageActionsPopup()
        return cls._instance

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an empty panel; rows are filled in :meth:`show_for`."""
        super().__init__(parent)
        self.setObjectName("aiUserMessageActionsPopup")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(0)
        self._anchor: QWidget | None = None
        self._opened_at_ms = 0
        self._fork_enabled = True
        self._fork_callback: Callable[[], None] | None = None

    def toggle_for(
        self,
        anchor: QWidget,
        *,
        fork_enabled: bool = True,
        on_fork: Callable[[], None] | None = None,
    ) -> None:
        """Hide when already open for *anchor*; otherwise show."""
        if self.isVisible() and self._anchor is anchor:
            self.hide_popup()
            return
        self.show_for(anchor, fork_enabled=fork_enabled, on_fork=on_fork)

    def show_for(
        self,
        anchor: QWidget,
        *,
        fork_enabled: bool = True,
        on_fork: Callable[[], None] | None = None,
    ) -> None:
        """Populate rows and position near *anchor*."""
        if not Shiboken.isValid(anchor):
            return
        app = QGuiApplication.instance()
        if app is not None and self.isVisible():
            app.removeEventFilter(self)
        self._anchor = anchor
        self._fork_enabled = fork_enabled
        self._fork_callback = on_fork
        self._rebuild()
        self.adjustSize()
        self._position_near_anchor(anchor)
        self.show()
        self.raise_()
        self._opened_at_ms = QDateTime.currentMSecsSinceEpoch()
        if app is not None:
            app.installEventFilter(self)

    def hide_popup(self) -> None:
        """Hide the flyout and remove the click-away filter."""
        if not self.isVisible():
            return
        app = QGuiApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.hide()
        self._anchor = None
        self._fork_callback = None
        self.hidden.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Dismiss on Escape."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide_popup()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Close on a mouse press outside the flyout after the grace window."""
        is_press = event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent)
        past_grace = QDateTime.currentMSecsSinceEpoch() - self._opened_at_ms >= _SHOW_GRACE_MS
        if is_press and past_grace and self.isVisible():
            mouse = event
            global_pos = mouse.globalPosition().toPoint()  # type: ignore[attr-defined]
            if self.geometry().contains(global_pos):
                return super().eventFilter(obj, event)
            if self._hits_anchor(global_pos):
                return super().eventFilter(obj, event)
            self.hide_popup()
        return super().eventFilter(obj, event)

    def _hits_anchor(self, global_pos: QPoint) -> bool:
        """True when *global_pos* is over the config button that opened this flyout."""
        anchor = self._anchor
        if anchor is None or not Shiboken.isValid(anchor) or not anchor.isVisible():
            return False
        local = anchor.mapFromGlobal(global_pos)
        return anchor.rect().contains(local)

    def _position_near_anchor(self, anchor: QWidget) -> None:
        """Place the flyout below *anchor*, right-aligned; flip above if clipped."""
        if not Shiboken.isValid(anchor):
            return
        gap = 4
        panel_h = self.height()
        panel_w = self.width()
        bottom_right = anchor.mapToGlobal(anchor.rect().bottomRight())
        x = bottom_right.x() - panel_w
        y = bottom_right.y() + gap
        screen = QGuiApplication.screenAt(bottom_right) or QGuiApplication.primaryScreen()
        sr = screen.availableGeometry() if screen else None
        if sr is not None:
            x = max(sr.left(), min(x, sr.right() - panel_w))
            if y + panel_h > sr.bottom():
                top_right = anchor.mapToGlobal(anchor.rect().topRight())
                y = top_right.y() - panel_h - gap
            y = max(sr.top(), min(y, sr.bottom() - panel_h))
        self.move(x, y)

    def _rebuild(self) -> None:
        """Fill the flyout with edit (display-only) and fork action rows."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        edit_row = ActionOptionRow(
            "Edit message",
            row_object_name="aiUserMessageActionRow",
            label_object_name="aiUserMessageActionLabel",
            parent=self,
        )
        edit_row.setEnabled(False)
        self._layout.addWidget(edit_row)
        fork_row = ActionOptionRow(
            "Fork chat",
            row_object_name="aiUserMessageActionRow",
            label_object_name="aiUserMessageActionLabel",
            parent=self,
        )
        fork_row.setEnabled(self._fork_enabled)
        fork_row.clicked.connect(self._on_fork)
        self._layout.addWidget(fork_row)

    def _on_fork(self) -> None:
        """Run the fork callback and dismiss."""
        callback = self._fork_callback
        self.hide_popup()
        if callback is not None:
            callback()


__all__ = ["AiUserMessageActionsPopup"]
