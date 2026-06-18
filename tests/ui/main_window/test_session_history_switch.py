"""Regression tests for AI session history switching through MainWindow."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator

import pytest
from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from database.models.ai_chat.ai_chat_repository import append_message, create_session
from services.ai.ai_config import AiConfig, AiModelEntry
from services.ai.chat.session_service import AiChatSessionDict, AiChatSessionService
from tests.ui.conftest import finish_main_window_startup
from ui.main_window.window import MainWindow
from ui.sidebar.ai.chat_sessions.history_popup import AiSessionHistoryPopup
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


def _seed_sessions(count: int, *, turns: int) -> list[str]:
    """Persist *count* chat sessions each with *turns* user/assistant pairs."""
    session_ids: list[str] = []
    for index in range(count):
        session_id = str(uuid.uuid4())
        create_session(
            session_id=session_id,
            title=f"History switch {index}",
            model_id="gpt-test",
            mode="agent",
        )
        for turn in range(turns):
            append_message(
                session_id=session_id,
                role="user" if turn % 2 == 0 else "assistant",
                content=f"session {index} turn {turn}",
            )
        session_ids.append(session_id)
    return session_ids


def _session_rows(session_ids: list[str]) -> list[AiChatSessionDict]:
    """Load session dict rows for the history popover."""
    rows: list[AiChatSessionDict] = []
    for session_id in session_ids:
        row = AiChatSessionService.get_session(session_id)
        assert row is not None
        rows.append(row)
    return rows


def _user_bubbles_in_transcript_layout(panel: object) -> list[ChatMessageBubble]:
    """Return user rows still owned by the transcript ``QVBoxLayout``."""
    layout = panel._messages_layout  # type: ignore[attr-defined]
    bubbles: list[ChatMessageBubble] = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if isinstance(widget, ChatMessageBubble) and widget.role == "user":
            bubbles.append(widget)
    return bubbles


@pytest.fixture()
def _qt_mapto_warning_guard() -> Iterator[Callable[[], list[str]]]:
    """Collect Qt warnings about broken ``mapTo`` ancestry during a test."""
    captured: list[str] = []

    def _handler(_mode: QtMsgType, _context: object, message: str) -> None:
        if "mapTo" in message and "parent must be in parent hierarchy" in message:
            captured.append(message)

    previous = qInstallMessageHandler(_handler)

    def _assert_clean() -> list[str]:
        qInstallMessageHandler(previous)
        return captured

    yield _assert_clean


def test_main_window_history_row_switch_during_transcript_load(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    _qt_mapto_warning_guard: Callable[[], list[str]],
) -> None:
    """Picking another session while the transcript builds must not map torn-down bubbles."""
    entry = _model_entry()
    monkeypatch.setattr(AiConfig, "get_models", lambda *_a, **_kw: [entry])
    monkeypatch.setattr(AiConfig, "get_chat_model_id", lambda: entry["id"])

    session_ids = _seed_sessions(4, turns=10)
    AiConfig.set_chat_session_id(session_ids[0])

    window = MainWindow()
    qtbot.addWidget(window)
    finish_main_window_startup(window)
    window._right_sidebar.open_panel("ai")
    qtbot.waitExposed(window._right_sidebar)
    panel = window._right_sidebar.ai_chat_panel
    panel.resize(420, 640)
    qapp.processEvents()

    popup = AiSessionHistoryPopup.instance()
    anchor = window._right_sidebar.ai_history_button
    rows = _session_rows(session_ids)

    try:
        for _round in range(6):
            for session_id in session_ids:
                popup.show_for(
                    anchor,
                    rows,
                    window._on_ai_session_selected,
                    active_session_id=window._active_ai_session_id,
                )
                row = session_ids.index(session_id)
                popup._on_row_activated(popup._model.index(row, 0))
                for _ in range(35):
                    qapp.processEvents()
                qtbot.wait(5)
    finally:
        popup.hide_popup()
        window._cleanup_ai_chat_threads()
        panel.cancel_transcript_load()
        panel._shutdown_context_usage_worker()
        qapp.processEvents()

    mapto_warnings = _qt_mapto_warning_guard()
    assert mapto_warnings == [], "\n".join(mapto_warnings)


def test_user_bubble_height_after_session_switch(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A short user prompt stays compact after switching sessions (layout chrome intact)."""
    entry = _model_entry()
    monkeypatch.setattr(AiConfig, "get_models", lambda *_a, **_kw: [entry])
    monkeypatch.setattr(AiConfig, "get_chat_model_id", lambda: entry["id"])

    session_a = str(uuid.uuid4())
    session_b = str(uuid.uuid4())
    for session_id, title in ((session_a, "test"), (session_b, "other")):
        create_session(session_id=session_id, title=title, model_id="gpt-test", mode="agent")
        append_message(session_id=session_id, role="user", content=title)
        append_message(session_id=session_id, role="assistant", content=f"reply to {title}")

    AiConfig.set_chat_session_id(session_a)

    window = MainWindow()
    qtbot.addWidget(window)
    finish_main_window_startup(window)
    window._right_sidebar.open_panel("ai")
    panel = window._right_sidebar.ai_chat_panel
    panel.resize(420, 640)
    qtbot.waitExposed(panel)

    window._activate_chat_session(session_b)
    qtbot.waitUntil(lambda: not panel.is_transcript_load_active(), timeout=5000)
    window._activate_chat_session(session_a)
    qtbot.waitUntil(lambda: not panel.is_transcript_load_active(), timeout=5000)
    qapp.processEvents()

    user_bubbles = _user_bubbles_in_transcript_layout(panel)
    assert len(user_bubbles) == 1
    bubble = user_bubbles[0]
    assert bubble.text() == "test"
    assert bubble.sizeHint().height() < 120
    assert bubble.height() < 160, f"user bubble layout height {bubble.height()}px"

    window._cleanup_ai_chat_threads()
    panel.cancel_transcript_load()
    panel._shutdown_context_usage_worker()
    qapp.processEvents()
