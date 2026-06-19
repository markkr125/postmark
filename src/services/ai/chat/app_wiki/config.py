"""Allowlisted roots and paths for the app wiki query tool."""

from __future__ import annotations

from pathlib import Path

from database.data_paths import project_root

WIKI_CHAR_CAP = 12_000
MAX_MATCHED_PAGES = 8

# Prose scripting pages ingested into the wiki index (not all of docs/scripting/).
SCRIPTING_ALLOWLIST: tuple[str, ...] = (
    "docs/scripting/overview.md",
    "docs/scripting/javascript-api.md",
    "docs/scripting/python-api.md",
    "docs/scripting/examples.md",
    "docs/scripting/postman-parity.md",
    "docs/scripting/external-packages.md",
    "docs/scripting/local-modules.md",
    "docs/scripting/snippets.md",
    "docs/guides/writing-scripts.md",
)


def docs_root(root: Path | None = None) -> Path:
    """Return the ``docs/`` directory under the project root."""
    return (root or project_root()) / "docs"


def user_guide_root(root: Path | None = None) -> Path:
    """Return ``docs/user-guide/``."""
    return docs_root(root) / "user-guide"


def app_wiki_root(root: Path | None = None) -> Path:
    """Return ``data/app-wiki/``."""
    return (root or project_root()) / "data" / "app-wiki"


def wiki_index_path(root: Path | None = None) -> Path:
    """Return the generated wiki index file."""
    return app_wiki_root(root) / "index.md"


def is_allowed_wiki_doc(rel_path: str, root: Path | None = None) -> bool:
    """Return whether *rel_path* (posix, repo-relative) may be read by the wiki tool."""
    norm = rel_path.replace("\\", "/").lstrip("/")
    if norm.startswith("docs/user-guide/") and norm.endswith(".md"):
        return True
    if norm in SCRIPTING_ALLOWLIST:
        return True
    return norm.startswith("data/app-wiki/") and norm.endswith(".md")


def resolve_allowed_path(rel_path: str, root: Path | None = None) -> Path | None:
    """Resolve *rel_path* to an absolute path if allowlisted; else ``None``."""
    norm = rel_path.replace("\\", "/").lstrip("/")
    if not is_allowed_wiki_doc(norm, root):
        return None
    repo = root or project_root()
    candidate = (repo / norm).resolve()
    try:
        candidate.relative_to(repo.resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate
