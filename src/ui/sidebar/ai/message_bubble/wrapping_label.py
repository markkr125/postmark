"""Word-wrapped QLabel used in chat message rows."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QSize, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QSizePolicy, QWidget

_QWIDGET_MAX_HEIGHT = 16777215


def forward_wheel_to_ancestor_scroll_area(widget: QWidget, event: QWheelEvent) -> bool:
    """Forward wheel input to the nearest ancestor ``QScrollArea`` viewport."""
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QScrollArea):
            viewport = parent.viewport()
            local = viewport.mapFromGlobal(event.globalPosition().toPoint())
            forwarded = QWheelEvent(
                QPointF(local),
                event.globalPosition(),
                event.pixelDelta(),
                event.angleDelta(),
                event.buttons(),
                event.modifiers(),
                event.phase(),
                event.inverted(),
            )
            QApplication.sendEvent(viewport, forwarded)
            event.accept()
            return True
        parent = parent.parentWidget()
    return False


class _WrappingLabel(QLabel):
    """Word-wrapped label that reports height-for-width to the layout."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        """Configure wrap, expansion, and selectable text."""
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._measured_text_width = -1
        self._measured_height: int | None = None
        self._reflow_deferred = False
        self._reflow_flush_pending = False

    def _invalidate_measured_height(self) -> None:
        """Drop cached wrap height so the next measure recomputes."""
        self._measured_text_width = -1
        self._measured_height = None

    def _text_width_for_widget_width(self, width: int) -> int:
        """Return the inner text column width for a proposed widget width."""
        margins = self.contentsMargins()
        return max(1, width - margins.left() - margins.right())

    def _measure_wrapped_height(self, text_width: int) -> int:
        """Measure wrapped height at *text_width*."""
        rect = self.fontMetrics().boundingRect(
            0,
            0,
            text_width,
            0,
            Qt.TextFlag.TextWordWrap,
            self.text(),
        )
        margins = self.contentsMargins()
        return rect.height() + margins.top() + margins.bottom() + 2

    def set_reflow_deferred(self, deferred: bool) -> None:
        """Skip width reflow during pane resize when the row is off-screen."""
        if self._reflow_deferred == deferred:
            return
        self._reflow_deferred = deferred
        if not deferred and self._reflow_flush_pending:
            self.flush_deferred_reflow()

    def flush_deferred_reflow(self) -> None:
        """Re-run layout after a deferred resize drag ends or the row becomes visible."""
        if not self._reflow_flush_pending and not self._reflow_deferred:
            return
        self._reflow_deferred = False
        self._reflow_flush_pending = False
        self._invalidate_measured_height()
        self.updateGeometry()

    def hasHeightForWidth(self) -> bool:
        """Allow the layout to size this label from the available width."""
        return True

    def _clamp_to_max_height(self, height: int) -> int:
        """Return *height* capped by ``maximumHeight`` when the label is clamped."""
        max_h = self.maximumHeight()
        if 0 < max_h < _QWIDGET_MAX_HEIGHT:
            return min(height, max_h)
        return height

    def sizeHint(self) -> QSize:
        """Return a size hint that respects an active ``maximumHeight`` clamp."""
        hint = super().sizeHint()
        return QSize(hint.width(), self._clamp_to_max_height(hint.height()))

    def _cached_height_for_text_width(self, text_width: int) -> int:
        """Return wrap height for *text_width*, reusing the last measure when unchanged."""
        if self._measured_text_width == text_width and self._measured_height is not None:
            return self._measured_height
        height = self._measure_wrapped_height(text_width)
        self._measured_text_width = text_width
        self._measured_height = height
        return height

    def heightForWidth(self, width: int) -> int:
        """Return wrapped text height for *width*."""
        if width <= 0:
            return self.sizeHint().height()
        if self._reflow_deferred and self._measured_height is not None:
            return self._measured_height
        text_width = self._text_width_for_widget_width(width)
        if self._reflow_deferred:
            self._reflow_flush_pending = True
            return max(1, self.height())
        return self._clamp_to_max_height(self._cached_height_for_text_width(text_width))

    def setText(self, text: str) -> None:
        """Replace text and invalidate cached height."""
        self._invalidate_measured_height()
        super().setText(text)
        self.updateGeometry()

    def changeEvent(self, event: QEvent) -> None:
        """Invalidate cached height when the label font changes."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._invalidate_measured_height()

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Route wheel input to the transcript scroll area instead of the label."""
        if forward_wheel_to_ancestor_scroll_area(self, event):
            return
        super().wheelEvent(event)
