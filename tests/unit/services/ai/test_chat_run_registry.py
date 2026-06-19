"""Tests for concurrent AI chat run registry."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from services.ai.ai_config import AiModelEntry
from services.ai.chat.run_registry import ChatRunRegistry, MAX_CONCURRENT_CHAT_RUNS
from services.ai.sdk_env import MAX_CONCURRENT_CHAT_RUNS as SDK_CAP


class _ImmediateWorker(QObject):
    """Fake worker that finishes on the next event-loop tick."""

    assistant_finished = Signal(str, str)
    failed = Signal(str, str, str)
    chunk_received = Signal(str, str)
    status_changed = Signal(str)
    usage_updated = Signal(object)
    context_compacted = Signal()

    def set_run(self, **kwargs: object) -> None:
        self._kwargs = kwargs

    def cancel(self) -> None:
        return

    def run(self) -> None:
        self.assistant_finished.emit("", "done")


def _entry() -> AiModelEntry:
    return AiModelEntry(
        id="m1",
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


def test_registry_start_and_finish_lifecycle(qapp: QApplication, qtbot, monkeypatch) -> None:
    """Starting a run emits running chrome and clears after finish."""
    monkeypatch.setattr("services.ai.chat.run_registry.AiChatWorker", _ImmediateWorker)
    registry = ChatRunRegistry()
    counts: list[int] = []
    registry.running_sessions_changed.connect(lambda: counts.append(registry.count_running()))
    handle = registry.start_run(
        session_id="sess-1",
        run_generation=registry.next_run_generation(),
        user_message_id=1,
        user_text="hi",
        model_id="m1",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="hi",
        composer=None,
    )
    assert handle is not None
    assert registry.is_running("sess-1")
    qtbot.waitUntil(lambda: registry.count_running() == 0, timeout=3000)
    assert counts


def test_registry_rejects_second_start_for_same_session(
    qapp: QApplication, qtbot, monkeypatch
) -> None:
    """Only one worker may run per session id at a time."""
    import time

    class _SlowWorker(_ImmediateWorker):
        def run(self) -> None:
            time.sleep(0.2)
            self.assistant_finished.emit("", "done")

    monkeypatch.setattr("services.ai.chat.run_registry.AiChatWorker", _SlowWorker)
    registry = ChatRunRegistry()
    first = registry.start_run(
        session_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        run_generation=registry.next_run_generation(),
        user_message_id=1,
        user_text="hi",
        model_id="m1",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="hi",
        composer=None,
    )
    second = registry.start_run(
        session_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        run_generation=registry.next_run_generation(),
        user_message_id=2,
        user_text="again",
        model_id="m1",
        entry=_entry(),
        agent_id="postmark-assistant",
        text="again",
        composer=None,
    )
    assert first is not None
    assert second is None
    qtbot.waitUntil(lambda: registry.count_running() == 0, timeout=3000)


def test_default_concurrent_limit_is_ten() -> None:
    """Registry and sdk_env agree on the default advisory concurrent limit."""
    assert MAX_CONCURRENT_CHAT_RUNS == SDK_CAP == 10
