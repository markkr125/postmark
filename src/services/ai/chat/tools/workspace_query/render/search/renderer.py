"""Main workspace search renderer with fielded query support."""

from __future__ import annotations

import json
from typing import Any

from services.ai.chat.workspace_snapshot import set_last_search_hits
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.local_script_service import LocalScriptService

from ...constants import _SEARCH_SCRIPT_SCAN_CAP
from ...helpers import (
    _cap_rows,
    _env_global_search_matches,
    _link,
    _mask_header_value,
    _mask_param_value,
    _redact_auth,
    _redact_request_body,
    _search_tokens,
    _walk_tree,
    _with_leading_markers,
)
from ...query_parse import FieldedQuery, parse_fielded_query
from .buckets import (
    _assertion_hay,
    _flags_ok,
    _method_ok,
    _path_ok,
    _related_findings_footer,
    _request_has_flags,
    _scripts_norm,
    _text_match,
    _want_bucket,
)
from .counts import (
    _count_local_scripts,
    _count_tree_folders,
    _count_tree_requests,
    _ordered_collection_ids_for_script_scan,
    _ordered_local_script_ids_for_scan,
    _ordered_request_ids_for_script_scan,
)
from .within import (
    _filter_lines_by_request_ids,
    _needle_looks_secret_like,
    _request_ids_from_tree_lines,
    _resolve_within_ids,
)


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


def _resolve_url_for_request(
    url: str,
    *,
    env_id: int | None,
    request_id: int | None,
    use_collection: bool,
) -> str:
    """Substitute variables into *url* (collection-aware when requested)."""
    rid = request_id if use_collection else None
    var_map = EnvironmentService.build_combined_variable_map(env_id, rid)
    resolved = url
    for key, value in var_map.items():
        resolved = resolved.replace(f"{{{{{key}}}}}", str(value))
    return resolved


def _legacy_tokens(query: FieldedQuery, needle: str) -> list[str]:
    """Tokens for backward-compatible AND matching on simple needles."""
    if query.text_tokens:
        return list(query.text_tokens)
    return _search_tokens(needle)


def _render_search(
    query: str,
    *,
    snap: dict[str, Any] | None = None,
    within_ids: list[int] | None = None,
    session_id: str = "",
) -> str:
    """Search requests, folders, and script content (supports fielded operators)."""
    needle = query.strip()
    if not needle:
        return "Provide non-empty ``search`` for scope=search."
    within, within_err = _resolve_within_ids(within_ids, session_id=session_id)
    if within_err:
        return within_err
    fq = parse_fielded_query(needle)
    if fq.error:
        return fq.error
    tokens = _legacy_tokens(fq, needle)
    tree = CollectionService.fetch_all()
    lines: list[str] = []
    tree_ok = _want_bucket(fq, "name") or _want_bucket(fq, "url")
    tree_needle = " ".join(fq.bare_tokens + fq.phrases) if fq.has_field_constraints else needle
    structural_only = (
        not tokens
        and not fq.phrases
        and not fq.or_groups
        and bool(fq.has or fq.missing or fq.method or fq.path_prefix)
    )
    if tree_ok and tree_needle.strip() and not structural_only:
        _walk_tree(tree, search=tree_needle.strip(), lines=lines)
    tree_matched_request_ids = _request_ids_from_tree_lines(lines)
    env_id_raw = (snap or {}).get("current_env_id")
    env_id = env_id_raw if isinstance(env_id_raw, int) else None
    resolved_url_hits: list[str] = []
    saw_template_url = False
    paths_by_id: dict[int, str] = {}

    def _scan_resolved_urls(nodes: dict[str, Any], prefix: str = "") -> None:
        nonlocal saw_template_url
        if not _want_bucket(fq, "url"):
            return
        for node in nodes.values():
            name = str(node.get("name", ""))
            path = f"{prefix}/{name}" if prefix else name
            if node.get("type") == "folder":
                _scan_resolved_urls(node.get("children") or {}, path)
            elif node.get("type") == "request" and isinstance(node.get("id"), int):
                rid = int(node["id"])
                paths_by_id[rid] = path
                if within is not None and rid not in within:
                    continue
                if not _path_ok(path, fq) or not _method_ok(str(node.get("method", "GET")), fq):
                    continue
                raw_url = str(node.get("url") or "")
                if "{{" in raw_url:
                    saw_template_url = True
                if rid in tree_matched_request_ids and not fq.resolved:
                    continue
                resolved = _resolve_url_for_request(
                    raw_url,
                    env_id=env_id,
                    request_id=rid,
                    use_collection=fq.resolved,
                )
                method = str(node.get("method", "GET"))
                hay = f"{name} {method} {resolved} {path}"
                raw_hay = f"{name} {method} {raw_url} {path}"
                if _text_match(hay, fq, tokens) and (
                    fq.resolved or not _text_match(raw_hay, fq, tokens)
                ):
                    resolved_url_hits.append(
                        f"- {_link('request', rid, name)} (resolved URL match) · in {path}"
                    )

    _scan_resolved_urls(tree)
    if resolved_url_hits:
        lines.extend(resolved_url_hits)
    # Apply method/path filters to tree lines.
    if fq.method or fq.path_prefix:
        lines = _filter_tree_lines_structural(lines, tree, fq, within)
    if within is not None:
        lines = _filter_lines_by_request_ids(lines, within)

    script_matches: list[str] = []
    body_matches: list[str] = []
    header_matches: list[str] = []
    auth_matches: list[str] = []
    param_matches: list[str] = []
    assert_matches: list[str] = []
    env_matches: list[str] = []
    scanned = 0
    ordered_ids = _ordered_request_ids_for_script_scan(tree)
    ordered_folder_ids = _ordered_collection_ids_for_script_scan(tree)
    local_tree = LocalScriptService.fetch_all()
    ordered_script_items = _ordered_local_script_ids_for_scan(local_tree)
    ordered_script_ids = [sid for sid, _path in ordered_script_items]
    local_script_path_by_id = dict(ordered_script_items)
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
        rid: (name, body, body_mode, body_options, description, headers, auth, params)
        for rid, name, body, body_mode, body_options, description, headers, auth, params in (
            CollectionService.fetch_request_fields_for_ids(ordered_ids)
        )
    }
    assertion_counts = {
        rid: (total, enabled)
        for rid, total, enabled in CollectionService.fetch_assertion_counts_for_ids(ordered_ids)
    }
    need_deep = (
        any(
            _want_bucket(fq, b)
            for b in ("script", "body", "header", "auth", "params", "assert", "local")
        )
        or bool(fq.has or fq.missing)
        or structural_only
    )

    def _scan_requests(nodes: dict[str, Any], prefix: str = "") -> None:
        nonlocal scanned
        if not need_deep and not fq.has and not fq.missing:
            return
        for node in nodes.values():
            name = str(node.get("name", ""))
            path = f"{prefix}/{name}" if prefix else name
            if node.get("type") == "folder":
                cid = node.get("id")
                if (
                    within is None
                    and isinstance(cid, int)
                    and _want_bucket(fq, "script")
                    and _path_ok(path, fq)
                ):
                    folder_row = folder_scripts_by_id.get(cid)
                    if folder_row is not None:
                        fname, events = folder_row
                        for kind, src in _scripts_norm(None, events).items():
                            if _text_match(src, fq, tokens):
                                script_matches.append(
                                    f"- {_link('collection', cid, fname, focus=kind)} "
                                    f"({kind} folder script match) · in {path}"
                                )
                _scan_requests(node.get("children") or {}, path)
            elif node.get("type") == "request" and isinstance(node.get("id"), int):
                rid = node["id"]
                paths_by_id.setdefault(rid, path)
                if within is not None and rid not in within:
                    continue
                if scanned >= _SEARCH_SCRIPT_SCAN_CAP:
                    return
                scanned += 1
                method = str(node.get("method", "GET"))
                if not _method_ok(method, fq) or not _path_ok(path, fq):
                    continue
                row_data = scripts_by_id.get(rid)
                field_row = fields_by_id.get(rid)
                norm_scripts = (
                    _scripts_norm(row_data[1], row_data[2]) if row_data is not None else {}
                )
                auth_val = field_row[6] if field_row is not None else None
                _total, enabled_n = assertion_counts.get(rid, (0, 0))
                # Unresolved count only when needed for has:/missing:
                unresolved_n = 0
                if "unresolved" in fq.has or "unresolved" in fq.missing:
                    url_raw = str(node.get("url") or "")
                    unresolved_n = url_raw.count("{{")  # cheap heuristic
                flags = _request_has_flags(
                    scripts=norm_scripts,
                    assertion_enabled=enabled_n,
                    auth=auth_val,
                    unresolved_count=unresolved_n,
                )
                if not _flags_ok(flags, fq):
                    continue
                if structural_only and not fq.in_buckets:
                    lines.append(f"- {_link('request', rid, name)} ({method}) · in {path}")
                    continue
                if row_data is not None and _want_bucket(fq, "script"):
                    rname = row_data[0]
                    for kind, src in norm_scripts.items():
                        if _text_match(src, fq, tokens):
                            script_matches.append(
                                f"- {_link('request', rid, rname, focus=kind)} "
                                f"({kind} script match) · in {path}"
                            )
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
                    if _want_bucket(fq, "body"):
                        body_ctx = {
                            "body_mode": body_mode,
                            "body_options": body_options,
                            "headers": headers,
                            "auth": auth,
                        }
                        full_body = _redact_request_body(str(body or ""), body_ctx) if body else ""
                        body_hay = f"{full_body} {description or ''}".strip()
                        if body_hay and _text_match(body_hay, fq, tokens):
                            body_matches.append(
                                f"- {_link('request', rid, fname)} "
                                f"(body/description match) · in {path}"
                            )
                    if _want_bucket(fq, "params"):
                        params_hay = _params_haystack(params)
                        if params_hay and _text_match(params_hay, fq, tokens):
                            param_matches.append(
                                f"- {_link('request', rid, fname)} (params match) · in {path}"
                            )
                    if _want_bucket(fq, "header") and isinstance(headers, list):
                        for h in headers:
                            if not isinstance(h, dict):
                                continue
                            hkey = str(h.get("key", ""))
                            hval = str(h.get("value", ""))
                            hay = f"{hkey} {_mask_header_value(hkey, hval)}"
                            if _text_match(hay, fq, tokens):
                                header_matches.append(
                                    f"- {_link('request', rid, fname)} (header match) · in {path}"
                                )
                                break
                    if _want_bucket(fq, "auth") and isinstance(auth, dict):
                        redacted_auth = _redact_auth(auth) or {}
                        auth_blob = json.dumps(redacted_auth, ensure_ascii=False)
                        if _text_match(auth_blob, fq, tokens):
                            auth_matches.append(
                                f"- {_link('request', rid, fname)} (auth match) · in {path}"
                            )
                if _want_bucket(fq, "assert"):
                    ahay = _assertion_hay(rid)
                    if ahay and _text_match(ahay, fq, tokens):
                        assert_matches.append(
                            f"- {_link('request', rid, name, focus='assertions')} "
                            f"(assertion match) · in {path}"
                        )

    _scan_requests(tree)
    if within is None and _want_bucket(fq, "local"):
        local_scanned = 0
        for sid, _spath in ordered_script_items:
            if local_scanned >= _SEARCH_SCRIPT_SCAN_CAP:
                break
            local_scanned += 1
            row = local_scripts_by_id.get(sid)
            if row is None:
                continue
            name, content = row
            path = local_script_path_by_id.get(sid, name)
            loaded = LocalScriptService.get_script_load_dict(sid)
            lang = str(loaded.get("language", "")) if loaded else ""
            mod = str(loaded.get("module_format", "")) if loaded else ""
            if fq.lang and fq.lang not in lang.casefold():
                continue
            if fq.module_format and fq.module_format not in mod.casefold():
                continue
            badge = f"{lang}/{mod}".strip("/")
            hay = f"{name} {content} {badge}"
            if _text_match(hay, fq, tokens) or (
                not tokens and not fq.phrases and (fq.lang or fq.module_format)
            ):
                script_matches.append(
                    f"- {_link('script', sid, name)} (local script match · {badge}) · in {path}"
                )
    if within is None and _want_bucket(fq, "env") and (tokens or fq.phrases):
        env_matches.extend(_env_global_search_matches(tokens))

    has_tree = bool(lines)
    has_scripts = bool(script_matches)
    has_body = bool(body_matches)
    has_headers = bool(header_matches) or bool(auth_matches)
    has_params = bool(param_matches)
    has_assert = bool(assert_matches)
    has_env = bool(env_matches)
    all_hit_ids = sorted(
        _request_ids_from_tree_lines(lines)
        | _request_ids_from_tree_lines(body_matches)
        | _request_ids_from_tree_lines(header_matches)
        | _request_ids_from_tree_lines(auth_matches)
        | _request_ids_from_tree_lines(param_matches)
        | _request_ids_from_tree_lines(script_matches)
        | _request_ids_from_tree_lines(assert_matches)
    )
    if session_id and all_hit_ids:
        set_last_search_hits(session_id, all_hit_ids)
    cap = _SEARCH_SCRIPT_SCAN_CAP
    total_requests = _count_tree_requests(tree)
    total_folders = _count_tree_folders(tree)
    total_local_scripts = _count_local_scripts(local_tree)
    any_deep_capped = (
        total_requests > cap or total_folders > cap or total_local_scripts > cap
    ) and within is None
    markers: list[str] = []
    coverage = (
        "Search coverage note: does not scan history/saved-response bodies or snippet "
        "bodies (use those dedicated scopes). Request params tables, bodies/descriptions, "
        "headers/auth, scripts, assertions (when in:assert or unrestricted), and enabled "
        "environment/global variable keys (non-secret values) are matched "
        "(bodies/params after secret redaction). Fielded operators: "
        "in:/method:/path:/lang:/format:/has:/missing:/resolved:, OR, -exclude, "
        '"phrases".'
    )
    if within is not None:
        coverage = (
            "Search coverage note: does not scan history/saved-response bodies or snippet "
            "bodies (use those dedicated scopes). Request params tables, bodies/"
            "descriptions, headers/auth, scripts, and assertions are matched within the "
            "prior request set. Environment/global variable keys are not scanned under "
            "within_ids (bodies/params after secret redaction). Fielded operators: "
            "in:/method:/path:/lang:/format:/has:/missing:/resolved:, OR, -exclude, "
            '"phrases".'
        )
    markers.append(coverage)
    if within is not None:
        markers.append(
            f"[partial] Restricted to {len(within)} prior request ids (refine of a previous list)."
        )
    if any_deep_capped:
        markers.append(
            f"[partial] Name/URL/folder search was exhaustive; body/header/auth/script/"
            f"local-script scanning was capped — limited to the first {cap} "
            "requests/folders/local scripts per pass."
        )
    if saw_template_url and fq.resolved:
        markers.append("[partial] URLs matched with collection-aware active-env resolution.")
    elif saw_template_url:
        markers.append(
            "[partial] URLs matched in raw and active-environment-resolved form; "
            "collection-variable overrides per request need a resolved-URL search "
            "(assistant: add resolved:1 — do not quote that operator to the user)."
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
    if header_matches or auth_matches:
        out.append("\nHeader/auth matches:")
        out.extend(_cap_rows([*header_matches, *auth_matches], label="header/auth matches"))
    if has_assert:
        out.append("\nAssertion matches:")
        out.extend(_cap_rows(assert_matches, label="assertion matches"))
    if has_scripts:
        out.append("\nScript-content matches:")
        out.extend(_cap_rows(script_matches, label="script matches"))
    if has_env:
        out.append("\nEnvironment/global matches:")
        out.extend(_cap_rows(env_matches, label="environment/global matches"))
    empty = not any((has_tree, has_scripts, has_body, has_headers, has_params, has_assert, has_env))
    if empty:
        out.extend(_empty_markers(markers, within, any_deep_capped, needle, tokens, cap))
    else:
        out.extend(
            _related_findings_footer(
                hit_ids=all_hit_ids,
                paths_by_id=paths_by_id,
                unresolved_hint="unresolved" in fq.has,
            )
        )
    return _with_leading_markers("\n".join(out), markers)


def _filter_tree_lines_structural(
    lines: list[str],
    tree: dict[str, Any],
    fq: FieldedQuery,
    within: set[int] | None,
) -> list[str]:
    """Drop tree lines that fail method/path filters (re-scan ids from tree)."""
    kept: list[str] = []
    id_meta: dict[int, tuple[str, str]] = {}

    def walk(ns: dict[str, Any], prefix: str = "") -> None:
        for node in ns.values():
            name = str(node.get("name", ""))
            path = f"{prefix}/{name}" if prefix else name
            if node.get("type") == "folder":
                walk(node.get("children") or {}, path)
            elif node.get("type") == "request" and isinstance(node.get("id"), int):
                id_meta[int(node["id"])] = (str(node.get("method", "GET")), path)

    walk(tree)
    from .within import REQUEST_LINK_RE

    for line in lines:
        match = REQUEST_LINK_RE.search(line)
        if not match:
            kept.append(line)
            continue
        rid = int(match.group(1))
        if within is not None and rid not in within:
            continue
        meta = id_meta.get(rid)
        if meta is None:
            kept.append(line)
            continue
        method, path = meta
        if _method_ok(method, fq) and _path_ok(path, fq):
            kept.append(line)
    return kept


def _empty_markers(
    markers: list[str],
    within: set[int] | None,
    any_deep_capped: bool,
    needle: str,
    tokens: list[str],
    cap: int,
) -> list[str]:
    """Append empty-result body lines and insert leading epistemic markers."""
    out: list[str] = []
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
            f"body/header/auth/script/local-script scanning was capped — limited to the "
            f"first {cap} entities per pass; a match may exist beyond that — try a more "
            "specific name/URL filter or narrow scope before concluding nothing matched.",
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
    elif len(tokens) > 1:
        safe_tokens = [t for t in tokens if not _needle_looks_secret_like(t)]
        hint_token = max(safe_tokens, key=len) if safe_tokens else None
        if hint_token is not None:
            retry_hint = (
                "retry once with the most distinctive single word "
                f'(e.g. search="{hint_token}") or a shorter phrase before concluding '
                "nothing matches."
            )
        else:
            retry_hint = (
                "retry once with a shorter non-secret name/URL/path phrase before "
                "concluding nothing matches."
            )
        markers.insert(
            0,
            f"[partial] No single item matched ALL {len(tokens)} words of this search "
            "(words AND-match within one item, in any order). Absence is not confirmed — "
            f"{retry_hint}",
        )
        out.append("No matches (multi-word AND — see partial marker above).")
    else:
        markers.insert(
            0,
            "[authoritative] No matching requests, folders, or scripts in the "
            "scopes this search covers (names, methods, URLs, folders, "
            "bodies/descriptions, params tables, headers/auth, script/"
            "local-script content, assertions, and enabled environment/global "
            "variable keys). Do not retry query variations or fall back to the wiki "
            "for those fields. Other scopes may still match — try globals, environments, "
            "snippets, recent_history, saved_responses, or assertions if the user "
            "asked about those.",
        )
        out.append("No matches (see authoritative marker above).")
    return out
