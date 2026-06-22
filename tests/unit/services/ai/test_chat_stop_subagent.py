"""Tests for cancellable AI chat worker runs."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from services.ai.chat.run_registry import ChatRunRegistry, ResearchTurnState
from ui.sidebar.ai.workers.chat_worker import (
    CHAT_STOP_POLL_INTERVAL_S,
    CHAT_STOP_SUBAGENT_TIMEOUT_S,
    AiChatWorker,
)


def test_run_until_done_or_stop_interrupts_blocking_arun() -> None:
    """Stop requests interrupt a long-running arun and return promptly."""
    worker = AiChatWorker()
    interrupted = {"count": 0}

    class _Conv:
        async def arun(self) -> None:
            try:
                while True:
                    await asyncio.sleep(CHAT_STOP_POLL_INTERVAL_S)
            except asyncio.CancelledError:
                raise

        def interrupt(self) -> None:
            interrupted["count"] += 1

    worker._stop_requested = True
    asyncio.run(worker._run_until_done_or_stop(_Conv()))  # type: ignore[arg-type]
    assert interrupted["count"] >= 1


def test_run_until_done_or_stop_completes_normally() -> None:
    """Arun that finishes quickly does not require interrupt."""

    class _Conv:
        async def arun(self) -> None:
            await asyncio.sleep(0)

        def interrupt(self) -> None:
            raise AssertionError("interrupt should not be called")

    worker = AiChatWorker()
    asyncio.run(worker._run_until_done_or_stop(_Conv()))  # type: ignore[arg-type]


def test_registry_cancel_emits_stopped_research_payload(qapp) -> None:
    """Cancel clears active research and emits a stopped payload."""
    registry = ChatRunRegistry()
    session_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    handle = SimpleNamespace(
        worker=SimpleNamespace(cancel=lambda: None),
        research_state=ResearchTurnState(is_active=True, progress_lines=["Researching…"]),
        context=SimpleNamespace(run_generation=3),
        send_mode="agent",
    )
    registry._handles[session_id] = handle  # type: ignore[assignment]

    payloads: list[str] = []
    registry.research_updated.connect(lambda _sid, _gen, payload: payloads.append(payload))

    registry.cancel(session_id)

    assert handle.research_state.is_active is False
    assert payloads
    assert '"phase": "stopped"' in payloads[0]


def test_run_until_done_or_stop_propagates_arun_failure() -> None:
    """``arun`` exceptions reach ``run()`` so ``failed`` is emitted."""

    class _Conv:
        async def arun(self) -> None:
            raise RuntimeError("provider boom")

        def interrupt(self) -> None:
            raise AssertionError("interrupt should not be called")

    worker = AiChatWorker()
    with pytest.raises(RuntimeError, match="provider boom"):
        asyncio.run(worker._run_until_done_or_stop(_Conv()))  # type: ignore[arg-type]


def test_chat_stop_constants_are_positive() -> None:
    """Stop timeout and poll interval are sane."""
    assert CHAT_STOP_SUBAGENT_TIMEOUT_S > 0
    assert CHAT_STOP_POLL_INTERVAL_S > 0
