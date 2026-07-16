"""Breakpoint / watch metadata mutations via merge_*_debug APIs."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from services.ai.chat.mutation.audit import append_mutation_audit
from services.ai.chat.mutation.bridge import OpenTargetDict, enqueue_mutation_event
from services.ai.chat.tools.workspace_mutate.common import (
    WorkspaceMutateObservation,
    mutate_obs,
)
from services.scripting.debug_script_metadata import (
    SCRIPT_TYPE_PRE,
    SCRIPT_TYPE_TEST,
    DebugScriptSlice,
    parse_from_local_metadata,
    slice_to_local_metadata,
)


def filter_debug_metadata_fields(
    action: str,
    fields: dict[str, Any],
) -> tuple[dict[str, Any] | None, WorkspaceMutateObservation | None]:
    """Validate debug_metadata update fields."""
    if action not in {"update", "replace"}:
        return None, mutate_obs(f"ok: false\nerror: unsupported_action\naction: {action}\n")
    target_kind = str(fields.get("target_kind") or "").strip()
    if target_kind not in {"request", "collection", "local_script"}:
        return None, mutate_obs("ok: false\nerror: invalid_target_kind\n")
    target_id = fields.get("target_id")
    if not isinstance(target_id, int) or target_id <= 0:
        return None, mutate_obs("ok: false\nerror: target_id_required\n")
    cleaned = {
        "target_kind": target_kind,
        "target_id": int(target_id),
    }
    if target_kind == "local_script":
        # Flat slice
        slice_raw = fields.get("per_type") or fields.get("slice") or fields
        if not isinstance(slice_raw, dict):
            return None, mutate_obs("ok: false\nerror: invalid_debug_slice\n")
        # Accept either flat breakpoints/watches or nested under a dummy key.
        if "breakpoints" in slice_raw or "watches" in slice_raw:
            cleaned["slice"] = {
                "breakpoints": slice_raw.get("breakpoints") or [],
                "watches": slice_raw.get("watches") or [],
            }
        else:
            return None, mutate_obs("ok: false\nerror: breakpoints_or_watches_required\n")
    else:
        per_type = fields.get("per_type")
        if not isinstance(per_type, dict):
            return None, mutate_obs("ok: false\nerror: per_type_required\n")
        cleaned["per_type"] = per_type
    return cleaned, None


def apply_debug_metadata_mutation(
    *,
    verb: str,
    fields: dict[str, Any],
    open_after: bool,
) -> WorkspaceMutateObservation:
    """Merge breakpoints/watches without touching script bodies."""
    del verb  # already filtered to update/replace
    from services.collection_service import CollectionService
    from services.local_script_service import LocalScriptService
    from services.scripting.debug_script_metadata import (
        merge_debug_into_scripts_dict,
        truncate_condition,
    )

    target_kind = str(fields["target_kind"])
    target_id = int(fields["target_id"])
    mutation_id = uuid4().hex[:12]
    open_target: OpenTargetDict | None = None
    focus: str | None = None

    try:
        if target_kind == "local_script":
            raw_slice = fields.get("slice") or {}
            bps = []
            for item in raw_slice.get("breakpoints") or []:
                if not isinstance(item, dict):
                    continue
                line = item.get("line")
                if not isinstance(line, int) or line < 0:
                    continue
                cond = item.get("condition")
                cond = truncate_condition(cond) if isinstance(cond, str) else None
                bps.append({"line": line, "condition": cond})
            watches = [str(w).strip() for w in (raw_slice.get("watches") or []) if str(w).strip()]
            slice_data = DebugScriptSlice(breakpoints=bps, watches=watches)  # type: ignore[typeddict-item]
            # Validate via parser round-trip.
            parsed = parse_from_local_metadata(slice_to_local_metadata(slice_data))
            LocalScriptService.merge_debug_metadata(
                target_id,
                slice_to_local_metadata(parsed),
            )
            summary = f"Updated debug metadata for local script #{target_id}"
            open_target = {"kind": "local_script", "id": target_id}
        else:
            per_type_raw = fields.get("per_type") or {}
            per_type: dict[str, DebugScriptSlice] = {
                SCRIPT_TYPE_PRE: DebugScriptSlice(breakpoints=[], watches=[]),
                SCRIPT_TYPE_TEST: DebugScriptSlice(breakpoints=[], watches=[]),
            }
            for st in (SCRIPT_TYPE_PRE, SCRIPT_TYPE_TEST):
                raw = per_type_raw.get(st)
                if not isinstance(raw, dict):
                    continue
                bps = []
                for item in raw.get("breakpoints") or []:
                    if not isinstance(item, dict):
                        continue
                    line = item.get("line")
                    if not isinstance(line, int) or line < 0:
                        continue
                    cond = item.get("condition")
                    cond = truncate_condition(cond) if isinstance(cond, str) else None
                    bps.append({"line": line, "condition": cond})
                watches = [str(w).strip() for w in (raw.get("watches") or []) if str(w).strip()]
                per_type[st] = DebugScriptSlice(breakpoints=bps, watches=watches)  # type: ignore[typeddict-item]
                if bps or watches:
                    focus = st

            if target_kind == "request":
                req = CollectionService.get_request(target_id)
                if req is None:
                    return mutate_obs("ok: false\nerror: request_not_found\n")
                existing = dict(req.scripts) if isinstance(req.scripts, dict) else {}
                # Build debug blob only — merge API replaces scripts["debug"].
                debug_blob = merge_debug_into_scripts_dict({}, per_type).get("debug") or {}
                # Preserve other debug keys not in per_type if empty replacement intended.
                CollectionService.merge_request_scripts_debug(target_id, debug_blob)
                # Verify script bodies intact via parse.
                del existing
                summary = f"Updated debug metadata for request #{target_id}"
                open_target = {
                    "kind": "request",
                    "id": target_id,
                    "focus": focus or "test",
                }
            else:
                coll = CollectionService.get_collection(target_id)
                if coll is None:
                    return mutate_obs("ok: false\nerror: collection_not_found\n")
                debug_blob = merge_debug_into_scripts_dict({}, per_type).get("debug") or {}
                CollectionService.merge_collection_events_debug(target_id, debug_blob)
                summary = f"Updated debug metadata for collection #{target_id}"
                open_target = {
                    "kind": "collection",
                    "id": target_id,
                    "focus": focus or "test",
                }

        ids = {f"{target_kind}_id": target_id}
        if open_after and open_target is not None:
            enqueue_mutation_event({"type": "open_target", "open_target": open_target})
        enqueue_mutation_event(
            {
                "type": "mutated",
                "entity": "debug_metadata",
                "action": "update",
                "ids": ids,
                "payload": {"summary": summary},
            }
        )
        append_mutation_audit(
            {
                "mutation_id": mutation_id,
                "entity": "debug_metadata",
                "action": "update",
                "ids": ids,
                "summary": summary,
            }
        )
        return mutate_obs(
            "ok: true\n"
            f"mutation_id: {mutation_id}\n"
            f"entity: debug_metadata\n"
            f"action: update\n"
            f"summary: {summary}\n"
            f"ids: {ids}\n"
        )
    except Exception as exc:
        return mutate_obs(f"ok: false\nerror: {type(exc).__name__}\nmessage: {exc}\n")
