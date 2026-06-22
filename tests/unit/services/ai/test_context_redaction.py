"""Unit tests for context redaction helpers."""

from __future__ import annotations

from services.ai.chat.context_redaction import redact_env_values, redact_headers, redact_text


def test_redact_authorization_header() -> None:
    """Bearer tokens in Authorization headers are redacted."""
    text = "Authorization: Bearer secret-token-123"
    assert "[REDACTED]" in redact_text(text)
    assert "secret-token" not in redact_text(text)


def test_redact_env_secret_keys() -> None:
    """Secret-like environment keys are redacted."""
    values = {"API_KEY": "abc", "HOST": "localhost"}
    out = redact_env_values(values)
    assert out["API_KEY"] == "[REDACTED]"
    assert out["HOST"] == "localhost"


def test_redact_headers_authorization() -> None:
    """Header rows with Authorization key are redacted."""
    rows = [{"key": "Authorization", "value": "Bearer x"}]
    out = redact_headers(rows)
    assert out[0]["value"] == "[REDACTED]"
