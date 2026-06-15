"""OpenHands chat condenser tuning constants and diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from services.ai.ai_logging import log as ai_log

if TYPE_CHECKING:
    from openhands.sdk.context.condenser import LLMSummarizingCondenser
    from openhands.sdk.llm import LLM

# Proactive event-count threshold before the condenser LLM runs (chat-tuned).
CHAT_CONDENSER_MAX_EVENTS = 45

# Proactive token threshold as a fraction of the model run context window.
CHAT_CONDENSER_MAX_TOKEN_FRACTION = 0.72

# Minimum fraction of view events that must be forgotten for soft condensation.
CHAT_CONDENSER_MINIMUM_PROGRESS = 0.05

# Ring usage fraction that triggers pre-run compaction diagnostics logging.
CHAT_CONDENSER_DIAGNOSTIC_USAGE_FRACTION = 0.70


def condenser_max_tokens(run_context_tokens: int) -> int | None:
    """Return proactive ``max_tokens`` for the chat condenser, or ``None`` when unknown."""
    if run_context_tokens <= 0:
        return None
    return int(run_context_tokens * CHAT_CONDENSER_MAX_TOKEN_FRACTION)


def log_compaction_diagnostics(
    *,
    session_id: str,
    diagnostics: dict[str, Any],
    condensation_occurred: bool | None = None,
) -> None:
    """Emit ``[postmark.ai]`` lines comparing SQLite estimates to SDK condenser state."""
    sqlite_msgs = int(diagnostics.get("sqlite_message_count", 0))
    sqlite_tokens = int(diagnostics.get("sqlite_transcript_tokens", 0))
    sdk_events = int(diagnostics.get("sdk_event_count", 0))
    sdk_tokens = diagnostics.get("sdk_view_tokens")
    used = int(diagnostics.get("ring_used_tokens", 0))
    total = int(diagnostics.get("ring_total_tokens", 0))
    ring_pct = round(100 * used / total) if total > 0 else 0
    reasons = diagnostics.get("condensation_reasons")
    reasons_text = ", ".join(sorted(str(r) for r in reasons)) if reasons else "none"
    ai_log(
        "Compaction diag "
        f"session={session_id[:8]} "
        f"ring={ring_pct}% ({used}/{total}) "
        f"sqlite_msgs={sqlite_msgs} sqlite_tokens={sqlite_tokens} "
        f"sdk_events={sdk_events} sdk_tokens={sdk_tokens} "
        f"max_size={diagnostics.get('condenser_max_size')} "
        f"max_tokens={diagnostics.get('condenser_max_tokens')} "
        f"minimum_progress={diagnostics.get('condenser_minimum_progress')} "
        f"reasons={reasons_text} "
        f"sdk_fallback={diagnostics.get('used_sqlite_fallback', False)}"
    )
    if diagnostics.get("transcript_larger_than_sdk") and ring_pct >= round(
        100 * CHAT_CONDENSER_DIAGNOSTIC_USAGE_FRACTION
    ):
        ai_log(
            "Compaction diag: SQLite transcript is larger than the SDK model view "
            f"(msgs {sqlite_msgs} vs sdk_events {sdk_events})"
        )
    if condensation_occurred is False and reasons:
        ai_log("Compaction diag: run finished without condensation despite active reasons")
    elif condensation_occurred is True:
        ai_log("Compaction diag: condensation event emitted during run")


def evaluate_condensation_reasons(
    condenser: LLMSummarizingCondenser,
    view: Any,
    *,
    agent_llm: LLM | None,
) -> set[Any]:
    """Return OpenHands condensation reasons for *view*, or an empty set on failure."""
    try:
        return condenser.get_condensation_reasons(view, agent_llm=agent_llm)
    except Exception:
        ai_log("Compaction diag: get_condensation_reasons failed")
        return set()


__all__ = [
    "CHAT_CONDENSER_DIAGNOSTIC_USAGE_FRACTION",
    "CHAT_CONDENSER_MAX_EVENTS",
    "CHAT_CONDENSER_MAX_TOKEN_FRACTION",
    "CHAT_CONDENSER_MINIMUM_PROGRESS",
    "condenser_max_tokens",
    "evaluate_condensation_reasons",
    "log_compaction_diagnostics",
]
