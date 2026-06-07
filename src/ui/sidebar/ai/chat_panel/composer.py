"""Composer input and model picker controls for :class:`AiChatPanel`."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QSizePolicy, QWidget

from ui.styling.icons import phi

_NO_MODELS_TEXT = "No models configured"
_COMPOSER_MIN_LINES = 3
_COMPOSER_MAX_LINES = 15
# Matches ``padding: 6px`` top+bottom on ``aiChatInput`` in global_qss.py.
_COMPOSER_QSS_VERTICAL_PADDING = 12


class _ComposerInput(QPlainTextEdit):
    """Prompt input that auto-grows (3..15 lines) and emits submit on Enter."""

    submit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Configure wrap, scrollbars, and connect auto-grow recompute."""
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.document().documentLayout().documentSizeChanged.connect(self._adjust_height)
        self._adjust_height()

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
        if self.height() != target:
            self.setFixedHeight(target)

    def resizeEvent(self, event) -> None:
        """Recompute height when width changes (wrapping can change line count)."""
        super().resizeEvent(event)
        self._adjust_height()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Submit on Enter; Shift+Enter inserts a newline."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ModelPickerButton(QWidget):
    """Compact model pill matching :class:`AgentModeButton` (label · tags · caret)."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build name, context/reasoning tags, and trailing caret."""
        super().__init__(parent)
        self.setObjectName("aiChatModelButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        mouse_through = Qt.WidgetAttribute.WA_TransparentForMouseEvents

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 6, 3)
        lay.setSpacing(4)

        self._name = QLabel(_NO_MODELS_TEXT)
        self._name.setObjectName("aiChatModelButtonPart")
        self._name.setAttribute(mouse_through, True)
        lay.addWidget(self._name, 0)

        self._sep_ctx = QLabel("·")
        self._sep_ctx.setObjectName("aiChatModelButtonPart")
        self._sep_ctx.setAttribute(mouse_through, True)
        lay.addWidget(self._sep_ctx, 0)

        self._ctx = QLabel()
        self._ctx.setObjectName("aiModelPickerContext")
        self._ctx.setAttribute(mouse_through, True)
        lay.addWidget(self._ctx, 0)

        self._sep_effort = QLabel("·")
        self._sep_effort.setObjectName("aiChatModelButtonPart")
        self._sep_effort.setAttribute(mouse_through, True)
        lay.addWidget(self._sep_effort, 0)

        self._effort = QLabel()
        self._effort.setObjectName("aiModelPickerEffort")
        self._effort.setAttribute(mouse_through, True)
        lay.addWidget(self._effort, 0)

        caret = QLabel()
        caret.setPixmap(phi("caret-down", size=10).pixmap(10, 10))
        caret.setAttribute(mouse_through, True)
        lay.addWidget(caret, 0)

        self._hide_tags()

    def _hide_tags(self) -> None:
        """Hide context/reasoning segments (empty-state / name-only)."""
        self._sep_ctx.hide()
        self._ctx.hide()
        self._sep_effort.hide()
        self._effort.hide()

    def set_parts(self, parts: tuple[str, str | None, str | None] | None) -> None:
        """Update visible segments from ``(name, context, effort)`` or empty state."""
        if parts is None:
            self._name.setText(_NO_MODELS_TEXT)
            self._hide_tags()
        else:
            name, ctx_val, effort_val = parts
            self._name.setText(name)
            if ctx_val:
                self._ctx.setText(ctx_val)
                self._sep_ctx.show()
                self._ctx.show()
            else:
                self._sep_ctx.hide()
                self._ctx.hide()
            if effort_val:
                self._effort.setText(effort_val)
                self._sep_effort.show()
                self._effort.show()
            else:
                self._sep_effort.hide()
                self._effort.hide()
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit ``clicked`` on left press."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)
