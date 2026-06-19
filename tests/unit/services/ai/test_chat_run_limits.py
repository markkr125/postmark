"""Tests for advisory concurrent AI chat run limits."""

from __future__ import annotations

from PySide6.QtCore import QSettings

from services.ai.chat.chat_run_limits import (
    DEFAULT_MAX_CONCURRENT_CHAT_RUNS,
    max_concurrent_chat_runs,
    set_max_concurrent_chat_runs,
)
from services.ai.sdk_env import MAX_CONCURRENT_CHAT_RUNS


def test_default_limit_is_ten() -> None:
    """Default advisory limit matches sdk_env re-export."""
    assert DEFAULT_MAX_CONCURRENT_CHAT_RUNS == MAX_CONCURRENT_CHAT_RUNS == 10


def test_max_concurrent_chat_runs_round_trip(qapp) -> None:
    """QSettings read/write clamps and persists the advisory limit."""
    settings = QSettings("Postmark", "Postmark")
    settings.remove("ai/max_concurrent_runs")
    assert max_concurrent_chat_runs() == 10

    set_max_concurrent_chat_runs(24)
    assert max_concurrent_chat_runs() == 24

    set_max_concurrent_chat_runs(999)
    assert max_concurrent_chat_runs() == 64

    set_max_concurrent_chat_runs(0)
    assert max_concurrent_chat_runs() == 1

    settings.remove("ai/max_concurrent_runs")
