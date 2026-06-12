"""Collapsible user prompt body for AI chat transcript rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QResizeEvent, QShowEvent
from PySide6.QtWidgets import QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ui.sidebar.ai.message_bubble.user_message.fade import UserMessageBottomFade
from ui.sidebar.ai.message_bubble.wrapping_label import _WrappingLabel

if TYPE_CHECKING:
    from ui.sidebar.ai.message_bubble.bubble import ChatMessageBubble

_USER_MESSAGE_COLLAPSED_MAX_LINES = 5
_SHOW_MORE_LABEL = "Show more"
_SHOW_LESS_LABEL = "Show less"
_QWIDGET_MAX_HEIGHT = 16777215


class UserMessageSection(QWidget):
    """Wrapped user prompt with optional collapsed preview and Show more/less."""

    layout_height_changed = Signal()

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        """Build the label host, fade overlay, and expand/collapse toggle."""
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._label_host = QWidget(self)
        self._label_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        host_layout = QVBoxLayout(self._label_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)

        self._label = _WrappingLabel(text, self._label_host)
        self._label.setObjectName("aiChatUserMessageText")
        host_layout.addWidget(self._label)

        self._fade = UserMessageBottomFade(self._label_host)
        self._fade.hide()

        layout.addWidget(self._label_host)

        self._toggle = QPushButton()
        self._toggle.setObjectName("aiChatUserMessageToggle")
        self._toggle.setFlat(True)
        self._toggle.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._on_toggle_clicked)
        self._toggle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._toggle.hide()
        layout.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignLeft)

        self._expanded = True
        self._collapsible = False
        self._overlay_clamp_active = False
        self._viewport_label_cap: int | None = None
        self._last_layout_width = -1
        self._initial_layout_done = False

    def text(self) -> str:
        """Return the full user prompt text."""
        return self._label.text()

    def set_text(self, text: str) -> None:
        """Replace the user prompt text and refresh collapse state."""
        self._label.setText(text)
        self._refresh_collapse_layout(force=True)

    def label_widget(self) -> _WrappingLabel:
        """Return the wrapped prompt label (tests and wheel forwarding)."""
        return self._label

    def is_expanded(self) -> bool:
        """Return whether the full prompt is shown."""
        return self._expanded or not self._collapsible

    def is_collapsible(self) -> bool:
        """Return whether the prompt exceeds the collapsed preview threshold."""
        return self._collapsible

    def collapsed_cap_height(self) -> int | None:
        """Return the collapsed label cap height when collapsible."""
        if not self._collapsible:
            return None
        width = max(1, self._layout_width())
        return self._collapsed_cap_height(width)

    def natural_label_height_for_width(self, width: int) -> int:
        """Return uncapped wrapped label height at *width*."""
        return self._natural_label_height(max(1, width))

    def collapsed_label_height_for_width(self, width: int) -> int | None:
        """Return the collapsed preview cap at *width*, if applicable."""
        if width <= 0 or not self._needs_collapse(width):
            return None
        return self._collapsed_cap_height(width)

    def needs_collapse_for_width(self, width: int) -> bool:
        """Return whether *width* requires a collapsed preview for the current text."""
        return self._needs_collapse(max(1, width))

    def toggle_row_height_for_width(self, width: int) -> int:
        """Return toggle row height when the prompt would be collapsible at *width*."""
        if not self._needs_collapse(width):
            return 0
        if self._toggle.isVisible():
            return self.toggle_row_height()
        layout = self.layout()
        spacing = layout.spacing() if layout is not None else 0
        return self._toggle.sizeHint().height() + spacing

    def set_reflow_deferred(self, deferred: bool) -> None:
        """Defer width reflow on the prompt label during pane resize."""
        self._label.set_reflow_deferred(deferred)

    def flush_deferred_reflow(self) -> None:
        """Flush deferred label reflow and refresh collapse measurements."""
        self._label.flush_deferred_reflow()
        self._refresh_collapse_layout(force=True)

    def apply_viewport_clamp(self, label_max_height: int | None) -> None:
        """Clamp the prompt label for the sticky overlay viewport cap."""
        self._viewport_label_cap = label_max_height
        self._overlay_clamp_active = label_max_height is not None and label_max_height > 0
        self.setMaximumHeight(_QWIDGET_MAX_HEIGHT)
        self._refresh_collapse_layout(force=True)

    def set_expanded(self, expanded: bool) -> None:
        """Set expanded/collapsed state without scroll capture (sticky clone sync)."""
        self._expanded = expanded
        self._refresh_collapse_layout(force=True)

    def toggle_row_height(self) -> int:
        """Return the Show more/less row height when the toggle is visible."""
        if not self._toggle.isVisible():
            return 0
        layout = self.layout()
        spacing = layout.spacing() if layout is not None else 0
        return self._toggle.sizeHint().height() + spacing

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Re-measure collapse when the section width changes."""
        super().resizeEvent(event)
        self._position_fade()
        width = self._layout_width()
        if width > 0 and width != self._last_layout_width:
            self._refresh_collapse_layout()

    def changeEvent(self, event: QEvent) -> None:
        """Re-measure collapse when fonts change."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._label._invalidate_measured_height()
            self._refresh_collapse_layout(force=True)

    def _layout_width(self) -> int:
        """Return the inner width available for wrapped prompt measurement."""
        width = self.width()
        if width > 0:
            return width
        parent = self.parentWidget()
        if parent is not None and parent.width() > 0:
            return parent.width()
        return 0

    def _collapsed_cap_height(self, width: int) -> int:
        """Return the maximum label height for the collapsed preview."""
        line_h = self._label.fontMetrics().lineSpacing()
        margins = self._label.contentsMargins()
        return line_h * _USER_MESSAGE_COLLAPSED_MAX_LINES + margins.top() + margins.bottom() + 2

    def _natural_label_height(self, width: int) -> int:
        """Return the uncapped wrapped label height at *width*."""
        if width <= 0:
            self._label._invalidate_measured_height()
            return self._label.sizeHint().height()
        text_width = self._label._text_width_for_widget_width(width)
        return self._label._measure_wrapped_height(text_width)

    def _needs_collapse(self, width: int) -> bool:
        """Return whether *width* forces a collapsed preview for the current text."""
        if width <= 0 or not self.text().strip():
            return False
        return self._natural_label_height(width) > self._collapsed_cap_height(width)

    def _refresh_collapse_layout(self, *, force: bool = False) -> None:
        """Update collapsible state, label clamp, fade, and toggle visibility."""
        self._label._invalidate_measured_height()
        width = self._layout_width()
        if width <= 0 and not force:
            return
        if width > 0:
            self._last_layout_width = width

        collapsible = self._needs_collapse(max(1, width))
        collapsible_changed = collapsible != self._collapsible
        self._collapsible = collapsible

        if collapsible and not self._expanded:
            cap = self._collapsed_cap_height(max(1, width))
            if self._overlay_clamp_active and self._viewport_label_cap is not None:
                cap = min(cap, self._viewport_label_cap)
            self._set_label_max_height(cap)
        else:
            label_max = _QWIDGET_MAX_HEIGHT
            if self._overlay_clamp_active and self._viewport_label_cap is not None:
                label_max = self._viewport_label_cap
            self._set_label_max_height(label_max)

        if (collapsible and not self._expanded) or self._overlay_clamp_active:
            self._fade.show()
        else:
            self._fade.hide()

        if self._collapsible:
            self._toggle.show()
            self._toggle.setText(_SHOW_LESS_LABEL if self.is_expanded() else _SHOW_MORE_LABEL)
            self._toggle.setFixedWidth(self._toggle.sizeHint().width())
        else:
            self._toggle.hide()

        self._position_fade()
        self._invalidate_section_layout()
        if collapsible_changed:
            self._emit_layout_height_changed()

    def _set_label_max_height(self, max_height: int) -> None:
        """Apply a label height cap and force the layout to re-measure."""
        self._label.setMaximumHeight(max_height)
        self._label.setMinimumHeight(0)
        self._label._invalidate_measured_height()
        self._label.updateGeometry()

    def _invalidate_section_layout(self) -> None:
        """Re-query wrapped label height after collapse state or caps change."""
        self._label._invalidate_measured_height()
        self._label.updateGeometry()
        self.updateGeometry()

    def _position_fade(self) -> None:
        """Place the fade strip along the bottom of the label host."""
        if not self._fade.isVisible():
            return
        host = self._label_host
        self._fade.setFixedWidth(host.width())
        self._fade.move(0, max(0, host.height() - self._fade.height()))
        self._fade.raise_()

    def _ancestor_message_bubble(self) -> ChatMessageBubble | None:
        """Return the enclosing ``ChatMessageBubble``, if any."""
        from ui.sidebar.ai.message_bubble.bubble import ChatMessageBubble

        widget: QWidget | None = self.parentWidget()
        while widget is not None:
            if isinstance(widget, ChatMessageBubble):
                return widget
            widget = widget.parentWidget()
        return None

    def _on_toggle_clicked(self) -> None:
        """Expand or collapse the prompt preview."""
        bubble = self._ancestor_message_bubble()
        if bubble is not None:
            bubble.begin_scroll_compensation_capture(bubble)
        self._expanded = not self._expanded
        self._refresh_collapse_layout(force=True)
        if bubble is not None:
            bubble.updateGeometry()
        self._emit_layout_height_changed()

    def _emit_layout_height_changed(self) -> None:
        """Notify the parent row that section height changed."""
        self.layout_height_changed.emit()

    def showEvent(self, event: QShowEvent) -> None:
        """Choose the initial collapsed state once width is known."""
        super().showEvent(event)
        if not self._initial_layout_done:
            self._initial_layout_done = True
            if self._needs_collapse(self._layout_width()):
                self._expanded = False
        self._refresh_collapse_layout(force=True)
