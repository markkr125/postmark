"""Workspace search for the postmark_app_context tool."""

from __future__ import annotations

from typing import Any, Literal

from database.models.collections import collection_query_repository
from database.models.local_scripts import local_script_query_repository
from database.models.request_history import request_history_repository
from database.models.environments.environment_repository import fetch_all_environments
from services.ai.chat.context_redaction import redact_env_values

SearchScope = Literal[
    "all",
    "collections",
    "requests",
    "local_scripts",
    "content",
    "send_history",
    "saved_responses",
    "environments",
]

_MAX_HITS = 50
_SNIPPET_LEN = 120


def _history_label(row: dict[str, Any]) -> str:
    """Format a send-history row label with optional (deleted) suffix."""
    name = str(row.get("request_name") or row.get("url") or "History")
    method = str(row.get("method") or "")
    suffix = ""
    if row.get("request_id") is None and row.get("was_persisted_request"):
        suffix = " (deleted)"
    return f"{method} {name}{suffix}".strip()


def _append_hit(
    hits: list[str],
    *,
    kind: str,
    label: str,
    entity_id: int,
    snippet: str = "",
) -> None:
    """Append one markdown hit line if under the global cap."""
    if len(hits) >= _MAX_HITS:
        return
    line = f"- [{kind}] {label} (id={entity_id})"
    if snippet:
        line += f" — {snippet[:_SNIPPET_LEN]}"
    hits.append(line)


def search_app_context(query: str, scope: SearchScope) -> str:
    """Return a markdown index of workspace matches for *query*."""
    term = query.strip()
    if not term:
        return "Provide a non-empty query for focus=search."

    hits: list[str] = []
    scopes: list[SearchScope]
    if scope == "all":
        scopes = [
            "collections",
            "requests",
            "local_scripts",
            "send_history",
            "saved_responses",
            "environments",
        ]
    elif scope == "content":
        scopes = ["content"]
    else:
        scopes = [scope]

    for sc in scopes:
        if len(hits) >= _MAX_HITS:
            break
        if sc == "collections":
            for row in collection_query_repository.search_collections(term, limit=20):
                _append_hit(
                    hits,
                    kind="collection",
                    label=str(row.get("name") or ""),
                    entity_id=int(row["id"]),
                )
        elif sc == "requests":
            for row in collection_query_repository.search_requests(term, limit=30):
                label = f"{row.get('method', '')} {row.get('name', '')}".strip()
                _append_hit(hits, kind="request", label=label, entity_id=int(row["id"]))
        elif sc == "local_scripts":
            for row in local_script_query_repository.search_local_scripts(term, limit=30):
                _append_hit(
                    hits,
                    kind="local_script",
                    label=str(row.get("name") or ""),
                    entity_id=int(row["id"]),
                )
        elif sc == "content":
            for row in collection_query_repository.search_requests(
                term, limit=20, include_content=True
            ):
                label = f"{row.get('method', '')} {row.get('name', '')}".strip()
                _append_hit(
                    hits,
                    kind="request",
                    label=label,
                    entity_id=int(row["id"]),
                    snippet=str(row.get("body_snippet") or ""),
                )
            for row in local_script_query_repository.search_local_scripts(
                term, limit=20, include_content=True
            ):
                _append_hit(
                    hits,
                    kind="local_script",
                    label=str(row.get("name") or ""),
                    entity_id=int(row["id"]),
                    snippet=str(row.get("content_snippet") or ""),
                )
        elif sc == "send_history":
            for row in request_history_repository.list_entries_for_sidebar(search=term, limit=30):
                _append_hit(
                    hits,
                    kind="history",
                    label=_history_label(row),
                    entity_id=int(row["id"]),
                )
        elif sc == "saved_responses":
            for row in collection_query_repository.search_saved_responses(term, limit=20):
                _append_hit(
                    hits,
                    kind="saved_response",
                    label=str(row.get("name") or ""),
                    entity_id=int(row["id"]),
                )
        elif sc == "environments":
            term_lower = term.lower()
            for env in fetch_all_environments():
                name = str(env.get("name") or "")
                values = env.get("values") or []
                key_match = any(
                    term_lower in str(v.get("key") or "").lower()
                    for v in values
                    if isinstance(v, dict)
                )
                if term_lower not in name.lower() and not key_match:
                    continue
                _append_hit(
                    hits,
                    kind="environment",
                    label=name,
                    entity_id=int(env["id"]),
                )

    header = f"## Matches ({len(hits)})\n"
    if not hits:
        return header + "_No matches._"
    return header + "\n".join(hits)


def format_environment_detail(environment_id: int) -> str:
    """Return redacted environment key/value detail."""
    for env in fetch_all_environments():
        if int(env["id"]) != environment_id:
            continue
        lines = [f"# Environment: {env.get('name')}", f"id={environment_id}"]
        values: dict[str, str] = {}
        for row in env.get("values") or []:
            if isinstance(row, dict):
                key = str(row.get("key") or "")
                if key:
                    values[key] = str(row.get("value") or "")
        for key, value in redact_env_values(values).items():
            lines.append(f"{key}={value}")
        return "\n".join(lines)
    return f"Environment id={environment_id} not found."
