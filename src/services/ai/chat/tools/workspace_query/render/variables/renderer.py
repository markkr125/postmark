"""Variable definition / resolution / usage renderer for workspace query."""

from __future__ import annotations

import json
import re
from typing import Any

from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.scripting.context import load_globals, mask_sensitive_value

from ...constants import SECRET_PLACEHOLDER, _SEARCH_SCRIPT_SCAN_CAP
from ...helpers import (
    _cap_rows,
    _collection_secret_keys_by_id,
    _default_collection_id,
    _default_request_id,
    _key_is_sensitive,
    _link,
    _mask_header_value,
    _mask_param_value,
    _redact_auth,
    _redact_env_values,
    _redact_request_body,
    _script_assigned_variable_keys,
    _scripts_from_data,
    _secret_keys_from_variable_rows,
    _truncate_text,
    _with_leading_markers,
)
from ..search import (
    _count_tree_folders,
    _count_tree_requests,
    _ordered_collection_ids_for_script_scan,
    _ordered_request_ids_for_script_scan,
)

_VAR_REF_PREFIX = r"\{\{\s*"
_VAR_REF_SUFFIX = r"\s*\}\}"


def _usage_patterns(keys: list[str]) -> list[re.Pattern[str]]:
    """Compile case-sensitive ``{{key}}`` matchers for each exact spelling."""
    return [re.compile(_VAR_REF_PREFIX + re.escape(k) + _VAR_REF_SUFFIX) for k in keys]


def _hay_matches_any(hay: str, patterns: list[re.Pattern[str]]) -> bool:
    """Return True when any usage pattern matches *hay*."""
    return any(p.search(hay) for p in patterns)


def _similar_keys(needle_cf: str, candidates: set[str], *, limit: int = 10) -> list[str]:
    """Return up to *limit* keys that look similar to *needle_cf*."""
    scored: list[tuple[int, str]] = []
    for key in candidates:
        folded = key.casefold()
        if folded == needle_cf:
            continue
        if folded.startswith(needle_cf) or needle_cf.startswith(folded):
            scored.append((0, key))
        elif needle_cf in folded or folded in needle_cf:
            scored.append((1, key))
    scored.sort(key=lambda pair: (pair[0], pair[1].casefold()))
    return [key for _rank, key in scored[:limit]]


def _format_def_value(key: str, value: str, *, is_secret: bool) -> str:
    """Format a definition value with secret masking."""
    if is_secret or _key_is_sensitive(key):
        return SECRET_PLACEHOLDER
    return _truncate_text(value, max_len=200)


def _render_variable(search: str, *, snap: dict[str, Any] | None = None) -> str:
    """Report where a variable key is defined, what wins, and where it is used."""
    needle = search.strip()
    if not needle:
        return (
            "Provide non-empty ``search`` for scope=variable "
            "(the variable key to look up, e.g. base_url)."
        )
    snap = snap or {}
    needle_cf = needle.casefold()
    scan_cap = _SEARCH_SCRIPT_SCAN_CAP

    globals_map = load_globals()
    all_known_keys: set[str] = set(globals_map)
    spellings: set[str] = set()
    def_lines: list[str] = []

    if needle_cf in {k.casefold() for k in globals_map}:
        for gkey, gval in sorted(globals_map.items(), key=lambda kv: kv[0].casefold()):
            if gkey.casefold() != needle_cf:
                continue
            spellings.add(gkey)
            masked = mask_sensitive_value(gkey, str(gval))
            display = (
                SECRET_PLACEHOLDER if masked != gval else _truncate_text(str(gval), max_len=200)
            )
            def_lines.append(f"- Globals · {gkey} = {display}")

    for env in EnvironmentService.fetch_all():
        eid = env.get("id")
        ename = str(env.get("name", ""))
        if not isinstance(eid, int):
            continue
        raw_values = env.get("values")
        values = raw_values if isinstance(raw_values, list) else []
        for item in values:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", ""))
            all_known_keys.add(key)
            if key.casefold() != needle_cf:
                continue
            spellings.add(key)
            redacted = _redact_env_values([item])
            raw_val = str(redacted[0].get("value", "")) if redacted else ""
            flags = []
            if str(item.get("type", "")).lower() == "secret" or raw_val == SECRET_PLACEHOLDER:
                flags.append("secret")
            if item.get("enabled") is False:
                flags.append("disabled")
            flag_s = f" ({', '.join(flags)})" if flags else ""
            def_lines.append(
                f"- {_link('environment', eid, ename)} · {key} = "
                f"{_truncate_text(raw_val, max_len=200)}{flag_s}"
            )

    tree = CollectionService.fetch_all()
    folder_ids = _ordered_collection_ids_for_script_scan(tree, limit=scan_cap)
    folder_events: dict[int, Any] = {}
    folder_names: dict[int, str] = {}
    total_folders = _count_tree_folders(tree)
    folder_capped = total_folders > scan_cap

    for cid in folder_ids:
        row = CollectionService.get_collection(cid)
        if row is None:
            continue
        folder_names[cid] = str(row.name or "")
        folder_events[cid] = row.events
        variables = row.variables if isinstance(row.variables, list) else []
        for item in variables:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", ""))
            all_known_keys.add(key)
            if key.casefold() != needle_cf:
                continue
            spellings.add(key)
            redacted = _redact_env_values([item])
            raw_val = str(redacted[0].get("value", "")) if redacted else ""
            flags = []
            if str(item.get("type", "")).lower() == "secret" or raw_val == SECRET_PLACEHOLDER:
                flags.append("secret")
            if item.get("enabled") is False:
                flags.append("disabled")
            flag_s = f" ({', '.join(flags)})" if flags else ""
            def_lines.append(
                f"- {_link('collection', cid, folder_names[cid])} · {key} = "
                f"{_truncate_text(raw_val, max_len=200)}{flag_s}"
            )

    usage_keys = sorted({*spellings, needle}, key=str.casefold)
    usage_key_set = set(usage_keys)
    patterns = _usage_patterns(usage_keys)

    # Resolution (active context).
    env_id_raw = snap.get("current_env_id")
    env_id = env_id_raw if isinstance(env_id_raw, int) else None
    request_id = _default_request_id(snap)
    collection_id = None if request_id is not None else _default_collection_id(snap)
    details = EnvironmentService.build_combined_variable_detail_map(
        env_id,
        request_id,
        collection_id=collection_id,
    )
    env_secret_keys: set[str] = set()
    if env_id is not None:
        env_row = EnvironmentService.get_environment(env_id)
        if env_row is not None:
            env_secret_keys = _secret_keys_from_variable_rows(
                env_row.values if isinstance(env_row.values, list) else None
            )
    coll_secret_by_id = _collection_secret_keys_by_id(details)

    def _is_secret_value(key: str, source: str, source_id: object) -> bool:
        if _key_is_sensitive(key):
            return True
        if source == "environment" and key in env_secret_keys:
            return True
        return (
            source == "collection"
            and isinstance(source_id, int)
            and key in coll_secret_by_id.get(source_id, set())
        )

    resolution_lines: list[str] = []
    active_spelling: str | None = None
    for key in usage_keys:
        if key in details or key in globals_map:
            active_spelling = key
            break
    if active_spelling is None and spellings:
        active_spelling = sorted(spellings, key=str.casefold)[0]

    env_label = "none"
    if env_id is not None:
        env_row = EnvironmentService.get_environment(env_id)
        env_label = str(env_row.name or env_id) if env_row is not None else str(env_id)
    if request_id is not None:
        req_row = CollectionService.get_request(request_id)
        ctx_label = (
            f"environment: {env_label}, request: "
            f"{req_row.name if req_row is not None else request_id}"
        )
    elif collection_id is not None:
        coll_row = CollectionService.get_collection(collection_id)
        ctx_label = (
            f"environment: {env_label}, collection: "
            f"{coll_row.name if coll_row is not None else collection_id}"
        )
    else:
        ctx_label = f"environment: {env_label}, request: none"

    if active_spelling is not None:
        chain_parts: list[str] = []
        detail = details.get(active_spelling)
        env_def: str | None = None
        coll_def: str | None = None
        if isinstance(detail, dict):
            source = str(detail.get("source", ""))
            source_id = detail.get("source_id")
            value = str(detail.get("value", ""))
            display = _format_def_value(
                active_spelling,
                value,
                is_secret=_is_secret_value(active_spelling, source, source_id),
            )
            if source == "environment" and isinstance(source_id, int):
                env_row = EnvironmentService.get_environment(source_id)
                label = env_row.name if env_row is not None else f"environment {source_id}"
                env_def = f"environment [{_link('environment', source_id, label)}] = {display}"
            elif source == "collection" and isinstance(source_id, int):
                crow = CollectionService.get_collection(source_id)
                label = crow.name if crow is not None else f"collection {source_id}"
                coll_def = f"collection [{_link('collection', source_id, label)}] = {display}"

        if coll_def is None:
            coll_only = EnvironmentService.build_combined_variable_detail_map(
                None,
                request_id,
                collection_id=collection_id,
            )
            cdetail = coll_only.get(active_spelling)
            if isinstance(cdetail, dict) and cdetail.get("source") == "collection":
                source_id = cdetail.get("source_id")
                if isinstance(source_id, int):
                    crow = CollectionService.get_collection(source_id)
                    if crow is not None and source_id not in coll_secret_by_id:
                        coll_secret_by_id[source_id] = _secret_keys_from_variable_rows(
                            crow.variables if isinstance(crow.variables, list) else None
                        )
                    label = crow.name if crow is not None else f"collection {source_id}"
                    display = _format_def_value(
                        active_spelling,
                        str(cdetail.get("value", "")),
                        is_secret=_is_secret_value(active_spelling, "collection", source_id),
                    )
                    coll_def = f"collection [{_link('collection', source_id, label)}] = {display}"

        global_def: str | None = None
        if active_spelling in globals_map:
            masked = mask_sensitive_value(active_spelling, str(globals_map[active_spelling]))
            display = (
                SECRET_PLACEHOLDER
                if masked != globals_map[active_spelling]
                else _truncate_text(str(globals_map[active_spelling]), max_len=200)
            )
            global_def = (
                f"globals = {display} (scripts only — pm.globals; "
                "never substituted into URLs/headers)"
            )

        if isinstance(detail, dict) and str(detail.get("source")) == "environment":
            if env_def:
                chain_parts.append(f"{env_def} (wins)")
            if coll_def:
                chain_parts.append(coll_def)
            if global_def:
                chain_parts.append(global_def)
        elif isinstance(detail, dict) and str(detail.get("source")) == "collection":
            if coll_def:
                chain_parts.append(f"{coll_def} (wins)")
            if global_def:
                chain_parts.append(global_def)
        elif global_def and not isinstance(detail, dict):
            chain_parts.append(
                f"{global_def} (wins — global-only; not used in URL/header substitution)"
            )

        if chain_parts:
            resolution_lines.append(
                f"Active override chain for `{active_spelling}` (highest first):"
            )
            resolution_lines.append("  " + " → ".join(chain_parts))
        elif spellings and active_spelling in spellings:
            disabled_in_active = False
            if env_id is not None:
                env_row = EnvironmentService.get_environment(env_id)
                active_values = (
                    env_row.values
                    if env_row is not None and isinstance(env_row.values, list)
                    else None
                )
                if active_values is not None:
                    for item in active_values:
                        if not isinstance(item, dict):
                            continue
                        if str(item.get("key", "")) != active_spelling:
                            continue
                        disabled_in_active = item.get("enabled") is False
                        break
            if disabled_in_active:
                resolution_lines.append(
                    f"`{active_spelling}` is defined in the active environment but disabled "
                    "(not used in substitution until enabled)."
                )
            else:
                resolution_lines.append(
                    f"`{active_spelling}` is defined, but not in the active environment/"
                    "collection context (defined only in other environments or folders)."
                )
        else:
            resolution_lines.append(
                f"`{needle}` is not defined in globals, environments, or scanned collections."
            )
    else:
        resolution_lines.append(
            f"`{needle}` is not defined in globals, environments, or scanned collections."
        )

    # Usages — bounded request + folder-script DFS.
    request_ids = _ordered_request_ids_for_script_scan(tree, limit=scan_cap)
    total_requests = _count_tree_requests(tree)
    req_capped = total_requests > scan_cap
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
    usage_rows: list[str] = []
    scanned = 0

    def _sets_it(src: str) -> bool:
        return any(k in usage_key_set for k in _script_assigned_variable_keys(src))

    def _scan_usages(nodes: dict[str, Any], prefix: str = "") -> None:
        nonlocal scanned
        for node in nodes.values():
            name = str(node.get("name", ""))
            path = f"{prefix}/{name}" if prefix else name
            if node.get("type") == "folder":
                cid = node.get("id")
                if isinstance(cid, int) and cid in folder_events:
                    norm = _scripts_from_data({"events": folder_events[cid]})
                    parts: list[str] = []
                    for kind, src in norm.items():
                        matched = _hay_matches_any(src, patterns)
                        sets_it = _sets_it(src)
                        if matched and sets_it:
                            parts.append(f"{kind} script (sets it)")
                        elif matched:
                            parts.append(f"{kind} script")
                        elif sets_it:
                            parts.append(f"{kind} script (sets it)")
                    if parts:
                        usage_rows.append(
                            f"- {_link('collection', cid, name)} — {', '.join(parts)} · in {path}"
                        )
                _scan_usages(node.get("children") or {}, path)
            elif node.get("type") == "request" and isinstance(node.get("id"), int):
                rid = int(node["id"])
                if scanned >= scan_cap:
                    return
                scanned += 1
                field_row = fields_by_id.get(rid)
                script_row = scripts_by_id.get(rid)
                parts = []
                if field_row is not None:
                    (
                        _fname,
                        body,
                        body_mode,
                        body_options,
                        _description,
                        headers,
                        auth,
                        params,
                    ) = field_row
                    url = str(node.get("url") or "")
                    if _hay_matches_any(url, patterns):
                        parts.append("url")
                    if isinstance(headers, list):
                        for h in headers:
                            if not isinstance(h, dict):
                                continue
                            hkey = str(h.get("key", ""))
                            hval = _mask_header_value(hkey, str(h.get("value", "")))
                            if _hay_matches_any(f"{hkey} {hval}", patterns):
                                parts.append("headers")
                                break
                    if isinstance(params, list):
                        for p in params:
                            if not isinstance(p, dict):
                                continue
                            pkey = str(p.get("key", ""))
                            pval = _mask_param_value(pkey, str(p.get("value", "")))
                            if _hay_matches_any(f"{pkey} {pval}", patterns):
                                parts.append("params")
                                break
                    body_ctx = {
                        "body_mode": body_mode,
                        "body_options": body_options,
                        "headers": headers,
                        "auth": auth,
                    }
                    full_body = _redact_request_body(str(body or ""), body_ctx) if body else ""
                    if full_body and _hay_matches_any(full_body, patterns):
                        parts.append("body")
                    if isinstance(auth, dict):
                        redacted_auth = _redact_auth(auth) or {}
                        auth_blob = json.dumps(redacted_auth, ensure_ascii=False)
                        if _hay_matches_any(auth_blob, patterns):
                            parts.append("auth")
                if script_row is not None:
                    _sname, scripts, events = script_row
                    norm = _scripts_from_data({"scripts": scripts, "events": events})
                    for kind, src in norm.items():
                        matched = _hay_matches_any(src, patterns)
                        sets_it = _sets_it(src)
                        if matched and sets_it:
                            parts.append(f"{kind} script (sets it)")
                        elif matched:
                            parts.append(f"{kind} script")
                        elif sets_it:
                            parts.append(f"{kind} script (sets it)")
                if parts:
                    usage_rows.append(
                        f"- {_link('request', rid, name)} — {', '.join(parts)} · in {path}"
                    )

    _scan_usages(tree)

    markers: list[str] = []
    scan_capped = folder_capped or req_capped
    out: list[str] = [f'Variable report for "{needle}":']

    if not spellings:
        similar = _similar_keys(needle_cf, all_known_keys)
        if similar:
            out.append("No exact definitions found. Similar keys:")
            for key in similar:
                out.append(f"- {key}")
        else:
            out.append("No exact definitions found.")
    else:
        out.append("\nDefinitions:")
        out.extend(_cap_rows(def_lines, label="definitions"))

    out.append(f"\nResolution ({ctx_label}):")
    out.extend(resolution_lines)

    out.append("\nUsages:")
    if usage_rows:
        out.extend(_cap_rows(usage_rows, label="usages"))
    elif scan_capped:
        markers.insert(
            0,
            "[partial] No usages found in the scanned subset — a match may exist "
            f"beyond the first {scan_cap} requests/folders.",
        )
        out.append("No usages in the scanned subset (see partial marker above).")
    else:
        markers.insert(
            0,
            f"[authoritative] No usages of `{needle}` in request URL/headers/params/"
            "body/auth/scripts or scanned folder scripts.",
        )
        out.append("No usages (see authoritative marker above).")

    if scan_capped and usage_rows:
        markers.append(
            f"[partial] Usage/definition collection scan capped at the first {scan_cap} "
            "requests/folders in tree order."
        )

    return _with_leading_markers("\n".join(out), markers)
