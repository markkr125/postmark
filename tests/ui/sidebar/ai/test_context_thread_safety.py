"""Thread-safety tests for AI chat context usage refresh."""

from __future__ import annotations

import threading

import pytest
from PySide6.QtCore import QThread, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from ui.sidebar.ai.chat_panel.panel import AiChatPanel

_TIMER_WARNINGS = (
    "QObject::killTimer: Timers cannot be stopped from another thread",
    "QObject::startTimer: Timers cannot be started from another thread",
)


@pytest.fixture
def _panel(qapp: QApplication, qtbot) -> AiChatPanel:
    """Return a panel with one enabled model."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
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
    return panel


def test_refresh_from_worker_thread_marshals_to_gui(
    qapp: QApplication, qtbot, _panel: AiChatPanel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cross-thread refresh requests do not touch QTimer off the GUI thread."""
    warnings: list[str] = []
    previous = qInstallMessageHandler(lambda _mode, _context, message: warnings.append(message))
    started = threading.Event()
    done = threading.Event()

    def _worker() -> None:
        started.set()
        _panel.deliver_context_usage_metrics({"prompt_tokens": 3, "completion_tokens": 2})
        done.set()

    try:
        thread = threading.Thread(target=_worker)
        thread.start()
        assert started.wait(timeout=2)
        qtbot.waitUntil(done.is_set, timeout=3000)
        thread.join(timeout=2)
        qtbot.wait(250)
        assert not any(warn in message for message in warnings for warn in _TIMER_WARNINGS)
    finally:
        qInstallMessageHandler(previous)
        _panel._shutdown_context_usage_worker()


def test_stale_context_thread_finished_is_ignored(
    qapp: QApplication, qtbot, _panel: AiChatPanel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A late ``finished`` from an older context worker cannot delete the active thread."""
    from ui.sidebar.ai.workers.context_usage_worker import ContextUsageWorker

    old_thread = QThread()
    old_worker = ContextUsageWorker()
    old_worker.moveToThread(old_thread)
    _panel._context_usage_thread = old_thread
    _panel._context_usage_worker = old_worker
    _panel._context_refresh_generation = 1

    new_thread = QThread()
    new_worker = ContextUsageWorker()
    new_worker.moveToThread(new_thread)
    _panel._context_usage_thread = new_thread
    _panel._context_usage_worker = new_worker
    _panel._context_refresh_generation = 2

    _panel._release_context_usage_thread(old_thread, old_worker, generation=1)
    assert _panel._context_usage_thread is new_thread
    assert _panel._context_usage_worker is new_worker

    new_thread.quit()
    new_thread.wait(2000)
    old_thread.quit()
    old_thread.wait(2000)
    _panel._shutdown_context_usage_worker()
