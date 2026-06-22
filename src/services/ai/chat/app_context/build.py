"""Format app context snapshots and DB entities for the AI tool."""

from __future__ import annotations

import json
from typing import Any, Literal

from database.models.collections import collection_query_repository
from database.models.local_scripts import local_script_query_repository
from database.models.request_history import request_history_repository
from services.ai.chat.app_context.search import format_environment_detail, search_app_context
from services.ai.chat.app_context.snapshot import AppContextSnapshot
from services.ai.chat.context_redaction import redact_headers, redact_text
from services.collection_service import CollectionService
from services.local_script_service import LocalScriptService

AppContextFocus = Literal[
    "current",
    "collection",
    "request",
    "local_script",
    "local_scripts_tree",
    "search",
    "send_history",
    "saved_response",
    "environment",
    "workspace",
]

_SEARCH_MAX = 4000
_DETAIL_MAX = 12000


def _cap(text: str, limit: int) -> str:
    """Truncate *text* with a footer when over *limit*."""
    if len(text) <= limit:
        return text
    return text[: limit - len("\n…[truncated]")] + "\n…[truncated]"


def _format_current(snapshot: AppContextSnapshot) -> str:
    """Format active tab + environment + tree selection."""
    tab = snapshot["active_tab"]
    lines = [
        "# Current context",
        f"tab_type={tab['tab_type']}",
        f"title={tab['title']}",
        f"method={tab.get('method')}",
        f"request_id={tab.get('request_id')}",
        f"collection_id={tab.get('collection_id')}",
        f"local_script_id={tab.get('local_script_id')}",
        f"dirty={tab.get('is_dirty')}",
        f"preview={tab.get('active_sub_tab')}",
    ]
    if tab.get("editor_preview"):
        lines.append(f"\nEditor preview:\n{tab['editor_preview']}")
    env = snapshot["environment"]
    if env.get("name"):
        lines.append(f"\nEnvironment: {env['name']} (id={env.get('id')})")
    tree = snapshot["tree_selection"]
    if tree.get("kind") != "none" and tree.get("label"):
        lines.append(f"\nTree selection: {tree['kind']} — {tree['label']}")
    return "\n".join(lines)


def _format_request(request_id: int) -> str:
    """Format one HTTP request with pre/post scripts (not local scripts)."""
    req = CollectionService.get_request(request_id)
    if req is None:
        return f"Request id={request_id} not found."
    lines = [
        f"# Request: {req.name}",
        f"id={request_id}",
        f"method={req.method}",
        f"url={redact_text(str(req.url or ''))}",
        f"description={req.description or ''}",
    ]
    if req.headers:
        headers = req.headers if isinstance(req.headers, list) else []
        lines.append(f"\nHeaders:\n{json.dumps(redact_headers(headers), indent=2)}")
    if req.body:
        lines.append(f"\nBody:\n{redact_text(str(req.body))}")
    scripts = req.scripts or req.events or {}
    if isinstance(scripts, dict):
        pre = scripts.get("pre_request") or scripts.get("prerequest")
        test = scripts.get("test") or scripts.get("post_response")
        if pre:
            lines.append(f"\nPre-request script:\n{redact_text(str(pre))}")
        if test:
            lines.append(f"\nTest script:\n{redact_text(str(test))}")
    return "\n".join(lines)


def _format_collection(collection_id: int) -> str:
    """Format collection tree summary."""
    summary = collection_query_repository.collection_tree_summary(collection_id)
    breadcrumb = CollectionService.get_collection_breadcrumb(collection_id)
    path = " / ".join(seg.get("name", "") for seg in breadcrumb)
    return (
        f"# Collection: {summary.get('name')}\n"
        f"id={collection_id}\n"
        f"path={path}\n"
        f"requests={summary.get('request_count')}\n"
        f"subfolders={summary.get('folder_count')}"
    )


def _format_local_script(script_id: int) -> str:
    """Format one local script (distinct from request scripts)."""
    data = LocalScriptService.get_script_load_dict(script_id)
    if data is None:
        return f"Local script id={script_id} not found."
    content = redact_text(str(data.get("content") or ""))
    return (
        f"# Local script: {data.get('name')}\n"
        f"id={script_id}\n"
        f"language={data.get('language')}\n"
        f"module_format={data.get('module_format')}\n"
        f"\n{content}"
    )


def _format_local_scripts_tree() -> str:
    """Return local scripts tree names only (no bodies)."""
    tree = local_script_query_repository.fetch_all_local_scripts_tree()

    def walk(node: dict[str, Any], depth: int = 0) -> list[str]:
        lines: list[str] = []
        indent = "  " * depth
        for child in node.get("children", {}).values():
            if child.get("type") == "folder":
                lines.append(f"{indent}[folder] {child.get('name')} (id={child.get('id')})")
                lines.extend(walk(child, depth + 1))
            elif child.get("type") == "script":
                lines.append(
                    f"{indent}[script] {child.get('name')} "
                    f"(id={child.get('id')}, lang={child.get('language')})"
                )
        return lines

    body = walk(tree)
    return "# Local scripts tree\n" + ("\n".join(body) if body else "_Empty._")


def _format_send_history(entity_id: int | None, request_id: int | None) -> str:
    """Format one send-history entry."""
    row: dict[str, Any] | None = None
    if entity_id is not None:
        row = request_history_repository.get_entry_metadata(entity_id)
    elif request_id is not None:
        rows = request_history_repository.list_for_request(request_id, limit=1)
        row = rows[0] if rows else None
    if row is None:
        return "Send history entry not found."
    deleted = row.get("request_id") is None and row.get("was_persisted_request")
    suffix = " (deleted)" if deleted else ""
    draft = (
        " (draft)" if row.get("request_id") is None and not row.get("was_persisted_request") else ""
    )
    return (
        f"# Send history{suffix}{draft}\n"
        f"entry_id={row.get('id')}\n"
        f"method={row.get('method')}\n"
        f"url={redact_text(str(row.get('url') or ''))}\n"
        f"status={row.get('status_code')}\n"
        f"executed_at={row.get('executed_at')}"
    )


def _format_saved_response(response_id: int) -> str:
    """Format one saved response example."""
    row = collection_query_repository.get_saved_response(response_id)
    if row is None:
        return f"Saved response id={response_id} not found."
    body = redact_text(str(row.get("body") or ""))
    return (
        f"# Saved response: {row.get('name')}\n"
        f"id={response_id}\n"
        f"request_id={row.get('request_id')}\n"
        f"code={row.get('code')}\n"
        f"\nBody:\n{body}"
    )


def _format_workspace(snapshot: AppContextSnapshot) -> str:
    """Compact workspace rollup without full DB scan."""
    lines = ["# Workspace summary"]
    env = snapshot["environment"]
    if env.get("name"):
        lines.append(f"Environment: {env['name']}")
    tab = snapshot["active_tab"]
    lines.append(f"Active: {tab['title']} ({tab['tab_type']})")
    for entry in snapshot.get("open_tabs") or []:
        lines.append(f"- {entry['label']} [{entry['tab_type']}]")
    return "\n".join(lines)


def format_app_context(
    focus: AppContextFocus,
    snapshot: AppContextSnapshot,
    *,
    query: str | None = None,
    scope: str = "all",
    entity_id: int | None = None,
) -> str:
    """Resolve *focus* to markdown text for the AI tool."""
    tab = snapshot["active_tab"]
    if focus == "current":
        text = _format_current(snapshot)
    elif focus == "request":
        rid = entity_id or tab.get("request_id")
        text = _format_request(int(rid)) if rid is not None else "No request in context."
    elif focus == "collection":
        cid = entity_id or tab.get("collection_id")
        if cid is None and tab.get("request_id"):
            req_id = tab["request_id"]
            if req_id is not None:
                req = CollectionService.get_request(int(req_id))
                if req is not None:
                    cid = req.collection_id
        text = _format_collection(int(cid)) if cid is not None else "No collection in context."
    elif focus == "local_script":
        sid = entity_id or tab.get("local_script_id")
        text = _format_local_script(int(sid)) if sid is not None else "No local script in context."
    elif focus == "local_scripts_tree":
        text = _format_local_scripts_tree()
    elif focus == "search":
        text = search_app_context(query or "", scope)  # type: ignore[arg-type]
    elif focus == "send_history":
        text = _format_send_history(entity_id, tab.get("request_id"))
    elif focus == "saved_response":
        text = (
            _format_saved_response(int(entity_id))
            if entity_id is not None
            else "entity_id required."
        )
    elif focus == "environment":
        eid = entity_id or snapshot["environment"].get("id")
        text = (
            format_environment_detail(int(eid)) if eid is not None else "No environment selected."
        )
    elif focus == "workspace":
        text = _format_workspace(snapshot)
    else:
        text = f"Unknown focus: {focus}"

    limit = _SEARCH_MAX if focus == "search" else _DETAIL_MAX
    return _cap(text, limit)
