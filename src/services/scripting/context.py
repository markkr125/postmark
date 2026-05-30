"""Script context builder, mutation applicator, and HTTP sub-request bridge.

Converts between the app's internal data formats and the
``ScriptInput``/``ScriptOutput`` types used by the runtimes.
Also provides ``execute_sub_request()`` for ``pm.sendRequest()``.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from services.scripting import ScriptInput

logger = logging.getLogger(__name__)

# Keys in scripts/events dicts that are not executable script bodies.
_SCRIPT_METADATA_KEYS = frozenset(
    {
        "debug",
        "disabled_inherited",
    }
)

# Keys whose values should be masked in console logs.
_SENSITIVE_KEYS = re.compile(
    r"(token|password|secret|key|auth|bearer|api.?key|credential)",
    re.IGNORECASE,
)


def build_script_info(
    *,
    event_name: str,
    request_name: str = "",
    request_id: str = "",
    iteration: int = 0,
    iteration_count: int = 0,
    test_filter: str | None = None,
) -> dict[str, Any]:
    """Build the ``info`` dict injected into script runtimes."""
    info: dict[str, Any] = {
        "eventName": event_name,
        "requestName": request_name,
        "requestId": request_id,
        "iteration": iteration,
        "iterationCount": iteration_count,
    }
    if test_filter:
        info["testFilter"] = test_filter
    return info


def harvest_legacy_tests(
    legacy: Any,
    test_results: list[dict[str, Any]],
) -> None:
    """Append Postman v1 ``tests`` object entries not already in *test_results*."""
    if not isinstance(legacy, dict):
        return
    existing = {str(tr.get("name", "")) for tr in test_results}
    for name, value in legacy.items():
        sname = str(name)
        if sname in existing:
            continue
        test_results.append(
            {
                "name": sname,
                "passed": bool(value),
                "error": None,
                "duration_ms": 0.0,
            }
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
    auth: dict[str, Any] | None = None,
    environment_name: str = "",
) -> ScriptInput:
    """Build a ``ScriptInput`` for a pre-request script.

    The ``response`` field is ``None`` — this tells the runtime that
    request mutations are allowed.
    """
    request: dict[str, Any] = {
        "url": url,
        "method": method,
        "headers": headers,
        "body": body,
    }
    if auth is not None:
        request["auth"] = auth
    ctx: ScriptInput = {
        "request": request,
        "response": None,
        "variables": dict(variables),
        "environment_vars": dict(environment_vars),
        "collection_vars": dict(collection_vars),
        "global_vars": dict(global_vars) if global_vars else {},
        "info": dict(info),
    }
    if iteration_data:
        ctx["iteration_data"] = iteration_data
    if environment_name:
        ctx["environment_name"] = environment_name
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
    environment_name: str = "",
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
    if environment_name:
        ctx["environment_name"] = environment_name
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
            if key in _SCRIPT_METADATA_KEYS:
                continue
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

# HTTP status codes that trigger a redirect.
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})

# Maximum redirect hops to follow (each hop is re-validated for SSRF).
_MAX_REDIRECTS = 10


def _is_blocked_subrequest_host(hostname: str) -> bool:
    """Return ``True`` if *hostname* points at a non-public address.

    Blocks loopback, private (RFC1918), link-local (incl. the cloud-metadata
    endpoint ``169.254.169.254``), reserved, multicast, and unspecified
    addresses — the targets of script-driven SSRF.  IP literals are checked
    directly; host names are resolved via DNS.  A resolution failure returns
    ``False`` so the underlying network error surfaces from httpx instead.
    """
    if not hostname:
        return True
    try:
        candidates = [str(ipaddress.ip_address(hostname))]
    except ValueError:
        try:
            candidates = [str(info[4][0]) for info in socket.getaddrinfo(hostname, None)]
        except OSError:
            return False
    for cand in candidates:
        try:
            addr = ipaddress.ip_address(cand)
        except ValueError:
            continue
        if (
            addr.is_loopback
            or addr.is_private
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return True
    return False


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

    Redirects are followed manually so every hop is re-checked against the
    SSRF host policy (an open redirect can't bounce the request to a private
    or metadata address).  Raises nothing — all errors are captured.
    """
    url = str(spec.get("url", ""))
    method = str(spec.get("method", "GET")).upper()

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

    from services.scripting.runtime_settings import RuntimeSettings

    block_local = not RuntimeSettings.allow_local_subrequests()

    # -- Execute (manual redirect loop; every hop is re-validated) ------
    try:
        import httpx

        cur_url = url
        cur_method = method
        cur_content = body.encode("utf-8") if body else None
        start = time.monotonic()
        for _hop in range(_MAX_REDIRECTS + 1):
            parsed = urlparse(cur_url)
            if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
                return {"error": f"Scheme not allowed: {parsed.scheme or '(empty)'}"}
            if block_local and _is_blocked_subrequest_host(parsed.hostname or ""):
                return {
                    "error": (
                        f"Blocked sub-request to non-public host "
                        f"'{parsed.hostname or '(none)'}'. Enable "
                        f"scripting/allow_local_subrequests to permit local targets."
                    )
                }
            resp = httpx.request(
                cur_method,
                cur_url,
                headers=headers,
                content=cur_content,
                timeout=_PER_CALL_TIMEOUT,
                follow_redirects=False,
            )
            location = resp.headers.get("location")
            if resp.status_code in _REDIRECT_CODES and location:
                cur_url = str(httpx.URL(cur_url).join(location))
                if resp.status_code in (301, 302, 303) and cur_method not in ("GET", "HEAD"):
                    cur_method = "GET"
                    cur_content = None
                    headers.pop("Content-Length", None)
                    headers.pop("content-length", None)
                continue

            if len(resp.content) > _MAX_RESPONSE_BYTES:
                return {
                    "error": (
                        f"Response too large ({len(resp.content)} bytes, "
                        f"limit {_MAX_RESPONSE_BYTES})"
                    ),
                }
            elapsed_ms = (time.monotonic() - start) * 1000
            return {
                "code": resp.status_code,
                "status": resp.reason_phrase or "",
                "headers": [{"key": k, "value": v} for k, v in resp.headers.items()],
                "body": resp.text,
                "responseTime": round(elapsed_ms, 2),
                "responseSize": len(resp.content),
            }
        return {"error": f"Too many redirects (limit {_MAX_REDIRECTS})"}
    except Exception as exc:
        logger.warning("pm.sendRequest failed: %s", exc)
        return {"error": str(exc)}
