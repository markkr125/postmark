"""Circular context-usage ring button for the AI chat composer."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from services.ai.provider_catalog import format_run_context_tokens
from ui.styling.theme import COLOR_ACCENT, COLOR_BORDER
from ui.styling.theme_manager import ThemeManager


def _install_ring_theme_hook(widget: ContextUsageRingButton) -> None:
    """Connect ``ThemeManager.theme_changed`` so the ring repaints on theme flips."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    for child in app.children():
        if isinstance(child, ThemeManager):
            child.theme_changed.connect(widget.update)


class ContextUsageRingButton(QWidget):
    """28x28 ring showing context fill level; click opens the breakdown popover."""

    context_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an empty ring with a dash tooltip."""
        super().__init__(parent)
        self.setObjectName("aiChatContextRing")
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Context usage")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._used_tokens = 0
        self._total_tokens = 0
        self.setToolTip("Context: —")
        _install_ring_theme_hook(self)

    def fill_fraction(self) -> float:
        """Return ``used / total`` clamped to ``[0, 1]``."""
        if self._total_tokens <= 0:
            return 0.0
        return min(1.0, max(0.0, self._used_tokens / self._total_tokens))

    def used_tokens(self) -> int:
        """Return the last applied used-token count."""
        return self._used_tokens

    def total_tokens(self) -> int:
        """Return the last applied context-window size."""
        return self._total_tokens

    def set_usage(self, used_tokens: int, total_tokens: int) -> None:
        """Update fill level and tooltip."""
        self._used_tokens = max(0, used_tokens)
        self._total_tokens = max(0, total_tokens)
        if total_tokens <= 0:
            self.setToolTip("Context: —")
        else:
            pct = min(100, round(100 * self._used_tokens / total_tokens))
            used = format_run_context_tokens(self._used_tokens)
            total = format_run_context_tokens(total_tokens)
            self.setToolTip(f"Context: {pct}% ({used}/{total})")
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint a muted track circle and accent arc for the fill level."""
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(3, 3, -3, -3)
        track = QPen(QColor(COLOR_BORDER), 2.5)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)
        fraction = self.fill_fraction()
        if fraction > 0:
            arc_pen = QPen(QColor(COLOR_ACCENT), 2.5)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc_pen)
            span = int(-360 * 16 * fraction)
            painter.drawArc(rect, 90 * 16, span)
        painter.end()

    def click(self) -> None:
        """Emit the click signal for tests and keyboard-like callers."""
        self.context_requested.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit ``context_requested`` on left click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.click()
            event.accept()
            return
        super().mousePressEvent(event)
