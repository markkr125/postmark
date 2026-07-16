"""Drain mutation/execute bridge events on the GUI thread."""

from __future__ import annotations

from typing import Any

from services.ai.chat.mutation.bridge import drain_mutation_events
from ui.main_window.mutation_drain.execute_ui import apply_executed_event
from ui.main_window.mutation_drain.reload import (
    close_stale_workspace_tabs,
    close_tabs_for_mutation_ids,
    reload_open_folder_from_db,
    reload_open_request_from_db,
)

_UNSET = object()


def _env_sidebar(host: Any) -> Any:
    """Return the environments sidebar panel (``_env_selector``)."""
    panel = getattr(host, "_env_selector", None)
    if panel is not None:
        return panel
    return getattr(host, "_environment_sidebar_panel", None)


def drain_mutation_bridge(host: Any) -> None:
    """Apply queued mutate/execute GUI side effects on the main thread."""
    events = drain_mutation_events()
    needs_collection_tree_refresh = False
    needs_local_tree_refresh = False
    saw_delete = False
    select_collection_id: int | None = None
    select_request_id: int | None = None
    select_local_script_id: int | None = None
    mutated_request_ids: set[int] = set()
    mutated_collection_ids: set[int] = set()
    mutated_local_script_ids: set[int] = set()
    open_targets: list[tuple[str, int, str]] = []
    execute_records: list[Any] = []
    refresh_environments = False
    refresh_variables = False
    refresh_snippets = False
    refresh_saved_responses = False
    refresh_history_panels = False
    active_environment_id: int | None | object = _UNSET

    for event in events:
        etype = event.get("type")
        if etype == "open_target":
            target = event.get("open_target")
            if isinstance(target, dict):
                kind = str(target.get("kind") or "")
                if kind == "local_script":
                    kind = "script"
                entity_id = target.get("id")
                focus = target.get("focus") or ""
                if isinstance(entity_id, int) and entity_id > 0 and kind:
                    open_targets.append((kind, entity_id, str(focus)))
                    if kind == "collection":
                        select_collection_id = entity_id
                    elif kind == "request":
                        select_request_id = entity_id
                    elif kind == "script":
                        select_local_script_id = entity_id
        elif etype == "mutated":
            entity = str(event.get("entity") or "")
            action = str(event.get("action") or "")
            ids = event.get("ids") or {}
            if not isinstance(ids, dict):
                ids = {}
            if entity in {"local_script", "local_script_folder"}:
                needs_local_tree_refresh = True
            elif entity == "active_environment":
                if action == "clear":
                    active_environment_id = None
                else:
                    env_id = ids.get("environment_id")
                    if isinstance(env_id, int) and env_id > 0:
                        active_environment_id = env_id
                refresh_variables = True
            elif entity == "history_entry":
                refresh_history_panels = True
            elif entity == "import":
                needs_collection_tree_refresh = True
                payload = event.get("payload") or {}
                if isinstance(payload, dict):
                    env_count = payload.get("environments_imported") or 0
                    if isinstance(env_count, int) and env_count > 0:
                        refresh_environments = True
                        refresh_variables = True
                else:
                    refresh_environments = True
                    refresh_variables = True
            elif entity in {"environment", "globals", "snippet", "saved_response"}:
                if entity == "environment":
                    refresh_environments = True
                    refresh_variables = True
                elif entity == "globals":
                    refresh_variables = True
                elif entity == "snippet":
                    refresh_snippets = True
                elif entity == "saved_response":
                    refresh_saved_responses = True
            elif entity == "script_version":
                pass
            elif entity == "settings":
                pass  # banners refreshed best-effort below
            elif entity == "debug_metadata":
                pass  # open editors reloaded via mutated_*_ids
            else:
                needs_collection_tree_refresh = True
            if action == "delete":
                saw_delete = True
                close_tabs_for_mutation_ids(host, ids)
            else:
                rid = ids.get("request_id")
                cid = ids.get("collection_id")
                sid = ids.get("local_script_id")
                if isinstance(rid, int) and rid > 0:
                    mutated_request_ids.add(rid)
                    if select_request_id is None and entity in {
                        "request",
                        "script_version",
                        "debug_metadata",
                    }:
                        select_request_id = rid
                if isinstance(cid, int) and cid > 0:
                    mutated_collection_ids.add(cid)
                    if select_collection_id is None and entity in {
                        "collection",
                        "script_version",
                        "debug_metadata",
                    }:
                        select_collection_id = cid
                if isinstance(sid, int) and sid > 0:
                    mutated_local_script_ids.add(sid)
                    if select_local_script_id is None and entity in {
                        "local_script",
                        "script_version",
                        "debug_metadata",
                    }:
                        select_local_script_id = sid
                    if entity == "script_version":
                        needs_local_tree_refresh = True
        elif etype == "executed":
            from services.ai.chat.execute_events import record_from_bridge_event

            record = record_from_bridge_event(event)
            if record is not None:
                execute_records.append(record)
            apply_executed_event(host, event)
        elif etype == "attach_graphql_schema":
            raw_payload = event.get("payload")
            gql_payload: dict[str, Any] = dict(raw_payload) if isinstance(raw_payload, dict) else {}
            raw_ids = event.get("ids")
            ids_map: dict[str, Any] = dict(raw_ids) if isinstance(raw_ids, dict) else {}
            rid = gql_payload.get("request_id") or ids_map.get("request_id")
            schema = gql_payload.get("schema")
            if isinstance(rid, int) and rid > 0 and isinstance(schema, dict):
                _attach_graphql_schema_to_open_editor(host, rid, schema)

    if execute_records:
        panel = host._right_sidebar.ai_chat_panel
        deliver = getattr(panel, "deliver_execute_update", None)
        if callable(deliver):
            deliver(execute_records)
        refresh_global = getattr(host, "_refresh_global_history_panel", None)
        if callable(refresh_global):
            refresh_global()
        request_panel = getattr(host, "_request_history_panel", None)
        if request_panel is not None:
            refresh = getattr(request_panel, "refresh", None)
            if callable(refresh):
                refresh()

    if saw_delete:
        close_stale_workspace_tabs(host)

    for request_id in mutated_request_ids:
        reload_open_request_from_db(host, request_id)
    for collection_id in mutated_collection_ids:
        reload_open_folder_from_db(host, collection_id)
    for script_id in mutated_local_script_ids:
        _reload_open_local_script_from_db(host, script_id)

    for kind, entity_id, focus in open_targets:
        open_target = getattr(host, "_on_workspace_target_requested", None)
        if callable(open_target):
            open_target(kind, entity_id, focus)

    if needs_collection_tree_refresh:
        collection_widget = getattr(host, "collection_widget", None)
        if collection_widget is not None:
            refresh = getattr(collection_widget, "refresh_collections", None)
            if callable(refresh):
                refresh(
                    select_request_id=select_request_id,
                    select_collection_id=select_collection_id,
                )
            else:
                start_fetch = getattr(collection_widget, "_start_fetch", None)
                if callable(start_fetch):
                    start_fetch()
        tabs = getattr(host, "_tabs", None)
        tab_bar = getattr(host, "_tab_bar", None)
        if isinstance(tabs, dict) and tab_bar is not None:
            ctx = tabs.get(tab_bar.currentIndex())
            sync = getattr(host, "_sync_tree_selection", None)
            if callable(sync):
                sync(ctx)

    if needs_local_tree_refresh:
        local_widget = getattr(host, "local_scripts_widget", None)
        if local_widget is not None:
            refresh = getattr(local_widget, "refresh_collections", None)
            if callable(refresh):
                refresh(select_request_id=select_local_script_id)
            else:
                start_fetch = getattr(local_widget, "_start_fetch", None)
                if callable(start_fetch):
                    start_fetch()

    if active_environment_id is not _UNSET:
        env_panel = _env_sidebar(host)
        if env_panel is not None:
            set_active = getattr(env_panel, "set_active_environment", None)
            if callable(set_active):
                set_active(active_environment_id)
    if refresh_environments:
        env_panel = _env_sidebar(host)
        if env_panel is not None:
            reload = getattr(env_panel, "refresh", None)
            if callable(reload):
                reload()
    if refresh_variables:
        refresh_sidebar = getattr(host, "_refresh_sidebar", None)
        if callable(refresh_sidebar):
            refresh_sidebar(history_load_detail=False)
    if refresh_snippets:
        refresh_snippets_fn = getattr(host, "refresh_snippets_sidebar", None)
        if callable(refresh_snippets_fn):
            refresh_snippets_fn()
    if refresh_saved_responses:
        refresh_sidebar = getattr(host, "_refresh_sidebar", None)
        if callable(refresh_sidebar):
            refresh_sidebar(history_load_detail=False)
    if refresh_history_panels:
        refresh_global = getattr(host, "_refresh_global_history_panel", None)
        if callable(refresh_global):
            refresh_global()
        request_panel = getattr(host, "_request_history_panel", None)
        if request_panel is not None:
            refresh = getattr(request_panel, "refresh", None)
            if callable(refresh):
                refresh()
        _clear_viewer_if_deleted_history(host, events)


def _clear_viewer_if_deleted_history(host: Any, events: list[Any]) -> None:
    """Best-effort: clear Response viewer if it shows a deleted history entry."""
    deleted_ids: set[int] = set()
    for event in events:
        if event.get("type") != "mutated":
            continue
        if str(event.get("entity") or "") != "history_entry":
            continue
        if str(event.get("action") or "") != "delete":
            continue
        ids = event.get("ids") or {}
        if not isinstance(ids, dict):
            continue
        hid = ids.get("history_entry_id")
        if isinstance(hid, int) and hid > 0:
            deleted_ids.add(hid)
    if not deleted_ids:
        return
    tabs = getattr(host, "_tabs", None)
    if not isinstance(tabs, dict):
        return
    for ctx in tabs.values():
        viewer = getattr(ctx, "response_widget", None)
        if viewer is None:
            continue
        viewing = getattr(viewer, "_viewing_stored_entry_id", None)
        if viewing not in deleted_ids:
            continue
        clear_fn = getattr(viewer, "clear_replay_history_source", None)
        if callable(clear_fn):
            clear_fn()
        discard = getattr(viewer, "_discard_stored_response_for_send", None)
        if callable(discard):
            discard()


def _reload_open_local_script_from_db(host: Any, script_id: int) -> None:
    """Reload an open local-script tab from the database."""
    from services.local_script_service import LocalScriptService

    data = LocalScriptService.get_script_load_dict(script_id)
    if data is None:
        return
    for idx, ctx in list(getattr(host, "_tabs", {}).items()):
        if getattr(ctx, "tab_type", None) != "local_script":
            continue
        if getattr(ctx, "local_script_id", None) != script_id:
            continue
        editor = getattr(ctx, "local_script_editor", None)
        if editor is None:
            continue
        editor.load_script(data)
        ctx.is_dirty = False
        update_tab = getattr(host._tab_bar, "update_tab", None)
        if callable(update_tab):
            from ui.local_scripts.script_filename import script_display_name

            update_tab(
                idx,
                name=script_display_name(
                    str(data.get("name") or ""),
                    str(data.get("language") or "javascript"),
                    str(data.get("module_format") or "esm"),
                ),
                is_dirty=False,
            )
        return


def _attach_graphql_schema_to_open_editor(
    host: Any,
    request_id: int,
    schema: dict[str, Any],
) -> None:
    """Attach an introspected schema onto an open GraphQL request editor."""
    from services.http.graphql_schema_service import GraphQLSchemaService

    tabs = getattr(host, "_tabs", None)
    if not isinstance(tabs, dict):
        return
    for ctx in tabs.values():
        if getattr(ctx, "tab_type", None) != "request":
            continue
        if getattr(ctx, "request_id", None) != request_id:
            continue
        editor = getattr(ctx, "request_widget", None)
        if editor is None:
            continue
        editor._gql_schema = schema
        label = getattr(editor, "_gql_schema_label", None)
        types_raw = schema.get("types")
        types = types_raw if isinstance(types_raw, list) else []
        count = len(types)
        if label is not None:
            label.setText(f"Schema ({count} types)")
            try:
                summary = GraphQLSchemaService.format_schema_summary(schema)  # type: ignore[arg-type]
                label.setToolTip(summary)
            except Exception:
                label.setToolTip("")
        return
