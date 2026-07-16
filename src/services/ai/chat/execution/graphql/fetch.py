"""Fetch GraphQL schema for agent execute."""

from __future__ import annotations

from typing import Any


def run_fetch_graphql_schema(
    *,
    request_id: int | None = None,
    url: str | None = None,
    environment_id: int | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    """Introspect a GraphQL endpoint and return a truncated summary."""
    from services.ai.chat.mutation.bridge import enqueue_mutation_event
    from services.collection_service import CollectionService
    from services.environment_service import EnvironmentService
    from services.http.graphql_schema_service import GraphQLSchemaService
    from services.http.header_utils import parse_header_dict

    endpoint = (url or "").strip()
    headers: dict[str, str] | None = None
    resolved_request_id = request_id

    if resolved_request_id is not None:
        req = CollectionService.get_request(resolved_request_id)
        if req is None:
            return {
                "ok": False,
                "error": "request_not_found",
                "message": f"id={resolved_request_id}",
            }
        if not endpoint:
            endpoint = str(req.url or "").strip()
        variables = EnvironmentService.build_combined_variable_map(
            environment_id,
            resolved_request_id,
        )
        endpoint = EnvironmentService.substitute(endpoint, variables)
        raw_headers = str(req.headers or "")
        if raw_headers:
            raw_headers = EnvironmentService.substitute(raw_headers, variables)
            headers = parse_header_dict(raw_headers)
        # Auth: only use headers already on the request (placeholders resolved).
        # Do not inject raw secrets from auth dict into observation path.
    elif endpoint:
        variables = EnvironmentService.build_combined_variable_map(environment_id, None)
        endpoint = EnvironmentService.substitute(endpoint, variables)
    else:
        return {
            "ok": False,
            "error": "url_or_request_id_required",
            "message": "Provide url or request_id",
        }

    if not endpoint:
        return {"ok": False, "error": "empty_url", "message": "GraphQL URL is empty"}

    result = GraphQLSchemaService.fetch_schema(endpoint, headers=headers)
    if result.get("error"):
        return {
            "ok": False,
            "error": "schema_fetch_failed",
            "message": str(result.get("error")),
        }

    summary = GraphQLSchemaService.format_schema_summary(result)  # type: ignore[arg-type]
    types = list(result.get("types") or [])
    if search:
        needle = search.casefold()
        types = [t for t in types if needle in str(t.get("name") or "").casefold()]
    # Progressive disclosure: strip descriptions if large, then hard-truncate.
    truncated_types = _truncate_types(types)
    schema_summary = summary
    if len(schema_summary) > 4000:
        schema_summary = schema_summary[:4000] + "… (truncated)"
    type_lines = []
    for t in truncated_types[:80]:
        name = t.get("name") or "?"
        kind = t.get("kind") or ""
        type_lines.append(f"- {name} ({kind})")
    if len(truncated_types) > 80:
        type_lines.append(f"… and {len(truncated_types) - 80} more (narrow with search)")
    schema_summary = schema_summary + "\n\nTypes:\n" + "\n".join(type_lines)

    # Never put raw introspection JSON in the observation.
    schema_for_bridge = {
        "query_type": result.get("query_type"),
        "mutation_type": result.get("mutation_type"),
        "subscription_type": result.get("subscription_type"),
        "types": truncated_types[:200],
    }
    ids: dict[str, int] = {}
    if isinstance(resolved_request_id, int) and resolved_request_id > 0:
        ids["request_id"] = resolved_request_id
        enqueue_mutation_event(
            {
                "type": "attach_graphql_schema",
                "ids": ids,
                "payload": {
                    "request_id": resolved_request_id,
                    "schema": schema_for_bridge,
                },
            }
        )

    return {
        "ok": True,
        "summary": f"Fetched GraphQL schema from {endpoint}",
        "schema_summary": schema_summary,
        "ids": ids,
        "url": endpoint,
        "schema": schema_for_bridge,
    }


def _truncate_types(types: list[Any]) -> list[dict[str, Any]]:
    """Strip descriptions from type dicts for smaller observations."""
    out: list[dict[str, Any]] = []
    for item in types:
        if not isinstance(item, dict):
            continue
        row = {k: v for k, v in item.items() if k != "description"}
        fields = row.get("fields")
        if isinstance(fields, list):
            row["fields"] = [
                {fk: fv for fk, fv in f.items() if fk != "description"}
                if isinstance(f, dict)
                else f
                for f in fields
            ]
        out.append(row)
    return out
