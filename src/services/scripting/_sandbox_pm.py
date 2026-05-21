"""Root ``pm`` object and variable scopes for the RestrictedPython sandbox."""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as _ET
from typing import Any

from services.scripting._sandbox_pm_assertions import _Expectation
from services.scripting._sandbox_pm_models import (
    _PmCookies,
    _PmExecution,
    _PmInfo,
    _PmIterationData,
    _PmRequest,
    _PmResponse,
)
from services.scripting._sandbox_pm_tests import _PmTestCallable
from services.scripting._sandbox_runtime import _console_emit


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


class _ResolvedVariables:
    """Postman-style ``pm.variables`` — read-through across scopes.

    Read precedence (highest first): local → iterationData → environment
    → collectionVariables → globals. Writes land in ``local``.
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

    def toObject(self) -> dict[str, Any]:
        return self.to_object()

    def to_dict(self) -> dict[str, Any]:
        return self.to_object()

    def replace_in(self, template: str) -> str:
        merged = self.to_object()

        def _repl(m: re.Match[str]) -> str:
            k = m.group(1)
            return str(merged.get(k, m.group(0)))

        return re.sub(r"\{\{(.+?)\}\}", _repl, template)

    def replaceIn(self, template: str) -> str:
        return self.replace_in(template)


class _PmVisualizer:
    """``pm.visualizer`` stub — `set` raises a documented "not supported" error."""

    def set(self, _template: Any = None, _data: Any = None, _options: Any = None) -> None:
        msg = (
            "pm.visualizer.set is not supported in postmark — "
            "see data/snippets/README.md (Out of scope) for the rationale."
        )
        raise RuntimeError(msg)


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
        self.test = _PmTestCallable(self)

    def expect(self, value: Any) -> _Expectation:
        return _Expectation(value)

    @property
    def collectionVariables(self) -> _VariableScope:
        return self.collection_variables

    @property
    def iterationData(self) -> _PmIterationData:
        return self.iteration_data

    def sendRequest(self, spec: Any, callback: Any = None) -> Any:
        return self.send_request(spec, callback)

    def require(self, spec: str) -> Any:
        """Postman-style ``pm.require``: bare names map to vendor table."""
        import importlib

        if not isinstance(spec, str):
            msg = "pm.require: specifier must be a string"
            raise RuntimeError(msg)
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
        sys.stdout.write(json.dumps({"__ipc__": "sendRequest", "spec": req_spec}) + "\n")
        sys.stdout.flush()
        resp_line = sys.stdin.readline()
        if not resp_line:
            msg = "No IPC response received"
            raise RuntimeError(msg)
        resp_dict: dict[str, Any] = json.loads(resp_line)
        wrapped = _PmResponse(resp_dict, req_spec)
        if callback:
            callback(resp_dict.get("error"), wrapped)
        return wrapped


def _serialize_request_mutations(req: _PmRequest) -> dict[str, Any]:
    """Convert wrapped ``_PmRequest`` back to JSON-friendly host shape."""
    url_val = req.url
    url_str = url_val.toString() if hasattr(url_val, "toString") else str(url_val)
    body_val = req.body
    body_str = str(body_val.raw or "") if hasattr(body_val, "raw") else str(body_val or "")
    headers_val = req.headers
    if hasattr(headers_val, "to_object"):
        headers_dict: dict[str, str] = headers_val.to_object()
    elif isinstance(headers_val, dict):
        headers_dict = dict(headers_val)
    else:
        headers_dict = {}
    return {
        "url": url_str,
        "method": req.method,
        "headers": headers_dict,
        "body": body_str,
    }


def _legacy_script_globals(pm: _Pm) -> dict[str, Any]:
    """Return Postman v1 legacy globals (``responseBody``, ``responseCode``, …)."""
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

    out["xml2Json"] = _xml2_json_helper
    return out


def _xml2_json_helper(xml_text: Any) -> Any:
    """Convert simple XML to a nested dict (Postman ``xml2Json`` shim).

    Pre-imported at module scope so the function works inside the
    RestrictedPython sandbox where ``import`` statements are forbidden.
    """
    ET = _ET  # local alias

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

    try:
        root = ET.fromstring(str(xml_text))
    except ET.ParseError:
        return None
    return {root.tag: _node_to_dict(root)}
