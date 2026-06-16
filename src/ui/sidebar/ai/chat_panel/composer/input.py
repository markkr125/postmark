"""Auto-growing prompt input for AI chat composers."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QPlainTextEdit, QSizePolicy, QWidget

_COMPOSER_MIN_LINES = 3
_COMPOSER_MAX_LINES = 15
_COMPOSER_QSS_VERTICAL_PADDING = 12


class ComposerInput(QPlainTextEdit):
    """Prompt input that auto-grows (3..15 lines) and emits submit on Enter."""

    submit_requested = Signal()
    cancel_requested = Signal()
    height_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Configure wrap, scrollbars, and connect auto-grow recompute."""
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._edit_mode = False
        self.document().documentLayout().documentSizeChanged.connect(self._adjust_height)
        self._adjust_height()

    def set_edit_mode(self, enabled: bool) -> None:
        """When enabled, Escape emits ``cancel_requested`` instead of clearing focus."""
        self._edit_mode = enabled

    def _vertical_chrome(self) -> int:
        """Pixels consumed by frame, document margin, and stylesheet padding."""
        frame = 2 * self.frameWidth()
        doc_margin = int(2 * self.document().documentMargin())
        return _COMPOSER_QSS_VERTICAL_PADDING + frame + doc_margin

    def _adjust_height(self, *_args: object) -> None:
        """Resize to fit content, clamped to 3..15 lines; scroll past the cap.

        Height changes here must not scroll the transcript.
        """
        line_height = self.fontMetrics().lineSpacing()
        chrome = self._vertical_chrome()
        visual_lines = self.document().documentLayout().documentSize().height()
        visual_lines = max(1.0, visual_lines)

        min_h = _COMPOSER_MIN_LINES * line_height + chrome
        max_h = _COMPOSER_MAX_LINES * line_height + chrome
        content_h = int(visual_lines * line_height) + chrome
        target = max(min_h, min(content_h, max_h))

        over_cap = content_h > max_h
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if over_cap
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        prev = self.height()
        if prev != target:
            self.setFixedHeight(target)
            if prev > 0:
                self.height_changed.emit()

    def resizeEvent(self, event) -> None:
        """Recompute height when width changes (wrapping can change line count)."""
        super().resizeEvent(event)
        self._adjust_height()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Submit on Enter; Shift+Enter inserts a newline; Escape cancels in edit mode."""
        if event.key() == Qt.Key.Key_Escape and self._edit_mode:
            self.cancel_requested.emit()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


# Backward-compatible alias for tests and legacy imports.
_ComposerInput = ComposerInput

__all__ = [
    "_COMPOSER_MAX_LINES",
    "_COMPOSER_MIN_LINES",
    "_COMPOSER_QSS_VERTICAL_PADDING",
    "ComposerInput",
    "_ComposerInput",
]
