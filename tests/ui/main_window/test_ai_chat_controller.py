"""Tests for AI chat controller finalize paths on the GUI thread."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QLabel

from services.ai.chat.run_registry import AiChatRunContext, ChatRunRegistry
from services.ai.chat.session_service import AiChatSessionDict
from ui.main_window.ai_chat_controller import _AiChatControllerMixin, _AiChatRunContext
from ui.sidebar import RightSidebar
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent


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


def _flush_stream_chunks(qtbot) -> None:
    """Wait for the coalesced chunk delivery timer (~50ms)."""
    qtbot.wait(60)


class _ChatControllerHost(_AiChatControllerMixin):
    """Minimal host exposing controller methods for panel integration tests."""

    def __init__(
        self,
        panel: AiChatPanel,
        session_id: str = "sess-1",
        *,
        sidebar: RightSidebar | None = None,
    ) -> None:
        """Wire a panel as the right-sidebar chat surface."""
        if sidebar is None:
            self._right_sidebar = cast(
                RightSidebar,
                SimpleNamespace(
                    ai_chat_panel=panel,
                    set_ai_session_title=lambda _title: None,
                    set_ai_session_title_rename_enabled=lambda _enabled: None,
                    ai_history_button=panel,
                ),
            )
        else:
            self._right_sidebar = sidebar
        self._active_ai_session_id = session_id
        self._manual_ai_session_titles = set()
        self._chat_run_generation = 0
        self._ai_chat_thread_generation = 0
        self._ai_title_thread_generation = 0
        self._active_run_context = None
        self._stopped_generations = {}
        self._chat_run_registry = ChatRunRegistry()
        self._pending_title_session_id = None
        self._pending_fork_composer = None
        self._session_load_generation = 0
        self._session_loader = SimpleNamespace(cancel=lambda: None, shutdown=lambda: None)  # type: ignore[assignment]


class _ControllerQObjectHost(QObject, _AiChatControllerMixin):
    """QObject-backed host used to exercise signal wiring."""

    _ai_assistant_finish_requested = Signal(str, int, str, str)
    _ai_chat_fail_requested = Signal(str, int, str, str, str)
    _ai_title_ready_requested = Signal(str)

    def __init__(self, sidebar: RightSidebar) -> None:
        """Initialise the real controller wiring against *sidebar*."""
        super().__init__()
        self._right_sidebar = sidebar
        self._init_ai_chat_controller()


class _FakeUsageWorker(QObject):
    """Minimal worker used to test ``usage_updated`` controller wiring."""

    chunk_received = Signal(str, str)
    assistant_finished = Signal(str, str)
    failed = Signal(str, str, str)
    status_changed = Signal(str)
    usage_updated = Signal(object)
    context_compacted = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._run_args: dict[str, object] = {}

    def set_run(self, **kwargs: object) -> None:
        self._run_args = kwargs

    def cancel(self) -> None:
        return

    def run(self) -> None:
        self.usage_updated.emit({"prompt_tokens": 7, "completion_tokens": 3})
        self.assistant_finished.emit("", "reply")


def _session_row(session_id: str, title: str) -> AiChatSessionDict:
    """Build a minimal session dict for controller title tests."""
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


def _cancellable_slow_worker_class():
    """Build a fake worker that sleeps briefly but exits promptly on cancel."""

    class _SlowWorker(_FakeUsageWorker):
        def __init__(self) -> None:
            super().__init__()
            self._cancelled = False

        def cancel(self) -> None:
            self._cancelled = True

        def run(self) -> None:
            import time

            for _ in range(50):
                if self._cancelled:
                    self.failed.emit("stopped", "", "")
                    return
                time.sleep(0.01)
            self.assistant_finished.emit("", "reply")

    return _SlowWorker


def test_sync_ai_session_title_uses_active_session(qapp: QApplication, qtbot) -> None:
    """Controller sync reads the active session title into flyout chrome."""
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ChatControllerHost(AiChatPanel(), session_id="sess-1", sidebar=sidebar)
    with (
        patch(
            "ui.main_window.ai_chat_controller.AiChatSessionService.get_session",
            return_value=_session_row("sess-1", "Go HTTP client"),
        ),
        patch(
            "ui.main_window.ai_chat_controller.AiChatSessionService.flyout_title_for_session",
            return_value="Go HTTP client",
        ),
    ):
        host._sync_ai_session_title()
    title = sidebar._flyout.findChild(QLabel, "aiChatSessionTitle")
    assert title is not None
    assert title.toolTip() == "Go HTTP client"


def test_on_ai_title_ready_updates_flyout_title(qapp: QApplication, qtbot) -> None:
    """Generated titles refresh the flyout subtitle for the active session."""
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ChatControllerHost(AiChatPanel(), session_id="sess-1", sidebar=sidebar)
    with (
        patch(
            "ui.main_window.ai_chat_controller.AiChatSessionService.rename_session",
        ) as rename,
        patch(
            "ui.main_window.ai_chat_controller.AiChatSessionService.get_session",
            return_value=_session_row("sess-1", "Generated title"),
        ),
        patch(
            "ui.main_window.ai_chat_controller.AiChatSessionService.flyout_title_for_session",
            return_value="Generated title",
        ),
    ):
        host._on_ai_title_ready("sess-1", "Generated title")
    rename.assert_called_once_with("sess-1", "Generated title")
    title = sidebar._flyout.findChild(QLabel, "aiChatSessionTitle")
    assert title is not None
    assert title.toolTip() == "Generated title"


def test_on_ai_session_title_renamed_persists_title(qapp: QApplication, qtbot) -> None:
    """Flyout inline rename persists through the session service."""
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ChatControllerHost(AiChatPanel(), session_id="sess-1", sidebar=sidebar)
    with (
        patch(
            "ui.main_window.ai_chat_controller.AiChatSessionService.rename_session",
        ) as rename,
        patch(
            "ui.main_window.ai_chat_controller.AiChatSessionService.get_session",
            return_value=_session_row("sess-1", "Custom title"),
        ),
        patch(
            "ui.main_window.ai_chat_controller.AiChatSessionService.flyout_title_for_session",
            return_value="Custom title",
        ),
    ):
        host._on_ai_session_title_renamed("Custom title")
    rename.assert_called_once_with("sess-1", "Custom title")
    title = sidebar._flyout.findChild(QLabel, "aiChatSessionTitle")
    assert title is not None
    assert title.toolTip() == "Custom title"


def test_on_ai_title_ready_skips_manual_rename(qapp: QApplication, qtbot) -> None:
    """Auto-generated titles do not overwrite a user-renamed session."""
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ChatControllerHost(AiChatPanel(), session_id="sess-1", sidebar=sidebar)
    host._manual_ai_session_titles.add("sess-1")
    with patch(
        "ui.main_window.ai_chat_controller.AiChatSessionService.rename_session",
    ) as rename:
        host._on_ai_title_ready("sess-1", "Generated title")
    rename.assert_not_called()


def test_init_ai_chat_controller_wires_transcript_refresh(
    qapp: QApplication, qtbot, monkeypatch
) -> None:
    """Transcript load completion triggers the panel context refresh callback."""
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    calls: list[object | None] = []

    def _record_refresh(sdk_metrics: object | None = None) -> None:
        calls.append(sdk_metrics)

    monkeypatch.setattr(sidebar.ai_chat_panel, "refresh_context_usage", _record_refresh)
    sidebar.ai_chat_panel.transcript_load_finished.emit()
    assert calls == [None]
    host._cleanup_ai_chat_threads()


def test_user_fork_prefills_composer_after_transcript_load(
    qapp: QApplication, qtbot, monkeypatch
) -> None:
    """Forking from a user message restores draft text when the transcript finishes loading."""
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
    forked_id = "fork-session-1"
    fork_result = {
        "session": {
            "id": forked_id,
            "title": "Chat (1)",
            "model_id": "m1",
            "mode": "agent",
            "agent_id": "postmark",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "last_preview": None,
            "archived": False,
        },
        "composer_draft": "Draft prompt",
    }

    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.fork_session_at_user_message",
        lambda _sid, _mid: fork_result,
    )

    def _activate_only(session_id: str) -> None:
        host._active_ai_session_id = session_id

    monkeypatch.setattr(host, "_activate_chat_session", _activate_only)
    host._active_ai_session_id = "source-session"
    host._on_user_fork_requested(42)
    assert host._pending_fork_composer == (forked_id, "Draft prompt")
    panel.transcript_load_finished.emit()
    assert panel._input.toPlainText() == "Draft prompt"
    assert host._pending_fork_composer is None
    host._cleanup_ai_chat_threads()


def test_usage_updated_signal_reaches_panel_refresh(qapp: QApplication, qtbot, monkeypatch) -> None:
    """Worker ``usage_updated`` signals flow through controller wiring into the panel."""
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
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
    refresh_calls: list[object | None] = []

    def _record_refresh(sdk_metrics: object | None = None) -> None:
        refresh_calls.append(sdk_metrics)

    monkeypatch.setattr(panel, "refresh_context_usage", _record_refresh)
    monkeypatch.setattr("services.ai.chat.run_registry.AiChatWorker", _FakeUsageWorker)
    host._on_ai_message_submitted("hello")
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 0, timeout=3000)

    assert refresh_calls
    assert {"prompt_tokens": 7, "completion_tokens": 3} in refresh_calls
    host._cleanup_ai_chat_threads()


def test_concurrent_send_in_second_session_while_first_runs(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second session can start while the first session worker is still running."""
    _SlowWorker = _cancellable_slow_worker_class()
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
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
    monkeypatch.setattr("services.ai.chat.run_registry.AiChatWorker", _SlowWorker)
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.record_user_message",
        lambda session_id, text, **kwargs: {
            "id": 1 if session_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" else 2,
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
        lambda entry, mode, first_message="": _session_row(
            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            first_message or "New",
        ),
    )

    host._active_ai_session_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    host._on_ai_message_submitted("first")
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 1, timeout=3000)

    host._active_ai_session_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    panel.begin_virtual_session(
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        {
            "messages": [],
            "has_older": False,
            "has_newer": False,
            "oldest_id": None,
            "newest_id": None,
        },
        session_model_id="m1",
    )
    host._on_ai_message_submitted("second")
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 2, timeout=3000)
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 0, timeout=5000)
    panel._shutdown_context_usage_worker()
    host._cleanup_ai_chat_threads()
    qtbot.wait(500)
    qapp.processEvents()


def test_stale_registry_release_is_ignored(qapp: QApplication, qtbot) -> None:
    """Late cleanup from an older chat run cannot drop a newer active handle."""
    from PySide6.QtCore import QThread

    from ui.sidebar.ai.workers.chat_worker import AiChatWorker

    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    registry = host._chat_run_registry
    old_thread = QThread()
    old_worker = AiChatWorker()
    new_thread = QThread()
    new_worker = AiChatWorker()
    ctx = AiChatRunContext("sess-1", 1, "hi", 1, "m1")
    registry._handles["sess-1"] = type(
        "H",
        (),
        {
            "context": ctx,
            "thread": new_thread,
            "worker": new_worker,
            "thread_generation": 2,
        },
    )()
    registry._release("sess-1", old_thread, old_worker, thread_generation=1)
    assert registry.is_running("sess-1")
    host._cleanup_ai_chat_threads()
    old_thread.deleteLater()
    new_thread.deleteLater()
    qapp.processEvents()


def test_session_switch_resets_context_ring(qapp: QApplication, qtbot, monkeypatch) -> None:
    """Switching sessions clears the previous ring fill immediately."""
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
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
    host._active_ai_session_id = "sess-1"
    panel.set_context_usage(64_000, 128_000)
    monkeypatch.setattr(host._session_loader, "load_tail", lambda *_args: None)

    host._activate_chat_session("sess-2")

    assert panel._context_ring.used_tokens() == 0
    assert panel._context_ring.total_tokens() == 128_000
    host._cleanup_ai_chat_threads()


def test_controller_stop_finalizes_streaming_rich_html(qapp: QApplication, qtbot) -> None:
    """User stop marshals through the controller and exits streaming with rich HTML."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _ChatControllerHost(panel, session_id="sess-1")
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "**Partial**")
    _flush_stream_chunks(qtbot)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.is_content_streaming()
    host._on_ai_chat_failed("sess-1", "stopped", "", "")
    assert not bubble.is_content_streaming()
    body = bubble.findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    html = body.toHtml().lower()
    assert "font-weight:600" in html or "font-weight:700" in html
    assert "stopped" in bubble.text().lower()


def test_controller_failure_finalizes_streaming_rich_html(qapp: QApplication, qtbot) -> None:
    """Provider failure preserves streamed text and renders rich markdown."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _ChatControllerHost(panel, session_id="sess-1")
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("trace", "")
    panel.append_assistant_chunk("", "**Hi**")
    _flush_stream_chunks(qtbot)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.is_content_streaming()
    host._on_ai_chat_failed("sess-1", "boom", "", "")
    assert not bubble.is_content_streaming()
    assert bubble.thinking_text() == "trace"
    body = bubble.findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    html = body.toHtml().lower()
    assert "font-weight:600" in html or "font-weight:700" in html
    assert "boom" in bubble.text().lower()


def test_handle_chat_stop_clears_busy_immediately_pre_stream(qapp: QApplication, qtbot) -> None:
    """Pre-stream stop rewinds the user bubble and restores the composer."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _ChatControllerHost(panel, session_id="sess-1")
    panel.add_message("user", "hello")
    panel.set_run_busy(True)
    panel.begin_assistant_stream()
    host._active_run_context = _AiChatRunContext("sess-1", 42, "hello", 1, "m1")
    host._chat_run_generation = 1

    with patch(
        "ui.main_window.ai_chat_controller.AiChatSessionService.delete_message",
        return_value=True,
    ) as delete_message:
        host._handle_chat_stop()

    delete_message.assert_called_once_with("sess-1", 42)
    assert panel._run_busy is False
    assert panel._input.toPlainText() == "hello"
    assert panel.findChildren(ChatMessageBubble) == []


def test_handle_chat_stop_finalizes_partial_post_stream(qapp: QApplication, qtbot) -> None:
    """Post-stream stop keeps partial text with a Stopped footer and clears busy."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _ChatControllerHost(panel, session_id="sess-1")
    panel.add_message("user", "hello")
    panel.set_run_busy(True)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "Partial")
    _flush_stream_chunks(qtbot)
    host._active_run_context = _AiChatRunContext("sess-1", 7, "hello", 2, "m1")
    host._chat_run_generation = 2

    host._handle_chat_stop()

    assert panel._run_busy is False
    assistant = next(b for b in panel.findChildren(ChatMessageBubble) if b.role == "assistant")
    assert "partial" in assistant.text().lower()
    assert "stopped" in assistant.text().lower()


def test_apply_worker_failed_ignored_after_pre_stream_stop(qapp: QApplication, qtbot) -> None:
    """Late worker Stopped signals do not recreate bubbles after pre-stream rollback."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _ChatControllerHost(panel, session_id="sess-1")
    panel.add_message("user", "hello")
    panel.set_run_busy(True)
    panel.begin_assistant_stream()
    host._active_run_context = _AiChatRunContext("sess-1", 11, "hello", 3, "m1")
    with patch(
        "ui.main_window.ai_chat_controller.AiChatSessionService.delete_message",
        return_value=True,
    ):
        host._handle_chat_stop()

    with patch(
        "ui.main_window.ai_chat_controller.AiChatSessionService.record_assistant_message",
    ) as record:
        host._apply_registry_failed("sess-1", 3, "Stopped", "", "")

    record.assert_not_called()
    assert panel.findChildren(ChatMessageBubble) == []


def test_usage_updated_refreshes_panel_breakdown(qapp: QApplication, qtbot) -> None:
    """Controller ``usage_updated`` wiring updates the panel ring breakdown."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models(
        [
            {
                "id": "gpt-test",
                "provider": "openai",
                "label": "GPT",
                "model": "openai/gpt-4o",
                "base_url": "",
                "api_version": "",
                "auth_kind": "none",
                "auth_ref": "",
                "context": 128_000,
            }
        ]
    )
    breakdown = {
        "used_tokens": 9000,
        "total_tokens": 128_000,
        "categories": [],
        "has_summarized": False,
        "is_estimated": False,
    }
    panel.refresh_context_usage(sdk_metrics=breakdown)
    assert panel._context_ring.used_tokens() == 9000


def test_new_chat_resets_context_ring(qapp: QApplication, qtbot) -> None:
    """New chat clears the context ring to empty usage."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models(
        [
            {
                "id": "gpt-test",
                "provider": "openai",
                "label": "GPT",
                "model": "openai/gpt-4o",
                "base_url": "",
                "api_version": "",
                "auth_kind": "none",
                "auth_ref": "",
                "context": 128_000,
            }
        ]
    )
    host = _ChatControllerHost(panel, session_id="sess-1")
    panel.set_context_usage(50_000, 128_000)
    host._on_ai_new_chat()
    assert panel._context_ring.used_tokens() == 0


def test_user_edit_submitted_truncates_and_resubmits(
    qapp: QApplication, qtbot, monkeypatch
) -> None:
    """Edit submit rewinds DB, truncates transcript, and starts a worker on the same user row."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models(
        [
            {
                "id": "gpt-test",
                "provider": "openai",
                "label": "GPT",
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
    panel.resize(400, 600)
    panel.show()
    host = _ChatControllerHost(panel, session_id="sess-edit")
    panel.add_message("user", "old", message_id=10)
    panel.add_message("assistant", "reply", message_id=11)
    assert panel.begin_inline_edit(10) is True
    state = panel._inline_edit
    assert state is not None
    state.composer.restore_text("new")

    rewind_calls: list[tuple] = []
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.count_messages_after",
        lambda _sid, _mid: 0,
    )

    def _rewind(session_id: str, message_id: int, text: str, snapshot: object) -> bool:
        rewind_calls.append((session_id, message_id, text))
        return True

    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.edit_user_message_and_rewind",
        _rewind,
    )

    class _FakeEditWorker(_FakeUsageWorker):
        """Worker stub that does not auto-finish (avoids QObject delivery in this test)."""

        def run(self) -> None:
            return

    monkeypatch.setattr("services.ai.chat.run_registry.AiChatWorker", _FakeEditWorker)
    monkeypatch.setattr(
        "services.ai.chat.run_registry.QThread.start",
        lambda self: None,
    )

    host._on_user_edit_submitted(10, "new")
    assert rewind_calls == [("sess-edit", 10, "new")]
    assert panel._inline_edit is None
    assert panel._bubble_by_message_id.get(11) is None
    assert panel._bubble_by_message_id.get(10) is not None
    assert panel._run_busy is True


def test_hard_budget_blocks_message_submit(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hard budget cap prevents starting a new assistant run."""
    from services.ai.chat.budget_status import ConnectionBudgetStatus

    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    host._active_ai_session_id = "sess-budget"
    panel = sidebar.ai_chat_panel
    panel.set_models(
        [
            {
                "id": "m1",
                "provider": "openai",
                "label": "GPT-4o",
                "model": "openai/gpt-4o",
                "base_url": "",
                "api_version": "",
                "auth_kind": "token",
                "auth_ref": "ref-a",
                "context": 128_000,
                "enabled": True,
            }
        ]
    )
    record_calls: list[tuple] = []

    def _record_user_message(session_id: str, text: str, **kwargs: object) -> dict[str, object]:
        record_calls.append((session_id, text))
        return {"id": 1, "session_id": session_id, "role": "user", "content": text}

    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.record_user_message",
        _record_user_message,
    )
    hard_status = ConnectionBudgetStatus(
        connection_key="ref-a",
        provider_label="OpenAI",
        rated=True,
        period="monthly",
        period_reset_label="monthly on the 1st at 00:00",
        period_known_usd=1.0,
        period_usd=1.0,
        partial_period=False,
        soft_limit_usd=0.53,
        hard_limit_usd=1.0,
        state="hard_exceeded",
        dedupe_key="ref-a:2026-07-01T00:00:00",
    )
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.connection_budget_status",
        lambda _entry, **kwargs: hard_status,
    )

    host._on_ai_message_submitted("hello")
    assert record_calls == []
    assert host._chat_run_registry.count_running() == 0
    host._cleanup_ai_chat_threads()


def test_apply_session_chrome_prefers_stored_chat_model(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Restoring a session keeps the persisted composer model, not stale session.model_id."""
    from services.ai.ai_config import AiConfig

    AiConfig.set_chat_model_id("gpt-55")
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    panel = sidebar.ai_chat_panel
    host = _ChatControllerHost(panel, session_id="sess-restore", sidebar=sidebar)
    panel.set_models(
        [
            {
                "id": "gpt-55",
                "provider": "openai",
                "label": "gpt-5.5",
                "model": "openai/gpt-5.5",
                "base_url": "",
                "api_version": "",
                "auth_kind": "none",
                "auth_ref": "",
                "context": 128_000,
                "enabled": True,
            },
            {
                "id": "oss-1",
                "provider": "ollama",
                "label": "gpt-oss",
                "model": "ollama/gpt-oss:20b",
                "base_url": "",
                "api_version": "",
                "auth_kind": "none",
                "auth_ref": "",
                "context": 128_000,
                "enabled": True,
            },
        ]
    )
    session = _session_row("sess-restore", "Linux vs macOS")
    session["model_id"] = "oss-1"
    host._apply_session_chrome(session)
    assert panel.current_model_id() == "gpt-55"
    assert "gpt-5.5" in panel._model_button_label()
    AiConfig.set_chat_model_id("")


def test_activate_session_does_not_cancel_background_run(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Switching sessions leaves an in-flight worker running in the background."""
    _SlowWorker = _cancellable_slow_worker_class()
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
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
    monkeypatch.setattr("services.ai.chat.run_registry.AiChatWorker", _SlowWorker)
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.record_user_message",
        lambda session_id, text, **kwargs: {
            "id": 1,
            "session_id": session_id,
            "role": "user",
            "content": text,
        },
    )
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.get_session",
        lambda session_id: _session_row(session_id, "Title"),
    )
    cancel_calls: list[str] = []
    original_cancel = host._chat_run_registry.cancel

    def _track_cancel(session_id: str) -> None:
        cancel_calls.append(session_id)
        original_cancel(session_id)

    monkeypatch.setattr(host._chat_run_registry, "cancel", _track_cancel)
    monkeypatch.setattr(host._session_loader, "load_tail", lambda *_args, **_kwargs: None)

    session_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    session_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    host._active_ai_session_id = session_a
    host._on_ai_message_submitted("first")
    qtbot.waitUntil(lambda: host._chat_run_registry.is_running(session_a), timeout=3000)

    host._activate_chat_session(session_b)
    assert session_a not in cancel_calls
    assert host._chat_run_registry.is_running(session_a)
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 0, timeout=5000)
    panel._shutdown_context_usage_worker()
    host._cleanup_ai_chat_threads()
    qtbot.wait(500)
    qapp.processEvents()


def test_background_finish_persists_without_end_assistant_stream(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Background session completion persists to SQLite without touching the visible stream."""
    from services.ai.chat.run_registry import ChatRunHandle

    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
    session_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    session_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    host._active_ai_session_id = session_b

    ctx = AiChatRunContext(session_a, 1, "hi", 1, "m1")
    host._chat_run_registry._handles[session_a] = ChatRunHandle(
        context=ctx,
        thread=None,  # type: ignore[arg-type]
        worker=None,  # type: ignore[arg-type]
        thread_generation=1,
        bridge=None,  # type: ignore[arg-type]
        thinking_buffer="",
        content_buffer="partial",
    )

    end_calls: list[object] = []
    monkeypatch.setattr(
        panel,
        "end_assistant_stream",
        lambda *args, **kwargs: end_calls.append((args, kwargs)),
    )
    persist_calls: list[dict[str, object]] = []

    def _record_persist(*args, **kwargs) -> None:
        persist_calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(host, "_persist_assistant_turn", _record_persist)

    host._apply_registry_assistant_finished(session_a, 1, "", "background reply")
    assert end_calls == []
    assert persist_calls
    first_kwargs = persist_calls[0].get("kwargs")
    assert isinstance(first_kwargs, dict)
    assert first_kwargs.get("update_panel") is False
    host._chat_run_registry._handles.pop(session_a, None)
    host._cleanup_ai_chat_threads()


def test_reattach_replays_background_buffers(qapp: QApplication, qtbot) -> None:
    """Switching back to a running session resumes streaming from buffered chunks."""
    from services.ai.chat.run_registry import ChatRunHandle

    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
    session_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    host._active_ai_session_id = session_a

    ctx = AiChatRunContext(session_a, 1, "hi", 1, "m1")
    host._chat_run_registry._handles[session_a] = ChatRunHandle(
        context=ctx,
        thread=None,  # type: ignore[arg-type]
        worker=None,  # type: ignore[arg-type]
        thread_generation=1,
        bridge=None,  # type: ignore[arg-type]
        thinking_buffer="thought",
        content_buffer="answer",
        status_text="Planning",
    )

    resume_calls: list[tuple[str, str, str]] = []

    def _resume(
        thinking: str,
        content: str,
        *,
        status: str = "",
        subagent_records: object = None,
        tool_activity_records: object = None,
    ) -> None:
        resume_calls.append((thinking, content, status))

    panel.resume_assistant_stream = _resume  # type: ignore[method-assign]
    host._reattach_session_run_if_needed(session_a)
    assert resume_calls == [("thought", "answer", "Planning")]
    host._chat_run_registry._handles.pop(session_a, None)
    host._cleanup_ai_chat_threads()


def test_concurrency_warn_allows_send_past_advisory_limit(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At the advisory limit, additional sends warn but still start workers."""
    _SlowWorker = _cancellable_slow_worker_class()
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    panel = sidebar.ai_chat_panel
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
    monkeypatch.setattr("services.ai.chat.run_registry.AiChatWorker", _SlowWorker)
    monkeypatch.setattr(
        "ui.main_window.ai_chat_runs.max_concurrent_chat_runs",
        lambda: 1,
    )
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.record_user_message",
        lambda session_id, text, **kwargs: {
            "id": hash(session_id) % 1000,
            "session_id": session_id,
            "role": "user",
            "content": text,
        },
    )
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.AiChatSessionService.get_session",
        lambda session_id: _session_row(session_id, "Title"),
    )
    warn_messages: list[str] = []
    monkeypatch.setattr(
        "ui.main_window.ai_chat_runs.QMessageBox.warning",
        lambda *_args, **kwargs: warn_messages.append(
            str(kwargs.get("text") or (_args[2] if len(_args) > 2 else ""))
        ),
    )

    sessions = [
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    ]
    host._active_ai_session_id = sessions[0]
    host._on_ai_message_submitted("first")
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 1, timeout=3000)

    host._active_ai_session_id = sessions[1]
    panel.begin_virtual_session(
        sessions[1],
        {
            "messages": [],
            "has_older": False,
            "has_newer": False,
            "oldest_id": None,
            "newest_id": None,
        },
        session_model_id="m1",
    )
    host._on_ai_message_submitted("second")
    assert warn_messages
    assert host._chat_run_registry.count_running() == 2
    qtbot.waitUntil(lambda: host._chat_run_registry.count_running() == 0, timeout=5000)
    panel._shutdown_context_usage_worker()
    host._cleanup_ai_chat_threads()
    qtbot.wait(500)
    qapp.processEvents()
