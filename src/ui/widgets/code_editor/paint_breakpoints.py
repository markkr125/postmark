"""Breakpoint-gutter painter and click/hover handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen

from ui.widgets.code_editor.gutter import _BREAKPOINT_GUTTER_WIDTH

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPlainTextEdit


def paint_breakpoint_area(editor: QPlainTextEdit, event: QPaintEvent) -> None:
    """Paint breakpoint circles and debug line arrow in the gutter."""
    p = editor._editor_palette()  # type: ignore[attr-defined]
    painter = QPainter(editor._bp_gutter_area)  # type: ignore[attr-defined]
    painter.fillRect(event.rect(), QColor(p["editor_gutter_bg"]))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    bp_color = QColor(p["editor_breakpoint"])
    arrow_color = QColor(p["editor_debug_gutter_arrow"])
    debug_bg = QColor(p["editor_debug_line"])
    radius = 4.0

    block = editor.firstVisibleBlock()
    top = round(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
    bottom = top + round(editor.blockBoundingRect(block).height())

    while block.isValid() and top <= event.rect().bottom():
        if block.isVisible() and bottom >= event.rect().top():
            line = block.blockNumber()

            if editor._debug_line is not None and line == editor._debug_line:  # type: ignore[attr-defined]
                painter.fillRect(0, top, _BREAKPOINT_GUTTER_WIDTH, bottom - top, debug_bg)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(arrow_color)
                cx = _BREAKPOINT_GUTTER_WIDTH / 2.0
                cy = (top + bottom) / 2.0
                painter.drawPolygon(
                    [
                        QPoint(round(cx - 3), round(cy - 4)),
                        QPoint(round(cx + 4), round(cy)),
                        QPoint(round(cx - 3), round(cy + 4)),
                    ]
                )

            if line in editor._breakpoints:  # type: ignore[attr-defined]
                cx = _BREAKPOINT_GUTTER_WIDTH / 2.0
                cy = (top + bottom) / 2.0
                tll: set[int] = editor._top_level_lines  # type: ignore[attr-defined]
                unreachable = bool(tll) and line not in tll
                cond = editor._breakpoints.get(line)  # type: ignore[attr-defined]
                if unreachable:
                    painter.setPen(QPen(QColor(p["editor_breakpoint_unreachable"]), 1.25))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                elif cond:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(p["editor_breakpoint_conditional"]))
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(bp_color)
                painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
            elif (
                editor._breakpoint_hover_line is not None  # type: ignore[attr-defined]
                and line == editor._breakpoint_hover_line  # type: ignore[attr-defined]
                and not (
                    editor._debug_line is not None  # type: ignore[attr-defined]
                    and line == editor._debug_line  # type: ignore[attr-defined]
                )
            ):
                cx = _BREAKPOINT_GUTTER_WIDTH / 2.0
                cy = (top + bottom) / 2.0
                hover = QColor(bp_color)
                hover.setAlpha(200)
                painter.setPen(QPen(hover, 1.25))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

        block = block.next()
        top = bottom
        bottom = top + round(editor.blockBoundingRect(block).height())

    painter.end()


def line_at_gutter_y(editor: QPlainTextEdit, y: float) -> int | None:
    """Return 0-based line index for *y* in gutter widget coordinates, or ``None``."""
    block = editor.firstVisibleBlock()
    top = round(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
    bottom = top + round(editor.blockBoundingRect(block).height())

    while block.isValid():
        if top <= y <= bottom:
            return block.blockNumber()
        block = block.next()
        top = bottom
        bottom = top + round(editor.blockBoundingRect(block).height())
    return None


def breakpoint_gutter_clicked(editor: QPlainTextEdit, y: int) -> None:
    """Toggle breakpoint for the block at viewport y-coordinate *y*."""
    line = line_at_gutter_y(editor, float(y))
    if (
        line is not None
        and editor._show_breakpoint_gutter  # type: ignore[attr-defined]
        and not editor._read_only  # type: ignore[attr-defined]
    ):
        editor.toggle_breakpoint(line)  # type: ignore[attr-defined]


def set_breakpoint_hover_line(editor: QPlainTextEdit, line: int | None) -> None:
    """Update breakpoint hover preview line (``None`` clears)."""
    if editor._breakpoint_hover_line == line:  # type: ignore[attr-defined]
        return
    editor._breakpoint_hover_line = line  # type: ignore[attr-defined]
    editor._bp_gutter_area.update()  # type: ignore[attr-defined]
    sched = getattr(editor, "_schedule_breakpoint_hover_tooltip", None)
    if callable(sched):
        sched()


def update_breakpoint_hover_for_gutter_y(editor: QPlainTextEdit, y: float) -> None:
    """Set hover preview from gutter-local *y*; clears when debugging gutter is hidden."""
    if not editor._show_breakpoint_gutter or editor._read_only:  # type: ignore[attr-defined]
        set_breakpoint_hover_line(editor, None)
        return
    set_breakpoint_hover_line(editor, line_at_gutter_y(editor, y))
