"""Workspace search renderer for the workspace query tool."""

from __future__ import annotations

import json
import re
from typing import Any

from services.ai.chat.workspace_snapshot import (
    WITHIN_IDS_LAST_SENTINEL,
    get_last_search_hits,
    set_last_search_hits,
)
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.local_script_service import LocalScriptService

from ..constants import _SEARCH_SCRIPT_SCAN_CAP
from ..helpers import (
    _cap_rows,
    _link,
    _mask_header_value,
    _mask_param_value,
    _redact_auth,
    _redact_request_body,
    _scripts_from_data,
    _walk_tree,
    _with_leading_markers,
)


def _count_tree_requests(nodes: dict[str, Any]) -> int:
    """Count all request nodes in a collection tree."""
    count = 0
    for node in nodes.values():
        if node.get("type") == "folder":
            count += _count_tree_requests(node.get("children") or {})
        elif node.get("type") == "request":
            count += 1
    return count


def _count_tree_folders(nodes: dict[str, Any]) -> int:
    """Count all folder nodes in a collection tree."""
    count = 0
    for node in nodes.values():
        if node.get("type") == "folder":
            count += 1
            count += _count_tree_folders(node.get("children") or {})
    return count


def _count_local_scripts(nodes: dict[str, Any]) -> int:
    """Count all script nodes in the local-script tree."""
    count = 0
    for node in nodes.values():
        if node.get("type") == "folder":
            count += _count_local_scripts(node.get("children") or {})
        elif node.get("type") == "script":
            count += 1
    return count


def _ordered_request_ids_for_script_scan(
    nodes: dict[str, Any],
    *,
    limit: int = _SEARCH_SCRIPT_SCAN_CAP,
) -> list[int]:
    """DFS-collect request ids in tree order, capped for script-content scanning."""
    ids: list[int] = []

    def walk(ns: dict[str, Any]) -> None:
        for node in ns.values():
            if len(ids) >= limit:
                return
            if node.get("type") == "folder":
                walk(node.get("children") or {})
            elif node.get("type") == "request" and isinstance(node.get("id"), int):
                ids.append(node["id"])
                if len(ids) >= limit:
                    return

    walk(nodes)
    return ids


def _ordered_collection_ids_for_script_scan(
    nodes: dict[str, Any],
    *,
    limit: int = _SEARCH_SCRIPT_SCAN_CAP,
) -> list[int]:
    """DFS-collect folder ids in tree order, capped for folder-script scanning."""
    ids: list[int] = []

    def walk(ns: dict[str, Any]) -> None:
        for node in ns.values():
            if len(ids) >= limit:
                return
            if node.get("type") == "folder" and isinstance(node.get("id"), int):
                ids.append(node["id"])
                walk(node.get("children") or {})
                if len(ids) >= limit:
                    return

    walk(nodes)
    return ids


def _ordered_local_script_ids_for_scan(
    nodes: dict[str, Any],
    *,
    limit: int = _SEARCH_SCRIPT_SCAN_CAP,
) -> list[int]:
    """DFS-collect local script ids in tree order, capped for content scanning."""
    ids: list[int] = []

    def walk(ns: dict[str, Any]) -> None:
        for node in ns.values():
            if len(ids) >= limit:
                return
            if node.get("type") == "folder":
                walk(node.get("children") or {})
            elif node.get("type") == "script" and isinstance(node.get("id"), int):
                ids.append(node["id"])
                if len(ids) >= limit:
                    return

    walk(nodes)
    return ids


_REQUEST_LINK_RE = re.compile(r"postmark://request/(\d+)")

# Needles that look like secrets — search cannot match redacted body/header values.
_SECRET_LIKE_NEEDLE_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|client[_-]?secret|bearer\s+\S+|sk-[a-z0-9]{8,})"
)


def _needle_looks_secret_like(needle: str) -> bool:
    """Return True when *needle* looks like a credential rather than a name/URL."""
    text = needle.strip()
    if not text:
        return False
    if _SECRET_LIKE_NEEDLE_RE.search(text):
        return True
    # Long opaque tokens without spaces (API keys, JWTs, hex secrets).
    return bool(" " not in text and len(text) >= 24 and re.fullmatch(r"[A-Za-z0-9_\-./+=]+", text))


def _request_ids_from_tree_lines(lines: list[str]) -> set[int]:
    """Collect request ids already listed by the collection-tree name/URL pass."""
    ids: set[int] = set()
    for line in lines:
        match = _REQUEST_LINK_RE.search(line)
        if match:
            ids.add(int(match.group(1)))
    return ids


def _filter_lines_by_request_ids(lines: list[str], within: set[int]) -> list[str]:
    """Keep only lines that link a request id in *within* (drop folder/script-only rows)."""
    kept: list[str] = []
    for line in lines:
        match = _REQUEST_LINK_RE.search(line)
        if match and int(match.group(1)) in within:
            kept.append(line)
    return kept


def _resolve_within_ids(
    within_ids: list[int] | None,
    *,
    session_id: str,
) -> tuple[set[int] | None, str | None]:
    """Resolve *within_ids* to an allowlist, or an error message.

    ``None`` means unrestricted search. A provided list that is empty, all-invalid,
    or resolves to zero existing requests returns an error (never unrestricted).
    ``[-1]`` / any list containing the last-hits sentinel uses the session's last
    search hit set.
    """
    if within_ids is None:
        return None, None
    if WITHIN_IDS_LAST_SENTINEL in within_ids:
        last = get_last_search_hits(session_id)
        if not last:
            return None, (
                "within_ids=[-1] means reuse the last scope=search hit set, but none is "
                "stored for this conversation. Re-run scope=search to discover requests "
                "first, then refine."
            )
        return set(last), None
    positives = [int(rid) for rid in within_ids if isinstance(rid, int) and rid > 0]
    if not positives:
        return None, (
            "within_ids was provided but contained no valid request ids "
            "(need positive integers, or [-1] for the last search hit set). "
            "Refusing to run an unrestricted search."
        )
    existing_rows = CollectionService.fetch_request_fields_for_ids(positives)
    existing = {row[0] for row in existing_rows}
    if not existing:
        return None, (
            "within_ids did not match any requests. Pass request ids from "
            "postmark://request/<id> links (not history/script/collection ids), "
            "or within_ids=[-1] to reuse the last search hits."
        )
    return existing, None


def _params_haystack(params: list[dict[str, Any]] | None) -> str:
    """Build a redacted searchable string from a request params table."""
    if not isinstance(params, list):
        return ""
    parts: list[str] = []
    for row in params:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key", ""))
        value = _mask_param_value(key, str(row.get("value", "")))
        parts.append(f"{key}={value}")
    return " ".join(parts)


def _render_search(
    query: str,
    *,
    snap: dict[str, Any] | None = None,
    within_ids: list[int] | None = None,
    session_id: str = "",
) -> str:
    """Search requests, folders, and script content."""
    needle = query.strip()
    if not needle:
        return "Provide non-empty ``search`` for scope=search."
    within, within_err = _resolve_within_ids(within_ids, session_id=session_id)
    if within_err:
        return within_err
    n = needle.casefold()
    tree = CollectionService.fetch_all()
    lines: list[str] = []
    _walk_tree(tree, search=needle, lines=lines)
    tree_matched_request_ids = _request_ids_from_tree_lines(lines)
    env_id_raw = (snap or {}).get("current_env_id")
    env_id = env_id_raw if isinstance(env_id_raw, int) else None
    var_map = EnvironmentService.build_combined_variable_map(env_id, None)
    resolved_url_hits: list[str] = []
    saw_template_url = False

    def _resolve_url(url: str) -> str:
        resolved = url
        for key, value in var_map.items():
            resolved = resolved.replace(f"{{{{{key}}}}}", str(value))
        return resolved

    def _scan_resolved_urls(nodes: dict[str, Any]) -> None:
        nonlocal saw_template_url
        for node in nodes.values():
            if node.get("type") == "folder":
                _scan_resolved_urls(node.get("children") or {})
            elif node.get("type") == "request" and isinstance(node.get("id"), int):
                rid = int(node["id"])
                if within is not None and rid not in within:
                    continue
                raw_url = str(node.get("url") or "")
                if "{{" in raw_url:
                    saw_template_url = True
                if rid in tree_matched_request_ids:
                    continue
                resolved = _resolve_url(raw_url)
                name = str(node.get("name", ""))
                if n in resolved.casefold() and n not in raw_url.casefold():
                    resolved_url_hits.append(
                        f"- {_link('request', rid, name)} (resolved URL match)"
                    )

    _scan_resolved_urls(tree)
    if resolved_url_hits:
        lines.extend(resolved_url_hits)
    if within is not None:
        lines = _filter_lines_by_request_ids(lines, within)
    script_matches: list[str] = []
    body_matches: list[str] = []
    header_matches: list[str] = []
    param_matches: list[str] = []
    scanned = 0
    ordered_ids = _ordered_request_ids_for_script_scan(tree)
    ordered_folder_ids = _ordered_collection_ids_for_script_scan(tree)
    local_tree = LocalScriptService.fetch_all()
    ordered_script_ids = _ordered_local_script_ids_for_scan(local_tree)
    scripts_by_id = {
        rid: (name, scripts, events)
        for rid, name, scripts, events in CollectionService.fetch_request_scripts_for_ids(
            ordered_ids
        )
    }
    folder_scripts_by_id = {
        cid: (name, events)
        for cid, name, events in CollectionService.fetch_folder_scripts_for_ids(ordered_folder_ids)
    }
    local_scripts_by_id = {
        sid: (name, content)
        for sid, name, content in LocalScriptService.fetch_local_script_contents_for_ids(
            ordered_script_ids
        )
    }
    fields_by_id = {
        rid: (
            name,
            body,
            body_mode,
            body_options,
            description,
            headers,
            auth,
            params,
        )
        for rid, name, body, body_mode, body_options, description, headers, auth, params in (
            CollectionService.fetch_request_fields_for_ids(ordered_ids)
        )
    }

    def _scan_requests(nodes: dict[str, Any]) -> None:
        nonlocal scanned
        for node in nodes.values():
            if node.get("type") == "folder":
                cid = node.get("id")
                # Folder-script hits have no request id — drop when refining a prior list.
                if within is None and isinstance(cid, int):
                    folder_row = folder_scripts_by_id.get(cid)
                    if folder_row is not None:
                        fname, events = folder_row
                        norm_scripts = _scripts_from_data({"events": events})
                        for kind, src in norm_scripts.items():
                            if n in src.casefold():
                                script_matches.append(
                                    f"- {_link('collection', cid, fname, focus=kind)} "
                                    f"({kind} folder script match)"
                                )
                _scan_requests(node.get("children") or {})
            elif node.get("type") == "request" and isinstance(node.get("id"), int):
                rid = node["id"]
                if within is not None and rid not in within:
                    continue
                if scanned >= _SEARCH_SCRIPT_SCAN_CAP:
                    return
                scanned += 1
                row_data = scripts_by_id.get(rid)
                if row_data is not None:
                    name, scripts, events = row_data
                    norm_scripts = _scripts_from_data({"scripts": scripts, "events": events})
                    for kind, src in norm_scripts.items():
                        if n in src.casefold():
                            script_matches.append(
                                f"- {_link('request', rid, name, focus=kind)} ({kind} script match)"
                            )
                field_row = fields_by_id.get(rid)
                if field_row is not None:
                    (
                        fname,
                        body,
                        body_mode,
                        body_options,
                        description,
                        headers,
                        auth,
                        params,
                    ) = field_row
                    body_ctx = {
                        "body_mode": body_mode,
                        "body_options": body_options,
                        "headers": headers,
                        "auth": auth,
                    }
                    full_body = _redact_request_body(str(body or ""), body_ctx) if body else ""
                    desc = str(description or "")
                    if (full_body and n in full_body.casefold()) or (desc and n in desc.casefold()):
                        body_matches.append(
                            f"- {_link('request', rid, fname)} (body/description match)"
                        )
                    params_hay = _params_haystack(params)
                    if params_hay and n in params_hay.casefold():
                        param_matches.append(f"- {_link('request', rid, fname)} (params match)")
                    matched_header = False
                    if isinstance(headers, list):
                        for h in headers:
                            if not isinstance(h, dict):
                                continue
                            hkey = str(h.get("key", ""))
                            hval = str(h.get("value", ""))
                            hay = f"{hkey} {_mask_header_value(hkey, hval)}".casefold()
                            if n in hay:
                                header_matches.append(
                                    f"- {_link('request', rid, fname)} (header match)"
                                )
                                matched_header = True
                                break
                    if isinstance(auth, dict) and not matched_header:
                        redacted_auth = _redact_auth(auth) or {}
                        auth_type = str(redacted_auth.get("type", ""))
                        auth_blob = json.dumps(redacted_auth, ensure_ascii=False).casefold()
                        if n in auth_type.casefold() or n in auth_blob:
                            header_matches.append(f"- {_link('request', rid, fname)} (auth match)")

    _scan_requests(tree)
    # Local scripts have no request id — skip when refining a prior request list.
    if within is None:
        local_scanned = 0
        for sid in ordered_script_ids:
            if local_scanned >= _SEARCH_SCRIPT_SCAN_CAP:
                break
            local_scanned += 1
            row = local_scripts_by_id.get(sid)
            if row is None:
                continue
            name, content = row
            if n in content.casefold() or n in name.casefold():
                script_matches.append(f"- {_link('script', sid, name)} (local script match)")
    has_tree = bool(lines)
    has_scripts = bool(script_matches)
    has_body = bool(body_matches)
    has_headers = bool(header_matches)
    has_params = bool(param_matches)
    all_hit_ids = sorted(
        _request_ids_from_tree_lines(lines)
        | _request_ids_from_tree_lines(body_matches)
        | _request_ids_from_tree_lines(header_matches)
        | _request_ids_from_tree_lines(param_matches)
        | _request_ids_from_tree_lines(script_matches)
    )
    if session_id and all_hit_ids:
        set_last_search_hits(session_id, all_hit_ids)
    cap = _SEARCH_SCRIPT_SCAN_CAP
    total_requests = _count_tree_requests(tree)
    total_folders = _count_tree_folders(tree)
    total_local_scripts = _count_local_scripts(local_tree)
    req_capped = total_requests > cap
    folder_capped = total_folders > cap
    local_capped = total_local_scripts > cap
    any_deep_capped = req_capped or folder_capped or local_capped
    markers: list[str] = []
    markers.append(
        "Search coverage note: does not scan assertions, history/saved-response bodies, "
        "globals/env values, or snippet bodies (use those dedicated scopes). "
        "Request params tables, bodies/descriptions, headers/auth, and scripts are "
        "matched (bodies/params after secret redaction)."
    )
    if within is not None:
        markers.append(
            f"[partial] Restricted to {len(within)} prior request ids (refine of a previous list)."
        )
    if any_deep_capped and within is None:
        markers.append(
            f"[partial] Name/URL/folder search was exhaustive; body/header/auth/script/"
            f"local-script scanning was capped — limited to the first {cap} "
            "requests/folders/local scripts per pass."
        )
    if saw_template_url:
        markers.append(
            "[partial] URLs matched in both raw and active-environment-resolved form; "
            "collection-variable overrides per request are not applied."
        )
    out: list[str] = [f'Search results for "{needle}":']
    if has_tree:
        out.extend(_cap_rows(lines, label="name/URL/folder matches"))
    if has_body:
        out.append("\nBody/description matches:")
        out.extend(_cap_rows(body_matches, label="body/description matches"))
    if has_params:
        out.append("\nParams matches:")
        out.extend(_cap_rows(param_matches, label="params matches"))
    if has_headers:
        out.append("\nHeader/auth matches:")
        out.extend(_cap_rows(header_matches, label="header/auth matches"))
    if has_scripts:
        out.append("\nScript-content matches:")
        out.extend(_cap_rows(script_matches, label="script matches"))
    if not has_tree and not has_scripts and not has_body and not has_headers and not has_params:
        if within is not None:
            markers.insert(
                0,
                "[partial] No matches within the prior request-id set for this needle. "
                "This is not a whole-workspace empty — only the refined subset was searched. "
                "Try a different criterion on the same within_ids, or re-run the original "
                "search if the prior list is stale.",
            )
            out.append("No matches in the prior request set (see partial marker above).")
        elif any_deep_capped:
            markers.insert(
                0,
                "[partial] No matching requests, folders, or scripts in the scanned subset. "
                "Name/method/URL/folder search covered the entire workspace, but "
                f"body/header/auth/script/local-script scanning was capped — a match may "
                f"exist beyond the first {cap} entities per pass; try a more specific "
                "name/URL filter or narrow scope before concluding nothing matched.",
            )
            out.append("No matches in the scanned subset (see partial marker above).")
        elif _needle_looks_secret_like(needle):
            markers.insert(
                0,
                "[partial] Search needle looks secret-like. Bodies/headers/auth/params are "
                "matched after secret redaction, so credential literals usually cannot match. "
                "Do not treat this empty result as proof the secret is absent — try a "
                "non-secret name/URL/path filter, or inspect via request/active_tab scopes "
                "(values remain redacted).",
            )
            out.append(
                "No matches (secret-like needle — redacted values cannot be searched; "
                "see partial marker above)."
            )
        else:
            markers.insert(
                0,
                "[authoritative] No matching requests, folders, or scripts in the "
                "scopes this search covers (names, methods, URLs, folders, "
                "bodies/descriptions, params tables, headers/auth, and script/"
                "local-script content). "
                "Do not retry query variations or fall back to the wiki for those "
                "fields. Other scopes may still match — try snippets, recent_history, "
                "globals, environments, saved_responses, or assertions if the user "
                "asked about those.",
            )
            out.append("No matches (see authoritative marker above).")
    return _with_leading_markers("\n".join(out), markers)
