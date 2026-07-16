"""OpenHands tool — execute Postmark sends and script runs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import Field
from rich.text import Text

from openhands.sdk.tool.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)

if TYPE_CHECKING:
    from openhands.sdk.conversation.base import BaseConversation

ExecuteOperation = Literal[
    "send_request",
    "send_draft",
    "replay_history",
    "run_scripts",
    "run_local_script",
    "run_collection",
    "run_iterations",
    "fetch_graphql_schema",
    "generate_snippet",
    "export_workspace_artifact",
    "oauth_get_token",
]

ArtifactKind = Literal[
    "test_results_json",
    "test_results_junit",
    "run_csv",
    "run_json",
]


class WorkspaceExecuteAction(Action):
    """Propose a workspace execution (send / run scripts / fetch / export)."""

    operation: ExecuteOperation = Field(description="Execution verb.")
    request_id: int | None = Field(default=None, description="Saved request id.")
    collection_id: int | None = Field(default=None, description="Collection id for run_collection.")
    request_ids: list[int] | None = Field(
        default=None,
        description="Optional subset of request ids for run_collection (None = all).",
    )
    local_script_id: int | None = Field(
        default=None, description="Local script id for run_local_script."
    )
    history_entry_id: int | None = Field(
        default=None, description="History entry id for replay / export."
    )
    run_history_id: int | None = Field(
        default=None, description="Run history id for collection-run export."
    )
    environment_id: int | None = Field(default=None, description="Environment id override.")
    persist_globals: bool = Field(
        default=False,
        description="Persist script globals after run (default false).",
    )
    record_history: bool = Field(
        default=True,
        description="Record agent send in request history (default true).",
    )
    include_scripts: bool = Field(
        default=True,
        description="Run pre-request/test scripts on send (default true).",
    )
    scripts_enabled: bool = Field(
        default=True,
        description="For run_collection: run scripts during the run (default true).",
    )
    script_phase: Literal["pre", "test", "both"] = Field(
        default="both",
        description="For run_scripts: which phase to run.",
    )
    iterations: int = Field(
        default=1,
        description="For run_collection: iteration count (default 1).",
    )
    delay_ms: int = Field(
        default=0,
        description="For run_collection: delay between requests in ms.",
    )
    iteration_data: list[dict[str, Any]] | None = Field(
        default=None,
        description="Data rows for run_collection / run_iterations.",
    )
    iteration_count: int | None = Field(
        default=None,
        description="For run_iterations: override iteration count (default = len(data)).",
    )
    mock_response: dict[str, Any] | None = Field(
        default=None,
        description="For run_iterations: optional mock response (default empty 200).",
    )
    url: str | None = Field(
        default=None,
        description="For fetch_graphql_schema: explicit GraphQL endpoint URL.",
    )
    search: str | None = Field(
        default=None,
        description="For fetch_graphql_schema: optional type-name filter.",
    )
    language: str | None = Field(
        default=None,
        description="For generate_snippet: snippet language id.",
    )
    draft: dict[str, Any] | None = Field(
        default=None,
        description="For generate_snippet: optional inline request fields.",
    )
    artifact_kind: ArtifactKind | None = Field(
        default=None,
        description="For export_workspace_artifact: export format kind.",
    )
    write_path: str | None = Field(
        default=None,
        description="Optional allowlisted path to write export content.",
    )
    bound_var: str | None = Field(
        default=None,
        description="For oauth_get_token: environment variable name to bind the token.",
    )
    oauth_config: dict[str, Any] | None = Field(
        default=None,
        description="For oauth_get_token: inline OAuth2 config (no browser grants in v1).",
    )
    update_auth_placeholder: bool = Field(
        default=True,
        description="For oauth_get_token: set request auth accessToken to {{bound_var}}.",
    )

    @property
    def visualize(self) -> Text:
        """Return Rich Text for SDK logs (Approve UI uses :meth:`human_preview`)."""
        from services.ai.chat.execution.preview_url import resolve_execute_preview_url

        content = Text()
        content.append("Workspace execute: ", style="bold magenta")
        content.append(self.operation, style="white")
        if self.request_id is not None:
            content.append(f" request_id={self.request_id}", style="dim")
        if self.history_entry_id is not None:
            content.append(f" history_entry_id={self.history_entry_id}", style="dim")
        url = resolve_execute_preview_url(self)
        if url:
            content.append(" url=", style="dim")
            content.append(url, style="cyan")
        return content

    def preview_url(self) -> str | None:
        """Return the redacted destination URL for Approve chrome, if any."""
        from services.ai.chat.execution.preview_url import resolve_execute_preview_url

        return resolve_execute_preview_url(self)

    def human_preview(self) -> str:
        """Return a short human-readable detail line for Approve chrome."""
        url = self.preview_url()
        if self.operation == "send_request":
            method = _saved_request_method(self.request_id)
            if url and method:
                return f"{method} {url}"
            if url:
                return url
            if self.request_id is not None:
                return f"Request #{self.request_id}"
            return "Send saved request"
        if self.operation == "send_draft":
            return url or "Open tab draft"
        if self.operation == "replay_history":
            if url:
                return url
            if self.history_entry_id is not None:
                return f"History #{self.history_entry_id}"
            return "Replay history send"
        if self.operation == "run_scripts":
            phase = self.script_phase or "both"
            if self.request_id is not None:
                return f"Request #{self.request_id} · {phase}"
            return f"Run scripts ({phase})"
        if self.operation == "run_local_script":
            if self.local_script_id is not None:
                return f"Local script #{self.local_script_id}"
            return "Run local script"
        if self.operation == "run_collection":
            if self.collection_id is not None:
                n = len(self.request_ids) if self.request_ids else None
                if n is not None:
                    return f"Collection #{self.collection_id} · {n} request(s)"
                return f"Collection #{self.collection_id}"
            return "Run collection"
        if self.operation == "run_iterations":
            rows = len(self.iteration_data or [])
            if self.request_id is not None:
                return f"Request #{self.request_id} · {rows} iteration(s)"
            return f"Run iterations ({rows})"
        if self.operation == "fetch_graphql_schema":
            if url:
                return f"Fetch schema {url}"
            if self.request_id is not None:
                return f"Fetch schema · request #{self.request_id}"
            return "Fetch GraphQL schema"
        if self.operation == "generate_snippet":
            lang = self.language or "snippet"
            if self.request_id is not None:
                return f"Generate {lang} · request #{self.request_id}"
            return f"Generate {lang}"
        if self.operation == "export_workspace_artifact":
            kind = self.artifact_kind or "artifact"
            return f"Export {kind}"
        if self.operation == "oauth_get_token":
            var = (self.bound_var or "oauth_access_token").strip() or "oauth_access_token"
            target = "{{" + var + "}}"
            if self.request_id is not None:
                return f"OAuth Get Token · request #{self.request_id} → {target}"
            return f"OAuth Get Token → {target}"
        return url or self.operation


def _saved_request_method(request_id: int | None) -> str | None:
    """Return the uppercase HTTP method for a saved request, if known."""
    if request_id is None:
        return None
    try:
        from services.collection_service import CollectionService

        req = CollectionService.get_request(request_id)
        if req is None:
            return None
        method = str(getattr(req, "method", "") or "").strip().upper()
        return method or None
    except Exception:
        return None


class WorkspaceExecuteObservation(Observation):
    """Observation after a workspace execution attempt."""


EXECUTE_DESCRIPTION = """Send HTTP requests or run scripts in the Postmark workspace.

Requires Agent mode. Pauses for user Approve unless the operation kind is auto-approved.

operations:
- send_request: send a saved request by request_id (same path as the Send button)
- send_draft: send the dirty open-tab draft for the current session snapshot
- replay_history: replay a history entry by history_entry_id
- run_scripts: run pre/test/both scripts on a saved request without HTTP (optional)
- run_local_script: run a local script tab by local_script_id (no HTTP)
- run_collection: run a folder checklist (collection_id; optional request_ids, iterations,
  delay_ms, iteration_data, scripts_enabled). Persists RunHistory with source=agent.
- run_iterations: run request test scripts once per iteration_data row (mock response
  unless mock_response is provided). Agent must supply iteration_data arrays (no file picker).
- fetch_graphql_schema: introspect a GraphQL endpoint (request_id and/or url); returns a
  truncated summary (never the full raw schema).
- generate_snippet: generate code for a request (language); auth secrets stay as {{var}}.
- export_workspace_artifact: export test results / run CSV|JSON from history_entry_id or
  run_history_id (content in observation; optional allowlisted write_path).
- oauth_get_token: exchange OAuth credentials (client_credentials / password only); binds
  the token to an environment {{var}} — the token value never appears in the observation.

Binary body_mode sends file bytes (path must be under user-data / project data / temp).
record_history defaults true. persist_globals defaults false.
Approve pending text shows the resolved URL for send operations."""


class WorkspaceExecuteExecutor(ToolExecutor):
    """Run sends/scripts after SDK confirmation."""

    def __call__(
        self,
        action: WorkspaceExecuteAction,
        _conversation: BaseConversation | None = None,
    ) -> WorkspaceExecuteObservation:
        """Execute the operation."""
        return _execute(action)


def _execute(action: WorkspaceExecuteAction) -> WorkspaceExecuteObservation:
    """Dispatch execute (compat alias for tests + executor)."""
    from services.ai.chat.tools.workspace_execute.dispatch import (
        execute_workspace_action,
    )

    return execute_workspace_action(action)


class PostmarkWorkspaceExecuteTool(
    ToolDefinition[WorkspaceExecuteAction, WorkspaceExecuteObservation]
):
    """Postmark workspace execute tool."""

    @classmethod
    def create(
        cls,
        conv_state: object | None = None,
        **params: object,
    ) -> Sequence[Self]:
        """Create the execute tool instance."""
        del conv_state
        if params:
            raise ValueError("postmark_workspace_execute does not accept parameters")
        return [
            cls(
                description=EXECUTE_DESCRIPTION,
                action_type=WorkspaceExecuteAction,
                observation_type=WorkspaceExecuteObservation,
                executor=WorkspaceExecuteExecutor(),
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
        ]


def register_workspace_execute_tool() -> None:
    """Register ``postmark_workspace_execute`` with Postmark and OpenHands."""
    from services.ai.chat.tool_registry import register_postmark_tool

    register_postmark_tool("postmark_workspace_execute", PostmarkWorkspaceExecuteTool)
