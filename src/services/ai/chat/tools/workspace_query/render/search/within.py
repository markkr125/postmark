"""within_ids resolution and request-id line helpers for workspace search."""

from __future__ import annotations

import re

from services.ai.chat.workspace_snapshot import (
    WITHIN_IDS_LAST_SENTINEL,
    get_last_search_hits,
)
from services.collection_service import CollectionService

REQUEST_LINK_RE = re.compile(r"postmark://request/(\d+)")
# Back-compat alias for internal callers.
_REQUEST_LINK_RE = REQUEST_LINK_RE

_SECRET_LIKE_NEEDLE_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|client[_-]?secret|bearer\s+\S+|sk-[a-z0-9]{8,})"
)


def _needle_looks_secret_like(needle: str) -> bool:
    """Return True when *needle* looks like a credential rather than a name/URL."""
    text = needle.strip()
    if not text:
        return False
    if _SECRET_LIKE_NEEDLE_RE.search(text):
        return True
    return bool(" " not in text and len(text) >= 24 and re.fullmatch(r"[A-Za-z0-9_\-./+=]+", text))


def _request_ids_from_tree_lines(lines: list[str]) -> set[int]:
    """Collect request ids already listed by the collection-tree name/URL pass."""
    ids: set[int] = set()
    for line in lines:
        match = _REQUEST_LINK_RE.search(line)
        if match:
            ids.add(int(match.group(1)))
    return ids


def _filter_lines_by_request_ids(lines: list[str], within: set[int]) -> list[str]:
    """Keep only lines that link a request id in *within* (drop folder/script-only rows)."""
    kept: list[str] = []
    for line in lines:
        match = _REQUEST_LINK_RE.search(line)
        if match and int(match.group(1)) in within:
            kept.append(line)
    return kept


def _resolve_within_ids(
    within_ids: list[int] | None,
    *,
    session_id: str,
) -> tuple[set[int] | None, str | None]:
    """Resolve *within_ids* to an allowlist, or an error message.

    ``None`` means unrestricted search. A provided list that is empty, all-invalid,
    or resolves to zero existing requests returns an error (never unrestricted).
    ``[-1]`` / any list containing the last-hits sentinel uses the session's last
    search hit set.
    """
    if within_ids is None:
        return None, None
    if WITHIN_IDS_LAST_SENTINEL in within_ids:
        last = get_last_search_hits(session_id)
        if not last:
            return None, (
                "within_ids=[-1] means reuse the last scope=search hit set, but none is "
                "stored for this conversation. Re-run scope=search to discover requests "
                "first, then refine."
            )
        return set(last), None
    positives = [int(rid) for rid in within_ids if isinstance(rid, int) and rid > 0]
    if not positives:
        return None, (
            "within_ids was provided but contained no valid request ids "
            "(need positive integers, or [-1] for the last search hit set). "
            "Refusing to run an unrestricted search."
        )
    existing_rows = CollectionService.fetch_request_fields_for_ids(positives)
    existing = {row[0] for row in existing_rows}
    if not existing:
        return None, (
            "within_ids did not match any requests. Pass request ids from "
            "postmark://request/<id> links (not history/script/collection ids), "
            "or within_ids=[-1] to reuse the last search hits."
        )
    return existing, None
