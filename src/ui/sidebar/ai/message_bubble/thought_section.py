"""Collapsible thinking block for assistant message rows."""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, Qt, Signal, QSize
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QFrame, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ui.sidebar.ai.message_bubble.wrapping_label import _WrappingLabel, _QWIDGET_MAX_HEIGHT
from ui.styling.icons import phi

_THOUGHT_TEXT_INDENT_PX = 14


class ThoughtSection(QFrame):
    """Collapsible internal-reasoning block above the assistant answer."""

    layout_height_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build a toggle header and wrapped thinking body."""
        super().__init__(parent)
        self.setObjectName("aiChatThoughtBlock")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(2)

        self._header = QPushButton()
        self._header.setObjectName("aiChatThoughtToggle")
        self._header.setFlat(True)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.clicked.connect(self._toggle)
        layout.addWidget(self._header)

        self._label = _WrappingLabel()
        self._label.setObjectName("aiChatThoughtText")
        self._label.setContentsMargins(_THOUGHT_TEXT_INDENT_PX, 0, 0, 0)
        layout.addWidget(self._label)

        self._expanded = False
        self._duration_seconds: int | None = None
        self._timer = QElapsedTimer()
        self._header_elapsed_shown = -1
        self._stream_height_floor = 0
        self._stream_floor_width = 0
        self._refresh_header()

    def has_text(self) -> bool:
        """Return whether any thinking text is present."""
        return bool(self._label.text().strip())

    def text(self) -> str:
        """Return the accumulated thinking text."""
        return self._label.text()

    def append_text(self, text: str, *, defer_geometry: bool = False) -> None:
        """Append streaming thinking text."""
        if not text:
            return
        if not self._timer.isValid():
            self._timer.start()
        self._label.append_text(text, defer_geometry=defer_geometry)
        has_text = bool(self._label.text().strip())
        self.setVisible(has_text)
        self._header.setVisible(has_text)
        if has_text and self._duration_seconds is None:
            self._expanded = True
        self._label.setVisible(has_text and self._expanded)
        self._refresh_header(update_elapsed=not defer_geometry)
        self._sync_label_geometry(force=False)
        if not defer_geometry:
            self.updateGeometry()

    def flush_stream_geometry(self) -> None:
        """Commit deferred thinking label geometry after a coalesced stream flush."""
        if not self.has_text():
            return
        self._sync_label_geometry(force=False)
        self._refresh_header(update_elapsed=True)
        self.updateGeometry()

    def set_text(self, text: str) -> None:
        """Replace the thinking text."""
        self._label.setText(text)
        has_text = bool(text.strip())
        self.setVisible(has_text)
        self._header.setVisible(has_text)
        self._label.setVisible(has_text and self._expanded)
        self._stream_height_floor = 0
        self._stream_floor_width = 0
        self._sync_label_geometry(force=True)
        self.updateGeometry()

    def set_duration_seconds(self, seconds: int | None) -> None:
        """Restore or override the frozen thinking duration shown in the header."""
        if seconds is not None and seconds > 0:
            self._duration_seconds = seconds
        else:
            self._duration_seconds = None
        self._refresh_header()

    def duration_seconds(self) -> int | None:
        """Return the frozen thinking duration, if any."""
        return self._duration_seconds

    def finalize_thinking(self, *, collapse: bool = True) -> None:
        """Freeze the thinking duration and optionally collapse the body."""
        already_finalized = self._duration_seconds is not None
        if not already_finalized and self._timer.isValid():
            self._duration_seconds = max(1, round(self._timer.elapsed() / 1000))
            self._timer.invalidate()
        # #region agent log
        try:
            from debug_stream_log import debug_stream_log

            debug_stream_log(
                location="thought_section.py:finalize_thinking",
                message="finalize_thinking",
                data={
                    "already_finalized": already_finalized,
                    "duration_seconds": self._duration_seconds,
                    "timer_valid": self._timer.isValid(),
                },
                hypothesis_id="H-timer-overwrite",
            )
        except Exception:
            pass
        # #endregion
        if collapse:
            self.set_collapsed(True)
        else:
            self._refresh_header()

    def set_collapsed(self, collapsed: bool) -> None:
        """Show or hide the thinking body while keeping the header."""
        # #region agent log
        try:
            from debug_stream_log import debug_stream_log

            debug_stream_log(
                location="thought_section.py:set_collapsed",
                message="set_collapsed",
                data={
                    "collapsed": collapsed,
                    "was_expanded": self._expanded,
                    "duration": self._duration_seconds,
                    "text_len": len(self._label.text()),
                },
                hypothesis_id="H1-reexpand",
            )
        except Exception:
            pass
        # #endregion
        self._expanded = not collapsed
        has_text = bool(self._label.text().strip())
        self.setVisible(has_text)
        self._header.setVisible(has_text)
        self._label.setVisible(has_text and self._expanded)
        self._refresh_header()
        self._sync_label_geometry(force=True)
        self.updateGeometry()
        self._emit_layout_height_changed()

    def is_expanded(self) -> bool:
        """Return whether the thinking body is expanded."""
        return self._expanded

    def sizeHint(self) -> QSize:
        """Return height from measured wrapped text, not stale layout slack."""
        width = self._block_layout_width()
        if width <= 0:
            return super().sizeHint()
        return QSize(width, self.layout_height_hint())

    def minimumSizeHint(self) -> QSize:
        """Return the same compact hint as ``sizeHint``."""
        return self.sizeHint()

    def layout_height_hint(self) -> int:
        """Return the preferred block height without nested layout queries."""
        if not self.has_text():
            return 0
        layout = self.layout()
        margins = layout.contentsMargins() if layout is not None else None
        chrome = 0
        if margins is not None:
            chrome = margins.top() + margins.bottom()
        spacing = layout.spacing() if layout is not None else 0
        header_h = self._header.sizeHint().height()
        if not self._expanded:
            return chrome + header_h
        width = self.width()
        if width <= 0:
            parent = self.parentWidget()
            if parent is not None and parent.width() > 0:
                width = parent.width()
        label_width = self._label.width() if self._label.width() > 0 else width
        label_h = (
            self._label.heightForWidth(max(1, label_width)) if width > 0 else self._label.height()
        )
        if self._expanded and self._label.height() > 0:
            label_h = max(label_h, self._label.height())
        return chrome + header_h + spacing + max(1, label_h)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Keep wrapped thinking text measured to the current block width."""
        super().resizeEvent(event)
        self._sync_label_geometry(force=True)
        if self._expanded and self.has_text():
            self.updateGeometry()

    def _block_layout_width(self) -> int:
        """Return the inner width available for the thinking label."""
        width = self.width()
        if width <= 0:
            parent = self.parentWidget()
            if parent is not None and parent.width() > 0:
                width = parent.width()
        return max(0, width)

    def _sync_label_width(self) -> None:
        """Clamp the thinking label to the current block width."""
        width = self._block_layout_width()
        if width > 0:
            self._label.setMaximumWidth(width)

    def _release_label_height_clamp(self) -> None:
        """Allow the hidden label to reflow on the next expand."""
        self._label.setMinimumHeight(0)
        self._label.setMaximumHeight(_QWIDGET_MAX_HEIGHT)

    def _sync_label_geometry(self, *, force: bool = False) -> None:
        """Set the label height from wrapped text measured at the stable block width.

        Uses the section's own width (not the label's transient laid-out width,
        which fluctuates during a layout pass) and a per-width monotonic floor so
        appended streaming text can only grow the block — never shrink it on an
        intermediate pass, which is what made the thought block bounce.
        """
        self._sync_label_width()
        if not (self._expanded and self.has_text()):
            self._release_label_height_clamp()
            self._stream_height_floor = 0
            self._stream_floor_width = 0
            return
        width = self._block_layout_width()
        if width <= 0:
            return
        if force:
            self._label._invalidate_measured_height()
        self._release_label_height_clamp()
        text_width = self._label._text_width_for_widget_width(width)
        target = max(1, self._label._measure_wrapped_height(text_width))
        if width != self._stream_floor_width:
            self._stream_floor_width = width
            self._stream_height_floor = 0
        target = max(target, self._stream_height_floor)
        self._stream_height_floor = target
        # Always re-apply the clamp: ``_release_label_height_clamp`` above left
        # min=0/max=MAX, so a conditional ``setFixedHeight`` would leave the label
        # unclamped whenever its height already equalled ``target`` — letting the
        # layout float it to its plain ``sizeHint`` and bounce.
        self._label.setFixedHeight(target)
        self._label.updateGeometry()

    def header_text(self) -> str:
        """Return the current thought header label."""
        return self._header.text().strip()

    def _toggle(self) -> None:
        bubble = self.parentWidget()
        if bubble is not None and hasattr(bubble, "begin_scroll_compensation_capture"):
            bubble.begin_scroll_compensation_capture(self)
        self._expanded = not self._expanded
        self._label.setVisible(self._expanded and self.has_text())
        self._refresh_header()
        self._sync_label_geometry(force=True)
        self.updateGeometry()
        self._emit_layout_height_changed()

    def _emit_layout_height_changed(self) -> None:
        """Notify the parent row that thought visibility changed the layout."""
        self.layout_height_changed.emit()

    def _refresh_header(self, *, update_elapsed: bool = True) -> None:
        icon_name = "caret-down" if self._expanded else "caret-right"
        self._header.setIcon(phi(icon_name, size=10))
        if self._duration_seconds is not None:
            label = f"Thought for {self._duration_seconds}s"
        elif self._timer.isValid() and self.has_text():
            elapsed = max(1, self._timer.elapsed() // 1000)
            if not update_elapsed and elapsed == self._header_elapsed_shown:
                return
            self._header_elapsed_shown = elapsed
            label = f"Thought for {elapsed}s"
        else:
            label = "Thought"
        self._header.setText(f" {label}")


_ThoughtSection = ThoughtSection
