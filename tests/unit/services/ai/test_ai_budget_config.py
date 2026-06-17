"""Tests for provider budget QSettings persistence."""

from __future__ import annotations

import json

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QSettings

from services.ai.ai_budget_config import AiBudgetConfig, validate_budget_entry
from services.ai.ai_config import AiModelEntry


@pytest.fixture(autouse=True)
def _clear_budget_settings() -> Iterator[None]:
    """Use an isolated QSettings scope for each test."""
    settings = QSettings("Postmark", "Postmark")
    settings.remove("ai/provider_budgets")
    settings.sync()
    yield
    settings.remove("ai/provider_budgets")
    settings.sync()


def _model(**kw: object) -> AiModelEntry:
    base: AiModelEntry = {
        "id": "m1",
        "provider": "openai",
        "label": "GPT-4o",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "token",
        "auth_ref": "ref-a",
        "input_cost_per_token": 0.0,
        "output_cost_per_token": 0.0,
    }
    base.update(kw)  # type: ignore[typeddict-item]
    return base


def test_save_all_persists_enabled_limits() -> None:
    """Valid enabled limits are stored under ai/provider_budgets."""
    AiBudgetConfig.save_all(
        [
            {
                "connection_key": "ref-a",
                "period": "monthly",
                "period_anchor": "2026-06-01",
                "soft_limit_usd": 50.0,
                "hard_limit_usd": 100.0,
            }
        ]
    )
    rows = AiBudgetConfig.get_budgets()
    assert len(rows) == 1
    assert rows[0]["connection_key"] == "ref-a"
    assert rows[0]["period"] == "monthly"
    assert rows[0]["soft_limit_usd"] == 50.0
    assert rows[0]["hard_limit_usd"] == 100.0


def test_save_all_omits_rows_without_enabled_limits() -> None:
    """Rows with no enabled limits are not persisted."""
    AiBudgetConfig.save_all(
        [
            {
                "connection_key": "ref-a",
                "period": "none",
                "soft_limit_usd": None,
                "hard_limit_usd": None,
            }
        ]
    )
    assert AiBudgetConfig.get_budgets() == []


def test_validate_budget_entry_rejects_soft_above_hard() -> None:
    """Soft limit cannot exceed hard limit."""
    err = validate_budget_entry(
        {
            "connection_key": "openai|ref-a",
            "period": "monthly",
            "period_anchor": "2026-06-01",
            "soft_limit_usd": 75.0,
            "hard_limit_usd": 50.0,
        }
    )
    assert err is not None


def test_prune_orphaned_removes_stale_connection_keys() -> None:
    """Removing models drops budget rows for missing connections."""
    AiBudgetConfig.save_all(
        [
            {
                "connection_key": "ref-a",
                "period": "monthly",
                "period_anchor": "2026-06-01",
                "soft_limit_usd": 10.0,
                "hard_limit_usd": None,
            },
            {
                "connection_key": "ref-b",
                "period": "monthly",
                "period_anchor": "2026-06-01",
                "soft_limit_usd": 20.0,
                "hard_limit_usd": None,
            },
        ]
    )
    AiBudgetConfig.prune_orphaned([_model(provider="openai", auth_ref="ref-a")])
    keys = {row["connection_key"] for row in AiBudgetConfig.get_budgets()}
    assert keys == {"ref-a"}


def test_validate_budget_entry_requires_anchor_for_period() -> None:
    """Non-none periods require a valid anchor date."""
    err = validate_budget_entry(
        {
            "connection_key": "ref-a",
            "period": "weekly",
            "period_anchor": None,
            "soft_limit_usd": 10.0,
            "hard_limit_usd": None,
        }
    )
    assert err is not None


def test_save_all_persists_period_anchor_without_limits() -> None:
    """Period and anchor can be saved without enabled USD limits."""
    AiBudgetConfig.save_all(
        [
            {
                "connection_key": "ref-a",
                "period": "weekly",
                "period_anchor": "2026-06-01",
                "soft_limit_usd": None,
                "hard_limit_usd": None,
            }
        ]
    )
    row = AiBudgetConfig.budget_for_connection("ref-a")
    assert row is not None
    assert row["period"] == "weekly"
    assert row.get("period_anchor") == "2026-06-01"


def test_get_budgets_reads_schema_payload() -> None:
    """Persisted JSON uses schema version 1."""
    settings = QSettings("Postmark", "Postmark")
    settings.setValue(
        "ai/provider_budgets",
        json.dumps(
            {
                "schema": 1,
                "entries": [
                    {
                        "connection_key": "ref-a",
                        "period": "daily",
                        "soft_limit_usd": 1.0,
                        "hard_limit_usd": 2.0,
                    }
                ],
            }
        ),
    )
    settings.sync()
    row = AiBudgetConfig.budget_for_connection("ref-a")
    assert row is not None
    assert row["period"] == "daily"
