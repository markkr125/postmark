"""Tests for async text-format helpers."""

from __future__ import annotations

from ui.widgets.text_format_async.helpers import skip_inline_text_for_async_pretty


class TestSkipInlineTextForAsyncPretty:
    """Tests for :func:`skip_inline_text_for_async_pretty`."""

    def test_small_body_uses_inline(self) -> None:
        assert not skip_inline_text_for_async_pretty("{}", pretty=True)

    def test_large_body_skips_inline_when_pretty(self) -> None:
        assert skip_inline_text_for_async_pretty("x" * 40_000, pretty=True)

    def test_large_body_allows_inline_when_not_pretty(self) -> None:
        assert not skip_inline_text_for_async_pretty("x" * 40_000, pretty=False)
