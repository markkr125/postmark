"""Local ``$ref`` resolution for OpenAPI documents."""

from __future__ import annotations

from typing import Any


def resolve_ref(
    doc: dict[str, Any],
    node: Any,
    warnings: list[str],
    *,
    depth: int = 0,
) -> Any:
    """Resolve local ``#/…`` refs; leave external refs with a warning."""
    if depth > 32 or not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if not isinstance(ref, str) or not ref:
        return node
    if not ref.startswith("#/"):
        warnings.append(f"Skipped external $ref: {ref}")
        return node
    cur: Any = doc
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(cur, dict) or part not in cur:
            warnings.append(f"Unresolved $ref: {ref}")
            return node
        cur = cur[part]
    if isinstance(cur, dict) and "$ref" in cur:
        return resolve_ref(doc, cur, warnings, depth=depth + 1)
    return cur


__all__ = ["resolve_ref"]
