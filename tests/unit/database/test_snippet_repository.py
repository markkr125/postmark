"""Repository tests for user-authored script snippets."""

from __future__ import annotations

from database.models.snippets.snippet_repository import (
    create_snippet,
    delete_snippet,
    list_snippets,
)


def test_create_and_list_global_snippet() -> None:
    """Global snippets appear for any scope."""
    row = create_snippet(
        name="My log",
        language="js",
        category="Helpers",
        body="console.log('hi');",
        context="both",
    )
    rows = list_snippets(language="js")
    assert any(r["id"] == row.id for r in rows)


def test_collection_scope_filter() -> None:
    """Collection-scoped snippets are hidden without a matching collection id."""
    create_snippet(
        name="Scoped",
        language="js",
        category="Helpers",
        body="x = 1;",
        context="pre",
        scope_collection_id=42,
    )
    assert not list_snippets(language="js", collection_id=99)
    assert list_snippets(language="js", collection_id=42)


def test_delete_snippet() -> None:
    """Deleting removes the row from subsequent list calls."""
    row = create_snippet(
        name="Temp",
        language="py",
        category="Helpers",
        body="pass",
        context="both",
    )
    delete_snippet(int(row.id))
    assert not any(r["id"] == row.id for r in list_snippets(language="py"))
