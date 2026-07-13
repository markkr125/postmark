"""Collection walkthrough scope renderer."""

from __future__ import annotations

from typing import Any

from services.collection_service import CollectionService
from services.environment_service import EnvironmentService

from ...constants import _SEARCH_SCRIPT_SCAN_CAP
from ...helpers import _default_collection_id, _link, _with_leading_markers
from ..dependencies.graph import (
    _STATIC_CAVEAT,
    build_dependency_graph,
    pick_start_request,
    topo_run_order,
)
from ..insights.scans.common import _extract_var_refs, _walk_request_nodes
from ..search.renderer import _resolve_url_for_request


def _collect_subtree_request_ids(
    nodes: dict[str, Any],
    *,
    root_id: int,
) -> tuple[set[int], list[tuple[str, str]]]:
    """Return request ids under *root_id* and folder blurbs ``(path, blurb)``."""
    found_root = False
    request_ids: set[int] = set()
    folders: list[tuple[str, str]] = []

    def walk(ns: dict[str, Any], prefix: str = "", *, collecting: bool) -> None:
        nonlocal found_root
        for node in ns.values():
            name = str(node.get("name", ""))
            path = f"{prefix}/{name}" if prefix else name
            nid = node.get("id")
            if node.get("type") == "folder" and isinstance(nid, int):
                here = collecting or nid == root_id
                if nid == root_id:
                    found_root = True
                if here and nid != root_id:
                    desc = ""
                    row = CollectionService.get_collection(nid)
                    if row is not None and getattr(row, "description", None):
                        desc = str(row.description or "").strip().split("\n", 1)[0][:80]
                    if not desc:
                        children = node.get("children") or {}
                        for child in children.values():
                            if child.get("type") == "request":
                                desc = f"includes {child.get('name', 'request')}"
                                break
                    folders.append((path, desc or "folder"))
                walk(node.get("children") or {}, path, collecting=here)
            elif collecting and node.get("type") == "request" and isinstance(nid, int):
                request_ids.add(int(nid))

    walk(nodes, collecting=False)
    if not found_root:
        walk(nodes, collecting=True)
    return request_ids, folders


def _env_keys_to_supply(
    nodes: set[int],
    graph: dict[str, Any],
    *,
    env_id: int | None,
) -> tuple[list[str], list[str]]:
    """Return ``(env_needed, runtime_needed)`` variable keys for the walkthrough."""
    produced_by: dict[str, list[tuple[int, str]]] = graph["produced_by"]
    runtime_set = set(produced_by)
    unresolved: set[str] = set()
    runtime_needed: set[str] = set()

    for rid in nodes:
        url = graph["urls"].get(rid, "")
        url_refs = _extract_var_refs(url)
        for key in url_refs & runtime_set:
            runtime_needed.add(key)
        if env_id is not None:
            resolved = _resolve_url_for_request(
                url, env_id=env_id, request_id=rid, use_collection=True
            )
            # Keys still present as {{…}} after substitution were *not* supplied
            # by the env; script-produced keys belong under runtime_needed only.
            leftover = _extract_var_refs(resolved)
            unresolved |= leftover - runtime_set
            runtime_needed |= leftover & runtime_set
            var_map = EnvironmentService.build_combined_variable_map(env_id, rid)
            for key in graph["consumer_keys"].get(rid, set()):
                if key in runtime_set:
                    runtime_needed.add(key)
                elif key not in var_map:
                    unresolved.add(key)
        else:
            unresolved |= url_refs - runtime_set
            for key in graph["consumer_keys"].get(rid, set()):
                if key in runtime_set:
                    runtime_needed.add(key)
                else:
                    unresolved.add(key)

    return sorted(unresolved), sorted(runtime_needed)


def _render_walkthrough(
    *,
    snap: dict[str, Any] | None = None,
    collection_id: int | None = None,
) -> str:
    """Assemble a guided narrative for one collection/folder."""
    snap = snap or {}
    cid = collection_id if collection_id is not None else _default_collection_id(snap)
    if cid is None:
        return "No collection id; open a folder tab or set target_id."
    coll = CollectionService.get_collection(cid)
    if coll is None:
        return f"Collection {cid} not found."

    tree = CollectionService.fetch_all()
    subtree_ids, folders = _collect_subtree_request_ids(tree, root_id=cid)
    if not subtree_ids:
        all_rows = _walk_request_nodes(tree, within=None, limit=_SEARCH_SCRIPT_SCAN_CAP)
        subtree_ids = {rid for rid, _n, _m, _u in all_rows}

    graph = build_dependency_graph(within=subtree_ids if subtree_ids else None)
    names: dict[int, str] = graph["names"]
    edges: list[tuple[int, str, int]] = graph["edges"]
    produced_by: dict[str, list[tuple[int, str]]] = graph["produced_by"]
    markers: list[str] = []
    if graph["partial"]:
        markers.append(
            f"[partial] Walkthrough dependency scan limited to the first "
            f"{_SEARCH_SCRIPT_SCAN_CAP} requests in tree order."
        )

    lines = [f"Walkthrough — collection {_link('collection', cid, coll.name)}:"]

    nodes = set(names.keys()) & (subtree_ids or set(names.keys()))
    if not nodes:
        nodes = set(names.keys())

    start_rid = pick_start_request(nodes, edges, produced_by, names)
    if start_rid is not None:
        produced_keys = [
            k for k, prods in produced_by.items() if any(p == start_rid for p, _w in prods)
        ]
        if len(produced_keys) > 1:
            blurb = (
                f" — produces {{{{{produced_keys[0]}}}}} "
                f"(+{len(produced_keys) - 1} more) the rest may need"
            )
        elif produced_keys:
            blurb = f" — produces {{{{{produced_keys[0]}}}}} the rest need"
        else:
            blurb = ""
        lines.append(
            f"Start here: {_link('request', start_rid, names.get(start_rid, str(start_rid)))}"
            f"{blurb}."
        )
    else:
        lines.append("Start here: (no requests in this collection).")

    auth_line = "Auth: (none detected on scanned requests)."
    sample_rid = start_rid if start_rid is not None else next(iter(nodes), None)
    if sample_rid is not None:
        chain = CollectionService.get_request_auth_chain(sample_rid)
        if isinstance(chain, dict) and chain:
            atype = str(chain.get("type") or "inherit")
            auth_line = (
                f"Auth: {atype} (inherited chain for "
                f"{_link('request', sample_rid, names.get(sample_rid, str(sample_rid)))})."
            )
        else:
            auth_line = "Auth: no inherited auth on scanned requests."
    lines.append(auth_line)

    env_raw = snap.get("current_env_id")
    env_id = env_raw if isinstance(env_raw, int) else None
    env_needed, runtime_needed = _env_keys_to_supply(nodes, graph, env_id=env_id)
    env_label = "an environment"
    if env_id is not None:
        env = EnvironmentService.get_environment(env_id)
        if env is not None:
            env_label = _link("environment", env_id, env.name)
    env_bits: list[str] = []
    if env_needed:
        env_bits.append("supply " + ", ".join(f"{{{{{k}}}}}" for k in env_needed[:8]))
    if runtime_needed:
        env_bits.append(
            "runtime-set by scripts: " + ", ".join(f"{{{{{k}}}}}" for k in runtime_needed[:8])
        )
    if env_bits:
        lines.append(f"Environment: select {env_label}; " + "; ".join(env_bits) + ".")
    else:
        lines.append(f"Environment: select {env_label} (no unresolved env vars detected).")

    if folders:
        folder_bits = []
        for path, blurb in folders[:12]:
            folder_bits.append(f"{path} ({blurb})" if blurb else path)
        lines.append("Folders: " + " · ".join(folder_bits) + ".")
    else:
        lines.append("Folders: (flat collection — no nested folders).")

    if not edges:
        lines.append("Suggested first run: (no static dependency edges — run any request).")
    else:
        order, blocked = topo_run_order(edges, nodes)
        if blocked:
            markers.append(
                "[partial] Dependency cycle or blocked nodes — suggested run order incomplete."
            )
            lines.append(
                "Suggested first run: (cycle/blocked) "
                + ", ".join(_link("request", rid, names[rid]) for rid in blocked[:8])
            )
            if order:
                run_chain = " → ".join(_link("request", rid, names[rid]) for rid in order[:15])
                lines.append(f"Acyclic prefix: {run_chain}.")
        elif order:
            run_chain = " → ".join(_link("request", rid, names[rid]) for rid in order[:15])
            lines.append(f"Suggested first run: {run_chain}.")

    lines.append(_STATIC_CAVEAT)

    body = "\n".join(lines)
    return _with_leading_markers(body, markers) if markers else body
