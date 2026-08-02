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
1. ``operation=start`` with ``name`` — and whenever the document defines them, also ``variables`` (with values from the document, e.g. an endpoint convention like ``https://myendpoint.com/v1.32/{{{{operation}}}}`` means ``baseURL`` = ``https://myendpoint.com`` and ``version`` = ``v1.32``), markdown ``description`` (document front-matter: authentication, endpoint conventions, required headers, response/error vocabulary, timeouts), collection ``auth`` (map the document's Authentication section — Postmark auth with ``{{{{variables}}}}`` for credentials, never hardcode secrets), ``default_headers``, optional ``signature`` (named recipe — see Guidance), plus collection-level ``pre_script`` / ``test_script`` for shared mechanical contracts. If the document describes how authentication works (Basic/Bearer/API key), ``auth`` is NOT optional — set it at start.
2. ``operation=add_requests`` with up to 20 fully defined endpoints. Each entry takes ``name``, ``method``, ``url`` (``path`` also accepted), and optional ``folder``, ``headers`` (object or key/value rows), ``params`` (query-string rows with per-parameter ``description``), ``body``, markdown ``description`` (endpoint prose + parameter tables for body fields), ``pre_script``, ``test_script``, and up to 12 ``responses`` examples (``name``/``status``/``code``/``headers``/``body``). **For POST/PUT/PATCH, provide the documented request input whenever the document shows one:** ``body`` (JSON object/array or XML/text string) and/or ``params`` (query-string). Query-only POSTs are fine with ``params`` and an empty body. A markdown parameter table in ``description`` documents fields; it does **not** replace ``body``/``params`` — when you omitted them in an earlier batch, re-issue those endpoints with the real input. Saved ``responses`` store response examples and copy the parent request body into each example's request snapshot. Use one batch per document chunk. When a chunk has no endpoints (TOC, prose, auth-only pages), pass ``requests: []`` or skip ``add_requests`` — an empty batch is a soft no-op, not an error. Do not invent endpoints merely named in a table of contents.
3. ``operation=status`` at any time to see what the draft already contains.
4. ``operation=finish`` to create the collection. This is the only step that writes and asks for Approve. It returns the real collection id and link.

Guidance:
- Distill the document's introductory/convention chapters into the collection ``description`` at ``start``.
- Put query-string parameters in ``params`` (copying each parameter's documented description into the row), not embedded in the URL query string. Body field docs may also appear as a markdown table in the request ``description``, but the actual example payload must still go in ``body``.
- For every POST/PUT/PATCH endpoint, copy the documented request input into ``body`` (JSON object/array or XML/text) and/or ``params`` (query-string). Query-only endpoints need ``params`` only. If an earlier observation warned about a missing body/params, re-add that endpoint with the input. Saved ``responses`` are response examples only — they do not fill the request body, but each example's Request Body tab mirrors the parent request ``body``.
- URL placeholders in any convention (``{{var}}``, ``:var``, ``<var>``) are rewritten to ``{{{{var}}}}`` at finish; missing collection variables are created automatically.
- **Signatures / HMAC:** If the document requires a signature or HMAC header, pass ``signature`` on ``start`` with a known ``kind`` (``sha256_apikey_secret_timestamp``, ``hmac_sha256``) plus optional header/var names. A reviewed pre-request script is generated for you — **do NOT write crypto yourself**. For algorithms the library does not cover, put a note in the collection description instead of improvising.
- When the document defines an endpoint base URL, version, or default path segments, pre-fill those variable VALUES from the document (e.g. ``version`` = ``v1.32`` when examples use ``/v1.32/``) — only credentials stay empty.
- Map the document's Authentication section to collection ``auth`` — if the document says how auth works (Basic auth, bearer token, API key header), you MUST set ``auth`` at ``start`` with ``{{{{username}}}}`` / ``{{{{password}}}}`` / ``{{{{apiKey}}}}`` / ``{{{{token}}}}`` placeholders and add those variables (empty values) so the user fills credentials once. Do not skip auth and do not bake an ``Authorization`` header into ``default_headers``. Use ``default_headers`` for non-auth headers every request shares (e.g. ``Content-Type``; request headers override).
- Scripts are written in **{script_language}** (the app setting for draft-import scripts). Use only mechanical contracts the document itself defines (response envelope fields, documented status codes) — never invent logic or crypto. Check the scripting-api quickref via ``postmark_wiki_query`` before writing ``pm.*`` code. Shared assertions belong in the collection-level script at ``start``; endpoint-specific ones on the request. Shared helper logic may be extracted into a local script via ``postmark_workspace_mutate`` (``local_script`` create) and required with ``pm.require("local:<folder>/<name>.ext")``; report each created script (name, ``postmark://script/<id>`` link, require path) in your final reply.

``operation=discard`` throws the draft away. Requires Agent mode.
"""


COLLECTION_DRAFT_DESCRIPTION = _collection_draft_description("python")


class DraftRequestInput(BaseModel):
    """One request supplied in an ``add_requests`` batch.

    Every field is optional and unknown keys are ignored: models emit small, natural
    variations (``path`` for ``url``, a header object instead of rows, a stray
    ``target_id``), and rejecting those at the schema level produces a hard tool
    error that derails the run. Real validation happens in the ops layer, which
    returns a recoverable ``ok: false`` observation for structural failures.
    Soft caps (body/params/responses) truncate with warnings so the batch stays green.
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
            "Request body. For POST/PUT/PATCH, provide body and/or params when the "
            "document shows a request example. Pass a JSON object/array, or an "
            "XML/text string — never abbreviate with ellipses. Query-only POSTs "
            "may omit body when params are set."
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
    responses: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Optional saved response examples (max 12): each with name, status, code, "
            "headers, and body. Prefer short documented examples — not full dumps."
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
        description=(
            "Collection variables for start. Pre-fill values the document defines "
            "(e.g. {'key':'version','value':'v1.32'} from an endpoint convention); "
            "leave values empty only for credentials the user must supply."
        ),
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
    signature: dict[str, Any] | None = Field(
        default=None,
        description=(
            "If the document requires a signature/HMAC header, describe it here "
            "(kind + optional header/var names). A reviewed pre-request script is "
            "generated for you — do NOT write crypto yourself. Known kinds: "
            "sha256_apikey_secret_timestamp, hmac_sha256."
        ),
    )
    auth: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Postmark collection auth (type + fields). Required when the document "
            "has an Authentication section (Basic/Bearer/API key) — use {{variables}} "
            "for credentials, never hardcode secrets or example values."
        ),
    )
    default_headers: list[dict[str, Any]] | dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional headers applied to every request (request headers override), "
            "e.g. {'Content-Type':'application/json'} or key/value rows."
        ),
    )
    requests: list[DraftRequestInput] | None = Field(
        default=None,
        description=(
            "For add_requests: every fully defined endpoint found in the current "
            "document chunk. Pass an empty list when the chunk has no endpoints "
            "(TOC/prose) — that is a soft no-op. Do not include names seen only "
            "in a table of contents."
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
        default_headers = self.default_headers
        if isinstance(default_headers, dict):
            default_headers = [{"key": str(k), "value": str(v)} for k, v in default_headers.items()]
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "variables": self.variables,
            "pre_script": self.pre_script,
            "test_script": self.test_script,
            "signature": self.signature,
            "auth": self.auth,
            "default_headers": default_headers,
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
