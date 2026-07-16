"""Field filters and mutate finish helper for data-plane entities."""

from __future__ import annotations

from typing import Any

from services.ai.chat.mutation.audit import append_mutation_audit
from services.ai.chat.mutation.bridge import OpenTargetDict, enqueue_mutation_event
from services.ai.chat.tools.workspace_mutate.common import WorkspaceMutateObservation, mutate_obs

_ENV_CREATE = frozenset({"name", "values"})
_ENV_UPDATE = frozenset({"values", "name"})
_GLOBALS_UPDATE = frozenset({"values"})
_ACTIVE_ENV_UPDATE = frozenset({"environment_id"})
_SNIPPET_CREATE = frozenset({"name", "language", "body", "category", "context"})
_SNIPPET_UPDATE = frozenset({"name", "body", "category", "context"})
_SAVED_CREATE = frozenset(
    {
        "name",
        "status",
        "code",
        "headers",
        "body",
        "preview_language",
        "history_entry_id",
        "request_id",
    }
)
_SAVED_RENAME = frozenset({"name"})
_IMPORT_CREATE = frozenset({"text", "curl", "url", "path", "format"})


def filter_data_fields(
    entity: str,
    action: str,
    fields: dict[str, Any],
) -> tuple[dict[str, Any] | None, WorkspaceMutateObservation | None]:
    """Return filtered fields for data-plane entities."""
    if action == "delete" and not fields:
        return {}, None
    if entity == "environment":
        if action == "create":
            allowed = _ENV_CREATE
        elif action == "rename":
            allowed = frozenset({"name"})
        elif action == "update":
            allowed = _ENV_UPDATE
        else:
            allowed = frozenset()
    elif entity == "active_environment":
        if action != "update":
            return None, mutate_obs("ok: false\nerror: active_environment_requires_update\n")
        allowed = _ACTIVE_ENV_UPDATE
    elif entity == "history_entry":
        if action != "delete":
            return None, mutate_obs("ok: false\nerror: history_entry_requires_delete\n")
        allowed = frozenset()
    elif entity == "import":
        if action != "create":
            return None, mutate_obs("ok: false\nerror: import_requires_create\n")
        allowed = _IMPORT_CREATE
    elif entity == "script_version":
        if action != "restore":
            return None, mutate_obs("ok: false\nerror: script_version_requires_restore\n")
        allowed = frozenset()
    elif entity == "globals":
        if action != "update":
            return None, mutate_obs("ok: false\nerror: globals_requires_update\n")
        allowed = _GLOBALS_UPDATE
    elif entity == "snippet":
        if action == "create":
            allowed = _SNIPPET_CREATE
        elif action == "rename":
            allowed = frozenset({"name", "category", "language"})
        elif action == "update":
            allowed = _SNIPPET_UPDATE
        elif action == "delete":
            allowed = frozenset({"language", "category"})
        else:
            allowed = frozenset()
    elif entity == "saved_response":
        if action == "create":
            allowed = _SAVED_CREATE
        elif action == "rename":
            allowed = _SAVED_RENAME
        elif action in {"delete", "duplicate"}:
            allowed = frozenset()
        else:
            allowed = frozenset()
    else:
        return None, mutate_obs(f"ok: false\nerror: unsupported_entity\nentity: {entity}\n")
    cleaned: dict[str, Any] = {}
    for key, value in fields.items():
        if key not in allowed:
            return None, mutate_obs(f"ok: false\nerror: unsupported_field\nfield: {key}\n")
        cleaned[key] = value
    if entity == "import":
        sources = [k for k in ("text", "curl", "url", "path") if k in cleaned]
        if len(sources) != 1:
            return None, mutate_obs(
                "ok: false\nerror: import_requires_exactly_one_source\nfields: text|curl|url|path\n"
            )
    return cleaned, None


def _finish(
    *,
    mutation_id: str,
    verb: str,
    entity: str,
    ids: dict[str, int],
    summary: str,
    warnings: list[str],
    open_after: bool,
    open_target: OpenTargetDict | None,
) -> WorkspaceMutateObservation:
    if open_after and open_target is not None:
        enqueue_mutation_event(
            {
                "type": "open_target",
                "entity": entity,
                "action": verb,
                "ids": ids,
                "open_target": open_target,
                "warnings": warnings,
            }
        )
    enqueue_mutation_event(
        {
            "type": "mutated",
            "entity": entity,
            "action": verb,
            "ids": ids,
            "warnings": warnings,
        }
    )
    append_mutation_audit(
        {
            "mutation_id": mutation_id,
            "action": verb,
            "entity": entity,
            "ids": ids,
            "summary": summary,
        }
    )
    lines = [
        "ok: true",
        f"mutation_id: {mutation_id}",
        f"summary: {summary}",
        f"action: {verb}",
        f"entity: {entity}",
        f"ids: {ids}",
    ]
    if warnings:
        lines.append(f"warnings: {warnings}")
    return mutate_obs("\n".join(lines) + "\n")
