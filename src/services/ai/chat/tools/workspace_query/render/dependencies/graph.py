"""Static request dependency graph helpers for workspace query scopes."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from services.collection_service import CollectionService

from ...constants import _SEARCH_SCRIPT_SCAN_CAP
from ...helpers import _script_assigned_variable_keys, _scripts_from_data
from ..insights.scans.common import _extract_var_refs, _walk_request_nodes

_STATIC_CAVEAT = (
    '(Static analysis — only literal pm.*.set("key", …) is detected; '
    "dynamic/response-derived vars are not.)"
)

_AUTH_PRODUCER_KEYS = frozenset({"token", "access_token", "auth_token", "bearer"})


def _field_texts(field_row: Any, url: str) -> list[str]:
    """Collect consumer-haystack texts (URL/headers/params/body/auth — not description)."""
    texts = [url]
    if field_row is None:
        return texts
    (
        _name,
        body,
        _body_mode,
        _body_options,
        _description,
        headers,
        auth,
        params,
    ) = field_row
    if body:
        texts.append(str(body))
    if isinstance(headers, list):
        for h in headers:
            if isinstance(h, dict):
                texts.append(f"{h.get('key', '')} {h.get('value', '')}")
    if isinstance(params, list):
        for p in params:
            if isinstance(p, dict):
                texts.append(f"{p.get('key', '')} {p.get('value', '')}")
    if isinstance(auth, dict):
        texts.append(str(auth))
    return texts


def _script_sources(script_row: Any) -> tuple[str, str]:
    """Return ``(pre_request, test)`` source strings from a scripts prefetch row."""
    if script_row is None:
        return "", ""
    _sname, scripts, events = script_row
    norm = _scripts_from_data({"scripts": scripts, "events": events})
    return norm.get("pre_request", "") or "", norm.get("test", "") or ""


def _where_set(pre: str, test: str, key: str) -> str:
    """Describe which script(s) statically set *key*."""
    pre_keys = _script_assigned_variable_keys(pre)
    test_keys = _script_assigned_variable_keys(test)
    in_pre = key in pre_keys
    in_test = key in test_keys
    if in_pre and in_test:
        return "pre-request + test"
    if in_pre:
        return "pre-request"
    if in_test:
        return "test script"
    return "script"


def graph_from_prefetch(
    request_rows: list[tuple[int, str, str, str]],
    scripts_by_id: dict[int, Any],
    fields_by_id: dict[int, Any],
    *,
    partial: bool = False,
) -> dict[str, Any]:
    """Build the dependency graph dict from already-fetched request rows/maps."""
    names = {rid: name for rid, name, _m, _u in request_rows}
    urls = {rid: url for rid, _n, _m, url in request_rows}

    produced_by: dict[str, list[tuple[int, str]]] = defaultdict(list)
    consumed_by: dict[str, list[int]] = defaultdict(list)
    producer_keys: dict[int, set[str]] = {}
    consumer_keys: dict[int, set[str]] = {}

    for rid, _name, _method, url in request_rows:
        pre, test = _script_sources(scripts_by_id.get(rid))
        produced = _script_assigned_variable_keys(pre, test)
        producer_keys[rid] = produced
        for key in produced:
            produced_by[key].append((rid, _where_set(pre, test, key)))

        texts = _field_texts(fields_by_id.get(rid), url)
        texts.extend([pre, test])
        used = _extract_var_refs(*texts)
        consumer_keys[rid] = used
        for key in used:
            consumed_by[key].append(rid)

    edges: list[tuple[int, str, int]] = []
    for key, producers in produced_by.items():
        consumers = consumed_by.get(key) or []
        for prod_rid, _where in producers:
            for cons_rid in consumers:
                if cons_rid == prod_rid:
                    continue
                edges.append((prod_rid, key, cons_rid))

    return {
        "request_rows": request_rows,
        "names": names,
        "urls": urls,
        "produced_by": dict(produced_by),
        "consumed_by": dict(consumed_by),
        "producer_keys": producer_keys,
        "consumer_keys": consumer_keys,
        "edges": edges,
        "orphan_producers": sorted(k for k in produced_by if not consumed_by.get(k)),
        "undefined_consumers": sorted(k for k in consumed_by if k not in produced_by),
        "partial": partial,
    }


def build_dependency_graph(
    *,
    within: set[int] | None = None,
    limit: int = _SEARCH_SCRIPT_SCAN_CAP,
) -> dict[str, Any]:
    """Build a static producer→consumer graph over scanned requests.

    Returns a dict with keys: ``request_rows``, ``names``, ``produced_by``,
    ``consumed_by``, ``edges`` (list of ``(producer, key, consumer)``),
    ``orphan_producers``, ``undefined_consumers``, ``partial``.
    """
    tree = CollectionService.fetch_all()
    request_rows = _walk_request_nodes(tree, within=within, limit=limit)
    request_ids = [rid for rid, _n, _m, _u in request_rows]
    partial = len(request_ids) >= limit
    scripts_by_id = {
        rid: (name, scripts, events)
        for rid, name, scripts, events in CollectionService.fetch_request_scripts_for_ids(
            request_ids
        )
    }
    fields_by_id = {
        rid: (name, body, body_mode, body_options, description, headers, auth, params)
        for rid, name, body, body_mode, body_options, description, headers, auth, params in (
            CollectionService.fetch_request_fields_for_ids(request_ids)
        )
    }
    return graph_from_prefetch(
        request_rows,
        scripts_by_id,
        fields_by_id,
        partial=partial,
    )


def pick_start_request(
    nodes: set[int],
    edges: list[tuple[int, str, int]],
    produced_by: dict[str, list[tuple[int, str]]],
    names: dict[int, str],
) -> int | None:
    """Pick a sensible entry-point request (prefer producers of consumed vars)."""
    if not nodes:
        return None

    # 1. Auth-token producers that feed at least one consumer edge.
    for prod, key, cons in edges:
        if prod in nodes and cons in nodes and key.casefold() in _AUTH_PRODUCER_KEYS:
            return prod

    # 2. Any producer with an outgoing edge (produces a var others consume).
    edge_producers = sorted(
        {prod for prod, _key, cons in edges if prod in nodes and cons in nodes},
        key=lambda r: names.get(r, ""),
    )
    if edge_producers:
        return edge_producers[0]

    # 3. Auth-token producers even without consumers (orphan but intentional).
    for key, prods in produced_by.items():
        if key.casefold() not in _AUTH_PRODUCER_KEYS:
            continue
        for prod, _where in prods:
            if prod in nodes:
                return prod

    # 4. Any producer in the subgraph.
    any_producers = sorted(
        {prod for prods in produced_by.values() for prod, _where in prods if prod in nodes},
        key=lambda r: names.get(r, ""),
    )
    if any_producers:
        return any_producers[0]

    # 5. Alphabetical fallback when there are no static producers.
    return sorted(nodes, key=lambda r: names.get(r, ""))[0]


def topo_run_order(
    edges: list[tuple[int, str, int]], nodes: set[int]
) -> tuple[list[int], list[int]]:
    """Return ``(order, blocked_nodes)`` for *nodes* given producer→consumer *edges*.

    Edges mean producer should run before consumer. *blocked_nodes* are those
    that could not be ordered (cycle members and anything downstream of a cycle).
    """
    preds: dict[int, set[int]] = {n: set() for n in nodes}
    succs: dict[int, set[int]] = {n: set() for n in nodes}
    for prod, _key, cons in edges:
        if prod not in nodes or cons not in nodes:
            continue
        preds[cons].add(prod)
        succs[prod].add(cons)

    ready = sorted(n for n in nodes if not preds[n])
    order: list[int] = []
    remaining = set(nodes)
    while ready:
        n = ready.pop(0)
        order.append(n)
        remaining.discard(n)
        for s in sorted(succs[n]):
            preds[s].discard(n)
            if not preds[s] and s in remaining and s not in ready:
                ready.append(s)
                ready.sort()
    return order, sorted(remaining)


def linked_var_rids(graph: dict[str, Any]) -> set[int]:
    """Return request ids that appear as a producer or consumer on any edge."""
    linked: set[int] = set()
    for prod, _key, cons in graph["edges"]:
        linked.add(prod)
        linked.add(cons)
    return linked
