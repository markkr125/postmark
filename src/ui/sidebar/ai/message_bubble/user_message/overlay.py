"""Viewport overlay for the sticky user prompt in the AI chat transcript."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, NamedTuple

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QResizeEvent, QShowEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QScrollArea, QWidget

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
    content_height: int = 0


class _StickyInnerScrollArea(QScrollArea):
    """Internal sticky scroll area that releases boundary wheels to the transcript."""

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Scroll internally, but forward to the transcript at top/bottom edges."""
        if self._forward_boundary_wheel_to_transcript(event):
            return
        super().wheelEvent(event)

    def _forward_boundary_wheel_to_transcript(self, event: QWheelEvent) -> bool:
        """Return True when a boundary wheel was forwarded to the transcript."""
        bar = self.verticalScrollBar()
        delta_y = event.angleDelta().y()
        at_top = bar.value() <= bar.minimum()
        at_bottom = bar.value() >= bar.maximum()
        if not ((delta_y > 0 and at_top) or (delta_y < 0 and at_bottom)):
            return False
        widget: QWidget | None = self
        while widget is not None:
            parent = widget.parentWidget()
            if isinstance(parent, QScrollArea) and parent.objectName() == "aiChatScroll":
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
            widget = parent
        return forward_wheel_to_ancestor_scroll_area(self, event)


class _StickyPromptLabel(_WrappingLabel):
    """Sticky prompt label that scrolls internally and releases boundary wheels."""

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Route wheels through the internal scroll area boundary logic."""
        scroll_area = self.parentWidget()
        while scroll_area is not None and not isinstance(scroll_area, _StickyInnerScrollArea):
            scroll_area = scroll_area.parentWidget()
        if isinstance(scroll_area, _StickyInnerScrollArea):
            if scroll_area._forward_boundary_wheel_to_transcript(event):
                return
            super().wheelEvent(event)
            return
        if forward_wheel_to_ancestor_scroll_area(self, event):
            return
        super().wheelEvent(event)


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

        self._scroll_area = _StickyInnerScrollArea(self._frame)
        self._scroll_area.setObjectName("aiChatStickyScroll")
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.viewport().setAutoFillBackground(False)

        self._label = _StickyPromptLabel("", self._scroll_area)
        self._label.setObjectName("aiChatUserMessageText")
        self._scroll_area.setWidget(self._label)

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
        """Return the visible label viewport height (for layout repair checks)."""
        return self._scroll_area.height()

    def label_widget(self) -> _StickyPromptLabel:
        """Return the wrapped prompt label."""
        return self._label

    def prompt_content_bottom_y(self) -> int:
        """Return the bottom edge of label/toggle chrome in overlay coordinates."""
        bottom = self._scroll_area.y() + self._scroll_area.height()
        if self._toggle.isVisible():
            bottom = max(bottom, self._toggle.y() + self._toggle.height())
        return self._frame.y() + bottom

    def set_anchor_state(
        self,
        *,
        text: str,
        sent_at: datetime | None,
        collapsible: bool,
    ) -> None:
        """Mirror anchor prompt text/time without relying on nested row layout."""
        text_changed = text != self._text
        self._text = text
        self._sent_at = sent_at
        self._collapsible = collapsible
        self._label.setText(text)
        if text_changed:
            self._expanded = not collapsible
        if sent_at is not None:
            self._timestamp.setText(format_message_sent_at(sent_at))
        else:
            self._timestamp.clear()
        self._refresh_collapsible_state()
        self._toggle.hide()
        self._timestamp.hide()

    def sync_expanded_from_anchor(self, anchor: ChatMessageBubble) -> None:
        """Copy text/time/collapsible from a transcript user row (keeps own expand state)."""
        section = anchor._user_section
        inner_w = self._inner_label_width(max(1, self.width()))
        collapsible = False
        if section is not None:
            collapsible = section.is_collapsible() or section.needs_collapse_for_width(inner_w)
        self.set_anchor_state(
            text=anchor.text(),
            sent_at=anchor.sent_at(),
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
        return StickyOverlayMetrics(label_h, chrome, chrome + label_h, clamped, natural_h)

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
        """Re-apply child geometry when the scroll viewport failed to size as expected."""
        if self._scroll_area.height() < max(8, min(metrics.label_height, 40) // 2):
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
        expanded = self.is_user_message_expanded()

        y = _FRAME_MARGIN_TOP
        x = _FRAME_MARGIN_LEFT

        content_h = max(metrics.content_height, metrics.label_height)
        self._scroll_area.setGeometry(x, y, inner_w, metrics.label_height)
        self._label.setFixedWidth(inner_w)
        self._label.setFixedHeight(content_h)
        if expanded and content_h > metrics.label_height:
            self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._scroll_area.verticalScrollBar().setValue(0)
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

        if collapsible and not expanded:
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
        """Flip expanded state and let the panel recompute geometry (avoids stale-metric flicker)."""
        self._expanded = not self._expanded
        self._refresh_collapsible_state()
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
