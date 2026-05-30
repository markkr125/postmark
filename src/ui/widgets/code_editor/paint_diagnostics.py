"""Line-number gutter painter — severity colouring and diff stripes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent

from ui.widgets.code_editor.gutter import line_worst_validation_severity

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPlainTextEdit


def paint_line_number_area(editor: QPlainTextEdit, event: QPaintEvent) -> None:
    """Paint line numbers, error markers, and diff stripes in the gutter."""
    p = editor._editor_palette()  # type: ignore[attr-defined]
    painter = QPainter(editor._line_number_area)  # type: ignore[attr-defined]
    painter.fillRect(event.rect(), QColor(p["editor_gutter_bg"]))

    line_severity = line_worst_validation_severity(editor._errors)  # type: ignore[attr-defined]
    diff_colors = editor._diff_line_colors  # type: ignore[attr-defined]

    block = editor.firstVisibleBlock()
    block_number = block.blockNumber()
    top = round(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
    bottom = top + round(editor.blockBoundingRect(block).height())
    width = editor._line_number_area.width()  # type: ignore[attr-defined]
    line_height = editor.fontMetrics().height()

    while block.isValid() and top <= event.rect().bottom():
        if block.isVisible() and bottom >= event.rect().top():
            number = str(block_number + 1)
            line_num = block_number + 1
            sev = line_severity.get(line_num)

            if block_number in diff_colors:
                painter.fillRect(0, top, 3, bottom - top, diff_colors[block_number])

            if sev is not None:
                if sev == "warning":
                    painter.fillRect(
                        0,
                        top,
                        width,
                        bottom - top,
                        QColor(p["editor_warning_gutter_bg"]),
                    )
                    painter.setPen(QColor(p["editor_warning_underline"]))
                elif sev == "info":
                    painter.fillRect(
                        0,
                        top,
                        width,
                        bottom - top,
                        QColor(p["editor_info_gutter_bg"]),
                    )
                    painter.setPen(QColor(p["editor_info_underline"]))
                elif sev == "hint":
                    painter.fillRect(
                        0,
                        top,
                        width,
                        bottom - top,
                        QColor(p["editor_hint_gutter_bg"]),
                    )
                    painter.setPen(QColor(p["editor_hint_underline"]))
                else:
                    painter.fillRect(
                        0,
                        top,
                        width,
                        bottom - top,
                        QColor(p["editor_error_gutter_bg"]),
                    )
                    painter.setPen(QColor(p["editor_error_underline"]))
            else:
                painter.setPen(QColor(p["editor_gutter_text"]))

            painter.drawText(
                0,
                top,
                width - 4,
                line_height,
                Qt.AlignmentFlag.AlignRight,
                number,
            )

        block = block.next()
        top = bottom
        bottom = top + round(editor.blockBoundingRect(block).height())
        block_number += 1

    painter.end()
