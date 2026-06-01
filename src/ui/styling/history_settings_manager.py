"""History settings manager — reads/writes QSettings for send-history retention."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from ui.styling.tab_settings_manager import _as_bool
from ui.styling.theme_manager import _APP, _ORG

logger = logging.getLogger(__name__)

_KEY_RETENTION_DAYS = "history/retention_days"
_KEY_MAX_ITEMS_PER_DAY = "history/max_items_per_day"
_KEY_UNLIMITED_PER_DAY = "history/unlimited_per_day"
_KEY_SAVE_RESPONSES = "history/save_responses"
_KEY_MAX_RESPONSE_BYTES = "history/max_response_bytes"

DEFAULT_RETENTION_DAYS = 30
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 365

DEFAULT_MAX_ITEMS_PER_DAY = 100
MIN_MAX_ITEMS_PER_DAY = 1
MAX_MAX_ITEMS_PER_DAY = 10_000

DEFAULT_MAX_RESPONSE_BYTES = 1_048_576
MAX_MAX_RESPONSE_BYTES = 10_485_760
MIN_MAX_RESPONSE_BYTES = DEFAULT_MAX_RESPONSE_BYTES


def _clamp_int(value: object, default: int, low: int, high: int) -> int:
    """Parse and clamp an integer QSettings value."""
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


class HistorySettingsManager(QObject):
    """Persisted preferences for HTTP send history retention and body storage."""

    settings_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        """Load history settings from QSettings."""
        super().__init__(parent)
        from PySide6.QtCore import QSettings

        self._settings = QSettings(_ORG, _APP)
        self._retention_days = _clamp_int(
            self._settings.value(_KEY_RETENTION_DAYS, DEFAULT_RETENTION_DAYS),
            DEFAULT_RETENTION_DAYS,
            MIN_RETENTION_DAYS,
            MAX_RETENTION_DAYS,
        )
        self._max_items_per_day = _clamp_int(
            self._settings.value(_KEY_MAX_ITEMS_PER_DAY, DEFAULT_MAX_ITEMS_PER_DAY),
            DEFAULT_MAX_ITEMS_PER_DAY,
            MIN_MAX_ITEMS_PER_DAY,
            MAX_MAX_ITEMS_PER_DAY,
        )
        self._unlimited_per_day = _as_bool(
            self._settings.value(_KEY_UNLIMITED_PER_DAY, False),
            False,
        )
        self._save_responses = _as_bool(
            self._settings.value(_KEY_SAVE_RESPONSES, True),
            True,
        )
        self._max_response_bytes = _clamp_int(
            self._settings.value(_KEY_MAX_RESPONSE_BYTES, DEFAULT_MAX_RESPONSE_BYTES),
            DEFAULT_MAX_RESPONSE_BYTES,
            MIN_MAX_RESPONSE_BYTES,
            MAX_MAX_RESPONSE_BYTES,
        )

    @property
    def retention_days(self) -> int:
        """Number of calendar days to retain history entries."""
        return self._retention_days

    @retention_days.setter
    def retention_days(self, value: int) -> None:
        clamped = _clamp_int(value, DEFAULT_RETENTION_DAYS, MIN_RETENTION_DAYS, MAX_RETENTION_DAYS)
        if self._retention_days == clamped:
            return
        self._retention_days = clamped
        self._settings.setValue(_KEY_RETENTION_DAYS, clamped)
        self.settings_changed.emit()

    @property
    def max_items_per_day(self) -> int:
        """Maximum history entries kept per local calendar day."""
        return self._max_items_per_day

    @max_items_per_day.setter
    def max_items_per_day(self, value: int) -> None:
        clamped = _clamp_int(
            value,
            DEFAULT_MAX_ITEMS_PER_DAY,
            MIN_MAX_ITEMS_PER_DAY,
            MAX_MAX_ITEMS_PER_DAY,
        )
        if self._max_items_per_day == clamped:
            return
        self._max_items_per_day = clamped
        self._settings.setValue(_KEY_MAX_ITEMS_PER_DAY, clamped)
        self.settings_changed.emit()

    @property
    def unlimited_per_day(self) -> bool:
        """When true, do not cap entries per calendar day."""
        return self._unlimited_per_day

    @unlimited_per_day.setter
    def unlimited_per_day(self, value: bool) -> None:
        parsed = bool(value)
        if self._unlimited_per_day == parsed:
            return
        self._unlimited_per_day = parsed
        self._settings.setValue(_KEY_UNLIMITED_PER_DAY, parsed)
        self.settings_changed.emit()

    @property
    def save_responses(self) -> bool:
        """When false, skip writing response body files (snapshots still saved)."""
        return self._save_responses

    @save_responses.setter
    def save_responses(self, value: bool) -> None:
        parsed = bool(value)
        if self._save_responses == parsed:
            return
        self._save_responses = parsed
        self._settings.setValue(_KEY_SAVE_RESPONSES, parsed)
        self.settings_changed.emit()

    @property
    def max_response_bytes(self) -> int:
        """Maximum bytes stored per response body file."""
        return self._max_response_bytes

    @max_response_bytes.setter
    def max_response_bytes(self, value: int) -> None:
        clamped = _clamp_int(
            value,
            DEFAULT_MAX_RESPONSE_BYTES,
            MIN_MAX_RESPONSE_BYTES,
            MAX_MAX_RESPONSE_BYTES,
        )
        if self._max_response_bytes == clamped:
            return
        self._max_response_bytes = clamped
        self._settings.setValue(_KEY_MAX_RESPONSE_BYTES, clamped)
        self.settings_changed.emit()

    def max_response_bytes_for_storage(self) -> int:
        """Return the byte cap for body files, or ``0`` when bodies are not saved."""
        if not self._save_responses:
            return 0
        return self._max_response_bytes
