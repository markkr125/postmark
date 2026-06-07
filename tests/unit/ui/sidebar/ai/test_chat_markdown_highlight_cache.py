"""Tests for fenced-code HTML caching."""

from __future__ import annotations

from ui.sidebar.ai.markdown.highlight_code import (
    clear_highlight_cache,
    highlight_code_to_html,
)
from ui.styling.theme import DARK_PALETTE


class TestHighlightCache:
    """Tests for :func:`highlight_code_to_html` caching."""

    def test_cache_returns_same_html(self) -> None:
        clear_highlight_cache()
        first = highlight_code_to_html("print(1)", "python", palette=DARK_PALETTE)
        second = highlight_code_to_html("print(1)", "python", palette=DARK_PALETTE)
        assert first is second

    def test_clear_cache_forces_rebuild(self) -> None:
        clear_highlight_cache()
        first = highlight_code_to_html("x = 1", "python", palette=DARK_PALETTE)
        clear_highlight_cache()
        second = highlight_code_to_html("x = 1", "python", palette=DARK_PALETTE)
        assert first == second
        assert first is not second

    def test_different_palette_bypasses_cache(self) -> None:
        from ui.styling.theme import LIGHT_PALETTE

        clear_highlight_cache()
        dark = highlight_code_to_html("x = 1", "python", palette=DARK_PALETTE)
        light = highlight_code_to_html("x = 1", "python", palette=LIGHT_PALETTE)
        assert dark != light

    def test_cache_evicts_oldest_entry(self) -> None:
        from ui.sidebar.ai.markdown.highlight_code import _HIGHLIGHT_CACHE_MAX_ENTRIES

        clear_highlight_cache()
        first_key = highlight_code_to_html("first = 1", "python", palette=DARK_PALETTE)
        for index in range(_HIGHLIGHT_CACHE_MAX_ENTRIES):
            highlight_code_to_html(f"v{index} = {index}", "python", palette=DARK_PALETTE)
        second_first = highlight_code_to_html("first = 1", "python", palette=DARK_PALETTE)
        assert second_first == first_key
        assert second_first is not first_key
