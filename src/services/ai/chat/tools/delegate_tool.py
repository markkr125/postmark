"""OpenHands delegate tool — parallel subagent spawn and delegation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Self

from openhands.sdk.tool.tool import (
    ToolAnnotations,
    ToolDefinition,
)
from openhands.tools.delegate.definition import DelegateAction, DelegateObservation
from openhands.tools.delegate.impl import DelegateExecutor
from services.ai.chat.subagent_limits import max_parallel_subagents

if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState
    from openhands.tools.task.manager import ConfirmationHandler

DELEGATE_TOOL_NAME = "delegate"

DELEGATE_TOOL_DESCRIPTION = """Spawn and delegate work to subagents in parallel. ALWAYS exactly two calls, in order.

Call 1 — spawn (copy this shape exactly):
  {"command": "spawn", "ids": ["ts", "py"], "agent_types": ["wiki-researcher", "wiki-researcher"]}

Call 2 — delegate (each task value is a PLAIN STRING, never an object):
  {"command": "delegate", "tasks": {"ts": "Find TypeScript scripting docs", "py": "Find Python scripting docs"}}

Hard rules — do NOT deliberate about these, they are fixed:
- ``tasks`` values are plain strings. Never nest prompt/description/subagent_type/resume inside a task.
- Always two separate calls: spawn first, then delegate. Never combine them.
- ``agent_types``: use ``wiki-researcher`` for Postmark wiki lookups, ``general-purpose`` for synthesis.
- Pick ids and task strings in ONE pass. Do not re-derive the schema or second-guess the format."""


class PostmarkDelegateTool(ToolDefinition[DelegateAction, DelegateObservation]):
    """Delegate tool backed by :class:`DelegateExecutor`."""

    name = DELEGATE_TOOL_NAME

    def _get_tool_schema(
        self,
        add_security_risk_prediction: bool = False,
        action_type: type[Any] | None = None,
    ) -> dict[str, Any]:
        """Return a delegate schema with explicit task value typing."""
        schema = super()._get_tool_schema(add_security_risk_prediction, action_type)
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return schema

        tasks = properties.get("tasks")
        if isinstance(tasks, dict):
            tasks["description"] = (
                "For command='delegate' only. Map each spawned id to one plain task "
                "string. Example: {'ts': 'Find TypeScript scripting docs'}. "
                "Never use nested prompt/description/subagent_type objects here."
            )
            tasks["additionalProperties"] = {"type": "string"}

        ids = properties.get("ids")
        if isinstance(ids, dict):
            ids["description"] = "For command='spawn' only. Short ids, e.g. ['ts', 'py']."

        agent_types = properties.get("agent_types")
        if isinstance(agent_types, dict):
            agent_types["description"] = (
                "For command='spawn' only. Use 'wiki-researcher' for wiki lookups "
                "and 'general-purpose' for synthesis."
            )

        security_risk = properties.get("security_risk")
        if isinstance(security_risk, dict):
            security_risk["description"] = "Use LOW for Postmark wiki lookup delegation."

        return schema

    @classmethod
    def create(
        cls,
        conv_state: ConversationState | None = None,
        confirmation_handler: ConfirmationHandler | None = None,
        **params: object,
    ) -> Sequence[Self]:
        """Create the delegate tool for one conversation."""
        if params:
            msg = "delegate does not accept extra parameters"
            raise ValueError(msg)
        executor = DelegateExecutor(max_children=max_parallel_subagents())
        return [
            cls(
                description=DELEGATE_TOOL_DESCRIPTION,
                action_type=DelegateAction,
                observation_type=DelegateObservation,
                executor=executor,
                annotations=ToolAnnotations(
                    title="delegate",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
        ]


def register_postmark_delegate_tool() -> None:
    """Register the delegate tool with Postmark and OpenHands."""
    from services.ai.chat.tool_registry import register_postmark_tool

    register_postmark_tool(DELEGATE_TOOL_NAME, PostmarkDelegateTool)


__all__ = [
    "DELEGATE_TOOL_DESCRIPTION",
    "DELEGATE_TOOL_NAME",
    "PostmarkDelegateTool",
    "register_postmark_delegate_tool",
]
