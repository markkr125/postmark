"""Markdown answer body and theme re-render registry for assistant rows."""

from __future__ import annotations

import math
import weakref

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer, QUrl, QUrlQuery, Signal
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QColor,
    QCursor,
    QDesktopServices,
    QEnterEvent,
    QFont,
    QGuiApplication,
    QHoverEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPalette,
    QPen,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextTable,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QMenu, QScrollArea, QSizePolicy, QWidget
from shiboken6 import isValid

from ui.sidebar.ai.markdown.fence_split import fenced_code_sources
from ui.sidebar.ai.markdown.highlight_code import (
    COPY_LINK_FONT_PX,
    clear_highlight_cache,
    code_copy_href,
    copy_anchor_spans,
    copy_block_header_hit_rects,
    copy_block_index_at_document_pos,
    parse_code_copy_block_index,
)
from ui.sidebar.ai.markdown.streaming_render import StreamingMarkdownCache
from ui.sidebar.ai.message_bubble.wrapping_label import (
    find_ancestor_scroll_area,
    forward_wheel_to_ancestor_scroll_area,
)
from ui.styling.theme import COLOR_ASSISTANT_FOOTER_SEPARATOR, current_palette
from ui.styling.theme_manager import ThemeManager

_markdown_bodies: weakref.WeakSet[MarkdownContent] = weakref.WeakSet()
_theme_hook_installed = False
_SELECTION_DRAG_THRESHOLD_PX = 4
_AUTOSCROLL_EDGE_MARGIN_PX = 24
_AUTOSCROLL_INTERVAL_MS = 16
_AUTOSCROLL_MIN_STEP_PX = 2
_AUTOSCROLL_MAX_STEP_PX = 48
_COPY_CONFIRM_MS = 2000
_FOOTER_RULE_GAP_PX = 10
_FOOTER_RULE_DASH_PX = 5
_FOOTER_RULE_DASH_GAP_PX = 4


def rerender_all_markdown_browsers() -> None:
    """Re-render stored markdown when the application theme changes."""
    clear_highlight_cache()
    for body in list(_markdown_bodies):
        if not isValid(body):
            continue
        if body.is_render_deferred():
            continue
        if body.is_streaming():
            body._render_markdown_streaming()
        else:
            body._render_markdown()


def _install_markdown_theme_hook() -> None:
    """Connect ``ThemeManager.theme_changed`` once for all markdown bodies."""
    global _theme_hook_installed
    if _theme_hook_installed:
        return
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    for child in app.children():
        if isinstance(child, ThemeManager):
            child.theme_changed.connect(rerender_all_markdown_browsers)
            _theme_hook_installed = True
            return


class MarkdownContent(QWidget):
    """Read-only assistant body that renders Markdown and auto-grows to fit."""

    height_changed = Signal()
    workspace_target_requested = Signal(str, int, str)

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        """Configure markdown rendering, link handling, and height sync."""
        super().__init__(parent)
        self.setObjectName("aiChatAssistantText")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._document = QTextDocument(self)
        self._document.setDocumentMargin(0)
        self._markdown = ""
        self._streaming = False
        self._render_deferred = False
        self._stream_cache = StreamingMarkdownCache()
        self._stream_layout_floor_px = 0
        self._defer_height_changed = False
        self._height_changed_pending = False
        self._cached_text_width = -1
        self._cached_measured_height = -1
        self._reflow_deferred = False
        self._reflow_flush_pending = False
        self._layout_query_depth = 0
        self._last_sync_width = -1
        self._paint_footer_rule = False
        self._painted_content_height_px = 0
        self._selection_anchor: int | None = None
        self._selection_cursor: int | None = None
        self._press_position: QPointF | None = None
        self._copy_confirmed_index: int | None = None
        self._copy_hover_index: int | None = None
        self._copy_hit_rects: dict[int, QRectF] = {}
        self._copy_anchor_spans: dict[int, tuple[int, int]] = {}
        self._copy_confirm_timer = QTimer(self)
        self._copy_confirm_timer.setSingleShot(True)
        self._copy_confirm_timer.timeout.connect(self._clear_copy_confirmation)
        self._autoscroll_timer = QTimer(self)
        self._autoscroll_timer.setInterval(_AUTOSCROLL_INTERVAL_MS)
        self._autoscroll_timer.timeout.connect(self._on_autoscroll_tick)
        self._autoscroll_step = 0
        self._autoscroll_global_pos: QPoint | None = None
        self._scroll_hover_connected = False
        _markdown_bodies.add(self)
        _install_markdown_theme_hook()
        self._apply_document_defaults()
        if text:
            self.set_markdown(text)

    def document(self) -> QTextDocument:
        """Return the owned rich-text document."""
        return self._document

    def toHtml(self) -> str:
        """Return the rendered HTML document (for tests and diagnostics)."""
        return self._document.toHtml()

    def markdown(self) -> str:
        """Return the accumulated markdown source."""
        return self._markdown

    def is_streaming(self) -> bool:
        """Return whether an assistant reply is still streaming into this body."""
        return self._streaming

    def is_render_deferred(self) -> bool:
        """Return whether full markdown rendering is still pending."""
        return self._render_deferred

    def ensure_rendered(self) -> None:
        """Render deferred markdown when the row becomes visible."""
        if not self._render_deferred:
            return
        self._render_deferred = False
        self._render_markdown()

    def set_paint_footer_rule(self, paint: bool) -> None:
        """Paint a dashed rule below the answer when the turn footer is shown."""
        self._paint_footer_rule = paint
        self.resync_height_for_footer()
        self.update()

    def resync_height_for_footer(self) -> None:
        """Re-measure after deferred reflow or before footer chrome appears."""
        self._reflow_deferred = False
        self._reflow_flush_pending = False
        self._invalidate_measured_height()
        self._sync_height(force=True)

    def set_markdown_lazy(self, text: str) -> None:
        """Store markdown source and defer the expensive HTML pipeline."""
        self._streaming = False
        self._stream_cache.clear()
        self._markdown = text
        self._render_deferred = True
        self._invalidate_measured_height()
        line_h = max(1, self.fontMetrics().height())
        placeholder_lines = 3
        self.setFixedHeight(line_h * placeholder_lines)
        self.updateGeometry()

    def streaming_cache_segment_count(self) -> int:
        """Return the number of cached rendered segments (for tests)."""
        return self._stream_cache.segment_count

    def begin_streaming(self) -> None:
        """Mark the body as receiving incremental stream updates."""
        self._streaming = True
        self._stream_cache.clear()
        self._stream_layout_floor_px = 0

    def end_streaming(self, *, render: bool = True) -> None:
        """Leave streaming mode and optionally re-render the final markdown."""
        self._streaming = False
        self._stream_cache.clear()
        self._stream_layout_floor_px = 0
        if render:
            self._render_markdown()

    def set_markdown(self, text: str) -> None:
        """Replace the markdown source and re-render."""
        self._streaming = False
        self._stream_cache.clear()
        self._markdown = text
        self._render_markdown()

    def _set_document_html(self, html: str, *, preserve_selection: bool = False) -> None:
        """Replace document HTML and schedule a repaint."""
        if not preserve_selection:
            self._clear_selection()
        self._invalidate_measured_height()
        self._document.setHtml(html)
        self._rebuild_copy_hit_rects()
        if self._copy_hover_index is not None or self._copy_confirmed_index is not None:
            self._sync_copy_link_appearance()
        else:
            self.update()

    def _copy_anchor_char_format(
        self,
        block_index: int,
        color: QColor,
        *,
        underline: bool,
    ) -> QTextCharFormat:
        """Return anchor char format for a fenced-code Copy control."""
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        fmt.setFontUnderline(underline)
        fmt.setAnchor(True)
        fmt.setAnchorHref(code_copy_href(block_index))
        font = QFont("sans-serif")
        font.setPixelSize(COPY_LINK_FONT_PX)
        fmt.setFont(font)
        return fmt

    def _sync_copy_link_appearance(self) -> None:
        """Apply hover/copied accent and underline via in-place char formats."""
        if not self._copy_anchor_spans:
            self._copy_anchor_spans = copy_anchor_spans(self._document)
        if not self._copy_anchor_spans:
            self.update()
            return

        palette = current_palette()
        muted = QColor(palette["text_muted"])
        accent = QColor(palette["accent"])
        needs_rescan = False

        spans = sorted(
            self._copy_anchor_spans.items(),
            key=lambda item: item[1][0],
            reverse=True,
        )
        for block_index, (start, end) in spans:
            cursor = QTextCursor(self._document)
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            confirmed = block_index == self._copy_confirmed_index
            hovered = block_index == self._copy_hover_index and not confirmed
            label = "Copied" if confirmed else "Copy"
            active = accent if (confirmed or hovered) else muted

            if cursor.selectedText() != label:
                cursor.insertText(
                    label,
                    self._copy_anchor_char_format(block_index, active, underline=hovered),
                )
                needs_rescan = True
                continue

            fmt = QTextCharFormat()
            fmt.setForeground(active)
            fmt.setFontUnderline(hovered)
            cursor.mergeCharFormat(fmt)

        if needs_rescan:
            self._copy_anchor_spans = copy_anchor_spans(self._document)
        self.update()

    def _clear_copy_confirmation(self) -> None:
        """Revert a confirmed Copy label after the feedback timeout."""
        if self._copy_confirmed_index is None:
            return
        self._copy_confirmed_index = None
        self._sync_copy_link_appearance()

    def _rebuild_copy_hit_rects(self) -> None:
        """Refresh Copy-link hit rectangles and anchor spans after layout changes."""
        self._copy_hit_rects = copy_block_header_hit_rects(self._document)
        self._copy_anchor_spans = copy_anchor_spans(self._document)

    def _interactive_anchor_at(self, pos: QPointF) -> str | None:
        """Return the anchor href under *pos* when it should show a hand cursor."""
        anchor = self._document.documentLayout().anchorAt(pos)
        if not anchor:
            return None
        if parse_code_copy_block_index(anchor) is not None:
            return anchor
        url = QUrl(anchor)
        if url.isValid():
            return anchor
        return None

    def _sync_hover_cursor(self, pos: QPointF) -> None:
        """Use a text cursor over prose and a hand over links and Copy controls."""
        if self._copy_hover_index is not None or self._interactive_anchor_at(pos) is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.IBeamCursor)

    def _copy_block_index_at(self, pos: QPointF) -> int | None:
        """Return the fenced-code Copy index under widget-local *pos*, if any."""
        return copy_block_index_at_document_pos(self._document, pos)

    def _connect_transcript_scroll_hover(self) -> None:
        """Re-check Copy hover when the transcript scrolls under a stationary cursor."""
        if self._scroll_hover_connected:
            return
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                parent.verticalScrollBar().valueChanged.connect(self._on_transcript_scrolled)
                self._scroll_hover_connected = True
                return
            parent = parent.parentWidget()

    def _on_transcript_scrolled(self, _value: int) -> None:
        """Refresh Copy hover after scroll moves content under the pointer."""
        if not self.isVisible():
            return
        local = QPointF(self.mapFromGlobal(QCursor.pos()))
        if not self.rect().contains(local.toPoint()):
            if self._copy_hover_index is not None:
                self._copy_hover_index = None
                self._sync_copy_link_appearance()
            self.setCursor(Qt.CursorShape.IBeamCursor)
            return
        self._update_copy_hover(local)

    def _update_copy_hover(self, pos: QPointF) -> None:
        """Track hover over fenced-code Copy links for cursor and link styling."""
        hover_index = self._copy_block_index_at(pos)
        if hover_index == self._copy_hover_index:
            self._sync_hover_cursor(pos)
            return
        self._copy_hover_index = hover_index
        self._sync_hover_cursor(pos)
        self._sync_copy_link_appearance()

    def _invalidate_measured_height(self) -> None:
        """Drop cached wrap height so the next measure recomputes."""
        self._cached_text_width = -1
        self._cached_measured_height = -1
        self._last_sync_width = -1

    def _measure_height_for_text_width(self, text_width: int) -> float:
        """Measure wrapped document height at *text_width* (always live)."""
        self._document.setTextWidth(text_width)
        layout = self._document.documentLayout()
        max_bottom = layout.documentSize().height()
        block = self._document.begin()
        while block != self._document.end():
            max_bottom = max(max_bottom, layout.blockBoundingRect(block).bottom())
            block = block.next()
        return max_bottom

    def _layout_height_for_text_width(self, text_width: int, *, force: bool = False) -> int:
        """Return wrapped document height for *text_width*, reusing the cache when possible."""
        if not force and self._should_defer_reflow():
            if self._cached_measured_height >= 0:
                return self._cached_measured_height
            return max(1, self._painted_content_height_px or self.height())
        if (
            not force
            and self._cached_text_width == text_width
            and self._cached_measured_height >= 0
        ):
            return self._cached_measured_height
        height = max(1, math.ceil(self._measure_height_for_text_width(text_width)))
        self._cached_text_width = text_width
        self._cached_measured_height = height
        return height

    def _cached_height_for_text_width(self, text_width: int) -> int:
        """Return wrap height for *text_width*, reusing the last measure when unchanged."""
        return self._layout_height_for_text_width(text_width)

    def set_reflow_deferred(self, deferred: bool) -> None:
        """Skip expensive height sync while the chat pane width is changing."""
        if self._reflow_deferred == deferred:
            return
        self._reflow_deferred = deferred
        if not deferred and self._reflow_flush_pending:
            self.flush_deferred_reflow()

    def flush_deferred_reflow(self) -> None:
        """Re-run layout after a deferred pane resize settles."""
        if not self._reflow_flush_pending and not self._reflow_deferred:
            return
        self._reflow_deferred = False
        self._reflow_flush_pending = False
        self._invalidate_measured_height()
        self._sync_height(force=True)

    def _ancestor_resize_coalescing(self) -> bool:
        """Return whether an ancestor chat panel is coalescing pane resize."""
        if self._layout_query_depth > 1:
            return False
        parent = self.parentWidget()
        while parent is not None:
            checker = getattr(parent, "is_resize_coalescing", None)
            if callable(checker):
                return bool(checker())
            parent = parent.parentWidget()
        return False

    def _should_defer_reflow(self) -> bool:
        """Return whether width-triggered document layout should be skipped."""
        return self._reflow_deferred or (not self._streaming and self._ancestor_resize_coalescing())

    def _render_markdown(self) -> None:
        """Render stored markdown via the table-aware streaming HTML pipeline."""
        # Reuse the same renderer as live streaming so finalize cannot drop GFM
        # table rows (e.g. cells with ``<br>``) that Qt markdown mishandles.
        self._set_document_html(self._stream_cache.render_document_html(self._markdown))
        self._sync_height(force=True)

    def _render_markdown_streaming(self) -> None:
        """Incrementally render stored markdown while a stream is open."""
        self._set_document_html(self._stream_cache.render_document_html(self._markdown))
        self._sync_height()

    def set_defer_height_changed(self, defer: bool) -> None:
        """Batch ``height_changed`` emissions during a stream flush."""
        self._defer_height_changed = defer

    def take_deferred_height_pending(self) -> bool:
        """Return and clear whether a deferred ``height_changed`` was queued."""
        pending = self._height_changed_pending
        self._height_changed_pending = False
        return pending

    def flush_deferred_height(self) -> None:
        """Emit one deferred ``height_changed`` if layout grew while deferred."""
        if self.take_deferred_height_pending():
            self.height_changed.emit()

    def append_markdown(self, delta: str) -> None:
        """Append markdown source and update the viewport."""
        if not delta:
            return
        self._markdown += delta
        if self._streaming:
            self._render_markdown_streaming()
        else:
            self._render_markdown()

    def _apply_document_defaults(self) -> None:
        """Sync document default font and text color from the widget palette."""
        self._document.setDefaultFont(self.font())
        self._document.setDefaultStyleSheet(
            f"body {{ color: {self.palette().color(self.foregroundRole()).name()}; }}"
        )

    def _content_width(self) -> int:
        """Return the document wrap width in pixels."""
        if self.width() > 0:
            return self.width()
        parent = self.parentWidget()
        if parent is not None and parent.width() > 0:
            return max(1, parent.width())
        return 1

    def _is_in_transcript_viewport(self) -> bool:
        """Return whether this body intersects the ancestor transcript scroll viewport."""
        parent = self.parentWidget()
        while parent is not None:
            checker = getattr(parent, "markdown_body_intersects_viewport", None)
            if callable(checker):
                return bool(checker(self))
            parent = parent.parentWidget()
        return True

    def _sync_height(self, *_args: object, force: bool = False) -> None:
        """Resize the widget to the wrapped document height."""
        if not force and self._should_defer_reflow():
            self._reflow_flush_pending = True
            return
        width = max(1, self._content_width())
        text_width_px = int(self._document.textWidth())
        if force or text_width_px != width:
            self._invalidate_measured_height()
            self._document.setTextWidth(width)
        self._last_sync_width = width
        doc_h = self._layout_height_for_text_width(width, force=force)
        self._painted_content_height_px = doc_h
        margins = self.contentsMargins()
        chrome = margins.top() + margins.bottom()
        target = max(
            1, doc_h + chrome + (self._footer_rule_gap_px() if self._paint_footer_rule else 0)
        )

        if self._streaming:
            target = max(target, self._stream_layout_floor_px)
            self._stream_layout_floor_px = target

        if not force and self.height() == target and int(self._document.textWidth()) == width:
            self._rebuild_copy_hit_rects()
            return
        self.setFixedHeight(target)
        self.updateGeometry()
        self._rebuild_copy_hit_rects()
        if self._defer_height_changed:
            self._height_changed_pending = True
        else:
            self.height_changed.emit()

    def _transcript_load_blocks_lazy_render(self) -> bool:
        """Return whether session load should defer eager markdown materialisation."""
        parent = self.parentWidget()
        while parent is not None:
            if getattr(parent, "_transcript_loading_visible", False):
                return True
            parent = parent.parentWidget()
        return False

    def showEvent(self, event) -> None:
        """Attach transcript scroll listeners once the body is on screen."""
        super().showEvent(event)
        self._connect_transcript_scroll_hover()
        if self.underMouse():
            self._update_copy_hover(QPointF(self.mapFromGlobal(QCursor.pos())))
        if (
            self._render_deferred
            and self._is_in_transcript_viewport()
            and not self._transcript_load_blocks_lazy_render()
        ):
            self.ensure_rendered()

    def enterEvent(self, event: QEnterEvent) -> None:
        """Apply Copy hover when the pointer enters without a move event."""
        super().enterEvent(event)
        self._update_copy_hover(event.position())

    def resizeEvent(self, event) -> None:
        """Recompute height when the available width changes."""
        super().resizeEvent(event)
        if self._should_defer_reflow():
            self._reflow_flush_pending = True
            return
        self._sync_height()

    def changeEvent(self, event: QEvent) -> None:
        """Refresh document defaults when palette or font changes."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange or event.type() == QEvent.Type.FontChange:
            self._invalidate_measured_height()
            self._apply_document_defaults()
            self.update()

    def hasHeightForWidth(self) -> bool:
        """Allow the transcript layout to size this body from width."""
        return True

    def _fallback_height_for_width(self) -> int:
        """Return a stable height when layout is already measuring this body."""
        margins = self.contentsMargins()
        if self._cached_measured_height >= 0:
            return self._cached_measured_height + margins.top() + margins.bottom()
        laid_out = self.height()
        if laid_out > 0:
            return laid_out
        return 1

    def heightForWidth(self, width: int) -> int:
        """Return wrapped markdown height for *width*."""
        if self._layout_query_depth > 0:
            return self._fallback_height_for_width()
        self._layout_query_depth += 1
        try:
            if width <= 0:
                width = self.width()
            if width <= 0:
                return self._fallback_height_for_width()
            if self._should_defer_reflow() and self._cached_measured_height >= 0:
                margins = self.contentsMargins()
                return self._cached_measured_height + margins.top() + margins.bottom()
            margins = self.contentsMargins()
            text_width = max(1, width - margins.left() - margins.right())
            if self._should_defer_reflow():
                self._reflow_flush_pending = True
                return max(1, self.height())
            doc_h = self._cached_height_for_text_width(text_width)
            return int(doc_h) + margins.top() + margins.bottom()
        finally:
            self._layout_query_depth -= 1

    def _footer_rule_gap_px(self) -> int:
        """Return vertical space reserved below the document for the painted rule."""
        return _FOOTER_RULE_GAP_PX if self._paint_footer_rule else 0

    def _paint_footer_rule_line(self, painter: QPainter) -> None:
        """Draw the dashed separator immediately below the document."""
        y = self._painted_content_height_px + self._footer_rule_gap_px() // 2
        pen = QPen(QColor(COLOR_ASSISTANT_FOOTER_SEPARATOR))
        pen.setCosmetic(True)
        pen.setWidthF(1.0)
        pen.setStyle(Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([float(_FOOTER_RULE_DASH_PX), float(_FOOTER_RULE_DASH_GAP_PX)])
        painter.setPen(pen)
        painter.drawLine(0, y, self.width(), y)

    def paintEvent(self, event) -> None:
        """Paint the owned ``QTextDocument`` and any active text selection."""
        del event
        width = max(1, self.width())
        if int(self._document.textWidth()) != width:
            self._document.setTextWidth(width)
        layout = self._document.documentLayout()
        content_h = max(1, math.ceil(layout.documentSize().height()))
        if content_h != self._painted_content_height_px:
            self._painted_content_height_px = content_h
            chrome = self.contentsMargins().top() + self.contentsMargins().bottom()
            target = content_h + chrome + self._footer_rule_gap_px()
            if self.height() != target:
                QTimer.singleShot(0, self._repair_height_from_paint)
        painter = QPainter(self)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        selection = self._selection_paint_context()
        if selection is not None:
            ctx.selections = [selection]
        layout.draw(painter, ctx)
        if self._paint_footer_rule:
            self._paint_footer_rule_line(painter)
        painter.end()

    def _repair_height_from_paint(self) -> None:
        """Correct the widget height when paint found a width/height mismatch."""
        if not isValid(self):
            return
        content_h = self._painted_content_height_px
        chrome = self.contentsMargins().top() + self.contentsMargins().bottom()
        target = max(1, content_h + chrome + self._footer_rule_gap_px())
        if self.height() == target:
            return
        self._cached_text_width = max(1, self.width())
        self._cached_measured_height = content_h
        self.setFixedHeight(target)
        self.updateGeometry()
        self.height_changed.emit()

    def _cursor_position_at(self, pos: QPointF) -> int:
        """Map a widget-local point to a character index in the document."""
        layout = self._document.documentLayout()
        hit = layout.hitTest(pos, Qt.HitTestAccuracy.ExactHit)
        if hit < 0:
            hit = layout.hitTest(pos, Qt.HitTestAccuracy.FuzzyHit)
        return max(0, hit)

    def _clear_selection(self) -> None:
        """Drop the active selection without repainting when already empty."""
        if self._selection_anchor is None and self._selection_cursor is None:
            return
        self._selection_anchor = None
        self._selection_cursor = None
        self.update()

    def _has_selection(self) -> bool:
        """Return whether the document has a non-empty highlighted range."""
        if self._selection_anchor is None or self._selection_cursor is None:
            return False
        return self._selection_anchor != self._selection_cursor

    def _plain_text_for_table_selection(self, cursor: QTextCursor, table: QTextTable) -> str:
        """Rebuild plain text for a range that spans HTML table rows.

        ``QTextCursor.selectedText()`` concatenates table cells with no
        separator; walk rows/columns and join with tabs/newlines instead.
        """
        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()
        rows_text: list[str] = []
        for row in range(table.rows()):
            row_parts: list[str] = []
            for col in range(table.columns()):
                cell = table.cellAt(row, col)
                if cell.row() != row or cell.column() != col:
                    continue
                cell_start = cell.firstPosition()
                cell_end = cell.lastPosition()
                if cell_end <= sel_start or cell_start >= sel_end:
                    continue
                sub = QTextCursor(self._document)
                sub.setPosition(max(sel_start, cell_start))
                sub.setPosition(min(sel_end, cell_end), QTextCursor.MoveMode.KeepAnchor)
                part = sub.selection().toPlainText()
                if part:
                    row_parts.append(part)
            if row_parts:
                rows_text.append("\t".join(row_parts))
        return "\n".join(rows_text)

    def _selected_text(self) -> str:
        """Return the currently selected plain text, if any."""
        if not self._has_selection():
            return ""
        anchor = self._selection_anchor
        cursor_pos = self._selection_cursor
        if anchor is None or cursor_pos is None:
            return ""
        start = min(anchor, cursor_pos)
        end = max(anchor, cursor_pos)
        cursor = QTextCursor(self._document)
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        table = cursor.currentTable()
        if table is not None:
            return self._plain_text_for_table_selection(cursor, table)
        return cursor.selection().toPlainText()

    def _selection_paint_context(self) -> QAbstractTextDocumentLayout.Selection | None:
        """Build a paint-context selection for the active highlight range."""
        if not self._has_selection():
            return None
        anchor = self._selection_anchor
        cursor_pos = self._selection_cursor
        if anchor is None or cursor_pos is None:
            return None
        start = min(anchor, cursor_pos)
        end = max(anchor, cursor_pos)
        cursor = QTextCursor(self._document)
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        selection = QAbstractTextDocumentLayout.Selection()
        selection.cursor = cursor
        selection.format.setBackground(self.palette().color(QPalette.ColorRole.Highlight))
        selection.format.setForeground(self.palette().color(QPalette.ColorRole.HighlightedText))
        return selection

    def _copy_selection_to_clipboard(self) -> bool:
        """Copy the highlighted range to the clipboard."""
        text = self._selected_text()
        if not text:
            return False
        QGuiApplication.clipboard().setText(text)
        return True

    def _try_copy_fenced_code_block(self, anchor: str) -> bool:
        """Copy a fenced code block when the user clicks its header Copy link."""
        block_index = parse_code_copy_block_index(anchor)
        if block_index is None:
            return False
        sources = fenced_code_sources(self._markdown)
        if block_index < 0 or block_index >= len(sources):
            return False
        QGuiApplication.clipboard().setText(sources[block_index])
        self._copy_confirmed_index = block_index
        self._copy_hover_index = None
        self._copy_confirm_timer.start(_COPY_CONFIRM_MS)
        self._sync_copy_link_appearance()
        return True

    def _update_selection_autoscroll(self, global_pos: QPoint) -> None:
        """Start or stop edge auto-scroll while drag-selecting."""
        scroll = find_ancestor_scroll_area(self)
        if scroll is None:
            self._stop_selection_autoscroll()
            return
        viewport = scroll.viewport()
        if viewport is None:
            self._stop_selection_autoscroll()
            return
        local = viewport.mapFromGlobal(global_pos)
        height = viewport.height()
        step = 0
        if local.y() < _AUTOSCROLL_EDGE_MARGIN_PX:
            dist = _AUTOSCROLL_EDGE_MARGIN_PX - local.y()
            step = -self._autoscroll_step_for_distance(dist)
        elif local.y() > height - _AUTOSCROLL_EDGE_MARGIN_PX:
            dist = local.y() - (height - _AUTOSCROLL_EDGE_MARGIN_PX)
            step = self._autoscroll_step_for_distance(dist)
        self._autoscroll_step = step
        self._autoscroll_global_pos = global_pos
        if step != 0:
            if not self._autoscroll_timer.isActive():
                self._autoscroll_timer.start()
        else:
            self._stop_selection_autoscroll()

    def _autoscroll_step_for_distance(self, dist: float) -> int:
        """Scale scroll speed based on how far past the edge the pointer is."""
        cap = 4 * _AUTOSCROLL_EDGE_MARGIN_PX
        clamped = min(max(dist, 0.0), float(cap))
        ratio = clamped / cap
        magnitude = _AUTOSCROLL_MIN_STEP_PX + ratio * (
            _AUTOSCROLL_MAX_STEP_PX - _AUTOSCROLL_MIN_STEP_PX
        )
        return int(round(magnitude))

    def _on_autoscroll_tick(self) -> None:
        """Nudge the transcript scroll area and extend the active selection."""
        if not isValid(self) or self._autoscroll_step == 0 or self._autoscroll_global_pos is None:
            self._stop_selection_autoscroll()
            return
        scroll = find_ancestor_scroll_area(self)
        if scroll is None:
            self._stop_selection_autoscroll()
            return
        bar = scroll.verticalScrollBar()
        next_value = max(bar.minimum(), min(bar.maximum(), bar.value() + self._autoscroll_step))
        if next_value == bar.value():
            self._autoscroll_timer.stop()
            return
        bar.setValue(next_value)
        local = self.mapFromGlobal(self._autoscroll_global_pos)
        self._selection_cursor = self._cursor_position_at(QPointF(local))
        self.update()

    def _stop_selection_autoscroll(self) -> None:
        """Stop drag-selection auto-scroll."""
        self._autoscroll_timer.stop()
        self._autoscroll_step = 0
        self._autoscroll_global_pos = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Begin or extend a text selection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            pos = QPointF(event.position())
            if self._copy_block_index_at(pos) is not None:
                self._press_position = pos
                self._clear_selection()
                event.accept()
                return
            self._press_position = pos
            index = self._cursor_position_at(pos)
            if (
                event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                and self._selection_anchor is not None
            ):
                self._selection_cursor = index
            else:
                self._selection_anchor = index
                self._selection_cursor = index
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Extend the selection while the left button is held."""
        if event.buttons() & Qt.MouseButton.LeftButton and self._press_position is not None:
            self._selection_cursor = self._cursor_position_at(QPointF(event.position()))
            self._update_selection_autoscroll(event.globalPosition().toPoint())
            self.update()
            event.accept()
            return
        self._update_copy_hover(QPointF(event.position()))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """Clear copy-link hover styling when the pointer leaves the body."""
        if self._copy_hover_index is not None:
            self._copy_hover_index = None
            self._sync_copy_link_appearance()
        self.setCursor(Qt.CursorShape.IBeamCursor)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Open external links when the user clicks without selecting text."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._stop_selection_autoscroll()
            dragged = False
            if self._press_position is not None:
                dragged = (
                    QPointF(event.position()) - self._press_position
                ).manhattanLength() > _SELECTION_DRAG_THRESHOLD_PX
            self._press_position = None
            if not dragged and not self._has_selection():
                pos = QPointF(event.position())
                copy_index = self._copy_block_index_at(pos)
                if copy_index is not None and self._try_copy_fenced_code_block(
                    code_copy_href(copy_index)
                ):
                    event.accept()
                    return
                anchor = self._document.documentLayout().anchorAt(pos)
                if anchor:
                    url = QUrl(anchor)
                    if url.scheme() == "postmark":
                        kind = url.host()
                        path = url.path().lstrip("/")
                        try:
                            entity_id = int(path)
                        except ValueError:
                            entity_id = 0
                        if kind and entity_id > 0:
                            focus = QUrlQuery(url).queryItemValue("focus")
                            self.workspace_target_requested.emit(kind, entity_id, focus)
                        # Malformed / non-numeric postmark:// must never open externally.
                        event.accept()
                        return
                    if url.isValid() and QDesktopServices.openUrl(url):
                        event.accept()
                        return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Select the word under the cursor."""
        if event.button() == Qt.MouseButton.LeftButton:
            cursor = QTextCursor(self._document)
            cursor.setPosition(self._cursor_position_at(QPointF(event.position())))
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            self._selection_anchor = cursor.selectionStart()
            self._selection_cursor = cursor.selectionEnd()
            self.update()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:
        """Support copy and select-all shortcuts for highlighted text."""
        if event.matches(QKeySequence.StandardKey.Copy) and self._copy_selection_to_clipboard():
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self._selection_anchor = 0
            end = max(0, self._document.characterCount() - 1)
            self._selection_cursor = end
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)

    def _show_context_menu(self, pos) -> None:
        """Show a context menu with copy actions for the selection or markdown source."""
        if not self._markdown and not self._has_selection():
            return
        menu = QMenu(self)
        copy_selection_action = None
        if self._has_selection():
            copy_selection_action = menu.addAction("Copy")
        copy_message_action = None
        if self._markdown:
            copy_message_action = menu.addAction("Copy message")
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen is copy_selection_action:
            self._copy_selection_to_clipboard()
        elif chosen is copy_message_action:
            QGuiApplication.clipboard().setText(self._markdown)

    def event(self, event: QEvent) -> bool:
        """Route hover and wheel input before default widget handling."""
        if event.type() == QEvent.Type.HoverMove and isinstance(event, QHoverEvent):
            self._update_copy_hover(event.position())
        if (
            event.type() == QEvent.Type.Wheel
            and isinstance(event, QWheelEvent)
            and forward_wheel_to_ancestor_scroll_area(self, event)
        ):
            return True
        return super().event(event)


# Private alias kept for tests that import ``_MarkdownContent``.
_MarkdownContent = MarkdownContent
