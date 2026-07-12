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
    """Render the local-script tree with optional filter."""
    tree = LocalScriptService.fetch_all()
    lines = _walk_local_tree(tree, search=search.strip())
    if not lines:
        return (
            "No local scripts match." if search.strip() else "No local script folders or scripts."
        )
    title = "Local scripts"
    if search.strip():
        title += f' (filter: "{search.strip()}")'
    body = _cap_rows(lines, label="rows")
    return title + ":\n" + "\n".join(body)


def _render_script(script_id: int) -> str:
    """Return a local script's language and source."""
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
