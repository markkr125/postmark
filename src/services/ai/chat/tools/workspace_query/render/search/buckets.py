"""Fielded search bucket helpers and related-findings footer."""

from __future__ import annotations

from typing import Any

from services.assertion_service import AssertionService
from services.scripting.context import mask_sensitive_value

from ...helpers import _scripts_from_data
from ...query_parse import FieldedQuery, hay_matches_fielded


def _want_bucket(query: FieldedQuery, bucket: str) -> bool:
    """Return True when *bucket* should be searched for *query*."""
    if not query.in_buckets:
        return True
    return bucket in query.in_buckets


def _text_match(hay: str, query: FieldedQuery, legacy_tokens: list[str]) -> bool:
    """Match *hay* using fielded rules when operators are present, else legacy AND."""
    if query.has_field_constraints or query.phrases or query.or_groups or query.exclude_tokens:
        # Structural-only queries (no text) match any hay that passes excludes.
        if not query.text_tokens and not query.or_groups:
            return hay_matches_fielded(hay or " ", query)
        return hay_matches_fielded(hay, query)
    return all(t in hay.casefold() for t in legacy_tokens) if legacy_tokens else True


def _path_ok(path: str, query: FieldedQuery) -> bool:
    """Return True when *path* satisfies an optional ``path:`` prefix filter."""
    if not query.path_prefix:
        return True
    return query.path_prefix.casefold() in path.casefold()


def _method_ok(method: str, query: FieldedQuery) -> bool:
    """Return True when *method* satisfies an optional ``method:`` filter."""
    if not query.method:
        return True
    return method.upper() == query.method


def _assertion_hay(request_id: int) -> str:
    """Build a searchable string from declarative assertions for *request_id*."""
    rows = AssertionService.fetch_for_request(request_id)
    parts: list[str] = []
    for row in rows:
        subject = str(row.get("subject", ""))
        operator = str(row.get("operator", ""))
        expected = mask_sensitive_value(subject, str(row.get("expected", "")))
        parts.append(f"{subject} {operator} {expected}")
    return " ".join(parts)


def _request_has_flags(
    *,
    scripts: dict[str, str],
    assertion_enabled: int,
    auth: Any,
    unresolved_count: int,
) -> dict[str, bool]:
    """Compute boolean presence flags for has:/missing: filters."""
    has_test = bool(str(scripts.get("test") or "").strip()) or assertion_enabled > 0
    has_assert = assertion_enabled > 0
    has_auth = isinstance(auth, dict) and bool(auth)
    has_unresolved = unresolved_count > 0
    return {
        "test": has_test,
        "assert": has_assert,
        "auth": has_auth,
        "unresolved": has_unresolved,
    }


def _flags_ok(flags: dict[str, bool], query: FieldedQuery) -> bool:
    """Return True when has:/missing: constraints are satisfied."""
    if not all(flags.get(key) for key in query.has):
        return False
    return all(not flags.get(key) for key in query.missing)


def _scripts_norm(scripts: Any, events: Any) -> dict[str, str]:
    """Normalize scripts/events into a kind→source map."""
    return _scripts_from_data({"scripts": scripts, "events": events})


def _related_findings_footer(
    *,
    hit_ids: list[int],
    paths_by_id: dict[int, str],
    unresolved_hint: bool,
) -> list[str]:
    """Suggest follow-up scopes after a search with hits."""
    if not hit_ids:
        return []
    lines = [
        "\nRelated next steps (assistant only — translate to plain English for the user; "
        "never quote these operators/scopes in the chat reply):"
    ]
    # Shared folder prefix across hits.
    prefixes = [paths_by_id[rid].rsplit("/", 1)[0] for rid in hit_ids if rid in paths_by_id]
    if prefixes:
        common = prefixes[0]
        for p in prefixes[1:]:
            while common and not p.startswith(common):
                common = common.rsplit("/", 1)[0] if "/" in common else ""
        if common and common.count("/") >= 0 and len(hit_ids) >= 2:
            lines.append(
                f"- Hits share folder path `{common}` — offer to open that folder "
                "(assistant: scope=collection)."
            )
    lines.append(
        "- Among these hits, offer a health check (assistant: insights + within_ids=[-1])."
    )
    if unresolved_hint:
        lines.append(
            "- Unresolved vars likely — offer to list unresolved / disabled refs among hits."
        )
    lines.append(
        "- Product how-to questions → postmark_wiki_query (never dump wiki for workspace facts)."
    )
    return lines[:6]
