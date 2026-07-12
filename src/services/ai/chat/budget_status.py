"""Connection budget status for AI chat enforcement and display."""

from __future__ import annotations

from typing import Literal, TypedDict

from services.ai.ai_budget_config import AiBudgetConfig, BudgetPeriod
from services.ai.ai_config import AiConfig, AiModelEntry
from services.ai.budget_period import format_period_reset_label, period_window
from services.ai.chat.message_usage import format_usd_amount
from services.ai.chat.spend_rollup import (
    ConnectionSpendSummary,
    GlobalSpendSummary,
    global_spend_summary,
)
from services.ai.provider_catalog import (
    connection_has_usd_pricing,
    provider_connection_key,
    provider_group_label,
)

_MIN_LIMIT_USD = 0.01

BudgetLimitState = Literal["ok", "no_limits", "unrated", "soft_exceeded", "hard_exceeded"]


class ConnectionBudgetStatus(TypedDict):
    """Period spend vs configured caps for one provider connection."""

    connection_key: str
    provider_label: str
    rated: bool
    period: BudgetPeriod
    period_reset_label: str
    period_known_usd: float
    period_usd: float | None
    partial_period: bool
    soft_limit_usd: float | None
    hard_limit_usd: float | None
    state: BudgetLimitState
    dedupe_key: str


def _limit_enabled(value: float | None) -> bool:
    """Return whether a soft or hard cap is configured."""
    return value is not None and value >= _MIN_LIMIT_USD


def budget_period_dedupe_key(
    connection_key: str,
    period: BudgetPeriod,
    period_anchor: str | None,
) -> str:
    """Return a stable key for deduping soft-limit banners within one period window."""
    window = period_window(period, period_anchor)
    if window is None:
        return connection_key
    return f"{connection_key}:{window[1].isoformat()}"


def _resolve_state(
    *,
    rated: bool,
    period_known_usd: float,
    soft_limit_usd: float | None,
    hard_limit_usd: float | None,
) -> BudgetLimitState:
    """Classify spend against configured soft and hard caps."""
    if not rated:
        return "unrated"
    if not _limit_enabled(soft_limit_usd) and not _limit_enabled(hard_limit_usd):
        return "no_limits"
    if _limit_enabled(hard_limit_usd) and period_known_usd >= float(hard_limit_usd or 0):
        return "hard_exceeded"
    if _limit_enabled(soft_limit_usd) and period_known_usd > float(soft_limit_usd or 0):
        return "soft_exceeded"
    return "ok"


def connection_budget_status(
    entry: AiModelEntry,
    *,
    spend_summary: GlobalSpendSummary | None = None,
    models: list[AiModelEntry] | None = None,
) -> ConnectionBudgetStatus:
    """Compute budget status for the connection backing *entry*.

    When no soft/hard caps are configured and the caller did not pass a
    precomputed *spend_summary*, skip ``global_spend_summary()`` — chat
    chrome only needs spend totals for enforcement and the budget card.
    """
    connection_key = provider_connection_key(entry)
    provider_label = provider_group_label(entry)
    model_list = list(models) if models is not None else AiConfig.get_models()
    connection_models = [
        row for row in model_list if provider_connection_key(row) == connection_key
    ]
    rated = connection_has_usd_pricing(connection_models)

    budget_row = AiBudgetConfig.budget_for_connection(connection_key) or {}
    period_raw = budget_row.get("period") or "none"
    period: BudgetPeriod = (
        period_raw
        if period_raw
        in {
            "none",
            "daily",
            "weekly",
            "monthly",
            "yearly",
        }
        else "none"
    )
    period_anchor = budget_row.get("period_anchor")
    soft_limit = budget_row.get("soft_limit_usd")
    hard_limit = budget_row.get("hard_limit_usd")
    reset_label = format_period_reset_label(period, period_anchor)

    limits_enabled = _limit_enabled(soft_limit) or _limit_enabled(hard_limit)
    if spend_summary is None and not limits_enabled:
        state = _resolve_state(
            rated=rated,
            period_known_usd=0.0,
            soft_limit_usd=soft_limit,
            hard_limit_usd=hard_limit,
        )
        return ConnectionBudgetStatus(
            connection_key=connection_key,
            provider_label=provider_label,
            rated=rated,
            period=period,
            period_reset_label=reset_label,
            period_known_usd=0.0,
            period_usd=None,
            partial_period=False,
            soft_limit_usd=soft_limit,
            hard_limit_usd=hard_limit,
            state=state,
            dedupe_key=budget_period_dedupe_key(connection_key, period, period_anchor),
        )

    summary = (
        spend_summary if spend_summary is not None else global_spend_summary(models=model_list)
    )
    conn_spend: ConnectionSpendSummary | None = None
    for row in summary.get("connections") or []:
        if row.get("connection_key") == connection_key:
            conn_spend = row
            break

    period_known = float(conn_spend.get("known_period_usd") or 0.0) if conn_spend else 0.0
    period_total = conn_spend.get("period_usd") if conn_spend else None
    partial_period = bool(conn_spend.get("partial_period")) if conn_spend else False

    state = _resolve_state(
        rated=rated,
        period_known_usd=period_known,
        soft_limit_usd=soft_limit,
        hard_limit_usd=hard_limit,
    )

    return ConnectionBudgetStatus(
        connection_key=connection_key,
        provider_label=provider_label,
        rated=rated,
        period=period,
        period_reset_label=reset_label,
        period_known_usd=period_known,
        period_usd=period_total,
        partial_period=partial_period,
        soft_limit_usd=soft_limit,
        hard_limit_usd=hard_limit,
        state=state,
        dedupe_key=budget_period_dedupe_key(connection_key, period, period_anchor),
    )


def format_connection_budget_banner_html(status: ConnectionBudgetStatus) -> str:
    """Return rich-text banner copy for soft or hard exceed states."""
    label = status["provider_label"]
    spend = format_usd_amount(status["period_known_usd"])
    settings_link = '<a href="action:budgets">Adjust limits in Settings</a>'
    if status["state"] == "soft_exceeded":
        soft = format_usd_amount(float(status["soft_limit_usd"] or 0))
        return f"{label} period spend {spend} exceeded soft limit {soft}. {settings_link}"
    if status["state"] == "hard_exceeded":
        hard = format_usd_amount(float(status["hard_limit_usd"] or 0))
        return (
            f"{label} period spend {spend} reached hard limit {hard}. "
            f"New messages are blocked until the period resets or you {settings_link}."
        )
    return ""


def format_connection_budget_card_amounts(status: ConnectionBudgetStatus) -> str:
    """Format period spend against configured caps for the Spend flyout card."""
    spend = format_usd_amount(status["period_known_usd"])
    limit_parts: list[str] = []
    if _limit_enabled(status.get("soft_limit_usd")):
        limit_parts.append(f"{format_usd_amount(float(status['soft_limit_usd'] or 0))} soft")
    if _limit_enabled(status.get("hard_limit_usd")):
        limit_parts.append(f"{format_usd_amount(float(status['hard_limit_usd'] or 0))} hard")
    if not limit_parts:
        return spend
    return f"{spend} / {' · '.join(limit_parts)}"


def connection_budget_card_visible(status: ConnectionBudgetStatus | None) -> bool:
    """Return whether the Spend flyout should show the connection budget card."""
    if status is None:
        return False
    if not status["rated"]:
        return False
    return _limit_enabled(status.get("soft_limit_usd")) or _limit_enabled(
        status.get("hard_limit_usd")
    )


__all__ = [
    "BudgetLimitState",
    "ConnectionBudgetStatus",
    "budget_period_dedupe_key",
    "connection_budget_card_visible",
    "connection_budget_status",
    "format_connection_budget_banner_html",
    "format_connection_budget_card_amounts",
]
