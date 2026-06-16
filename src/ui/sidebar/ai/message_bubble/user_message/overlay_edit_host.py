"""Inline-edit composer hosting for the sticky user-prompt overlay."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from ui.sidebar.ai.message_bubble.user_message.overlay import StickyOverlayMetrics

if TYPE_CHECKING:
    from ui.sidebar.ai.chat_panel.composer import AiChatComposer
    from ui.sidebar.ai.message_bubble.user_message.overlay import StickyUserPromptOverlay

_FRAME_MARGIN_LEFT = 12
_FRAME_MARGIN_TOP = 6
_FRAME_MARGIN_RIGHT = 12
_FRAME_MARGIN_BOTTOM = 6


def hosts_inline_composer(overlay: StickyUserPromptOverlay) -> bool:
    """Return whether the overlay currently hosts an inline edit composer."""
    return overlay._inline_composer is not None


def hide_readonly_chrome(overlay: StickyUserPromptOverlay) -> None:
    """Hide read-only sticky chrome while hosting the inline composer."""
    overlay._label_host.hide()
    overlay._scroll_area.hide()
    overlay._toggle.hide()
    overlay._footer.hide()
    overlay._fade.hide()


def show_readonly_chrome(overlay: StickyUserPromptOverlay) -> None:
    """Restore read-only sticky chrome after releasing the inline composer."""
    overlay._label_host.show()
    overlay._footer.show()


def host_inline_composer(overlay: StickyUserPromptOverlay, composer: AiChatComposer) -> None:
    """Embed *composer* in the sticky user frame for off-screen inline edit."""
    overlay._inline_composer = composer
    hide_readonly_chrome(overlay)
    composer.setParent(overlay._frame)
    composer.show()


def release_inline_composer(overlay: StickyUserPromptOverlay) -> QWidget | None:
    """Remove the hosted inline composer and restore read-only chrome."""
    composer = overlay._inline_composer
    if composer is None:
        return None
    composer.setParent(None)
    overlay._inline_composer = None
    show_readonly_chrome(overlay)
    return composer


def measure_edit_for_width(
    overlay: StickyUserPromptOverlay,
    width: int,
    max_height: int,
    composer: QWidget,
) -> StickyOverlayMetrics:
    """Measure sticky geometry when hosting an inline composer."""
    _ = overlay
    inner_w = max(1, width - _FRAME_MARGIN_LEFT - _FRAME_MARGIN_RIGHT)
    composer.setFixedWidth(inner_w)
    composer_h = max(composer.sizeHint().height(), composer.minimumSizeHint().height())
    chrome = _FRAME_MARGIN_TOP + _FRAME_MARGIN_BOTTOM
    total = min(max_height, chrome + composer_h)
    label_h = max(1, min(composer_h, total - chrome))
    return StickyOverlayMetrics(
        label_height=label_h,
        chrome_height=chrome,
        total_height=total,
        clamped=composer_h + chrome > total,
        content_height=composer_h,
    )


def apply_edit_geometry(
    overlay: StickyUserPromptOverlay,
    width: int,
    height: int,
    metrics: StickyOverlayMetrics,
    composer: QWidget,
) -> None:
    """Layout the sticky frame around a hosted inline composer."""
    overlay.setFixedSize(width, height)
    overlay._applied_metrics = metrics
    overlay._frame.setGeometry(0, 0, width, height)
    inner_w = max(1, width - _FRAME_MARGIN_LEFT - _FRAME_MARGIN_RIGHT)
    composer.setGeometry(_FRAME_MARGIN_LEFT, _FRAME_MARGIN_TOP, inner_w, metrics.label_height)
