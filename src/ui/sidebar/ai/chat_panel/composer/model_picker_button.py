"""Compact model pill for AI chat composers."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ui.styling.icons import phi

_NO_MODELS_TEXT = "No models configured"
_NO_ENABLED_MODELS_TEXT = "Enable a model in Settings"


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


__all__ = ["_NO_ENABLED_MODELS_TEXT", "_NO_MODELS_TEXT", "ModelPickerButton"]
