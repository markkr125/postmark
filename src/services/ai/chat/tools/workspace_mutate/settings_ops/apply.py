"""Allowlisted settings mutations for Agent."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from services.ai.chat.mutation.audit import append_mutation_audit
from services.ai.chat.mutation.bridge import enqueue_mutation_event
from services.ai.chat.tools.workspace_mutate.common import (
    WorkspaceMutateObservation,
    mutate_obs,
)

# Keys Agent may read and write (mirrored in workspace_query settings render).
SETTINGS_ALLOWLIST = frozenset(
    {
        "deno_path",
        "python_path",
        "lsp_enabled",
        "format_on_save",
        "allow_local_subrequests",
        "history_retention_days",
        "history_max_items_per_day",
        "history_unlimited_per_day",
        "history_max_response_bytes",
        "tabs_small_labels",
        "tabs_wrap_mode",
        "tabs_show_path_for_duplicates",
        "tabs_mark_modified",
        "tabs_show_full_path_on_hover",
        "tabs_open_new_tabs_at_end",
        "tabs_enable_preview_tab",
        "tabs_activate_on_close",
    }
)


def filter_settings_fields(
    action: str,
    fields: dict[str, Any],
) -> tuple[dict[str, Any] | None, WorkspaceMutateObservation | None]:
    """Keep only allowlisted settings keys."""
    if action != "update":
        return None, mutate_obs(f"ok: false\nerror: unsupported_action\naction: {action}\n")
    if not fields:
        return None, mutate_obs("ok: false\nerror: fields_required\n")
    cleaned: dict[str, Any] = {}
    for key, value in fields.items():
        if key.startswith("ai/") or key.startswith("ai_"):
            return None, mutate_obs(f"ok: false\nerror: settings_key_forbidden\nfield: {key}\n")
        if key not in SETTINGS_ALLOWLIST:
            return None, mutate_obs(f"ok: false\nerror: unsupported_field\nfield: {key}\n")
        cleaned[key] = value
    return cleaned, None


def apply_settings_mutation(
    *,
    fields: dict[str, Any],
) -> WorkspaceMutateObservation:
    """Apply allowlisted settings via owning managers."""
    from services.scripting.runtime_settings import RuntimeSettings
    from ui.styling.history_settings_manager import HistorySettingsManager
    from ui.styling.tab_settings_manager import TabSettingsManager

    mutation_id = uuid4().hex[:12]
    applied: list[str] = []
    try:
        history = HistorySettingsManager()
        tabs = TabSettingsManager()
        for key, value in fields.items():
            if key == "deno_path":
                RuntimeSettings.set_deno_path(str(value))
            elif key == "python_path":
                RuntimeSettings.set_python_path(str(value))
            elif key == "lsp_enabled":
                RuntimeSettings.set_lsp_enabled(bool(value))
            elif key == "format_on_save":
                RuntimeSettings.set_format_on_save(bool(value))
            elif key == "allow_local_subrequests":
                RuntimeSettings.set_allow_local_subrequests(bool(value))
            elif key == "history_retention_days":
                history.retention_days = int(value)
            elif key == "history_max_items_per_day":
                history.max_items_per_day = int(value)
            elif key == "history_unlimited_per_day":
                history.unlimited_per_day = bool(value)
            elif key == "history_max_response_bytes":
                history.max_response_bytes = int(value)
            elif key == "tabs_small_labels":
                tabs.small_labels = bool(value)
            elif key == "tabs_wrap_mode":
                tabs.wrap_mode = str(value)
            elif key == "tabs_show_path_for_duplicates":
                tabs.show_path_for_duplicates = bool(value)
            elif key == "tabs_mark_modified":
                tabs.mark_modified = bool(value)
            elif key == "tabs_show_full_path_on_hover":
                tabs.show_full_path_on_hover = bool(value)
            elif key == "tabs_open_new_tabs_at_end":
                tabs.open_new_tabs_at_end = bool(value)
            elif key == "tabs_enable_preview_tab":
                tabs.enable_preview_tab = bool(value)
            elif key == "tabs_activate_on_close":
                tabs.activate_on_close = str(value)
            else:
                return mutate_obs(f"ok: false\nerror: unsupported_field\nfield: {key}\n")
            applied.append(key)

        summary = f"Updated settings: {', '.join(applied)}"
        enqueue_mutation_event(
            {
                "type": "mutated",
                "entity": "settings",
                "action": "update",
                "ids": {},
                "payload": {"summary": summary, "keys": applied},
            }
        )
        append_mutation_audit(
            {
                "mutation_id": mutation_id,
                "entity": "settings",
                "action": "update",
                "summary": summary,
                "keys": applied,
            }
        )
        return mutate_obs(
            "ok: true\n"
            f"mutation_id: {mutation_id}\n"
            "entity: settings\n"
            "action: update\n"
            f"summary: {summary}\n"
            f"keys: {applied}\n"
        )
    except Exception as exc:
        return mutate_obs(f"ok: false\nerror: {type(exc).__name__}\nmessage: {exc}\n")
