"""Postmark ``pm`` API for Pyodide (loaded by ``pyodide_run.mjs``).

Built from :file:`src/services/scripting/_py_sandbox.py` (shared behaviour, no
``RestrictedPython``).  ``__pm_context_json`` must exist before this module
initialises ``pm``.
"""

from __future__ import annotations

import hmac
import json
import math
import re
import sys
import time
import uuid
from base64 import b64decode, b64encode
from datetime import UTC, datetime
from hashlib import md5, sha256
from typing import Any
from urllib.parse import quote, urlencode
_CONSOLE_LIMIT = 200
_console_logs: list[dict[str, Any]] = []


def _console_emit(level: str, *args: object) -> None:
    """Capture a console message (rate-limited)."""
    if len(_console_logs) >= _CONSOLE_LIMIT:
        return
    parts = []
    for a in args:
        try:
            parts.append(str(a))
        except Exception:
            parts.append("<unprintable>")
    _console_logs.append({"level": level, "message": " ".join(parts), "timestamp": time.time()})

class _VariableScope:
    """Mimics the JS ``pm.variables`` API."""

    def __init__(self, initial: dict[str, str]) -> None:
        self._store: dict[str, str] = dict(initial)
        self._changes: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        """Get variable value by key."""
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        """Set variable value and record the change."""
        s = str(value)
        self._store[key] = s
        self._changes[key] = s

    def has(self, key: str) -> bool:
        return key in self._store

    def unset(self, key: str) -> None:
        self._store.pop(key, None)

    def to_dict(self) -> dict[str, str]:
        return dict(self._store)

    def replace_in(self, template: str) -> str:
        """Substitute ``{{var}}`` patterns in *template*."""
        import re as _re

        def _repl(m: re.Match[str]) -> str:
            k = m.group(1)
            return self._store.get(k, m.group(0))

        return _re.sub(r"\{\{(.+?)\}\}", _repl, template)


class _Expectation:
    """Chainable assertion object for ``pm.expect()``."""

    _CHAIN_NOOPS = frozenset({"to", "be", "been", "have", "has_", "at", "of", "same", "deep"})

    def __init__(self, value: Any) -> None:
        self._value = value
        self._negated = False

    def __getattr__(self, name: str) -> _Expectation:
        """Return ``self`` for readability chains (to, be, have, …)."""
        if name in _Expectation._CHAIN_NOOPS:
            return self
        msg = f"'_Expectation' has no attribute {name!r}"
        raise AttributeError(msg)

    @property
    def not_(self) -> _Expectation:
        """Negate the next assertion."""
        self._negated = not self._negated
        return self

    def _assert(self, result: bool, msg: str) -> _Expectation:
        if self._negated:
            result = not result
        if not result:
            raise AssertionError(msg)
        return self

    def equal(self, expected: Any) -> _Expectation:
        """Assert strict equality."""
        return self._assert(
            self._value == expected, f"expected {self._value!r} to equal {expected!r}"
        )

    def eql(self, expected: Any) -> _Expectation:
        """Assert deep equality (via JSON round-trip)."""
        a = json.dumps(self._value, sort_keys=True, default=str)
        b = json.dumps(expected, sort_keys=True, default=str)
        return self._assert(a == b, f"expected {self._value!r} to deeply equal {expected!r}")

    deep_equal = eql

    def a(self, type_name: str) -> _Expectation:
        """Assert type."""
        type_map: dict[str, type | tuple[type, ...]] = {
            "string": str,
            "str": str,
            "number": (int, float),
            "int": int,
            "float": float,
            "boolean": bool,
            "bool": bool,
            "list": list,
            "array": list,
            "dict": dict,
            "object": dict,
        }
        expected_type = type_map.get(type_name.lower())
        if expected_type:
            ok = isinstance(self._value, expected_type)
        else:
            ok = type(self._value).__name__ == type_name
        return self._assert(ok, f"expected {self._value!r} to be a {type_name}")

    an = a

    def include(self, val: Any) -> _Expectation:
        """Assert inclusion (substring, element, or key)."""
        ok = val in self._value if isinstance(self._value, str | list | tuple | dict) else False
        return self._assert(ok, f"expected {self._value!r} to include {val!r}")

    contain = include

    _MISSING = object()

    def has_property(self, name: str, value: Any = _MISSING) -> _Expectation:
        """Assert own property existence, optionally with value.

        Exposed to scripts as both ``has_property`` and ``property``
        (the latter is aliased after the class definition to avoid
        shadowing the built-in ``property`` descriptor).
        """
        has = isinstance(self._value, dict) and name in self._value
        if value is not _Expectation._MISSING:
            has = has and self._value.get(name) == value
        return self._assert(has, f"expected {self._value!r} to have property {name!r}")

    def length_of(self, n: int) -> _Expectation:
        """Assert length."""
        length = len(self._value) if hasattr(self._value, "__len__") else 0
        return self._assert(length == n, f"expected length {length} to be {n}")

    def above(self, n: float) -> _Expectation:
        """Assert greater than."""
        return self._assert(self._value > n, f"expected {self._value} to be above {n}")

    def below(self, n: float) -> _Expectation:
        """Assert less than."""
        return self._assert(self._value < n, f"expected {self._value} to be below {n}")

    def least(self, n: float) -> _Expectation:
        """Assert greater than or equal."""
        return self._assert(self._value >= n, f"expected {self._value} to be at least {n}")

    def most(self, n: float) -> _Expectation:
        """Assert less than or equal."""
        return self._assert(self._value <= n, f"expected {self._value} to be at most {n}")

    def match(self, pattern: str) -> _Expectation:
        """Assert regex match."""
        ok = bool(re.search(pattern, str(self._value)))
        return self._assert(ok, f"expected {self._value!r} to match {pattern!r}")

    def status(self, code: int) -> _Expectation:
        """Assert HTTP status code (dict response or :class:`_PmResponse`)."""
        actual: Any = self._value
        if isinstance(actual, dict) and "code" in actual:
            actual = int(actual["code"])
        elif type(actual).__name__ == "_PmResponse" and hasattr(actual, "code"):
            actual = int(getattr(actual, "code", 0))
        return self._assert(actual == code, f"expected status {actual} to be {code}")

    def header(self, name: str, value: Any = None) -> _Expectation:
        """Assert response header existence/value (dict or :class:`_PmResponse`)."""
        resp = self._value
        headers: dict[str, str] | None = None
        if isinstance(resp, dict) and "headers" in resp:
            h = resp.get("headers")
            headers = h if isinstance(h, dict) else None
        elif type(resp).__name__ == "_PmResponse" and hasattr(resp, "headers"):
            h = getattr(resp, "headers", None)
            headers = dict(h) if isinstance(h, dict) else None
        if not headers:
            return self._assert(False, "expected a response object with headers")
        lower = name.lower()
        found: Any = None
        for k, v in headers.items():
            if k.lower() == lower:
                found = v
                break
        if value is not None:
            return self._assert(
                found == value, f"expected header {name} to be {value!r} but got {found!r}"
            )
        return self._assert(found is not None, f"expected response to have header {name!r}")

    def json_body(self, path: str, value: Any = _MISSING) -> _Expectation:
        """Assert JSON body path (Postman-style), or path exists when *value* omitted."""
        resp = self._value
        raw: str
        if type(resp).__name__ == "_PmResponse" and hasattr(resp, "_body"):
            raw = str(getattr(resp, "_body", "") or "")
        elif isinstance(resp, dict) and "body" in resp:
            b = resp.get("body")
            raw = b if isinstance(b, str) else json.dumps(b, default=str)
        else:
            return self._assert(False, "expected a response object with a body")
        s = raw.strip()
        if not s:
            return self._assert(False, "jsonBody: response body is empty")
        try:
            data: Any = json.loads(s)
        except json.JSONDecodeError as e:
            return self._assert(False, f"jsonBody: invalid JSON ({e.msg})")
        cur: Any = data
        for part in path.split("."):
            if part == "":
                continue
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(part)
        if value is not _Expectation._MISSING:
            a = json.dumps(cur, sort_keys=True, default=str)
            b = json.dumps(value, sort_keys=True, default=str)
            return self._assert(a == b, f"expected {path!r} to be {value!r} but got {cur!r}")
        return self._assert(cur is not None, f"expected body to have path {path!r}")

    # -- Boolean property assertions --

    @property
    def true(self) -> _Expectation:
        return self._assert(self._value is True, f"expected {self._value!r} to be True")

    @property
    def false(self) -> _Expectation:
        return self._assert(self._value is False, f"expected {self._value!r} to be False")

    @property
    def none(self) -> _Expectation:
        return self._assert(self._value is None, f"expected {self._value!r} to be None")

    @property
    def exist(self) -> _Expectation:
        return self._assert(self._value is not None, "expected value to exist")

    @property
    def empty(self) -> _Expectation:
        ok = len(self._value) == 0 if isinstance(self._value, str | list | tuple | dict) else False
        return self._assert(ok, f"expected {self._value!r} to be empty")


# Postman / JS naming alias for :meth:`_Expectation.json_body`.
_Expectation.jsonBody = _Expectation.json_body  # type: ignore[attr-defined, misc]

# Alias so scripts can call ``pm.expect(x).to.have.property("key")``
# without shadowing Python's built-in ``property`` descriptor inside the class.
_Expectation.property = _Expectation.has_property  # type: ignore[attr-defined]


class _ConsolePrintCollector:
    """Print collector for RestrictedPython's rewritten ``print()`` calls."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def _call_print(self, *args: object, **kwargs: object) -> None:
        _console_emit("log", *args)


def _parse_cookie(raw: str) -> tuple[str, str] | None:
    """Parse a single ``Set-Cookie`` header value into ``(name, value)``."""
    eq = raw.find("=")
    if eq <= 0:
        return None
    name = raw[:eq].strip()
    rest = raw[eq + 1 :]
    semi = rest.find(";")
    return name, (rest[:semi].strip() if semi >= 0 else rest.strip())


class _PmCookies:
    """Cookie jar parsed from response ``Set-Cookie`` headers."""

    def __init__(self, response_data: dict[str, Any] | None) -> None:
        self._cookies: dict[str, str] = {}
        if response_data:
            headers = response_data.get("headers")
            if isinstance(headers, list):
                for entry in headers:
                    if isinstance(entry, dict) and entry.get("key", "").lower() == "set-cookie":
                        parsed = _parse_cookie(entry.get("value", ""))
                        if parsed:
                            self._cookies[parsed[0]] = parsed[1]
            elif isinstance(headers, dict):
                for k, v in headers.items():
                    if k.lower() == "set-cookie":
                        parsed = _parse_cookie(v)
                        if parsed:
                            self._cookies[parsed[0]] = parsed[1]

    def get(self, name: str) -> str | None:
        """Get cookie value by name."""
        return self._cookies.get(name)

    def get_all(self) -> list[dict[str, str]]:
        """Return all cookies as list of ``{name, value}`` dicts."""
        return [{"name": k, "value": v} for k, v in self._cookies.items()]


class _PmRequest:
    """Mutable request representation for pre-request scripts."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.url: str = data.get("url", "")
        self.method: str = data.get("method", "GET")
        self.headers: dict[str, str] = dict(data.get("headers", {}))
        self.body: str = data.get("body", "")


class _PmResponse:
    """Read-only response representation for test scripts."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.code: int = data.get("status_code", data.get("code", 0))
        self.status: str = data.get("status", "")
        self.headers: dict[str, str] = dict(data.get("headers", {}))
        self.response_time: float = data.get("response_time", data.get("elapsed_ms", 0))
        self.response_size: int = data.get("response_size", data.get("size_bytes", 0))
        self._body: str = data.get("body", "")

    def json(self) -> Any:
        body = self._body or ""
        if not body:
            raise ValueError(
                "pm.response.json(): response body is empty. "
                "Set a JSON body in the Mock response section below the script editor, "
                "or guard the call with `if pm.response.text():` before parsing."
            )
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise ValueError(
                "pm.response.json(): body is not valid JSON "
                f"({e.msg}). Check the Mock response body below the script editor."
            ) from e

    def text(self) -> str:
        return self._body

    @property
    def to(self) -> _Expectation:
        """Postman-style ``pm.response.to.have.status(…)`` (fresh chain per access)."""
        return _Expectation(self)


class _PmInfo:
    """Execution metadata."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.request_name = str(data.get("requestName", data.get("request_name", "")))
        self.request_id = str(data.get("requestId", data.get("request_id", "")))
        self.iteration = int(data.get("iteration", 0))
        self.iteration_count = int(data.get("iterationCount", data.get("iteration_count", 0)))


class _PmExecution:
    """Flow control for ``setNextRequest`` / ``skipRequest``."""

    def __init__(self) -> None:
        self._next: str | None = None
        self._next_set = self._skip = False

    def set_next_request(self, name: str | None = None) -> None:
        self._next = str(name) if name is not None else None
        self._next_set = True

    def skip_request(self) -> None:
        self._skip = True


class _PmIterationData:
    """Read-only iteration data for data-driven collection runs."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get(self, key: str) -> Any:
        return self._data.get(key)

    def to_object(self) -> dict[str, Any]:
        return dict(self._data)

    def has(self, key: str) -> bool:
        return key in self._data


class _Pm:
    """Root ``pm`` object injected into user scripts."""

    def __init__(self, context: dict[str, Any]) -> None:
        self.info = _PmInfo(context.get("info", {}))
        self.request = _PmRequest(context.get("request", {}))
        resp = context.get("response")
        self.response: _PmResponse | None = _PmResponse(resp) if resp else None
        self.cookies = _PmCookies(resp)
        self.variables = _VariableScope(context.get("variables", {}))
        self.environment = _VariableScope(context.get("environment_vars", {}))
        self.collection_variables = _VariableScope(context.get("collection_vars", {}))
        self.globals = _VariableScope(context.get("global_vars", {}))
        self.execution = _PmExecution()
        self.iteration_data = _PmIterationData(context.get("iteration_data", {}))
        self._test_results: list[dict[str, Any]] = []
        self._is_pre_request: bool = resp is None
        self._send_count = 0

    def test(self, name: str, fn: Any) -> None:
        start = time.time()
        result: dict[str, Any] = {"name": name, "passed": True, "error": None, "duration_ms": 0.0}
        try:
            fn()
        except Exception as e:
            result["passed"] = False
            result["error"] = str(e)
        result["duration_ms"] = (time.time() - start) * 1000
        self._test_results.append(result)

    def expect(self, value: Any) -> _Expectation:
        return _Expectation(value)

    def send_request(self, spec: Any, callback: Any = None) -> Any:
        """Execute sub-request via IPC to the Deno parent (``postmark_ipc``)."""
        if self._send_count >= 10:
            msg = "pm.sendRequest rate limit exceeded (max 10)"
            raise RuntimeError(msg)
        self._send_count += 1
        req_spec: dict[str, Any] = (
            {"url": spec, "method": "GET"} if isinstance(spec, str) else dict(spec)
        )
        _console_emit(
            "log",
            f'[Script] pm.sendRequest("{req_spec.get("method", "GET")} {req_spec.get("url", "")}")',
        )
        import postmark_ipc

        raw = postmark_ipc.send_request_sync(json.dumps(req_spec))
        resp: dict[str, Any] = json.loads(raw)
        if callback:
            callback(resp.get("error"), resp)
        return resp

    def require(self, spec: str) -> Any:
        """Import a package pre-installed by micropip (``name`` or ``name==version``)."""
        import importlib

        name_part = spec.split("==", 1)[0].strip().lower()
        candidates = [name_part.replace("-", "_"), name_part]
        last_err: Exception | None = None
        for mod in candidates:
            try:
                return importlib.import_module(mod)
            except Exception as e:
                last_err = e
                continue
        msg = f"pm.require({spec!r}): could not import (tried {candidates}): {last_err}"
        raise RuntimeError(msg) from last_err


def collect_pm_output() -> dict[str, Any]:
    """Build script output dict (mirrors :func:`_py_sandbox._execute_restricted` tail)."""
    all_changes: dict[str, str] = {}
    for scope in (pm.variables, pm.environment, pm.collection_variables):
        all_changes.update(scope._changes)
    global_changes: dict[str, str] = dict(pm.globals._changes)
    request_mutations: dict[str, Any] | None = None
    if pm._is_pre_request:
        request_mutations = {
            "url": pm.request.url,
            "method": pm.request.method,
            "headers": pm.request.headers,
            "body": pm.request.body,
        }
    logs = list(_console_logs)
    out: dict[str, Any] = {
        "test_results": pm._test_results,
        "console_logs": logs,
        "variable_changes": all_changes,
        "request_mutations": request_mutations,
    }
    if global_changes:
        out["global_variable_changes"] = global_changes
    if pm.execution._next_set:
        out["next_request"] = pm.execution._next
    if pm.execution._skip:
        out["skip_request"] = True
    return out


def _safe_type(obj: object) -> type:
    """Single-argument ``type()`` — blocks metaclass creation via 3-arg form."""
    return type(obj)


def _pm_print(*args: object, **kwargs: object) -> None:
    """Forward ``print()`` to the same capture as RestrictedPython scripts."""
    _console_emit("log", *args)


# fmt: off
_SAFE_BUILTINS: dict[str, Any] = {
    "True": True, "False": False, "None": None,
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "filter": filter, "float": float, "int": int,
    "isinstance": isinstance, "len": len, "list": list, "map": map,
    "max": max, "min": min, "print": _pm_print, "range": range, "reversed": reversed,
    "round": round, "set": set, "sorted": sorted, "str": str,
    "sum": sum, "tuple": tuple, "type": _safe_type, "zip": zip,
}
# fmt: on

# fmt: off
_SAFE_STDLIB: dict[str, Any] = {
    "json_loads": json.loads, "json_dumps": json.dumps,
    "re_match": re.match, "re_search": re.search,
    "re_findall": re.findall, "re_sub": re.sub,
    "math_ceil": math.ceil, "math_floor": math.floor,
    "math_sqrt": math.sqrt, "math_pow": math.pow, "math_log": math.log,
    "math_pi": math.pi, "math_e": math.e,
    "b64encode": b64encode, "b64decode": b64decode,
    "hashlib_md5": lambda d: md5(d.encode() if isinstance(d, str) else d).hexdigest(),
    "hashlib_sha256": lambda d: sha256(d.encode() if isinstance(d, str) else d).hexdigest(),
    "hashlib_hmac_sha256": lambda d, k: hmac.new(
        k.encode() if isinstance(k, str) else k,
        d.encode() if isinstance(d, str) else d,
        "sha256",
    ).hexdigest(),
    "uuid_v4": lambda: str(uuid.uuid4()),
    "datetime_now": lambda: datetime.now(tz=UTC).isoformat(),
    "datetime_utcnow": lambda: datetime.now(tz=UTC).isoformat(),
    "url_quote": quote, "url_urlencode": urlencode,
}
# fmt: on


def init_pm() -> None:
    """Parse ``__pm_context_json`` and set ``pm``."""
    global pm
    ctx: dict[str, Any] = json.loads(__pm_context_json)
    globals()["pm"] = _Pm(ctx)


def run_user_script(src: str) -> None:
    """Execute user *src* with the same globals shape as the RestrictedPython path."""
    g: dict[str, Any] = {}
    g.update(_SAFE_BUILTINS)
    g["__builtins__"] = _SAFE_BUILTINS
    g["pm"] = pm
    g.update(_SAFE_STDLIB)
    exec(compile(src, "<script>", "exec"), g, g)
