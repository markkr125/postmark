"""Smoke tests for the Pyodide-backed Python runtime (Deno subprocess)."""

from __future__ import annotations

import os

import pytest

from services.scripting import ScriptInput
from services.scripting.pyodide_runtime import PyodideRuntime, pyodide_vendor_ready
from services.scripting.runtime_settings import RuntimeSettings

_MIN_CTX: ScriptInput = {
    "request": {
        "url": "https://example.com",
        "method": "GET",
        "headers": {},
        "body": "",
    },
    "response": None,
    "variables": {},
    "environment_vars": {},
    "collection_vars": {},
    "info": {},
}


@pytest.fixture(autouse=True)
def _require_deno_and_vendor() -> None:
    """Skip when Deno or vendored Pyodide is unavailable."""
    if not pyodide_vendor_ready():
        pytest.skip("Vendored Pyodide runtime missing (data/scripts/vendor_pyodide/)")
    if not RuntimeSettings.validate_deno(RuntimeSettings.deno_path()).get("available"):
        pytest.skip("Deno not available")


def test_basic_python_runs() -> None:
    """Variables and simple code work under Pyodide."""
    out = PyodideRuntime.execute(
        'pm.variables.set("v", str(2 + 2))\n',
        _MIN_CTX,
    )
    assert out.get("error") is None
    assert out["variable_changes"]["v"] == "4"


@pytest.mark.skipif(
    not os.environ.get("POSTMARK_PYODIDE_NETWORK"),
    reason="micropip hits PyPI; set POSTMARK_PYODIDE_NETWORK=1 to enable",
)
def test_pm_require_jmespath() -> None:
    """``pm.require`` installs a small pure-Python wheel (network)."""
    script = (
        'jmespath = pm.require("jmespath")\n'
        'pm.variables.set("v", str(jmespath.search("a.b", {"a": {"b": 7}})))\n'
    )
    out = PyodideRuntime.execute(
        script,
        _MIN_CTX,
    )
    assert out.get("error") is None
    assert out["variable_changes"]["v"] == "7"


def test_pm_require_invalid_version_rejected() -> None:
    """``detect_pm_require_py_specs`` rejects range versions."""
    from services.scripting.py_runtime import detect_pm_require_py_specs

    with pytest.raises(ValueError, match="exact"):
        detect_pm_require_py_specs('pm.require("jmespath==^1.0")')
