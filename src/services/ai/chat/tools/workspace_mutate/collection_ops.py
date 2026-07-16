"""Collection, request, and assertion_set mutations for ``postmark_workspace_mutate``."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from services.ai.chat.mutation.audit import append_mutation_audit
from services.ai.chat.mutation.bridge import OpenTargetDict, enqueue_mutation_event
from services.ai.chat.tools.workspace_mutate.common import (
    WorkspaceMutateObservation,
    env_values_have_secret_writes,
    mutate_obs,
    sanitize_auth_payload,
    sanitize_env_values,
)
from services.ai.chat.tools.workspace_mutate.data_ops import (
    apply_auth_update,
    apply_collection_variables,
)

_COLLECTION_UPDATE_FIELDS = frozenset({"description", "variables", "auth"})
_COLLECTION_EVENTS_FIELD = frozenset({"events"})
_REQUEST_P1_FIELDS = frozenset(
    {
        "name",
        "method",
        "url",
        "body",
        "request_parameters",
        "headers",
        "description",
        "body_mode",
        "body_options",
        "auth",
    }
)
_REQUEST_P2_EXTRA = frozenset({"scripts"})


def _reject_disallowed_binary_body(
    fields: dict[str, Any],
) -> WorkspaceMutateObservation | None:
    """Reject binary body paths that fail the Agent path allowlist."""
    mode = str(fields.get("body_mode") or "").strip().casefold()
    if mode != "binary":
        return None
    if "body" not in fields:
        return None
    body = str(fields.get("body") or "").strip()
    if not body:
        return mutate_obs("ok: false\nerror: empty_binary_path\n")
    from services.ai.chat.execution.binary.path_policy import validate_binary_path

    _path, err = validate_binary_path(body)
    if err:
        return mutate_obs(f"ok: false\nerror: {err}\n")
    return None


def filter_collection_fields(
    entity: str,
    action: str,
    fields: dict[str, Any],
    *,
    allow_scripts: bool,
) -> tuple[dict[str, Any] | None, WorkspaceMutateObservation | None]:
    """Return filtered fields for collection / request / assertion_set."""
    if action in {"delete", "duplicate"} and not fields:
        return {}, None
    if action == "move" and not fields:
        return {}, None
    if entity == "collection":
        if action in {"create", "rename"}:
            allowed = frozenset({"name"})
        elif action == "update":
            allowed_set = set(_COLLECTION_UPDATE_FIELDS)
            if allow_scripts:
                allowed_set |= _COLLECTION_EVENTS_FIELD
            allowed = frozenset(allowed_set)
        else:
            allowed = frozenset()
    elif entity == "request":
        if action == "rename":
            allowed = frozenset({"name"})
        elif action in {"create", "update"}:
            allowed_set = set(_REQUEST_P1_FIELDS)
            if allow_scripts:
                allowed_set |= _REQUEST_P2_EXTRA
            allowed = frozenset(allowed_set)
        else:
            allowed = frozenset()
    elif entity == "assertion_set":
        allowed = frozenset({"assertions"})
    else:
        return None, mutate_obs(f"ok: false\nerror: unsupported_entity\nentity: {entity}\n")
    cleaned: dict[str, Any] = {}
    for key, value in fields.items():
        if key not in allowed:
            return None, mutate_obs(f"ok: false\nerror: unsupported_field\nfield: {key}\n")
        cleaned[key] = value
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
    deep_links: list[str] = []
    if "request_id" in ids:
        deep_links.append(f"postmark://request/{ids['request_id']}")
    if "collection_id" in ids:
        deep_links.append(f"postmark://collection/{ids['collection_id']}")
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


def apply_collection_mutation(
    *,
    verb: str,
    entity: str,
    target_id: int | None,
    parent_id: int | None,
    collection_id: int | None,
    fields: dict[str, Any],
    open_after: bool,
    allow_scripts: bool,
) -> WorkspaceMutateObservation:
    """Apply collection / request / assertion_set mutations."""
    del allow_scripts  # filtering already applied
    from services.assertion_service import AssertionService
    from services.collection_service import CollectionService

    if verb == "duplicate" and entity != "request":
        return mutate_obs("ok: false\nerror: collection_duplicate_not_supported\n")

    mutation_id = uuid4().hex[:12]
    ids: dict[str, int] = {}
    summary = ""
    warnings: list[str] = []
    open_target: OpenTargetDict | None = None

    try:
        if entity == "collection":
            if verb == "create":
                name = str(fields.get("name") or "").strip()
                if not name:
                    return mutate_obs("ok: false\nerror: name_required\n")
                created = CollectionService.create_collection(name, parent_id=parent_id)
                ids["collection_id"] = int(created.id)
                summary = f"Created collection {name!r}"
                open_target = {"kind": "collection", "id": int(created.id)}
            elif verb == "update":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                field_keys = set(fields.keys())
                if field_keys == {"auth"}:
                    return apply_auth_update(
                        entity="collection",
                        target_id=target_id,
                        auth=fields["auth"],
                        open_after=open_after,
                    )
                if field_keys == {"variables"}:
                    variables = fields.get("variables")
                    if not isinstance(variables, list):
                        return mutate_obs("ok: false\nerror: variables_list_required\n")
                    return apply_collection_variables(
                        target_id=target_id,
                        variables=variables,
                        open_after=open_after,
                    )
                update_fields = dict(fields)
                if "auth" in update_fields:
                    cleaned_auth, err = sanitize_auth_payload(update_fields["auth"])
                    if err or cleaned_auth is None:
                        return mutate_obs(f"ok: false\nerror: {err or 'invalid_auth'}\n")
                    update_fields["auth"] = cleaned_auth
                    warnings.append("auth_placeholders_only")
                if "variables" in update_fields:
                    variables_raw = update_fields["variables"]
                    if not isinstance(variables_raw, list):
                        return mutate_obs("ok: false\nerror: variables_list_required\n")
                    cleaned_vars, err = sanitize_env_values(variables_raw)
                    if err or cleaned_vars is None:
                        return mutate_obs(f"ok: false\nerror: {err or 'invalid_variables'}\n")
                    update_fields["variables"] = cleaned_vars
                    if env_values_have_secret_writes(cleaned_vars):
                        warnings.append("secret_keys_placeholder_only")
                CollectionService.update_collection(target_id, **update_fields)
                ids["collection_id"] = int(target_id)
                summary = f"Updated collection {target_id}"
                focus = None
                events_payload = update_fields.get("events")
                if isinstance(events_payload, dict):
                    if events_payload.get("test"):
                        focus = "test"
                    elif events_payload.get("pre_request"):
                        focus = "pre_request"
                open_target = {
                    "kind": "collection",
                    "id": int(target_id),
                    "focus": focus,
                }
            elif verb == "rename":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                name = str(fields.get("name") or "").strip()
                if not name:
                    return mutate_obs("ok: false\nerror: name_required\n")
                CollectionService.rename_collection(target_id, name)
                ids["collection_id"] = int(target_id)
                summary = f"Renamed collection to {name!r}"
                open_target = {"kind": "collection", "id": int(target_id)}
            elif verb == "move":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                CollectionService.move_collection(target_id, parent_id)
                ids["collection_id"] = int(target_id)
                summary = f"Moved collection {target_id}"
            elif verb == "delete":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                CollectionService.delete_collection(target_id)
                ids["collection_id"] = int(target_id)
                summary = f"Deleted collection {target_id}"
            else:
                return mutate_obs(f"ok: false\nerror: unsupported_action\naction: {verb}\n")
        elif entity == "request":
            if verb == "create":
                if collection_id is None:
                    return mutate_obs("ok: false\nerror: collection_id_required\n")
                bin_err = _reject_disallowed_binary_body(fields)
                if bin_err is not None:
                    return bin_err
                create_fields = dict(fields)
                auth_payload = create_fields.pop("auth", None)
                name = str(create_fields.get("name") or "New Request")
                method = str(create_fields.get("method") or "GET")
                url = str(create_fields.get("url") or "")
                created_req = CollectionService.create_request(
                    collection_id,
                    method,
                    url,
                    name,
                    body=create_fields.get("body"),
                    request_parameters=create_fields.get("request_parameters"),
                    headers=create_fields.get("headers"),
                    scripts=create_fields.get("scripts"),
                )
                post_create = {
                    key: create_fields[key]
                    for key in ("description", "body_mode", "body_options")
                    if key in create_fields
                }
                if auth_payload is not None:
                    cleaned_auth, err = sanitize_auth_payload(auth_payload)
                    if err or cleaned_auth is None:
                        return mutate_obs(f"ok: false\nerror: {err or 'invalid_auth'}\n")
                    post_create["auth"] = cleaned_auth
                    warnings.append("auth_placeholders_only")
                if post_create:
                    CollectionService.update_request(int(created_req.id), **post_create)
                ids["request_id"] = int(created_req.id)
                summary = f"Created request {name!r}"
                open_target = {
                    "kind": "request",
                    "id": int(created_req.id),
                    "focus": "test" if "scripts" in fields else None,
                }
            elif verb == "update":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                update_fields = dict(fields)
                # When only body is set, resolve body_mode from the saved request.
                if (
                    "body" in update_fields
                    and str(update_fields.get("body_mode") or "").casefold() != "binary"
                ):
                    existing = CollectionService.get_request(int(target_id))
                    existing_mode = (
                        str(getattr(existing, "body_mode", "") or "")
                        if existing is not None
                        else ""
                    )
                    check_fields = dict(update_fields)
                    if existing_mode.casefold() == "binary" and "body_mode" not in check_fields:
                        check_fields["body_mode"] = "binary"
                    bin_err = _reject_disallowed_binary_body(check_fields)
                else:
                    bin_err = _reject_disallowed_binary_body(update_fields)
                if bin_err is not None:
                    return bin_err
                if set(update_fields.keys()) == {"auth"}:
                    return apply_auth_update(
                        entity="request",
                        target_id=target_id,
                        auth=update_fields["auth"],
                        open_after=open_after,
                    )
                if "auth" in update_fields:
                    cleaned_auth, err = sanitize_auth_payload(update_fields["auth"])
                    if err or cleaned_auth is None:
                        return mutate_obs(f"ok: false\nerror: {err or 'invalid_auth'}\n")
                    update_fields["auth"] = cleaned_auth
                    warnings.append("auth_placeholders_only")
                CollectionService.update_request(target_id, **update_fields)
                ids["request_id"] = int(target_id)
                summary = f"Updated request {target_id}"
                focus = None
                if "scripts" in update_fields:
                    focus = "test"
                elif "auth" in update_fields:
                    focus = "auth"
                open_target = {
                    "kind": "request",
                    "id": int(target_id),
                    "focus": focus,
                }
            elif verb == "rename":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                name = str(fields.get("name") or "").strip()
                if not name:
                    return mutate_obs("ok: false\nerror: name_required\n")
                CollectionService.rename_request(target_id, name)
                ids["request_id"] = int(target_id)
                summary = f"Renamed request to {name!r}"
                open_target = {"kind": "request", "id": int(target_id)}
            elif verb == "move":
                if target_id is None or collection_id is None:
                    return mutate_obs("ok: false\nerror: target_id_and_collection_id_required\n")
                CollectionService.move_request(target_id, collection_id)
                ids["request_id"] = int(target_id)
                summary = f"Moved request {target_id}"
                open_target = {"kind": "request", "id": int(target_id)}
            elif verb == "duplicate":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                duplicated = CollectionService.duplicate_request(target_id)
                ids["request_id"] = int(duplicated.id)
                summary = f"Duplicated request {target_id} → {duplicated.id}"
                open_target = {"kind": "request", "id": int(duplicated.id)}
            elif verb == "delete":
                if target_id is None:
                    return mutate_obs("ok: false\nerror: target_id_required\n")
                CollectionService.delete_request(target_id)
                ids["request_id"] = int(target_id)
                summary = f"Deleted request {target_id}"
            else:
                return mutate_obs(f"ok: false\nerror: unsupported_action\naction: {verb}\n")
        elif entity == "assertion_set":
            if verb != "update":
                return mutate_obs("ok: false\nerror: assertion_set_requires_update\n")
            if target_id is None:
                return mutate_obs("ok: false\nerror: target_id_required\n")
            assertions = fields.get("assertions")
            if not isinstance(assertions, list):
                return mutate_obs("ok: false\nerror: assertions_list_required\n")
            AssertionService.save_for_request(target_id, assertions)
            ids["request_id"] = int(target_id)
            summary = f"Replaced assertions on request {target_id}"
            open_target = {
                "kind": "request",
                "id": int(target_id),
                "focus": "assertions",
            }
        else:
            return mutate_obs(f"ok: false\nerror: unsupported_entity\nentity: {entity}\n")
    except Exception as exc:
        return mutate_obs(f"ok: false\nerror: {type(exc).__name__}\nmessage: {exc}\n")

    return _finish(
        mutation_id=mutation_id,
        verb=verb,
        entity=entity,
        ids=ids,
        summary=summary,
        warnings=warnings,
        open_after=open_after,
        open_target=open_target,
    )


__all__ = [
    "apply_collection_mutation",
    "filter_collection_fields",
]
