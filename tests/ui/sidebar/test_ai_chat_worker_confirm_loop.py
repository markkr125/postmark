"""P0-W integration: AiChatWorker.run through WAITING → Approve/Reject/Stop."""

from __future__ import annotations

import tempfile
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from openhands.sdk import Agent, Conversation
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.security import ConfirmRisky, SecurityRisk
from openhands.sdk.testing import TestLLM
from openhands.sdk.tool import Tool
from openhands.sdk.workspace import LocalWorkspace
from PySide6.QtCore import QThread, QTimer
from pytestqt.qtbot import QtBot

from services.ai.ai_config import AiModelEntry
from services.ai.chat.mutation.auto_approve import clear_rules
from services.ai.chat.mutation.security import PostmarkWorkspaceSecurityAnalyzer
from services.ai.chat.session_service import ComposerRunContext
from services.ai.chat.tools.workspace_mutate.tool import (
    WorkspaceMutateAction,
    WorkspaceMutateObservation,
)
from ui.sidebar.ai.workers.chat_worker import AiChatWorker


def _entry() -> AiModelEntry:
    """Minimal model entry for worker tests."""
    return {
        "id": "id1",
        "provider": "openai",
        "label": "L",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
    }


@pytest.fixture(autouse=True)
def _clear_auto_approve(qapp: Any) -> Generator[None, None, None]:
    """Clear auto-approve whitelist so confirm tests pause for Approve."""
    del qapp
    clear_rules()
    yield
    clear_rules()


def _tool_call(call_id: str = "c1") -> MessageToolCall:
    """Script a mutate create-collection call."""
    return MessageToolCall(
        id=call_id,
        name="postmark_workspace_mutate",
        arguments=(
            '{"action":"create","entity":"collection",'
            '"fields":{"name":"WTest"},"security_risk":"HIGH"}'
        ),
        origin="completion",
    )


def _patch_build_waiting_conversation(
    monkeypatch: pytest.MonkeyPatch,
    *,
    llm: TestLLM,
    executed: list[bool],
) -> None:
    """Patch build_conversation to return a ConfirmRisky Conversation with TestLLM."""

    def _fake_apply(action: WorkspaceMutateAction, *, allow_scripts: bool = True):
        del action, allow_scripts
        executed.append(True)
        return WorkspaceMutateObservation.from_text("ok: true\nsummary: stub\n")

    monkeypatch.setattr(
        "services.ai.chat.tools.workspace_mutate.tool._apply_mutation",
        _fake_apply,
    )

    def _build(
        session_id: str,
        entry: AiModelEntry,
        agent_id: str,
        *,
        callbacks: list | None = None,
        token_callbacks: list | None = None,
        composer: ComposerRunContext | None = None,
        stream: bool = True,
    ) -> Conversation:
        del entry, agent_id, composer, stream
        import services.ai.chat.agent_registry  # noqa: F401

        agent = Agent(
            llm=llm,
            tools=[Tool(name="postmark_workspace_mutate")],
            system_prompt="test",
            include_default_tools=[],
        )
        root = Path(tempfile.mkdtemp())
        conv = Conversation(
            agent=agent,
            workspace=LocalWorkspace(working_dir=str(root / "ws")),
            persistence_dir=str(root / "persist"),
            conversation_id=uuid.UUID(session_id),
            callbacks=callbacks or [],
            token_callbacks=token_callbacks or [],
            max_iteration_per_run=5,
            delete_on_close=False,
        )
        # LocalConversation methods; Conversation factory return type is opaque to mypy.
        conv.set_security_analyzer(PostmarkWorkspaceSecurityAnalyzer())  # type: ignore[attr-defined]
        conv.set_confirmation_policy(  # type: ignore[attr-defined]
            ConfirmRisky(threshold=SecurityRisk.HIGH, confirm_unknown=True)
        )
        return conv

    monkeypatch.setattr(
        "services.ai.chat.session_service.AiChatSessionService.build_conversation",
        _build,
    )
    monkeypatch.setattr(
        "services.ai.chat.session_service.AiChatSessionService.get_messages",
        lambda _sid: [],
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.ContextUsageService.collect_compaction_diagnostics",
        lambda **_kw: {"ring_total_tokens": 0, "ring_used_tokens": 0},
    )
    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.resolve_assistant_parts",
        lambda _conv, thinking, content: MagicMock(
            thinking=thinking or "", content=content or "ok"
        ),
    )
    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.metrics_from_conversation",
        lambda *_a, **_k: None,
    )


def test_worker_waiting_approve_executes(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """P0-W1/W2: arun pauses → Approve → tool runs → finished."""
    executed: list[bool] = []
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[_tool_call("wa")],
            ),
            Message(role="assistant", content=[TextContent(text="Created.")]),
        ]
    )
    _patch_build_waiting_conversation(monkeypatch, llm=llm, executed=executed)

    worker = AiChatWorker()
    session_id = str(uuid.uuid4())
    worker.set_run(
        session_id=session_id,
        entry=_entry(),
        agent_id="postmark-assistant",
        text="create",
        composer=ComposerRunContext(send_mode="agent"),
    )
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    with qtbot.waitSignal(worker.confirmation_needed, timeout=15000) as blocker:
        thread.start()
    assert executed == []
    payload = blocker.args[1]
    assert isinstance(payload, dict)
    assert payload.get("actions")

    with qtbot.waitSignal(worker.assistant_finished, timeout=15000):
        QTimer.singleShot(0, worker.approve_confirmation)
    assert executed == [True]
    thread.quit()
    thread.wait(5000)


def test_worker_waiting_reject_skips_executor(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0-W3: Reject → executor not applied."""
    executed: list[bool] = []
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[_tool_call("wr")],
            ),
            Message(role="assistant", content=[TextContent(text="Understood.")]),
        ]
    )
    _patch_build_waiting_conversation(monkeypatch, llm=llm, executed=executed)

    worker = AiChatWorker()
    session_id = str(uuid.uuid4())
    worker.set_run(
        session_id=session_id,
        entry=_entry(),
        agent_id="postmark-assistant",
        text="create",
        composer=ComposerRunContext(send_mode="agent"),
    )
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    with qtbot.waitSignal(worker.confirmation_needed, timeout=15000):
        thread.start()
    with qtbot.waitSignal(worker.assistant_finished, timeout=15000):
        QTimer.singleShot(0, lambda: worker.reject_confirmation("nope"))
    assert executed == []
    thread.quit()
    thread.wait(5000)


def test_worker_waiting_stop_fails_stopped(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """P0-W4: Stop while waiting → failed Stopped; no hang."""
    executed: list[bool] = []
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[_tool_call("ws")],
            ),
            Message(role="assistant", content=[TextContent(text="x")]),
        ]
    )
    _patch_build_waiting_conversation(monkeypatch, llm=llm, executed=executed)

    worker = AiChatWorker()
    session_id = str(uuid.uuid4())
    worker.set_run(
        session_id=session_id,
        entry=_entry(),
        agent_id="postmark-assistant",
        text="create",
        composer=ComposerRunContext(send_mode="agent"),
    )
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    with qtbot.waitSignal(worker.confirmation_needed, timeout=15000):
        thread.start()
    with qtbot.waitSignal(worker.failed, timeout=15000) as blocker:
        QTimer.singleShot(0, worker.cancel)
    assert blocker.args[0] == "Stopped"
    assert executed == []
    thread.quit()
    thread.wait(5000)


def test_worker_stop_before_confirm_loop_no_hang(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bug 2: cancel during payload build (before loop.exec) must not hang.

    Exercises the real pre-loop guards in ``_wait_for_confirmation_decision``
    by cancelling from ``pending_actions_payload`` (after waiting=True, before
    the QEventLoop is created).
    """
    executed: list[bool] = []
    llm = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text="")],
                tool_calls=[_tool_call("wt")],
            ),
            Message(role="assistant", content=[TextContent(text="x")]),
        ]
    )
    _patch_build_waiting_conversation(monkeypatch, llm=llm, executed=executed)

    worker = AiChatWorker()
    session_id = str(uuid.uuid4())
    worker.set_run(
        session_id=session_id,
        entry=_entry(),
        agent_id="postmark-assistant",
        text="create",
        composer=ComposerRunContext(send_mode="agent"),
    )

    import services.ai.chat.confirmation_payload as payload_mod

    real_payload = payload_mod.pending_actions_payload

    def _payload_then_cancel(conv: object) -> dict:
        # Simulate Stop arriving in the TOCTOU window before loop.exec().
        worker.cancel()
        return real_payload(conv)

    monkeypatch.setattr(
        "ui.sidebar.ai.workers.chat_worker.pending_actions_payload",
        _payload_then_cancel,
    )

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    with qtbot.waitSignal(worker.failed, timeout=15000) as blocker:
        thread.start()
    assert blocker.args[0] == "Stopped"
    assert executed == []
    thread.quit()
    thread.wait(5000)


def test_pending_payload_includes_send_url(qapp: Any) -> None:
    """Bug 1: execute send_request pending summary exposes destination URL."""
    del qapp
    from services.ai.chat.tools.workspace_execute.tool import WorkspaceExecuteAction
    from services.collection_service import CollectionService

    coll = CollectionService.create_collection("AuditURL")
    req = CollectionService.create_request(
        int(coll.id),
        "GET",
        "https://api.example.com/v1/items?token=sekrit",
        "Items",
    )
    action = WorkspaceExecuteAction(operation="send_request", request_id=int(req.id))
    url = action.preview_url()
    assert url is not None
    assert "api.example.com" in url
    viz = str(action.visualize)
    assert "api.example.com" in viz


def test_preview_url_substitutes_variables(qapp: Any) -> None:
    """Finding A: Approve preview resolves ``{{baseUrl}}`` via the environment."""
    del qapp
    from services.ai.chat.tools.workspace_execute.tool import WorkspaceExecuteAction
    from services.collection_service import CollectionService
    from services.environment_service import EnvironmentService

    env = EnvironmentService.create_environment(
        "PreviewEnv",
        [{"key": "baseUrl", "value": "https://resolved.example.com", "enabled": True}],
    )
    coll = CollectionService.create_collection("AuditSub")
    req = CollectionService.create_request(
        int(coll.id),
        "POST",
        "{{baseUrl}}/login",
        "Login",
    )
    action = WorkspaceExecuteAction(
        operation="send_request",
        request_id=int(req.id),
        environment_id=int(env.id),
    )
    url = action.preview_url()
    assert url is not None
    assert "resolved.example.com" in url
    assert "{{" not in url


def test_preview_url_replay_history(qapp: Any) -> None:
    """Finding C: replay_history Approve preview shows the history entry URL."""
    del qapp
    from services.ai.chat.tools.workspace_execute.tool import WorkspaceExecuteAction
    from services.request_history_service import RequestHistoryService, SendIdentityDict
    from ui.styling.history_settings_manager import HistorySettingsManager

    identity: SendIdentityDict = {
        "request_id": None,
        "request_name": "ReplayMe",
        "method": "GET",
        "url": "https://replay.example.com/path",
    }
    entry_id = RequestHistoryService.record_send(
        identity=identity,
        response={
            "status_code": 200,
            "elapsed_ms": 1.0,
            "headers": [],
            "body": "ok",
            "request_url": "https://replay.example.com/path",
            "request_method": "GET",
        },
        original_request={"method": "GET", "url": "https://replay.example.com/path"},
        settings=HistorySettingsManager(),
    )
    assert entry_id is not None
    action = WorkspaceExecuteAction(operation="replay_history", history_entry_id=entry_id)
    url = action.preview_url()
    assert url is not None
    assert "replay.example.com" in url


def test_preview_url_send_draft(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Finding C: send_draft Approve preview uses the dirty tab URL from snapshot."""
    del qapp
    from services.ai.chat.tools.workspace_execute.tool import WorkspaceExecuteAction
    from services.ai.chat.workspace_snapshot import set_workspace_snapshot

    session_id = str(uuid.uuid4())
    monkeypatch.setattr(
        "services.ai.ai_config.AiConfig.get_chat_session_id",
        staticmethod(lambda: session_id),
    )
    set_workspace_snapshot(
        session_id,
        {
            "active_tab_index": 0,
            "active_collection_id": None,
            "current_env_id": None,
            "active_response": None,
            "tabs": [
                {
                    "index": 0,
                    "tab_type": "request",
                    "name": "Draft",
                    "request_id": None,
                    "collection_id": None,
                    "local_script_id": None,
                    "is_dirty": True,
                    "is_active": True,
                    "request_data": {
                        "method": "GET",
                        "url": "https://draft.example.com/v2",
                    },
                }
            ],
        },
    )
    action = WorkspaceExecuteAction(operation="send_draft")
    url = action.preview_url()
    assert url is not None
    assert "draft.example.com" in url
