"""Postmark chat conversation visualizer — forwards SDK events to Qt signals."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from openhands.sdk.conversation.visualizer import ConversationVisualizerBase
from openhands.sdk.event.base import Event

_STATUS_RESEARCHING = "Researching workspace…"
_STATUS_SEARCHING = "Searching workspace…"
_STATUS_WIKI = "Searching docs…"

_TASK_TOOL_NAMES = frozenset({"task", "task_tool_set", "TaskTool", "TaskToolSet"})


def _event_class_name(event: object) -> str:
    """Return the concrete SDK event class name."""
    return type(event).__name__


def _tool_name_from_action(action: object | None) -> str:
    """Extract a tool name from an OpenHands action object."""
    if action is None:
        return ""
    for attr in ("tool_name", "name"):
        value = getattr(action, attr, None)
        if value:
            return str(value)
    return ""


def _observation_text(observation: object | None) -> str:
    """Read human-readable text from an observation payload."""
    if observation is None:
        return ""
    for attr in ("text", "content", "message"):
        value = getattr(observation, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


class PostmarkChatVisualizer(ConversationVisualizerBase):
    """Map OpenHands tool events to Postmark chat activity + research state."""

    def __init__(
        self,
        *,
        on_status: Callable[[str], None] | None = None,
        on_research: Callable[[str], None] | None = None,
    ) -> None:
        """Store callbacks invoked on the GUI thread via worker signals."""
        super().__init__()
        self._on_status = on_status
        self._on_research = on_research
        self._child_visualizers: dict[str, PostmarkChatVisualizer] = {}

    def create_sub_visualizer(self, agent_id: str) -> ConversationVisualizerBase:
        """Return a child visualizer for TaskManager sub-runs."""
        child = PostmarkChatVisualizer(
            on_status=self._on_status,
            on_research=self._on_research,
        )
        self._child_visualizers[agent_id] = child
        return child

    def on_event(self, event: Event) -> None:
        """Handle one SDK event."""
        name = _event_class_name(event)
        if name == "ActionEvent":
            self._handle_action(event)
        elif name == "ObservationEvent":
            self._handle_observation(event)

    def _emit_status(self, text: str) -> None:
        if self._on_status is not None:
            self._on_status(text)
        if self._on_research is not None:
            payload = json.dumps({"phase": "status", "status": text, "findings": ""})
            self._on_research(payload)

    def _emit_findings(self, text: str) -> None:
        if self._on_research is not None:
            payload = json.dumps({"phase": "findings", "status": "", "findings": text})
            self._on_research(payload)

    def _handle_action(self, event: Any) -> None:
        action = getattr(event, "action", None)
        tool_name = _tool_name_from_action(action)
        if tool_name in _TASK_TOOL_NAMES:
            self._emit_status(_STATUS_RESEARCHING)
            return
        if tool_name == "postmark_app_context":
            self._emit_status(_STATUS_SEARCHING)
            return
        if tool_name == "postmark_wiki_query":
            self._emit_status(_STATUS_WIKI)

    def _handle_observation(self, event: Any) -> None:
        observation = getattr(event, "observation", None)
        if _event_class_name(observation) != "TaskObservation":
            return
        text = _observation_text(observation)
        if text:
            self._emit_findings(text)


__all__ = ["PostmarkChatVisualizer"]
