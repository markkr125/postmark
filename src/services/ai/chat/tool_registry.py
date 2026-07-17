"""Postmark tool registry wrapper over the OpenHands SDK tool system.

To add a custom tool:
1. Define ``Action`` / ``Observation`` / ``ToolDefinition`` under ``chat/tools/``.
2. Call ``register_postmark_tool("postmark_xxx", factory)`` (wraps SDK
   ``register_tool``).
3. Add the name to ``PostmarkAgentDef.tool_names`` and, if it writes, to
   ``agent_tools._WRITE_TOOLS`` plus ``mutation/auto_approve`` kind mapping /
   ``is_mutate_or_execute_tool``.

Do **not** bury a new user-facing capability inside
``postmark_workspace_mutate`` / ``postmark_workspace_execute`` and then paper
over discovery with system-prompt paragraphs. OpenHands discovers tools from
Action Field schemas + the tool description — see skill ``openhands-tools``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openhands.sdk import Tool

_POSTMARK_TOOL_FACTORIES: dict[str, Any] = {}


def register_postmark_tool(name: str, factory: Any) -> None:
    """Register a Postmark tool factory with the SDK and local index."""
    from openhands.sdk.tool import register_tool

    register_tool(name, factory)
    _POSTMARK_TOOL_FACTORIES[name] = factory


def resolve_tools(names: tuple[str, ...]) -> list[Tool]:
    """Resolve tool name tuples into OpenHands ``Tool`` specs."""
    from openhands.sdk import Tool

    return [Tool(name=n) for n in names]
