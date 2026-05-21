"""Inline log annotation painter (A4 feature).

Renders faint italic text after the visible end-of-line for ``console.log`` /
print captures. Called by :class:`_PaintingMixin` in :mod:`painting`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter

from ui.widgets.code_editor.gutter import _INLINE_LOG_ANNOT_MAX_PX

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPlainTextEdit


def _paint_inline_log_annotations(
    editor: QPlainTextEdit,
    painter: QPainter,
    content_offset: QPointF,
    vp_top: int,
    vp_bottom: int,
    base_x: float,
) -> None:
    """Draw faint trailing annotations for captured ``console.log`` lines."""
    annotations = getattr(editor, "_inline_log_annotations", None)
    if not annotations:
        return

    p = editor._editor_palette()  # type: ignore[attr-defined]
    color = QColor(p["editor_inline_log_text"])
    fm = editor.fontMetrics()
    italic = QFont(editor.font())
    italic.setItalic(True)
    painter.setFont(italic)
    painter.setPen(color)

    block = editor.firstVisibleBlock()
    while block.isValid():
        geom = editor.blockBoundingGeometry(block).translated(content_offset)
        if geom.top() > vp_bottom:
            break
        if block.isVisible() and geom.bottom() >= vp_top:
            line_no = block.blockNumber()
            text = annotations.get(line_no)
            if text:
                layout = block.layout()
                line0 = layout.lineAt(0) if layout.lineCount() > 0 else None
                if line0 is not None:
                    block_text = block.text()
                    end_col = len(block_text.rstrip())
                    if end_col > 0:
                        x_tuple: tuple[float, int] = line0.cursorToX(end_col)  # type: ignore[assignment]
                        x = round(content_offset.x() + x_tuple[0] + 8)
                    else:
                        x = round(base_x + 8)
                else:
                    x = round(base_x + fm.horizontalAdvance(block.text()) + 8)
                y = round(geom.top() + (geom.height() + fm.ascent() - fm.descent()) / 2)
                elided = fm.elidedText(
                    text,
                    Qt.TextElideMode.ElideRight,
                    _INLINE_LOG_ANNOT_MAX_PX,
                )
                painter.drawText(x, y, elided)
        block = block.next()
