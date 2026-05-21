"""Postmark ``pm`` API for Pyodide (loaded by ``pyodide_run.mjs``).

Built from :file:`src/services/scripting/_py_sandbox.py` (shared behaviour, no
``RestrictedPython``).  ``__pm_context_json`` must exist before this module
initialises ``pm``.
"""

from __future__ import annotations

import hmac
import inspect
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

# Prelude lines prepended to ``<script>`` before user ``exec`` (see py_runtime.py).
_PY_PRELUDE_LINE_COUNT = 0


def _console_source_line() -> int | None:
    """Best-effort 0-based editor line for the console call site."""
    # ``inspect`` is imported at module load (before user ``exec``) so Pyodide
    # does not hit file-descriptor limits when opening the stdlib module later.
    offset = _PY_PRELUDE_LINE_COUNT
    raw = globals().get("__pm_user_script_line0", 0) or 0
    try:
        offset += int(raw)
    except (TypeError, ValueError):
        offset += 0
    frame = inspect.currentframe()
    if frame is None:
        return None
    f = frame.f_back
    shim_names = frozenset({"_console_emit", "_call_print", "_pm_print"})
    while f is not None:
        if f.f_code.co_filename == "<script>":
            line0 = f.f_lineno - 1 - offset
            return line0 if line0 >= 0 else None
        if f.f_code.co_name in shim_names:
            f = f.f_back
            continue
        f = f.f_back
    return None


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
    entry: dict[str, Any] = {
        "level": level,
        "message": " ".join(parts),
        "timestamp": time.time(),
    }
    sl = _console_source_line()
    if sl is not None:
        entry["source_line"] = sl
    _console_logs.append(entry)


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

    def clear(self) -> None:
        """Remove all keys from this scope (Postman ``clear``)."""
        for k in list(self._store.keys()):
            self._store.pop(k, None)

    def to_dict(self) -> dict[str, str]:
        return dict(self._store)

    def toObject(self) -> dict[str, str]:
        """Postman camelCase alias for :meth:`to_dict`."""
        return self.to_dict()

    def replace_in(self, template: str) -> str:
        """Substitute ``{{var}}`` patterns in *template*."""
        import re as _re

        def _repl(m: re.Match[str]) -> str:
            k = m.group(1)
            return self._store.get(k, m.group(0))

        return _re.sub(r"\{\{(.+?)\}\}", _repl, template)


# HTTP status code to canonical reason phrase (used by ``.status("Created")``;
# referenced from ``data/snippets/python.json`` test snippets).
_HTTP_REASON: dict[int, str] = {
    100: "Continue",
    101: "Switching Protocols",
    200: "OK",
    201: "Created",
    202: "Accepted",
    203: "Non-Authoritative Information",
    204: "No Content",
    205: "Reset Content",
    206: "Partial Content",
    300: "Multiple Choices",
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    304: "Not Modified",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    400: "Bad Request",
    401: "Unauthorized",
    402: "Payment Required",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    411: "Length Required",
    412: "Precondition Failed",
    413: "Payload Too Large",
    414: "URI Too Long",
    415: "Unsupported Media Type",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}


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

    def status(self, code: int | str) -> _Expectation:
        """Assert HTTP status code (numeric or canonical reason phrase)."""
        actual: Any = self._value
        if isinstance(actual, dict) and "code" in actual:
            actual = int(actual["code"])
        elif type(actual).__name__ == "_PmResponse" and hasattr(actual, "code"):
            actual = int(getattr(actual, "code", 0))
        if isinstance(code, str):
            code_int = int(actual) if isinstance(actual, int) else 0
            reason = _HTTP_REASON.get(code_int, "")
            return self._assert(
                reason.lower() == code.lower(),
                f"expected status {actual} ({reason!r}) to be {code!r}",
            )
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

    def body(self, expected: str | re.Pattern[str]) -> _Expectation:
        """Assert response body equals *expected* string or matches *expected* regex."""
        resp = self._value
        actual = ""
        if isinstance(resp, dict):
            actual = str(resp.get("body", "") or "")
        elif type(resp).__name__ == "_PmResponse":
            text_fn = getattr(resp, "text", None)
            actual = str(text_fn()) if callable(text_fn) else str(getattr(resp, "_body", "") or "")
        elif isinstance(resp, str):
            actual = resp
        preview = actual if len(actual) <= 80 else actual[:77] + "..."
        if isinstance(expected, re.Pattern):
            return self._assert(
                bool(expected.search(actual)),
                f"expected body to match {expected!r} but got {preview!r}",
            )
        return self._assert(
            actual == expected,
            f"expected body to equal {expected!r} but got {preview!r}",
        )

    def one_of(self, allowed: list[Any]) -> _Expectation:
        """Assert value is in *allowed* (``in`` / strict list membership)."""
        if not isinstance(allowed, list):
            return self._assert(False, "oneOf expects a list argument")
        ok = self._value in allowed
        return self._assert(ok, f"expected {self._value!r} to be one of {allowed!r}")

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
        # Lodash-style path: ``a.b[0].c`` → ["a", "b", 0, "c"].
        tokens: list[Any] = []
        for chunk in path.split("."):
            for tok in re.split(r"[\[\]]+", chunk):
                if tok == "":
                    continue
                tokens.append(int(tok) if tok.lstrip("-").isdigit() else tok)
        for tok in tokens:
            if isinstance(tok, int):
                if isinstance(cur, list) and -len(cur) <= tok < len(cur):
                    cur = cur[tok]
                else:
                    cur = None
                    break
            else:
                if isinstance(cur, dict):
                    cur = cur.get(tok)
                else:
                    cur = None
                    break
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

# Postman / JS-style alias for ``one_of``.
_Expectation.oneOf = _Expectation.one_of  # type: ignore[attr-defined]


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


class _HeaderList:
    """Postman-style header collection (mirrors ``__makeHeaderList`` in JS).

    Provides case-insensitive ``get/has/find``, ordered iteration via
    ``each/all/idx``, dict-style ``[]`` sugar, and mutation methods
    (``add/remove/upsert``) gated behind ``mutable=True`` so response
    headers and test-time request headers raise on writes.

    See https://www.postmanlabs.com/postman-collection/HeaderList.html
    for the canonical Postman shape.
    """

    def __init__(self, source: Any, *, mutable: bool = False) -> None:
        self._items: list[tuple[str, str]] = []
        if isinstance(source, dict):
            for k, v in source.items():
                self._items.append((str(k), str(v)))
        elif isinstance(source, list):
            for entry in source:
                if isinstance(entry, dict):
                    k = str(entry.get("key") or entry.get("name") or "")
                    v = str(entry.get("value") or "")
                    if k:
                        self._items.append((k, v))
                elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    self._items.append((str(entry[0]), str(entry[1])))
        self._mutable = mutable

    def get(self, name: str) -> str | None:
        lname = name.lower()
        for k, v in self._items:
            if k.lower() == lname:
                return v
        return None

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    def all(self) -> list[dict[str, str]]:
        return [{"key": k, "value": v} for k, v in self._items]

    def each(self, fn: Any) -> None:
        for k, v in self._items:
            fn({"key": k, "value": v})

    def find(self, name: str) -> dict[str, str] | None:
        lname = name.lower()
        for k, v in self._items:
            if k.lower() == lname:
                return {"key": k, "value": v}
        return None

    def idx(self, n: int) -> dict[str, str] | None:
        if 0 <= n < len(self._items):
            k, v = self._items[n]
            return {"key": k, "value": v}
        return None

    def to_object(self) -> dict[str, str]:
        return {k: v for k, v in self._items}

    def toObject(self) -> dict[str, str]:  # noqa: N802
        """Postman camelCase alias for :meth:`to_object`."""
        return self.to_object()

    def add(self, entry: Any) -> None:
        self._require_mutable()
        if not isinstance(entry, dict):
            return
        k = str(entry.get("key") or entry.get("name") or "")
        v = str(entry.get("value") or "")
        if k:
            self._items.append((k, v))

    def remove(self, name: str) -> None:
        self._require_mutable()
        lname = name.lower()
        self._items = [(k, v) for k, v in self._items if k.lower() != lname]

    def upsert(self, entry: Any) -> None:
        self._require_mutable()
        if not isinstance(entry, dict):
            return
        k = str(entry.get("key") or entry.get("name") or "")
        v = str(entry.get("value") or "")
        if not k:
            return
        lname = k.lower()
        for i, (ek, _) in enumerate(self._items):
            if ek.lower() == lname:
                self._items[i] = (ek, v)
                return
        self._items.append((k, v))

    def _require_mutable(self) -> None:
        if not self._mutable:
            msg = "HeaderList is immutable (response headers or test-time request headers)"
            raise RuntimeError(msg)

    def __getitem__(self, name: str) -> str | None:
        return self.get(name)

    def __setitem__(self, name: str, value: str) -> None:
        self.upsert({"key": name, "value": str(value)})

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self.has(name)

    def __iter__(self) -> Any:
        return iter(self.all())

    def __len__(self) -> int:
        return len(self._items)


class _PmUrl:
    """Postman-style ``Url`` wrapper (mirrors ``__pm_makeUrl`` in JS).

    Exposes ``toString/getHost/getPath/getQueryString``, plus parsed
    components ``protocol/host/port/path`` and a mutable ``query``
    HeaderList. See
    https://www.postmanlabs.com/postman-collection/Url.html.
    """

    def __init__(self, raw: Any) -> None:
        from urllib.parse import parse_qsl, urlparse

        self._raw = str(raw or "")
        try:
            self._parsed = urlparse(self._raw)
        except Exception:
            self._parsed = None
        query_items: list[dict[str, str]] = []
        if self._parsed and self._parsed.query:
            for k, v in parse_qsl(self._parsed.query, keep_blank_values=True):
                query_items.append({"key": k, "value": v})
        self.query = _HeaderList(query_items, mutable=True)

    def toString(self) -> str:  # noqa: N802
        return self._raw

    def __str__(self) -> str:
        return self._raw

    def getHost(self) -> str:  # noqa: N802
        return self._parsed.hostname or "" if self._parsed else ""

    def getPath(self) -> str:  # noqa: N802
        return self._parsed.path or "" if self._parsed else ""

    def getQueryString(self) -> str:  # noqa: N802
        return self._parsed.query or "" if self._parsed else ""

    @property
    def protocol(self) -> str:
        return (self._parsed.scheme or "") if self._parsed else ""

    @property
    def host(self) -> str:
        return self.getHost()

    @property
    def port(self) -> str:
        if self._parsed and self._parsed.port is not None:
            return str(self._parsed.port)
        return ""

    @property
    def path(self) -> str:
        return self.getPath()


class _PmRequestBody:
    """Discriminated union for ``pm.request.body`` (matches Postman ``RequestBody``).

    ``mode`` is one of ``"raw" | "urlencoded" | "formdata" | "graphql" |
    "file" | ""``. ``urlencoded`` and ``formdata`` are :class:`_HeaderList`
    instances. See https://www.postmanlabs.com/postman-collection/RequestBody.html.
    """

    def __init__(self, body: Any) -> None:
        b: dict[str, Any]
        if isinstance(body, str):
            b = {"mode": "raw", "raw": body}
        elif isinstance(body, dict):
            b = body
        else:
            b = {}
        self.mode: str = str(b.get("mode") or ("raw" if b.get("raw") else ""))
        self.raw: str = str(b.get("raw") or "")
        self.urlencoded = _HeaderList(b.get("urlencoded") or [], mutable=True)
        self.formdata = _HeaderList(b.get("formdata") or [], mutable=True)
        self.graphql = b.get("graphql")
        self.file = b.get("file")

    def __str__(self) -> str:
        return self.raw or ""


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

    def getAll(self) -> list[dict[str, str]]:  # noqa: N802
        """Postman camelCase alias for :meth:`get_all`."""
        return self.get_all()

    def jar(self) -> Any:
        """Return a ``CookieJar``-shaped helper.

        Read paths return what we know from this response; mutation
        paths (``set/unset/clear``) raise a documented error pending a
        host-side cookie store.
        """

        outer = self

        class _CookieJar:
            def get(self_inner, _url: str, name: str, callback: Any = None) -> Any:
                value = outer.get(name)
                if callback:
                    callback(None, value)
                return value

            def getAll(self_inner, _url: str, callback: Any = None) -> list[dict[str, str]]:  # noqa: N802
                values = outer.get_all()
                if callback:
                    callback(None, values)
                return values

            def set(self_inner, *_a: Any, **_kw: Any) -> None:
                msg = "pm.cookies.jar().set is not yet supported in postmark"
                raise RuntimeError(msg)

            def unset(self_inner, *_a: Any, **_kw: Any) -> None:
                msg = "pm.cookies.jar().unset is not yet supported in postmark"
                raise RuntimeError(msg)

            def clear(self_inner, *_a: Any, **_kw: Any) -> None:
                msg = "pm.cookies.jar().clear is not yet supported in postmark"
                raise RuntimeError(msg)

        return _CookieJar()


class _PmRequest:
    """Mutable request representation for pre-request scripts.

    ``url`` is wrapped in :class:`_PmUrl`, ``headers`` in
    :class:`_HeaderList` (mutable when ``is_pre_request`` is True), and
    ``body`` in :class:`_PmRequestBody` so Postman scripts that branch
    on ``pm.request.body.mode`` or call ``pm.request.url.query.add(...)``
    work without modification. The string-based attributes
    (``_url_str``, ``_body_str``) are preserved for the host context
    serializer in :func:`collect_pm_output`.
    """

    def __init__(self, data: dict[str, Any], *, is_pre_request: bool = True) -> None:
        self._url_str: str = str(data.get("url", "") or "")
        self.url = _PmUrl(self._url_str)
        self.method: str = data.get("method", "GET")
        self.headers = _HeaderList(data.get("headers", {}), mutable=is_pre_request)
        body_raw = data.get("body", "")
        self._body_str: str = body_raw if isinstance(body_raw, str) else ""
        self.body = _PmRequestBody(body_raw)


_HTTP_REASON: dict[int, str] = {
    100: "Continue",
    101: "Switching Protocols",
    200: "OK",
    201: "Created",
    202: "Accepted",
    203: "Non-Authoritative Information",
    204: "No Content",
    205: "Reset Content",
    206: "Partial Content",
    300: "Multiple Choices",
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    304: "Not Modified",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    400: "Bad Request",
    401: "Unauthorized",
    402: "Payment Required",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    411: "Length Required",
    412: "Precondition Failed",
    413: "Payload Too Large",
    414: "URI Too Long",
    415: "Unsupported Media Type",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}


class _PmResponse:
    """Read-only response representation for test scripts.

    Mirrors https://www.postmanlabs.com/postman-collection/Response.html.
    ``headers`` is a :class:`_HeaderList` (immutable), ``cookies`` is a
    :class:`_PmCookies` parsed from ``Set-Cookie``, and
    ``originalRequest`` (when the host provides it) carries the request
    that produced this response wrapped as a Postman-style request.
    """

    def __init__(
        self,
        data: dict[str, Any],
        original_request: dict[str, Any] | None = None,
    ) -> None:
        self.code: int = data.get("status_code", data.get("code", 0))
        self.status: str = data.get("status", "")
        self.headers = _HeaderList(data.get("headers", {}), mutable=False)
        self.response_time: float = data.get("response_time", data.get("elapsed_ms", 0))
        self.response_size: int = data.get("response_size", data.get("size_bytes", 0))
        self._body: str = data.get("body", "")
        self.cookies = _PmCookies(data)
        if original_request:
            self.originalRequest = _PmRequest(original_request, is_pre_request=False)
        else:
            self.originalRequest = None

    def json(self) -> Any:
        body = self._body or ""
        if not body:
            raise ValueError(
                "pm.response.json(): response body is empty. "
                "Set a JSON body on the Mock response tab (Body field), "
                "or guard the call with `if pm.response.text():` before parsing."
            )
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise ValueError(
                "pm.response.json(): body is not valid JSON "
                f"({e.msg}). Check the Mock response body on the Mock response tab."
            ) from e

    def text(self) -> str:
        return self._body

    def reason(self) -> str:
        """Canonical HTTP reason phrase for ``self.code``."""
        return _HTTP_REASON.get(int(self.code or 0), "")

    def mime(self) -> dict[str, str]:
        """Parse ``Content-Type`` into ``{type, charset}`` (Postman shape)."""
        ct = self.headers.get("Content-Type") or ""
        sep = ct.find(";")
        primary = ct[:sep].strip() if sep >= 0 else ct.strip()
        m = re.search(r"charset=([^;]+)", ct, flags=re.IGNORECASE)
        charset = m.group(1).strip() if m else ""
        return {"type": primary, "charset": charset}

    def dataURI(self) -> str:  # noqa: N802
        """Encode the body as a ``data:`` URI using ``Content-Type`` (or octet-stream)."""
        ct = self.headers.get("Content-Type") or "application/octet-stream"
        body_bytes = (self._body or "").encode("utf-8")
        return "data:" + ct + ";base64," + b64encode(body_bytes).decode("ascii")

    def size(self) -> int:
        """Return ``response_size`` if known, otherwise ``len(body)``."""
        return self.response_size or (len(self._body) if self._body else 0)

    @property
    def responseTime(self) -> float:  # noqa: N802
        """Postman-style alias for :attr:`response_time`."""
        return self.response_time

    @property
    def responseSize(self) -> int:  # noqa: N802
        """Postman-style alias for :attr:`response_size`."""
        return self.response_size

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
        raw_filter = data.get("testFilter")
        self.test_filter = str(raw_filter) if raw_filter else None


class _PmExecutionLocation:
    """``pm.execution.location`` — folder/collection path for the current request."""

    def __init__(self, data: Any) -> None:
        if isinstance(data, dict):
            self.current = str(data.get("current", "") or "")
            self._path: list[str] = [str(p) for p in (data.get("path") or [])]
        elif isinstance(data, str):
            self.current = data
            self._path = []
        else:
            self.current = ""
            self._path = []

    def __str__(self) -> str:
        return self.current


class _PmExecution:
    """Flow control for ``setNextRequest`` / ``skipRequest`` plus ``location``."""

    def __init__(self, location: Any = None) -> None:
        self._next: str | None = None
        self._next_set = self._skip = False
        self.location = _PmExecutionLocation(location)

    def set_next_request(self, name: str | None = None) -> None:
        self._next = str(name) if name is not None else None
        self._next_set = True

    def skip_request(self) -> None:
        self._skip = True

    # Postman camelCase aliases.
    def setNextRequest(self, name: str | None = None) -> None:  # noqa: N802
        self.set_next_request(name)

    def skipRequest(self) -> None:  # noqa: N802
        self.skip_request()


class _PmIterationData:
    """Read-only iteration data for data-driven collection runs."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get(self, key: str) -> Any:
        return self._data.get(key)

    def to_object(self) -> dict[str, Any]:
        return dict(self._data)

    def toObject(self) -> dict[str, Any]:
        """Postman camelCase alias for :meth:`to_object`."""
        return dict(self._data)

    def has(self, key: str) -> bool:
        return key in self._data


class _ResolvedVariables:
    """Postman-style ``pm.variables`` — read-through across scopes.

    Read precedence (highest first): local → iterationData → environment
    → collectionVariables → globals. Writes land in ``local`` so
    successive reads from any scope still see the override.
    """

    def __init__(self, owner: _Pm, initial_local: dict[str, str]) -> None:
        self._owner = owner
        self._local: dict[str, str] = dict(initial_local)
        self._changes: dict[str, str] = {}

    def get(self, key: str) -> Any:
        if key in self._local:
            return self._local[key]
        v = self._owner.iteration_data.get(key)
        if v is not None:
            return v
        for scope in (
            self._owner.environment,
            self._owner.collection_variables,
            self._owner.globals,
        ):
            v = scope.get(key)
            if v is not None:
                return v
        return None

    def set(self, key: str, value: Any) -> None:
        s = str(value)
        self._local[key] = s
        self._changes[key] = s

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def unset(self, key: str) -> None:
        self._local.pop(key, None)

    def clear(self) -> None:
        self._local.clear()

    def to_object(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        out.update(self._owner.globals.to_dict())
        out.update(self._owner.collection_variables.to_dict())
        out.update(self._owner.environment.to_dict())
        if hasattr(self._owner.iteration_data, "to_object"):
            out.update(self._owner.iteration_data.to_object())
        out.update(self._local)
        return out

    def toObject(self) -> dict[str, Any]:  # noqa: N802
        return self.to_object()

    def to_dict(self) -> dict[str, Any]:
        """Compatibility shim used by ``collect_pm_output``."""
        return self.to_object()

    def replace_in(self, template: str) -> str:
        merged = self.to_object()

        def _repl(m: re.Match[str]) -> str:
            k = m.group(1)
            return str(merged.get(k, m.group(0)))

        return re.sub(r"\{\{(.+?)\}\}", _repl, template)

    def replaceIn(self, template: str) -> str:  # noqa: N802
        return self.replace_in(template)


class _SkipTest(Exception):  # noqa: N818  (Postman semantics: not an error)
    """Raised by inline ``ctx.skip()`` to short-circuit a ``pm.test`` body."""


class _PmTestCallable:
    """Callable shim so ``pm.test(name, fn)`` works AND ``pm.test.skip(...)`` works.

    ``pm.test.skip(name, fn)`` records a skipped result without
    invoking *fn*. Inside a normal ``pm.test`` callback users can call
    ``ctx.skip()`` (the first positional argument the callback
    receives) to mark this run skipped mid-flight.
    """

    def __init__(self, owner: _Pm) -> None:
        self._owner = owner

    def __call__(self, name: str, fn: Any) -> None:
        filt = self._owner.info.test_filter
        if filt is not None and str(name) != str(filt):
            return
        start = time.time()
        result: dict[str, Any] = {
            "name": str(name),
            "passed": True,
            "error": None,
            "duration_ms": 0.0,
        }
        skip_marker = {"hit": False}

        class _Ctx:
            def skip(self_inner) -> None:
                skip_marker["hit"] = True
                raise _SkipTest()

        try:
            try:
                fn(_Ctx())
            except TypeError:
                # Callback may not accept the ctx arg — call without it.
                fn()
        except _SkipTest:
            result["passed"] = True
            result["skipped"] = True
        except Exception as e:
            result["passed"] = False
            result["error"] = str(e)
        if skip_marker["hit"]:
            result["skipped"] = True
        result["duration_ms"] = (time.time() - start) * 1000
        src = getattr(self._owner, "_test_source_name", None)
        if src:
            result["source_name"] = str(src)
        self._owner._test_results.append(result)

    def skip(self, name: str, _fn: Any = None) -> None:
        """Record *name* as skipped without invoking the callback."""
        self._owner._test_results.append(
            {
                "name": str(name),
                "passed": True,
                "skipped": True,
                "error": None,
                "duration_ms": 0.0,
            }
        )


class _PmVisualizer:
    """``pm.visualizer`` stub — `set` raises a documented "not supported" error.

    Tracked under "Out of scope" in ``data/snippets/README.md``. The
    explicit raise (rather than a no-op) makes it obvious to users that
    the call did nothing and forces them to remove it from scripts they
    paste from Postman.
    """

    def set(self, _template: Any = None, _data: Any = None, _options: Any = None) -> None:
        msg = (
            "pm.visualizer.set is not supported in postmark — "
            "see data/snippets/README.md (Out of scope) for the rationale."
        )
        raise RuntimeError(msg)


# Built-in modules accessible via ``pm.require("name")`` (Postman parity).
# Names that can't be vendored from the Python sandbox raise a documented
# error so users see "not supported" rather than a generic ImportError.
_PM_BUILTIN_MODULE_NAMES: frozenset[str] = frozenset(
    {
        "tv4",
        "xml2js",
        "crypto-js",
        "chai",
        "lodash",
        "moment",
        "cheerio",
        "csv-parse/lib/sync",
        "ajv",
        "atob",
        "btoa",
        "uuid",
    }
)


class _Pm:
    """Root ``pm`` object injected into user scripts."""

    def __init__(self, context: dict[str, Any]) -> None:
        self.info = _PmInfo(context.get("info", {}))
        resp = context.get("response")
        self._is_pre_request: bool = resp is None
        self.request = _PmRequest(
            context.get("request", {}),
            is_pre_request=self._is_pre_request,
        )
        original_req = context.get("original_request") or context.get("request") or {}
        self.response: _PmResponse | None = _PmResponse(resp, original_req) if resp else None
        self.cookies = _PmCookies(resp)
        # Scope objects must exist before _ResolvedVariables references them.
        self.environment = _VariableScope(context.get("environment_vars", {}))
        self.collection_variables = _VariableScope(context.get("collection_vars", {}))
        self.globals = _VariableScope(context.get("global_vars", {}))
        self.iteration_data = _PmIterationData(context.get("iteration_data", {}))
        self.variables = _ResolvedVariables(self, context.get("variables", {}))
        self.execution = _PmExecution(context.get("execution_location") or {})
        self.visualizer = _PmVisualizer()
        self._test_results: list[dict[str, Any]] = []
        self._test_source_name: str | None = None
        self._send_count = 0
        # Bind ``test`` as a callable instance so ``pm.test.skip(name, fn)``
        # works without rewriting ``def test`` as a class. Built lazily so
        # method lookup of ``self.test`` returns the same callable each time.
        self.test = _PmTestCallable(self)

    def expect(self, value: Any) -> _Expectation:
        return _Expectation(value)

    # -- Postman camelCase aliases on the root ``pm`` object ----------
    @property
    def collectionVariables(self) -> _VariableScope:  # noqa: N802
        return self.collection_variables

    @property
    def iterationData(self) -> _PmIterationData:  # noqa: N802
        return self.iteration_data

    def sendRequest(self, spec: Any, callback: Any = None) -> Any:  # noqa: N802
        return self.send_request(spec, callback)

    def send_request(self, spec: Any, callback: Any = None) -> _PmResponse:
        """Execute sub-request via IPC; return a wrapped :class:`_PmResponse`."""
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
        resp_dict: dict[str, Any] = json.loads(raw)
        wrapped = _PmResponse(resp_dict, req_spec)
        if callback:
            callback(resp_dict.get("error"), wrapped)
        return wrapped

    def require(self, spec: str) -> Any:
        """Postman-style ``pm.require``: bare names map to the built-in vendor table.

        Bare names like ``"crypto-js"``, ``"lodash"``, ``"uuid"`` are
        looked up in :data:`_PM_BUILTIN_MODULE_NAMES` and dispatched to
        the import path. Otherwise behaves like the original importlib
        fallback so ``pm.require("name==1.2.3")`` style still works.
        """
        import importlib

        if not isinstance(spec, str):
            msg = "pm.require: specifier must be a string"
            raise RuntimeError(msg)
        name_part = spec.split("==", 1)[0].strip().lower()
        candidates: list[str] = []
        if name_part in _PM_BUILTIN_MODULE_NAMES or name_part in {
            n.replace("-", "_") for n in _PM_BUILTIN_MODULE_NAMES
        }:
            candidates.append(name_part.replace("-", "_"))
            candidates.append(name_part)
        else:
            candidates.append(name_part.replace("-", "_"))
            candidates.append(name_part)
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
        # ``pm.request.url`` / ``.body`` are now wrapper objects; serialise
        # back to plain JSON-friendly shapes for the host context.
        url_val = pm.request.url
        url_str = url_val.toString() if hasattr(url_val, "toString") else str(url_val)
        body_val = pm.request.body
        if hasattr(body_val, "raw"):
            body_str = str(body_val.raw or "")
        else:
            body_str = str(body_val or "")
        headers_val = pm.request.headers
        if hasattr(headers_val, "to_object"):
            headers_dict = headers_val.to_object()
        elif isinstance(headers_val, dict):
            headers_dict = dict(headers_val)
        else:
            headers_dict = {}
        request_mutations = {
            "url": url_str,
            "method": pm.request.method,
            "headers": headers_dict,
            "body": body_str,
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
    # Common exception types so user scripts can ``try/except`` (Postman parity).
    "Exception": Exception, "ValueError": ValueError, "RuntimeError": RuntimeError,
    "KeyError": KeyError, "TypeError": TypeError, "IndexError": IndexError,
    "AssertionError": AssertionError, "AttributeError": AttributeError,
}
# fmt: on

# fmt: off
_SAFE_STDLIB: dict[str, Any] = {
    "json_loads": json.loads, "json_dumps": json.dumps,
    "re_match": re.match, "re_search": re.search,
    "re_findall": re.findall, "re_sub": re.sub, "re_compile": re.compile,
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


def _legacy_globals() -> dict[str, Any]:
    """Return Postman v1 legacy script globals (``responseBody`` etc.).

    These mirror the JS bootstrap's ``globalThis.responseBody`` /
    ``responseCode`` / ``responseHeaders`` / ``tests`` / ``xml2Json``
    so old Postman scripts continue to run. Modern code should use
    ``pm.response.*`` / ``pm.test`` instead — kept for compatibility.
    """
    out: dict[str, Any] = {}
    if pm.response is not None:
        out["responseBody"] = pm.response.text()
        out["responseCode"] = {
            "code": pm.response.code,
            "name": pm.response.reason(),
        }
        out["responseHeaders"] = pm.response.headers.to_object()
    else:
        out["responseBody"] = ""
        out["responseCode"] = {"code": 0, "name": ""}
        out["responseHeaders"] = {}
    out["tests"] = {}

    def _xml2_json(xml_text: Any) -> Any:
        try:
            import xml.etree.ElementTree as ET

            def _node_to_dict(node: Any) -> Any:
                children = list(node)
                if not children:
                    return node.text or ""
                result: dict[str, Any] = {}
                for child in children:
                    val = _node_to_dict(child)
                    if child.tag in result:
                        existing = result[child.tag]
                        if isinstance(existing, list):
                            existing.append(val)
                        else:
                            result[child.tag] = [existing, val]
                    else:
                        result[child.tag] = val
                return result

            root = ET.fromstring(str(xml_text))
            return {root.tag: _node_to_dict(root)}
        except Exception:
            return None

    out["xml2Json"] = _xml2_json
    return out


def run_user_script(src: str) -> None:
    """Execute user *src* with the same globals shape as the RestrictedPython path."""
    g: dict[str, Any] = {}
    g.update(_SAFE_BUILTINS)
    g["__builtins__"] = _SAFE_BUILTINS
    g["pm"] = pm
    g["postman"] = _PostmanLegacyV1(pm)
    g.update(_SAFE_STDLIB)
    g.update(_legacy_globals())
    exec(compile(src, "<script>", "exec"), g, g)


class _PostmanLegacyV1:
    """Legacy Postman v1 ``postman.*`` shim (mirrors JS ``postman`` global).

    Provides ``setEnvironmentVariable`` / ``getEnvironmentVariable`` /
    ``clearEnvironmentVariable`` / ``setGlobalVariable`` /
    ``getGlobalVariable`` / ``clearGlobalVariable`` / ``setNextRequest``.
    Kept for compatibility with very old Postman scripts.
    """

    def __init__(self, owner: _Pm) -> None:
        self._pm = owner

    def setEnvironmentVariable(self, key: str, value: Any) -> None:  # noqa: N802
        self._pm.environment.set(key, str(value))

    def getEnvironmentVariable(self, key: str) -> Any:  # noqa: N802
        return self._pm.environment.get(key)

    def clearEnvironmentVariable(self, key: str) -> None:  # noqa: N802
        self._pm.environment.unset(key)

    def setGlobalVariable(self, key: str, value: Any) -> None:  # noqa: N802
        self._pm.globals.set(key, str(value))

    def getGlobalVariable(self, key: str) -> Any:  # noqa: N802
        return self._pm.globals.get(key)

    def clearGlobalVariable(self, key: str) -> None:  # noqa: N802
        self._pm.globals.unset(key)

    def setNextRequest(self, name: str | None) -> None:  # noqa: N802
        self._pm.execution.set_next_request(name)
