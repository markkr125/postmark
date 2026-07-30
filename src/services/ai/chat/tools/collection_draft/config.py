"""QSettings-backed language for scripts generated during draft imports."""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import QSettings

_ORG = "Postmark"
_APP = "Postmark"
_KEY = "ai/draft_script_language"

DraftScriptLanguage = Literal["python", "javascript", "typescript"]

DEFAULT_DRAFT_SCRIPT_LANGUAGE: DraftScriptLanguage = "python"
_VALID: frozenset[str] = frozenset({"python", "javascript", "typescript"})


def _get_settings() -> QSettings:
    """Return the Postmark QSettings store."""
    return QSettings(_ORG, _APP)


def draft_script_language() -> DraftScriptLanguage:
    """Return the language for AI-generated draft-import scripts.

    Defaults to ``python``. Unknown or empty values fall back to the default.
    """
    raw = _get_settings().value(_KEY, DEFAULT_DRAFT_SCRIPT_LANGUAGE)
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in _VALID:
            return value  # type: ignore[return-value]
    return DEFAULT_DRAFT_SCRIPT_LANGUAGE


def set_draft_script_language(value: str) -> None:
    """Persist the draft-import script language (invalid values become python)."""
    cleaned = str(value or "").strip().lower()
    if cleaned not in _VALID:
        cleaned = DEFAULT_DRAFT_SCRIPT_LANGUAGE
    _get_settings().setValue(_KEY, cleaned)


__all__ = [
    "DEFAULT_DRAFT_SCRIPT_LANGUAGE",
    "DraftScriptLanguage",
    "draft_script_language",
    "set_draft_script_language",
]
