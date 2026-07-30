"""Non-modal viewer for the Markdown produced from one uploaded attachment.

Clicking a file chip in a user transcript bubble opens this window so the user
can read exactly what the model was handed for that upload. The body is the
same ``MarkdownContent`` widget (``aiChatAssistantText``) used by assistant
transcript rows and the subagent detail reply pane — not a parallel renderer.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent
from ui.styling.icons import phi

_DEFAULT_WIDTH = 680
_DEFAULT_HEIGHT = 720
_MAX_WIDTH_FRACTION = 0.62
_MAX_HEIGHT_FRACTION = 0.78
_EMPTY_BODY_NOTICE = "No Markdown was produced for this attachment."
# Retry layout sync a few times if the scroll viewport is still 0-wide after show.
_LAYOUT_SYNC_RETRIES = 8


def _initial_dialog_size() -> tuple[int, int]:
    """Return a compact default size capped to the available screen."""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return _DEFAULT_WIDTH, _DEFAULT_HEIGHT
    geo = screen.availableGeometry()
    width = min(_DEFAULT_WIDTH, int(geo.width() * _MAX_WIDTH_FRACTION))
    height = min(_DEFAULT_HEIGHT, int(geo.height() * _MAX_HEIGHT_FRACTION))
    return max(520, width), max(480, height)


class AttachmentMarkdownDialog(QDialog):
    """Read-only viewer for the Markdown conversion of one uploaded file.

    Layout mirrors ``SubagentDetailDialog``'s reply pane: a non-resizable
    ``QScrollArea`` hosting a stock ``MarkdownContent`` (objectName
    ``aiChatAssistantText``), width-pinned via ``sync_to_viewport_width``.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the file-name header, scrollable markdown body, and close button."""
        super().__init__(parent)
        self.setObjectName("aiChatAttachmentMarkdownDialog")
        self.setWindowTitle("Attachment")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.resize(*_initial_dialog_size())

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self._title = QLabel()
        self._title.setObjectName("aiChatAttachmentMarkdownTitle")
        self._title.setWordWrap(True)
        root.addWidget(self._title)

        # Same scroll + MarkdownContent wiring as SubagentDetailDialog's reply pane.
        self._scroll = QScrollArea()
        self._scroll.setObjectName("aiChatAttachmentMarkdownScroll")
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        viewport = self._scroll.viewport()
        if viewport is not None:
            viewport.setObjectName("aiChatAttachmentMarkdownScrollViewport")
        # Keep the default ``aiChatAssistantText`` objectName so QSS and the
        # shared markdown paint path match assistant rows / subagent replies.
        self._body = MarkdownContent()
        self._scroll.setWidget(self._body)
        root.addWidget(self._scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("aiChatAttachmentMarkdownClose")
        close_btn.setIcon(phi("x", size=12))
        close_btn.setIconSize(QSize(12, 12))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        footer.addWidget(close_btn)
        root.addLayout(footer)

        self._name = ""
        self._layout_sync_retries = 0

    def open_attachment(self, name: str, markdown: str) -> None:
        """Show the dialog for *name* rendered from *markdown*.

        Show first so the scroll viewport has a real width, then set markdown
        and pin the body — the same order as ``SubagentDetailDialog.open_record``.
        """
        self._name = name
        self._title.setText(name)
        self.setWindowTitle(name)
        body = markdown.strip() or _EMPTY_BODY_NOTICE
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        # Set markdown after show so the first layout pass sees a real width.
        self._body.set_markdown(body)
        self._layout_sync_retries = 0
        self._schedule_body_layout_sync()

    def showEvent(self, event: QShowEvent) -> None:
        """Lay out markdown at the scroll viewport width once visible."""
        super().showEvent(event)
        self._schedule_body_layout_sync()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Reflow markdown when the dialog or scroll viewport width changes."""
        super().resizeEvent(event)
        self._schedule_body_layout_sync()

    def _schedule_body_layout_sync(self) -> None:
        """Re-render markdown after the dialog has a real viewport width."""
        QTimer.singleShot(0, self._sync_body_layout)

    def _sync_body_layout(self) -> None:
        """Match the markdown body width to the scroll viewport and re-render."""
        viewport = self._scroll.viewport()
        if viewport is None or viewport.width() <= 0:
            if self._layout_sync_retries < _LAYOUT_SYNC_RETRIES:
                self._layout_sync_retries += 1
                self._schedule_body_layout_sync()
            return
        self._layout_sync_retries = 0
        self._body.sync_to_viewport_width(viewport.width())


__all__ = ["AttachmentMarkdownDialog"]
