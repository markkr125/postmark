"""Collapsible thinking block for assistant message rows."""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, Qt, Signal
from PySide6.QtWidgets import QFrame, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ui.sidebar.ai.message_bubble.wrapping_label import _WrappingLabel
from ui.styling.icons import phi


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
        layout.setSpacing(4)

        self._header = QPushButton()
        self._header.setObjectName("aiChatThoughtToggle")
        self._header.setFlat(True)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.clicked.connect(self._toggle)
        layout.addWidget(self._header)

        self._label = _WrappingLabel()
        self._label.setObjectName("aiChatThoughtText")
        layout.addWidget(self._label)

        self._expanded = False
        self._duration_seconds: int | None = None
        self._timer = QElapsedTimer()
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
        self._label.setText(self._label.text() + text)
        has_text = bool(self._label.text().strip())
        self.setVisible(has_text)
        self._header.setVisible(has_text)
        if has_text and self._duration_seconds is None:
            self._expanded = True
        self._label.setVisible(has_text and self._expanded)
        self._refresh_header()
        if not defer_geometry:
            self.updateGeometry()

    def set_text(self, text: str) -> None:
        """Replace the thinking text."""
        self._label.setText(text)
        has_text = bool(text.strip())
        self.setVisible(has_text)
        self._header.setVisible(has_text)
        self._label.setVisible(has_text and self._expanded)
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
        if self._timer.isValid():
            self._duration_seconds = max(1, round(self._timer.elapsed() / 1000))
        if collapse:
            self.set_collapsed(True)
        else:
            self._refresh_header()

    def set_collapsed(self, collapsed: bool) -> None:
        """Show or hide the thinking body while keeping the header."""
        self._expanded = not collapsed
        has_text = bool(self._label.text().strip())
        self.setVisible(has_text)
        self._header.setVisible(has_text)
        self._label.setVisible(has_text and self._expanded)
        self._refresh_header()
        self.updateGeometry()
        self._emit_layout_height_changed()

    def is_expanded(self) -> bool:
        """Return whether the thinking body is expanded."""
        return self._expanded

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
        self.updateGeometry()
        self._emit_layout_height_changed()

    def _emit_layout_height_changed(self) -> None:
        """Notify the parent row that thought visibility changed the layout."""
        self.layout_height_changed.emit()

    def _refresh_header(self) -> None:
        icon_name = "caret-down" if self._expanded else "caret-right"
        self._header.setIcon(phi(icon_name, size=10))
        if self._duration_seconds is not None:
            label = f"Thought for {self._duration_seconds}s"
        elif self._timer.isValid() and self.has_text():
            elapsed = max(1, self._timer.elapsed() // 1000)
            label = f"Thought for {elapsed}s"
        else:
            label = "Thought"
        self._header.setText(f" {label}")


_ThoughtSection = ThoughtSection
