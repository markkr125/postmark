"""Persist Key / Value column widths for :class:`KeyValueTableWidget` in QSettings."""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import QSettings

from ui.styling.theme_manager import _APP, _ORG

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "ui/kv_col_widths"
_MIN_WIDTH = 48
_MAX_WIDTH = 800


def _clamp(w: int) -> int:
    """Clamp a column width into the supported pixel range."""
    return max(_MIN_WIDTH, min(_MAX_WIDTH, w))


def _read_map(settings: QSettings) -> dict[str, dict[str, int]]:
    """Return the stored profile→widths map, or empty dict if missing or corrupt."""
    raw = settings.value(_SETTINGS_KEY, "")
    if not raw or not isinstance(raw, str):
        return {}
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Ignoring corrupt %s JSON", _SETTINGS_KEY)
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, int]] = {}
    for profile, entry in data.items():
        if not isinstance(profile, str) or not isinstance(entry, dict):
            continue
        try:
            kw = int(entry.get("key", 0))
            vw = int(entry.get("value", 0))
        except (TypeError, ValueError):
            continue
        if kw > 0 and vw > 0:
            out[profile] = {"key": _clamp(kw), "value": _clamp(vw)}
    return out


def load_column_widths(profile: str, default_key: int, default_value: int) -> tuple[int, int]:
    """Return persisted Key/Value widths for *profile*, or defaults when unset."""
    settings = QSettings(_ORG, _APP)
    data = _read_map(settings)
    entry = data.get(profile)
    if entry is None:
        return _clamp(default_key), _clamp(default_value)
    return entry["key"], entry["value"]


def save_column_widths(profile: str, key_width: int, value_width: int) -> None:
    """Merge *profile* Key/Value widths into the shared JSON blob and persist."""
    settings = QSettings(_ORG, _APP)
    data = _read_map(settings)
    data[profile] = {
        "key": _clamp(key_width),
        "value": _clamp(value_width),
    }
    settings.setValue(_SETTINGS_KEY, json.dumps(data))
    settings.sync()
