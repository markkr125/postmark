"""Actions flyout for assistant message footer menus."""

from __future__ import annotations

from typing import ClassVar

from collections.abc import Callable

from PySide6.QtCore import QDateTime, QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget
from shiboken6 import Shiboken

from ui.sidebar.ai.message_bubble.assistant_message.action_option_row import ActionOptionRow
from ui.sidebar.ai.message_bubble.assistant_message.action_popup_anchor import (
    AnchorFollowingActionsPopupMixin,
)

_SHOW_GRACE_MS = 200


class AiAssistantMessageActionsPopup(AnchorFollowingActionsPopupMixin, QFrame):
    """Small flyout listing assistant-message actions."""

    hidden = Signal()
    _instance: ClassVar[AiAssistantMessageActionsPopup | None] = None

    @classmethod
    def instance(cls) -> AiAssistantMessageActionsPopup:
        """Return the shared assistant-message actions flyout."""
        if cls._instance is not None and not Shiboken.isValid(cls._instance):
            cls._instance = None
        if cls._instance is None:
            cls._instance = AiAssistantMessageActionsPopup()
        return cls._instance

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an empty panel; rows are filled in :meth:`show_for`."""
        super().__init__(parent)
        self.setObjectName("aiAssistantMessageActionsPopup")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(0)
        self._anchor: QWidget | None = None
        self._init_anchor_popup_tracking_state()
        self._opened_at_ms = 0
        self._fork_enabled = True
        self._fork_callback: Callable[[], None] | None = None
        self._copy_callback: Callable[[], None] | None = None

    def toggle_for(
        self,
        anchor: QWidget,
        *,
        fork_enabled: bool = True,
        on_fork: Callable[[], None] | None = None,
        on_copy: Callable[[], None] | None = None,
    ) -> None:
        """Hide when already open for *anchor*; otherwise show."""
        if self.isVisible() and self._anchor is anchor:
            self.hide_popup()
            return
        self.show_for(
            anchor,
            fork_enabled=fork_enabled,
            on_fork=on_fork,
            on_copy=on_copy,
        )

    def show_for(
        self,
        anchor: QWidget,
        *,
        fork_enabled: bool = True,
        on_fork: Callable[[], None] | None = None,
        on_copy: Callable[[], None] | None = None,
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
        self._copy_callback = on_copy
        self._rebuild()
        self.adjustSize()
        self._position_near_anchor(anchor)
        self.show()
        self.raise_()
        self._opened_at_ms = QDateTime.currentMSecsSinceEpoch()
        self._attach_anchor_scroll_tracking()
        if app is not None:
            app.installEventFilter(self)

    def hide_popup(self) -> None:
        """Hide the flyout and remove the click-away filter."""
        if not self.isVisible():
            return
        self._teardown_anchor_popup_tracking()
        app = QGuiApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.hide()
        self._anchor = None
        self._fork_callback = None
        self._copy_callback = None
        self.hidden.emit()

    def is_open_for(self, anchor: QWidget) -> bool:
        """Return whether this flyout is visible and anchored to *anchor*."""
        return self.isVisible() and self._anchor is anchor

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Dismiss on Escape."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide_popup()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Close on outside click; reposition when the anchor window moves."""
        etype = event.type()
        if self.isVisible() and etype in (QEvent.Type.Move, QEvent.Type.Resize):
            anchor = self._anchor
            if anchor is not None and Shiboken.isValid(anchor):
                window = anchor.window()
                if obj is window:
                    self._schedule_popup_position_sync()
                    return super().eventFilter(obj, event)
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
        """True when *global_pos* is over the menu button that opened this flyout."""
        anchor = self._anchor
        if anchor is None or not Shiboken.isValid(anchor) or not anchor.isVisible():
            return False
        local = anchor.mapFromGlobal(global_pos)
        return anchor.rect().contains(local)

    def _rebuild(self) -> None:
        """Fill the flyout with copy and fork action rows."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        copy_row = ActionOptionRow(
            "Copy message",
            row_object_name="aiAssistantMessageActionRow",
            label_object_name="aiAssistantMessageActionLabel",
            parent=self,
        )
        copy_row.clicked.connect(self._on_copy)
        self._layout.addWidget(copy_row)
        fork_row = ActionOptionRow(
            "Fork chat",
            row_object_name="aiAssistantMessageActionRow",
            label_object_name="aiAssistantMessageActionLabel",
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

    def _on_copy(self) -> None:
        """Run the copy callback and dismiss."""
        callback = self._copy_callback
        self.hide_popup()
        if callback is not None:
            callback()


__all__ = ["AiAssistantMessageActionsPopup"]
