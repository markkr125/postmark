"""Tests for ``scripts/build_app_wiki.py`` and index generation."""

from __future__ import annotations

from pathlib import Path

from database.data_paths import project_root
from services.ai.chat.app_wiki.build_index import build_index_markdown, collect_index_sources
from services.ai.chat.app_wiki.config import SCRIPTING_ALLOWLIST


def test_collect_index_sources_includes_user_guide_and_scripting() -> None:
    """Index sources cover user-guide and allowlisted scripting only."""
    root = project_root()
    rels = {p.relative_to(root).as_posix() for p in collect_index_sources(root)}
    assert "docs/user-guide/collections/create-and-organize.md" in rels
    assert "docs/scripting/javascript-api.md" in rels
    assert "docs/guides/writing-scripts.md" in rels
    assert not any(r.startswith("docs/api-reference/") for r in rels)
    assert not any(r.startswith("docs/architecture/") for r in rels)
    assert not any(r.startswith("docs/ui-reference/") for r in rels)


def test_scripting_allowlist_excludes_dev_guides() -> None:
    """Allowlist is explicit and does not pull contributor guides."""
    assert "docs/guides/writing-tests.md" not in SCRIPTING_ALLOWLIST
    assert "docs/guides/adding-import-parser.md" not in SCRIPTING_ALLOWLIST


def test_build_index_markdown_lists_entries() -> None:
    """Generated index contains bullet lines for known pages."""
    body = build_index_markdown(project_root())
    assert "docs/user-guide/scripting/javascript/first-test-script.md" in body
    assert "docs/scripting/javascript-api.md" in body
    assert "`docs/user-guide/" in body


def test_build_app_wiki_script_writes_index(tmp_path: Path, monkeypatch) -> None:
    """Running the build script writes index and schema under data/app-wiki/."""
    import scripts.build_app_wiki as build_mod

    monkeypatch.setattr(build_mod, "project_root", lambda: project_root())
    assert build_mod.main() == 0
    out = project_root() / "data" / "app-wiki" / "index.md"
    assert out.is_file()
    assert (project_root() / "data" / "app-wiki" / "WIKI.md").is_file()
