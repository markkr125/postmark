"""Reload open tabs from the database after Agent mutations."""

from __future__ import annotations

from typing import Any

from services.collection_service import CollectionService, RequestLoadDict


def reload_open_request_from_db(host: Any, request_id: int) -> None:
    """Reload a materialised request tab from the database (Agent wins)."""
    request = CollectionService.get_request(request_id)
    if request is None:
        return
    data: RequestLoadDict = {
        "name": request.name,
        "method": request.method,
        "url": request.url,
        "body": request.body,
        "request_parameters": request.request_parameters,
        "headers": request.headers,
        "description": request.description,
        "scripts": request.scripts or request.events,
        "body_mode": request.body_mode,
        "body_options": request.body_options,
        "auth": request.auth,
    }
    for idx, ctx in list(getattr(host, "_tabs", {}).items()):
        if getattr(ctx, "request_id", None) != request_id:
            continue
        editor = getattr(ctx, "editor", None)
        if editor is None:
            continue
        editor.load_request(data, request_id=request_id)
        ctx.is_dirty = False
        update_tab = getattr(host._tab_bar, "update_tab", None)
        if callable(update_tab):
            path = ""
            path_fn = getattr(host, "_request_full_path", None)
            if callable(path_fn):
                path = path_fn(request_id)
            update_tab(
                idx,
                name=request.name,
                method=request.method,
                path=path,
                is_dirty=False,
            )
        if idx == host._tab_bar.currentIndex():
            crumb = getattr(host._breadcrumb_bar, "update_last_segment_text", None)
            if callable(crumb):
                crumb(request.name)
        sync_name = getattr(host, "_sync_name_across_tabs", None)
        if callable(sync_name):
            sync_name("request", request_id, request.name)
        return


def reload_open_folder_from_db(host: Any, collection_id: int) -> None:
    """Reload an open folder tab from the database (Agent wins)."""
    collection = CollectionService.get_collection(collection_id)
    if collection is None:
        return
    data: dict[str, Any] = {
        "name": collection.name,
        "description": collection.description,
        "auth": collection.auth,
        "events": collection.events,
        "variables": collection.variables,
    }
    request_count = CollectionService.get_folder_request_count(collection_id)
    recent_requests = CollectionService.get_recent_requests(collection_id)
    created_at = collection.created_at.strftime("%Y-%m-%d %H:%M") if collection.created_at else None
    updated_at = collection.updated_at.strftime("%Y-%m-%d %H:%M") if collection.updated_at else None
    for idx, ctx in list(getattr(host, "_tabs", {}).items()):
        if getattr(ctx, "tab_type", None) != "folder":
            continue
        if getattr(ctx, "collection_id", None) != collection_id:
            continue
        folder_editor = getattr(ctx, "folder_editor", None)
        if folder_editor is None:
            continue
        folder_editor.load_collection(
            data,
            collection_id=collection_id,
            request_count=request_count,
            created_at=created_at,
            updated_at=updated_at,
            recent_requests=recent_requests,
        )
        ctx.is_dirty = False
        crumbs = CollectionService.get_collection_breadcrumb(collection_id)
        folder_path = " / ".join(
            str(crumb.get("name", "")) for crumb in crumbs if crumb.get("name")
        )
        update_tab = getattr(host._tab_bar, "update_tab", None)
        if callable(update_tab):
            update_tab(idx, name=collection.name, path=folder_path, is_dirty=False)
        if idx == host._tab_bar.currentIndex():
            crumb = getattr(host._breadcrumb_bar, "update_last_segment_text", None)
            if callable(crumb):
                crumb(collection.name)
        sync_name = getattr(host, "_sync_name_across_tabs", None)
        if callable(sync_name):
            sync_name("folder", collection_id, collection.name)
        return


def close_tabs_for_mutation_ids(host: Any, ids: dict[str, int]) -> None:
    """Close open tabs matching deleted request/collection/local-script ids."""
    request_id = ids.get("request_id")
    collection_id = ids.get("collection_id")
    local_script_id = ids.get("local_script_id")
    to_close: list[int] = []
    tabs = getattr(host, "_tabs", {})
    deferred = getattr(host, "_deferred_tabs", {})
    for idx, ctx in list(tabs.items()):
        if isinstance(request_id, int) and getattr(ctx, "request_id", None) == request_id:
            to_close.append(idx)
            continue
        if (
            isinstance(collection_id, int)
            and getattr(ctx, "tab_type", None) == "folder"
            and getattr(ctx, "collection_id", None) == collection_id
        ):
            to_close.append(idx)
            continue
        if (
            isinstance(local_script_id, int)
            and getattr(ctx, "tab_type", None) == "local_script"
            and getattr(ctx, "local_script_id", None) == local_script_id
        ):
            to_close.append(idx)
    for idx, info in list(deferred.items()):
        if isinstance(request_id, int) and info.get("request_id") == request_id:
            to_close.append(idx)
    close = getattr(host, "_on_tab_close", None)
    if not callable(close):
        return
    for idx in sorted(set(to_close), reverse=True):
        close(idx)


def close_stale_workspace_tabs(host: Any) -> None:
    """Close request/folder/local-script tabs whose DB rows no longer exist."""
    from services.local_script_service import LocalScriptService

    to_close: list[int] = []
    tabs = getattr(host, "_tabs", {})
    deferred = getattr(host, "_deferred_tabs", {})
    for idx, ctx in list(tabs.items()):
        request_id = getattr(ctx, "request_id", None)
        if isinstance(request_id, int) and CollectionService.get_request(request_id) is None:
            to_close.append(idx)
            continue
        if (
            getattr(ctx, "tab_type", None) == "folder"
            and isinstance(getattr(ctx, "collection_id", None), int)
            and CollectionService.get_collection(ctx.collection_id) is None
        ):
            to_close.append(idx)
            continue
        if (
            getattr(ctx, "tab_type", None) == "local_script"
            and isinstance(getattr(ctx, "local_script_id", None), int)
            and LocalScriptService.get_script_load_dict(ctx.local_script_id) is None
        ):
            to_close.append(idx)
    for idx, info in list(deferred.items()):
        rid = info.get("request_id")
        if isinstance(rid, int) and CollectionService.get_request(rid) is None:
            to_close.append(idx)
    close = getattr(host, "_on_tab_close", None)
    if not callable(close):
        return
    for idx in sorted(set(to_close), reverse=True):
        close(idx)
