"""User-managed auto-approve whitelist for Agent mutate/execute kinds."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QSettings

_ORG = "Postmark"
_APP = "Postmark"
_KEY = "ai/agent_auto_approve_rules"

# Phase 0-1 catalog (Phase 2 kinds appended below).
_PHASE01_CATALOG: dict[str, str] = {
    "mutate:create:collection": "Create collection",
    "mutate:update:collection": "Update collection",
    "mutate:rename:collection": "Rename collection",
    "mutate:move:collection": "Move collection",
    "mutate:delete:collection": "Delete collection",
    "mutate:create:request": "Create request",
    "mutate:update:request": "Update request",
    "mutate:rename:request": "Rename request",
    "mutate:move:request": "Move request",
    "mutate:delete:request": "Delete request",
    "mutate:duplicate:request": "Duplicate request",
    "execute:send_request": "Send request",
    "execute:send_draft": "Send draft",
    "execute:replay_history": "Replay history",
}

_PHASE2_CATALOG: dict[str, str] = {
    "mutate:update:assertion_set": "Replace assertions",
    "execute:run_scripts": "Run scripts",
    "execute:run_local_script": "Run local script",
    "mutate:create:local_script": "Create local script",
    "mutate:update:local_script": "Update local script",
    "mutate:rename:local_script": "Rename local script",
    "mutate:move:local_script": "Move local script",
    "mutate:delete:local_script": "Delete local script",
    "mutate:create:local_script_folder": "Create local script folder",
    "mutate:rename:local_script_folder": "Rename local script folder",
    "mutate:move:local_script_folder": "Move local script folder",
    "mutate:delete:local_script_folder": "Delete local script folder",
    "mutate:create:environment": "Create environment",
    "mutate:rename:environment": "Rename environment",
    "mutate:update:environment": "Update environment",
    "mutate:delete:environment": "Delete environment",
    "mutate:update:active_environment": "Set active environment",
    "mutate:update:globals": "Update globals",
    "mutate:create:snippet": "Create snippet",
    "mutate:rename:snippet": "Rename snippet",
    "mutate:update:snippet": "Update snippet",
    "mutate:delete:snippet": "Delete snippet",
    "mutate:create:saved_response": "Create saved response",
    "mutate:rename:saved_response": "Rename saved response",
    "mutate:delete:saved_response": "Delete saved response",
    "mutate:duplicate:saved_response": "Duplicate saved response",
    "mutate:delete:history_entry": "Delete history entry",
    "mutate:create:import": "Import workspace",
    "mutate:restore:script_version": "Restore script version",
    "mutate:update:debug_metadata": "Update breakpoints / watches",
    "mutate:update:settings": "Update settings",
    "execute:run_collection": "Run collection",
    "execute:run_iterations": "Run data-driven iterations",
    "execute:fetch_graphql_schema": "Fetch GraphQL schema",
    "execute:generate_snippet": "Generate code snippet",
    "execute:export_workspace_artifact": "Export workspace artifact",
}

# Sensitive kinds — never persist via Always allow (not in CATALOG).
_NEVER_ALWAYS_ALLOW = frozenset(
    {
        "mutate:update:auth",
        "mutate:update:environment_secret",
        "execute:oauth_get_token",
    }
)

CATALOG: dict[str, str] = {**_PHASE01_CATALOG, **_PHASE2_CATALOG}

_READ_ONLY_TOOLS = frozenset(
    {
        "postmark_wiki_query",
        "postmark_workspace_query",
        "postmark_datetime",
        "delegate",
        "task",
        "task_tracker",
        "ThinkTool",
        "FinishTool",
        "think",
        "finish",
    }
)

_MUTATE_TOOL = "postmark_workspace_mutate"
_EXECUTE_TOOL = "postmark_workspace_execute"


def _get_settings() -> QSettings:
    return QSettings(_ORG, _APP)


def kind_label(kind: str) -> str:
    """Return the human label for a catalog kind, or the kind itself."""
    return CATALOG.get(kind, kind)


def list_rules() -> list[str]:
    """Return persisted auto-approve kind strings (catalog-validated)."""
    raw = _get_settings().value(_KEY, "[]")
    items: list[Any]
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw) if raw.strip() else []
        except json.JSONDecodeError:
            return []
        items = parsed if isinstance(parsed, list) else []
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        kind = item.strip()
        if kind not in CATALOG or kind in seen:
            continue
        seen.add(kind)
        out.append(kind)
    return sorted(out)


def _write_rules(kinds: list[str]) -> None:
    cleaned = sorted({k for k in kinds if k in CATALOG})
    _get_settings().setValue(_KEY, json.dumps(cleaned))


def add_rule(kind: str) -> bool:
    """Add a catalog kind to the whitelist. Return False if invalid."""
    kind = kind.strip()
    if kind in _NEVER_ALWAYS_ALLOW:
        return False
    if kind not in CATALOG:
        return False
    rules = list_rules()
    if kind not in rules:
        rules.append(kind)
        _write_rules(rules)
    return True


def remove_rule(kind: str) -> None:
    """Remove a kind from the whitelist (no-op if absent)."""
    rules = [k for k in list_rules() if k != kind.strip()]
    _write_rules(rules)


def clear_rules() -> None:
    """Clear the auto-approve whitelist."""
    _write_rules([])


def is_auto_approved(kind: str | None) -> bool:
    """Return True when *kind* is on the user whitelist."""
    if not kind:
        return False
    return kind in set(list_rules())


def kind_from_tool_args(
    tool_name: str,
    *,
    action: str | None = None,
    entity: str | None = None,
    operation: str | None = None,
) -> str | None:
    """Build a catalog kind from tool name + action fields."""
    if tool_name in _READ_ONLY_TOOLS:
        return None
    if tool_name == _MUTATE_TOOL:
        if not action or not entity:
            return None
        kind = f"mutate:{action}:{entity}"
        return kind
    if tool_name == _EXECUTE_TOOL:
        if not operation:
            return None
        kind = f"execute:{operation}"
        return kind
    return None


def kind_from_action_event(action_event: object) -> str | None:
    """Derive a whitelist kind from an OpenHands ActionEvent."""
    tool_name = str(getattr(action_event, "tool_name", "") or "")
    action_obj = getattr(action_event, "action", None)
    if action_obj is None:
        return kind_from_tool_args(tool_name)
    action = getattr(action_obj, "action", None)
    entity = getattr(action_obj, "entity", None)
    operation = getattr(action_obj, "operation", None)
    fields = getattr(action_obj, "fields", None)
    field_map = fields if isinstance(fields, dict) else {}
    action_s = str(action) if action is not None else None
    entity_s = str(entity) if entity is not None else None
    if tool_name == _MUTATE_TOOL and action_s == "update":
        if "auth" in field_map:
            return "mutate:update:auth"
        if entity_s == "environment" and _fields_have_secret_env_writes(field_map):
            return "mutate:update:environment_secret"
        if entity_s == "collection" and _fields_have_secret_env_writes(
            {"values": field_map.get("variables")}
        ):
            return "mutate:update:environment_secret"
    return kind_from_tool_args(
        tool_name,
        action=action_s,
        entity=entity_s,
        operation=str(operation) if operation is not None else None,
    )


def _fields_have_secret_env_writes(fields: dict[str, object]) -> bool:
    """Return True when *fields* carries secret env keys or raw secret values."""
    from services.ai.chat.tools.workspace_mutate.common import (
        env_values_have_secret_writes,
        key_looks_sensitive,
        reject_raw_secret_value,
        sanitize_env_values,
    )

    values = fields.get("values")
    if not isinstance(values, list):
        return False
    for raw in values:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        if not key:
            continue
        type_raw = str(raw.get("type") or "default").strip().lower()
        is_secret_type = type_raw in {"secret", "password", "hidden"}
        if (is_secret_type or key_looks_sensitive(key)) and reject_raw_secret_value(
            key, raw.get("value", "")
        ):
            return True
    cleaned, err = sanitize_env_values(values)
    if err or cleaned is None:
        return False
    return env_values_have_secret_writes(cleaned)


def is_mutate_or_execute_tool(tool_name: str) -> bool:
    """Return True for Postmark mutate/execute tool names."""
    return tool_name in {_MUTATE_TOOL, _EXECUTE_TOOL}


__all__ = [
    "CATALOG",
    "add_rule",
    "clear_rules",
    "is_auto_approved",
    "is_mutate_or_execute_tool",
    "kind_from_action_event",
    "kind_from_tool_args",
    "kind_label",
    "list_rules",
    "remove_rule",
]
