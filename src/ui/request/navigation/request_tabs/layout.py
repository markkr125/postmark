"""Layout logic for the wrapped request-tab deck.

Extracted from ``bar.py`` to keep both modules under the 600-line limit.
Provides ``_TabLayoutMixin`` which handles row wrapping, single-row
compression, scroll-offset capping, and auto-scroll to the active tab.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QWidget

from .labels import layout_config

if TYPE_CHECKING:
    from .bar import _TabEntry

_ROW_GAP = 2
_TAB_GAP = 2
_PADDING_X = 4
_PADDING_Y = 4
_MIN_SINGLE_ROW_WIDTH = 1
_MAX_VISIBLE_ROWS = 6


class _TabLayoutMixin:
    """Mixin that manages chip positioning and row-overflow scrolling.

    The host class must provide ``_entries``, ``_small_labels``,
    ``_wrap_mode``, ``_scroll_y``, ``_content_height``,
    ``_layout_height``, and ``_current_index`` attributes.
    """

    # -- Host-class interface (declared for mypy) ----------------------
    _entries: list[_TabEntry]
    _small_labels: bool
    _wrap_mode: str
    _scroll_y: int
    _content_height: int
    _layout_height: int
    _current_index: int

    # -- Static helper --------------------------------------------------

    @staticmethod
    def _fit_single_row_widths(base_widths: list[int], available_width: int) -> list[int]:
        """Compress tab widths to fit a single visible row."""
        if not base_widths:
            return []
        if sum(base_widths) <= available_width:
            return base_widths

        total = sum(base_widths)
        scaled = [
            max(_MIN_SINGLE_ROW_WIDTH, (width * available_width) // total) for width in base_widths
        ]
        assigned = sum(scaled)
        remainder = available_width - assigned

        index = 0
        while remainder > 0:
            scaled[index % len(scaled)] += 1
            remainder -= 1
            index += 1

        index = 0
        while remainder < 0:
            target = index % len(scaled)
            if scaled[target] > _MIN_SINGLE_ROW_WIDTH:
                scaled[target] -= 1
                remainder += 1
            index += 1

        return scaled

    # -- Single-row layout ----------------------------------------------

    def _relayout_single_row(self: _TabLayoutMixin) -> None:
        """Lay out every tab on a single compressed row."""
        widget: QWidget = self  # type: ignore[assignment]
        content: QRect = widget.contentsRect()
        available_width = max(1, content.width() - (_PADDING_X * 2))
        count = len(self._entries)
        available_for_tabs = max(1, available_width - (_TAB_GAP * max(0, count - 1)))
        base_widths = [entry.button.sizeHint().width() for entry in self._entries]
        widths = self._fit_single_row_widths(base_widths, available_for_tabs)
        row_height = max(entry.button.sizeHint().height() for entry in self._entries)

        x = content.x() + _PADDING_X
        y = content.y() + _PADDING_Y
        for entry, width in zip(self._entries, widths, strict=False):
            entry.button.setGeometry(x, y, width, row_height)
            x += width + _TAB_GAP

        total_height = y + row_height + _PADDING_Y
        self._content_height = total_height
        self._scroll_y = 0
        if total_height != self._layout_height:
            self._layout_height = total_height
            widget.setFixedHeight(total_height)
        widget.updateGeometry()

    # -- Multi-row (wrapped) layout -------------------------------------

    def _relayout_tabs(self: _TabLayoutMixin) -> None:
        """Wrap the tab chips across multiple rows based on the current width."""
        widget: QWidget = self  # type: ignore[assignment]
        if not self._entries:
            self._layout_height = layout_config(self._small_labels).tab_height + (_PADDING_Y * 2)
            self._content_height = self._layout_height
            self._scroll_y = 0
            widget.setFixedHeight(self._layout_height)
            return

        if self._wrap_mode == "single_row":
            self._relayout_single_row()
            return

        content = widget.contentsRect()
        available_width = max(1, content.width() - (_PADDING_X * 2))
        row_start = content.x() + _PADDING_X
        x = row_start
        y = content.y() + _PADDING_Y
        row_height = 0

        for entry in self._entries:
            hint = entry.button.sizeHint()
            width = min(max(hint.width(), 92), available_width)
            height = hint.height()
            if x > row_start and x + width > row_start + available_width:
                x = row_start
                y += row_height + _ROW_GAP
                row_height = 0
            entry.button.setGeometry(x, y - self._scroll_y, width, height)
            x += width + _TAB_GAP
            row_height = max(row_height, height)

        total_height = y + row_height + _PADDING_Y
        self._content_height = total_height

        # Cap visible height at _MAX_VISIBLE_ROWS rows.
        single_row = row_height + _ROW_GAP if row_height else 0
        max_height = (_PADDING_Y * 2) + (_MAX_VISIBLE_ROWS * single_row) - _ROW_GAP
        clamped = min(total_height, max_height)

        # Clamp scroll offset to valid range.
        max_offset = max(0, total_height - clamped)
        self._scroll_y = max(0, min(self._scroll_y, max_offset))

        if clamped != self._layout_height:
            self._layout_height = clamped
            widget.setFixedHeight(clamped)
        widget.updateGeometry()

    # -- Auto-scroll to active tab --------------------------------------

    def _ensure_current_visible(self: _TabLayoutMixin) -> None:
        """Scroll so the currently selected tab is within the visible area."""
        if self._current_index < 0 or self._current_index >= len(self._entries):
            return
        if self._content_height <= self._layout_height:
            return
        btn = self._entries[self._current_index].button
        # Button geometry uses the scroll-offset coordinate system,
        # so the original (unscrolled) top is btn.y() + scroll_y.
        top = btn.y() + self._scroll_y
        bottom = top + btn.height()
        if top < self._scroll_y:
            self._scroll_y = top
        elif bottom > self._scroll_y + self._layout_height:
            self._scroll_y = bottom - self._layout_height
        self._relayout_tabs()
