"""Turn raw provider/SDK exception text into one short line for the transcript.

Provider errors arrive as multi-paragraph blobs carrying stack context, log
directories, and upstream bug-report instructions. Rendering that verbatim buries
the one thing the user can act on, so known failure shapes are summarized here
while the full text stays in the log.
"""

from __future__ import annotations

import re

_LOG_TAIL = re.compile(
    r"\s*(?:Conversation logs are stored at|To help debug this issue).*",
    re.IGNORECASE | re.DOTALL,
)
_BASE_URL = re.compile(r"https?://[^\s'\"]+")

MALFORMED_TOOL_CALL_NOTE = (
    "The model sent a malformed tool call and the provider rejected it, so the run "
    "stopped. This usually means the model abbreviated its own arguments. Try again — "
    "if it repeats, use a larger model for this task."
)

UNREACHABLE_NOTE = "Could not reach the model provider{where}. Check that it is running."


def _strip_log_tail(text: str) -> str:
    """Drop the SDK's log-location and bug-report trailer."""
    return _LOG_TAIL.sub("", text).strip()


def summarize_provider_error(message: str) -> str:
    """Return a single actionable line describing *message*."""
    text = (message or "").strip()
    if not text:
        return "Unknown error"
    lowered = text.lower()

    if "error parsing tool call" in lowered or "invalid tool call" in lowered:
        return MALFORMED_TOOL_CALL_NOTE
    if "connection refused" in lowered or "connecterror" in lowered:
        match = _BASE_URL.search(text)
        where = f" at {match.group(0)}" if match else ""
        return UNREACHABLE_NOTE.format(where=where)

    cleaned = _strip_log_tail(text)
    first = next((line.strip() for line in cleaned.splitlines() if line.strip()), "")
    return first or "Unknown error"


__all__ = [
    "MALFORMED_TOOL_CALL_NOTE",
    "UNREACHABLE_NOTE",
    "summarize_provider_error",
]
