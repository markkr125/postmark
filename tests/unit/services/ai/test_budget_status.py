"""Tests for connection budget status classification."""

from __future__ import annotations

from services.ai.ai_config import AiModelEntry
from services.ai.chat.budget_status import (
    connection_budget_card_visible,
    connection_budget_status,
    format_connection_budget_banner_html,
    format_connection_budget_card_amounts,
)
from services.ai.chat.spend_rollup import ConnectionSpendSummary, GlobalSpendSummary


def _entry(**kw: object) -> AiModelEntry:
    base: AiModelEntry = {
        "id": "m1",
        "provider": "openai",
        "label": "GPT-4o",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "token",
        "auth_ref": "ref-a",
        "input_cost_per_token": 0.0000025,
        "output_cost_per_token": 0.00001,
    }
    base.update(kw)  # type: ignore[typeddict-item]
    return base


def _connection_row(
    *, known_period_usd: float, connection_key: str = "ref-a"
) -> ConnectionSpendSummary:
    return {
        "connection_key": connection_key,
        "provider_label": "OpenAI",
        "period_usd": known_period_usd,
        "known_period_usd": known_period_usd,
        "overall_usd": known_period_usd,
        "known_overall_usd": known_period_usd,
        "period_tokens": 1000,
        "overall_tokens": 1000,
        "partial_period": False,
        "partial_overall": False,
        "models": [],
    }


def _spend_summary(*, known_period_usd: float, connection_key: str = "ref-a") -> GlobalSpendSummary:
    return {
        "connections": [
            _connection_row(known_period_usd=known_period_usd, connection_key=connection_key)
        ],
        "period_usd": known_period_usd,
        "known_period_usd": known_period_usd,
        "overall_usd": known_period_usd,
        "known_overall_usd": known_period_usd,
        "period_tokens": 1000,
        "overall_tokens": 1000,
        "partial_period": False,
        "partial_overall": False,
        "models": [],
    }


def _budget_row(**kw: object) -> dict[str, object]:
    row = {
        "connection_key": "ref-a",
        "period": "monthly",
        "period_anchor": "2026-06-01",
        "soft_limit_usd": 0.53,
        "hard_limit_usd": 1.0,
    }
    row.update(kw)
    return row


def test_connection_budget_status_ok_under_soft(monkeypatch) -> None:
    """Known period spend below soft cap stays in the ok state."""
    monkeypatch.setattr(
        "services.ai.chat.budget_status.AiBudgetConfig.budget_for_connection",
        lambda _key: _budget_row(),
    )
    status = connection_budget_status(
        _entry(),
        spend_summary=_spend_summary(known_period_usd=0.40),
        models=[_entry()],
    )
    assert status["state"] == "ok"
    assert status["period_known_usd"] == 0.40
    assert connection_budget_card_visible(status)


def test_connection_budget_status_soft_exceeded(monkeypatch) -> None:
    """Spend above soft but below hard yields soft_exceeded."""
    monkeypatch.setattr(
        "services.ai.chat.budget_status.AiBudgetConfig.budget_for_connection",
        lambda _key: _budget_row(),
    )
    status = connection_budget_status(
        _entry(),
        spend_summary=_spend_summary(known_period_usd=0.56),
        models=[_entry()],
    )
    assert status["state"] == "soft_exceeded"
    assert "exceeded soft limit" in format_connection_budget_banner_html(status)


def test_connection_budget_status_hard_exceeded(monkeypatch) -> None:
    """Spend at or above hard cap yields hard_exceeded."""
    monkeypatch.setattr(
        "services.ai.chat.budget_status.AiBudgetConfig.budget_for_connection",
        lambda _key: _budget_row(),
    )
    status = connection_budget_status(
        _entry(),
        spend_summary=_spend_summary(known_period_usd=1.0),
        models=[_entry()],
    )
    assert status["state"] == "hard_exceeded"
    assert "hard limit" in format_connection_budget_banner_html(status)


def test_connection_budget_status_no_limits(monkeypatch) -> None:
    """Missing enabled caps classify as no_limits."""
    monkeypatch.setattr(
        "services.ai.chat.budget_status.AiBudgetConfig.budget_for_connection",
        lambda _key: _budget_row(soft_limit_usd=None, hard_limit_usd=None),
    )
    status = connection_budget_status(
        _entry(),
        spend_summary=_spend_summary(known_period_usd=5.0),
        models=[_entry()],
    )
    assert status["state"] == "no_limits"
    assert not connection_budget_card_visible(status)


def test_connection_budget_status_unrated(monkeypatch) -> None:
    """Connections without USD rates skip enforcement."""
    monkeypatch.setattr(
        "services.ai.chat.budget_status.AiBudgetConfig.budget_for_connection",
        lambda _key: _budget_row(),
    )
    unrated = _entry(input_cost_per_token=0.0, output_cost_per_token=0.0)
    status = connection_budget_status(
        unrated,
        spend_summary=_spend_summary(known_period_usd=5.0),
        models=[unrated],
    )
    assert status["state"] == "unrated"
    assert not connection_budget_card_visible(status)


def test_format_connection_budget_card_amounts_lists_caps(monkeypatch) -> None:
    """Spend flyout amounts line includes configured soft and hard caps."""
    monkeypatch.setattr(
        "services.ai.chat.budget_status.AiBudgetConfig.budget_for_connection",
        lambda _key: _budget_row(),
    )
    status = connection_budget_status(
        _entry(),
        spend_summary=_spend_summary(known_period_usd=0.56),
        models=[_entry()],
    )
    text = format_connection_budget_card_amounts(status)
    assert "$0.56" in text
    assert "soft" in text
    assert "hard" in text
