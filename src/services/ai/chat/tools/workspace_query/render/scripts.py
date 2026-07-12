"""Local script scope renderers for the workspace query tool."""

from __future__ import annotations

from services.collection_service import CollectionService
from services.local_script_service import LocalScriptService
from services.script_version_service import ScriptVersionService
from services.scripting.context import load_globals, mask_sensitive_value
from services.snippet_service import SnippetService

from ..constants import _MAX_RESULT_ROWS
from ..helpers import (
    _cap_rows,
    _follow_up_ids_block,
    _format_ts,
    _link,
    _matches_tokens,
    _search_tokens,
    _truncate_text,
    _walk_local_tree,
)

_SNIPPET_LANGUAGES = ("javascript", "typescript", "python")


def _render_local_scripts(search: str = "") -> str:
    """Render the local-script tree with optional filter and polyglot inventory."""
    tree = LocalScriptService.fetch_all()
    lines = _walk_local_tree(tree, search=search.strip())
    # Polyglot inventory (language / module_format counts).
    from .search.counts import _ordered_local_script_ids_for_scan

    items = _ordered_local_script_ids_for_scan(tree, limit=200)
    lang_counts: dict[str, int] = {}
    for sid, _path in items:
        loaded = LocalScriptService.get_script_load_dict(sid)
        if loaded is None:
            continue
        key = f"{loaded.get('language', '?')}/{loaded.get('module_format', '?')}"
        lang_counts[key] = lang_counts.get(key, 0) + 1
    inventory = ""
    if lang_counts:
        bits = ", ".join(f"{k}={v}" for k, v in sorted(lang_counts.items()))
        inventory = f"\n  Polyglot inventory (scanned): {bits}"
    if not lines:
        empty = (
            "No local scripts match." if search.strip() else "No local script folders or scripts."
        )
        return empty + inventory
    title = "Local scripts"
    if search.strip():
        title += f' (filter: "{search.strip()}")'
    body = _cap_rows(lines, label="rows")
    return title + ":" + inventory + "\n" + "\n".join(body)


def _render_script(script_id: int) -> str:
    """Return a local script's language, source, and local dependency graph."""
    loaded = LocalScriptService.get_script_load_dict(script_id)
    if loaded is None:
        return "Local script not found."
    name = loaded.get("name", f"script {script_id}")
    lang = loaded.get("language", "javascript")
    mod = loaded.get("module_format", "esm")
    breadcrumb = LocalScriptService.get_script_breadcrumb(script_id)
    path = " / ".join(str(seg.get("name", "")) for seg in breadcrumb)
    content = loaded.get("content") or ""
    lines = [
        f"{_link('script', script_id, name)}:",
        f"  Path: {path}",
        f"  Language: {lang}/{mod}",
        _truncate_text(content, max_len=2000),
    ]
    # Dependency graph (requires / dependents) — Postmark-only local-script moat.
    try:
        from services.scripting.local_script_modules import (
            lookup_rel_path_by_script_id,
            resolve_required,
        )

        rel = lookup_rel_path_by_script_id(script_id)
        requires: list[str] = []
        if content.strip():
            try:
                mods = resolve_required(str(content), str(lang))
                for rpath, mod_obj in mods.items():
                    sid = getattr(mod_obj, "script_id", None)
                    if isinstance(sid, int):
                        requires.append(f"    - {_link('script', sid, rpath)}")
                    else:
                        requires.append(f"    - {rpath}")
            except Exception as exc:
                requires.append(f"    - (resolve error: {exc})")
        if requires:
            lines.append("\n  Requires (local):")
            lines.extend(requires[:30])
        dependents: list[str] = []
        if rel:
            tree = LocalScriptService.fetch_all()
            from .search.counts import _ordered_local_script_ids_for_scan

            items = _ordered_local_script_ids_for_scan(tree, limit=100)
            contents = {
                sid: (n, c)
                for sid, n, c in LocalScriptService.fetch_local_script_contents_for_ids(
                    [sid for sid, _p in items]
                )
            }
            for sid, spath in items:
                if sid == script_id:
                    continue
                row = contents.get(sid)
                if row is None:
                    continue
                _n, src = row
                if f"local:{rel}" not in str(src):
                    continue
                loaded_other = LocalScriptService.get_script_load_dict(sid)
                other_lang = (
                    str(loaded_other.get("language", "javascript"))
                    if loaded_other
                    else "javascript"
                )
                try:
                    mods = resolve_required(str(src or ""), other_lang)
                except Exception:
                    dependents.append(f"    - {_link('script', sid, spath)}")
                    continue
                if any(getattr(m, "script_id", None) == script_id for m in mods.values()):
                    dependents.append(f"    - {_link('script', sid, spath)}")
        if dependents:
            lines.append("\n  Required by:")
            lines.extend(dependents[:30])
    except Exception:
        pass
    debug_meta = loaded.get("debug_metadata")
    if isinstance(debug_meta, dict) and debug_meta:
        bps = debug_meta.get("breakpoints")
        watches = debug_meta.get("watches")
        if bps or watches:
            lines.append("\n  Debug metadata:")
            if isinstance(bps, list) and bps:
                lines.append(f"    Breakpoints: {len(bps)} stored")
            if isinstance(watches, list) and watches:
                lines.append(f"    Watches: {len(watches)} stored")
    return "\n".join(lines)


def _render_globals() -> str:
    """List persisted pm.globals with sensitive values masked."""
    globals_map = load_globals()
    if not globals_map:
        return "No global variables."
    lines = ["Global variables:"]
    row_lines: list[str] = []
    for key in sorted(globals_map):
        value = mask_sensitive_value(key, globals_map[key])
        row_lines.append(f"- {key} = {_truncate_text(value, max_len=200)}")
    lines.extend(_cap_rows(row_lines, label="globals"))
    return "\n".join(lines)


def _render_snippets(search: str = "") -> str:
    """List user snippets grouped by language and category."""
    needle = search.strip()
    tokens = _search_tokens(needle) if needle else []
    grouped: dict[tuple[str, str], list[tuple[int, str, str, str]]] = {}
    for language in _SNIPPET_LANGUAGES:
        for row in SnippetService.list_all(language):
            name = str(row.get("name", ""))
            category = str(row.get("category", ""))
            sid = int(row["id"])
            ctx = str(row.get("context", "both"))
            hay = f"{name} {category} {language} {ctx} {row.get('body', '')}"
            if tokens and not _matches_tokens(hay, tokens):
                continue
            preview = _truncate_text(str(row.get("body", "")), max_len=80)
            grouped.setdefault((language, category), []).append((sid, name, ctx, preview))
    if not grouped:
        return "No user snippets match." if needle else "No user snippets."
    row_lines: list[str] = []
    follow_ups: list[tuple[str, int]] = []
    snippet_count = 0
    hidden_snippets = 0
    for language, category in sorted(grouped):
        group_lines: list[str] = []
        for sid, name, ctx, preview in sorted(
            grouped[(language, category)], key=lambda r: r[1].casefold()
        ):
            if snippet_count >= _MAX_RESULT_ROWS:
                hidden_snippets += 1
                continue
            snippet_count += 1
            block = f"  - {name} · context={ctx}"
            if preview:
                block += f"\n      {preview}"
            group_lines.append(block)
            follow_ups.append((f"snippet · {language}/{category}/{name}", sid))
        if group_lines:
            row_lines.append(f"\n  {language} / {category}:")
            row_lines.extend(group_lines)
    header = "User snippets:"
    parts = [header, *row_lines]
    if hidden_snippets:
        parts.insert(
            1,
            f"[partial] Showing first {_MAX_RESULT_ROWS} of "
            f"{_MAX_RESULT_ROWS + hidden_snippets} snippets.",
        )
    parts.extend(_follow_up_ids_block(follow_ups))
    return "\n".join(parts)


def _render_request_script_versions(request_id: int) -> str:
    """List pre-request and test script versions for a saved request."""
    row = CollectionService.get_request(request_id)
    label = row.name if row else f"request {request_id}"
    merged: list[dict[str, object]] = []
    for script_type in ("pre_request", "test"):
        versions = ScriptVersionService.list_versions(
            request_id=request_id,
            script_type=script_type,
            limit=25,
        )
        for version in versions:
            item = dict(version)
            item["_script_type"] = script_type
            merged.append(item)
    if not merged:
        return f"No script versions for {_link('request', request_id, label)}."
    merged.sort(key=lambda v: str(v.get("created_at") or ""), reverse=True)
    lines = [f"Request script versions for {_link('request', request_id, label)} (newest first):"]
    version_lines: list[str] = []
    follow_ups: list[tuple[str, int]] = []
    for version in merged:
        vid = version.get("id")
        when = _format_ts(version.get("created_at") or "")
        lang = version.get("language") or ""
        stype = version.get("_script_type") or version.get("script_type") or ""
        version_lines.append(f"- {when} · {stype} · {lang}")
        if isinstance(vid, int):
            follow_ups.append((f"script_version · {stype} · {when}", vid))
    lines.extend(_cap_rows(version_lines, label="versions"))
    lines.extend(_follow_up_ids_block(follow_ups))
    return "\n".join(lines)


def _render_snippet(snippet_id: int) -> str:
    """Render one user snippet body."""
    row = SnippetService.get(snippet_id)
    if row is None:
        return "Snippet not found."
    language = SnippetService.to_editor_language(row["language"])
    lines = [
        f"Snippet · {row['name']}:",
        f"  Language: {language}",
        f"  Category: {row['category']}",
        f"  Context: {row['context']}",
        _truncate_text(str(row["body"]), max_len=2000),
    ]
    lines.extend(_follow_up_ids_block([(f"snippet · {row['name']}", snippet_id)]))
    return "\n".join(lines)


def _render_script_versions(script_id: int) -> str:
    """List version snapshots for a local script."""
    loaded = LocalScriptService.get_script_load_dict(script_id)
    label = loaded.get("name", f"script {script_id}") if loaded else f"script {script_id}"
    versions = ScriptVersionService.list_versions(
        local_script_id=script_id,
        script_type="local_script",
        limit=25,
    )
    if not versions:
        return f"No versions for {_link('script', script_id, label)}."
    lines = [f"Script versions for {_link('script', script_id, label)} (newest first):"]
    version_lines: list[str] = []
    follow_ups: list[tuple[str, int]] = []
    for version in versions:
        vid = version.get("id")
        when = version.get("created_at") or ""
        lang = version.get("language") or ""
        when_s = _format_ts(when)
        version_lines.append(f"- {when_s} · {lang}")
        if isinstance(vid, int):
            follow_ups.append((f"script_version · {when_s}", vid))
    lines.extend(_cap_rows(version_lines, label="versions"))
    lines.extend(_follow_up_ids_block(follow_ups))
    return "\n".join(lines)


def _render_script_version(version_id: int) -> str:
    """Render one script version snapshot."""
    version = ScriptVersionService.get_version(version_id)
    if version is None:
        return "Script version not found."
    content = str(version.get("content") or "")
    lines = [
        "Script version:",
        f"  Type: {version.get('script_type', '')}",
        f"  Language: {version.get('language', '')}",
        _truncate_text(content, max_len=2000),
    ]
    lines.extend(_follow_up_ids_block([("script_version", version_id)]))
    return "\n".join(lines)
