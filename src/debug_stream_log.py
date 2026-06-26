"""Append-only NDJSON debug logging for streaming investigations."""

from __future__ import annotations

import json
import time
from typing import Any

_DEBUG_LOG_PATH = "/home/marik/Projects/postmark/.cursor/debug-a2acf3.log"
_DEBUG_SESSION_ID = "a2acf3"


def debug_stream_log(
    location: str,
    message: str,
    data: dict[str, Any],
    *,
    hypothesis_id: str,
    run_id: str = "pre-fix",
) -> None:
    """Write one debug event without raising."""
    payload = {
        "sessionId": _DEBUG_SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        return


__all__ = ["debug_stream_log"]
