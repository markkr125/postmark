"""Service-layer history retention settings (no UI imports).

Single source of truth for ``history/*`` QSettings keys, defaults, and clamps.
The UI :class:`~ui.styling.history_settings_manager.HistorySettingsManager`
loads and writes through these helpers.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings

_ORG = "Postmark"
_APP = "Postmark"

KEY_RETENTION_DAYS = "history/retention_days"
KEY_MAX_ITEMS_PER_DAY = "history/max_items_per_day"
KEY_UNLIMITED_PER_DAY = "history/unlimited_per_day"
KEY_SAVE_RESPONSES = "history/save_responses"
KEY_MAX_RESPONSE_BYTES = "history/max_response_bytes"

DEFAULT_RETENTION_DAYS = 30
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 365
DEFAULT_MAX_ITEMS_PER_DAY = 100
MIN_MAX_ITEMS_PER_DAY = 1
MAX_MAX_ITEMS_PER_DAY = 10_000
DEFAULT_MAX_RESPONSE_BYTES = 1_048_576
MAX_MAX_RESPONSE_BYTES = 10_485_760
MIN_MAX_RESPONSE_BYTES = DEFAULT_MAX_RESPONSE_BYTES


def clamp_history_int(value: object, default: int, low: int, high: int) -> int:
    """Parse and clamp an integer QSettings value for history settings."""
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def history_settings_as_bool(value: object, default: bool) -> bool:
    """Parse a QSettings bool-ish value for history settings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, int):
        return bool(value)
    return default


@dataclass(frozen=True, slots=True)
class HistoryRetentionConfig:
    """Immutable snapshot of history retention preferences for record_send."""

    retention_days: int
    max_items_per_day: int
    unlimited_per_day: bool
    save_responses: bool
    max_response_bytes: int

    def max_response_bytes_for_storage(self) -> int:
        """Return the body size cap used when persisting response bodies."""
        return self.max_response_bytes if self.save_responses else 0


def load_history_retention_config(
    settings: QSettings | None = None,
) -> HistoryRetentionConfig:
    """Load history retention settings from QSettings (worker-safe)."""
    store = settings if settings is not None else QSettings(_ORG, _APP)
    return HistoryRetentionConfig(
        retention_days=clamp_history_int(
            store.value(KEY_RETENTION_DAYS, DEFAULT_RETENTION_DAYS),
            DEFAULT_RETENTION_DAYS,
            MIN_RETENTION_DAYS,
            MAX_RETENTION_DAYS,
        ),
        max_items_per_day=clamp_history_int(
            store.value(KEY_MAX_ITEMS_PER_DAY, DEFAULT_MAX_ITEMS_PER_DAY),
            DEFAULT_MAX_ITEMS_PER_DAY,
            MIN_MAX_ITEMS_PER_DAY,
            MAX_MAX_ITEMS_PER_DAY,
        ),
        unlimited_per_day=history_settings_as_bool(
            store.value(KEY_UNLIMITED_PER_DAY, False),
            False,
        ),
        save_responses=history_settings_as_bool(
            store.value(KEY_SAVE_RESPONSES, True),
            True,
        ),
        max_response_bytes=clamp_history_int(
            store.value(KEY_MAX_RESPONSE_BYTES, DEFAULT_MAX_RESPONSE_BYTES),
            DEFAULT_MAX_RESPONSE_BYTES,
            MIN_MAX_RESPONSE_BYTES,
            MAX_MAX_RESPONSE_BYTES,
        ),
    )


__all__ = [
    "DEFAULT_MAX_ITEMS_PER_DAY",
    "DEFAULT_MAX_RESPONSE_BYTES",
    "DEFAULT_RETENTION_DAYS",
    "KEY_MAX_ITEMS_PER_DAY",
    "KEY_MAX_RESPONSE_BYTES",
    "KEY_RETENTION_DAYS",
    "KEY_SAVE_RESPONSES",
    "KEY_UNLIMITED_PER_DAY",
    "MAX_MAX_ITEMS_PER_DAY",
    "MAX_MAX_RESPONSE_BYTES",
    "MAX_RETENTION_DAYS",
    "MIN_MAX_ITEMS_PER_DAY",
    "MIN_MAX_RESPONSE_BYTES",
    "MIN_RETENTION_DAYS",
    "HistoryRetentionConfig",
    "clamp_history_int",
    "history_settings_as_bool",
    "load_history_retention_config",
]
