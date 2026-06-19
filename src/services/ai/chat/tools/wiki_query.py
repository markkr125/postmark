"""OpenHands tool — query the Postmark user knowledge base."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Self

from pydantic import Field
from rich.text import Text

from openhands.sdk.tool.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)
from services.ai.chat.app_wiki.query import execute_wiki_query

if TYPE_CHECKING:
    from openhands.sdk.conversation.base import BaseConversation


class WikiQueryAction(Action):
    """Action to search the Postmark user wiki."""

    query: str = Field(
        description="Keywords or question about using Postmark (UI, scripting, settings).",
    )
    page: str | None = Field(
        default=None,
        description="Optional repo-relative path from index.md (e.g. docs/user-guide/collections/create-and-organize.md).",
    )

    @property
    def visualize(self) -> Text:
        """Return Rich Text for the action."""
        content = Text()
        content.append("Wiki query: ", style="bold cyan")
        content.append(self.query, style="white")
        if self.page:
            content.append(f" (page={self.page})", style="dim")
        return content


class WikiQueryObservation(Observation):
    """Observation with wiki excerpts."""


WIKI_QUERY_DESCRIPTION = """Search Postmark's user knowledge base for how to use the app.

Use before answering questions about:
- UI workflows (collections, requests, environments, settings, history)
- Scripting (pre-request/test scripts, pm.* API, debugging)
- AI assistant and collection runner

Provide ``query`` with keywords. Optionally set ``page`` to a path from the index.

When writing scripts for the user, query scripting/API pages first and use only
documented pm/postman members."""


class WikiQueryExecutor(ToolExecutor):
    """Read-only executor for wiki lookups."""

    def __call__(
        self,
        action: WikiQueryAction,
        _conversation: BaseConversation | None = None,
    ) -> WikiQueryObservation:
        """Run the wiki query and return excerpts."""
        text = execute_wiki_query(action.query, page=action.page)
        return WikiQueryObservation.from_text(text)


class PostmarkWikiQueryTool(ToolDefinition[WikiQueryAction, WikiQueryObservation]):
    """Postmark user wiki query tool."""

    @classmethod
    def create(
        cls,
        conv_state: object | None = None,
        **params: object,
    ) -> Sequence[Self]:
        """Create a single wiki query tool instance.

        ``conv_state`` is passed positionally/by-keyword by the OpenHands tool
        registry; the parameter name must stay ``conv_state`` so the registry's
        ``create(conv_state=...)`` call binds here instead of landing in
        ``**params``.
        """
        del conv_state
        if params:
            msg = "postmark_wiki_query does not accept parameters"
            raise ValueError(msg)
        return [
            cls(
                description=WIKI_QUERY_DESCRIPTION,
                action_type=WikiQueryAction,
                observation_type=WikiQueryObservation,
                executor=WikiQueryExecutor(),
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
        ]


def register_wiki_query_tool() -> None:
    """Register ``postmark_wiki_query`` with Postmark and OpenHands."""
    from services.ai.chat.tool_registry import register_postmark_tool

    register_postmark_tool("postmark_wiki_query", PostmarkWikiQueryTool)
