"""Constants for the workspace query tool."""

from __future__ import annotations

import re

_VALID_SCOPES = frozenset(
    {
        "overview",
        "open_tabs",
        "active_tab",
        "active_response",
        "collection_tree",
        "collection",
        "local_scripts",
        "recent_history",
        "request",
        "request_history",
        "history_entry",
        "saved_responses",
        "saved_response",
        "runs",
        "run",
        "environments",
        "search",
        "script",
        "script_versions",
        "script_version",
        "globals",
        "snippets",
        "snippet",
        "insights",
        "tab",
        "settings",
        "request_script_versions",
        "variable",
    }
)

_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "x-access-token",
        "x-amz-security-token",
        "private-token",
        "x-csrf-token",
        "x-xsrf-token",
        "www-authenticate",
    }
)

_SENSITIVE_QS_PARAMS = frozenset(
    {
        "api_key",
        "apikey",
        "key",
        "token",
        "access_token",
        "refresh_token",
        "auth",
        "sig",
        "signature",
        "password",
        "passwd",
        "secret",
        "client_secret",
        "sas",
        "x-amz-signature",
        "x-amz-security-token",
    }
)

_SECRET_BODY_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "id_token",
        "token",
        "password",
        "secret",
        "api_key",
        "apikey",
        "client_secret",
        "authorization",
        "session_token",
        "private_key",
    }
)

_QS_PARAM_RE = re.compile(r"([?&])([^=&#]+)=([^&#]*)")

_BODY_PREVIEW_MAX = 800
_URL_PREVIEW_MAX = 140
_HEADER_VALUE_MAX = 200
_ENV_KEY_CAP = 40
_MAX_RESULT_ROWS = 50
_SEARCH_SCRIPT_SCAN_CAP = 200
_MAX_OUTPUT_CHARS = 48000
REDACTED_PLACEHOLDER = "‹redacted›"  # noqa: RUF001
SECRET_PLACEHOLDER = "‹secret›"  # noqa: RUF001
