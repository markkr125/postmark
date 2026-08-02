"""Bare global helpers exposed in script sandboxes (not under ``pm.``).

These are injected as top-level builtins by the script runtimes, so they are
called *without* a ``pm.`` prefix (e.g. ``datetime_now()``, not
``pm.datetime_now()``). They are absent from ``pm.d.ts`` / ``pm.pyi`` (which only
cover the ``pm`` object), so the wiki quickref lists them separately to stop the
chat model inventing ``pm.``-prefixed versions.

Mirrors the documented tables in ``docs/scripting/python-api.md`` and
``docs/scripting/javascript-api.md`` (asserted by ``test_pm_api_quickref``).
"""

from __future__ import annotations

# (name, signature, short doc)
GlobalHelper = tuple[str, str, str]

PYTHON_SANDBOX_GLOBALS: tuple[GlobalHelper, ...] = (
    ("json_loads", "(s: str)", "Parse JSON string"),
    ("json_dumps", "(obj)", "Serialize to JSON string"),
    ("re_match", "(pattern, string)", "Match regex at start of string"),
    ("re_search", "(pattern, string)", "Search for regex in string"),
    ("re_findall", "(pattern, string)", "Find all regex matches"),
    ("re_sub", "(pattern, repl, string)", "Replace regex matches"),
    ("math_ceil", "(x)", "Ceiling of x"),
    ("math_floor", "(x)", "Floor of x"),
    ("math_sqrt", "(x)", "Square root of x"),
    ("math_pow", "(x, y)", "x raised to power y"),
    ("math_log", "(x)", "Natural logarithm of x"),
    ("math_pi", "", "Constant pi"),
    ("math_e", "", "Constant e"),
    ("b64encode", "(s)", "Base64 encode"),
    ("b64decode", "(s)", "Base64 decode"),
    ("hashlib_md5", "(s)", "MD5 hex digest"),
    ("hashlib_sha256", "(s)", "SHA-256 hex digest"),
    ("hashlib_sha512", "(s)", "SHA-512 hex digest"),
    ("hashlib_hmac_sha256", "(data, key)", "HMAC-SHA256 hex digest"),
    ("hashlib_hmac_sha512", "(data, key)", "HMAC-SHA512 hex digest"),
    ("uuid_v4", "()", "Random UUID v4 string"),
    ("datetime_now", "()", "Current UTC ISO timestamp"),
    ("datetime_utcnow", "()", "Alias for datetime_now()"),
    ("unix_timestamp", "()", "Current Unix time in seconds (int; Python sandbox only)"),
    ("url_quote", "(s)", "URL-encode a string"),
    ("url_urlencode", "(params)", "URL-encode query parameters"),
)

JS_SANDBOX_GLOBALS: tuple[GlobalHelper, ...] = (
    ("require", "(module)", "Import a bundled library (lodash, moment, crypto-js, …)"),
    ("atob", "(encoded)", "Decode base64 string"),
    ("btoa", "(data)", "Encode string to base64"),
    ("responseTime", "", "Legacy global: response elapsed ms (test scripts)"),
)


def globals_for_language(language: str) -> tuple[GlobalHelper, ...]:
    """Return sandbox global helpers for *language* (javascript/typescript/python)."""
    if language == "python":
        return PYTHON_SANDBOX_GLOBALS
    return JS_SANDBOX_GLOBALS
