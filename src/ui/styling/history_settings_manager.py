"""History settings manager — reads/writes QSettings for send-history retention."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QSettings, Signal

from services.history_retention_config import (
    DEFAULT_MAX_ITEMS_PER_DAY,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_RETENTION_DAYS,
    KEY_MAX_ITEMS_PER_DAY,
    KEY_MAX_RESPONSE_BYTES,
    KEY_RETENTION_DAYS,
    KEY_SAVE_RESPONSES,
    KEY_UNLIMITED_PER_DAY,
    MAX_MAX_ITEMS_PER_DAY,
    MAX_MAX_RESPONSE_BYTES,
    MAX_RETENTION_DAYS,
    MIN_MAX_ITEMS_PER_DAY,
    MIN_MAX_RESPONSE_BYTES,
    MIN_RETENTION_DAYS,
    clamp_history_int,
    load_history_retention_config,
)
from ui.styling.theme_manager import _APP, _ORG

logger = logging.getLogger(__name__)

# Re-export bounds for Settings UI / tests that import from this module.
__all__ = [
    "DEFAULT_MAX_ITEMS_PER_DAY",
    "DEFAULT_MAX_RESPONSE_BYTES",
    "DEFAULT_RETENTION_DAYS",
    "MAX_MAX_ITEMS_PER_DAY",
    "MAX_MAX_RESPONSE_BYTES",
    "MAX_RETENTION_DAYS",
    "MIN_MAX_ITEMS_PER_DAY",
    "MIN_MAX_RESPONSE_BYTES",
    "MIN_RETENTION_DAYS",
    "HistorySettingsManager",
]


class HistorySettingsManager(QObject):
    """Persisted preferences for HTTP send history retention and body storage.

    Values are loaded from the shared service-layer
    :func:`~services.history_retention_config.load_history_retention_config`
    so agent sends and the UI Settings page share one QSettings schema.
    """

    settings_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        """Load history settings from QSettings."""
        super().__init__(parent)
        self._settings = QSettings(_ORG, _APP)
        cfg = load_history_retention_config(self._settings)
        self._retention_days = cfg.retention_days
        self._max_items_per_day = cfg.max_items_per_day
        self._unlimited_per_day = cfg.unlimited_per_day
        self._save_responses = cfg.save_responses
        self._max_response_bytes = cfg.max_response_bytes

    @property
    def retention_days(self) -> int:
        """Number of calendar days to retain history entries."""
        return self._retention_days

    @retention_days.setter
    def retention_days(self, value: int) -> None:
        clamped = clamp_history_int(
            value, DEFAULT_RETENTION_DAYS, MIN_RETENTION_DAYS, MAX_RETENTION_DAYS
        )
        if self._retention_days == clamped:
            return
        self._retention_days = clamped
        self._settings.setValue(KEY_RETENTION_DAYS, clamped)
        self.settings_changed.emit()

    @property
    def max_items_per_day(self) -> int:
        """Maximum history entries kept per local calendar day."""
        return self._max_items_per_day

    @max_items_per_day.setter
    def max_items_per_day(self, value: int) -> None:
        clamped = clamp_history_int(
            value,
            DEFAULT_MAX_ITEMS_PER_DAY,
            MIN_MAX_ITEMS_PER_DAY,
            MAX_MAX_ITEMS_PER_DAY,
        )
        if self._max_items_per_day == clamped:
            return
        self._max_items_per_day = clamped
        self._settings.setValue(KEY_MAX_ITEMS_PER_DAY, clamped)
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
        self._settings.setValue(KEY_UNLIMITED_PER_DAY, parsed)
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
        self._settings.setValue(KEY_SAVE_RESPONSES, parsed)
        self.settings_changed.emit()

    @property
    def max_response_bytes(self) -> int:
        """Maximum bytes stored per response body file."""
        return self._max_response_bytes

    @max_response_bytes.setter
    def max_response_bytes(self, value: int) -> None:
        clamped = clamp_history_int(
            value,
            DEFAULT_MAX_RESPONSE_BYTES,
            MIN_MAX_RESPONSE_BYTES,
            MAX_MAX_RESPONSE_BYTES,
        )
        if self._max_response_bytes == clamped:
            return
        self._max_response_bytes = clamped
        self._settings.setValue(KEY_MAX_RESPONSE_BYTES, clamped)
        self.settings_changed.emit()

    def max_response_bytes_for_storage(self) -> int:
        """Return the byte cap for body files, or ``0`` when bodies are not saved."""
        if not self._save_responses:
            return 0
        return self._max_response_bytes
