"""Item delegate for ``{{variable}}`` highlighting in key-value table cells."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QModelIndex, QPersistentModelIndex, QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QHelpEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QAbstractItemView, QStyledItemDelegate, QStyleOptionViewItem, QWidget

if TYPE_CHECKING:
    from services.environment_service import VariableDetail

# Regex for {{variable}} references
_VAR_RE = re.compile(r"\{\{(.+?)\}\}")

# Padding (px) around the highlight box
_HIGHLIGHT_PAD_X = 2
_HIGHLIGHT_PAD_Y = 1
_HIGHLIGHT_RADIUS = 3


class _VariableHighlightDelegate(QStyledItemDelegate):
    """Delegate that highlights ``{{variable}}`` patterns with a coloured background.

    Only columns listed in *highlight_columns* are processed; other
    columns fall through to the default paint implementation.
    """

    def __init__(
        self,
        highlight_columns: set[int],
        parent: QWidget | None = None,
    ) -> None:
        """Initialise with the set of column indices to highlight."""
        super().__init__(parent)
        self._columns = highlight_columns
        self._variable_map: dict[str, VariableDetail] = {}

    def set_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Update the variable resolution map for tooltips."""
        self._variable_map = variables

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint the cell, overlaying variable highlights when present."""
        if index.column() not in self._columns:
            super().paint(painter, option, index)
            return

        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text or "{{" not in text:
            super().paint(painter, option, index)
            return

        self.initStyleOption(option, index)
        option.text = ""
        style = option.widget.style() if option.widget else None
        if style:
            style.drawControl(
                style.ControlElement.CE_ItemViewItem,
                option,
                painter,
                option.widget,
            )

        text_rect = option.rect.adjusted(4, 0, -4, 0)

        painter.save()
        painter.setClipRect(text_rect)

        fm = QFontMetrics(option.font)
        y_center = text_rect.top() + (text_rect.height() + fm.ascent() - fm.descent()) // 2

        from ui.styling.theme import (
            COLOR_VARIABLE_HIGHLIGHT,
            COLOR_VARIABLE_UNRESOLVED_HIGHLIGHT,
            COLOR_VARIABLE_UNRESOLVED_TEXT,
            COLOR_WARNING,
        )

        hl_bg = QColor(COLOR_VARIABLE_HIGHLIGHT)
        hl_fg = QColor(COLOR_WARNING)
        unresolved_bg = QColor(COLOR_VARIABLE_UNRESOLVED_HIGHLIGHT)
        unresolved_fg = QColor(COLOR_VARIABLE_UNRESOLVED_TEXT)

        x = text_rect.left()
        pos = 0
        full_text: str = text
        for match in _VAR_RE.finditer(full_text):
            if match.start() > pos:
                normal = full_text[pos : match.start()]
                painter.setPen(option.palette.color(option.palette.ColorRole.Text))
                painter.drawText(x, y_center, normal)
                x += fm.horizontalAdvance(normal)
            var_name = match.group(1)
            resolved = var_name in self._variable_map
            var_text = match.group(0)
            var_w = fm.horizontalAdvance(var_text)
            bg_rect = QRect(
                x - _HIGHLIGHT_PAD_X,
                text_rect.top() + (text_rect.height() - fm.height()) // 2 - _HIGHLIGHT_PAD_Y,
                var_w + 2 * _HIGHLIGHT_PAD_X,
                fm.height() + 2 * _HIGHLIGHT_PAD_Y,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(hl_bg if resolved else unresolved_bg)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.drawRoundedRect(bg_rect, _HIGHLIGHT_RADIUS, _HIGHLIGHT_RADIUS)
            painter.setPen(hl_fg if resolved else unresolved_fg)
            painter.drawText(x, y_center, var_text)
            x += var_w
            pos = match.end()
        if pos < len(full_text):
            painter.setPen(option.palette.color(option.palette.ColorRole.Text))
            painter.drawText(x, y_center, full_text[pos:])

        painter.restore()

    def helpEvent(
        self,
        event: QHelpEvent,
        view: QAbstractItemView,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """Suppress default tooltip for variable cells."""
        if event.type() == QEvent.Type.ToolTip and index.column() in self._columns:
            text = index.data(Qt.ItemDataRole.DisplayRole)
            if text and "{{" in text:
                return True
        return super().helpEvent(event, view, option, index)

    def var_at_pos(
        self,
        pos: QMouseEvent,
        view: QAbstractItemView,
    ) -> str | None:
        """Return the variable name at pixel *pos*, or ``None``."""
        mouse_pos = pos.position().toPoint()
        index = view.indexAt(mouse_pos)
        if not index.isValid() or index.column() not in self._columns:
            return None
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text or "{{" not in text:
            return None

        option = QStyleOptionViewItem()
        self.initStyleOption(option, index)
        option.rect = view.visualRect(index)
        text_rect = option.rect.adjusted(4, 0, -4, 0)
        fm = QFontMetrics(option.font)
        mouse_x = mouse_pos.x()

        x = text_rect.left()
        char_pos = 0
        for match in _VAR_RE.finditer(text):
            if match.start() > char_pos:
                x += fm.horizontalAdvance(text[char_pos : match.start()])
            var_w = fm.horizontalAdvance(match.group(0))
            if x <= mouse_x <= x + var_w:
                return match.group(1)
            x += var_w
            char_pos = match.end()

        return None
