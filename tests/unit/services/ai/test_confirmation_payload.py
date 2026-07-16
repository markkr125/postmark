"""Tests for humanized Approve confirmation payloads."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from services.ai.chat.confirmation_payload import pending_actions_payload
from services.ai.chat.tools.workspace_execute.tool import WorkspaceExecuteAction
from services.ai.chat.tools.workspace_mutate.tool import WorkspaceMutateAction


def test_mutate_human_preview_create_collection() -> None:
    """Create collection preview is the name only — no tool dump."""
    action = WorkspaceMutateAction(
        action="create",
        entity="collection",
        fields={"name": "Payments API"},
    )
    assert action.human_preview() == "Payments API"
    assert "Workspace mutate" not in action.human_preview()
    assert "postmark_" not in action.human_preview()


def test_execute_human_preview_send_request_uses_url(monkeypatch: Any) -> None:
    """Send request preview prefers the redacted URL."""
    action = WorkspaceExecuteAction(operation="send_request", request_id=7)
    monkeypatch.setattr(
        "services.ai.chat.execution.preview_url.resolve_execute_preview_url",
        lambda _a: "https://api.example.com/health",
    )
    assert action.human_preview() == "https://api.example.com/health"


def test_pending_actions_payload_titles_without_tool_names(monkeypatch: Any) -> None:
    """Payload exposes title/detail for UI; tool_name is debug-only."""
    action = WorkspaceMutateAction(
        action="create",
        entity="collection",
        fields={"name": "Payments API"},
    )
    event = SimpleNamespace(
        tool_name="postmark_workspace_mutate",
        action=action,
    )

    conv = SimpleNamespace(state=SimpleNamespace(events=[event]))

    monkeypatch.setattr(
        "openhands.sdk.conversation.state.ConversationState.get_unmatched_actions",
        staticmethod(lambda events: list(events)),
    )
    monkeypatch.setattr(
        "services.ai.chat.confirmation_payload.kind_from_action_event",
        lambda _e: "mutate:create:collection",
    )

    payload = pending_actions_payload(conv)
    rows = payload["actions"]
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "Create collection"
    assert row["detail"] == "Payments API"
    assert row["kind"] == "mutate:create:collection"
    assert row["risk"] == "normal"
    assert row["tool_name"] == "postmark_workspace_mutate"
    joined = f"{row['title']} {row['detail']}"
    assert "postmark_workspace_mutate" not in joined
    assert "Workspace mutate" not in joined


def test_pending_actions_payload_marks_delete_destructive(monkeypatch: Any) -> None:
    """Delete kinds get risk=destructive for UI tinting."""
    action = WorkspaceMutateAction(
        action="delete",
        entity="request",
        target_id=3,
    )
    event = SimpleNamespace(
        tool_name="postmark_workspace_mutate",
        action=action,
    )
    conv = SimpleNamespace(state=SimpleNamespace(events=[event]))
    monkeypatch.setattr(
        "openhands.sdk.conversation.state.ConversationState.get_unmatched_actions",
        staticmethod(lambda events: list(events)),
    )
    monkeypatch.setattr(
        "services.ai.chat.confirmation_payload.kind_from_action_event",
        lambda _e: "mutate:delete:request",
    )
    row = pending_actions_payload(conv)["actions"][0]
    assert row["risk"] == "destructive"
    assert row["title"] == "Delete request"
