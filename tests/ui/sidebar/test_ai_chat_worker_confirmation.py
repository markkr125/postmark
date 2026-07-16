"""Worker confirmation lifecycle tests (pause / Approve / Reject / Stop)."""

from __future__ import annotations

from PySide6.QtCore import QEventLoop, QTimer
from pytestqt.qtbot import QtBot

from services.ai.ai_config import AiModelEntry
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


def test_worker_approve_confirmation_clears_pending(qtbot: QtBot) -> None:
    """Approve slot clears pending and emits confirmation_cleared."""
    worker = AiChatWorker()
    worker.set_run(
        session_id="11111111-1111-1111-1111-111111111111",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="hi",
    )
    worker._pending_confirmation = {"actions": [{"tool_name": "postmark_workspace_mutate"}]}
    with qtbot.waitSignal(worker.confirmation_cleared, timeout=2000):
        worker.approve_confirmation()
    assert worker._confirmation_decision == "approve"
    assert worker._pending_confirmation is None


def test_worker_reject_confirmation_sets_decision(qtbot: QtBot) -> None:
    """Reject slot records decision and clears pending."""
    worker = AiChatWorker()
    worker.set_run(
        session_id="11111111-1111-1111-1111-111111111111",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="hi",
    )
    worker._pending_confirmation = {"actions": []}
    with qtbot.waitSignal(worker.confirmation_cleared, timeout=2000):
        worker.reject_confirmation("nope")
    assert worker._confirmation_decision == "reject"
    assert worker._reject_reason == "nope"


def test_worker_cancel_while_waiting_quits_loop(qtbot: QtBot) -> None:
    """Stop while waiting sets stop decision for the confirm loop."""
    del qtbot
    worker = AiChatWorker()
    worker.set_run(
        session_id="11111111-1111-1111-1111-111111111111",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="hi",
    )
    loop = QEventLoop()
    worker._confirm_loop = loop
    worker._waiting_for_confirmation = True
    QTimer.singleShot(10, worker.cancel)
    loop.exec()
    assert worker._stop_requested is True
    assert worker._confirmation_decision == "stop"
