"""End-to-end controller tests for concurrent AI chat runs."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from services.ai.chat.session_service import AiChatSessionDict
from ui.main_window.ai_chat_controller import _AiChatControllerMixin
from ui.sidebar import RightSidebar


class _FakeUsageWorker(QObject):
    """Minimal worker used to exercise concurrent run orchestration."""

    chunk_received = Signal(str, str)
    assistant_finished = Signal(str, str)
    failed = Signal(str, str, str)
    status_changed = Signal(str)
    usage_updated = Signal(object)
    context_compacted = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._cancelled = False

    def set_run(self, **kwargs: object) -> None:
        self._kwargs = kwargs

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        for _ in range(80):
            if self._cancelled:
                self.failed.emit("stopped", "", "")
                return
            time.sleep(0.01)
        self.assistant_finished.emit("", "reply")


class _ControllerQObjectHost(QObject, _AiChatControllerMixin):
    """QObject-backed host used to exercise real controller wiring."""

    _ai_assistant_finish_requested = Signal(str, int, str, str)
    _ai_chat_fail_requested = Signal(str, int, str, str, str)
    _ai_title_ready_requested = Signal(str)

    def __init__(self, sidebar: RightSidebar) -> None:
        """Initialise the real controller wiring against *sidebar*."""
        super().__init__()
        self._right_sidebar = sidebar
        self._init_ai_chat_controller()


def _session_row(session_id: str, title: str) -> AiChatSessionDict:
    """Build a minimal session dict for concurrent-run tests."""
    return AiChatSessionDict(
        id=session_id,
        title=title,
        model_id="m1",
        mode="agent",
        agent_id="postmark-assistant",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        last_preview=None,
        archived=False,
    )


def _enable_models(panel) -> None:
    """Install one enabled model on the chat panel."""
    panel.set_models(
        [
            {
                "id": "m1",
                "provider": "openai",
                "label": "GPT-4o",
                "model": "openai/gpt-4o",
                "base_url": "",
                "api_version": "",
                "auth_kind": "none",
                "auth_ref": "",
                "context": 128_000,
                "enabled": True,
            }
        ]
    )


@pytest.fixture(autouse=True)
def _shutdown_ai_sidebar_workers(qtbot, qapp) -> Iterator[None]:
    """Stop context-usage loader threads left by controller integration tests."""
    yield
    for widget in qapp.topLevelWidgets():
        panel = getattr(widget, "ai_chat_panel", None)
        if panel is not None and hasattr(panel, "_shutdown_context_usage_worker"):
            panel._shutdown_context_usage_worker()
    qtbot.wait(200)
    qapp.processEvents()


def _wire_session_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_a: str,
    session_b: str,
) -> None:
    """Patch session service helpers for two parallel chat sessions."""
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.record_user_message",
        lambda session_id, text, **kwargs: {
            "id": 1 if session_id == session_a else 2,
            "session_id": session_id,
            "role": "user",
            "content": text,
        },
    )
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.get_session",
        lambda session_id: _session_row(session_id, "Title"),
    )
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.new_session",
        lambda entry, mode, first_message="": _session_row(session_b, first_message or "New"),
    )


def test_new_chat_clears_composer_busy_while_background_run_continues(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """New chat must re-enable Send while the previous session worker keeps running."""
    session_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    session_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    monkeypatch.setattr("services.ai.chat.run_registry.AiChatWorker", _FakeUsageWorker)
    _wire_session_mocks(monkeypatch, session_a=session_a, session_b=session_b)

    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
    _enable_models(panel)

    host._active_ai_session_id = session_a
    host._on_ai_message_submitted("first")
    qtbot.waitUntil(lambda: host._chat_run_registry.is_running(session_a), timeout=3000)
    assert panel._run_busy

    host._on_ai_new_chat()
    assert not panel._run_busy
    assert host._chat_run_registry.is_running(session_a)
    assert host._chat_run_registry.count_running() == 1

    panel._shutdown_context_usage_worker()
    host._cleanup_ai_chat_threads()
    qtbot.wait(500)
    qapp.processEvents()


def test_new_chat_then_docked_send_starts_second_concurrent_run(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After New chat, Enter/Send must start a second worker — not Stop the first session."""
    session_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    session_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    monkeypatch.setattr("services.ai.chat.run_registry.AiChatWorker", _FakeUsageWorker)
    _wire_session_mocks(monkeypatch, session_a=session_a, session_b=session_b)

    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
    _enable_models(panel)

    stop_calls: list[bool] = []
    panel.stop_requested.connect(lambda: stop_calls.append(True))

    host._active_ai_session_id = session_a
    host._on_ai_message_submitted("first")
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 1, timeout=3000)

    host._on_ai_new_chat()
    assert not panel._run_busy

    panel._docked_composer.restore_text("second")
    panel._on_docked_send()
    assert stop_calls == []
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 2, timeout=3000)
    assert host._chat_run_registry.is_running(session_a)
    assert host._chat_run_registry.is_running(session_b)

    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 0, timeout=5000)
    panel._shutdown_context_usage_worker()
    host._cleanup_ai_chat_threads()
    qtbot.wait(500)
    qapp.processEvents()


def test_activate_idle_session_clears_composer_busy_while_other_runs(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Switching to an idle session re-enables Send while another session keeps running."""
    session_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    session_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    monkeypatch.setattr("services.ai.chat.run_registry.AiChatWorker", _FakeUsageWorker)
    _wire_session_mocks(monkeypatch, session_a=session_a, session_b=session_b)
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    monkeypatch.setattr(host._session_loader, "load_tail", lambda *_args, **_kwargs: None)
    panel = sidebar.ai_chat_panel
    _enable_models(panel)

    host._active_ai_session_id = session_a
    host._on_ai_message_submitted("first")
    qtbot.waitUntil(lambda: host._chat_run_registry.is_running(session_a), timeout=3000)
    assert panel._run_busy

    host._activate_chat_session(session_b)
    assert not panel._run_busy
    assert host._chat_run_registry.is_running(session_a)

    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 0, timeout=5000)
    panel._shutdown_context_usage_worker()
    host._cleanup_ai_chat_threads()
    qtbot.wait(500)
    qapp.processEvents()


def test_activate_running_session_restores_composer_busy(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Switching back to a running session shows Stop again for that session."""
    session_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    session_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    monkeypatch.setattr("services.ai.chat.run_registry.AiChatWorker", _FakeUsageWorker)
    _wire_session_mocks(monkeypatch, session_a=session_a, session_b=session_b)

    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
    _enable_models(panel)

    host._active_ai_session_id = session_a
    host._on_ai_message_submitted("first")
    qtbot.waitUntil(lambda: host._chat_run_registry.is_running(session_a), timeout=3000)

    host._on_ai_new_chat()
    host._on_ai_message_submitted("second")
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 2, timeout=3000)

    host._active_ai_session_id = session_a
    host._update_active_session_busy_state()
    assert panel._run_busy

    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 0, timeout=5000)
    panel._shutdown_context_usage_worker()
    host._cleanup_ai_chat_threads()
    qtbot.wait(500)
    qapp.processEvents()
