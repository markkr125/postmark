"""Auth field names treated as secrets for context redaction."""

from __future__ import annotations

# Field keys from auth types where values must not appear in AI context.
AUTH_SECRET_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "token",
        "password",
        "value",
        "consumerSecret",
        "tokenSecret",
        "authKey",
        "secretKey",
        "sessionToken",
        "secret",
        "clientSecret",
        "accessToken",
        "clientToken",
    }
)
