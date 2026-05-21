"""Service tests for user-authored script snippets."""

from __future__ import annotations

import ui.widgets.snippets.loader as snippet_loader
from services.snippet_service import SnippetService
from ui.widgets.snippets.loader import load_snippets


def test_normalize_language_maps_typescript_to_js() -> None:
    """TypeScript editor language stores as ``js`` in the database."""
    assert SnippetService.normalize_language("typescript") == "js"


def test_create_and_merge_into_loader() -> None:
    """User snippets appear before built-in JSON categories."""
    snippet_loader.load_snippets.cache_clear()
    try:
        SnippetService.create(
            name="User only row",
            language="javascript",
            body="console.log('custom');",
            category="ZZZ User cat",
            context="both",
        )
        cats = load_snippets("javascript")
        assert cats
        assert cats[0].name == "ZZZ User cat"
        assert cats[0].snippets[0].is_user
        assert "custom" in cats[0].snippets[0].body
    finally:
        snippet_loader.load_snippets.cache_clear()


def test_list_filters_context() -> None:
    """``list`` respects pre vs test context tags."""
    SnippetService.create(
        name="Pre only",
        language="javascript",
        body="pre();",
        context="pre",
    )
    pre_rows = SnippetService.list("javascript", "pre_request")
    test_rows = SnippetService.list("javascript", "test")
    assert any(r["name"] == "Pre only" for r in pre_rows)
    assert not any(r["name"] == "Pre only" for r in test_rows)
