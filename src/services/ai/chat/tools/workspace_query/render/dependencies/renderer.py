"""Request dependency graph scope renderer."""

from __future__ import annotations

from typing import Any

from ...constants import _SEARCH_SCRIPT_SCAN_CAP
from ...helpers import _cap_rows, _link, _with_leading_markers
from .graph import _STATIC_CAVEAT, build_dependency_graph, topo_run_order


def _render_dependencies(
    *,
    snap: dict[str, Any] | None = None,
    target_id: int | None = None,
    session_id: str = "",
) -> str:
    """Render static producer/consumer edges for one request or the workspace."""
    del snap  # reserved for future focus defaults
    graph = build_dependency_graph()
    names: dict[int, str] = graph["names"]
    produced_by: dict[str, list[tuple[int, str]]] = graph["produced_by"]
    edges: list[tuple[int, str, int]] = graph["edges"]
    markers: list[str] = []
    if graph["partial"]:
        markers.append(
            f"[partial] Dependency scan limited to the first "
            f"{_SEARCH_SCRIPT_SCAN_CAP} requests in tree order."
        )

    if target_id is not None:
        if target_id not in names:
            return f"Request {target_id} not found in the scanned workspace."
        focus_name = names[target_id]
        lines = [f"Dependencies for {_link('request', target_id, focus_name)}:"]
        producers: list[str] = []
        for prod, key, cons in edges:
            if cons != target_id:
                continue
            where = "script"
            for prid, w in produced_by.get(key, []):
                if prid == prod:
                    where = w
                    break
            producers.append(
                f"- {_link('request', prod, names.get(prod, str(prod)))} sets "
                f"{{{{{key}}}}} ({where}) → used in "
                f"{_link('request', target_id, focus_name)}"
            )
        lines.append("Must run first (producers):")
        if producers:
            lines.extend(_cap_rows(producers, label="producers"))
        else:
            lines.append("  (none)")

        consumers: list[str] = []
        for prod, key, cons in edges:
            if prod != target_id:
                continue
            consumers.append(
                f"- {_link('request', cons, names.get(cons, str(cons)))} uses "
                f"{{{{{key}}}}} set by {_link('request', target_id, focus_name)}"
            )
        lines.append("Depends on this request (consumers):")
        if consumers:
            lines.extend(_cap_rows(consumers, label="consumers"))
        else:
            lines.append("  (none)")
    else:
        lines = ["Workspace dependencies (static analysis):"]
        edge_lines = [
            f"- {_link('request', prod, names.get(prod, str(prod)))} "
            f"——{{{{{key}}}}}→ {_link('request', cons, names.get(cons, str(cons)))}"
            for prod, key, cons in edges
        ]
        if edge_lines:
            lines.append("Edges:")
            lines.extend(_cap_rows(edge_lines, label="edges"))
        else:
            lines.append("  (no producer→consumer edges detected)")

        nodes = set(names)
        if not edges:
            lines.append("Cycles: none")
            lines.append("Suggested run order: (no static edges — run any request)")
        else:
            order, blocked = topo_run_order(edges, nodes)
            if blocked:
                markers.append("[partial] Cycle detected — full run order unavailable.")
                cycle_links = ", ".join(_link("request", rid, names[rid]) for rid in blocked)
                lines.append(f"Could not order (cycle or blocked): {cycle_links}")
                if order:
                    chain = " → ".join(_link("request", rid, names[rid]) for rid in order[:40])
                    lines.append(f"Suggested run order (acyclic prefix): {chain}")
            else:
                lines.append("Cycles: none")
                if order:
                    chain = " → ".join(_link("request", rid, names[rid]) for rid in order[:40])
                    lines.append(f"Suggested run order: {chain}")

        if graph["orphan_producers"]:
            orphan = ", ".join(f"{{{{{k}}}}}" for k in graph["orphan_producers"][:20])
            lines.append(f"Orphan producers (set but unused): {orphan}")
        if graph["undefined_consumers"]:
            undef = ", ".join(f"{{{{{k}}}}}" for k in graph["undefined_consumers"][:20])
            lines.append(f"Used but not statically produced: {undef}")

    lines.append(_STATIC_CAVEAT)
    if session_id:
        from services.ai.chat.workspace_snapshot import set_last_search_hits

        hit_ids = sorted({n for prod, _k, cons in edges for n in (prod, cons)})
        if hit_ids:
            set_last_search_hits(session_id, hit_ids)

    body = "\n".join(lines)
    return _with_leading_markers(body, markers) if markers else body
