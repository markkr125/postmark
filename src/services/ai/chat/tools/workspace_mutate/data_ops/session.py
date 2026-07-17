"""Active environment, history, and script-version mutate ops."""

from __future__ import annotations

from typing import Any

from services.ai.chat.mutation.audit import append_mutation_audit
from services.ai.chat.mutation.bridge import OpenTargetDict, enqueue_mutation_event
from services.ai.chat.tools.workspace_mutate.common import (
    WorkspaceMutateObservation,
    mutate_obs,
)
from services.ai.chat.tools.workspace_mutate.data_ops.common import _finish


def _apply_active_environment(
    *,
    fields: dict[str, Any],
    mutation_id: str,
) -> WorkspaceMutateObservation:
    """Enqueue set/clear of the GUI active environment (no DB write)."""
    if "environment_id" not in fields:
        return mutate_obs("ok: false\nerror: environment_id_required\n")
    raw = fields.get("environment_id")
    ids: dict[str, int] = {}
    if raw is None:
        action = "clear"
        summary = "Cleared active environment"
    else:
        try:
            env_id = int(raw)
        except (TypeError, ValueError):
            return mutate_obs("ok: false\nerror: invalid_environment_id\n")
        if env_id <= 0:
            return mutate_obs("ok: false\nerror: invalid_environment_id\n")
        from services.environment_service import EnvironmentService

        env = EnvironmentService.get_environment(env_id)
        if env is None:
            return mutate_obs("ok: false\nerror: environment_not_found\n")
        ids["environment_id"] = env_id
        action = "set"
        summary = f"Set active environment {env.name!r}"
    enqueue_mutation_event(
        {
            "type": "mutated",
            "entity": "active_environment",
            "action": action,
            "ids": ids,
            "warnings": [],
        }
    )
    append_mutation_audit(
        {
            "mutation_id": mutation_id,
            "action": action,
            "entity": "active_environment",
            "ids": ids,
            "summary": summary,
        }
    )
    return mutate_obs(
        "\n".join(
            [
                "ok: true",
                f"mutation_id: {mutation_id}",
                f"summary: {summary}",
                f"action: {action}",
                "entity: active_environment",
                f"ids: {ids}",
            ]
        )
        + "\n"
    )


def _apply_history_entry_delete(
    *,
    target_id: int | None,
    mutation_id: str,
) -> WorkspaceMutateObservation:
    """Delete a request-history entry and enqueue UI refresh."""
    from services.request_history_service import RequestHistoryService

    if target_id is None:
        return mutate_obs("ok: false\nerror: target_id_required\n")
    ok = RequestHistoryService.delete_entry(int(target_id))
    if not ok:
        return mutate_obs("ok: false\nerror: history_entry_not_found\n")
    ids = {"history_entry_id": int(target_id)}
    summary = f"Deleted history entry {target_id}"
    return _finish(
        mutation_id=mutation_id,
        verb="delete",
        entity="history_entry",
        ids=ids,
        summary=summary,
        warnings=[],
        open_after=False,
        open_target=None,
    )


def _apply_script_version_restore(
    *,
    target_id: int | None,
    mutation_id: str,
    open_after: bool,
) -> WorkspaceMutateObservation:
    """Restore a script version snapshot into the live script body."""
    from services.collection_service import CollectionService
    from services.local_script_service import LocalScriptService
    from services.script_version_service import ScriptVersionService
    from services.scripting.context import normalize_events

    if target_id is None:
        return mutate_obs("ok: false\nerror: target_id_required\n")
    version = ScriptVersionService.get_version(int(target_id))
    if version is None:
        return mutate_obs("ok: false\nerror: script_version_not_found\n")
    content = str(version.get("content") or "")
    language = version.get("language")
    script_type = str(version.get("script_type") or "")
    local_id = version.get("local_script_id")
    request_id = version.get("request_id")
    collection_id = version.get("collection_id")
    ids: dict[str, int] = {"script_version_id": int(target_id)}
    open_target: OpenTargetDict | None = None
    summary = ""

    if isinstance(local_id, int) and local_id > 0:
        LocalScriptService.save_script_content(
            local_id,
            content,
            language=str(language) if language else None,
        )
        ids["local_script_id"] = local_id
        open_target = {"kind": "local_script", "id": local_id}
        summary = f"Restored local script #{local_id} from version {target_id}"
    elif isinstance(request_id, int) and request_id > 0:
        req = CollectionService.get_request(request_id)
        if req is None:
            return mutate_obs("ok: false\nerror: request_not_found\n")
        current = dict(req.scripts or req.events or {})
        if not isinstance(current, dict):
            current = {}
        key = "pre_request" if script_type == "pre_request" else "test"
        current[key] = content
        if language:
            lang_key = "pre_language" if key == "pre_request" else "test_language"
            current[lang_key] = str(language)
            if key == "pre_request":
                current["language"] = str(language)
        CollectionService.update_request(request_id, scripts=current)
        ids["request_id"] = request_id
        open_target = {
            "kind": "request",
            "id": request_id,
            "focus": "pre_request" if key == "pre_request" else "test",
        }
        summary = f"Restored request #{request_id} {key} from version {target_id}"
    elif isinstance(collection_id, int) and collection_id > 0:
        coll = CollectionService.get_collection(collection_id)
        if coll is None:
            return mutate_obs("ok: false\nerror: collection_not_found\n")
        current = dict(coll.events or {})
        if not isinstance(current, dict):
            current = {}
        # Preserve non-script metadata; normalize then set body keys.
        normalized = normalize_events(current)
        key = "pre_request" if script_type == "pre_request" else "test"
        current[key] = content
        for meta_key in ("pre_language", "test_language", "language", "debug"):
            if meta_key in current:
                continue
        if language:
            lang_key = "pre_language" if key == "pre_request" else "test_language"
            current[lang_key] = str(language)
            if key == "pre_request":
                current["language"] = str(language)
        # Keep other script body if present in normalized form.
        if key == "test" and "pre_request" not in current and "pre_request" in normalized:
            current["pre_request"] = normalized["pre_request"]
        if key == "pre_request" and "test" not in current and "test" in normalized:
            current["test"] = normalized["test"]
        CollectionService.update_collection(collection_id, events=current)
        ids["collection_id"] = collection_id
        open_target = {
            "kind": "collection",
            "id": collection_id,
            "focus": "pre_request" if key == "pre_request" else "test",
        }
        summary = f"Restored collection #{collection_id} {key} from version {target_id}"
    else:
        return mutate_obs("ok: false\nerror: script_version_has_no_owner\n")

    return _finish(
        mutation_id=mutation_id,
        verb="restore",
        entity="script_version",
        ids=ids,
        summary=summary,
        warnings=[],
        open_after=open_after,
        open_target=open_target,
    )
