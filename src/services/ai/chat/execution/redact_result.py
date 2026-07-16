"""Redact secrets from SharedSendCore response dicts for agent observations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.ai.chat.tools.workspace_query.helpers import (
    _mask_console_log_message,
    _mask_header_value,
    _redact_response_body,
    _redact_url,
)
from services.scripting.context import mask_sensitive_value

try:
    from openhands.sdk.utils.redact import redact_text_secrets
except ImportError:  # pragma: no cover — SDK always present in app/tests

    def redact_text_secrets(text: str) -> str:  # type: ignore[misc]
        """Fallback when OpenHands redact utils are unavailable."""
        return text


def _redact_variable_map(changes: dict[str, Any] | None) -> dict[str, str]:
    """Mask sensitive keys in a variable-change map."""
    if not changes:
        return {}
    out: dict[str, str] = {}
    for key, value in changes.items():
        raw = str(value)
        masked = mask_sensitive_value(str(key), raw)
        if masked != raw:
            out[str(key)] = masked
        else:
            out[str(key)] = redact_text_secrets(raw)
    return out


def _redact_headers(headers: list[Any] | None) -> list[dict[str, str]]:
    """Return header rows with sensitive values masked."""
    result: list[dict[str, str]] = []
    if not headers:
        return result
    for item in headers:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", ""))
        value = str(item.get("value", ""))
        result.append({"key": key, "value": _mask_header_value(key, value)})
    return result


def _redact_console_logs(logs: list[Any] | None) -> list[dict[str, Any]]:
    """Redact secret-looking fragments in console log messages."""
    out: list[dict[str, Any]] = []
    if not logs:
        return out
    for entry in logs:
        if not isinstance(entry, dict):
            continue
        row = dict(entry)
        msg = str(row.get("message", ""))
        row["message"] = redact_text_secrets(_mask_console_log_message(msg))
        out.append(row)
    return out


def redact_send_result(response: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied send response safe for agent tool observations.

    Masks sensitive headers, URL userinfo/query secrets, JSON/form/XML body
    secrets, console log fragments, and sensitive variable-change values.
    """
    out = deepcopy(response)

    if "request_url" in out and isinstance(out["request_url"], str):
        out["request_url"] = _redact_url(out["request_url"])

    headers = out.get("headers")
    if isinstance(headers, list):
        out["headers"] = _redact_headers(headers)

    req_headers = out.get("request_headers")
    if isinstance(req_headers, list):
        out["request_headers"] = _redact_headers(req_headers)

    body = out.get("body")
    if isinstance(body, str) and body:
        lang = str(out.get("preview_language") or "text")
        out["body"] = _redact_response_body(
            body,
            lang,
            headers=headers if isinstance(headers, list) else None,
        )
        out["body"] = redact_text_secrets(out["body"])

    if "console_logs" in out:
        out["console_logs"] = _redact_console_logs(
            out["console_logs"] if isinstance(out["console_logs"], list) else None
        )
    if "pre_request_console_logs" in out:
        out["pre_request_console_logs"] = _redact_console_logs(
            out["pre_request_console_logs"]
            if isinstance(out["pre_request_console_logs"], list)
            else None
        )

    if "variable_changes" in out and isinstance(out["variable_changes"], dict):
        out["variable_changes"] = _redact_variable_map(out["variable_changes"])
    if "pre_request_variable_changes" in out and isinstance(
        out["pre_request_variable_changes"], dict
    ):
        out["pre_request_variable_changes"] = _redact_variable_map(
            out["pre_request_variable_changes"]
        )

    error = out.get("error")
    if isinstance(error, str) and error:
        out["error"] = redact_text_secrets(error)

    tests = out.get("test_results")
    if isinstance(tests, list):
        out["test_results"] = _redact_test_results(tests)

    return out


def _redact_test_results(tests: list[Any]) -> list[dict[str, Any]]:
    """Mask secret-looking fragments in test result names/errors/messages."""
    import re

    bearer_re = re.compile(r"(?i)\b(bearer)\s+(\S+)")
    out: list[dict[str, Any]] = []
    for item in tests:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        for key in ("name", "error", "message", "detail"):
            val = row.get(key)
            if isinstance(val, str) and val:
                text = redact_text_secrets(val)
                text = _mask_console_log_message(text)
                text = bearer_re.sub(r"\1 ***", text)
                row[key] = text
        out.append(row)
    return out
