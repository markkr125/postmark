"""Redact credentials and secrets from text sent to AI context tools."""

from __future__ import annotations

import json
import re
from typing import Any

from services.http.auth_secret_fields import AUTH_SECRET_FIELD_NAMES

_AUTH_HEADER_RE = re.compile(
    r"(?im)^(Authorization\s*:\s*)(Bearer\s+|Basic\s+)?(.+)$",
)
_SECRET_ENV_KEY_RE = re.compile(
    r"(?i)(?:^|_)(TOKEN|SECRET|PASSWORD|API_KEY)(?:$|_)",
)


def _is_secret_env_key(key: str) -> bool:
    """Return whether an environment variable key should be redacted."""
    normalized = key.strip()
    if not normalized:
        return False
    if normalized.upper() in {"API_KEY", "APIKEY"}:
        return True
    return bool(_SECRET_ENV_KEY_RE.search(normalized))


def redact_text(text: str) -> str:
    """Redact authorization headers and JSON secret values in *text*."""
    if not text:
        return text

    def _auth_repl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        scheme = match.group(2) or ""
        return f"{prefix}{scheme}[REDACTED]"

    redacted = _AUTH_HEADER_RE.sub(_auth_repl, text)
    return _redact_json_secrets_in_text(redacted)


def _redact_json_secrets_in_text(text: str) -> str:
    """Best-effort JSON object redaction embedded in arbitrary text."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(parsed, dict):
        cleaned = _redact_mapping(parsed)
        return json.dumps(cleaned, indent=2, ensure_ascii=False)
    return text


def _redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *data* with secret keys redacted."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key in AUTH_SECRET_FIELD_NAMES or _is_secret_env_key(key):
            out[key] = "[REDACTED]"
        elif isinstance(value, dict):
            out[key] = _redact_mapping(value)
        elif isinstance(value, list):
            out[key] = [_redact_mapping(item) if isinstance(item, dict) else item for item in value]
        else:
            out[key] = value
    return out


def redact_headers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Redact secret values in key/value header rows."""
    result: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("key") or row.get("name") or "")
        value = row.get("value")
        if key.lower() == "authorization" or key in AUTH_SECRET_FIELD_NAMES:
            result.append({**row, "value": "[REDACTED]"})
        elif isinstance(value, str):
            result.append({**row, "value": redact_text(value)})
        else:
            result.append(dict(row))
    return result


def redact_env_values(values: dict[str, str]) -> dict[str, str]:
    """Redact environment variable values for secret-like keys."""
    return {
        key: ("[REDACTED]" if _is_secret_env_key(key) else value) for key, value in values.items()
    }
