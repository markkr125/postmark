"""Service tests for user-authored script snippets."""

from __future__ import annotations

import ui.widgets.snippets.loader as snippet_loader
from services.snippet_service import SnippetService
from ui.widgets.snippets.loader import load_snippets


def test_normalize_language_maps_typescript_to_ts() -> None:
    """TypeScript editor language stores as ``ts`` in the database (separate from ``js``)."""
    assert SnippetService.normalize_language("typescript") == "ts"


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


def test_delete_snippets_in_category() -> None:
    """``delete_snippets_in_category`` removes only rows in that category."""
    snippet_loader.load_snippets.cache_clear()
    try:
        SnippetService.create(
            name="Keep me",
            language="javascript",
            body="// a",
            category="Other",
        )
        SnippetService.create(
            name="Gone one",
            language="javascript",
            body="// b",
            category="To delete",
        )
        SnippetService.create(
            name="Gone two",
            language="javascript",
            body="// c",
            category="To delete",
        )
        removed = SnippetService.delete_snippets_in_category("javascript", "To delete")
        assert removed == 2
        names = [r["name"] for r in SnippetService.list_all("javascript")]
        assert "Keep me" in names
        assert "Gone one" not in names
        assert "Gone two" not in names
    finally:
        snippet_loader.load_snippets.cache_clear()


def test_rename_category() -> None:
    """``rename_category`` updates the category field on all matching rows."""
    snippet_loader.load_snippets.cache_clear()
    try:
        SnippetService.create(
            name="One",
            language="javascript",
            body="// 1",
            category="Old name",
        )
        SnippetService.create(
            name="Two",
            language="javascript",
            body="// 2",
            category="Old name",
        )
        SnippetService.create(
            name="Other",
            language="javascript",
            body="// 3",
            category="Keep",
        )
        count = SnippetService.rename_category("javascript", "Old name", "New name")
        assert count == 2
        by_cat = {
            (r.get("category") or "My snippets"): r["name"]
            for r in SnippetService.list_all("javascript")
        }
        assert by_cat["New name"] in ("One", "Two")
        assert "Old name" not in by_cat
        assert by_cat.get("Keep") == "Other"
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
