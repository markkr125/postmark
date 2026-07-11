"""Context window usage estimation and breakdown for the AI chat composer."""

from __future__ import annotations

import json
import logging
from typing import Any, NotRequired, TypedDict

from database.data_paths import session_disk_dir
from services.ai.ai_config import AiModelEntry
from services.ai.chat.agent_registry import DEFAULT_AGENT_ID, get_agent_def
from services.ai.chat.context_usage_sdk import (
    SdkViewSnapshot,
    collect_compaction_diagnostics as _collect_compaction_diagnostics,
    count_summarized_event_tokens,
    measure_sdk_view,
    transcript_larger_than_sdk,
)
from services.ai.chat.session_service import AiChatMessageDict, AiChatSessionService
from services.ai.chat.tool_registry import resolve_tools
from services.ai.provider_catalog import effective_run_context_tokens

logger = logging.getLogger(__name__)

_CHAR_FALLBACK_DIVISOR = 4

try:
    from litellm import token_counter as _litellm_token_counter
except ImportError:
    _litellm_token_counter = None  # type: ignore[assignment,misc]

_CATEGORY_SPECS: tuple[tuple[str, str], ...] = (
    ("system_prompt", "System prompt"),
    ("tools", "Tools"),
    ("rules", "Rules"),
    ("skills", "Skills"),
    ("mcp", "MCP"),
    ("subagents", "Subagents"),
    ("summarized_conversation", "Summarized conversation"),
    ("conversation", "Conversation"),
)


class ContextUsageCategory(TypedDict):
    """One row in the context usage breakdown."""

    id: str
    label: str
    tokens: int


class ContextUsageBreakdown(TypedDict):
    """Full context usage snapshot for the ring and popover."""

    used_tokens: int
    total_tokens: int
    categories: list[ContextUsageCategory]
    has_summarized: bool
    is_estimated: bool
    draft_tokens: NotRequired[int]
    sqlite_message_count: NotRequired[int]
    sqlite_transcript_tokens: NotRequired[int]
    sdk_event_count: NotRequired[int]
    sdk_view_tokens: NotRequired[int]
    transcript_larger_than_sdk: NotRequired[bool]
    used_sqlite_fallback: NotRequired[bool]
    condenser_max_size: NotRequired[int]
    condenser_max_tokens: NotRequired[int | None]
    condenser_minimum_progress: NotRequired[float]
    condensation_reasons: NotRequired[list[str]]


class ContextUsageSdkMetrics(TypedDict, total=False):
    """Optional post-run SDK token metrics from ``conversation_stats``."""

    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    per_turn_token: int
    turn_cost_usd: float


SdkUsageMetrics = ContextUsageSdkMetrics


def _model_name(entry: AiModelEntry | None) -> str:
    if entry is None:
        return ""
    return str(entry.get("model", "")).strip()


def _char_fallback_tokens(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, len(stripped) // _CHAR_FALLBACK_DIVISOR)


def estimate_text_tokens(text: str, model: str, *, char_only: bool = False) -> int:
    """Return token count for *text*, preferring LiteLLM when available."""
    stripped = text.strip()
    if not stripped:
        return 0
    if char_only:
        return _char_fallback_tokens(stripped)
    if _litellm_token_counter is not None:
        try:
            count = _litellm_token_counter(model=model or "gpt-4o", text=stripped)
            if isinstance(count, int) and count > 0:
                return count
        except Exception:
            logger.debug("LiteLLM token_counter failed; using char fallback", exc_info=True)
    return _char_fallback_tokens(stripped)


def _tool_schema_payload(tool: object) -> object:
    """Return a JSON-serialisable shape for one tool definition."""
    if hasattr(tool, "model_dump"):
        try:
            return tool.model_dump()  # type: ignore[no-any-return,call-arg]
        except Exception:
            logger.debug("Tool model_dump failed during context usage", exc_info=True)
    if hasattr(tool, "__dict__"):
        return dict(vars(tool))
    return getattr(tool, "name", str(tool))


def count_system_and_tools(
    agent_id: str, model: str, *, char_only: bool = False
) -> tuple[int, int]:
    """Tokenize the agent system prompt and serialized tool schemas."""
    defn = get_agent_def(agent_id)
    system_tokens = estimate_text_tokens(defn.system_prompt or "", model, char_only=char_only)
    tools_tokens = 0
    tools = resolve_tools(defn.tool_names)
    if tools or defn.include_default_tools:
        try:
            payload = json.dumps(
                {
                    "tools": [_tool_schema_payload(tool) for tool in tools],
                    "include_default_tools": list(defn.include_default_tools),
                },
                sort_keys=True,
            )
            tools_tokens = estimate_text_tokens(payload, model, char_only=char_only)
        except Exception:
            tools_tokens = _char_fallback_tokens(str(tools))
    return system_tokens, tools_tokens


def count_transcript_messages(
    messages: list[AiChatMessageDict], model: str, *, char_only: bool = False
) -> int:
    """Sum user/assistant/thinking content from SQLite transcript rows."""
    total = 0
    for row in messages:
        for key in ("content", "thinking"):
            raw = row.get(key)  # type: ignore[call-overload]
            if isinstance(raw, str) and raw.strip():
                total += estimate_text_tokens(raw, model, char_only=char_only)
    return total


def iter_session_events(session_id: str) -> list[Any]:
    """Load persisted OpenHands events for *session_id*, or return []."""
    disk = session_disk_dir(session_id)
    events_dir = disk / "events"
    if not events_dir.is_dir():
        return []
    try:
        from openhands.sdk.conversation.event_store import EventLog
        from openhands.sdk.io.local import LocalFileStore

        store = LocalFileStore(root=str(disk))
        log = EventLog(store)
        return [log[index] for index in range(len(log))]
    except Exception:
        logger.debug("Failed to load SDK events for %s", session_id, exc_info=True)
        return []


def count_summarized_events(session_id: str, model: str) -> tuple[int, bool]:
    """Sum token estimates for ``Condensation`` summary text on disk."""
    return count_summarized_event_tokens(iter_session_events(session_id), model)


def _empty_categories() -> dict[str, int]:
    return {spec_id: 0 for spec_id, _label in _CATEGORY_SPECS}


def _assemble_categories(token_by_id: dict[str, int]) -> list[ContextUsageCategory]:
    return [
        ContextUsageCategory(
            id=spec_id,
            label=label,
            tokens=max(0, int(token_by_id.get(spec_id, 0))),
        )
        for spec_id, label in _CATEGORY_SPECS
    ]


def collect_compaction_diagnostics(
    *,
    session_id: str,
    messages: list[AiChatMessageDict],
    entry: AiModelEntry | None,
    agent_id: str,
    condenser: Any | None = None,
    agent_llm: Any | None = None,
    run_context_tokens: int | None = None,
) -> dict[str, Any]:
    """Assemble SQLite vs SDK numbers and condenser thresholds for logging."""
    return _collect_compaction_diagnostics(
        session_id=session_id,
        messages=messages,
        entry=entry,
        agent_id=agent_id,
        build_breakdown=build_breakdown,
        condenser=condenser,
        agent_llm=agent_llm,
        run_context_tokens=run_context_tokens,
    )


def build_breakdown(
    *,
    session_id: str | None,
    messages: list[AiChatMessageDict],
    draft_text: str = "",
    streaming_thinking: str = "",
    streaming_content: str = "",
    entry: AiModelEntry | None,
    agent_id: str,
    sdk_metrics: ContextUsageSdkMetrics | None = None,
    char_only: bool = False,
) -> ContextUsageBreakdown:
    """Assemble category buckets and totals for the context ring."""
    total_tokens = effective_run_context_tokens(entry) if entry is not None else 0
    model = _model_name(entry)
    tokens = _empty_categories()

    system_tokens, tools_tokens = count_system_and_tools(agent_id, model, char_only=char_only)
    tokens["system_prompt"] = system_tokens
    tokens["tools"] = tools_tokens

    transcript_tokens = count_transcript_messages(messages, model, char_only=char_only)
    draft_tokens = estimate_text_tokens(draft_text, model, char_only=char_only)
    stream_tokens = estimate_text_tokens(
        f"{streaming_thinking}\n{streaming_content}".strip(),
        model,
        char_only=char_only,
    )
    sqlite_message_count = len(messages)

    subagent_tokens = 0
    if session_id:
        from services.ai.chat.subagent_transcript import count_session_subagent_context_tokens

        subagent_tokens = count_session_subagent_context_tokens(
            session_id, model, char_only=char_only
        )
    tokens["subagents"] = subagent_tokens

    summarized_tokens = 0
    has_summarized = False
    sdk_snapshot: SdkViewSnapshot | None = None
    if session_id and entry is not None and not char_only:
        sdk_snapshot = measure_sdk_view(session_id, entry)
        if sdk_snapshot is not None:
            summarized_tokens = sdk_snapshot["summarized_tokens"]
            has_summarized = sdk_snapshot["has_summarized"]
        else:
            summarized_tokens, has_summarized = count_summarized_events(session_id, model)
    tokens["summarized_conversation"] = summarized_tokens

    is_estimated = True
    used_sqlite_fallback = True
    # Subagent answers typically re-enter the parent as tool observations; keep
    # them in the Subagents bucket and exclude that slice from Conversation.
    if sdk_snapshot is not None and sdk_snapshot["view_tokens"] > 0:
        fixed = system_tokens + tools_tokens + summarized_tokens + subagent_tokens
        tokens["conversation"] = (
            max(0, sdk_snapshot["view_tokens"] - fixed) + draft_tokens + stream_tokens
        )
        is_estimated = False
        used_sqlite_fallback = False
    elif sdk_metrics is not None:
        prompt = int(sdk_metrics.get("prompt_tokens", 0) or 0)
        completion = int(sdk_metrics.get("completion_tokens", 0) or 0)
        reasoning = int(sdk_metrics.get("reasoning_tokens", 0) or 0)
        sdk_used = prompt + completion + reasoning
        if sdk_used > 0:
            is_estimated = False
            used_sqlite_fallback = False
            fixed = system_tokens + tools_tokens + summarized_tokens + subagent_tokens
            tokens["conversation"] = max(0, sdk_used - fixed) + draft_tokens + stream_tokens
    if is_estimated:
        tokens["conversation"] = (
            max(0, transcript_tokens - subagent_tokens) + draft_tokens + stream_tokens
        )

    categories = _assemble_categories(tokens)
    used_tokens = sum(category["tokens"] for category in categories)
    if total_tokens > 0:
        used_tokens = min(used_tokens, total_tokens)

    sdk_event_count = sdk_snapshot["event_count"] if sdk_snapshot is not None else 0
    sdk_view_tokens = sdk_snapshot["view_tokens"] if sdk_snapshot is not None else 0
    transcript_larger = transcript_larger_than_sdk(
        sqlite_message_count=sqlite_message_count,
        sqlite_transcript_tokens=transcript_tokens,
        sdk_event_count=sdk_event_count,
        sdk_view_tokens=sdk_view_tokens,
    )

    result = ContextUsageBreakdown(
        used_tokens=used_tokens,
        total_tokens=total_tokens,
        categories=categories,
        has_summarized=has_summarized,
        is_estimated=is_estimated,
        draft_tokens=draft_tokens,
        sqlite_message_count=sqlite_message_count,
        sqlite_transcript_tokens=transcript_tokens,
        sdk_event_count=sdk_event_count,
        transcript_larger_than_sdk=transcript_larger,
        used_sqlite_fallback=used_sqlite_fallback,
    )
    if sdk_snapshot is not None:
        result["sdk_view_tokens"] = sdk_view_tokens
        result["condenser_max_size"] = sdk_snapshot["condenser_max_size"]
        result["condenser_max_tokens"] = sdk_snapshot["condenser_max_tokens"]
        result["condenser_minimum_progress"] = sdk_snapshot["condenser_minimum_progress"]
        result["condensation_reasons"] = sdk_snapshot["condensation_reasons"]
    return result


def build_breakdown_for_session(
    session_id: str | None,
    *,
    entry: AiModelEntry | None,
    agent_id: str,
    draft_text: str = "",
    streaming_thinking: str = "",
    streaming_content: str = "",
    sdk_metrics: ContextUsageSdkMetrics | None = None,
    char_only: bool = False,
) -> ContextUsageBreakdown:
    """Load full SQLite transcript for *session_id* and build a breakdown."""
    messages: list[AiChatMessageDict] = []
    if session_id:
        messages = AiChatSessionService.get_messages(session_id)
    return build_breakdown(
        session_id=session_id,
        messages=messages,
        draft_text=draft_text,
        streaming_thinking=streaming_thinking,
        streaming_content=streaming_content,
        entry=entry,
        agent_id=agent_id,
        sdk_metrics=sdk_metrics,
        char_only=char_only,
    )


def metrics_from_conversation(
    conv: Any,
    session_id: str,
    *,
    baseline_accumulated_cost: float | None = None,
) -> ContextUsageSdkMetrics | None:
    """Extract chat LLM metrics from an OpenHands conversation after ``arun()``."""
    usage_id = f"postmark-chat-{session_id}"
    try:
        metrics = conv.conversation_stats.get_metrics_for_usage(usage_id)
        usage = metrics.accumulated_token_usage
        if usage is None:
            return None
        accumulated_cost = float(metrics.accumulated_cost or 0.0)
        turn_cost_usd: float | None = None
        if baseline_accumulated_cost is not None:
            delta = max(0.0, accumulated_cost - baseline_accumulated_cost)
            if delta > 0:
                turn_cost_usd = delta
        elif accumulated_cost > 0:
            turn_cost_usd = accumulated_cost
        payload = ContextUsageSdkMetrics(
            prompt_tokens=int(usage.prompt_tokens),
            completion_tokens=int(usage.completion_tokens),
            reasoning_tokens=int(getattr(usage, "reasoning_tokens", 0) or 0),
            per_turn_token=int(usage.per_turn_token),
        )
        if turn_cost_usd is not None:
            payload["turn_cost_usd"] = turn_cost_usd
        return payload
    except Exception:
        logger.debug("No SDK metrics for usage_id=%s", usage_id, exc_info=True)
        return None


class ContextUsageService:
    """Static helpers that build ring and popup context-usage snapshots."""

    @staticmethod
    def estimate_text_tokens(text: str, model: str) -> int:
        """Return the estimated token count for one text payload."""
        return estimate_text_tokens(text, model)

    @staticmethod
    def count_system_and_tools(agent_id: str, model: str) -> tuple[int, int]:
        """Return token counts for the agent prompt and tool schema payloads."""
        return count_system_and_tools(agent_id, model)

    @staticmethod
    def count_transcript_messages(messages: list[AiChatMessageDict], model: str) -> int:
        """Return token count for the full SQLite transcript rows."""
        return count_transcript_messages(messages, model)

    @staticmethod
    def count_summarized_events(session_id: str, model: str) -> tuple[int, bool]:
        """Return summarized token count plus whether any condensation exists."""
        return count_summarized_events(session_id, model)

    @staticmethod
    def build_breakdown(
        *,
        session_id: str | None,
        messages: list[AiChatMessageDict],
        draft_text: str = "",
        streaming_thinking: str = "",
        streaming_content: str = "",
        entry: AiModelEntry | None,
        agent_id: str = DEFAULT_AGENT_ID,
        sdk_metrics: ContextUsageSdkMetrics | None = None,
    ) -> ContextUsageBreakdown:
        """Assemble a Cursor-style breakdown from transcript and SDK state."""
        return build_breakdown(
            session_id=session_id,
            messages=messages,
            draft_text=draft_text,
            streaming_thinking=streaming_thinking,
            streaming_content=streaming_content,
            entry=entry,
            agent_id=agent_id,
            sdk_metrics=sdk_metrics,
        )

    @staticmethod
    def build_breakdown_for_session(
        session_id: str | None,
        *,
        entry: AiModelEntry | None,
        agent_id: str = DEFAULT_AGENT_ID,
        draft_text: str = "",
        streaming_thinking: str = "",
        streaming_content: str = "",
        sdk_metrics: ContextUsageSdkMetrics | None = None,
    ) -> ContextUsageBreakdown:
        """Load full session rows from SQLite and build the context breakdown."""
        return build_breakdown_for_session(
            session_id,
            entry=entry,
            agent_id=agent_id,
            draft_text=draft_text,
            streaming_thinking=streaming_thinking,
            streaming_content=streaming_content,
            sdk_metrics=sdk_metrics,
        )

    @staticmethod
    def metrics_from_conversation(
        conv: Any,
        session_id: str,
        *,
        baseline_accumulated_cost: float | None = None,
    ) -> ContextUsageSdkMetrics | None:
        """Extract authoritative SDK usage metrics after one chat run."""
        return metrics_from_conversation(
            conv,
            session_id,
            baseline_accumulated_cost=baseline_accumulated_cost,
        )

    @staticmethod
    def measure_sdk_view(session_id: str, entry: AiModelEntry) -> SdkViewSnapshot | None:
        """Return SDK view token accounting when an event log exists on disk."""
        return measure_sdk_view(session_id, entry)

    @staticmethod
    def collect_compaction_diagnostics(
        *,
        session_id: str,
        messages: list[AiChatMessageDict],
        entry: AiModelEntry | None,
        agent_id: str = DEFAULT_AGENT_ID,
        condenser: Any | None = None,
        agent_llm: Any | None = None,
        run_context_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Build SQLite vs SDK diagnostics for compaction logging."""
        return collect_compaction_diagnostics(
            session_id=session_id,
            messages=messages,
            entry=entry,
            agent_id=agent_id,
            condenser=condenser,
            agent_llm=agent_llm,
            run_context_tokens=run_context_tokens,
        )


__all__ = [
    "ContextUsageBreakdown",
    "ContextUsageCategory",
    "ContextUsageSdkMetrics",
    "ContextUsageService",
    "SdkUsageMetrics",
    "SdkViewSnapshot",
    "build_breakdown",
    "build_breakdown_for_session",
    "collect_compaction_diagnostics",
    "count_summarized_events",
    "count_system_and_tools",
    "count_transcript_messages",
    "estimate_text_tokens",
    "iter_session_events",
    "measure_sdk_view",
    "metrics_from_conversation",
]
