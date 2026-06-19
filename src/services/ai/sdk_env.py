"""OpenHands SDK environment defaults and shared timeouts for embedded desktop use."""

from __future__ import annotations

import logging
import os

from services.ai.chat.chat_run_limits import DEFAULT_MAX_CONCURRENT_CHAT_RUNS

CONNECTION_TEST_TIMEOUT_SEC: int = 10
CHAT_RUN_TIMEOUT_SEC: int = 300
MAX_CONCURRENT_CHAT_RUNS: int = DEFAULT_MAX_CONCURRENT_CHAT_RUNS
HTTP_TIMEOUT_SEC: float = 10.0
MODEL_LIST_TIMEOUT_SEC: float = 120.0


def ensure_openhands_env() -> None:
    """Apply env defaults before the first ``openhands.sdk`` import.

    OpenHands auto-configures a Rich ``StreamHandler`` on the root logger
    (``LOG_AUTO_CONFIG``, default true), which causes SQLAlchemy and other
    libraries to print INFO noise to the terminal. Postmark shows AI errors
    in the Settings UI instead.
    """
    os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
    os.environ.setdefault("LOG_AUTO_CONFIG", "false")
    for name in ("sqlalchemy.engine", "sqlalchemy.pool", "sqlalchemy.dialects"):
        logging.getLogger(name).setLevel(logging.WARNING)


__all__ = [
    "CHAT_RUN_TIMEOUT_SEC",
    "CONNECTION_TEST_TIMEOUT_SEC",
    "HTTP_TIMEOUT_SEC",
    "MAX_CONCURRENT_CHAT_RUNS",
    "MODEL_LIST_TIMEOUT_SEC",
    "ensure_openhands_env",
]
