"""OpenHands tool — build a collection from bounded request batches."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.text import Text

from openhands.sdk.tool.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)
from services.ai.chat.tools.collection_draft import ops
from services.ai.chat.tools.collection_draft.config import draft_script_language
from services.ai.chat.workspace_snapshot import resolve_workspace_session_id

if TYPE_CHECKING:
    from openhands.sdk.conversation.base import BaseConversation

COLLECTION_DRAFT_TOOL_NAME = "postmark_collection_draft"

DraftOperation = Literal["start", "add_requests", "status", "finish", "discard"]


def _collection_draft_description(script_language: str) -> str:
    """Return the tool description with the configured script language interpolated."""
    return f"""Build a Postmark collection from bounded batches of requests, then create it in one approved step. Use this for documents (PDF/DOCX) or any source that has no machine-readable spec.

Workflow:
1. ``operation=start`` with ``name``, and optional ``source``, ``variables``, markdown ``description`` (document front-matter: authentication, endpoint conventions, required headers, response/error vocabulary, timeouts), plus collection-level ``pre_script`` / ``test_script`` for shared mechanical contracts.
2. ``operation=add_requests`` with up to 20 fully defined endpoints. Each entry takes ``name``, ``method``, ``url`` (``path`` also accepted), and optional ``folder``, ``headers`` (object or key/value rows), ``params`` (query-string rows with per-parameter ``description``), ``body``, markdown ``description`` (endpoint prose + parameter tables for body fields), ``pre_script``, ``test_script``. Send JSON bodies as objects, NOT escaped JSON strings. Use one batch per document chunk. Do not add endpoints merely named in a table of contents.
3. ``operation=status`` at any time to see what the draft already contains.
4. ``operation=finish`` to create the collection. This is the only step that writes and asks for Approve. It returns the real collection id and link.

Guidance:
- Distill the document's introductory/convention chapters into the collection ``description`` at ``start``.
- Put query-string parameters in ``params`` (copying each parameter's documented description into the row), not embedded in the URL query string. Body parameters belong in the request ``description`` as a markdown table.
- URL placeholders in any convention (``{{var}}``, ``:var``, ``<var>``) are rewritten to ``{{{{var}}}}`` at finish; missing collection variables are created automatically.
- Scripts are written in **{script_language}** (the app setting for draft-import scripts). Use only mechanical contracts the document itself defines (response envelope fields, documented status codes, signatures) — never invent logic. Check the scripting-api quickref via ``postmark_wiki_query`` before writing ``pm.*`` code. Shared assertions belong in the collection-level script at ``start``; endpoint-specific ones on the request. Shared helper logic may be extracted into a local script via ``postmark_workspace_mutate`` (``local_script`` create) and required with ``pm.require("local:<folder>/<name>.ext")``; report each created script (name, ``postmark://script/<id>`` link, require path) in your final reply.

``operation=discard`` throws the draft away. Requires Agent mode.
"""


COLLECTION_DRAFT_DESCRIPTION = _collection_draft_description("python")


class DraftRequestInput(BaseModel):
    """One request supplied in an ``add_requests`` batch.

    Every field is optional and unknown keys are ignored: models emit small, natural
    variations (``path`` for ``url``, a header object instead of rows, a stray
    ``target_id``), and rejecting those at the schema level produces a hard tool
    error that derails the run. Real validation happens in the ops layer, which
    returns a recoverable ``ok: false`` observation instead.
    """

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, description="Short request name.", max_length=300)
    method: str | None = Field(
        default=None, description="HTTP method, e.g. GET or POST.", max_length=10
    )
    url: str | None = Field(
        default=None,
        description="Request URL or path; may contain {{variables}}. 'path' is also accepted.",
        max_length=4000,
    )
    path: str | None = Field(
        default=None,
        description="Alias for url; use either.",
        max_length=4000,
    )
    folder: str | None = Field(
        default=None,
        description="Optional folder path such as 'Bookings/Cancellation'.",
        max_length=500,
    )
    headers: list[dict[str, Any]] | dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional headers, either an object like {'Accept':'application/json'} or "
            "rows like [{'key':'Accept','value':'application/json'}]."
        ),
    )
    params: list[dict[str, Any]] | dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional query-string parameters as an object or rows like "
            "[{'key':'page','value':'1','description':'Page number'}]. "
            "Copy each parameter's documented description into the row."
        ),
    )
    body: dict[str, Any] | list[Any] | str | None = Field(
        default=None,
        description=(
            "Request body. For JSON, pass an object or array directly — never an "
            "escaped JSON string and never abbreviate it with ellipses."
        ),
    )
    description: str | None = Field(
        default=None,
        description=(
            "Markdown request notes: endpoint prose plus its parameter table "
            "(Parameter/Type/Required/Description) and notes. Body params go here; "
            "query-string params go in params."
        ),
    )
    pre_script: str | None = Field(
        default=None,
        description="Optional pre-request script for documented computed values only.",
    )
    test_script: str | None = Field(
        default=None,
        description=(
            "Optional post-response script for documented response contracts only "
            "(envelope fields, status codes, mandatory fields)."
        ),
    )

    @model_validator(mode="after")
    def _normalize(self) -> Self:
        """Fold ``path`` into ``url`` and header/param objects into key/value rows."""
        if not self.url and self.path:
            self.url = self.path
        self.path = None
        if isinstance(self.headers, dict):
            self.headers = [{"key": str(k), "value": str(v)} for k, v in self.headers.items()]
        if isinstance(self.params, dict):
            self.params = [{"key": str(k), "value": str(v)} for k, v in self.params.items()]
        return self


class CollectionDraftAction(Action):
    """Add to or complete an incrementally built collection draft.

    Extras are ignored rather than rejected: models routinely tack on fields from
    other tools (``target_id``), and a hard schema error over a harmless extra is
    what previously sent a well-formed batch into a recovery spiral.
    """

    model_config = ConfigDict(extra="ignore")

    operation: DraftOperation = Field(
        description=(
            "start | add_requests | status | finish | discard. Use add_requests for "
            "all endpoints in a bounded batch. Only finish writes to the workspace."
        ),
    )
    name: str | None = Field(
        default=None,
        description="Collection name for start or an optional override for finish.",
        max_length=300,
    )
    description: str | None = Field(
        default=None,
        description=(
            "Markdown collection description distilled from the document's front-matter: "
            "authentication, endpoint conventions, required headers, response/error "
            "vocabulary, timeouts — whatever the document defines."
        ),
    )
    source: str | None = Field(
        default=None,
        description="Where the draft came from, e.g. the document file name.",
        max_length=500,
    )
    variables: list[dict[str, Any]] | None = Field(
        default=None,
        description="Collection variables for start, e.g. [{'key':'baseUrl','value':''}].",
    )
    pre_script: str | None = Field(
        default=None,
        description="Optional collection-level pre-request script (shared across requests).",
    )
    test_script: str | None = Field(
        default=None,
        description=(
            "Optional collection-level post-response script for shared documented "
            "response contracts."
        ),
    )
    requests: list[DraftRequestInput] | None = Field(
        default=None,
        description=(
            "For add_requests: every fully defined endpoint found in the current "
            "document chunk. Do not include names seen only in a table of contents."
        ),
        max_length=20,
    )

    def human_preview(self) -> str:
        """Return a short human-readable detail line for cards and Approve chrome."""
        label = str(self.name or "").strip()
        if self.operation == "start":
            return f"Start draft {label or 'collection'}"
        if self.operation == "add_requests":
            return f"Add {len(self.requests or [])} requests"
        if self.operation == "finish":
            return f"Create collection {label}".strip() if label else "Create drafted collection"
        if self.operation == "discard":
            return "Discard collection draft"
        return "Review collection draft"

    @property
    def visualize(self) -> Text:
        """Return Rich Text for SDK logs."""
        content = Text()
        content.append("Collection draft: ", style="bold yellow")
        content.append(self.human_preview(), style="white")
        return content

    def op_fields(self) -> dict[str, Any]:
        """Return the operation payload as a plain dict for the ops layer."""
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "variables": self.variables,
            "pre_script": self.pre_script,
            "test_script": self.test_script,
            "requests": [
                request.model_dump(exclude_none=True) for request in (self.requests or [])
            ],
        }


class CollectionDraftObservation(Observation):
    """Observation after a draft operation."""


class CollectionDraftExecutor(ToolExecutor):
    """Apply one draft operation for the calling session."""

    def __call__(
        self,
        action: CollectionDraftAction,
        _conversation: BaseConversation | None = None,
    ) -> CollectionDraftObservation:
        """Dispatch the operation and return its observation text."""
        session_id = _conversation_session_id(_conversation)
        fields = action.op_fields()
        if action.operation == "start":
            return CollectionDraftObservation.from_text(ops.op_start(session_id, fields))
        if action.operation == "add_requests":
            return CollectionDraftObservation.from_text(ops.op_add_requests(session_id, fields))
        if action.operation == "status":
            return CollectionDraftObservation.from_text(ops.op_status(session_id, fields))
        if action.operation == "discard":
            return CollectionDraftObservation.from_text(ops.op_discard(session_id, fields))
        return CollectionDraftObservation.from_text(
            ops.op_finish(session_id, fields, mutation_id=uuid4().hex[:12])
        )


def _conversation_session_id(conversation: BaseConversation | None) -> str:
    """Return the parent Postmark session id owning the draft."""
    if conversation is None:
        return ""
    state = conversation.state
    return resolve_workspace_session_id(
        str(state.id),
        persistence_dir=getattr(state, "persistence_dir", None),
    )


class PostmarkCollectionDraftTool(
    ToolDefinition[CollectionDraftAction, CollectionDraftObservation]
):
    """Postmark incremental collection draft tool."""

    @classmethod
    def create(
        cls,
        conv_state: object | None = None,
        **params: object,
    ) -> Sequence[Self]:
        """Create a single collection draft tool instance."""
        del conv_state
        if params:
            msg = f"{COLLECTION_DRAFT_TOOL_NAME} does not accept parameters"
            raise ValueError(msg)
        language = draft_script_language()
        return [
            cls(
                description=_collection_draft_description(language),
                action_type=CollectionDraftAction,
                observation_type=CollectionDraftObservation,
                executor=CollectionDraftExecutor(),
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
            )
        ]


def register_collection_draft_tool() -> None:
    """Register ``postmark_collection_draft`` with Postmark and OpenHands."""
    from services.ai.chat.tool_registry import register_postmark_tool

    register_postmark_tool(COLLECTION_DRAFT_TOOL_NAME, PostmarkCollectionDraftTool)


__all__ = [
    "COLLECTION_DRAFT_DESCRIPTION",
    "COLLECTION_DRAFT_TOOL_NAME",
    "CollectionDraftAction",
    "CollectionDraftExecutor",
    "CollectionDraftObservation",
    "DraftRequestInput",
    "PostmarkCollectionDraftTool",
    "register_collection_draft_tool",
]
