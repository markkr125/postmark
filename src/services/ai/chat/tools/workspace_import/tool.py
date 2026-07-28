"""OpenHands tool — import collections from OpenAPI, WSDL, Postman, cURL, URL, or file."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Self
from uuid import uuid4

from pydantic import Field, model_validator
from rich.text import Text

from openhands.sdk.tool.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)
from services.ai.chat.mutation.claim_guard import observation_indicates_write
from services.ai.chat.tools.workspace_import.apply import apply_workspace_import
from services.ai.chat.tools.workspace_import.turn_guard import (
    import_source_key,
    prior_import_result,
    record_import_result,
)
from services.ai.chat.workspace_snapshot import resolve_workspace_session_id

if TYPE_CHECKING:
    from openhands.sdk.conversation.base import BaseConversation

IMPORT_TOOL_NAME = "postmark_import"

IMPORT_DESCRIPTION = """Import collections and environments into the Postmark workspace.

Supported sources: OpenAPI 3 / Swagger 2 (JSON or YAML), WSDL 1.1, Postman
collection/environment JSON, cURL, or any of those via URL or local path.

Pass exactly one of:
- ``url`` — http(s) URL of a spec or export
- ``path`` — local file or folder path
- ``text`` — pasted body
- ``curl`` — a cURL command string

Optional:
- ``collection_name_suffix`` — append text to every imported root collection
  name during this same import (for example ``10`` produces
  ``Hotel Booking API 10``). Use this instead of importing and renaming in
  separate calls. One successful call completes the import; never call this
  tool twice for the same source in one user turn.

Requires Agent mode. Pauses for user Approve unless Import workspace is auto-approved.

Examples:
- Make a collection from https://example.com/openapi.yaml → url=https://example.com/openapi.yaml
- Import this WSDL from /tmp/service.wsdl → path=/tmp/service.wsdl
- Import this cURL → curl=<command>
"""


class WorkspaceImportAction(Action):
    """Propose a workspace import (requires confirmation unless auto-approved)."""

    url: str | None = Field(
        default=None,
        description="http(s) URL of an OpenAPI/Swagger, WSDL, Postman, or other supported export.",
    )
    path: str | None = Field(
        default=None,
        description="Local file or folder path to import.",
    )
    text: str | None = Field(
        default=None,
        description="Pasted OpenAPI/WSDL/Postman/raw body to import.",
    )
    curl: str | None = Field(
        default=None,
        description="cURL command string to import as a request/collection.",
    )
    collection_name_suffix: str | None = Field(
        default=None,
        description=(
            "Optional text appended with one separating space to each imported root "
            "collection name in this same operation. Example: '10' produces "
            "'Hotel Booking API 10'. Do not re-import to rename."
        ),
        max_length=200,
    )

    @model_validator(mode="after")
    def _exactly_one_source(self) -> Self:
        """Require exactly one of url | path | text | curl."""
        present = [
            name
            for name, value in (
                ("url", self.url),
                ("path", self.path),
                ("text", self.text),
                ("curl", self.curl),
            )
            if value is not None and str(value).strip()
        ]
        if len(present) != 1:
            msg = "Provide exactly one of: url, path, text, curl"
            raise ValueError(msg)
        return self

    def source_fields(self) -> dict[str, str]:
        """Return the single non-empty source as a fields dict for ImportService."""
        if self.url is not None and str(self.url).strip():
            return {"url": str(self.url).strip()}
        if self.path is not None and str(self.path).strip():
            return {"path": str(self.path).strip()}
        if self.text is not None and str(self.text).strip():
            return {"text": str(self.text)}
        if self.curl is not None and str(self.curl).strip():
            return {"curl": str(self.curl)}
        return {}

    @property
    def visualize(self) -> Text:
        """Return Rich Text for SDK logs (Approve UI uses :meth:`human_preview`)."""
        content = Text()
        content.append("Import: ", style="bold yellow")
        content.append(self.human_preview(), style="white")
        return content

    def human_preview(self) -> str:
        """Return a short human-readable detail line for Approve chrome."""
        fields = self.source_fields()
        suffix = str(self.collection_name_suffix or "").strip()
        suffix_note = f"; append {suffix!r} to root name" if suffix else ""
        if "curl" in fields:
            return f"Import from cURL{suffix_note}"
        if "url" in fields:
            url = fields["url"]
            if len(url) > 80:
                return f"Import {url[:77]}…{suffix_note}"
            return f"Import {url}{suffix_note}"
        if "path" in fields:
            return f"Import {fields['path']}{suffix_note}"
        return f"Import workspace{suffix_note}"


class WorkspaceImportObservation(Observation):
    """Observation after an import attempt."""


class WorkspaceImportExecutor(ToolExecutor):
    """Execute an approved workspace import via ImportService."""

    def __call__(
        self,
        action: WorkspaceImportAction,
        _conversation: BaseConversation | None = None,
    ) -> WorkspaceImportObservation:
        """Run ImportService and return observation text."""
        fields = action.source_fields()
        session_id = _conversation_session_id(_conversation)
        source_key = import_source_key(fields)
        prior = prior_import_result(session_id, source_key)
        if prior is not None:
            duplicate_result = (
                prior.rstrip()
                + "\nduplicate_skipped: true\n"
                + "next_step: This source was already imported during the current user "
                + "turn. Do not call the import tool again; use the imported_collections "
                + "and collection_links above.\n"
            )
            return WorkspaceImportObservation.from_text(duplicate_result)
        mutation_id = uuid4().hex[:12]
        result = apply_workspace_import(
            fields=fields,
            mutation_id=mutation_id,
            collection_name_suffix=str(action.collection_name_suffix or ""),
        )
        if observation_indicates_write(result.text):
            record_import_result(session_id, source_key, result.text)
        return WorkspaceImportObservation.from_text(result.text)


def _conversation_session_id(conversation: BaseConversation | None) -> str:
    """Return the parent Postmark session id for per-turn duplicate guards."""
    if conversation is None:
        return ""
    state = conversation.state
    return resolve_workspace_session_id(
        str(state.id),
        persistence_dir=getattr(state, "persistence_dir", None),
    )


class PostmarkWorkspaceImportTool(
    ToolDefinition[WorkspaceImportAction, WorkspaceImportObservation]
):
    """Postmark workspace import tool (OpenAPI / WSDL / Postman / cURL)."""

    @classmethod
    def create(
        cls,
        conv_state: object | None = None,
        **params: object,
    ) -> Sequence[Self]:
        """Create a single import tool instance.

        ``conv_state`` is passed by the OpenHands tool registry; keep the name
        so ``create(conv_state=...)`` binds here instead of ``**params``.
        """
        del conv_state
        if params:
            msg = f"{IMPORT_TOOL_NAME} does not accept parameters"
            raise ValueError(msg)
        return [
            cls(
                description=IMPORT_DESCRIPTION,
                action_type=WorkspaceImportAction,
                observation_type=WorkspaceImportObservation,
                executor=WorkspaceImportExecutor(),
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
        ]


def register_workspace_import_tool() -> None:
    """Register ``postmark_import`` with Postmark and OpenHands."""
    from services.ai.chat.tool_registry import register_postmark_tool

    register_postmark_tool(IMPORT_TOOL_NAME, PostmarkWorkspaceImportTool)
