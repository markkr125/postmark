"""Collection tree and environment scope renderers for the workspace query tool."""

from __future__ import annotations

import json
from typing import Any, cast

from services.collection_service import CollectionService
from services.environment_service import EnvironmentService

from ...constants import _HEADER_VALUE_MAX
from ...helpers import (
    _cap_rows,
    _follow_up_ids_block,
    _format_env_pairs,
    _format_ts,
    _link,
    _redact_auth,
    _redact_env_values,
    _scripts_from_data,
    _truncate_text,
    _truncate_url,
    _walk_tree,
)


def _render_collection_tree(search: str) -> str:
    """Render folder→request tree with optional filter."""
    tree = CollectionService.fetch_all()
    lines = _walk_tree(tree, search=search.strip())
    if not lines:
        return "No collections or requests match." if search.strip() else "No collections."
    title = "Collection tree"
    if search.strip():
        title += f' (filter: "{search.strip()}")'
    body = _cap_rows(lines, label="rows")
    return title + ":\n" + "\n".join(body)


def _render_environments(*, env_id: int | None = None, search: str = "") -> str:
    """List environments with masked secret variable values.

    ``search=diff:<idA>:<idB>`` compares two environments (keys + masked value diffs).
    """
    raw = search.strip()
    if raw.lower().startswith("diff:"):
        parts = raw.split(":", 2)
        if len(parts) != 3:
            return "environments diff requires search=diff:<envIdA>:<envIdB>."
        try:
            id_a = int(parts[1].strip())
            id_b = int(parts[2].strip())
        except ValueError:
            return "environments diff requires integer environment ids."
        env_a = EnvironmentService.get_environment(id_a)
        env_b = EnvironmentService.get_environment(id_b)
        if env_a is None or env_b is None:
            return "One or both environments for diff were not found."
        vals_a = {
            str(v.get("key", "")): v
            for v in _redact_env_values(env_a.values if isinstance(env_a.values, list) else None)
            if v.get("enabled", True) and str(v.get("key", ""))
        }
        vals_b = {
            str(v.get("key", "")): v
            for v in _redact_env_values(env_b.values if isinstance(env_b.values, list) else None)
            if v.get("enabled", True) and str(v.get("key", ""))
        }
        only_a = sorted(set(vals_a) - set(vals_b))
        only_b = sorted(set(vals_b) - set(vals_a))
        shared_diff = sorted(
            k
            for k in set(vals_a) & set(vals_b)
            if str(vals_a[k].get("value", "")) != str(vals_b[k].get("value", ""))
        )
        lines = [
            "Environment diff:",
            f"  A: {_link('environment', id_a, env_a.name)}",
            f"  B: {_link('environment', id_b, env_b.name)}",
        ]
        if only_a:
            lines.append("  Only in A:")
            lines.extend(_cap_rows([f"    - {k}" for k in only_a], label="only-A keys"))
        if only_b:
            lines.append("  Only in B:")
            lines.extend(_cap_rows([f"    - {k}" for k in only_b], label="only-B keys"))
        if shared_diff:
            lines.append("  Value differs (masked):")
            for k in shared_diff[:40]:
                lines.append(
                    f"    - {k}: A={_truncate_text(str(vals_a[k].get('value', '')), max_len=40)} · "
                    f"B={_truncate_text(str(vals_b[k].get('value', '')), max_len=40)}"
                )
        if not only_a and not only_b and not shared_diff:
            lines.append("  (no differences in enabled keys)")
        return "\n".join(lines)
    if env_id is not None:
        env = EnvironmentService.get_environment(env_id)
        if env is None:
            return "Environment not found."
        values = _redact_env_values(env.values if isinstance(env.values, list) else None)
        var_rows = [
            f"{v.get('key', '')} = {_truncate_text(str(v.get('value', '')), max_len=_HEADER_VALUE_MAX)}"
            for v in values
            if v.get("enabled", True)
        ]
        lines = [f"Environment {_link('environment', env_id, env.name)}:"]
        if var_rows:
            lines.extend(_cap_rows([f"- {row}" for row in var_rows], label="variables"))
        else:
            lines.append("(no variables)")
        lines.extend(_follow_up_ids_block([(f"environment · {env.name}", env_id)]))
        return "\n".join(lines)
    envs = EnvironmentService.fetch_all()
    if not envs:
        return "No environments."
    env_lines: list[str] = []
    follow_ups: list[tuple[str, int]] = []
    for env_row in envs:
        eid = env_row.get("id")
        name = str(env_row.get("name", ""))
        values = _redact_env_values(env_row.get("values") or [])
        pairs = _format_env_pairs(values)
        header = _link("environment", eid, name) if isinstance(eid, int) else name
        env_lines.append(f"- {header}: {', '.join(pairs) if pairs else '(no variables)'}")
        if isinstance(eid, int):
            follow_ups.append((f"environment · {name}", eid))
    lines = ["Environments:"]
    lines.extend(_cap_rows(env_lines, label="environments"))
    lines.extend(_follow_up_ids_block(follow_ups))
    return "\n".join(lines)


def _render_collection(collection_id: int) -> str:
    """Render one folder's own configuration and direct children."""
    row = CollectionService.get_collection(collection_id)
    if row is None:
        return "Collection not found."
    breadcrumb = CollectionService.get_collection_breadcrumb(collection_id)
    path = " / ".join(str(seg.get("name", "")) for seg in breadcrumb)
    lines = [
        f"{_link('collection', collection_id, row.name)}:",
        f"  Path: {path}",
    ]
    if getattr(row, "updated_at", None) is not None:
        lines.append(f"  Last edited: {_format_ts(row.updated_at)}")
    if row.description:
        lines.append(f"  Description: {_truncate_text(str(row.description), max_len=400)}")
    auth = _redact_auth(row.auth if isinstance(row.auth, dict) else None)
    if auth:
        lines.append(f"  Auth: {json.dumps(auth, ensure_ascii=False)}")
    elif row.auth is None:
        inherited = _redact_auth(CollectionService.get_collection_inherited_auth(collection_id))
        if inherited:
            lines.append(f"  Inherited auth: {json.dumps(inherited, ensure_ascii=False)}")
        else:
            lines.append("  Inherited auth: (none / no-auth)")
    values = _redact_env_values(row.variables if isinstance(row.variables, list) else None)
    if values:
        pairs = _format_env_pairs(values)
        lines.append(f"  Variables: {', '.join(pairs)}")
    scripts = _scripts_from_data({"events": row.events})
    for kind, src in scripts.items():
        lines.append(
            f"\n  {kind} script ({_link('collection', collection_id, row.name, focus=kind)}):"
        )
        lines.append(_truncate_text(src, max_len=1200))
    count = CollectionService.get_folder_request_count(collection_id)
    lines.append(f"  Requests in subtree: {count}")
    child_lines: list[str] = []
    tree = CollectionService.fetch_all()

    def _find_node(nodes: dict[str, Any], cid: int) -> dict[str, Any] | None:
        for node in nodes.values():
            if node.get("type") == "folder" and node.get("id") == cid:
                return cast(dict[str, Any], node)
            found = _find_node(node.get("children") or {}, cid)
            if found is not None:
                return found
        return None

    node = _find_node(tree, collection_id)
    if node is not None:
        for _key, child in sorted(
            (node.get("children") or {}).items(),
            key=lambda kv: str(kv[1].get("name", "")).casefold(),
        ):
            ctype = child.get("type")
            cid = child.get("id")
            cname = str(child.get("name", ""))
            if ctype == "folder" and isinstance(cid, int):
                child_lines.append(f"  - {_link('collection', cid, cname)} (folder)")
            elif ctype == "request" and isinstance(cid, int):
                method = str(child.get("method", "GET"))
                url = _truncate_url(str(child.get("url", "")))
                child_lines.append(f"  - {_link('request', cid, cname)} — {method} {url}")
    if child_lines:
        lines.append("  Direct children:")
        lines.extend(_cap_rows(child_lines, label="children"))
    return "\n".join(lines)
