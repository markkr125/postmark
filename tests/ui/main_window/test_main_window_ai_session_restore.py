"""Regression tests for reopening the last AI chat session after restart."""

from __future__ import annotations

import uuid

import pytest
from PySide6.QtWidgets import QApplication

from database.models.ai_chat.ai_chat_repository import append_message, create_session
from services.ai.ai_config import AiConfig, AiModelEntry
from services.ai.chat.session_service import AiChatSessionDict, AiChatSessionService
from tests.ui.main_window.test_ai_chat_controller import (
    _ControllerQObjectHost,
    _FakeUsageWorker,
)
from ui.sidebar import RightSidebar
from ui.sidebar.ai.message_bubble import ChatMessageBubble


def _model_entry() -> AiModelEntry:
    return AiModelEntry(
        id="gpt-test",
        provider="openai",
        label="GPT",
        model="openai/gpt-4o",
        base_url="",
        api_version="",
        auth_kind="none",
        auth_ref="",
        context=128_000,
        enabled=True,
    )


def _session_row(session_id: str, title: str) -> AiChatSessionDict:
    return AiChatSessionDict(
        id=session_id,
        title=title,
        model_id="gpt-test",
        mode="agent",
        agent_id="postmark-assistant",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        last_preview=None,
        archived=False,
    )


def _user_bubbles(panel: object) -> list[ChatMessageBubble]:
    layout = panel._messages_layout  # type: ignore[attr-defined]
    return [
        layout.itemAt(index).widget()
        for index in range(layout.count())
        if layout.itemAt(index) is not None
        and isinstance(layout.itemAt(index).widget(), ChatMessageBubble)
        and layout.itemAt(index).widget().role == "user"  # type: ignore[union-attr]
    ]


def test_first_message_persists_chat_session_id(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sending the first message in a new chat must write ai/chat_session_id."""
    AiConfig.set_chat_session_id("")
    entry = _model_entry()
    monkeypatch.setattr(AiConfig, "get_models", lambda *_a, **_kw: [entry])
    monkeypatch.setattr(AiConfig, "get_chat_model_id", lambda: entry["id"])

    new_session_id = str(uuid.uuid4())
    monkeypatch.setattr(
        AiChatSessionService,
        "new_session",
        lambda *_a, **_kw: _session_row(new_session_id, "hello"),
    )
    monkeypatch.setattr(
        AiChatSessionService,
        "record_user_message",
        lambda session_id, text, **kwargs: {
            "id": 1,
            "session_id": session_id,
            "role": "user",
            "content": text,
        },
    )
    monkeypatch.setattr(
        AiChatSessionService,
        "get_session",
        lambda session_id: _session_row(session_id, "hello"),
    )
    monkeypatch.setattr("services.ai.chat.run_registry.AiChatWorker", _FakeUsageWorker)

    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    sidebar.ai_chat_panel.set_models([entry])

    host._on_ai_message_submitted("hello")
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 0, timeout=3000)

    assert AiConfig.get_chat_session_id() == new_session_id
    assert not AiConfig.is_chat_session_restore_cleared()
    assert host._active_ai_session_id == new_session_id
    host._cleanup_ai_chat_threads()


def test_restore_active_chat_session_loads_persisted_transcript(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_restore_active_chat_session`` reloads the id stored in QSettings."""
    entry = _model_entry()
    monkeypatch.setattr(AiConfig, "get_models", lambda *_a, **_kw: [entry])
    monkeypatch.setattr(AiConfig, "get_chat_model_id", lambda: entry["id"])

    session_id = str(uuid.uuid4())
    create_session(
        session_id=session_id,
        title="Restore me",
        model_id=entry["id"],
        mode="agent",
    )
    append_message(session_id=session_id, role="user", content="Remember me on restart")
    append_message(session_id=session_id, role="assistant", content="Will do")
    AiConfig.set_chat_session_id(session_id)

    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    sidebar.ai_chat_panel.set_models([entry])
    sidebar.ai_chat_panel.resize(420, 640)

    host._restore_active_chat_session()
    panel = sidebar.ai_chat_panel
    qtbot.waitUntil(lambda: host._active_ai_session_id == session_id, timeout=5000)
    qtbot.waitUntil(lambda: not panel.is_transcript_load_active(), timeout=5000)
    qapp.processEvents()

    user_bubbles = _user_bubbles(panel)
    assert len(user_bubbles) == 1
    assert user_bubbles[0].text() == "Remember me on restart"

    host._cleanup_ai_chat_threads()
    panel.cancel_transcript_load()
    panel._shutdown_context_usage_worker()
    qapp.processEvents()


def test_restore_active_chat_session_falls_back_without_persisted_id(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sessions created before restore-id persistence still reopen on startup."""
    entry = _model_entry()
    monkeypatch.setattr(AiConfig, "get_models", lambda *_a, **_kw: [entry])
    monkeypatch.setattr(AiConfig, "get_chat_model_id", lambda: entry["id"])

    session_id = str(uuid.uuid4())
    create_session(
        session_id=session_id,
        title="Legacy session",
        model_id=entry["id"],
        mode="agent",
    )
    append_message(session_id=session_id, role="user", content="Opened before persistence")
    append_message(session_id=session_id, role="assistant", content="Still here")

    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    sidebar.ai_chat_panel.set_models([entry])
    sidebar.ai_chat_panel.resize(420, 640)

    host._restore_active_chat_session()
    panel = sidebar.ai_chat_panel
    qtbot.waitUntil(lambda: host._active_ai_session_id == session_id, timeout=5000)
    qtbot.waitUntil(lambda: not panel.is_transcript_load_active(), timeout=5000)

    assert _user_bubbles(panel)[0].text() == "Opened before persistence"

    host._cleanup_ai_chat_threads()
    panel.cancel_transcript_load()
    panel._shutdown_context_usage_worker()
    qapp.processEvents()
