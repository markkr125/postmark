"""Regression tests for Postman parity on Deno (JS) and Pyodide (Python).

RestrictedPython-only tests in :mod:`test_pm_python_parity` miss name-mangling
and ESM ``globalThis`` injection bugs in the default runtimes.
"""

from __future__ import annotations

from typing import Any

import pytest

from services.scripting import ScriptInput, ScriptOutput
from services.scripting.js_runtime import JSRuntime
from services.scripting.pyodide_runtime import PyodideRuntime, pyodide_vendor_ready
from services.scripting.runtime_settings import RuntimeSettings


def _ctx(
    *,
    response: dict[str, Any] | None = None,
    auth: dict[str, Any] | None = None,
    environment_name: str = "",
) -> ScriptInput:
    request: dict[str, Any] = {
        "url": "https://example.com",
        "method": "GET",
        "headers": {},
        "body": "",
    }
    if auth is not None:
        request["auth"] = auth
    out: ScriptInput = {
        "request": request,
        "response": response,
        "variables": {},
        "environment_vars": {},
        "collection_vars": {},
        "info": {"eventName": "test", "requestName": "t"},
    }
    if environment_name:
        out["environment_name"] = environment_name
    return out


def _passed(result: ScriptOutput) -> bool:
    return all(r.get("passed") for r in result.get("test_results", []))


@pytest.fixture(autouse=True)
def _require_deno() -> None:
    st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
    if not st.get("available"):
        pytest.skip("Deno not available")


# -- Deno / JS ---------------------------------------------------------


def test_js_replace_in_resolves_dynamic_guid() -> None:
    """``pm.variables.replaceIn('{{$guid}}')`` must not return the literal."""
    script = """
pm.test("dyn", function () {
  var s = pm.variables.replaceIn("{{$guid}}");
  if (s.length !== 36) throw new Error("len=" + s.length + " val=" + s);
});
"""
    result = JSRuntime.execute(script, _ctx())
    assert _passed(result), result["test_results"]


def test_js_replace_in_trims_key_whitespace() -> None:
    """``{{ $guid }}`` with spaces resolves like send-time substitute."""
    script = """
pm.test("trim", function () {
  var s = pm.variables.replaceIn("{{ $guid }}");
  if (s.length !== 36) throw new Error("len=" + s.length);
});
"""
    result = JSRuntime.execute(script, _ctx())
    assert _passed(result), result["test_results"]


def test_js_request_auth_from_context() -> None:
    """``pm.request.auth`` is wired through ``_build_js_context``."""
    script = """
pm.test("auth", function () {
  if (!pm.request.auth || pm.request.auth.type !== "bearer") {
    throw new Error("missing auth");
  }
});
"""
    auth = {"type": "bearer", "bearer": [{"key": "token", "value": "x"}]}
    result = JSRuntime.execute(script, _ctx(auth=auth))
    assert _passed(result), result["test_results"]


def test_js_json_schema_passes() -> None:
    """``.jsonSchema()`` uses the injected fragment (not NameError)."""
    script = """
pm.test("schema", function () {
  pm.expect({a: 1}).to.have.jsonSchema({type: "object", required: ["a"]});
});
"""
    result = JSRuntime.execute(script, _ctx())
    assert _passed(result), result["test_results"]


# -- Pyodide / Python --------------------------------------------------


@pytest.fixture(autouse=True)
def _require_pyodide(_require_deno: None) -> None:
    if not pyodide_vendor_ready():
        pytest.skip("Vendored Pyodide runtime missing")


def test_pyodide_replace_in_resolves_dynamic_guid() -> None:
    """Pyodide ``replace_in`` must call ``_pm_resolve_dynamic`` (no mangling)."""
    script = """
def t_fn():
    s = pm.variables.replaceIn("{{$guid}}")
    pm.expect(len(s)).to.eql(36)
pm.test("dyn", t_fn)
"""
    out = PyodideRuntime.execute(script, _ctx())
    assert out.get("error") is None
    passed = [r for r in out.get("test_results", []) if r.get("passed")]
    assert passed, out.get("test_results")


def test_pyodide_json_schema_passes() -> None:
    """Pyodide ``json_schema`` must call ``_pm_validate_schema``."""
    script = """
def t_fn():
    pm.expect({"a": 1}).to.have.jsonSchema({"type": "object", "required": ["a"]})
pm.test("schema", t_fn)
"""
    out = PyodideRuntime.execute(script, _ctx())
    assert out.get("error") is None
    passed = [r for r in out.get("test_results", []) if r.get("passed")]
    assert passed, out.get("test_results")
