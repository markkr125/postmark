"""Viewport overlay with an indeterminate line animation during session load."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QPainter, QPaintEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.styling.theme import COLOR_ACCENT, COLOR_BORDER

_DEFAULT_MESSAGE = "Loading conversation\u2026"
_LINE_HEIGHT_PX = 3
_ANIM_INTERVAL_MS = 16
_SEGMENT_FRACTION = 0.35
_PHASE_SPEED = 0.018


class _IndeterminateLine(QWidget):
    """Thin track with a sliding accent segment."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create a fixed-height indeterminate progress line."""
        super().__init__(parent)
        self.setObjectName("aiChatTranscriptLoadingBar")
        self.setFixedHeight(_LINE_HEIGHT_PX)
        self._phase = 0.0
        self._animating = False
        self._timer = QTimer(self)
        self._timer.setInterval(_ANIM_INTERVAL_MS)
        self._timer.timeout.connect(self._advance)

    def start(self) -> None:
        """Begin the sliding segment animation."""
        if self._animating:
            return
        self._animating = True
        self._timer.start()

    def stop(self) -> None:
        """Stop the sliding segment animation."""
        self._animating = False
        self._timer.stop()

    def _advance(self) -> None:
        """Advance one animation frame."""
        self._phase = (self._phase + _PHASE_SPEED) % 1.0
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the track and sliding accent segment."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        height = self.height()
        radius = max(1, height // 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(COLOR_BORDER)
        painter.drawRoundedRect(0, 0, width, height, radius, radius)
        segment_w = max(24, int(width * _SEGMENT_FRACTION))
        travel = max(1, width - segment_w)
        x = int(self._phase * travel)
        painter.setBrush(COLOR_ACCENT)
        painter.drawRoundedRect(x, 0, segment_w, height, radius, radius)


class ChatTranscriptLoadingOverlay(QWidget):
    """Floating session-load indicator anchored to the transcript viewport bottom."""

    _H_MARGIN_PX = 24
    _BOTTOM_MARGIN_PX = 56
    _MAX_WIDTH_PX = 300

    def __init__(self, viewport: QWidget) -> None:
        """Build a viewport child overlay with a line animation and caption."""
        super().__init__(viewport)
        self.setObjectName("aiChatTranscriptLoading")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()
        viewport.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        self._line = _IndeterminateLine(self)
        layout.addWidget(self._line)

        self._label = QLabel(_DEFAULT_MESSAGE)
        self._label.setObjectName("aiChatTranscriptLoadingLabel")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

    def show_loading(self, message: str = _DEFAULT_MESSAGE) -> None:
        """Show the overlay and start the line animation."""
        self._label.setText(message)
        self._line.start()
        self.adjustSize()
        self.show()
        self.raise_()
        self._reposition()

    def hide_loading(self) -> None:
        """Hide the overlay and stop the line animation."""
        self._line.stop()
        self.hide()

    def is_loading_visible(self) -> bool:
        """Return whether the overlay is currently shown."""
        return not self.isHidden()

    def reposition(self, viewport: QWidget | None = None) -> None:
        """Place the overlay near the bottom centre of *viewport*."""
        host = viewport if viewport is not None else self.parentWidget()
        if host is None or self.isHidden():
            return
        vp_w = host.width()
        vp_h = host.height()
        width = min(self._MAX_WIDTH_PX, max(140, vp_w - 2 * self._H_MARGIN_PX))
        self.resize(width, self.sizeHint().height())
        x = max(0, (vp_w - width) // 2)
        y = max(8, vp_h - self.height() - self._BOTTOM_MARGIN_PX)
        self.move(x, y)
        self.raise_()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override]
        """Reposition when the transcript viewport is resized."""
        if (
            watched is self.parentWidget()
            and event.type() == QEvent.Type.Resize
            and not self.isHidden()
        ):
            self._reposition()
        return super().eventFilter(watched, event)

    def _reposition(self) -> None:
        """Reposition using the parent viewport."""
        self.reposition(self.parentWidget())
