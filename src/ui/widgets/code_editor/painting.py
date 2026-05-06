"""Painting mixin for the code editor.

Provides ``_PaintingMixin`` containing the heavy rendering methods:

* ``paintEvent`` — indent guides and collapsed-fold badges.
* ``paint_line_number_area`` / ``paint_fold_gutter_area`` — gutter
  rendering.
* ``_paint_selection_whitespace`` — whitespace dot overlay.
* Gutter geometry (``line_number_area_width``, ``_total_gutter_width``, etc.):
  left-to-right — line numbers, ``pm.test`` column, breakpoint column, fold column
  (matches JetBrains).

Must be combined with ``QPlainTextEdit`` (via ``CodeEditorWidget``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygonF,
    QTextBlock,
    QTextCursor,
)

from ui.styling.icons import font_family, glyph_char
from ui.widgets.code_editor.gutter import (
    _BREAKPOINT_GUTTER_WIDTH,
    _FOLD_BADGE_GAP,
    _FOLD_BADGE_H_PAD,
    _FOLD_BADGE_LABEL,
    _FOLD_BADGE_RADIUS,
    _FOLD_GUTTER_WIDTH,
    _FOLDABLE_LANGUAGES,
    _GUTTER_PADDING,
    _MINIMAP_WIDTH,
    _WHITESPACE_DOT_RADIUS,
    SyntaxError_,
    _BreakpointGutterArea,
    _FoldGutterArea,
    _LineNumberArea,
    _MinimapArea,
    _TestGutterArea,
)

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPlainTextEdit

    from ui.styling.theme import ThemePalette

    _PaintingBase = QPlainTextEdit
else:
    _PaintingBase = object


class _PaintingMixin(_PaintingBase):
    """Mixin providing painting and gutter geometry for the code editor."""

    # -- Attribute stubs (set by CodeEditorWidget.__init__) -------------
    _language: str
    _line_number_area: _LineNumberArea
    _fold_gutter_area: _FoldGutterArea
    _bp_gutter_area: _BreakpointGutterArea
    _test_gutter_area: _TestGutterArea
    _test_gutter_enabled: bool
    _pm_tests: list[dict[str, Any]]
    _detected_indent: int
    _sorted_folds: list[tuple[int, int, int]]
    _collapsed_folds: set[int]
    _fold_badge_rects: dict[int, QRect]
    _errors: list[SyntaxError_]
    _fold_regions: dict[int, int]
    _fold_font: QFont | None
    _breakpoints: set[int]
    _top_level_lines: set[int]
    _debug_line: int | None
    _show_breakpoint_gutter: bool
    _breakpoint_hover_line: int | None
    _read_only: bool
    _minimap: _MinimapArea
    _show_minimap: bool
    _diff_line_colors: dict[int, QColor]

    if TYPE_CHECKING:

        def toggle_fold(self, line: int) -> None: ...

        def toggle_breakpoint(self, line: int) -> bool: ...

        def test_gutter_width(self) -> int: ...

        def _editor_palette(self) -> ThemePalette: ...

    # -- Selection whitespace dots --------------------------------------

    def _paint_selection_whitespace(self, cursor: QTextCursor) -> None:
        """Draw small dots at each space character inside the current selection."""
        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()

        fm = self.fontMetrics()
        space_px = fm.horizontalAdvance(" ")
        if space_px <= 0:
            return

        content_offset = self.contentOffset()
        vp_top = self.viewport().rect().top()
        vp_bottom = self.viewport().rect().bottom()

        p = self._editor_palette()
        dot_color = QColor(p["editor_whitespace_dot"])
        radius = _WHITESPACE_DOT_RADIUS

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot_color)

        block = self.firstVisibleBlock()
        while block.isValid():
            geom = self.blockBoundingGeometry(block).translated(content_offset)
            if geom.top() > vp_bottom:
                break
            block_pos = block.position()
            block_len = block.length() - 1
            block_end = block_pos + block_len

            if block_end < sel_start or block_pos > sel_end:
                block = block.next()
                continue

            if block.isVisible() and geom.bottom() >= vp_top:
                text = block.text()
                layout = block.layout()
                local_start = max(0, sel_start - block_pos)
                local_end = min(len(text), sel_end - block_pos)

                for i in range(local_start, local_end):
                    if text[i] != " ":
                        continue
                    line = layout.lineForTextPosition(i)
                    if not line.isValid():
                        continue
                    x_tuple: tuple[float, int] = line.cursorToX(i)  # type: ignore[assignment]
                    x = content_offset.x() + x_tuple[0]
                    cx = x + space_px / 2.0
                    cy = geom.top() + line.y() + line.height() / 2.0
                    painter.drawEllipse(
                        QRectF(
                            cx - radius,
                            cy - radius,
                            radius * 2,
                            radius * 2,
                        )
                    )

            block = block.next()

        painter.end()

    # -- Gutter geometry ------------------------------------------------

    def line_number_area_width(self) -> int:
        """Calculate the width needed for line numbers."""
        digits = max(1, len(str(self.blockCount())))
        return _GUTTER_PADDING + self.fontMetrics().horizontalAdvance("9") * digits + 4

    def _total_gutter_width(self) -> int:
        """Return total width of line-number + test + breakpoint + fold gutters (JetBrains order)."""
        test_w = self.test_gutter_width() if self._test_gutter_enabled else 0
        bp_w = _BREAKPOINT_GUTTER_WIDTH if self._show_breakpoint_gutter else 0
        fold_w = _FOLD_GUTTER_WIDTH if self._language in _FOLDABLE_LANGUAGES else 0
        return self.line_number_area_width() + test_w + bp_w + fold_w

    def _update_gutter_width(self) -> None:
        """Update the left margin to accommodate gutters."""
        right = _MINIMAP_WIDTH if self._show_minimap else 0
        self.setViewportMargins(self._total_gutter_width(), 0, right, 0)

    def _update_gutters(self, rect: QRect, dy: int) -> None:
        """Scroll and repaint gutters when the viewport changes."""
        if dy:
            self._line_number_area.scroll(0, dy)
            self._test_gutter_area.scroll(0, dy)
            self._bp_gutter_area.scroll(0, dy)
            self._fold_gutter_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(), self._line_number_area.width(), rect.height()
            )
            self._test_gutter_area.update(
                0, rect.y(), self._test_gutter_area.width(), rect.height()
            )
            self._bp_gutter_area.update(0, rect.y(), self._bp_gutter_area.width(), rect.height())
            self._fold_gutter_area.update(
                0, rect.y(), self._fold_gutter_area.width(), rect.height()
            )
            self._minimap.update()
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event) -> None:
        """Reposition gutter widgets on resize."""
        super().resizeEvent(event)
        cr = self.contentsRect()
        x_offset = cr.left()

        ln_w = self.line_number_area_width()
        self._line_number_area.setGeometry(QRect(x_offset, cr.top(), ln_w, cr.height()))
        x_offset += ln_w

        test_w = self.test_gutter_width() if self._test_gutter_enabled else 0
        self._test_gutter_area.setGeometry(QRect(x_offset, cr.top(), test_w, cr.height()))
        x_offset += test_w

        bp_w = _BREAKPOINT_GUTTER_WIDTH if self._show_breakpoint_gutter else 0
        self._bp_gutter_area.setGeometry(QRect(x_offset, cr.top(), bp_w, cr.height()))
        x_offset += bp_w

        fold_w = _FOLD_GUTTER_WIDTH if self._language in _FOLDABLE_LANGUAGES else 0
        self._fold_gutter_area.setGeometry(QRect(x_offset, cr.top(), fold_w, cr.height()))

        # Minimap on the right edge
        if self._show_minimap:
            self._minimap.setGeometry(
                QRect(cr.right() - _MINIMAP_WIDTH + 1, cr.top(), _MINIMAP_WIDTH, cr.height())
            )

    # -- Indent guides & badges (main paintEvent) -----------------------

    @staticmethod
    def _effective_indent(block: QTextBlock) -> int:
        """Return the effective indent (in spaces) for *block*.

        For non-blank lines this is just the leading whitespace count.
        For blank lines, scan both neighbours and return the max.
        """
        txt = block.text()
        if txt.strip():
            return len(txt) - len(txt.lstrip())
        fwd = 0
        blk = block.next()
        while blk.isValid():
            t = blk.text()
            if t.strip():
                fwd = len(t) - len(t.lstrip())
                break
            blk = blk.next()
        bwd = 0
        blk = block.previous()
        while blk.isValid():
            t = blk.text()
            if t.strip():
                bwd = len(t) - len(t.lstrip())
                break
            blk = blk.previous()
        return max(fwd, bwd)

    def _active_indent_col(self, cursor_line: int) -> tuple[int, int, int]:
        """Return the active guide info for the cursor's innermost fold.

        Returns ``(column, fold_start_line, fold_end_line)``.
        Returns ``(-1, -1, -1)`` when the cursor is not inside any fold.
        """
        iw = self._detected_indent
        best_col = -1
        best_start = -1
        best_end = -1
        best_span = float("inf")
        for start_line, end_line, leading in self._sorted_folds:
            if start_line <= cursor_line <= end_line:
                span = end_line - start_line
                if span < best_span:
                    best_span = span
                    best_col = leading - (leading % iw) if iw else 0
                    best_start = start_line
                    best_end = end_line
        return (best_col, best_start, best_end)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint indent guides and collapsed-fold badges."""
        super().paintEvent(event)

        cursor = self.textCursor()
        if cursor.hasSelection():
            self._paint_selection_whitespace(cursor)

        if self._language not in _FOLDABLE_LANGUAGES:
            self._fold_badge_rects = {}
            return

        fm = self.fontMetrics()
        space_px = fm.horizontalAdvance(" ")
        if space_px <= 0:
            self._fold_badge_rects = {}
            return

        p = self._editor_palette()
        content_offset = self.contentOffset()
        base_x = self.document().documentMargin() + content_offset.x()
        doc = self.document()
        vp_top = self.viewport().rect().top()
        vp_bottom = self.viewport().rect().bottom()

        normal_pen = QPen(QColor(p["editor_indent_guide"]))
        normal_pen.setWidth(1)
        active_pen = QPen(QColor(p["editor_active_indent_guide"]))
        active_pen.setWidth(1)

        painter = QPainter(self.viewport())

        # 1. Indent guides
        cursor_line = self.textCursor().blockNumber()
        active_col, active_start, active_end = self._active_indent_col(cursor_line)
        iw = self._detected_indent

        block = self.firstVisibleBlock()
        while block.isValid():
            geom = self.blockBoundingGeometry(block).translated(content_offset)
            if geom.top() > vp_bottom:
                break
            if block.isVisible() and geom.bottom() >= vp_top:
                indent = self._effective_indent(block)
                layout = block.layout()
                line0 = layout.lineAt(0) if layout.lineCount() > 0 else None
                block_line = block.blockNumber()
                level = 1
                while level * iw <= indent:
                    draw_col = (level - 1) * iw
                    if line0 is not None:
                        cursor_x: tuple[float, int] = line0.cursorToX(draw_col)  # type: ignore[assignment]
                        x = round(content_offset.x() + cursor_x[0])
                    else:
                        x = round(base_x + draw_col * space_px)
                    top_y = round(geom.top())
                    bot_y = round(geom.bottom())
                    is_active = draw_col == active_col and active_start <= block_line <= active_end
                    painter.setPen(active_pen if is_active else normal_pen)
                    painter.drawLine(x, top_y, x, bot_y)
                    level += 1
            block = block.next()

        # 2. Collapsed-fold "..." badges
        badge_rects: dict[int, QRect] = {}
        if self._collapsed_folds:
            badge_bg = QColor(p["editor_fold_badge_bg"])
            badge_fg = QColor(p["editor_fold_badge_text"])
            badge_w = fm.horizontalAdvance(_FOLD_BADGE_LABEL) + _FOLD_BADGE_H_PAD * 2
            badge_h = fm.height() - 2

            for start_line in self._collapsed_folds:
                block = doc.findBlockByNumber(start_line)
                if not block.isValid() or not block.isVisible():
                    continue

                geom = self.blockBoundingGeometry(block).translated(content_offset)
                if geom.bottom() < vp_top or geom.top() > vp_bottom:
                    continue

                text_width = fm.horizontalAdvance(block.text())
                bx = round(base_x + text_width + _FOLD_BADGE_GAP)
                by = round(geom.top() + (geom.height() - badge_h) / 2)
                rect = QRect(bx, by, badge_w, badge_h)

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(badge_bg)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.drawRoundedRect(QRectF(rect), _FOLD_BADGE_RADIUS, _FOLD_BADGE_RADIUS)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

                painter.setPen(badge_fg)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, _FOLD_BADGE_LABEL)

                badge_rects[start_line] = rect

        self._fold_badge_rects = badge_rects
        painter.end()

    # -- Line number painting -------------------------------------------

    def paint_line_number_area(self, event: QPaintEvent) -> None:
        """Paint line numbers, error markers, and diff stripes in the gutter."""
        p = self._editor_palette()
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor(p["editor_gutter_bg"]))

        error_lines = {e.line for e in self._errors if e.severity == "error"}
        warning_lines = {e.line for e in self._errors if e.severity == "warning"}
        diff_colors = self._diff_line_colors

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        width = self._line_number_area.width()
        line_height = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                line_num = block_number + 1
                is_error = line_num in error_lines
                is_warning = line_num in warning_lines and not is_error

                # Diff gutter stripe (3px on the left edge)
                if block_number in diff_colors:
                    painter.fillRect(0, top, 3, bottom - top, diff_colors[block_number])

                if is_error:
                    painter.fillRect(
                        0,
                        top,
                        width,
                        bottom - top,
                        QColor(p["editor_error_gutter_bg"]),
                    )
                    painter.setPen(QColor(p["editor_error_underline"]))
                elif is_warning:
                    painter.fillRect(
                        0,
                        top,
                        width,
                        bottom - top,
                        QColor(p["editor_warning_gutter_bg"]),
                    )
                    painter.setPen(QColor(p["editor_warning_underline"]))
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
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

        painter.end()

    # -- Fold gutter painting -------------------------------------------

    def paint_fold_gutter_area(self, event: QPaintEvent) -> None:
        """Paint fold indicators (Phosphor chevrons) in the fold gutter."""
        if self._language not in _FOLDABLE_LANGUAGES:
            return

        p = self._editor_palette()
        painter = QPainter(self._fold_gutter_area)
        painter.fillRect(event.rect(), QColor(p["editor_gutter_bg"]))

        caret_right = glyph_char("caret-right-light")
        caret_down = glyph_char("caret-down-light")
        if self._fold_font is None:
            phi_family = font_family()
            if phi_family:
                f = QFont(phi_family)
                f.setPixelSize(16)
                self._fold_font = f
        if self._fold_font is not None:
            painter.setFont(self._fold_font)

        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line = block.blockNumber()
                if line in self._fold_regions:
                    is_collapsed = line in self._collapsed_folds
                    glyph = caret_right if is_collapsed else caret_down

                    if self._fold_font is not None and glyph:
                        painter.setPen(QColor(p["editor_fold_indicator"]))
                        painter.drawText(
                            0,
                            top,
                            _FOLD_GUTTER_WIDTH,
                            bottom - top,
                            Qt.AlignmentFlag.AlignCenter,
                            glyph,
                        )
                    else:
                        painter.setPen(QColor(p["editor_fold_indicator"]))
                        fallback = "\u203a" if is_collapsed else "\u2304"
                        painter.drawText(
                            0,
                            top,
                            _FOLD_GUTTER_WIDTH,
                            bottom - top,
                            Qt.AlignmentFlag.AlignCenter,
                            fallback,
                        )

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())

        painter.end()

    def is_fold_line_at(self, y: int) -> bool:
        """Return True if the viewport y-coordinate *y* is on a foldable line."""
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid():
            if top <= y <= bottom:
                return block.blockNumber() in self._fold_regions
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
        return False

    def fold_gutter_clicked(self, y: int) -> None:
        """Toggle fold for the block at viewport y-coordinate *y*, or breakpoint if no fold."""
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid():
            if top <= y <= bottom:
                line = block.blockNumber()
                if line in self._fold_regions:
                    self.toggle_fold(line)
                elif self._show_breakpoint_gutter and not self._read_only:
                    self.toggle_breakpoint(line)
                return
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())

    # -- Breakpoint gutter painting -------------------------------------

    def paint_breakpoint_area(self, event: QPaintEvent) -> None:
        """Paint breakpoint circles and debug line arrow in the gutter."""
        p = self._editor_palette()
        painter = QPainter(self._bp_gutter_area)
        painter.fillRect(event.rect(), QColor(p["editor_gutter_bg"]))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        bp_color = QColor(p["editor_breakpoint"])
        arrow_color = QColor(p["editor_debug_gutter_arrow"])
        debug_bg = QColor(p["editor_debug_line"])
        radius = 4.0

        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line = block.blockNumber()

                # Debug line background + arrow.
                if self._debug_line is not None and line == self._debug_line:
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

                # Breakpoint circle (hollow + muted when not a top-level checkpoint line).
                if line in self._breakpoints:
                    cx = _BREAKPOINT_GUTTER_WIDTH / 2.0
                    cy = (top + bottom) / 2.0
                    tll: set[int] = self._top_level_lines
                    unreachable = bool(tll) and line not in tll
                    if unreachable:
                        painter.setPen(QPen(QColor(p["editor_breakpoint_unreachable"]), 1.25))
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                    else:
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(bp_color)
                    painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
                elif (
                    self._breakpoint_hover_line is not None
                    and line == self._breakpoint_hover_line
                    and not (self._debug_line is not None and line == self._debug_line)
                ):
                    # Hover preview (JetBrains-style) — not shown on the active debug line.
                    cx = _BREAKPOINT_GUTTER_WIDTH / 2.0
                    cy = (top + bottom) / 2.0
                    hover = QColor(bp_color)
                    hover.setAlpha(200)
                    painter.setPen(QPen(hover, 1.25))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())

        painter.end()

    def paint_test_gutter_area(self, event: QPaintEvent) -> None:
        """Paint a run marker next to each line with a ``pm.test`` call."""
        tw = self.test_gutter_width()
        if tw <= 0:
            return
        p = self._editor_palette()
        painter = QPainter(self._test_gutter_area)
        painter.fillRect(event.rect(), QColor(p["editor_gutter_bg"]))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        mark = QColor(p["success"])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(mark)
        test_lines: dict[int, str] = {t["line"]: t["name"] for t in self._pm_tests}
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
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
            bottom = top + round(self.blockBoundingRect(block).height())
        painter.end()

    def _line_at_gutter_y(self, y: float) -> int | None:
        """Return 0-based line index for *y* in gutter widget coordinates, or ``None``."""
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid():
            if top <= y <= bottom:
                return block.blockNumber()
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
        return None

    def breakpoint_gutter_clicked(self, y: int) -> None:
        """Toggle breakpoint for the block at viewport y-coordinate *y*."""
        line = self._line_at_gutter_y(float(y))
        if line is not None and self._show_breakpoint_gutter and not self._read_only:
            self.toggle_breakpoint(line)

    def _set_breakpoint_hover_line(self, line: int | None) -> None:
        """Update breakpoint hover preview line (``None`` clears)."""
        if self._breakpoint_hover_line == line:
            return
        self._breakpoint_hover_line = line
        self._bp_gutter_area.update()
        sched = getattr(self, "_schedule_breakpoint_hover_tooltip", None)
        if callable(sched):
            sched()

    def _update_breakpoint_hover_for_gutter_y(self, y: float) -> None:
        """Set hover preview from gutter-local *y*; clears when debugging gutter is hidden."""
        if not self._show_breakpoint_gutter or self._read_only:
            self._set_breakpoint_hover_line(None)
            return
        self._set_breakpoint_hover_line(self._line_at_gutter_y(y))
