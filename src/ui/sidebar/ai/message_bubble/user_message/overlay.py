"""Viewport overlay for the sticky user prompt in the AI chat transcript."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, NamedTuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent, QShowEvent, QWheelEvent
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QWidget

from ui.sidebar.ai.chat_sessions.time_format import format_message_sent_at
from ui.sidebar.ai.message_bubble.user_message.fade import UserMessageBottomFade
from ui.sidebar.ai.message_bubble.wrapping_label import (
    _WrappingLabel,
    forward_wheel_to_ancestor_scroll_area,
)

if TYPE_CHECKING:
    from ui.sidebar.ai.message_bubble.bubble import ChatMessageBubble

_FRAME_MARGIN_LEFT = 12
_FRAME_MARGIN_TOP = 10
_FRAME_MARGIN_RIGHT = 12
_FRAME_MARGIN_BOTTOM = 10
_ROW_SPACING = 4
_COLLAPSED_MAX_LINES = 5
_SHOW_MORE_LABEL = "Show more"
_SHOW_LESS_LABEL = "Show less"


class StickyOverlayMetrics(NamedTuple):
    """Explicit sticky-overlay height parts."""

    label_height: int
    chrome_height: int
    total_height: int
    clamped: bool


class StickyUserPromptOverlay(QWidget):
    """Deterministic sticky user-prompt overlay (not a transcript ``ChatMessageBubble``)."""

    expanded_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build frame, label, fade, toggle, and optional timestamp for the viewport."""
        super().__init__(parent)
        self.setObjectName("aiChatStickyTurnPrompt")
        self._text = ""
        self._sent_at: datetime | None = None
        self._expanded = True
        self._collapsible = False
        self._applied_metrics: StickyOverlayMetrics | None = None

        self._frame = QFrame(self)
        self._frame.setObjectName("aiChatMessageUser")
        self._frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._label = _WrappingLabel("", self._frame)
        self._label.setObjectName("aiChatUserMessageText")

        self._fade = UserMessageBottomFade(self._frame)
        self._fade.hide()

        self._toggle = QPushButton(self._frame)
        self._toggle.setObjectName("aiChatUserMessageToggle")
        self._toggle.setFlat(True)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._on_toggle_clicked)
        self._toggle.hide()

        self._timestamp = QLabel(self._frame)
        self._timestamp.setObjectName("aiChatUserMessageTime")
        self._timestamp.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._timestamp.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._timestamp.hide()

    def text(self) -> str:
        """Return the full user prompt text."""
        return self._text

    def sent_at(self) -> datetime | None:
        """Return the mirrored send time, if any."""
        return self._sent_at

    def is_user_message_expanded(self) -> bool:
        """Return whether the overlay shows the full prompt."""
        return self._expanded or not self._collapsible

    def label_painted_height(self) -> int:
        """Return the painted label height (for layout repair checks)."""
        return self._label.height()

    def label_widget(self) -> _WrappingLabel:
        """Return the wrapped prompt label."""
        return self._label

    def prompt_content_bottom_y(self) -> int:
        """Return the bottom edge of label/toggle chrome in overlay coordinates."""
        bottom = self._label.y() + self._label.height()
        if self._toggle.isVisible():
            bottom = max(bottom, self._toggle.y() + self._toggle.height())
        return self._frame.y() + bottom

    def set_anchor_state(
        self,
        *,
        text: str,
        sent_at: datetime | None,
        expanded: bool,
        collapsible: bool,
    ) -> None:
        """Mirror anchor prompt state without relying on nested row layout."""
        self._text = text
        self._sent_at = sent_at
        self._expanded = expanded
        self._collapsible = collapsible
        self._label.setText(text)
        if sent_at is not None:
            self._timestamp.setText(format_message_sent_at(sent_at))
        else:
            self._timestamp.clear()
        self._refresh_collapsible_state()
        self._toggle.hide()
        self._timestamp.hide()

    def sync_expanded_from_anchor(self, anchor: ChatMessageBubble) -> None:
        """Copy expand/collapse state from a transcript user row."""
        section = anchor._user_section
        inner_w = self._inner_label_width(max(1, self.width()))
        collapsible = False
        expanded = True
        if section is not None:
            collapsible = section.is_collapsible() or section.needs_collapse_for_width(inner_w)
            expanded = section._expanded if collapsible else True
        self.set_anchor_state(
            text=anchor.text(),
            sent_at=anchor.sent_at(),
            expanded=expanded,
            collapsible=collapsible,
        )

    def measure_for_width(self, width: int, max_height: int) -> StickyOverlayMetrics:
        """Return overlay height parts at *width* without mutating visible geometry."""
        inner_w = self._inner_label_width(max(1, width))
        natural_h = self._natural_label_height(inner_w)
        collapsible = self._needs_collapse(inner_w)
        toggle_h = self._toggle_row_height(inner_w) if collapsible else 0
        chrome = self._chrome_height(toggle_h)
        label_budget = max(1, max_height - chrome)

        if collapsible and not self.is_user_message_expanded():
            collapsed_cap = self._collapsed_cap_height(inner_w)
            label_h = min(natural_h, collapsed_cap, label_budget)
        else:
            label_h = min(natural_h, label_budget)

        clamped = label_h < natural_h
        return StickyOverlayMetrics(label_h, chrome, chrome + label_h, clamped)

    @classmethod
    def measure_from_anchor(
        cls,
        anchor: ChatMessageBubble,
        *,
        content_width: int,
        max_height: int,
    ) -> StickyOverlayMetrics:
        """Measure sticky geometry from a transcript anchor row."""
        probe = cls()
        probe.sync_expanded_from_anchor(anchor)
        return probe.measure_for_width(content_width, max_height)

    def apply_geometry(self, width: int, height: int, metrics: StickyOverlayMetrics) -> None:
        """Apply one final overlay size and explicitly position children."""
        self.setFixedSize(width, height)
        self._applied_metrics = metrics
        self._layout_children(metrics)

    def ensure_painted_geometry(self, metrics: StickyOverlayMetrics) -> None:
        """Re-apply child geometry when the label failed to paint at the expected height."""
        if self._label.height() < max(8, min(metrics.label_height, 40) // 2):
            self._layout_children(metrics)

    def _inner_label_width(self, content_width: int) -> int:
        """Return label column width inside the user frame."""
        return max(
            1,
            content_width - _FRAME_MARGIN_LEFT - _FRAME_MARGIN_RIGHT,
        )

    def _natural_label_height(self, inner_width: int) -> int:
        """Return uncapped wrapped label height."""
        text_width = self._label._text_width_for_widget_width(inner_width)
        return self._label._measure_wrapped_height(text_width)

    def _collapsed_cap_height(self, inner_width: int) -> int:
        """Return collapsed preview cap height."""
        _ = inner_width
        line_h = self._label.fontMetrics().lineSpacing()
        margins = self._label.contentsMargins()
        return line_h * _COLLAPSED_MAX_LINES + margins.top() + margins.bottom() + 2

    def _needs_collapse(self, inner_width: int) -> bool:
        """Return whether the current text needs collapse at *inner_width*."""
        if inner_width <= 0 or not self._text.strip():
            return False
        return self._natural_label_height(inner_width) > self._collapsed_cap_height(inner_width)

    def _toggle_row_height(self, inner_width: int) -> int:
        """Return toggle row height when collapsible."""
        if not self._needs_collapse(inner_width):
            return 0
        return self._toggle.sizeHint().height() + _ROW_SPACING

    def _chrome_height(self, toggle_h: int) -> int:
        """Return non-label chrome height."""
        chrome = _FRAME_MARGIN_TOP + _FRAME_MARGIN_BOTTOM
        if self._sent_at is not None:
            chrome += self._timestamp.sizeHint().height()
        if toggle_h > 0:
            chrome += toggle_h
        return chrome

    def _refresh_collapsible_state(self) -> None:
        """Update collapse flags and toggle label without showing chrome."""
        inner_w = self._inner_label_width(max(1, self.width()))
        collapsible = self._collapsible or self._needs_collapse(inner_w)
        self._collapsible = collapsible
        if collapsible:
            self._toggle.setText(
                _SHOW_LESS_LABEL if self.is_user_message_expanded() else _SHOW_MORE_LABEL
            )

    def _layout_children(self, metrics: StickyOverlayMetrics) -> None:
        """Position frame children from explicit metrics (no height-for-width layout loop)."""
        self._frame.setGeometry(0, 0, self.width(), self.height())
        inner_w = self._inner_label_width(self.width())
        self._refresh_collapsible_state()
        collapsible = self._collapsible

        y = _FRAME_MARGIN_TOP
        x = _FRAME_MARGIN_LEFT
        self._label.setGeometry(x, y, inner_w, metrics.label_height)
        y += metrics.label_height

        if collapsible:
            toggle_h = self._toggle.sizeHint().height()
            self._toggle.setGeometry(x, y + _ROW_SPACING, inner_w, toggle_h)
            self._toggle.show()
            y += _ROW_SPACING + toggle_h
        else:
            self._toggle.hide()

        if self._sent_at is not None:
            ts_h = self._timestamp.sizeHint().height()
            self._timestamp.setGeometry(x, y, inner_w, ts_h)
            self._timestamp.show()
        else:
            self._timestamp.hide()

        if metrics.clamped or (self._collapsible and not self.is_user_message_expanded()):
            self._fade.show()
        else:
            self._fade.hide()
        self._position_fade(inner_w, metrics.label_height)

    def _position_fade(self, inner_w: int, label_h: int) -> None:
        """Place the fade along the bottom of the label area."""
        if not self._fade.isVisible():
            return
        fade_h = self._fade.height()
        self._fade.setFixedWidth(inner_w)
        self._fade.move(_FRAME_MARGIN_LEFT, _FRAME_MARGIN_TOP + label_h - fade_h)
        self._fade.raise_()

    def _on_toggle_clicked(self) -> None:
        """Toggle expanded/collapsed preview on the overlay."""
        self._expanded = not self._expanded
        self._refresh_collapsible_state()
        if self._applied_metrics is not None:
            self._layout_children(self._applied_metrics)
        self.expanded_changed.emit()

    def showEvent(self, event: QShowEvent) -> None:
        """Re-position chrome on first paint after the overlay becomes visible."""
        super().showEvent(event)
        if self._applied_metrics is not None:
            self._layout_children(self._applied_metrics)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Keep fade aligned when the overlay width changes."""
        super().resizeEvent(event)
        if self._applied_metrics is not None:
            self._layout_children(self._applied_metrics)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Forward wheel events to the transcript scroll area."""
        if forward_wheel_to_ancestor_scroll_area(self, event):
            return
        super().wheelEvent(event)
