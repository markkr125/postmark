"""Shared anchor tracking for chat message action flyouts."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QScrollArea, QScrollBar, QWidget
from shiboken6 import Shiboken


def transcript_scroll_for_anchor(anchor: QWidget) -> QScrollArea | None:
    """Return the chat transcript scroll area containing *anchor*, if any."""
    widget: QWidget | None = anchor
    while widget is not None:
        if widget.objectName() == "aiChatScroll" and isinstance(widget, QScrollArea):
            return widget
        widget = widget.parentWidget()
    return None


def anchor_visible_in_transcript_scroll(anchor: QWidget) -> bool:
    """Return whether *anchor* intersects the visible transcript viewport."""
    if not anchor.isVisible():
        return False
    scroll = transcript_scroll_for_anchor(anchor)
    if scroll is None:
        return True
    viewport = scroll.viewport()
    if viewport is None:
        return True
    top_left = anchor.mapTo(viewport, QPoint(0, 0))
    anchor_rect = QRect(top_left, anchor.size())
    return viewport.rect().intersects(anchor_rect)


class AnchorFollowingActionsPopupMixin:
    """Reposition (or dismiss) a tool flyout when the transcript scrolls."""

    _anchor: QWidget | None
    _scroll_bar: QScrollBar | None
    _anchor_reposition_pending: bool

    def _init_anchor_popup_tracking_state(self) -> None:
        """Reset mixin state used while a flyout is open."""
        self._scroll_bar = None
        self._anchor_reposition_pending = False

    def _position_near_anchor(self, anchor: QWidget) -> None:
        """Place the flyout below *anchor*, right-aligned; flip above if clipped."""
        if not Shiboken.isValid(anchor):
            return
        gap = 4
        panel_h = self.height()  # type: ignore[attr-defined]
        panel_w = self.width()  # type: ignore[attr-defined]
        bottom_right = anchor.mapToGlobal(anchor.rect().bottomRight())
        x = bottom_right.x() - panel_w
        y = bottom_right.y() + gap
        screen = QGuiApplication.screenAt(bottom_right) or QGuiApplication.primaryScreen()
        sr = screen.availableGeometry() if screen else None
        if sr is not None:
            x = max(sr.left(), min(x, sr.right() - panel_w))
            if y + panel_h > sr.bottom():
                top_right = anchor.mapToGlobal(anchor.rect().topRight())
                y = top_right.y() - panel_h - gap
            y = max(sr.top(), min(y, sr.bottom() - panel_h))
        self.move(x, y)  # type: ignore[attr-defined]

    def _attach_anchor_scroll_tracking(self) -> None:
        """Follow the anchor while the transcript scrolls or relayouts."""
        self._detach_anchor_scroll_tracking()
        anchor = self._anchor
        if anchor is None or not Shiboken.isValid(anchor):
            return
        scroll = transcript_scroll_for_anchor(anchor)
        if scroll is None:
            return
        bar = scroll.verticalScrollBar()
        self._scroll_bar = bar
        bar.valueChanged.connect(self._sync_popup_position_to_anchor)
        bar.rangeChanged.connect(self._sync_popup_position_to_anchor)

    def _detach_anchor_scroll_tracking(self) -> None:
        """Disconnect transcript scroll listeners."""
        bar = self._scroll_bar
        if bar is None:
            return
        try:
            bar.valueChanged.disconnect(self._sync_popup_position_to_anchor)
            bar.rangeChanged.disconnect(self._sync_popup_position_to_anchor)
        except (TypeError, RuntimeError):
            pass
        self._scroll_bar = None
        self._anchor_reposition_pending = False

    def _schedule_popup_position_sync(self) -> None:
        """Coalesce scroll-driven repositions to one update per event-loop tick."""
        if self._anchor_reposition_pending:
            return
        if not self.isVisible():  # type: ignore[attr-defined]
            return
        self._anchor_reposition_pending = True
        QTimer.singleShot(0, self._flush_popup_position_sync)

    def _flush_popup_position_sync(self) -> None:
        """Apply one coalesced reposition near the anchor."""
        self._anchor_reposition_pending = False
        if not self.isVisible():  # type: ignore[attr-defined]
            return
        anchor = self._anchor
        if anchor is None or not Shiboken.isValid(anchor) or not anchor.isVisible():
            self.hide_popup()  # type: ignore[attr-defined]
            return
        if not anchor_visible_in_transcript_scroll(anchor):
            self.hide_popup()  # type: ignore[attr-defined]
            return
        self._position_near_anchor(anchor)

    def _sync_popup_position_to_anchor(self, *_args: object) -> None:
        """Queue a coalesced reposition after transcript scroll or relayout."""
        self._schedule_popup_position_sync()

    def _teardown_anchor_popup_tracking(self) -> None:
        """Remove scroll tracking installed by :meth:`_attach_anchor_scroll_tracking`."""
        self._anchor_reposition_pending = False
        self._detach_anchor_scroll_tracking()


__all__ = [
    "AnchorFollowingActionsPopupMixin",
    "anchor_visible_in_transcript_scroll",
    "transcript_scroll_for_anchor",
]
