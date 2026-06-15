"""Tests for background context-usage worker delivery."""

from __future__ import annotations

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import QApplication

from services.ai.ai_config import AiModelEntry
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.workers.context_usage_worker import ContextUsageWorker


def _entry() -> AiModelEntry:
    return {
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


def test_context_usage_worker_updates_panel_off_thread(
    qapp: QApplication, qtbot, monkeypatch
) -> None:
    """The worker computes off-thread and delivers the breakdown back to the panel."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.refresh_context_usage = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    panel.set_models([_entry()])
    captured: dict[str, object] = {}

    def _capture_build(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "used_tokens": 12_000,
            "total_tokens": 128_000,
            "categories": [],
            "has_summarized": False,
            "is_estimated": True,
        }

    monkeypatch.setattr(
        "ui.sidebar.ai.workers.context_usage_worker.build_breakdown",
        _capture_build,
    )

    worker = ContextUsageWorker()
    worker.set_request(
        session_id="sess-1",
        messages=[],
        entry=panel.current_model_entry(),
        agent_id="postmark-assistant",
        draft_text="hello",
    )
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    queued = Qt.ConnectionType.QueuedConnection
    worker.finished.connect(panel.set_context_breakdown, queued)
    worker.finished.connect(thread.quit, queued)

    with qtbot.waitSignal(worker.finished, timeout=5000):
        thread.start()
    thread.wait(5000)
    qtbot.waitUntil(lambda: panel._context_breakdown is not None, timeout=1000)

    assert panel._context_breakdown is not None
    assert panel._context_breakdown["used_tokens"] == 12_000
    assert panel._context_ring.used_tokens() == 12_000
    assert captured.get("char_only") is not True
    panel._shutdown_context_usage_worker()


def test_context_usage_refresh_requeues_when_worker_busy(
    qapp: QApplication, qtbot, monkeypatch
) -> None:
    """A refresh requested while the worker runs is replayed after it finishes."""
    import threading

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models([_entry()])
    calls: list[str] = []
    first_started = threading.Event()
    release_first = threading.Event()

    def _slow_build(**_kwargs: object) -> dict[str, object]:
        if not first_started.is_set():
            first_started.set()
            release_first.wait(timeout=5)
        calls.append("build")
        return {
            "used_tokens": len(calls) * 1000,
            "total_tokens": 128_000,
            "categories": [],
            "has_summarized": False,
            "is_estimated": True,
        }

    monkeypatch.setattr(
        "ui.sidebar.ai.workers.context_usage_worker.build_breakdown",
        _slow_build,
    )
    panel._input.setPlainText("first")
    panel._run_context_usage_refresh()
    qtbot.waitUntil(first_started.is_set, timeout=2000)
    panel._input.setPlainText("second")
    panel._run_context_usage_refresh()
    assert panel._context_refresh_pending is True

    release_first.set()
    qtbot.waitUntil(
        lambda: panel._context_breakdown is not None
        and panel._context_breakdown.get("used_tokens") == 2000,
        timeout=5000,
    )
    assert len(calls) >= 2
    panel._shutdown_context_usage_worker()
