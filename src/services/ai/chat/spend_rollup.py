"""Cross-session spend rollups for Settings → AI → Budgets."""

from __future__ import annotations

from collections import defaultdict
from typing import TypedDict, cast

from services.ai.ai_budget_config import AiBudgetConfig, ProviderBudgetEntry
from services.ai.ai_config import AiConfig, AiModelEntry
from services.ai.ai_budget_config import BudgetPeriod
from services.ai.budget_period import (
    format_period_reset_label,
    message_in_window,
    period_window,
)
from services.ai.chat.message_usage import (
    ModelSpendRow,
    SessionSpendBreakdown,
    combined_model_entries,
    entry_for_model_id,
    format_run_context_tokens,
    format_usd_amount,
    resolve_turn_model_id,
    session_spend_breakdown,
)
from services.ai.chat.session_service import AiChatMessageDict
from services.ai.provider_catalog import provider_connection_key, provider_group_label

from database.models.ai_chat.ai_chat_query_repository import list_assistant_usage_messages


class ConnectionSpendSummary(TypedDict):
    """Spend rollup for one provider connection."""

    connection_key: str
    provider_label: str
    period_usd: float | None
    known_period_usd: float
    overall_usd: float | None
    known_overall_usd: float
    period_tokens: int
    overall_tokens: int
    partial_period: bool
    partial_overall: bool
    models: list[ModelSpendRow]


class GlobalSpendSummary(TypedDict):
    """Aggregated spend across all provider connections."""

    connections: list[ConnectionSpendSummary]
    period_usd: float | None
    known_period_usd: float
    overall_usd: float | None
    known_overall_usd: float
    period_tokens: int
    overall_tokens: int
    partial_period: bool
    partial_overall: bool
    models: list[ModelSpendRow]


def _token_total(row: ModelSpendRow) -> int:
    return (
        int(row.get("prompt_tokens") or 0)
        + int(row.get("completion_tokens") or 0)
        + int(row.get("reasoning_tokens") or 0)
    )


def _merge_model_rows(target: dict[str, ModelSpendRow], rows: list[ModelSpendRow]) -> None:
    """Merge *rows* into *target* keyed by ``model_id``."""
    for row in rows:
        key = row["model_id"]
        existing = target.get(key)
        if existing is None:
            target[key] = ModelSpendRow(
                model_id=row["model_id"],
                model_label=row["model_label"],
                provider_label=row["provider_label"],
                prompt_tokens=int(row.get("prompt_tokens") or 0),
                completion_tokens=int(row.get("completion_tokens") or 0),
                reasoning_tokens=int(row.get("reasoning_tokens") or 0),
                cost_usd=row.get("cost_usd"),
                turn_count=int(row.get("turn_count") or 0),
            )
            continue
        existing["prompt_tokens"] += int(row.get("prompt_tokens") or 0)
        existing["completion_tokens"] += int(row.get("completion_tokens") or 0)
        existing["reasoning_tokens"] += int(row.get("reasoning_tokens") or 0)
        existing["turn_count"] += int(row.get("turn_count") or 0)
        new_cost = row.get("cost_usd")
        if new_cost is None or existing.get("cost_usd") is None:
            existing["cost_usd"] = None
        else:
            existing["cost_usd"] = float(existing["cost_usd"] or 0.0) + float(new_cost)


def _breakdown_totals(breakdown: SessionSpendBreakdown) -> tuple[float, float | None, int, bool]:
    """Return ``(known_usd, total_usd, tokens, partial)`` from one breakdown."""
    tokens = sum(_token_total(row) for row in breakdown.get("models") or [])
    known = float(breakdown.get("known_usd") or 0.0)
    total = breakdown.get("total_usd")
    partial = bool(breakdown.get("partial"))
    return known, total, tokens, partial


def _messages_for_connection(
    messages: list[AiChatMessageDict],
    connection_key: str,
    *,
    resolved_entries: list[AiModelEntry],
    session_models: dict[str, str | None],
) -> list[AiChatMessageDict]:
    """Return assistant messages attributed to *connection_key*."""
    by_session: dict[str, list[AiChatMessageDict]] = defaultdict(list)
    for msg in messages:
        by_session[str(msg.get("session_id") or "")].append(msg)

    matched: list[AiChatMessageDict] = []
    for session_id, session_msgs in by_session.items():
        session_msgs.sort(
            key=lambda row: (str(row.get("created_at") or ""), int(row.get("id") or 0))
        )
        session_model_id = session_models.get(session_id)
        for index, msg in enumerate(session_msgs):
            if msg.get("role") != "assistant":
                continue
            model_id = resolve_turn_model_id(
                msg,
                messages=session_msgs,
                msg_index=index,
                session_model_id=session_model_id,
            )
            entry = entry_for_model_id(
                model_id, extra_entries=resolved_entries, include_configured=False
            )
            if entry is None:
                continue
            if provider_connection_key(entry) == connection_key:
                matched.append(msg)
    return matched


def _rollup_messages(
    messages: list[AiChatMessageDict],
    *,
    resolved_entries: list[AiModelEntry],
    session_models: dict[str, str | None],
) -> SessionSpendBreakdown:
    """Roll up *messages* that may span multiple sessions."""
    by_session: dict[str, list[AiChatMessageDict]] = defaultdict(list)
    for msg in messages:
        by_session[str(msg.get("session_id") or "")].append(msg)

    merged: dict[str, ModelSpendRow] = {}
    assistant_turns = 0
    priced_turns = 0
    known_usd = 0.0
    has_unpriced = False

    for session_id, session_msgs in by_session.items():
        session_msgs.sort(
            key=lambda row: (str(row.get("created_at") or ""), int(row.get("id") or 0))
        )
        breakdown = session_spend_breakdown(
            session_msgs,
            session_model_id=session_models.get(session_id),
            resolved_entries=resolved_entries,
        )
        assistant_turns += int(breakdown.get("assistant_turns") or 0)
        priced_turns += int(breakdown.get("priced_turns") or 0)
        known_usd += float(breakdown.get("known_usd") or 0.0)
        if (breakdown.get("partial") or breakdown.get("total_usd") is None) and int(
            breakdown.get("assistant_turns") or 0
        ) > int(breakdown.get("priced_turns") or 0):
            has_unpriced = True
        _merge_model_rows(merged, list(breakdown.get("models") or []))

    spend_models = sorted(
        merged.values(),
        key=lambda row: (row["provider_label"].lower(), row["model_label"].lower()),
    )
    total_usd = None if assistant_turns == 0 or has_unpriced else known_usd
    partial = has_unpriced and known_usd > 0
    return SessionSpendBreakdown(
        total_usd=total_usd,
        known_usd=known_usd,
        assistant_turns=assistant_turns,
        priced_turns=priced_turns,
        partial=partial,
        models=spend_models,
    )


def _session_model_ids() -> dict[str, str | None]:
    """Map session id → default model id for attribution fallbacks."""
    from database.models.ai_chat.ai_chat_query_repository import list_sessions

    out: dict[str, str | None] = {}
    for row in list_sessions(include_archived=True):
        sid = str(row.get("id") or "")
        if not sid:
            continue
        model_id = row.get("model_id")
        out[sid] = str(model_id) if isinstance(model_id, str) and model_id.strip() else None
    return out


def global_spend_summary(
    *,
    models: list[AiModelEntry] | None = None,
    budgets: list[ProviderBudgetEntry] | None = None,
) -> GlobalSpendSummary:
    """Compute per-connection and global spend from stored assistant messages."""
    model_list = list(models) if models is not None else list(AiConfig.get_models())
    resolved_entries = combined_model_entries(model_list)
    budget_rows = budgets if budgets is not None else AiBudgetConfig.get_budgets()
    budget_by_key = {row["connection_key"]: row for row in budget_rows if row.get("connection_key")}

    all_messages = cast(
        list[AiChatMessageDict],
        list_assistant_usage_messages(),
    )
    session_models = _session_model_ids()

    connection_keys: set[str] = set()
    models_by_connection: dict[str, list[AiModelEntry]] = defaultdict(list)
    for entry in model_list:
        key = provider_connection_key(entry)
        connection_keys.add(key)
        models_by_connection[key].append(entry)

    connections: list[ConnectionSpendSummary] = []
    global_period_known = 0.0
    global_overall_known = 0.0
    global_period_tokens = 0
    global_overall_tokens = 0
    global_period_partial = False
    global_overall_partial = False
    global_period_has_unpriced = False
    global_overall_has_unpriced = False
    all_models: dict[str, ModelSpendRow] = {}

    for key in sorted(
        connection_keys, key=lambda k: provider_group_label(models_by_connection[k][0]).lower()
    ):
        sample = models_by_connection[key][0]
        provider_label = provider_group_label(sample)
        conn_messages = _messages_for_connection(
            all_messages,
            key,
            resolved_entries=resolved_entries,
            session_models=session_models,
        )
        overall = _rollup_messages(
            conn_messages,
            resolved_entries=resolved_entries,
            session_models=session_models,
        )
        overall_known, overall_total, overall_tokens, overall_partial = _breakdown_totals(overall)

        budget = budget_by_key.get(key, {})
        period_name = budget.get("period") or "none"
        window = period_window(period_name, budget.get("period_anchor"))
        period_messages = (
            [msg for msg in conn_messages if message_in_window(msg, window)]
            if window is not None
            else []
        )
        if window is None and period_name == "none":
            period_breakdown = overall
        else:
            period_breakdown = _rollup_messages(
                period_messages,
                resolved_entries=resolved_entries,
                session_models=session_models,
            )
        period_known, period_total, period_tokens, period_partial = _breakdown_totals(
            period_breakdown
        )

        _merge_model_rows(all_models, list(overall.get("models") or []))

        global_period_known += period_known
        global_overall_known += overall_known
        global_period_tokens += period_tokens
        global_overall_tokens += overall_tokens
        if period_partial:
            global_period_partial = True
        if overall_partial:
            global_overall_partial = True
        if int(period_breakdown.get("assistant_turns") or 0) > int(
            period_breakdown.get("priced_turns") or 0
        ):
            global_period_has_unpriced = True
        if int(overall.get("assistant_turns") or 0) > int(overall.get("priced_turns") or 0):
            global_overall_has_unpriced = True

        connections.append(
            ConnectionSpendSummary(
                connection_key=key,
                provider_label=provider_label,
                period_usd=period_total,
                known_period_usd=period_known,
                overall_usd=overall_total,
                known_overall_usd=overall_known,
                period_tokens=period_tokens,
                overall_tokens=overall_tokens,
                partial_period=period_partial
                or (
                    int(period_breakdown.get("assistant_turns") or 0)
                    > int(period_breakdown.get("priced_turns") or 0)
                ),
                partial_overall=overall_partial,
                models=list(overall.get("models") or []),
            )
        )

    global_models = sorted(
        all_models.values(),
        key=lambda row: (row["provider_label"].lower(), row["model_label"].lower()),
    )
    return GlobalSpendSummary(
        connections=connections,
        period_usd=None
        if global_period_has_unpriced and global_period_known > 0
        else (global_period_known if global_period_known > 0 else None),
        known_period_usd=global_period_known,
        overall_usd=None
        if global_overall_has_unpriced
        else (global_overall_known if global_overall_known > 0 else None),
        known_overall_usd=global_overall_known,
        period_tokens=global_period_tokens,
        overall_tokens=global_overall_tokens,
        partial_period=global_period_partial or global_period_has_unpriced,
        partial_overall=global_overall_partial or global_overall_has_unpriced,
        models=global_models,
    )


_BUDGET_MIN_LIMIT_USD = 0.01


def format_budget_usd_cell(
    *,
    known_usd: float,
    total_usd: float | None,
    partial: bool,
    rated: bool,
) -> str:
    """Format a USD-only budgets table cell."""
    if not rated or known_usd <= 0:
        return "—"
    usd_text = format_usd_amount(known_usd)
    if partial or total_usd is None:
        return f"~{usd_text}+"
    return usd_text


def format_budget_tokens_cell(tokens: int) -> str:
    """Format a token-only budgets table cell."""
    if tokens <= 0:
        return "—"
    return format_run_context_tokens(tokens)


def format_budget_limits_summary(
    *,
    period: BudgetPeriod = "none",
    period_anchor: str | None = None,
    soft_limit_usd: float | None,
    hard_limit_usd: float | None,
) -> str:
    """Format configured period reset and soft/hard limits for the table."""
    parts: list[str] = []
    reset_label = format_period_reset_label(period, period_anchor)
    if reset_label:
        parts.append(reset_label)
    if soft_limit_usd is not None and soft_limit_usd >= _BUDGET_MIN_LIMIT_USD:
        parts.append(f"Soft {format_usd_amount(soft_limit_usd)}")
    if hard_limit_usd is not None and hard_limit_usd >= _BUDGET_MIN_LIMIT_USD:
        parts.append(f"Hard {format_usd_amount(hard_limit_usd)}")
    return " · ".join(parts) if parts else "—"


def format_budget_spend_label(
    *,
    known_usd: float,
    total_usd: float | None,
    tokens: int,
    rated: bool,
    partial: bool,
) -> str:
    """Format one spend table cell for the Budgets page."""
    token_text = format_run_context_tokens(tokens)
    if not rated:
        return f"{token_text} tokens" if tokens > 0 else "—"
    if known_usd <= 0 and tokens <= 0:
        return "—"
    if known_usd > 0:
        usd_text = format_usd_amount(known_usd)
        if partial or total_usd is None:
            usd_text = f"~{usd_text}+"
        return f"{usd_text} · {token_text}"
    return f"— · {token_text}" if tokens > 0 else "—"


def format_global_spend_summary_line(
    *,
    label: str,
    known_usd: float,
    total_usd: float | None,
    tokens: int,
    partial: bool,
    has_rated_spend: bool,
) -> str:
    """Format one summary line for the Budgets page header."""
    usd = format_budget_usd_cell(
        known_usd=known_usd,
        total_usd=total_usd,
        partial=partial,
        rated=has_rated_spend,
    )
    token_text = format_budget_tokens_cell(tokens)
    if usd == "—" and token_text == "—":
        return f"{label}: —"
    if usd == "—":
        return f"{label}: {token_text} tokens"
    if token_text == "—":
        return f"{label}: {usd}"
    return f"{label}: {usd} · {token_text} tokens"


__all__ = [
    "ConnectionSpendSummary",
    "GlobalSpendSummary",
    "format_budget_limits_summary",
    "format_budget_spend_label",
    "format_budget_tokens_cell",
    "format_budget_usd_cell",
    "format_global_spend_summary_line",
    "global_spend_summary",
]
