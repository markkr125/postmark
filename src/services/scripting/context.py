"""Script context builder, mutation applicator, and HTTP sub-request bridge.

Converts between the app's internal data formats and the
``ScriptInput``/``ScriptOutput`` types used by the runtimes.
Also provides ``execute_sub_request()`` for ``pm.sendRequest()``.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from services.scripting import ScriptInput

logger = logging.getLogger(__name__)

# Keys whose values should be masked in console logs.
_SENSITIVE_KEYS = re.compile(
    r"(token|password|secret|key|auth|bearer|api.?key|credential)",
    re.IGNORECASE,
)


def build_pre_request_context(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str,
    variables: dict[str, str],
    environment_vars: dict[str, str],
    collection_vars: dict[str, str],
    global_vars: dict[str, str] | None = None,
    info: dict[str, Any],
    iteration_data: dict[str, Any] | None = None,
) -> ScriptInput:
    """Build a ``ScriptInput`` for a pre-request script.

    The ``response`` field is ``None`` — this tells the runtime that
    request mutations are allowed.
    """
    ctx: ScriptInput = {
        "request": {
            "url": url,
            "method": method,
            "headers": headers,
            "body": body,
        },
        "response": None,
        "variables": dict(variables),
        "environment_vars": dict(environment_vars),
        "collection_vars": dict(collection_vars),
        "global_vars": dict(global_vars) if global_vars else {},
        "info": dict(info),
    }
    if iteration_data:
        ctx["iteration_data"] = iteration_data
    return ctx


def build_test_context(
    *,
    request_data: dict[str, Any],
    response_data: dict[str, Any],
    variables: dict[str, str],
    environment_vars: dict[str, str],
    collection_vars: dict[str, str],
    global_vars: dict[str, str] | None = None,
    info: dict[str, Any],
    iteration_data: dict[str, Any] | None = None,
) -> ScriptInput:
    """Build a ``ScriptInput`` for a test (post-response) script.

    The ``response`` field is populated — this tells the runtime that
    request mutations should be ignored.
    """
    ctx: ScriptInput = {
        "request": dict(request_data),
        "response": dict(response_data),
        "variables": dict(variables),
        "environment_vars": dict(environment_vars),
        "collection_vars": dict(collection_vars),
        "global_vars": dict(global_vars) if global_vars else {},
        "info": dict(info),
    }
    if iteration_data:
        ctx["iteration_data"] = iteration_data
    return ctx


def apply_request_mutations(
    mutations: dict[str, Any] | None,
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str,
) -> tuple[str, str, dict[str, str], str]:
    """Apply pre-request script mutations back to the request.

    Returns ``(method, url, headers, body)`` with any valid mutations
    applied.  Invalid mutation types are silently skipped.
    """
    if not mutations:
        return method, url, headers, body

    if isinstance(mutations.get("method"), str):
        method = mutations["method"]
    if isinstance(mutations.get("url"), str):
        url = mutations["url"]
    if isinstance(mutations.get("body"), str):
        body = mutations["body"]

    raw_headers = mutations.get("headers")
    if isinstance(raw_headers, dict):
        headers = {str(k): str(v) for k, v in raw_headers.items()}
    elif isinstance(raw_headers, list):
        headers = {}
        for entry in raw_headers:
            if isinstance(entry, dict):
                headers[str(entry.get("key", ""))] = str(entry.get("value", ""))

    return method, url, headers, body


def apply_variable_changes(
    changes: dict[str, str],
    local_overrides: dict[str, str],
) -> dict[str, str]:
    """Merge variable changes from script output into local overrides.

    Enforces string values only — non-string values are converted.
    Returns a new dict (does not mutate *local_overrides*).
    """
    result = dict(local_overrides)
    for key, value in changes.items():
        result[str(key)] = str(value)
    return result


def mask_sensitive_value(key: str, value: str) -> str:
    """Mask *value* if *key* looks like a sensitive credential.

    Returns ``"***masked***"`` for sensitive keys, otherwise the
    original value unchanged.
    """
    if _SENSITIVE_KEYS.search(key):
        return "***masked***"
    return value


# -- Global variable persistence ----------------------------------------

_GLOBALS_PATH = Path(__file__).resolve().parents[3] / "data" / "globals.json"


def load_globals() -> dict[str, str]:
    """Load persisted global variables from disk."""
    if _GLOBALS_PATH.exists():
        try:
            data = json.loads(_GLOBALS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception:
            logger.warning("Failed to load globals from %s", _GLOBALS_PATH)
    return {}


def save_globals(changes: dict[str, str]) -> None:
    """Merge *changes* into the persisted global variables file.

    Reads the current file, applies changes, and writes back.
    """
    current = load_globals()
    current.update({str(k): str(v) for k, v in changes.items()})
    try:
        _GLOBALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GLOBALS_PATH.write_text(
            json.dumps(current, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        logger.warning("Failed to save globals to %s", _GLOBALS_PATH)


def normalize_events(events: Any) -> dict[str, str]:
    """Convert events from any format to the internal dict format.

    Accepts:
    - ``None`` or empty → ``{}``
    - Our dict format: ``{"pre_request": "...", "test": "..."}``
    - Postman list format: ``[{"listen": "prerequest", "script": {...}}]``

    This is the canonical normalizer — both ``FolderEditorWidget``
    and ``ScriptService`` should use it.
    """
    if not events:
        return {}
    if isinstance(events, dict):
        # Validate that values are strings.  Imported data may store nested
        # dicts (e.g. {"pre_request": {"script": "...", ...}}) — extract the
        # script text when possible.
        clean: dict[str, str] = {}
        for key, val in events.items():
            if isinstance(val, str):
                clean[key] = val
            elif isinstance(val, dict):
                # Try common nested shapes: {"script": "..."} or
                # {"script": {"exec": [...]}}
                script = val.get("script", val)
                if isinstance(script, str):
                    clean[key] = script
                elif isinstance(script, dict):
                    exec_lines = script.get("exec", [])
                    if isinstance(exec_lines, list):
                        clean[key] = "\n".join(str(ln) for ln in exec_lines)
        return clean
    if isinstance(events, list):
        result: dict[str, str] = {}
        listen_map = {"prerequest": "pre_request", "test": "test"}
        for entry in events:
            if not isinstance(entry, dict):
                continue
            listen = entry.get("listen", "")
            our_key = listen_map.get(listen)
            if our_key is None:
                continue
            script = entry.get("script", {})
            if isinstance(script, dict):
                exec_lines = script.get("exec", [])
                if isinstance(exec_lines, list):
                    result[our_key] = "\n".join(exec_lines)
        return result
    return {}


# -- HTTP sub-request bridge (pm.sendRequest) --------------------------

# Only these schemes are allowed.
_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Per-call timeout (seconds).
_PER_CALL_TIMEOUT = 10

# Maximum response body size (bytes) — prevents memory exhaustion.
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB


def execute_sub_request(spec: dict[str, Any]) -> dict[str, Any]:
    """Execute a single HTTP sub-request for ``pm.sendRequest()``.

    *spec* follows the Postman ``pm.sendRequest`` shape:

    - ``spec.url`` (str) — target URL.
    - ``spec.method`` (str) — HTTP method (default ``GET``).
    - ``spec.header`` or ``spec.headers`` — list of ``{key, value}``
      dicts or a plain ``dict``.
    - ``spec.body`` — raw body string or ``{mode, raw}`` dict.

    Returns a response dict with ``code``, ``status``, ``headers``
    (list), ``body``, ``responseTime``, and ``responseSize``.  On
    failure returns an ``error`` key instead.

    Raises nothing — all errors are captured in the returned dict.
    """
    url = str(spec.get("url", ""))
    method = str(spec.get("method", "GET")).upper()

    # -- Scheme whitelist ----------------------------------------------
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return {"error": f"Scheme not allowed: {parsed.scheme or '(empty)'}"}

    # -- Parse headers -------------------------------------------------
    raw_headers = spec.get("header", spec.get("headers", []))
    headers: dict[str, str] = {}
    if isinstance(raw_headers, list):
        for entry in raw_headers:
            if isinstance(entry, dict):
                headers[str(entry.get("key", ""))] = str(entry.get("value", ""))
    elif isinstance(raw_headers, dict):
        headers = {str(k): str(v) for k, v in raw_headers.items()}

    # -- Parse body ----------------------------------------------------
    body_raw = spec.get("body")
    body: str | None = None
    if isinstance(body_raw, str):
        body = body_raw
    elif isinstance(body_raw, dict):
        body = body_raw.get("raw")
        if body is not None:
            body = str(body)

    # -- Execute -------------------------------------------------------
    try:
        import httpx

        start = time.monotonic()
        resp = httpx.request(
            method,
            url,
            headers=headers,
            content=body.encode("utf-8") if body else None,
            timeout=_PER_CALL_TIMEOUT,
            follow_redirects=True,
        )
        elapsed_ms = (time.monotonic() - start) * 1000

        if len(resp.content) > _MAX_RESPONSE_BYTES:
            return {
                "error": (
                    f"Response too large ({len(resp.content)} bytes, limit {_MAX_RESPONSE_BYTES})"
                ),
            }

        return {
            "code": resp.status_code,
            "status": resp.reason_phrase or "",
            "headers": [{"key": k, "value": v} for k, v in resp.headers.items()],
            "body": resp.text,
            "responseTime": round(elapsed_ms, 2),
            "responseSize": len(resp.content),
        }
    except Exception as exc:
        logger.warning("pm.sendRequest failed: %s", exc)
        return {"error": str(exc)}
