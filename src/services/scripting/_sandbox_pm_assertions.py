"""Postman-style ``pm.expect`` / ``pm.response.to`` assertion chains."""

from __future__ import annotations

import json
import re
from typing import Any

from services.scripting.json_schema_mini import validate as _validate_json_schema

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
            to_object = getattr(h, "to_object", None)
            if callable(to_object):
                headers = to_object()
            elif isinstance(h, dict):
                headers = dict(h)
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

    def json_schema(self, schema: dict[str, Any]) -> _Expectation:
        """Assert value (or response JSON body) matches a JSON Schema subset."""
        resp = self._value
        data: Any = resp
        if type(resp).__name__ == "_PmResponse" and hasattr(resp, "_body"):
            raw = str(getattr(resp, "_body", "") or "").strip()
            if not raw:
                return self._assert(False, "jsonSchema: response body is empty")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                return self._assert(False, f"jsonSchema: invalid JSON ({e.msg})")
        elif isinstance(resp, dict) and "body" in resp:
            b = resp.get("body")
            if isinstance(b, str):
                try:
                    data = json.loads(b) if b.strip() else {}
                except json.JSONDecodeError as e:
                    return self._assert(False, f"jsonSchema: invalid JSON ({e.msg})")
            else:
                data = b
        ok, errors = _validate_json_schema(data, schema)
        if not ok:
            return self._assert(
                False,
                "expected value to match schema: " + ", ".join(errors),
            )
        return self


# Postman / JS naming alias for :meth:`_Expectation.json_body`.
_Expectation.jsonBody = _Expectation.json_body  # type: ignore[attr-defined, misc]
_Expectation.jsonSchema = _Expectation.json_schema  # type: ignore[attr-defined, misc]

# Alias so scripts can call ``pm.expect(x).to.have.property("key")``
# without shadowing Python's built-in ``property`` descriptor inside the class.
_Expectation.property = _Expectation.has_property  # type: ignore[attr-defined]

_Expectation.oneOf = _Expectation.one_of  # type: ignore[attr-defined]
