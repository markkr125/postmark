"""Tests for the app wiki query executor."""

from __future__ import annotations

from pathlib import Path

from services.ai.chat.app_wiki.config import is_allowed_wiki_doc, resolve_allowed_path
from services.ai.chat.app_wiki.query import execute_wiki_query


def _fixture_index() -> str:
    return """# Index

## user-guide / collections

- `docs/user-guide/collections/create-and-organize.md` — Create and organize — New collection and HTTP request steps.
"""


def test_is_allowed_wiki_doc_user_guide() -> None:
    """User-guide paths are allowlisted."""
    assert is_allowed_wiki_doc("docs/user-guide/collections/create-and-organize.md")


def test_is_allowed_wiki_doc_rejects_api_reference() -> None:
    """Developer api-reference is not allowlisted."""
    assert not is_allowed_wiki_doc("docs/api-reference/signals.md")


def test_resolve_allowed_path_rejects_traversal(tmp_path: Path) -> None:
    """Path traversal outside allowlisted roots is rejected."""
    ug = tmp_path / "docs" / "user-guide"
    ug.mkdir(parents=True)
    page = ug / "page.md"
    page.write_text("# Page\n", encoding="utf-8")
    assert resolve_allowed_path("docs/user-guide/page.md", tmp_path) == page.resolve()
    assert resolve_allowed_path("../../etc/passwd", tmp_path) is None
    assert resolve_allowed_path("docs/api-reference/x.md", tmp_path) is None


def test_execute_wiki_query_by_page(tmp_path: Path) -> None:
    """Explicit page reads an allowlisted file."""
    ug = tmp_path / "docs" / "user-guide" / "collections"
    ug.mkdir(parents=True)
    page = ug / "create-and-organize.md"
    page.write_text("# Create\n\nStep one.\n", encoding="utf-8")
    wiki = tmp_path / "data" / "app-wiki"
    wiki.mkdir(parents=True)
    (wiki / "index.md").write_text(_fixture_index(), encoding="utf-8")

    result = execute_wiki_query(
        "ignored",
        page="docs/user-guide/collections/create-and-organize.md",
        root=tmp_path,
    )
    assert "Create" in result
    assert "Step one" in result


def test_execute_wiki_query_search_index(tmp_path: Path) -> None:
    """Keyword search uses the generated index."""
    ug = tmp_path / "docs" / "user-guide" / "collections"
    ug.mkdir(parents=True)
    (ug / "create-and-organize.md").write_text("# Create\n\nNew (+) button.\n", encoding="utf-8")
    wiki = tmp_path / "data" / "app-wiki"
    wiki.mkdir(parents=True)
    (wiki / "index.md").write_text(_fixture_index(), encoding="utf-8")

    result = execute_wiki_query("collection New", root=tmp_path)
    assert "create-and-organize.md" in result
    assert "New (+)" in result


def test_execute_wiki_query_wrong_page_falls_back_to_search(tmp_path: Path) -> None:
    """A non-existent explicit page falls back to keyword search instead of erroring."""
    ug = tmp_path / "docs" / "user-guide" / "scripting" / "javascript"
    ug.mkdir(parents=True)
    real = ug / "pre-request-scripts.md"
    real.write_text("# Pre-request scripts\n\nMutate the request before Send.\n", encoding="utf-8")
    wiki = tmp_path / "data" / "app-wiki"
    wiki.mkdir(parents=True)
    index = (
        "# Index\n\n## user-guide / scripting\n\n"
        "- `docs/user-guide/scripting/javascript/pre-request-scripts.md` — "
        "Pre-request scripts — Mutate the request before Send.\n"
    )
    (wiki / "index.md").write_text(index, encoding="utf-8")

    # Wrong path (missing javascript/ segment) should still resolve via search.
    result = execute_wiki_query(
        "pre-request script",
        page="docs/user-guide/scripting/pre-request-scripts.md",
        root=tmp_path,
    )
    assert "Mutate the request before Send" in result
    assert "javascript/pre-request-scripts.md" in result


def test_execute_wiki_query_char_cap(tmp_path: Path) -> None:
    """Total excerpt size respects the character cap."""
    ug = tmp_path / "docs" / "user-guide"
    ug.mkdir(parents=True)
    big = "x" * 5000
    (ug / "a.md").write_text(f"# A\n\n{big}\n", encoding="utf-8")
    (ug / "b.md").write_text(f"# B\n\n{big}\n", encoding="utf-8")
    wiki = tmp_path / "data" / "app-wiki"
    wiki.mkdir(parents=True)
    index = """# Index

## user-guide

- `docs/user-guide/a.md` — A — alpha page.
- `docs/user-guide/b.md` — B — beta page.
"""
    (wiki / "index.md").write_text(index, encoding="utf-8")

    result = execute_wiki_query("alpha beta", root=tmp_path, char_cap=6000)
    assert len(result) <= 6000 + 200
    assert len(result) <= 6000 + 200
