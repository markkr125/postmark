"""Tests for postmark:// deep-links in assistant markdown."""

from __future__ import annotations

from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QMouseEvent

from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent


def test_postmark_link_emits_workspace_target(qapp, qtbot) -> None:
    """Clicking a postmark:// link emits workspace_target_requested."""
    body = MarkdownContent("[Create user](postmark://request/12?focus=test)")
    qtbot.addWidget(body)
    body.resize(360, 120)
    body.show()
    qtbot.waitExposed(body)

    received: list[tuple[str, int, str]] = []
    body.workspace_target_requested.connect(
        lambda kind, entity_id, focus: received.append((kind, entity_id, focus))
    )

    local = QPointF(12, 8)
    with (
        patch.object(
            body._document.documentLayout(),
            "anchorAt",
            return_value="postmark://request/12?focus=test",
        ),
        patch(
            "ui.sidebar.ai.message_bubble.markdown_content.QDesktopServices.openUrl",
        ) as open_url,
    ):
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            local,
            local,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        body.mouseReleaseEvent(event)
        open_url.assert_not_called()

    assert received == [("request", 12, "test")]


def test_https_link_still_opens_externally(qapp, qtbot) -> None:
    """Ordinary https links continue to open in the browser."""
    body = MarkdownContent("[Example](https://example.com/test)")
    qtbot.addWidget(body)
    body.resize(360, 120)
    body.show()
    qtbot.waitExposed(body)

    opened: list[QUrl] = []

    def _open_url(url: QUrl) -> bool:
        opened.append(url)
        return True

    local = QPointF(12, 8)
    with (
        patch.object(
            body._document.documentLayout(),
            "anchorAt",
            return_value="https://example.com/test",
        ),
        patch(
            "ui.sidebar.ai.message_bubble.markdown_content.QDesktopServices.openUrl",
            side_effect=_open_url,
        ),
    ):
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            local,
            local,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        body.mouseReleaseEvent(event)

    assert opened and opened[0].toString() == "https://example.com/test"


def test_malformed_postmark_link_never_opens_externally(qapp, qtbot) -> None:
    """Non-numeric postmark:// paths must not fall through to QDesktopServices."""
    body = MarkdownContent("[Bad](postmark://history/abc)")
    qtbot.addWidget(body)
    body.resize(360, 120)
    body.show()
    qtbot.waitExposed(body)

    received: list[tuple[str, int, str]] = []
    body.workspace_target_requested.connect(
        lambda kind, entity_id, focus: received.append((kind, entity_id, focus))
    )

    local = QPointF(12, 8)
    with (
        patch.object(
            body._document.documentLayout(),
            "anchorAt",
            return_value="postmark://history/abc",
        ),
        patch(
            "ui.sidebar.ai.message_bubble.markdown_content.QDesktopServices.openUrl",
        ) as open_url,
    ):
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            local,
            local,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        body.mouseReleaseEvent(event)
        open_url.assert_not_called()

    assert received == []


def test_bracket_named_link_renders_anchor() -> None:
    """Labels containing ] produce valid markdown anchors through the renderer."""
    from ui.sidebar.ai.markdown.render import render_chat_markdown_html

    html = render_chat_markdown_html("[Req [beta]](postmark://request/5)")
    assert 'href="postmark://request/5"' in html
