"""Display-only actions flyout for user message config buttons."""

from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import QDateTime, QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget
from shiboken6 import Shiboken

from ui.styling.theme import COLOR_HOVER_BG

_ACTION_LABELS: tuple[str, ...] = ("Edit message", "Fork conversation")

_SHOW_GRACE_MS = 200


class _ActionOptionRow(QWidget):
    """One display-only action row with hover highlight and hand cursor."""

    def __init__(self, label_text: str, parent: QWidget | None = None) -> None:
        """Build a static action label row."""
        super().__init__(parent)
        self.setObjectName("aiUserMessageActionRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hovered = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        label = QLabel(label_text)
        label.setObjectName("aiUserMessageActionLabel")
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(label)

    def enterEvent(self, event) -> None:
        """Track hover for gentle highlight."""
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Clear hover highlight."""
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        """Paint hover wash when the pointer is over the row."""
        if self._hovered:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            wash = QColor(COLOR_HOVER_BG)
            wash.setAlpha(96)
            painter.setBrush(wash)
            painter.drawRoundedRect(self.rect().adjusted(2, 1, -2, -1), 4, 4)
        super().paintEvent(event)


class AiUserMessageActionsPopup(QFrame):
    """Small flyout listing user-message actions (display-only for now)."""

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

    def toggle_for(self, anchor: QWidget) -> None:
        """Hide when already open for *anchor*; otherwise show."""
        if self.isVisible() and self._anchor is anchor:
            self.hide_popup()
            return
        self.show_for(anchor)

    def show_for(self, anchor: QWidget) -> None:
        """Populate static rows and position near *anchor*."""
        app = QGuiApplication.instance()
        if app is not None and self.isVisible():
            app.removeEventFilter(self)
        self._anchor = anchor
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
        if self._anchor is None or not self._anchor.isVisible():
            return False
        local = self._anchor.mapFromGlobal(global_pos)
        return self._anchor.rect().contains(local)

    def _position_near_anchor(self, anchor: QWidget) -> None:
        """Place the flyout below *anchor*, right-aligned; flip above if clipped."""
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
        """Fill the flyout with static display-only action labels."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for label_text in _ACTION_LABELS:
            self._layout.addWidget(_ActionOptionRow(label_text, self))


__all__ = ["AiUserMessageActionsPopup"]
