"""Tests for AI chat controller finalize paths on the GUI thread."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QLabel

from ui.main_window.ai_chat_controller import _AiChatControllerMixin, _AiChatRunContext
from ui.sidebar import RightSidebar
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent


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
        self._ai_chat_worker = None
        self._ai_chat_thread = None
        self._pending_title_session_id = None
        self._pending_fork_composer = None
        self._session_load_generation = 0
        self._session_loader = SimpleNamespace(cancel=lambda: None, shutdown=lambda: None)  # type: ignore[assignment]


class _ControllerQObjectHost(QObject, _AiChatControllerMixin):
    """QObject-backed host used to exercise signal wiring."""

    _ai_assistant_finish_requested = Signal(str, str)
    _ai_chat_fail_requested = Signal(str, str, str)
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


def _session_row(session_id: str, title: str) -> dict[str, Any]:
    """Build a minimal session dict for controller title tests."""
    return {
        "id": session_id,
        "title": title,
        "model_id": "gpt-test",
        "mode": "agent",
        "agent_id": "postmark-assistant",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "last_preview": None,
        "archived": False,
    }


def test_sync_ai_session_title_uses_active_session(qapp: QApplication, qtbot) -> None:
    """Controller sync reads the active session title into flyout chrome."""
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ChatControllerHost(AiChatPanel(), session_id="sess-1", sidebar=sidebar)
    with patch(
        "ui.main_window.ai_chat_controller.AiChatSessionService.get_session",
        return_value=_session_row("sess-1", "Go HTTP client"),
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
    monkeypatch.setattr("ui.main_window.ai_chat_controller.AiChatWorker", _FakeUsageWorker)
    host._on_ai_message_submitted("hello")
    qtbot.waitUntil(lambda: host._ai_chat_thread is None, timeout=3000)

    assert refresh_calls
    assert {"prompt_tokens": 7, "completion_tokens": 3} in refresh_calls
    host._cleanup_ai_chat_threads()


def test_back_to_back_send_waits_for_prior_thread_cleanup(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second send can start after the first worker thread has fully stopped."""
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
    monkeypatch.setattr("ui.main_window.ai_chat_controller.AiChatWorker", _FakeUsageWorker)
    host._on_ai_message_submitted("first")
    qtbot.waitUntil(lambda: host._ai_chat_thread is None, timeout=3000)
    host._on_ai_message_submitted("second")
    assert host._ai_chat_thread is not None
    qtbot.waitUntil(lambda: host._ai_chat_thread is None, timeout=3000)
    host._cleanup_ai_chat_threads()


def test_stale_chat_thread_finished_is_ignored(qapp: QApplication, qtbot) -> None:
    """Late cleanup from an older chat run cannot delete the active worker thread."""
    from PySide6.QtCore import QThread

    from ui.sidebar.ai.workers.chat_worker import AiChatWorker

    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    host = _ControllerQObjectHost(sidebar)
    old_thread = QThread()
    old_worker = AiChatWorker()
    new_thread = QThread()
    new_worker = AiChatWorker()
    host._ai_chat_thread_generation = 2
    host._ai_chat_thread = new_thread
    host._ai_chat_worker = new_worker
    host._release_ai_chat_thread(old_thread, old_worker, generation=1)
    assert host._ai_chat_thread is new_thread
    assert host._ai_chat_worker is new_worker
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
    host = _ChatControllerHost(panel)
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
    host = _ChatControllerHost(panel)
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
    host = _ChatControllerHost(panel)
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
    host = _ChatControllerHost(panel)
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
    host = _ChatControllerHost(panel)
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
        host._apply_ai_worker_failed("Stopped", "", "")

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

    monkeypatch.setattr("ui.main_window.ai_chat_controller.AiChatWorker", _FakeEditWorker)
    monkeypatch.setattr(
        "ui.main_window.ai_chat_controller.QThread.start",
        lambda self: None,
    )

    host._on_user_edit_submitted(10, "new")
    assert rewind_calls == [("sess-edit", 10, "new")]
    assert panel._inline_edit is None
    assert panel._bubble_by_message_id.get(11) is None
    assert panel._bubble_by_message_id.get(10) is not None
    assert panel._run_busy is True
