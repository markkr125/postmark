"""Environment, globals, auth, snippet, and session mutate ops."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from services.ai.chat.tools.workspace_mutate.common import (
    WorkspaceMutateObservation,
    mutate_obs,
)
from services.ai.chat.tools.workspace_mutate.data_ops.common import filter_data_fields
from services.ai.chat.tools.workspace_mutate.data_ops.env import (
    apply_auth_update,
    apply_collection_variables,
    _apply_environment,
    _apply_globals,
)
from services.ai.chat.tools.workspace_mutate.data_ops.media import (
    _apply_saved_response,
    _apply_snippet,
)
from services.ai.chat.tools.workspace_mutate.data_ops.session import (
    _apply_active_environment,
    _apply_history_entry_delete,
    _apply_import,
    _apply_script_version_restore,
)

__all__ = [
    "apply_auth_update",
    "apply_collection_variables",
    "apply_data_mutation",
    "filter_data_fields",
]


def apply_data_mutation(
    *,
    verb: str,
    entity: str,
    target_id: int | None,
    collection_id: int | None,
    fields: dict[str, Any],
    open_after: bool,
) -> WorkspaceMutateObservation:
    """Apply environment / globals / snippet / saved_response mutations."""
    mutation_id = uuid4().hex[:12]

    try:
        if entity == "environment":
            return _apply_environment(
                verb=verb,
                target_id=target_id,
                fields=fields,
                mutation_id=mutation_id,
                open_after=open_after,
            )
        if entity == "active_environment":
            return _apply_active_environment(
                fields=fields,
                mutation_id=mutation_id,
            )
        if entity == "history_entry":
            return _apply_history_entry_delete(
                target_id=target_id,
                mutation_id=mutation_id,
            )
        if entity == "import":
            return _apply_import(
                fields=fields,
                mutation_id=mutation_id,
                open_after=open_after,
            )
        if entity == "script_version":
            return _apply_script_version_restore(
                target_id=target_id,
                mutation_id=mutation_id,
                open_after=open_after,
            )
        if entity == "globals":
            return _apply_globals(
                fields=fields,
                mutation_id=mutation_id,
                open_after=open_after,
            )
        if entity == "snippet":
            return _apply_snippet(
                verb=verb,
                target_id=target_id,
                fields=fields,
                mutation_id=mutation_id,
                open_after=open_after,
            )
        if entity == "saved_response":
            return _apply_saved_response(
                verb=verb,
                target_id=target_id,
                collection_id=collection_id,
                fields=fields,
                mutation_id=mutation_id,
                open_after=open_after,
            )
        return mutate_obs(f"ok: false\nerror: unsupported_entity\nentity: {entity}\n")
    except Exception as exc:
        return mutate_obs(f"ok: false\nerror: {type(exc).__name__}\nmessage: {exc}\n")
