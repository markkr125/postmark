"""Environment reach map — which hosts requests hit under an environment."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from urllib.parse import urlsplit

from services.collection_service import CollectionService
from services.environment_service import EnvironmentService

from ...constants import _SEARCH_SCRIPT_SCAN_CAP
from ...helpers import _cap_rows, _key_is_sensitive, _link, _with_leading_markers
from ..insights.scans.common import _walk_request_nodes
from ..search.renderer import _resolve_url_for_request

_REDACTED_HOST = "‹redacted-host›"  # noqa: RUF001


def _secret_host_fragments(env_id: int) -> set[str]:
    """Return non-empty secret-typed / sensitive-keyed env values that may appear in hosts."""
    env = EnvironmentService.get_environment(env_id)
    if env is None or not isinstance(env.values, list):
        return set()
    out: set[str] = set()
    for item in env.values:
        if not isinstance(item, dict) or not item.get("enabled", True):
            continue
        key = str(item.get("key", ""))
        val = str(item.get("value", "")).strip()
        if not val or "{{" in val:
            continue
        typ = str(item.get("type", "")).lower()
        if (typ == "secret" or _key_is_sensitive(key)) and 3 <= len(val) <= 253:
            # Hostnames are short; ignore huge token blobs for containment checks.
            out.add(val.casefold())
    return out


def _normalize_url_for_host(resolved: str) -> str:
    """Add a scheme when missing so ``urlsplit`` can parse the hostname."""
    text = resolved.strip()
    if not text or "{{" in text:
        return text
    if "://" in text:
        return text
    if text.startswith("//"):
        return "https:" + text
    return "https://" + text


def _host_bucket(resolved: str, *, secret_fragments: set[str] | None = None) -> str:
    """Return a hostname bucket key, or ``unresolved`` when templates remain."""
    if "{{" in resolved:
        return "unresolved"
    try:
        host = urlsplit(_normalize_url_for_host(resolved)).hostname
    except ValueError:
        return "unresolved"
    if not host:
        return "unresolved"
    folded = host.casefold()
    if secret_fragments and any(frag in folded for frag in secret_fragments):
        return _REDACTED_HOST
    return host


def _bucket_requests(
    request_rows: list[tuple[int, str, str, str]],
    *,
    env_id: int,
) -> dict[str, list[tuple[int, str]]]:
    """Resolve each request URL under *env_id* and group by hostname."""
    secrets = _secret_host_fragments(env_id)
    buckets: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for rid, name, _method, url in request_rows:
        resolved = _resolve_url_for_request(
            url,
            env_id=env_id,
            request_id=rid,
            use_collection=True,
        )
        buckets[_host_bucket(resolved, secret_fragments=secrets)].append((rid, name))
    return dict(buckets)


def _format_buckets(
    buckets: dict[str, list[tuple[int, str]]],
    *,
    unresolved_label: str,
) -> list[str]:
    """Render host buckets sorted by descending request count."""
    lines: list[str] = []
    ordered = sorted(
        buckets.items(),
        key=lambda item: (
            item[0] == "unresolved",
            -len(item[1]),
            item[0],
        ),
    )
    for host, rows in ordered:
        label = unresolved_label if host == "unresolved" else host
        links = ", ".join(_link("request", rid, name) for rid, name in rows)
        lines.append(f"- {label} — {len(rows)} request{'s' if len(rows) != 1 else ''}: {links}")
    return lines


def _render_env_diff(id_a: int, id_b: int) -> str:
    """Compare hostname reach for two environments request-by-request."""
    env_a = EnvironmentService.get_environment(id_a)
    env_b = EnvironmentService.get_environment(id_b)
    if env_a is None or env_b is None:
        return "One or both environments for env_reach diff were not found."
    tree = CollectionService.fetch_all()
    request_rows = _walk_request_nodes(tree, within=None, limit=_SEARCH_SCRIPT_SCAN_CAP)
    markers: list[str] = []
    if len(request_rows) >= _SEARCH_SCRIPT_SCAN_CAP:
        markers.append(
            f"[partial] Environment reach limited to the first "
            f"{_SEARCH_SCRIPT_SCAN_CAP} requests in tree order."
        )
    secrets_a = _secret_host_fragments(id_a)
    secrets_b = _secret_host_fragments(id_b)
    lines = [
        "Environment reach diff:",
        f"  A: {_link('environment', id_a, env_a.name)}",
        f"  B: {_link('environment', id_b, env_b.name)}",
    ]
    repoints: list[str] = []
    for rid, name, _method, url in request_rows:
        resolved_a = _resolve_url_for_request(url, env_id=id_a, request_id=rid, use_collection=True)
        resolved_b = _resolve_url_for_request(url, env_id=id_b, request_id=rid, use_collection=True)
        host_a = _host_bucket(resolved_a, secret_fragments=secrets_a)
        host_b = _host_bucket(resolved_b, secret_fragments=secrets_b)
        if host_a == host_b:
            continue
        repoints.append(f"- {_link('request', rid, name)} — {host_a} → {host_b}")
    if repoints:
        lines.append("  Host re-points:")
        lines.extend(_cap_rows(repoints, label="re-points"))
    else:
        lines.append("  (no hostname differences under these environments)")
    body = "\n".join(lines)
    return _with_leading_markers(body, markers) if markers else body


def _render_env_reach(
    *,
    snap: dict[str, Any] | None = None,
    env_id: int | None = None,
    search: str = "",
) -> str:
    """Map requests to resolved hostnames under one environment (or diff two)."""
    raw = search.strip()
    if raw.lower().startswith("diff:"):
        parts = raw.split(":", 2)
        if len(parts) != 3:
            return "env_reach diff requires search=diff:<envIdA>:<envIdB>."
        try:
            id_a = int(parts[1].strip())
            id_b = int(parts[2].strip())
        except ValueError:
            return "env_reach diff requires integer environment ids."
        return _render_env_diff(id_a, id_b)

    snap = snap or {}
    target = env_id
    if target is None:
        env_raw = snap.get("current_env_id")
        target = env_raw if isinstance(env_raw, int) else None
    if target is None:
        return (
            "No environment selected. Select an environment in the app or pass "
            "target_id=<environment id> (or search=diff:<idA>:<idB> to compare)."
        )
    env = EnvironmentService.get_environment(target)
    if env is None:
        return f"Environment {target} not found."

    tree = CollectionService.fetch_all()
    request_rows = _walk_request_nodes(tree, within=None, limit=_SEARCH_SCRIPT_SCAN_CAP)
    markers: list[str] = []
    if len(request_rows) >= _SEARCH_SCRIPT_SCAN_CAP:
        markers.append(
            f"[partial] Environment reach limited to the first "
            f"{_SEARCH_SCRIPT_SCAN_CAP} requests in tree order."
        )
    if not request_rows:
        return "No requests in the workspace."

    buckets = _bucket_requests(request_rows, env_id=target)
    lines = [
        f"Environment reach for {_link('environment', target, env.name)}:",
    ]
    bucket_lines = _format_buckets(
        buckets,
        unresolved_label="unresolved ({{…}} not set in this env)",
    )
    if bucket_lines:
        lines.extend(_cap_rows(bucket_lines, label="host buckets"))
    else:
        lines.append("  (no requests)")
    body = "\n".join(lines)
    return _with_leading_markers(body, markers) if markers else body
