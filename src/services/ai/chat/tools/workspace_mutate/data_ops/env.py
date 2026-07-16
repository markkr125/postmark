"""Environment, globals, auth, and collection-variable mutate ops."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from services.ai.chat.mutation.bridge import OpenTargetDict
from services.ai.chat.tools.workspace_mutate.common import (
    WorkspaceMutateObservation,
    env_values_have_secret_writes,
    globals_have_secret_writes,
    mutate_obs,
    reject_raw_secret_value,
    sanitize_auth_payload,
    sanitize_env_values,
)
from services.ai.chat.tools.workspace_mutate.data_ops.common import _finish


def apply_collection_variables(
    *,
    target_id: int,
    variables: list[Any],
    open_after: bool,
) -> WorkspaceMutateObservation:
    """Replace collection variables on a folder (secrets policy applied)."""
    from services.collection_service import CollectionService

    cleaned, err = sanitize_env_values(variables)
    if err or cleaned is None:
        return mutate_obs(f"ok: false\nerror: {err or 'invalid_variables'}\n")
    mutation_id = uuid4().hex[:12]
    CollectionService.update_collection(target_id, variables=cleaned)
    warnings: list[str] = []
    if env_values_have_secret_writes(cleaned):
        warnings.append("secret_keys_placeholder_only")
    return _finish(
        mutation_id=mutation_id,
        verb="update",
        entity="collection",
        ids={"collection_id": int(target_id)},
        summary=f"Updated collection variables on {target_id}",
        warnings=warnings,
        open_after=open_after,
        open_target={"kind": "collection", "id": int(target_id)},
    )


def apply_auth_update(
    *,
    entity: str,
    target_id: int,
    auth: object,
    open_after: bool,
) -> WorkspaceMutateObservation:
    """Update request or collection auth with placeholder-only secrets."""
    from services.collection_service import CollectionService

    cleaned, err = sanitize_auth_payload(auth)
    if err or cleaned is None:
        return mutate_obs(f"ok: false\nerror: {err or 'invalid_auth'}\n")
    mutation_id = uuid4().hex[:12]
    if entity == "request":
        CollectionService.update_request(target_id, auth=cleaned)
        ids = {"request_id": int(target_id)}
        open_target: OpenTargetDict | None = {
            "kind": "request",
            "id": int(target_id),
            "focus": "auth",
        }
        summary = f"Updated auth on request {target_id}"
    else:
        CollectionService.update_collection(target_id, auth=cleaned)
        ids = {"collection_id": int(target_id)}
        open_target = {"kind": "collection", "id": int(target_id)}
        summary = f"Updated auth on collection {target_id}"
    # Bridge entity stays request/collection for tab reload; action kind uses auth.
    return _finish(
        mutation_id=mutation_id,
        verb="update",
        entity=entity,
        ids=ids,
        summary=summary,
        warnings=["auth_placeholders_only"],
        open_after=open_after,
        open_target=open_target if open_after else None,
    )


def _apply_environment(
    *,
    verb: str,
    target_id: int | None,
    fields: dict[str, Any],
    mutation_id: str,
    open_after: bool,
) -> WorkspaceMutateObservation:
    from services.environment_service import EnvironmentService

    ids: dict[str, int] = {}
    warnings: list[str] = []
    if verb == "create":
        name = str(fields.get("name") or "").strip()
        if not name:
            return mutate_obs("ok: false\nerror: name_required\n")
        values_raw = fields.get("values") or []
        if not isinstance(values_raw, list):
            return mutate_obs("ok: false\nerror: values_list_required\n")
        cleaned, err = sanitize_env_values(values_raw)
        if err or cleaned is None:
            return mutate_obs(f"ok: false\nerror: {err or 'invalid_values'}\n")
        if env_values_have_secret_writes(cleaned):
            warnings.append("secret_keys_placeholder_only")
        created = EnvironmentService.create_environment(name, cleaned)
        ids["environment_id"] = int(created.id)
        summary = f"Created environment {name!r}"
    elif verb == "rename":
        if target_id is None:
            return mutate_obs("ok: false\nerror: target_id_required\n")
        name = str(fields.get("name") or "").strip()
        if not name:
            return mutate_obs("ok: false\nerror: name_required\n")
        EnvironmentService.rename_environment(target_id, name)
        ids["environment_id"] = int(target_id)
        summary = f"Renamed environment to {name!r}"
    elif verb == "update":
        if target_id is None:
            return mutate_obs("ok: false\nerror: target_id_required\n")
        if "name" in fields:
            name = str(fields.get("name") or "").strip()
            if not name:
                return mutate_obs("ok: false\nerror: name_required\n")
            EnvironmentService.rename_environment(target_id, name)
        if "values" in fields:
            values_raw = fields.get("values")
            if not isinstance(values_raw, list):
                return mutate_obs("ok: false\nerror: values_list_required\n")
            cleaned, err = sanitize_env_values(values_raw)
            if err or cleaned is None:
                return mutate_obs(f"ok: false\nerror: {err or 'invalid_values'}\n")
            if env_values_have_secret_writes(cleaned):
                warnings.append("secret_keys_placeholder_only")
            EnvironmentService.update_environment_values(target_id, cleaned)
        ids["environment_id"] = int(target_id)
        summary = f"Updated environment {target_id}"
    elif verb == "delete":
        if target_id is None:
            return mutate_obs("ok: false\nerror: target_id_required\n")
        EnvironmentService.delete_environment(target_id)
        ids["environment_id"] = int(target_id)
        summary = f"Deleted environment {target_id}"
    else:
        return mutate_obs(f"ok: false\nerror: unsupported_action\naction: {verb}\n")
    del open_after  # environments open via sidebar refresh, not tab open_target
    return _finish(
        mutation_id=mutation_id,
        verb=verb,
        entity="environment",
        ids=ids,
        summary=summary,
        warnings=warnings,
        open_after=False,
        open_target=None,
    )


def _apply_globals(
    *,
    fields: dict[str, Any],
    mutation_id: str,
    open_after: bool,
) -> WorkspaceMutateObservation:
    from services.scripting.context import load_globals, save_globals

    values_raw = fields.get("values")
    if not isinstance(values_raw, dict):
        return mutate_obs("ok: false\nerror: values_dict_required\n")
    changes: dict[str, str] = {}
    for key, value in values_raw.items():
        k = str(key).strip()
        if not k:
            continue
        err = reject_raw_secret_value(k, value)
        if err:
            return mutate_obs(f"ok: false\nerror: {err}\nfield: {k}\n")
        changes[k] = "" if value is None else str(value)
    warnings: list[str] = []
    if globals_have_secret_writes(changes):
        warnings.append("secret_keys_placeholder_only")
    save_globals(changes)
    current = load_globals()
    del open_after
    return _finish(
        mutation_id=mutation_id,
        verb="update",
        entity="globals",
        ids={},
        summary=f"Updated {len(changes)} global variable(s) (total={len(current)})",
        warnings=warnings,
        open_after=False,
        open_target=None,
    )
