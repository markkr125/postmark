"""Persistence for per-provider-connection AI spend budgets (QSettings-backed)."""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Literal, TypedDict, cast

from PySide6.QtCore import QSettings

from services.ai.ai_config import AiModelEntry
from services.ai.provider_catalog import provider_connection_key

logger = logging.getLogger(__name__)

_ORG = "Postmark"
_APP = "Postmark"
_SETTINGS_KEY = "ai/provider_budgets"
_SCHEMA_VERSION = 3
_MIN_LIMIT_USD = 0.01

BudgetPeriod = Literal["none", "daily", "weekly", "monthly", "yearly"]

BUDGET_PERIODS: tuple[BudgetPeriod, ...] = (
    "none",
    "daily",
    "weekly",
    "monthly",
    "yearly",
)

BUDGET_PERIOD_LABELS: dict[BudgetPeriod, str] = {
    "none": "No reset",
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly",
    "yearly": "Yearly",
}


class ProviderBudgetEntry(TypedDict, total=False):
    """Optional soft/hard USD limits for one provider connection."""

    connection_key: str
    period: BudgetPeriod
    period_anchor: str | None
    soft_limit_usd: float | None
    hard_limit_usd: float | None


def _parse_period_anchor(value: str | None) -> str | None:
    """Return normalized ``YYYY-MM-DD`` or ``YYYY-MM-DDTHH:MM`` text when valid."""
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    if "T" in text:
        date_part, time_part = text.split("T", 1)
        try:
            date.fromisoformat(date_part)
            hour_str, minute_str, *_rest = f"{time_part}:00".split(":")
            hour = int(hour_str)
            minute = int(minute_str)
        except ValueError:
            return None
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return None
        return f"{date_part}T{hour:02d}:{minute:02d}"
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def _get_settings() -> QSettings:
    return QSettings(_ORG, _APP)


def _normalize_entry(raw: object) -> ProviderBudgetEntry | None:
    """Parse one budget row from persisted JSON."""
    if not isinstance(raw, dict):
        return None
    key = str(raw.get("connection_key") or "").strip()
    if not key:
        return None
    period = str(raw.get("period") or "none").strip().lower()
    if period not in BUDGET_PERIODS:
        period = "none"
    soft = raw.get("soft_limit_usd")
    hard = raw.get("hard_limit_usd")
    soft_val = float(soft) if isinstance(soft, int | float) and soft is not None else None
    hard_val = float(hard) if isinstance(hard, int | float) and hard is not None else None
    anchor_raw = raw.get("period_anchor")
    anchor = str(anchor_raw).strip() if isinstance(anchor_raw, str) and anchor_raw.strip() else None
    entry: ProviderBudgetEntry = {
        "connection_key": key,
        "period": cast(BudgetPeriod, period),
        "period_anchor": anchor,
        "soft_limit_usd": soft_val,
        "hard_limit_usd": hard_val,
    }
    if not _entry_has_content(entry):
        return None
    return entry


def _entry_has_content(entry: ProviderBudgetEntry) -> bool:
    """Return whether *entry* should be persisted."""
    if _entry_has_limits(entry):
        return True
    period = entry.get("period") or "none"
    return period != "none" and _parse_period_anchor(entry.get("period_anchor")) is not None


def _entry_has_limits(entry: ProviderBudgetEntry) -> bool:
    """Return whether *entry* should be persisted."""
    soft = entry.get("soft_limit_usd")
    hard = entry.get("hard_limit_usd")
    has_soft = soft is not None and soft >= _MIN_LIMIT_USD
    has_hard = hard is not None and hard >= _MIN_LIMIT_USD
    return has_soft or has_hard


def validate_budget_entry(entry: ProviderBudgetEntry) -> str | None:
    """Return an error message when *entry* is invalid, else ``None``."""
    period = entry.get("period") or "none"
    if period != "none" and _parse_period_anchor(entry.get("period_anchor")) is None:
        return "Choose a reset schedule when a budget period is set."
    soft = entry.get("soft_limit_usd")
    hard = entry.get("hard_limit_usd")
    if soft is not None and soft < _MIN_LIMIT_USD:
        return "Soft limit must be at least $0.01 when enabled."
    if hard is not None and hard < _MIN_LIMIT_USD:
        return "Hard limit must be at least $0.01 when enabled."
    if (
        soft is not None
        and hard is not None
        and soft >= _MIN_LIMIT_USD
        and hard >= _MIN_LIMIT_USD
        and soft > hard
    ):
        return "Soft limit cannot exceed hard limit."
    return None


def connection_keys_from_models(models: list[AiModelEntry]) -> set[str]:
    """Return the set of provider connection keys present in *models*."""
    keys: set[str] = set()
    for row in models:
        keys.add(provider_connection_key(row))
    return keys


class AiBudgetConfig:
    """Static accessors for provider budget configuration in QSettings."""

    @staticmethod
    def _write_entries(entries: list[ProviderBudgetEntry]) -> None:
        """Persist *entries* as the full budget document."""
        payload = {
            "schema": _SCHEMA_VERSION,
            "entries": entries,
        }
        s = _get_settings()
        s.setValue(_SETTINGS_KEY, json.dumps(payload))
        s.sync()

    @staticmethod
    def get_budgets() -> list[ProviderBudgetEntry]:
        """Return all persisted provider budget rows."""
        s = _get_settings()
        raw = s.value(_SETTINGS_KEY, "")
        if not isinstance(raw, str) or not raw.strip():
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid %s JSON; resetting budgets", _SETTINGS_KEY)
            return []
        if not isinstance(payload, dict):
            return []
        entries_raw = payload.get("entries")
        if not isinstance(entries_raw, list):
            return []
        out: list[ProviderBudgetEntry] = []
        seen: set[str] = set()
        for item in entries_raw:
            entry = _normalize_entry(item)
            if entry is None:
                continue
            key = entry["connection_key"]
            if key in seen:
                continue
            seen.add(key)
            out.append(entry)
        return out

    @staticmethod
    def budget_for_connection(connection_key: str) -> ProviderBudgetEntry | None:
        """Return the budget row for *connection_key*, if any."""
        key = connection_key.strip()
        if not key:
            return None
        for entry in AiBudgetConfig.get_budgets():
            if entry.get("connection_key") == key:
                return entry
        return None

    @staticmethod
    def save_all(entries: list[ProviderBudgetEntry]) -> None:
        """Persist budget rows, merging by ``connection_key`` and dropping empty rows."""
        merged: dict[str, ProviderBudgetEntry] = {}
        for existing in AiBudgetConfig.get_budgets():
            key = existing.get("connection_key", "")
            if key:
                merged[key] = existing
        for entry in entries:
            key = str(entry.get("connection_key") or "").strip()
            if not key:
                continue
            normalized = _normalize_entry({**entry, "connection_key": key})
            if normalized is None:
                merged.pop(key, None)
                continue
            err = validate_budget_entry(normalized)
            if err is not None:
                continue
            merged[key] = normalized
        AiBudgetConfig._write_entries(list(merged.values()))

    @staticmethod
    def prune_orphaned(models: list[AiModelEntry]) -> None:
        """Remove budget rows whose connection keys are no longer configured."""
        valid = connection_keys_from_models(models)
        kept = [
            entry for entry in AiBudgetConfig.get_budgets() if entry.get("connection_key") in valid
        ]
        if len(kept) == len(AiBudgetConfig.get_budgets()):
            return
        AiBudgetConfig._write_entries(kept)


__all__ = [
    "BUDGET_PERIODS",
    "BUDGET_PERIOD_LABELS",
    "AiBudgetConfig",
    "BudgetPeriod",
    "ProviderBudgetEntry",
    "connection_keys_from_models",
    "validate_budget_entry",
]
