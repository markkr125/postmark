"""``ensure_openhands_env`` defaults."""

from __future__ import annotations

import logging
import os

import pytest

from services.ai.sdk_env import ensure_openhands_env


def test_ensure_openhands_env_sets_quiet_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Banner suppression and no Rich auto-config before SDK import."""
    for key in ("OPENHANDS_SUPPRESS_BANNER", "LOG_AUTO_CONFIG"):
        monkeypatch.delenv(key, raising=False)
    ensure_openhands_env()
    assert os.environ["OPENHANDS_SUPPRESS_BANNER"] == "1"
    assert os.environ["LOG_AUTO_CONFIG"] == "false"
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
