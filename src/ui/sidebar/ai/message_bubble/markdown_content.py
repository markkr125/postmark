"""Markdown answer body and theme re-render registry for assistant rows."""

from __future__ import annotations

import weakref

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QGuiApplication,
    QPainter,
    QTextDocument,
    QWheelEvent,
)
from shiboken6 import isValid
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QSizePolicy,
    QWidget,
)

from ui.sidebar.ai.message_bubble.wrapping_label import forward_wheel_to_ancestor_scroll_area

from ui.sidebar.ai.markdown.render import render_chat_markdown_html
from ui.sidebar.ai.markdown.highlight_code import clear_highlight_cache
from ui.sidebar.ai.markdown.streaming_render import StreamingMarkdownCache
from ui.styling.theme_manager import ThemeManager

_markdown_bodies: weakref.WeakSet[MarkdownContent] = weakref.WeakSet()
_theme_hook_installed = False


def rerender_all_markdown_browsers() -> None:
    """Re-render stored markdown when the application theme changes."""
    clear_highlight_cache()
    for body in list(_markdown_bodies):
        if not isValid(body):
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

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        """Configure markdown rendering, link handling, and height sync."""
        super().__init__(parent)
        self.setObjectName("aiChatAssistantText")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._document = QTextDocument(self)
        self._document.setDocumentMargin(0)
        self._markdown = ""
        self._streaming = False
        self._stream_cache = StreamingMarkdownCache()
        self._stream_layout_floor_px = 0
        self._defer_height_changed = False
        self._height_changed_pending = False
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

    def _set_document_html(self, html: str) -> None:
        """Replace document HTML and schedule a repaint."""
        self._document.setHtml(html)
        self.update()

    def _render_markdown(self) -> None:
        """Render stored markdown via the full HTML pipeline."""
        self._set_document_html(render_chat_markdown_html(self._markdown))
        self._sync_height()

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

    def _sync_height(self, *_args: object) -> None:
        """Resize the widget to the wrapped document height."""
        width = self._content_width()
        self._document.setTextWidth(width)
        doc_h = self._document.documentLayout().documentSize().height()
        margins = self.contentsMargins()
        chrome = margins.top() + margins.bottom()
        target = max(1, int(doc_h) + chrome)

        if self._streaming:
            target = max(target, self._stream_layout_floor_px)
            self._stream_layout_floor_px = target

        if self.height() == target:
            return
        self.setFixedHeight(target)
        self.updateGeometry()
        if self._defer_height_changed:
            self._height_changed_pending = True
        else:
            self.height_changed.emit()

    def resizeEvent(self, event) -> None:
        """Recompute height when the available width changes."""
        super().resizeEvent(event)
        self._sync_height()

    def changeEvent(self, event: QEvent) -> None:
        """Refresh document defaults when palette or font changes."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange or event.type() == QEvent.Type.FontChange:
            self._apply_document_defaults()
            self.update()

    def hasHeightForWidth(self) -> bool:
        """Allow the transcript layout to size this body from width."""
        return True

    def heightForWidth(self, width: int) -> int:
        """Return wrapped markdown height for *width*."""
        if width <= 0:
            return self.sizeHint().height()
        margins = self.contentsMargins()
        text_width = max(1, width - margins.left() - margins.right())
        self._document.setTextWidth(text_width)
        doc_h = self._document.documentLayout().documentSize().height()
        return int(doc_h) + margins.top() + margins.bottom()

    def paintEvent(self, event) -> None:
        """Paint the owned ``QTextDocument`` at the widget origin."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._document.drawContents(painter, QRectF(event.rect()))

    def mouseReleaseEvent(self, event) -> None:
        """Open external links when the user clicks a document anchor."""
        if event.button() == Qt.MouseButton.LeftButton:
            anchor = self._document.documentLayout().anchorAt(QPointF(event.position()))
            if anchor:
                url = QUrl(anchor)
                if url.isValid() and QDesktopServices.openUrl(url):
                    event.accept()
                    return
        super().mouseReleaseEvent(event)

    def _show_context_menu(self, pos) -> None:
        """Show a context menu with copy actions for the markdown source."""
        if not self._markdown:
            return
        menu = QMenu(self)
        copy_action = menu.addAction("Copy message")
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen is copy_action:
            QGuiApplication.clipboard().setText(self._markdown)

    def event(self, event: QEvent) -> bool:
        """Route wheel input to the transcript scroll area before local handling."""
        if (
            event.type() == QEvent.Type.Wheel
            and isinstance(event, QWheelEvent)
            and forward_wheel_to_ancestor_scroll_area(self, event)
        ):
            return True
        return super().event(event)


# Private alias kept for tests that import ``_MarkdownContent``.
_MarkdownContent = MarkdownContent
