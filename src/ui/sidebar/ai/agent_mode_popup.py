"""Cursor-style agent mode picker for the AI chat composer."""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from PySide6.QtCore import QDateTime, QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import Shiboken

from ui.styling.icons import phi
from ui.styling.theme import COLOR_HOVER_BG

AGENT_MODES: tuple[tuple[str, str, str], ...] = (
    ("Agent", "agent", "infinity"),
    ("Ask", "ask", "chat-circle"),
    ("Plan", "plan", "map-trifold"),
)

_MODE_LABELS: dict[str, str] = {value: label for label, value, _icon in AGENT_MODES}
_MODE_ICONS: dict[str, str] = {value: icon for _label, value, icon in AGENT_MODES}

_SHOW_GRACE_MS = 200


class _ModeOptionRow(QWidget):
    """One mode row with icon, label, and optional checkmark."""

    picked = Signal(str)

    def __init__(
        self,
        label: str,
        icon_name: str,
        value: str,
        *,
        checked: bool,
        parent: QWidget | None = None,
    ) -> None:
        """Build a clickable mode row."""
        super().__init__(parent)
        self._value = value
        self.setObjectName("aiAgentModeOption")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hovered = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(phi(icon_name, size=14).pixmap(14, 14))
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(icon_lbl, 0)

        text = QLabel(label)
        text.setObjectName("aiAgentModeOptionLabel")
        text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(text, 1)

        mark = QLabel("✓" if checked else "")
        mark.setObjectName("aiAgentModeCheck")
        mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(mark, 0)

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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit ``picked`` with the mode value on left click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self._value)
            event.accept()
            return
        super().mousePressEvent(event)


class AiAgentModePopup(QFrame):
    """Small flyout listing Agent / Ask / Plan."""

    mode_picked = Signal(str)
    hidden = Signal()
    _instance: ClassVar[AiAgentModePopup | None] = None

    @classmethod
    def instance(cls) -> AiAgentModePopup:
        """Return the shared mode picker."""
        if cls._instance is not None and not Shiboken.isValid(cls._instance):
            cls._instance = None
        if cls._instance is None:
            cls._instance = AiAgentModePopup()
        return cls._instance

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an empty panel; rows are filled in :meth:`show_for`."""
        super().__init__(parent)
        self.setObjectName("aiAgentModePopup")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(0)
        self._on_pick: Callable[[str], None] | None = None
        self._anchor: QWidget | None = None
        self._opened_at_ms = 0

    def show_for(
        self,
        anchor: QWidget,
        current: str,
        on_pick: Callable[[str], None],
    ) -> None:
        """Populate and show above *anchor*."""
        app = QGuiApplication.instance()
        if app is not None and self.isVisible():
            app.removeEventFilter(self)
        self._anchor = anchor
        self._on_pick = on_pick
        self._rebuild(current)
        self.adjustSize()
        self._position_above(anchor)
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
        self._on_pick = None
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
        """True when *global_pos* is over the mode pill that opened this flyout."""
        if self._anchor is None or not self._anchor.isVisible():
            return False
        local = self._anchor.mapFromGlobal(global_pos)
        return self._anchor.rect().contains(local)

    def _position_above(self, anchor: QWidget) -> None:
        """Place the flyout above *anchor*, left-aligned."""
        gap = 4
        panel_h = self.height()
        panel_w = self.width()
        top_left = anchor.mapToGlobal(QPoint(0, 0))
        x = top_left.x()
        y = top_left.y() - panel_h - gap
        screen = QGuiApplication.screenAt(top_left) or QGuiApplication.primaryScreen()
        sr = screen.availableGeometry() if screen else None
        if sr is not None:
            x = max(sr.left(), min(x, sr.right() - panel_w))
            y = max(sr.top(), min(y, sr.bottom() - panel_h))
        self.move(x, y)

    def _rebuild(self, current: str) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for label, value, icon_name in AGENT_MODES:
            row = _ModeOptionRow(label, icon_name, value, checked=value == current, parent=self)

            def _handler(picked: str = value) -> None:
                if self._on_pick is not None:
                    self._on_pick(picked)
                self.hide_popup()
                self.mode_picked.emit(picked)

            row.picked.connect(_handler)
            self._layout.addWidget(row)


class AgentModeButton(QFrame):
    """Compact pill showing the current agent mode (Cursor composer style)."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build with default mode ``agent``."""
        super().__init__(parent)
        self.setObjectName("aiChatModeButton")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mode = "agent"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 6, 3)
        layout.setSpacing(4)

        self._icon = QLabel()
        self._icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._icon, 0)

        self._label = QLabel("Agent")
        self._label.setObjectName("aiChatModeButtonLabel")
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._label, 0)

        caret = QLabel()
        caret.setPixmap(phi("caret-down", size=10).pixmap(10, 10))
        caret.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(caret, 0)

        self.set_mode("agent")

    def mode(self) -> str:
        """Return the selected mode value."""
        return self._mode

    def set_mode(self, mode: str) -> None:
        """Update icon and label for *mode*."""
        if mode not in _MODE_LABELS:
            mode = "agent"
        self._mode = mode
        self._label.setText(_MODE_LABELS[mode])
        icon_name = _MODE_ICONS.get(mode, "infinity")
        self._icon.setPixmap(phi(icon_name, size=14).pixmap(14, 14))
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit ``clicked`` on left press."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


__all__ = [
    "AGENT_MODES",
    "AgentModeButton",
    "AiAgentModePopup",
]
