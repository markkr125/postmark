"""Spike: OpenHands ConfirmRisky + analyzer pause/resume/reject (+ whitelist skip)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from openhands.sdk import Agent, Conversation, ConversationExecutionStatus
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.security import ConfirmRisky, SecurityRisk
from openhands.sdk.testing import TestLLM
from openhands.sdk.tool import Tool
from openhands.sdk.workspace import LocalWorkspace

from services.ai.chat.mutation.auto_approve import add_rule, clear_rules
from services.ai.chat.mutation.security import PostmarkWorkspaceSecurityAnalyzer
from services.ai.chat.tools.workspace_mutate.tool import (
    WorkspaceMutateAction,
    WorkspaceMutateObservation,
    _apply_mutation,
)


@pytest.fixture(autouse=True)
def _clear_auto_approve(qapp: Any) -> Iterator[None]:
    """Ensure whitelist starts empty for each spike case."""
    del qapp
    clear_rules()
    yield
    clear_rules()


def _build_conversation(tmp_path: Path, llm: TestLLM) -> Any:
    """Build Conversation with ConfirmRisky + Postmark analyzer + real mutate tool."""
    # Ensure tool is registered via agent registry import side effects.
    import services.ai.chat.agent_registry  # noqa: F401

    agent = Agent(
        llm=llm,
        tools=[Tool(name="postmark_workspace_mutate")],
        system_prompt="You are a test agent.",
        include_default_tools=[],
    )
    disk = tmp_path / "ws"
    disk.mkdir(parents=True, exist_ok=True)
    conv = cast(
        Any,
        Conversation(
            agent=agent,
            workspace=LocalWorkspace(working_dir=str(disk)),
            persistence_dir=str(tmp_path / "persist"),
            conversation_id=uuid4(),
            max_iteration_per_run=5,
            delete_on_close=False,
        ),
    )
    conv.set_security_analyzer(PostmarkWorkspaceSecurityAnalyzer())
    conv.set_confirmation_policy(ConfirmRisky(threshold=SecurityRisk.HIGH, confirm_unknown=True))
    return conv


def _tool_call(call_id: str, *, name: str = "Spike") -> MessageToolCall:
    """Script a create-collection mutate call."""
    return MessageToolCall(
        id=call_id,
        name="postmark_workspace_mutate",
        arguments=(
            '{"action":"create","entity":"collection",'
            f'"fields":{{"name":"{name}"}},"security_risk":"HIGH"}}'
        ),
        origin="completion",
    )


def test_spike_confirm_pause_resume(tmp_path: Path, qapp: Any, monkeypatch: Any) -> None:
    """SP-1…SP-4: WAITING → pending → second arun executes."""
    del qapp
    executed: list[bool] = []

    def _fake_apply(action: WorkspaceMutateAction, *, allow_scripts: bool = True):
        del allow_scripts
        executed.append(True)
        return WorkspaceMutateObservation.from_text(
            f"ok: true\nsummary: stub {action.fields.get('name')}\n"
        )

    monkeypatch.setattr(
        "services.ai.chat.tools.workspace_mutate.tool._apply_mutation",
        _fake_apply,
    )
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[_tool_call("c1")],
            ),
            Message(role="assistant", content=[TextContent(text="Created.")]),
        ]
    )
    conv = _build_conversation(tmp_path, llm)
    try:
        conv.send_message("create a collection")
        asyncio.run(conv.arun())
        assert conv.state.execution_status == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
        assert executed == []
        pending = ConversationState.get_unmatched_actions(conv.state.events)
        assert len(pending) >= 1
        assert pending[0].tool_name == "postmark_workspace_mutate"

        asyncio.run(conv.arun())
        assert executed == [True]
        assert conv.state.execution_status != ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
    finally:
        conv.close()


def test_spike_reject_pending(tmp_path: Path, qapp: Any, monkeypatch: Any) -> None:
    """SP-5: reject_pending_actions → executor not applied; resume finishes."""
    del qapp
    executed: list[bool] = []

    def _fake_apply(action: WorkspaceMutateAction, *, allow_scripts: bool = True):
        del action, allow_scripts
        executed.append(True)
        return WorkspaceMutateObservation.from_text("ok: true\n")

    monkeypatch.setattr(
        "services.ai.chat.tools.workspace_mutate.tool._apply_mutation",
        _fake_apply,
    )
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[_tool_call("c2", name="RejectMe")],
            ),
            Message(role="assistant", content=[TextContent(text="Understood.")]),
        ]
    )
    conv = _build_conversation(tmp_path / "r", llm)
    try:
        conv.send_message("create")
        asyncio.run(conv.arun())
        assert conv.state.execution_status == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
        conv.reject_pending_actions(reason="user rejected")
        assert executed == []
        asyncio.run(conv.arun())
        assert executed == []
    finally:
        conv.close()


def test_spike_whitelist_skips_confirmation(tmp_path: Path, qapp: Any, monkeypatch: Any) -> None:
    """SP-7: auto-approved kind executes without WAITING_FOR_CONFIRMATION."""
    del qapp
    assert add_rule("mutate:create:collection")
    executed: list[bool] = []

    def _fake_apply(action: WorkspaceMutateAction, *, allow_scripts: bool = True):
        del action, allow_scripts
        executed.append(True)
        return WorkspaceMutateObservation.from_text("ok: true\n")

    monkeypatch.setattr(
        "services.ai.chat.tools.workspace_mutate.tool._apply_mutation",
        _fake_apply,
    )
    # Touch real apply import so mypy/ruff see it used in module under test.
    assert callable(_apply_mutation)
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[_tool_call("c3", name="Auto")],
            ),
            Message(role="assistant", content=[TextContent(text="Done.")]),
        ]
    )
    conv = _build_conversation(tmp_path / "w", llm)
    try:
        conv.send_message("create")
        asyncio.run(conv.arun())
        assert conv.state.execution_status != ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
        assert executed == [True]
    finally:
        conv.close()
