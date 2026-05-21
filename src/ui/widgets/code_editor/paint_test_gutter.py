"""Per-test gutter painter — run marker next to ``pm.test`` lines."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPolygonF

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPlainTextEdit


def paint_test_gutter_area(editor: QPlainTextEdit, event: QPaintEvent) -> None:
    """Paint a run marker next to each line with a ``pm.test`` call."""
    tw = editor.test_gutter_width()  # type: ignore[attr-defined]
    if tw <= 0:
        return
    p = editor._editor_palette()  # type: ignore[attr-defined]
    painter = QPainter(editor._test_gutter_area)  # type: ignore[attr-defined]
    painter.fillRect(event.rect(), QColor(p["editor_gutter_bg"]))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    mark = QColor(p["success"])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(mark)
    test_lines: dict[int, str] = {t["line"]: t["name"] for t in editor._pm_tests}  # type: ignore[attr-defined]
    block = editor.firstVisibleBlock()
    top = round(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
    bottom = top + round(editor.blockBoundingRect(block).height())
    while block.isValid() and top <= event.rect().bottom():
        if (
            block.isVisible()
            and bottom >= event.rect().top()
            and block.blockNumber() + 1 in test_lines
            and event.rect().intersects(QRect(0, int(top), tw, int(bottom - top)))
        ):
            h = bottom - top
            cy = top + h / 2.0
            side = min(10.0, max(2.0, h - 4.0))
            left = (tw - side) / 2.0
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(left, cy - side / 2.0),
                        QPointF(left + side, cy),
                        QPointF(left, cy + side / 2.0),
                    ]
                )
            )
        block = block.next()
        top = bottom
        bottom = top + round(editor.blockBoundingRect(block).height())
    painter.end()
