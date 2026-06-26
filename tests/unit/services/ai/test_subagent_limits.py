"""Tests for subagent limits QSettings bridge."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QSettings

from services.ai.chat.subagent_limits import (
    DEFAULT_MAX_PARALLEL_SUBAGENTS,
    max_parallel_subagents,
    set_max_parallel_subagents,
)


@pytest.fixture(autouse=True)
def _clear_subagent_limits() -> Iterator[None]:
    """Isolate QSettings for subagent limit tests."""
    settings = QSettings("Postmark", "Postmark")
    settings.remove("ai/max_parallel_subagents")
    settings.sync()
    yield
    settings.remove("ai/max_parallel_subagents")
    settings.sync()


def test_default_parallel_subagents() -> None:
    """Default matches OpenHands DelegateExecutor default."""
    assert max_parallel_subagents() == DEFAULT_MAX_PARALLEL_SUBAGENTS


def test_persist_parallel_subagents() -> None:
    """set_max_parallel_subagents clamps and persists."""
    set_max_parallel_subagents(99)
    assert max_parallel_subagents() == 16
    set_max_parallel_subagents(3)
    assert max_parallel_subagents() == 3
