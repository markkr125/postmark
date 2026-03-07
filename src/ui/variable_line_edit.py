"""QLineEdit subclass that highlights ``{{variable}}`` references.

Draws coloured background rectangles behind each ``{{name}}`` pattern
and shows the resolved variable details in a popup on hover.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QLineEdit, QStyle, QStyleOptionFrame, QWidget

if TYPE_CHECKING:
    from services.environment_service import VariableDetail

# Regex for {{variable}} references (shared with key_value_table)
_VAR_RE = re.compile(r"\{\{(.+?)\}\}")

# Padding and radius for the highlight box (consistent with KV delegate)
_HIGHLIGHT_PAD_X = 2
_HIGHLIGHT_PAD_Y = 1
_HIGHLIGHT_RADIUS = 3


class VariableLineEdit(QLineEdit):
    """``QLineEdit`` that highlights ``{{variable}}`` references.

    Call :meth:`set_variable_map` to provide a dict mapping variable
    names to their resolved values.  The highlight colour is read from
    the theme at paint time so theme changes apply automatically.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the variable-aware line edit."""
        super().__init__(parent)
        self._variable_map: dict[str, VariableDetail] = {}
        self.setMouseTracking(True)

        # Hover tracking for fast popup display
        self._hover_var: str | None = None
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._show_hover_popup)
        self._hover_global_pos = QPoint()

    def set_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Update the variable resolution map and repaint."""
        self._variable_map = variables
        self.update()

    # -- Painting -------------------------------------------------------

    def _content_rect(self) -> QRect:
        """Return the text content area inside the line edit frame."""
        opt = QStyleOptionFrame()
        self.initStyleOption(opt)
        style = self.style()
        if style is None:
            return self.rect()
        return style.subElementRect(QStyle.SubElement.SE_LineEditContents, opt, self)

    def _scroll_offset(self) -> int:
        """Return the horizontal pixel offset caused by scrolling.

        Uses the current cursor position and its cursor rect to compute
        how far the text has been scrolled.
        """
        fm = self.fontMetrics()
        text = self.text()
        cur_pos = self.cursorPosition()
        cur_rect = self.cursorRect()
        content = self._content_rect()
        logical_x = fm.horizontalAdvance(text[:cur_pos])
        return logical_x - (cur_rect.left() - content.left())

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the default line edit, then overlay variable highlights."""
        super().paintEvent(event)

        text = self.text()
        if "{{" not in text:
            return

        matches = list(_VAR_RE.finditer(text))
        if not matches:
            return

        from ui.theme import (COLOR_VARIABLE_HIGHLIGHT,
                              COLOR_VARIABLE_UNRESOLVED_HIGHLIGHT,
                              COLOR_VARIABLE_UNRESOLVED_TEXT, COLOR_WARNING)

        hl_bg = QColor(COLOR_VARIABLE_HIGHLIGHT)
        hl_fg = QColor(COLOR_WARNING)
        unresolved_bg = QColor(COLOR_VARIABLE_UNRESOLVED_HIGHLIGHT)
        unresolved_fg = QColor(COLOR_VARIABLE_UNRESOLVED_TEXT)

        content = self._content_rect()
        dx = self._scroll_offset()
        fm = self.fontMetrics()
        y_mid = content.top() + (content.height() - fm.height()) // 2

        painter = QPainter(self)
        painter.setClipRect(content)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for match in matches:
            var_text = match.group(0)
            var_name = match.group(1)
            resolved = var_name in self._variable_map
            start_x = content.left() + fm.horizontalAdvance(text[: match.start()]) - dx
            var_w = fm.horizontalAdvance(var_text)

            # Draw background pill
            bg_rect = QRect(
                start_x - _HIGHLIGHT_PAD_X,
                y_mid - _HIGHLIGHT_PAD_Y,
                var_w + 2 * _HIGHLIGHT_PAD_X,
                fm.height() + 2 * _HIGHLIGHT_PAD_Y,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(hl_bg if resolved else unresolved_bg)
            painter.drawRoundedRect(bg_rect, _HIGHLIGHT_RADIUS, _HIGHLIGHT_RADIUS)

            # Redraw variable text in the appropriate colour on top
            painter.setPen(hl_fg if resolved else unresolved_fg)
            painter.drawText(
                start_x,
                content.top() + (content.height() + fm.ascent() - fm.descent()) // 2,
                var_text,
            )

        painter.end()

    # -- Popup ----------------------------------------------------------

    def _var_at_pos(self, pos: QPoint) -> str | None:
        """Return the variable name at pixel *pos*, or ``None``."""
        text = self.text()
        if "{{" not in text:
            return None
        content = self._content_rect()
        dx = self._scroll_offset()
        fm = self.fontMetrics()
        mouse_x = pos.x()
        for match in _VAR_RE.finditer(text):
            start_x = content.left() + fm.horizontalAdvance(text[: match.start()]) - dx
            end_x = start_x + fm.horizontalAdvance(match.group(0))
            if start_x <= mouse_x <= end_x:
                return match.group(1)
        return None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Detect variable under cursor and schedule popup display."""
        super().mouseMoveEvent(event)
        var_name = self._var_at_pos(event.position().toPoint())
        if var_name:
            if var_name != self._hover_var:
                self._hover_var = var_name
                self._hover_global_pos = event.globalPosition().toPoint()
                from ui.variable_popup import VariablePopup

                self._hover_timer.start(VariablePopup.hover_delay_ms())
        else:
            if self._hover_var is not None:
                self._hover_var = None
                self._hover_timer.stop()

    def leaveEvent(self, event: QEvent) -> None:
        """Cancel pending hover when the mouse leaves the widget."""
        self._hover_var = None
        self._hover_timer.stop()
        super().leaveEvent(event)

    def _show_hover_popup(self) -> None:
        """Show the variable popup for the currently hovered variable."""
        if self._hover_var is None:
            return
        from ui.variable_popup import VariablePopup

        detail = self._variable_map.get(self._hover_var)
        VariablePopup.show_variable(self._hover_var, detail, self._hover_global_pos, self)

    def event(self, ev: QEvent) -> bool:
        """Suppress default tooltip when hovering over variables."""
        if ev.type() == QEvent.Type.ToolTip:
            # Variables are handled by mouseMoveEvent; swallow the event
            # so no native tooltip appears.
            return True
        return super().event(ev)
