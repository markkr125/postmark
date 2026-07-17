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
from services.ai.chat.tools.workspace_import.apply import apply_workspace_import

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
        if "curl" in fields:
            return "Import from cURL"
        if "url" in fields:
            url = fields["url"]
            if len(url) > 80:
                return f"Import {url[:77]}…"
            return f"Import {url}"
        if "path" in fields:
            return f"Import {fields['path']}"
        return "Import workspace"


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
        mutation_id = uuid4().hex[:12]
        result = apply_workspace_import(
            fields=action.source_fields(),
            mutation_id=mutation_id,
        )
        return WorkspaceImportObservation.from_text(result.text)


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
