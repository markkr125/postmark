"""Local script / folder mutations for ``postmark_workspace_mutate``."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from services.ai.chat.mutation.audit import append_mutation_audit
from services.ai.chat.mutation.bridge import OpenTargetDict, enqueue_mutation_event
from services.ai.chat.tools.workspace_mutate.common import (
    WorkspaceMutateObservation,
    mutate_obs,
)

_LOCAL_SCRIPT_UPDATE = frozenset({"content", "language", "module_format", "name"})
_LOCAL_SCRIPT_CREATE = frozenset({"name", "content", "language", "module_format"})
_LOCAL_FOLDER_FIELDS = frozenset({"name"})


def filter_local_fields(
    entity: str,
    action: str,
    fields: dict[str, Any],
) -> tuple[dict[str, Any] | None, WorkspaceMutateObservation | None]:
    """Return filtered fields for local_script / local_script_folder."""
    if action in {"delete", "move"} and not fields:
        return {}, None
    if entity == "local_script":
        if action == "create":
            allowed = _LOCAL_SCRIPT_CREATE
        elif action == "rename":
            allowed = frozenset({"name", "language", "module_format"})
        elif action == "update":
            allowed = _LOCAL_SCRIPT_UPDATE
        else:
            allowed = frozenset()
    elif entity == "local_script_folder":
        allowed = _LOCAL_FOLDER_FIELDS if action in {"create", "rename"} else frozenset()
    else:
        return None, mutate_obs(f"ok: false\nerror: unsupported_entity\nentity: {entity}\n")
    cleaned: dict[str, Any] = {}
    for key, value in fields.items():
        if key not in allowed:
            return None, mutate_obs(f"ok: false\nerror: unsupported_field\nfield: {key}\n")
        cleaned[key] = value
    return cleaned, None


def apply_local_mutation(
    *,
    verb: str,
    entity: str,
    target_id: int | None,
    parent_id: int | None,
    fields: dict[str, Any],
    open_after: bool,
) -> WorkspaceMutateObservation:
    """Apply local script / folder mutations via LocalScriptService."""
    from services.local_script_service import LocalScriptService

    mutation_id = uuid4().hex[:12]
    ids: dict[str, int] = {}
    summary = ""
    warnings: list[str] = []
    open_target: OpenTargetDict | None = None

    try:
        if entity == "local_script_folder":
            if verb == "create":
                name = str(fields.get("name") or "").strip()
                if not name:
                    return mutate_obs("ok: false\nerror: name_required\n")
                created_folder = LocalScriptService.create_folder(name, parent_id=parent_id)
                ids["local_script_folder_id"] = int(created_folder.id)
                summary = f"Created local script folder {name!r}"
            elif verb == "rename":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                name = str(fields.get("name") or "").strip()
                if not name:
                    return mutate_obs("ok: false\nerror: name_required\n")
                LocalScriptService.rename_folder(target_id, name)
                ids["local_script_folder_id"] = int(target_id)
                summary = f"Renamed local script folder to {name!r}"
            elif verb == "move":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                LocalScriptService.move_folder(target_id, parent_id)
                ids["local_script_folder_id"] = int(target_id)
                summary = f"Moved local script folder {target_id}"
            elif verb == "delete":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                LocalScriptService.delete_folder(target_id)
                ids["local_script_folder_id"] = int(target_id)
                summary = f"Deleted local script folder {target_id}"
            else:
                return mutate_obs(f"ok: false\nerror: unsupported_action\naction: {verb}\n")
        elif entity == "local_script":
            if verb == "create":
                if parent_id is None:
                    return mutate_obs("ok: false\nerror: parent_id_required\n")
                name = str(fields.get("name") or "").strip()
                if not name:
                    return mutate_obs("ok: false\nerror: name_required\n")
                language = str(fields.get("language") or "javascript")
                module_format = str(fields.get("module_format") or "esm")
                content = str(fields.get("content") or "")
                created_script = LocalScriptService.create_script(
                    parent_id,
                    name,
                    language=language,
                    module_format=module_format,
                    content=content,
                )
                ids["local_script_id"] = int(created_script.id)
                summary = f"Created local script {name!r}"
                open_target = {"kind": "local_script", "id": int(created_script.id)}
            elif verb == "update":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                content_raw: Any = fields.get("content")
                language_raw: Any = fields.get("language")
                module_format_raw: Any = fields.get("module_format")
                name_raw: Any = fields.get("name")
                if (
                    content_raw is not None
                    or language_raw is not None
                    or module_format_raw is not None
                ):
                    load = LocalScriptService.get_script_load_dict(target_id)
                    if load is None:
                        return mutate_obs("ok: false\nerror: local_script_not_found\n")
                    LocalScriptService.save_script_content(
                        target_id,
                        str(content_raw)
                        if content_raw is not None
                        else str(load.get("content") or ""),
                        language=str(language_raw) if language_raw is not None else None,
                        module_format=(
                            str(module_format_raw) if module_format_raw is not None else None
                        ),
                    )
                if name_raw is not None:
                    nm = str(name_raw).strip()
                    if not nm:
                        return mutate_obs("ok: false\nerror: name_required\n")
                    LocalScriptService.rename_script(
                        target_id,
                        nm,
                        language=str(language_raw) if language_raw is not None else None,
                        module_format=(
                            str(module_format_raw) if module_format_raw is not None else None
                        ),
                    )
                ids["local_script_id"] = int(target_id)
                summary = f"Updated local script {target_id}"
                open_target = {"kind": "local_script", "id": int(target_id)}
            elif verb == "rename":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                name = str(fields.get("name") or "").strip()
                if not name:
                    return mutate_obs("ok: false\nerror: name_required\n")
                LocalScriptService.rename_script(
                    target_id,
                    name,
                    language=(str(fields["language"]) if "language" in fields else None),
                    module_format=(
                        str(fields["module_format"]) if "module_format" in fields else None
                    ),
                )
                ids["local_script_id"] = int(target_id)
                summary = f"Renamed local script to {name!r}"
                open_target = {"kind": "local_script", "id": int(target_id)}
            elif verb == "move":
                if target_id is None or parent_id is None:
                    return mutate_obs("ok: false\nerror: target_id_and_parent_id_required\n")
                LocalScriptService.move_script(target_id, parent_id)
                ids["local_script_id"] = int(target_id)
                summary = f"Moved local script {target_id}"
                open_target = {"kind": "local_script", "id": int(target_id)}
            elif verb == "delete":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                LocalScriptService.delete_script(target_id)
                ids["local_script_id"] = int(target_id)
                summary = f"Deleted local script {target_id}"
            else:
                return mutate_obs(f"ok: false\nerror: unsupported_action\naction: {verb}\n")
        else:
            return mutate_obs(f"ok: false\nerror: unsupported_entity\nentity: {entity}\n")
    except Exception as exc:
        return mutate_obs(f"ok: false\nerror: {type(exc).__name__}\nmessage: {exc}\n")

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
    deep_links: list[str] = []
    if "local_script_id" in ids:
        deep_links.append(f"postmark://script/{ids['local_script_id']}")
    lines = [
        "ok: true",
        f"mutation_id: {mutation_id}",
        f"summary: {summary}",
        f"action: {verb}",
        f"entity: {entity}",
        f"ids: {ids}",
    ]
    if deep_links:
        lines.append(f"deep_links: {deep_links}")
    if warnings:
        lines.append(f"warnings: {warnings}")
    return mutate_obs("\n".join(lines) + "\n")


__all__ = [
    "apply_local_mutation",
    "filter_local_fields",
]
