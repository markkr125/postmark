"""OpenHands tool — read Postmark workspace and editor context."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Self, cast

from pydantic import Field
from rich.text import Text

from openhands.sdk.tool.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)
from services.ai.chat.app_context.build import format_app_context
from services.ai.chat.app_context.snapshot import SNAPSHOT_FILENAME, AppContextSnapshot

if TYPE_CHECKING:
    from openhands.sdk.conversation.base import BaseConversation

PARENT_FORBIDDEN_FOCI = frozenset({"search", "workspace", "local_scripts_tree"})

FocusLiteral = Literal[
    "current",
    "collection",
    "request",
    "local_script",
    "local_scripts_tree",
    "search",
    "send_history",
    "saved_response",
    "environment",
    "workspace",
]

ScopeLiteral = Literal[
    "all",
    "collections",
    "requests",
    "local_scripts",
    "content",
    "send_history",
    "saved_responses",
    "environments",
]


class AppContextAction(Action):
    """Action to read workspace or editor context."""

    focus: FocusLiteral = Field(
        description="What to read: current tab, entity detail, or search index.",
    )
    query: str | None = Field(
        default=None,
        description="Search keywords when focus=search.",
    )
    scope: ScopeLiteral = Field(
        default="all",
        description="Search scope when focus=search.",
    )
    entity_id: int | None = Field(
        default=None,
        description="Entity id for detail foci (request, collection, script, history, etc.).",
    )

    @property
    def visualize(self) -> Text:
        """Return Rich Text for the action."""
        content = Text()
        content.append("App context: ", style="bold cyan")
        content.append(self.focus, style="white")
        if self.query:
            content.append(f" query={self.query!r}", style="dim")
        return content


class AppContextObservation(Observation):
    """Observation with workspace context text."""


APP_CONTEXT_DESCRIPTION = """Read the user's Postmark workspace context (tabs, editors, collections, scripts, history, environments).

Use focus=current for the active tab. Use detail foci (request, local_script, environment, send_history, saved_response) for one entity.
Sub-agents may use focus=search with query and scope for cross-workspace index."""


def _agent_has_task_tool(conversation: BaseConversation | None) -> bool:
    """Return whether the conversation agent includes TaskToolSet."""
    from services.ai.chat.mode_profiles import TASK_TOOL_SET_NAME

    agent = getattr(conversation, "agent", None)
    tools = getattr(agent, "tools_map", {}) or {}
    return TASK_TOOL_SET_NAME in tools


def _load_snapshot(conversation: BaseConversation | None) -> AppContextSnapshot | None:
    """Load app context snapshot from the session workspace."""
    if conversation is None:
        return None
    state = getattr(conversation, "state", None)
    workspace = getattr(state, "workspace", None) if state else None
    working_dir = getattr(workspace, "working_dir", None) if workspace else None
    if not working_dir:
        return None
    path = Path(str(working_dir)) / SNAPSHOT_FILENAME
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cast(AppContextSnapshot, raw)
    except (OSError, json.JSONDecodeError, TypeError):
        return None


class AppContextExecutor(ToolExecutor):
    """Read-only executor for workspace context."""

    def __call__(
        self,
        action: AppContextAction,
        conversation: BaseConversation | None = None,
    ) -> AppContextObservation:
        """Run the context query and return formatted text."""
        from services.ai.chat.agent_registry import ensure_app_context_stack

        ensure_app_context_stack()
        if action.focus in PARENT_FORBIDDEN_FOCI and _agent_has_task_tool(conversation):
            text = (
                f"focus={action.focus} is not available on the main agent. "
                'Call task(subagent_type="workspace_researcher", prompt="...", '
                'description="Search workspace") instead.'
            )
            return AppContextObservation.from_text(text)

        snapshot = _load_snapshot(conversation)
        if snapshot is None:
            return AppContextObservation.from_text(
                "No app context snapshot (send a message first).",
            )

        text = format_app_context(
            action.focus,
            snapshot,
            query=action.query,
            scope=action.scope,
            entity_id=action.entity_id,
        )
        return AppContextObservation.from_text(text)


class PostmarkAppContextTool(ToolDefinition[AppContextAction, AppContextObservation]):
    """Postmark workspace context tool."""

    @classmethod
    def create(
        cls,
        conv_state: object | None = None,
        **params: object,
    ) -> Sequence[Self]:
        """Create a single app context tool instance."""
        del conv_state
        if params:
            msg = "postmark_app_context does not accept parameters"
            raise ValueError(msg)
        return [
            cls(
                description=APP_CONTEXT_DESCRIPTION,
                action_type=AppContextAction,
                observation_type=AppContextObservation,
                executor=AppContextExecutor(),
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
        ]


def register_app_context_tool() -> None:
    """Register ``postmark_app_context`` with Postmark and OpenHands."""
    from services.ai.chat.tool_registry import register_postmark_tool

    register_postmark_tool("postmark_app_context", PostmarkAppContextTool)
