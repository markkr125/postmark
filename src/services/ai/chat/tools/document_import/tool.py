"""OpenHands tool — read an uploaded PDF/DOCX document one Markdown chunk at a time."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Self

from pydantic import Field
from rich.text import Text

from openhands.sdk.llm import ImageContent, TextContent
from openhands.sdk.tool.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)
from services.ai.chat.attachments.chunks import DocumentChunk, chunk_at
from services.ai.chat.attachments.screenshots import (
    chunk_ocr_text,
    chunk_screenshots,
    session_supports_vision,
)
from services.ai.chat.attachments.store import (
    list_attachments,
    read_markdown,
    resolve_attachment,
    store_attachments,
)
from services.ai.chat.workspace_snapshot import resolve_workspace_session_id

if TYPE_CHECKING:
    from openhands.sdk.conversation.base import BaseConversation

DOCUMENT_IMPORT_TOOL_NAME = "postmark_document_import"

DOCUMENT_IMPORT_DESCRIPTION = """Read an uploaded API document (PDF/DOCX converted to Markdown) one chunk at a time, so you can rebuild it as a collection. Read-only.

Attached documents are listed in the user's message as `postmark://uploaded/<name>.md`. With one attachment, OMIT `uri` on every call — Postmark resolves it without making you repeat an identifier. Pass `uri` only to choose among several attachments. Screenshots appear as `[image N]` markers: if your model can see images they are attached to the response, otherwise text recognised from them is placed under each marker.

Call with `chunk=1` first. Every response ends with `chunk X of Y`. As soon as a chunk has shown an endpoint's method, path, and request example (or complete request parameters when no example exists), call postmark_collection_draft `operation=add_requests`; response parameters/examples do not need to finish first. Then request `chunk=X+1`. Do not add endpoints merely named in a table of contents. Repeat until `chunk Y of Y`; do not skip chunks or postpone every request until the final chunk.

To read a document the user named but did not attach, pass its full `path` once; it is uploaded and chunked the same way."""

_ERROR_HINTS: dict[str, str] = {
    "no_uploads": (
        "No document is attached to this chat. Ask the user to attach it with the paperclip."
    ),
    "unknown_uri": (
        "That postmark://uploaded/ URI is not in this chat. Use one listed in the user's message."
    ),
    "ambiguous_attachment": (
        "Several documents are attached. Pass the postmark://uploaded/ URI of the one to read."
    ),
    "empty_document": "The document converted to no readable text.",
    "bad_chunk": "That chunk number is out of range; chunks start at 1.",
    "invalid_path": "Path must not contain .. segments.",
    "missing_file": "File not found. Use an absolute or home-relative path that exists.",
    "sensitive_path": "That path segment is blocked. Copy the document elsewhere first.",
    "denied_path": "System paths are blocked. Use a user-readable document location.",
    "file_too_large": "File exceeds the 50 MB limit.",
    "unsupported_document_type": "Only .pdf and .docx files are supported.",
}


def _format_document_error(code: str) -> str:
    """Return a machine- and human-readable failure observation."""
    hint = _ERROR_HINTS.get(code, "Pass the postmark://uploaded/ URI from the user's message.")
    return f"ok: false\nerror: {code}\nhint: {hint}\n"


def _render_chunk(
    name: str,
    uri: str,
    chunk: DocumentChunk,
    body: str,
    images: int = 0,
    skipped_images: int = 0,
    recognised_images: int = 0,
) -> str:
    """Render one chunk with the counter and the instruction for what to do next."""
    header = [
        "ok: true",
        f"document: {name}",
        f"uri: {uri}",
        f"chunk: {chunk.number} of {chunk.total}",
    ]
    if chunk.first_page:
        header.append(f"pages: {chunk.first_page}-{chunk.last_page}")
    if images:
        header.append(
            f"screenshots: {images} attached below; the [image N] markers show where "
            "each one belongs"
        )
    if skipped_images:
        header.append(
            f"screenshots_omitted: {skipped_images} over the per-chunk limit; read the "
            "remaining [image N] markers in a later call if you need them"
        )
    if recognised_images:
        header.append(
            f"screenshots: {recognised_images} read as text below their [image N] "
            "markers (your model cannot view images)"
        )
    if chunk.number < chunk.total:
        next_step = (
            "next_step: use postmark_collection_draft operation=add_requests once for "
            "endpoints whose method, path, and request example/parameters have now been "
            "seen (response docs may continue; TOC-only names do not count), then read "
            f"chunk={chunk.number + 1}. Do not postpone completed requests until the final "
            "chunk. With one upload, omit uri."
        )
    else:
        next_step = (
            "next_step: this is the final chunk. Add its remaining endpoints, then call "
            "postmark_collection_draft operation=finish to create the collection."
        )
    return "\n".join([*header, "", body.strip(), "", next_step, ""])


class DocumentImportAction(Action):
    """Action to read one chunk of an uploaded document."""

    uri: str | None = Field(
        default=None,
        description=(
            "Only use this to choose among several attachments. OMIT it when the chat "
            "has one attachment; Postmark resolves that document automatically."
        ),
        max_length=500,
    )
    chunk: int = Field(
        default=1,
        ge=1,
        description="Which chunk to read, starting at 1. Read them in order.",
    )
    path: str | None = Field(
        default=None,
        description=(
            "Only for a local .pdf or .docx the user named but did not attach. Pass the "
            "full path once; never shorten it."
        ),
    )

    def display_name(self) -> str:
        """Return the document label for activity cards."""
        from services.ai.chat.attachments.models import uri_document_name

        document = uri_document_name(self.uri or "")
        if document:
            return document
        raw = (self.path or "").strip()
        if raw:
            from pathlib import Path

            return Path(raw).name
        return "attached document"

    def human_preview(self) -> str:
        """Return a short human-readable preview for UI cards."""
        return f"Read {self.display_name()} (chunk {self.chunk})"

    @property
    def visualize(self) -> Text:
        """Return Rich Text for the action."""
        content = Text()
        content.append("Read document: ", style="bold cyan")
        content.append(self.display_name(), style="white")
        content.append(f" (chunk {self.chunk})", style="dim")
        return content


class DocumentImportObservation(Observation):
    """Observation with one chunk of an uploaded document."""


class DocumentImportExecutor(ToolExecutor):
    """Read-only executor serving chunks of uploaded Markdown."""

    def __call__(
        self,
        action: DocumentImportAction,
        _conversation: BaseConversation | None = None,
    ) -> DocumentImportObservation:
        """Return the requested chunk, or a diagnostic when it cannot be found."""
        session_id = _conversation_session_id(_conversation)
        error = _upload_on_demand(session_id, action.path)
        if error is not None:
            return DocumentImportObservation.from_text(_format_document_error(error), is_error=True)

        entries = list_attachments(session_id)
        if not entries:
            return DocumentImportObservation.from_text(
                _format_document_error("no_uploads"), is_error=True
            )
        reference = action.uri or action.path
        entry = resolve_attachment(session_id, reference)
        if entry is None:
            code = "unknown_uri" if reference else "ambiguous_attachment"
            return DocumentImportObservation.from_text(_format_document_error(code), is_error=True)

        markdown = read_markdown(entry)
        if not markdown.strip():
            return DocumentImportObservation.from_text(
                _format_document_error("empty_document"), is_error=True
            )
        chunk = chunk_at(markdown, action.chunk)
        if chunk is None:
            return DocumentImportObservation.from_text(
                _format_document_error("bad_chunk"), is_error=True
            )

        # The model's own capability decides how screenshots are delivered: a vision
        # model gets the images, anything else gets text recognised from them.
        urls: list[str] = []
        skipped = 0
        body = chunk.text
        recognised = 0
        if session_supports_vision(session_id):
            urls, skipped = chunk_screenshots(entry, body)
        else:
            body, recognised = chunk_ocr_text(entry, body)
        text = _render_chunk(
            str(entry.get("name") or ""),
            str(entry.get("uri") or ""),
            chunk,
            body,
            images=len(urls),
            skipped_images=skipped,
            recognised_images=recognised,
        )
        content: list[TextContent | ImageContent] = [TextContent(text=text)]
        content.extend(ImageContent(image_urls=[url]) for url in urls)
        return DocumentImportObservation(content=content)


def _upload_on_demand(session_id: str, path: str | None) -> str | None:
    """Upload a named-but-unattached *path*, returning an error code on failure."""
    raw = (path or "").strip()
    if not raw or resolve_attachment(session_id, raw) is not None:
        return None
    from services.document_import.extract import validate_document_path
    from services.document_import.models import DocumentImportError

    try:
        validate_document_path(raw)
    except DocumentImportError as exc:
        return exc.code
    store_attachments(session_id, [raw])
    return None


def _conversation_session_id(conversation: BaseConversation | None) -> str:
    """Return the parent Postmark session id owning the uploads."""
    if conversation is None:
        return ""
    state = conversation.state
    return resolve_workspace_session_id(
        str(state.id),
        persistence_dir=getattr(state, "persistence_dir", None),
    )


class PostmarkDocumentImportTool(ToolDefinition[DocumentImportAction, DocumentImportObservation]):
    """Postmark uploaded-document chunk reader."""

    @classmethod
    def create(
        cls,
        conv_state: object | None = None,
        **params: object,
    ) -> Sequence[Self]:
        """Create a single document import tool instance."""
        del conv_state
        if params:
            msg = f"{DOCUMENT_IMPORT_TOOL_NAME} does not accept parameters"
            raise ValueError(msg)
        return [
            cls(
                description=DOCUMENT_IMPORT_DESCRIPTION,
                action_type=DocumentImportAction,
                observation_type=DocumentImportObservation,
                executor=DocumentImportExecutor(),
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
        ]


def register_document_import_tool() -> None:
    """Register ``postmark_document_import`` with Postmark and OpenHands."""
    from services.ai.chat.tool_registry import register_postmark_tool

    register_postmark_tool(DOCUMENT_IMPORT_TOOL_NAME, PostmarkDocumentImportTool)


__all__ = [
    "DOCUMENT_IMPORT_DESCRIPTION",
    "DOCUMENT_IMPORT_TOOL_NAME",
    "DocumentImportAction",
    "DocumentImportExecutor",
    "DocumentImportObservation",
    "PostmarkDocumentImportTool",
    "register_document_import_tool",
]
