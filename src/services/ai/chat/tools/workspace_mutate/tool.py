"""OpenHands tool — mutate Postmark workspace entities (collections, requests, …)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import Field
from rich.text import Text

from openhands.sdk.tool.tool import (
    Action,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)
from services.ai.chat.tools.workspace_mutate.collection_ops import (
    apply_collection_mutation,
    filter_collection_fields,
)
from services.ai.chat.tools.workspace_mutate.common import (
    WorkspaceMutateObservation,
    mutate_obs,
)
from services.ai.chat.tools.workspace_mutate.data_ops import (
    apply_data_mutation,
    filter_data_fields,
)
from services.ai.chat.tools.workspace_mutate.local_ops import (
    apply_local_mutation,
    filter_local_fields,
)

if TYPE_CHECKING:
    from openhands.sdk.conversation.base import BaseConversation

MutateActionName = Literal[
    "create",
    "update",
    "rename",
    "move",
    "duplicate",
    "delete",
    "restore",
]
MutateEntity = Literal[
    "collection",
    "request",
    "assertion_set",
    "local_script",
    "local_script_folder",
    "environment",
    "active_environment",
    "globals",
    "snippet",
    "saved_response",
    "history_entry",
    "script_version",
    "debug_metadata",
    "settings",
]

_COLLECTION_ENTITIES = frozenset({"collection", "request", "assertion_set"})
_LOCAL_ENTITIES = frozenset({"local_script", "local_script_folder"})
_DATA_ENTITIES = frozenset(
    {
        "environment",
        "active_environment",
        "globals",
        "snippet",
        "saved_response",
        "history_entry",
        "script_version",
    }
)


class WorkspaceMutateAction(Action):
    """Propose a workspace mutation (requires confirmation unless auto-approved)."""

    action: MutateActionName = Field(description="Mutation verb.")
    entity: MutateEntity = Field(description="Target entity type.")
    target_id: int | None = Field(
        default=None,
        description="Existing entity id for update/rename/move/delete/duplicate.",
    )
    parent_id: int | None = Field(
        default=None,
        description="Parent collection or local-script folder id for create/move.",
    )
    collection_id: int | None = Field(
        default=None,
        description="Collection id for create/move request.",
    )
    fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Writable fields (phase allowlist enforced).",
    )
    open_after: bool = Field(
        default=True,
        description="Open/focus the result in the UI after success.",
    )

    @property
    def visualize(self) -> Text:
        """Return Rich Text for SDK logs (Approve UI uses :meth:`human_preview`)."""
        content = Text()
        content.append("Workspace mutate: ", style="bold yellow")
        content.append(f"{self.action} {self.entity}", style="white")
        if self.target_id is not None:
            content.append(f" id={self.target_id}", style="dim")
        keys = sorted(self.fields.keys()) if self.fields else []
        if keys:
            content.append(f" fields={','.join(keys)}", style="dim")
        return content

    def human_preview(self) -> str:
        """Return a short human-readable detail line for Approve chrome."""
        fields = self.fields if isinstance(self.fields, dict) else {}
        name = str(fields.get("name") or "").strip()
        method = str(fields.get("method") or "").strip()
        url = str(fields.get("url") or "").strip()
        description = str(fields.get("description") or "").strip()
        category = str(fields.get("category") or "").strip()
        language = str(fields.get("language") or "").strip()

        if self.action == "create":
            if self.entity == "collection":
                return name or "New collection"
            if self.entity == "request":
                bits = [p for p in (method.upper() if method else "", name or url) if p]
                return " ".join(bits) if bits else "New request"
            if self.entity == "assertion_set":
                return name or "Replace assertions"
            if self.entity == "local_script":
                return name or "New local script"
            if self.entity == "local_script_folder":
                return name or "New script folder"
            if self.entity == "environment":
                return name or "New environment"
            if self.entity == "snippet":
                return name or "New snippet"
            if self.entity == "saved_response":
                return name or "New saved example"
        if self.action == "rename" and name:
            if self.entity == "snippet" and category and self.target_id is None:
                return f"{category} → {name}"
            return name
        if self.action == "update":
            if self.entity == "globals":
                return "Update global variables"
            if self.entity == "active_environment":
                raw_env = fields.get("environment_id")
                if raw_env is None:
                    return "Clear active environment"
                try:
                    from services.environment_service import EnvironmentService

                    env = EnvironmentService.get_environment(int(raw_env))
                    if env is not None and str(env.name or "").strip():
                        return f"Activate {env.name}"
                except Exception:
                    pass
                return f"Activate environment #{raw_env}"
            if name:
                return name
            if method or url:
                bits = [p for p in (method.upper() if method else "", url) if p]
                return " ".join(bits)
            if description:
                return description[:80] + ("…" if len(description) > 80 else "")
            if self.entity == "local_script" and "content" in fields:
                return f"Update script #{self.target_id}" if self.target_id else "Update script"
            keys = sorted(str(k) for k in fields)
            if keys:
                return f"Update {', '.join(keys[:4])}"
        if self.action == "delete":
            if self.entity == "snippet" and category and language and self.target_id is None:
                return f"Delete {category!r} ({language})"
            if self.entity == "history_entry" and self.target_id is not None:
                return f"History entry #{self.target_id}"
            if self.target_id is not None:
                return f"{self.entity} #{self.target_id}"
            return f"Delete {self.entity}"
        if self.action == "restore":
            if self.target_id is not None:
                return f"Restore script version #{self.target_id}"
            return "Restore script version"
        if self.action == "duplicate":
            if self.entity == "saved_response":
                return f"Saved example #{self.target_id}" if self.target_id else "Duplicate example"
            return name or (f"Request #{self.target_id}" if self.target_id else "Duplicate request")
        if self.action == "move":
            if self.target_id is not None:
                return f"{self.entity} #{self.target_id}"
            return f"Move {self.entity}"
        if name:
            return name
        if self.target_id is not None:
            return f"{self.entity} #{self.target_id}"
        return f"{self.action} {self.entity}"


MUTATE_DESCRIPTION = """Create, update, rename, move, duplicate, delete, or restore workspace entities.

Requires Agent mode. Risky kinds pause for user Approve unless auto-approved.
Destructive actions pause for user Approve unless the kind is auto-approved.

Entities:
- collection, request, assertion_set (assertion_set = replace all rows for a request)
- local_script, local_script_folder
- environment, active_environment (update: set environment_id or null to clear), globals
- snippet, saved_response
- history_entry (delete only)
- script_version (restore only; merges into request scripts / collection events / local content)
- debug_metadata (update: breakpoints/watches via merge APIs; fields.target_kind + target_id + per_type)
- settings (update: allowlisted prefs only — never AI credentials)

duplicate is request-only and saved_response-only (not collections).
Collection title: action=rename with fields.name, or action=update with fields.name (rename service).
Collection update other fields: description, variables, auth, events (scripts gate).
Request create may include auth in fields; create_request has no auth kwarg — auth is applied via update after create.
Collection scripts live in fields.events (pre_request/test/languages), not scripts.
Scripts on requests only when writing tests (allow_scripts gate).
Binary body_mode + body path must be under user-data / project data / temp.

Secrets policy: write structure and non-secret values only. Secret-typed or
credential-like keys must be empty or a single ``{{var}}`` placeholder — raw
tokens/passwords are rejected. Observations never echo raw secrets."""


def _filter_fields(
    entity: str,
    action: str,
    fields: dict[str, Any],
    *,
    allow_scripts: bool,
) -> tuple[dict[str, Any] | None, WorkspaceMutateObservation | None]:
    """Return filtered fields or an error observation."""
    if entity == "debug_metadata":
        if not allow_scripts:
            return None, mutate_obs("ok: false\nerror: scripts_not_allowed\n")
        from services.ai.chat.tools.workspace_mutate.debug_ops import (
            filter_debug_metadata_fields,
        )

        return filter_debug_metadata_fields(action, fields)
    if entity == "settings":
        from services.ai.chat.tools.workspace_mutate.settings_ops import (
            filter_settings_fields,
        )

        return filter_settings_fields(action, fields)
    if entity in _COLLECTION_ENTITIES:
        return filter_collection_fields(entity, action, fields, allow_scripts=allow_scripts)
    if entity in _LOCAL_ENTITIES:
        return filter_local_fields(entity, action, fields)
    if entity in _DATA_ENTITIES:
        return filter_data_fields(entity, action, fields)
    return None, mutate_obs(f"ok: false\nerror: unsupported_entity\nentity: {entity}\n")


def _apply_mutation(
    action: WorkspaceMutateAction,
    *,
    allow_scripts: bool = True,
) -> WorkspaceMutateObservation:
    """Apply the mutation via the appropriate service layer."""
    verb = action.action
    entity = action.entity
    fields, err = _filter_fields(
        entity, verb, dict(action.fields or {}), allow_scripts=allow_scripts
    )
    if err is not None:
        return err
    assert fields is not None

    if entity == "debug_metadata":
        from services.ai.chat.tools.workspace_mutate.debug_ops import (
            apply_debug_metadata_mutation,
        )

        return apply_debug_metadata_mutation(
            verb=verb,
            fields=fields,
            open_after=action.open_after,
        )
    if entity == "settings":
        from services.ai.chat.tools.workspace_mutate.settings_ops import (
            apply_settings_mutation,
        )

        return apply_settings_mutation(fields=fields)
    if entity in _COLLECTION_ENTITIES:
        return apply_collection_mutation(
            verb=verb,
            entity=entity,
            target_id=action.target_id,
            parent_id=action.parent_id,
            collection_id=action.collection_id,
            fields=fields,
            open_after=action.open_after,
            allow_scripts=allow_scripts,
        )
    if entity in _LOCAL_ENTITIES:
        return apply_local_mutation(
            verb=verb,
            entity=entity,
            target_id=action.target_id,
            parent_id=action.parent_id,
            fields=fields,
            open_after=action.open_after,
        )
    if entity in _DATA_ENTITIES:
        return apply_data_mutation(
            verb=verb,
            entity=entity,
            target_id=action.target_id,
            collection_id=action.collection_id,
            fields=fields,
            open_after=action.open_after,
        )
    return mutate_obs(f"ok: false\nerror: unsupported_entity\nentity: {entity}\n")


class WorkspaceMutateExecutor(ToolExecutor):
    """Apply workspace mutations after SDK confirmation."""

    def __call__(
        self,
        action: WorkspaceMutateAction,
        _conversation: BaseConversation | None = None,
    ) -> WorkspaceMutateObservation:
        """Execute the mutation."""
        return _apply_mutation(action, allow_scripts=True)


class PostmarkWorkspaceMutateTool(
    ToolDefinition[WorkspaceMutateAction, WorkspaceMutateObservation]
):
    """Postmark workspace mutate tool."""

    @classmethod
    def create(
        cls,
        conv_state: object | None = None,
        **params: object,
    ) -> Sequence[Self]:
        """Create the mutate tool instance."""
        del conv_state
        if params:
            raise ValueError("postmark_workspace_mutate does not accept parameters")
        return [
            cls(
                description=MUTATE_DESCRIPTION,
                action_type=WorkspaceMutateAction,
                observation_type=WorkspaceMutateObservation,
                executor=WorkspaceMutateExecutor(),
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
            )
        ]


def register_workspace_mutate_tool() -> None:
    """Register ``postmark_workspace_mutate`` with Postmark and OpenHands."""
    from services.ai.chat.tool_registry import register_postmark_tool

    register_postmark_tool("postmark_workspace_mutate", PostmarkWorkspaceMutateTool)
