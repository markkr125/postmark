"""Tests for full chat markdown HTML assembly."""

from __future__ import annotations

import re

import pytest
from PySide6.QtWidgets import QApplication

from ui.sidebar.ai.markdown.render import render_chat_markdown_html
from ui.styling.theme import DARK_PALETTE


@pytest.fixture
def _qapp_for_markdown(qapp: QApplication) -> QApplication:
    """Ensure a QApplication exists for Qt markdown conversion."""
    return qapp


class TestRenderChatMarkdownHtml:
    """Tests for :func:`render_chat_markdown_html`."""

    def test_mixed_prose_and_two_blocks(self, _qapp_for_markdown: QApplication) -> None:
        source = "Intro\n\n```python\nprint(1)\n```\n\nMiddle\n\n```js\nconsole.log(2)\n```\n\nTail"
        html = render_chat_markdown_html(source, palette=DARK_PALETTE)
        assert html.count("<html>") == 1
        assert html.count("<body") == 1
        assert ">python<" in html
        assert ">javascript<" in html
        assert "Intro" in html
        assert "Middle" in html
        assert "Tail" in html

    def test_inline_code_pill(self, _qapp_for_markdown: QApplication) -> None:
        html = render_chat_markdown_html("Use `foo` here.", palette=DARK_PALETTE)
        assert "border-radius:4px" in html
        assert "font-family:monospace" in html
        assert "foo" in html

    def test_no_duplicate_html_wrappers_in_body(self, _qapp_for_markdown: QApplication) -> None:
        html = render_chat_markdown_html("**bold**", palette=DARK_PALETTE)
        body_match = re.search(r"<body[^>]*>(.*)</body>", html, re.DOTALL | re.IGNORECASE)
        assert body_match is not None
        body = body_match.group(1).lower()
        assert "<html" not in body
        assert "<head" not in body
