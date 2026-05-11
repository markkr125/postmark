"""Ensure ``pm_api_schema.PM_SCHEMA`` / ``POSTMAN_SCHEMA`` paths exist at JS runtime.

Each dotted path is probed inside ``pm.test`` so failures surface as test
results.  Requires Deno (same gate as ``TestJSRuntime``).
"""

from __future__ import annotations

from collections.abc import Generator, Mapping
from typing import Any

import pytest

from services.scripting import ScriptInput
from services.scripting.js_runtime import JSRuntime
from services.scripting.pm_api_schema import PM_SCHEMA, POSTMAN_SCHEMA


def _walk(node: Mapping[str, Any], parts: list[str]) -> Generator[tuple[str, ...], None, None]:
    """Yield terminal paths (each segment is a schema key, no ``pm`` prefix)."""
    children = node.get("children") or {}
    if not children:
        if parts:
            yield tuple(parts)
        return
    for name, child in sorted(children.items()):
        newp = [*parts, name]
        sub = child.get("children") or {}
        kind = child.get("kind", "namespace")
        if kind == "namespace" and not sub:
            yield tuple(newp)
        elif sub:
            yield from _walk(child, newp)
        else:
            yield tuple(newp)


def _all_drift_paths() -> list[tuple[str, ...]]:
    out: list[tuple[str, ...]] = []
    for path in _walk(PM_SCHEMA, []):
        out.append(("pm", *path))
    for path in _walk(POSTMAN_SCHEMA, []):
        out.append(("postman", *path))
    return out


def _make_minimal_context() -> ScriptInput:
    """Minimal ``ScriptInput`` for ``_build_js_context``."""
    return {
        "request": {"url": "https://a.test/x?q=1", "method": "GET", "headers": {}, "body": ""},
        "response": {
            "status_code": 200,
            "status": "OK",
            "headers": [{"key": "Content-Type", "value": "application/json; charset=utf-8"}],
            "body": "{}",
            "responseTime": 1.0,
            "responseSize": 2,
        },
        "variables": {},
        "environment_vars": {"E": "1"},
        "collection_vars": {},
        "global_vars": {},
        "info": {"requestName": "t", "folderName": "/Demo"},
        "iteration_data": {"row": "a"},
    }


@pytest.fixture(autouse=True)
def _require_deno() -> None:
    from services.scripting.runtime_settings import RuntimeSettings

    st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
    if not st.get("available"):
        pytest.skip("Deno not available")


@pytest.mark.parametrize("path", _all_drift_paths())
def test_schema_path_resolves_in_js(path: tuple[str, ...]) -> None:
    """Every schema leaf/namespace exists on ``globalThis`` / ``pm``."""
    ctx = _make_minimal_context()
    dotted = ".".join(path)
    root = path[0]
    chain = ".".join(path) if root == "postman" else "pm." + ".".join(path[1:])
    script = f"""
pm.test("_drift_{dotted.replace(".", "_")}", function () {{
  var cur = {chain};
  if (cur === undefined) throw new Error("missing {dotted}");
  var t = typeof cur;
  if (t !== "function" && t !== "object") throw new Error("bad type " + t + " for {dotted}");
}});
"""
    result = JSRuntime.execute(script, ctx)
    assert result["test_results"], f"no results for {dotted}"
    assert result["test_results"][0]["passed"], (
        f"{dotted}: {result['test_results'][0].get('error')}"
    )
