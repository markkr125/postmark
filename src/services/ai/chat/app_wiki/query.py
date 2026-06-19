"""Read-only wiki query executor for ``postmark_wiki_query``."""

from __future__ import annotations

import re
from pathlib import Path

from database.data_paths import project_root
from services.ai.chat.app_wiki.config import (
    MAX_MATCHED_PAGES,
    WIKI_CHAR_CAP,
    is_allowed_wiki_doc,
    resolve_allowed_path,
    wiki_index_path,
)

_INDEX_LINE_RE = re.compile(r"^-\s+`(?P<path>[^`]+)`\s+—\s+(?P<title>[^—]+)\s+—\s+(?P<summary>.+)$")


def _load_index(root: Path) -> str:
    """Load ``data/app-wiki/index.md`` or return an empty index."""
    path = wiki_index_path(root)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _parse_index_entries(index_text: str) -> list[tuple[str, str, str]]:
    """Parse bullet lines from the generated index."""
    entries: list[tuple[str, str, str]] = []
    for line in index_text.splitlines():
        match = _INDEX_LINE_RE.match(line.strip())
        if match is None:
            continue
        entries.append(
            (
                match.group("path").strip(),
                match.group("title").strip(),
                match.group("summary").strip(),
            )
        )
    return entries


def _score_entry(query: str, path: str, title: str, summary: str) -> int:
    """Higher score = better match (simple substring scoring)."""
    q = query.casefold().strip()
    if not q:
        return 0
    hay = f"{path} {title} {summary}".casefold()
    if q in hay:
        return 100 + hay.count(q)
    tokens = [t for t in re.split(r"\W+", q) if len(t) >= 2]
    return sum(10 for t in tokens if t in hay)


def _search_index(index_text: str, query: str) -> list[str]:
    """Return repo-relative paths ranked by relevance to *query*."""
    ranked: list[tuple[int, str]] = []
    for path, title, summary in _parse_index_entries(index_text):
        if not is_allowed_wiki_doc(path):
            continue
        score = _score_entry(query, path, title, summary)
        if score > 0:
            ranked.append((score, path))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    seen: set[str] = set()
    out: list[str] = []
    for _, path in ranked:
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
        if len(out) >= MAX_MATCHED_PAGES:
            break
    return out


def _read_excerpt(path: Path, remaining: int) -> tuple[str, int]:
    """Read up to *remaining* characters from *path*."""
    if remaining <= 0:
        return "", 0
    text = path.read_text(encoding="utf-8")
    if len(text) <= remaining:
        return text, len(text)
    return text[:remaining] + "\n\n… [truncated]", remaining


def execute_wiki_query(
    query: str,
    *,
    page: str | None = None,
    root: Path | None = None,
    char_cap: int = WIKI_CHAR_CAP,
) -> str:
    """Run a wiki lookup and return formatted excerpts for the LLM."""
    repo = root or project_root()
    index_text = _load_index(repo)

    paths: list[str] = []
    if page:
        norm_page = page.replace("\\", "/").lstrip("/")
        if resolve_allowed_path(norm_page, repo) is not None:
            paths = [norm_page]
        else:
            # Explicit page does not exist/allowed — fall back to a keyword
            # search seeded with the page's filename so a slightly-wrong path
            # (e.g. wrong subfolder) still returns the right docs instead of a
            # dead-end error that derails the model.
            hint = norm_page.rsplit("/", 1)[-1].removesuffix(".md").replace("-", " ")
            paths = _search_index(index_text, f"{query} {hint}".strip())

    if not paths:
        paths = _search_index(index_text, query)
    if not paths and index_text:
        first_token = query.split()
        if first_token:
            paths = _search_index(index_text, first_token[0])

    if not paths:
        hint = (
            "No matching wiki pages. Retry with simpler keywords and no explicit page "
            "(e.g. 'pre-request script', 'create collection', 'pm.expect')."
        )
        if not index_text:
            hint += " Index missing — run scripts/build_app_wiki.py."
        return hint

    parts: list[str] = []
    remaining = char_cap
    for rel in paths:
        resolved = resolve_allowed_path(rel, repo)
        if resolved is None:
            continue
        excerpt, used = _read_excerpt(resolved, remaining)
        if not excerpt:
            break
        parts.append(f"## {rel}\n\n{excerpt}")
        remaining -= used
        if remaining <= 0:
            break

    if not parts:
        return (
            "No readable pages matched. Retry postmark_wiki_query with simpler "
            "keywords and no explicit page (e.g. 'pre-request script')."
        )

    header = f"# Wiki results for: {query.strip() or page or ''}\n\n"
    return header + "\n\n---\n\n".join(parts)
