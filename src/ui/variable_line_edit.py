"""QLineEdit subclass that highlights ``{{variable}}`` references.

Draws coloured background rectangles behind each ``{{name}}`` pattern
and shows the resolved variable value in a tooltip on hover.
"""

from __future__ import annotations

import re
from typing import cast

from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import (
    QColor,
    QHelpEvent,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import QLineEdit, QStyle, QStyleOptionFrame, QToolTip, QWidget

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
        self._variable_map: dict[str, str] = {}

    def set_variable_map(self, variables: dict[str, str]) -> None:
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

        from ui.theme import COLOR_VARIABLE_HIGHLIGHT, COLOR_WARNING

        hl_bg = QColor(COLOR_VARIABLE_HIGHLIGHT)
        hl_fg = QColor(COLOR_WARNING)

        content = self._content_rect()
        dx = self._scroll_offset()
        fm = self.fontMetrics()
        y_mid = content.top() + (content.height() - fm.height()) // 2

        painter = QPainter(self)
        painter.setClipRect(content)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for match in matches:
            var_text = match.group(0)
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
            painter.setBrush(hl_bg)
            painter.drawRoundedRect(bg_rect, _HIGHLIGHT_RADIUS, _HIGHLIGHT_RADIUS)

            # Redraw variable text in the warning colour on top
            painter.setPen(hl_fg)
            painter.drawText(
                start_x,
                content.top() + (content.height() + fm.ascent() - fm.descent()) // 2,
                var_text,
            )

        painter.end()

    # -- Tooltip ---------------------------------------------------------

    def event(self, ev: QEvent) -> bool:
        """Show resolved variable value as tooltip on hover."""
        if ev.type() == QEvent.Type.ToolTip:
            help_ev = cast("QHelpEvent", ev)
            text = self.text()
            if "{{" in text:
                pos = help_ev.pos()
                content = self._content_rect()
                dx = self._scroll_offset()
                fm = self.fontMetrics()
                mouse_x = pos.x()

                for match in _VAR_RE.finditer(text):
                    start_x = content.left() + fm.horizontalAdvance(text[: match.start()]) - dx
                    end_x = start_x + fm.horizontalAdvance(match.group(0))
                    if start_x <= mouse_x <= end_x:
                        var_name = match.group(1)
                        resolved = self._variable_map.get(var_name)
                        if resolved is not None:
                            QToolTip.showText(
                                help_ev.globalPos(),
                                f"{var_name} = {resolved}",
                                self,
                            )
                        else:
                            QToolTip.showText(
                                help_ev.globalPos(),
                                f"{var_name} (unresolved)",
                                self,
                            )
                        return True
            QToolTip.hideText()
            return True
        return super().event(ev)
