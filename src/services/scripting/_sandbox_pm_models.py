"""Postman API model types for the RestrictedPython sandbox."""

from __future__ import annotations

import json
import re
from typing import Any

from services.scripting._sandbox_pm_assertions import _Expectation, _HTTP_REASON

_PM_DEBUG_BODY_PREVIEW_MAX = 400


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
    (``add/remove/upsert``) gated behind ``mutable=True``.

    See https://www.postmanlabs.com/postman-collection/HeaderList.html.
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
                elif isinstance(entry, list | tuple) and len(entry) >= 2:
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

    def toObject(self) -> dict[str, str]:
        return self.to_object()

    def __pm_debug__(self) -> dict[str, str]:
        """Debug-tree view: ``{header_name: value}`` (last-wins on duplicates)."""
        return self.to_object()

    def __repr__(self) -> str:
        return f"<HeaderList {self.to_object()!r}>"

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
            msg = "HeaderList is immutable (response or test-time request headers)"
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
    """Postman-style ``Url`` wrapper. See ``_HeaderList`` notes."""

    def __init__(self, raw: Any) -> None:
        from urllib.parse import ParseResult, parse_qsl, urlparse

        self._raw = str(raw or "")
        self._parsed: ParseResult | None
        try:
            self._parsed = urlparse(self._raw)
        except Exception:
            self._parsed = None
        query_items: list[dict[str, str]] = []
        if self._parsed and self._parsed.query:
            for k, v in parse_qsl(self._parsed.query, keep_blank_values=True):
                query_items.append({"key": k, "value": v})
        self.query = _HeaderList(query_items, mutable=True)

    def toString(self) -> str:
        return self._raw

    def __str__(self) -> str:
        return self._raw

    def getHost(self) -> str:
        return (self._parsed.hostname or "") if self._parsed else ""

    def getPath(self) -> str:
        return (self._parsed.path or "") if self._parsed else ""

    def getQueryString(self) -> str:
        return (self._parsed.query or "") if self._parsed else ""

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

    def __pm_debug__(self) -> dict[str, Any]:
        """Debug-tree view: full URL plus parsed components."""
        return {
            "toString": self._raw,
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "path": self.path,
            "query": self.query.to_object(),
        }


class _PmRequestBody:
    """Discriminated union for ``pm.request.body`` (mirrors Postman ``RequestBody``)."""

    def __init__(self, body: Any) -> None:
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

    def __pm_debug__(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "raw": self.raw,
            "urlencoded": self.urlencoded.to_object(),
            "formdata": self.formdata.to_object(),
            "graphql": self.graphql,
            "file": self.file,
        }


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

    def getAll(self) -> list[dict[str, str]]:
        return self.get_all()

    def __pm_debug__(self) -> dict[str, str]:
        return dict(self._cookies)

    def jar(self) -> Any:
        """Return a ``CookieJar`` shim. Reads work; mutators raise."""
        outer = self

        class _CookieJar:
            def get(self_inner, _url: str, name: str, callback: Any = None) -> Any:
                value = outer.get(name)
                if callback:
                    callback(None, value)
                return value

            def getAll(self_inner, _url: str, callback: Any = None) -> list[dict[str, str]]:
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

    ``url`` is a :class:`_PmUrl`, ``headers`` is a :class:`_HeaderList`
    (mutable when ``is_pre_request`` is True), ``body`` is a
    :class:`_PmRequestBody`. The string forms (``_url_str`` /
    ``_body_str``) are kept so the host context serialiser keeps working.
    """

    def __init__(self, data: dict[str, Any], *, is_pre_request: bool = True) -> None:
        self._url_str: str = str(data.get("url", "") or "")
        self.url = _PmUrl(self._url_str)
        self.method: str = data.get("method", "GET")
        self.headers = _HeaderList(data.get("headers", {}), mutable=is_pre_request)
        body_raw = data.get("body", "")
        self._body_str: str = body_raw if isinstance(body_raw, str) else ""
        self.body = _PmRequestBody(body_raw)

    def __pm_debug__(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url.toString(),
            "headers": self.headers.to_object(),
            "body": self.body.__pm_debug__(),
        }

    def __repr__(self) -> str:
        return f"<PmRequest {self.method} {self.url.toString()!r}>"

    def __str__(self) -> str:
        return self.__repr__()


class _PmResponse(dict):  # type: ignore[type-arg]
    """Read-only response representation for test scripts.

    Mirrors https://www.postmanlabs.com/postman-collection/Response.html
    — exposes ``code/status/headers/responseTime/responseSize/body``,
    ``text()/json()/reason()/mime()/dataURI()/size()``, ``cookies``,
    and ``originalRequest`` when the host provides it.

    Inherits from ``dict`` so Postman scripts ported to Python that gate on
    ``isinstance(response, dict)`` keep working — ``response.get("body")``,
    ``response["code"]`` and attribute access (``response.body``,
    ``response.code``) all resolve to the same fields.
    """

    def __init__(
        self,
        data: dict[str, Any],
        original_request: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.code: int = data.get("status_code", data.get("code", 0))
        self.status: str = data.get("status", "")
        self.headers = _HeaderList(data.get("headers", {}), mutable=False)
        self.response_time: float = data.get("response_time", data.get("elapsed_ms", 0))
        self.response_size: int = data.get("response_size", data.get("size_bytes", 0))
        # ``body`` is public so ``response.body`` works (matches JS
        # ``pm.response.body``); ``_body`` kept for callers that already
        # read the legacy private attribute (json()/text()/__pm_debug__).
        self.body: str = data.get("body", "")
        self._body: str = self.body
        self.cookies = _PmCookies(data)
        self.originalRequest: _PmRequest | None
        if original_request:
            self.originalRequest = _PmRequest(original_request, is_pre_request=False)
        else:
            self.originalRequest = None
        # Populate dict items so ``response["body"]`` / ``response.get(...)``
        # / ``dict(response)`` / ``json.dumps(response)`` all behave.
        dict.__setitem__(self, "code", self.code)
        dict.__setitem__(self, "status", self.status)
        dict.__setitem__(self, "body", self.body)
        dict.__setitem__(self, "headers", self.headers)
        dict.__setitem__(self, "responseTime", self.response_time)
        dict.__setitem__(self, "response_time", self.response_time)
        dict.__setitem__(self, "responseSize", self.response_size)
        dict.__setitem__(self, "response_size", self.response_size)
        dict.__setitem__(self, "cookies", self.cookies)
        dict.__setitem__(self, "originalRequest", self.originalRequest)

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

    def reason(self) -> str:
        return _HTTP_REASON.get(int(self.code or 0), "")

    def mime(self) -> dict[str, str]:
        ct = self.headers.get("Content-Type") or ""
        sep = ct.find(";")
        primary = ct[:sep].strip() if sep >= 0 else ct.strip()
        m = re.search(r"charset=([^;]+)", ct, flags=re.IGNORECASE)
        charset = m.group(1).strip() if m else ""
        return {"type": primary, "charset": charset}

    def dataURI(self) -> str:
        import base64

        ct = self.headers.get("Content-Type") or "application/octet-stream"
        body_bytes = (self._body or "").encode("utf-8")
        return "data:" + ct + ";base64," + base64.b64encode(body_bytes).decode("ascii")

    def size(self) -> int:
        return self.response_size or (len(self._body) if self._body else 0)

    @property
    def responseTime(self) -> float:
        return self.response_time

    @property
    def responseSize(self) -> int:
        return self.response_size

    @property
    def to(self) -> _Expectation:
        """Postman-style ``pm.response.to.have.status(…)`` (fresh chain per access)."""
        return _Expectation(self)

    def __pm_debug__(self) -> dict[str, Any]:
        body = self._body or ""
        body_preview = (
            body
            if len(body) <= _PM_DEBUG_BODY_PREVIEW_MAX
            else body[:_PM_DEBUG_BODY_PREVIEW_MAX] + "…"
        )
        out: dict[str, Any] = {
            "code": self.code,
            "status": self.status,
            "responseTime": self.response_time,
            "responseSize": self.response_size,
            "body": body_preview,
            "headers": self.headers.to_object(),
            "reason": self.reason(),
        }
        if self.originalRequest is not None:
            out["originalRequest"] = self.originalRequest.__pm_debug__()
        return out

    def __repr__(self) -> str:
        body = self._body or ""
        snippet = body if len(body) <= 60 else body[:60] + "…"
        return f"<PmResponse code={self.code} body={snippet!r}>"

    def __str__(self) -> str:
        return self.__repr__()


class _PmInfo:
    """Execution metadata."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.request_name = str(data.get("requestName", data.get("request_name", "")))
        self.request_id = str(data.get("requestId", data.get("request_id", "")))
        self.iteration = int(data.get("iteration", 0))
        self.iteration_count = int(data.get("iterationCount", data.get("iteration_count", 0)))


class _PmExecutionLocation:
    """``pm.execution.location`` — folder/collection path for the current request."""

    def __init__(self, data: Any) -> None:
        if isinstance(data, dict):
            self.current = str(data.get("current", "") or "")
        elif isinstance(data, str):
            self.current = data
        else:
            self.current = ""

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
    def setNextRequest(self, name: str | None = None) -> None:
        self.set_next_request(name)

    def skipRequest(self) -> None:
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
