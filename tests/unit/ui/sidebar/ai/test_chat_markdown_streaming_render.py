"""Tests for incremental streaming markdown rendering."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from ui.sidebar.ai.markdown.streaming_render import StreamingMarkdownCache
from ui.sidebar.ai.message_bubble import _MarkdownContent
from ui.styling.theme import DARK_PALETTE


@pytest.fixture
def _qapp_for_markdown(qapp: QApplication) -> QApplication:
    """Ensure a QApplication exists for widget tests."""
    return qapp


class TestStreamingMarkdownCache:
    """Tests for :class:`StreamingMarkdownCache`."""

    def test_reuses_stable_closed_code_segment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Closed code blocks are not re-highlighted when only trailing prose grows."""
        highlight_calls: list[tuple[str, str]] = []

        def _counting_highlight(
            code: str,
            lang: str,
            *,
            palette: object,
            line_numbers: bool = True,
        ) -> str:
            highlight_calls.append((lang, code))
            return f"<highlighted>{code}</highlighted>"

        monkeypatch.setattr(
            "ui.sidebar.ai.markdown.render.highlight_code_to_html",
            _counting_highlight,
        )
        cache = StreamingMarkdownCache()
        first = "Intro\n\n```python\nprint(1)\n```\n\nTail"
        cache.render_document_html(first, palette=DARK_PALETTE)
        assert len(highlight_calls) == 1
        cache.render_document_html(first + " more", palette=DARK_PALETTE)
        assert len(highlight_calls) == 1

    def test_provisional_code_uses_cheap_renderer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Open fences render via provisional HTML, not Pygments."""
        highlight_calls: list[str] = []
        provisional_calls: list[str] = []

        def _fake_highlight(
            code: str,
            lang: str,
            *,
            palette: object,
            line_numbers: bool = True,
        ) -> str:
            highlight_calls.append(code)
            return f"<highlighted>{code}</highlighted>"

        def _fake_provisional(code: str, lang: str, *, palette: object) -> str:
            provisional_calls.append(code)
            return f"<provisional>{code}</provisional>"

        monkeypatch.setattr(
            "ui.sidebar.ai.markdown.render.highlight_code_to_html",
            _fake_highlight,
        )
        monkeypatch.setattr(
            "ui.sidebar.ai.markdown.highlight_code.provisional_code_to_html",
            _fake_provisional,
        )
        cache = StreamingMarkdownCache()
        html = cache.render_document_html("```python\npartial", palette=DARK_PALETTE)
        assert provisional_calls == ["partial"]
        assert not highlight_calls
        assert "<provisional>" in html


class TestMarkdownContentStreamingIncremental:
    """Integration tests for :class:`MarkdownContent` streaming updates."""

    def test_streaming_appends_reuse_stable_segments(
        self, _qapp_for_markdown: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Growing trailing prose does not re-run Pygments on closed code blocks."""
        highlight_calls: list[str] = []

        def _counting_highlight(
            code: str,
            lang: str,
            *,
            palette: object,
            line_numbers: bool = True,
        ) -> str:
            highlight_calls.append(code)
            return f'<table><tr><td style="font-family:monospace;">{code}</td></tr></table>'

        monkeypatch.setattr(
            "ui.sidebar.ai.markdown.render.highlight_code_to_html",
            _counting_highlight,
        )
        body = _MarkdownContent()
        qtbot.addWidget(body)
        body.resize(360, 480)
        body.begin_streaming()
        body.append_markdown("Before\n\n```python\nprint(1)\n```\n\nAfter")
        assert len(highlight_calls) == 1
        body.append_markdown(" tail")
        assert len(highlight_calls) == 1
        html = body.toHtml().lower()
        assert "font-weight:600" in html or "after" in html

    def test_open_fence_renders_provisional_then_highlights_on_close(
        self,
        _qapp_for_markdown: QApplication,
        qtbot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Provisional code blocks upgrade to highlighted tables when the fence closes."""
        provisional_calls: list[str] = []
        highlight_calls: list[str] = []

        def _fake_provisional(code: str, lang: str, *, palette: object) -> str:
            provisional_calls.append(code)
            return f"<provisional>{code}</provisional>"

        def _fake_highlight(
            code: str,
            lang: str,
            *,
            palette: object,
            line_numbers: bool = True,
        ) -> str:
            highlight_calls.append(code)
            return f"<table>{code}</table>"

        monkeypatch.setattr(
            "ui.sidebar.ai.markdown.highlight_code.provisional_code_to_html",
            _fake_provisional,
        )
        monkeypatch.setattr(
            "ui.sidebar.ai.markdown.render.highlight_code_to_html",
            _fake_highlight,
        )
        body = _MarkdownContent()
        qtbot.addWidget(body)
        body.resize(360, 480)
        body.begin_streaming()
        body.append_markdown("```python\nprint(1")
        assert provisional_calls == ["print(1"]
        assert not highlight_calls
        body.append_markdown(")\n```")
        assert highlight_calls == ["print(1)\n"]
