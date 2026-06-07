"""Postmark tool registry wrapper over the OpenHands SDK tool system.

To add a custom tool later:
1. Define ``Action`` / ``Observation`` / ``ToolDefinition`` (e.g. under ``chat/tools/``).
2. Call ``register_postmark_tool("postmark_xxx", factory)``.
3. Reference the name in a ``PostmarkAgentDef.tool_names`` tuple.
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
