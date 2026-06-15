"""OpenHands SDK view token accounting for AI chat context usage."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from services.ai.ai_config import AiModelEntry
from services.ai.chat.compaction import (
    CHAT_CONDENSER_MAX_EVENTS,
    CHAT_CONDENSER_MINIMUM_PROGRESS,
    condenser_max_tokens,
    evaluate_condensation_reasons,
)
from services.ai.chat.session_service import AiChatMessageDict
from services.ai.provider_catalog import effective_run_context_tokens

logger = logging.getLogger(__name__)


class SdkViewSnapshot(TypedDict):
    """OpenHands SDK view token accounting for one session."""

    event_count: int
    view_tokens: int
    summarized_tokens: int
    has_summarized: bool
    condenser_max_size: int
    condenser_max_tokens: int | None
    condenser_minimum_progress: float
    condensation_reasons: list[str]


def _reason_names(reasons: set[Any]) -> list[str]:
    """Normalize OpenHands condensation reason enums for diagnostics."""
    names: list[str] = []
    for reason in reasons:
        name = getattr(reason, "name", None)
        names.append(str(name or reason).lower())
    return sorted(names)


def count_summarized_event_tokens(events: list[Any], model: str) -> tuple[int, bool]:
    """Sum token estimates for ``Condensation`` summary text in *events*."""
    try:
        from openhands.sdk.event.condenser import Condensation
    except ImportError:
        return 0, False

    total = 0
    found = False
    for event in events:
        if not isinstance(event, Condensation):
            continue
        found = True
        summary = getattr(event, "summary", None)
        if isinstance(summary, str) and summary.strip():
            from services.ai.chat.context_usage import estimate_text_tokens

            total += estimate_text_tokens(summary, model)
    return total, found


def transcript_larger_than_sdk(
    *,
    sqlite_message_count: int,
    sqlite_transcript_tokens: int,
    sdk_event_count: int,
    sdk_view_tokens: int,
) -> bool:
    """Return whether SQLite transcript rows outpace the loaded SDK event log."""
    if sqlite_message_count < 4 or sdk_event_count <= 0:
        return False
    if sdk_event_count >= sqlite_message_count:
        return False
    return sqlite_transcript_tokens > max(sdk_view_tokens, 1)


def sdk_view_snapshot_for_session(
    session_id: str,
    entry: AiModelEntry,
    model: str,
    *,
    run_context_tokens: int,
    events: list[Any],
) -> SdkViewSnapshot | None:
    """Return authoritative OpenHands View token accounting when SDK events exist."""
    if not events:
        return None
    try:
        from openhands.sdk.context.condenser import LLMSummarizingCondenser
        from openhands.sdk.context.condenser.utils import get_total_token_count
        from openhands.sdk.context.view import View

        from services.ai.llm_service import AiLlmService

        llm = AiLlmService.build_llm(
            entry,
            usage_id=f"postmark-chat-context-{session_id}",
            stream=False,
            run_context_tokens=run_context_tokens,
        )
        view = View.from_events(events)
        view_tokens = int(get_total_token_count(view.events, llm))
        max_tokens = condenser_max_tokens(run_context_tokens)
        condenser = LLMSummarizingCondenser(
            llm=llm,
            max_size=CHAT_CONDENSER_MAX_EVENTS,
            max_tokens=max_tokens,
            minimum_progress=CHAT_CONDENSER_MINIMUM_PROGRESS,
        )
        reasons = evaluate_condensation_reasons(condenser, view, agent_llm=llm)
        summarized_tokens, has_summarized = count_summarized_event_tokens(events, model)
        return SdkViewSnapshot(
            event_count=len(view.events),
            view_tokens=max(0, view_tokens),
            summarized_tokens=summarized_tokens,
            has_summarized=has_summarized,
            condenser_max_size=CHAT_CONDENSER_MAX_EVENTS,
            condenser_max_tokens=max_tokens,
            condenser_minimum_progress=CHAT_CONDENSER_MINIMUM_PROGRESS,
            condensation_reasons=_reason_names(reasons),
        )
    except Exception:
        logger.debug("Failed to count SDK View tokens for %s", session_id, exc_info=True)
        return None


def measure_sdk_view(
    session_id: str,
    entry: AiModelEntry,
    *,
    events: list[Any] | None = None,
) -> SdkViewSnapshot | None:
    """Build an OpenHands ``View`` and count LLM-view tokens when events exist on disk."""
    from services.ai.chat.context_usage import iter_session_events

    loaded = events if events is not None else iter_session_events(session_id)
    return sdk_view_snapshot_for_session(
        session_id,
        entry,
        str(entry.get("model", "")).strip(),
        run_context_tokens=effective_run_context_tokens(entry),
        events=loaded,
    )


def collect_compaction_diagnostics(
    *,
    session_id: str,
    messages: list[AiChatMessageDict],
    entry: AiModelEntry | None,
    agent_id: str,
    build_breakdown: Any,
    condenser: Any | None = None,
    agent_llm: Any | None = None,
    run_context_tokens: int | None = None,
) -> dict[str, Any]:
    """Assemble SQLite vs SDK numbers and condenser thresholds for logging."""
    from services.ai.chat.context_usage import count_transcript_messages, iter_session_events

    total_tokens = (
        run_context_tokens
        if run_context_tokens is not None
        else (effective_run_context_tokens(entry) if entry is not None else 0)
    )
    model = str(entry.get("model", "")).strip() if entry is not None else ""
    sqlite_message_count = len(messages)
    sqlite_transcript_tokens = count_transcript_messages(messages, model)
    sdk_snapshot = measure_sdk_view(session_id, entry) if entry is not None else None
    breakdown = build_breakdown(
        session_id=session_id,
        messages=messages,
        entry=entry,
        agent_id=agent_id,
    )
    diagnostics: dict[str, Any] = {
        "sqlite_message_count": sqlite_message_count,
        "sqlite_transcript_tokens": sqlite_transcript_tokens,
        "sdk_event_count": int(sdk_snapshot["event_count"]) if sdk_snapshot else 0,
        "sdk_view_tokens": sdk_snapshot["view_tokens"] if sdk_snapshot else None,
        "ring_used_tokens": breakdown["used_tokens"],
        "ring_total_tokens": breakdown["total_tokens"] or total_tokens,
        "used_sqlite_fallback": bool(breakdown.get("used_sqlite_fallback", False)),
        "transcript_larger_than_sdk": bool(breakdown.get("transcript_larger_than_sdk", False)),
        "condenser_max_size": CHAT_CONDENSER_MAX_EVENTS,
        "condenser_max_tokens": condenser_max_tokens(total_tokens),
        "condenser_minimum_progress": CHAT_CONDENSER_MINIMUM_PROGRESS,
        "condensation_reasons": set(sdk_snapshot["condensation_reasons"])
        if sdk_snapshot
        else set(),
    }
    if condenser is not None and sdk_snapshot is not None:
        try:
            from openhands.sdk.context.view import View

            events = iter_session_events(session_id)
            view = View.from_events(events)
            diagnostics["condensation_reasons"] = evaluate_condensation_reasons(
                condenser,
                view,
                agent_llm=agent_llm,
            )
        except Exception:
            logger.debug("Compaction reason evaluation failed", exc_info=True)
    return diagnostics


__all__ = [
    "SdkViewSnapshot",
    "collect_compaction_diagnostics",
    "count_summarized_event_tokens",
    "measure_sdk_view",
    "sdk_view_snapshot_for_session",
    "transcript_larger_than_sdk",
]
