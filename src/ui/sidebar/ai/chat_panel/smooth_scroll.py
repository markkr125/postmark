"""Animated smooth scrolling for the AI chat transcript viewport."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QElapsedTimer, QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QScrollArea

_SCROLL_TICK_MS = 16
_DEFAULT_PIXELS_PER_NOTCH = 180
_TRACKPAD_DELTA_MULTIPLIER = 2.2
_ANIMATION_DURATION_MS = 180
_MAX_QUEUED_DISTANCE_PX = 1400
_SETTLE_THRESHOLD_PX = 1


class SmoothScroller(QObject):
    """Intercept viewport wheel events and animate vertical scrollbar movement."""

    def __init__(
        self,
        scroll_area: QScrollArea,
        *,
        pixels_per_notch: int = _DEFAULT_PIXELS_PER_NOTCH,
        on_animation_started: Callable[[], None] | None = None,
        on_animation_finished: Callable[[], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Attach to *scroll_area* and animate wheel-driven scrollbar changes."""
        super().__init__(parent)
        self._scroll_area = scroll_area
        self._viewport = scroll_area.viewport()
        self._bar = scroll_area.verticalScrollBar()
        self._pixels_per_notch = pixels_per_notch
        self._on_animation_started = on_animation_started
        self._on_animation_finished = on_animation_finished
        self._start_value = 0
        self._target_value = 0
        self._duration_ms = _ANIMATION_DURATION_MS
        self._animating = False
        self._started_cb_fired = False
        self._elapsed = QElapsedTimer()
        self._easing = QEasingCurve(QEasingCurve.Type.OutCubic)

        self._timer = QTimer(self)
        self._timer.setInterval(_SCROLL_TICK_MS)
        self._timer.timeout.connect(self._tick)

        self._viewport.installEventFilter(self)
        self._bar.sliderPressed.connect(self._on_slider_pressed)

    def is_animating(self) -> bool:
        """Return whether a smooth-scroll animation is in progress."""
        return self._animating

    def cancel(self, *, sync_value: int | None = None) -> None:
        """Stop the animation and optionally snap the target to *sync_value*."""
        was_animating = self._animating
        self._timer.stop()
        self._animating = False
        if sync_value is not None:
            self._target_value = sync_value
        else:
            self._target_value = self._bar.value()
        self._started_cb_fired = False
        if was_animating and self._on_animation_finished is not None:
            self._on_animation_finished()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Consume wheel events on the transcript viewport for smooth scrolling."""
        if watched is not self._viewport or event.type() != QEvent.Type.Wheel:
            return False
        wheel = event
        if not isinstance(wheel, QWheelEvent):
            return False
        if self._should_pass_wheel_through(wheel):
            return False
        delta_px = self._wheel_delta_pixels(wheel)
        if delta_px == 0:
            return True
        self._apply_wheel_delta(delta_px)
        return True

    def _should_pass_wheel_through(self, event: QWheelEvent) -> bool:
        """Return whether *event* should use default scroll-area handling."""
        modifiers = event.modifiers()
        return bool(modifiers & Qt.KeyboardModifier.ControlModifier)

    def _wheel_delta_pixels(self, event: QWheelEvent) -> int:
        """Convert a wheel event to a scrollbar delta in pixels."""
        pixel_y = event.pixelDelta().y()
        if pixel_y != 0:
            return -int(round(pixel_y * _TRACKPAD_DELTA_MULTIPLIER))
        angle_y = event.angleDelta().y()
        if angle_y == 0:
            return 0
        return -int(round(angle_y / 120.0 * self._pixels_per_notch))

    def _apply_wheel_delta(self, delta_px: int) -> None:
        """Accumulate *delta_px* toward the animated scroll target."""
        bar = self._bar
        if not self._animating:
            self._start_value = bar.value()
            self._target_value = bar.value()
        bounded_delta = max(
            -_MAX_QUEUED_DISTANCE_PX,
            min(_MAX_QUEUED_DISTANCE_PX, delta_px),
        )
        self._target_value = max(
            bar.minimum(),
            min(bar.maximum(), self._target_value + bounded_delta),
        )
        self._start_value = bar.value()
        self._elapsed.restart()
        if not self._animating:
            self._animating = True
            if not self._started_cb_fired:
                self._started_cb_fired = True
                if self._on_animation_started is not None:
                    self._on_animation_started()
            self._timer.start()

    def _tick(self) -> None:
        """Advance one animation frame toward the accumulated target."""
        bar = self._bar
        current = bar.value()
        target = self._target_value
        if abs(target - current) <= _SETTLE_THRESHOLD_PX:
            if current != target:
                bar.setValue(target)
            self._finish_animation()
            return
        progress = min(1.0, self._elapsed.elapsed() / self._duration_ms)
        eased = self._easing.valueForProgress(progress)
        new_value = int(round(self._start_value + (target - self._start_value) * eased))
        new_value = max(bar.minimum(), min(bar.maximum(), new_value))
        if new_value == current and progress < 1.0:
            direction = 1 if target > current else -1
            new_value = max(bar.minimum(), min(bar.maximum(), current + direction))
        bar.setValue(new_value)
        if progress >= 1.0:
            self._finish_animation()

    def _finish_animation(self) -> None:
        """Stop the timer and notify listeners that scrolling settled."""
        self._timer.stop()
        self._animating = False
        self._started_cb_fired = False
        if self._on_animation_finished is not None:
            self._on_animation_finished()

    def _on_slider_pressed(self) -> None:
        """Yield to manual scrollbar dragging."""
        self.cancel()
