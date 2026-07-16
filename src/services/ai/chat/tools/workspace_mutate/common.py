"""Shared helpers for workspace mutate ops (observations + secrets policy).

Agent may write structure, non-secret values, and ``{{var}}`` placeholders.
Raw secret / token / password values are rejected. Observations must not echo
raw secrets (callers redact separately).
"""

from __future__ import annotations

import re
from typing import Any

from openhands.sdk.tool.tool import Observation

from services.scripting.context import _SENSITIVE_KEYS

_PLACEHOLDER_RE = re.compile(r"^\{\{.+\}\}$")
_AUTH_SECRET_KEYS = frozenset(
    {
        "token",
        "password",
        "value",  # API key value
        "accessToken",
        "access_token",
        "refreshToken",
        "refresh_token",
        "clientSecret",
        "client_secret",
        "secret",
        "passphrase",
        "privateKey",
        "private_key",
    }
)


class WorkspaceMutateObservation(Observation):
    """Observation after a workspace mutation attempt."""


def mutate_obs(text: str) -> WorkspaceMutateObservation:
    """Build a mutate observation from text."""
    return WorkspaceMutateObservation.from_text(text)


def is_var_placeholder(value: object) -> bool:
    """Return True when *value* is a single ``{{…}}`` placeholder."""
    if not isinstance(value, str):
        return False
    return bool(_PLACEHOLDER_RE.match(value.strip()))


def is_empty_or_placeholder(value: object) -> bool:
    """Return True for empty / whitespace / ``{{var}}`` values."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    text = value.strip()
    return not text or is_var_placeholder(text)


def key_looks_sensitive(key: str) -> bool:
    """Return True when *key* matches credential-like naming."""
    return bool(_SENSITIVE_KEYS.search(key))


def reject_raw_secret_value(key: str, value: object) -> str | None:
    """Return an error code when *value* is a disallowed raw secret for *key*.

    Non-sensitive keys may carry any string. Sensitive keys and auth secret
    fields may only be empty or a ``{{var}}`` placeholder.
    """
    if is_empty_or_placeholder(value):
        return None
    if key in _AUTH_SECRET_KEYS or key_looks_sensitive(key):
        return "raw_secret_rejected"
    return None


def sanitize_env_values(
    values: list[Any],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Validate environment/collection variable rows for the secrets policy."""
    cleaned: list[dict[str, Any]] = []
    for raw in values:
        if not isinstance(raw, dict):
            return None, "invalid_variable_row"
        key = str(raw.get("key") or "").strip()
        if not key:
            continue
        value = raw.get("value", "")
        type_raw = str(raw.get("type") or "default").strip().lower()
        is_secret_type = type_raw in {"secret", "password", "hidden"}
        if is_secret_type or key_looks_sensitive(key):
            err = reject_raw_secret_value(key, value)
            if err:
                return None, err
        row: dict[str, Any] = {
            "key": key,
            "value": "" if value is None else str(value),
            "enabled": bool(raw.get("enabled", True)),
        }
        if "type" in raw:
            row["type"] = type_raw if type_raw else "default"
        cleaned.append(row)
    return cleaned, None


def sanitize_auth_payload(auth: object) -> tuple[dict[str, Any] | None, str | None]:
    """Validate a request/folder auth dict; reject raw secret field values."""
    if auth is None:
        return {"type": "noauth"}, None
    if not isinstance(auth, dict):
        return None, "invalid_auth"
    out: dict[str, Any] = dict(auth)
    auth_type = str(out.get("type") or "noauth").strip().lower() or "noauth"
    out["type"] = auth_type
    if auth_type in {"", "noauth", "inherit"}:
        return out, None
    for key, value in list(out.items()):
        if key == "type":
            continue
        if isinstance(value, dict):
            nested, err = sanitize_auth_payload({**value, "type": auth_type})
            if err:
                return None, err
            if nested is not None:
                nested.pop("type", None)
                out[key] = nested
            continue
        err = reject_raw_secret_value(str(key), value)
        if err:
            return None, err
    return out, None


def globals_have_secret_writes(changes: dict[str, Any]) -> bool:
    """Return True when any global key looks sensitive."""
    for key, value in changes.items():
        if key_looks_sensitive(str(key)):
            return True
        if reject_raw_secret_value(str(key), value):
            return True
    return False


def env_values_have_secret_writes(values: list[dict[str, Any]]) -> bool:
    """Return True when any row is secret-typed or sensitive-keyed."""
    for row in values:
        key = str(row.get("key") or "")
        type_raw = str(row.get("type") or "default").strip().lower()
        if type_raw in {"secret", "password", "hidden"} or key_looks_sensitive(key):
            return True
    return False


__all__ = [
    "WorkspaceMutateObservation",
    "env_values_have_secret_writes",
    "globals_have_secret_writes",
    "is_empty_or_placeholder",
    "is_var_placeholder",
    "key_looks_sensitive",
    "mutate_obs",
    "reject_raw_secret_value",
    "sanitize_auth_payload",
    "sanitize_env_values",
]
