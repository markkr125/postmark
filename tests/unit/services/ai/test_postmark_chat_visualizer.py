"""Tests for PostmarkChatVisualizer event mapping."""

from __future__ import annotations

import json
from types import SimpleNamespace

from services.ai.chat.postmark_chat_visualizer import PostmarkChatVisualizer


def test_task_action_emits_researching_status() -> None:
    """Task tool actions update status and research payload."""
    statuses: list[str] = []
    research: list[str] = []

    class ActionEvent:
        action = SimpleNamespace(tool_name="task")

    viz = PostmarkChatVisualizer(
        on_status=statuses.append,
        on_research=research.append,
    )
    viz.on_event(ActionEvent())  # type: ignore[arg-type]

    assert statuses == ["Researching workspace…"]
    payload = json.loads(research[0])
    assert payload["phase"] == "status"
    assert payload["status"] == "Researching workspace…"


def test_task_observation_emits_findings() -> None:
    """TaskObservation text is forwarded as findings."""
    research: list[str] = []

    class TaskObservation:
        text = "## Hits\n- item"

    class ObservationEvent:
        observation = TaskObservation()

    viz = PostmarkChatVisualizer(on_research=research.append)
    viz.on_event(ObservationEvent())  # type: ignore[arg-type]

    assert len(research) == 1
    payload = json.loads(research[0])
    assert payload["phase"] == "findings"
    assert "Hits" in payload["findings"]


def test_app_context_action_emits_searching() -> None:
    """postmark_app_context actions show the searching caption."""
    statuses: list[str] = []

    class ActionEvent:
        action = SimpleNamespace(name="postmark_app_context")

    viz = PostmarkChatVisualizer(on_status=statuses.append)
    viz.on_event(ActionEvent())  # type: ignore[arg-type]
    assert statuses == ["Searching workspace…"]
