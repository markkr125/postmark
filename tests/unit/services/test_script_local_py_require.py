"""Tests for Python ``pm.require("local:…")`` via RestrictedPython sandbox."""

from __future__ import annotations

import io
import json
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from database.models.local_scripts.local_script_repository import create_folder, create_script
from services.scripting import ScriptInput, ScriptOutput
from services.scripting._py_sandbox import main as sandbox_main
from services.scripting.debug import py_debug
from services.scripting.debug.protocol import DebugProtocol
from services.scripting.py_runtime import PyRuntime, local_module_sources
from services.scripting.pyodide_runtime import PyodideRuntime
from ui.request.request_editor.scripts.script_run_worker import build_inline_context

pytestmark = pytest.mark.xdist_group("restricted_python_sandbox")


def _make_context(response: dict | None = None) -> ScriptInput:
    """Return a minimal ``ScriptInput``."""
    return {
        "request": {"url": "https://example.com", "method": "GET", "headers": {}, "body": ""},
        "response": response,
        "variables": {},
        "environment_vars": {},
        "collection_vars": {},
        "info": {},
    }


def _failed(result: ScriptOutput) -> list[dict[str, Any]]:
    """Return failed test rows from a ``ScriptOutput``."""
    return [dict(r) for r in result.get("test_results", []) if not r.get("passed")]


class TestLocalModuleSources:
    """Host-side ``local_module_sources`` helper."""

    def test_resolves_py_closure(self) -> None:
        root = create_folder("lib")
        create_script(
            root.id,
            "helpers",
            language="python",
            content="def add(a, b):\n    return a + b\n",
        )
        sources = local_module_sources('m = pm.require("local:lib/helpers.py")\n')
        assert "lib/helpers.py" in sources
        assert "def add" in sources["lib/helpers.py"]

    def test_empty_when_no_local_require(self) -> None:
        """Scripts without ``local:`` literals skip the DB index scan."""
        assert local_module_sources('pm.variables.set("v", "1")\n') == {}


class TestSandboxLocalModulesPayloadGuard:
    """Defensive guards in ``_py_sandbox.main`` for malformed payloads."""

    def test_non_dict_local_modules_rejected(self) -> None:
        """A non-object ``local_modules`` value yields a clean runtime error."""
        payload = (
            json.dumps(
                {
                    "script": "x = 1\n",
                    "context": dict(_make_context()),
                    "local_modules": ["not", "a", "dict"],
                }
            )
            + "\n"
        )
        out = io.StringIO()
        with patch.object(sys, "stdin", io.StringIO(payload)), patch.object(sys, "stdout", out):
            sandbox_main()
        lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
        assert lines
        data = json.loads(lines[-1])
        assert data.get("__done__") is True
        failed = [r for r in data.get("test_results", []) if not r.get("passed")]
        assert len(failed) == 1
        assert "local_modules" in (failed[0].get("error") or "").lower()


class TestPyLocalRequireRestricted:
    """End-to-end RestrictedPython ``pm.require("local:…")``."""

    def test_require_and_call(self) -> None:
        root = create_folder("lib")
        create_script(
            root.id,
            "helpers",
            language="python",
            content="def add(a, b):\n    return a + b\n",
        )
        script = 'h = pm.require("local:lib/helpers.py")\npm.variables.set("v", str(h.add(2, 3)))\n'
        result = PyRuntime.execute_restricted(script, _make_context())
        assert _failed(result) == []
        assert result["variable_changes"]["v"] == "5"

    def test_require_cached_same_object(self) -> None:
        root = create_folder("lib")
        create_script(
            root.id,
            "helpers",
            language="python",
            content="COUNTER = 0\n\ndef bump():\n    global COUNTER\n    COUNTER = COUNTER + 1\n    return COUNTER\n",
        )
        script = (
            'a = pm.require("local:lib/helpers.py")\n'
            'b = pm.require("local:lib/helpers.py")\n'
            "a.bump()\n"
            'pm.variables.set("same", str(a is b))\n'
            'pm.variables.set("count", str(b.COUNTER))\n'
        )
        result = PyRuntime.execute_restricted(script, _make_context())
        assert _failed(result) == []
        assert result["variable_changes"]["same"] == "True"
        assert result["variable_changes"]["count"] == "1"

    def test_nested_require_chain(self) -> None:
        root = create_folder("lib")
        create_script(
            root.id,
            "helpers",
            language="python",
            content="def add(a, b):\n    return a + b\n",
        )
        create_script(
            root.id,
            "mid",
            language="python",
            content=(
                'h = pm.require("local:lib/helpers.py")\ndef double(x):\n    return h.add(x, x)\n'
            ),
        )
        script = 'm = pm.require("local:lib/mid.py")\npm.variables.set("v", str(m.double(3)))\n'
        result = PyRuntime.execute_restricted(script, _make_context())
        assert _failed(result) == []
        assert result["variable_changes"]["v"] == "6"

    def test_pm_usable_inside_module(self) -> None:
        root = create_folder("lib")
        create_script(
            root.id,
            "side",
            language="python",
            content=('pm.variables.set("from_mod", "1")\ndef ping():\n    return "pong"\n'),
        )
        script = 's = pm.require("local:lib/side.py")\npm.variables.set("ping", s.ping())\n'
        result = PyRuntime.execute_restricted(script, _make_context())
        assert _failed(result) == []
        assert result["variable_changes"]["from_mod"] == "1"
        assert result["variable_changes"]["ping"] == "pong"

    def test_missing_path_error(self) -> None:
        script = 'pm.require("local:lib/missing.py")\n'
        result = PyRuntime.execute_restricted(script, _make_context())
        failed = _failed(result)
        assert len(failed) == 1
        assert "no local script" in (failed[0].get("error") or "").lower()

    def test_cycle_error(self) -> None:
        root = create_folder("cyc")
        create_script(
            root.id,
            "a",
            language="python",
            content='pm.require("local:cyc/b.py")\n',
        )
        create_script(
            root.id,
            "b",
            language="python",
            content='pm.require("local:cyc/a.py")\n',
        )
        script = 'pm.require("local:cyc/a.py")\n'
        result = PyRuntime.execute_restricted(script, _make_context())
        failed = _failed(result)
        assert failed
        assert "cycle" in (failed[0].get("error") or "").lower()

    def test_js_target_rejected(self) -> None:
        root = create_folder("lib")
        create_script(
            root.id,
            "jsmod",
            language="javascript",
            content="export default 1;\n",
        )
        script = 'pm.require("local:lib/jsmod.js")\n'
        result = PyRuntime.execute_restricted(script, _make_context())
        failed = _failed(result)
        assert failed
        err = (failed[0].get("error") or "").lower()
        assert "cannot import" in err or "no local script" in err

    def test_sanitized_module_names_do_not_collide(self) -> None:
        """Paths that share a sanitized stem still load as distinct modules."""
        from services.scripting._py_sandbox import _sanitize_local_mod_name

        assert _sanitize_local_mod_name("lib/a-b.py") != _sanitize_local_mod_name("lib/a_b.py")


class TestPyodideLocalModulesPayload:
    """Pyodide host payload includes ``local_modules`` and skips ``local:`` micropip."""

    def test_payload_includes_local_modules(self) -> None:
        root = create_folder("lib")
        create_script(
            root.id,
            "helpers",
            language="python",
            content="X = 1\n",
        )
        captured: dict = {}

        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()
        mock_proc.poll = lambda: 0
        mock_proc.wait = MagicMock()

        def _capture_write(data: bytes) -> int:
            import json

            captured.update(json.loads(data.decode().strip()))
            return len(data)

        mock_proc.stdin.write.side_effect = _capture_write

        with (
            patch(
                "services.scripting.pyodide_runtime.subprocess.Popen",
                return_value=mock_proc,
            ),
            patch(
                "services.scripting.pyodide_runtime._ipc_loop",
                return_value={"__done__": True, "variable_changes": {}, "test_results": []},
            ),
            patch(
                "services.scripting.pyodide_runtime.pyodide_vendor_ready",
                return_value=True,
            ),
            patch(
                "services.scripting.pyodide_runtime.RuntimeSettings.validate_deno",
                return_value={"available": True, "path": "/usr/bin/deno"},
            ),
            patch(
                "services.scripting.pyodide_runtime.RuntimeSettings.deno_path",
                return_value="/usr/bin/deno",
            ),
            patch(
                "services.scripting.pyodide_runtime.threading.Timer",
                return_value=MagicMock(),
            ),
        ):
            PyodideRuntime.execute(
                'm = pm.require("local:lib/helpers.py")\n',
                _make_context(),
            )

        assert "lib/helpers.py" in captured.get("local_modules", {})
        assert captured.get("pm_require") == []


class TestPyDebugLocalModulesPayload:
    """Debug payload includes ``local_modules``."""

    def test_debug_payload_includes_local_modules(self) -> None:
        root = create_folder("lib")
        create_script(
            root.id,
            "helpers",
            language="python",
            content="X = 1\n",
        )
        ctx = build_inline_context(script_type="pre_request")
        protocol = DebugProtocol()
        protocol.start()

        captured: dict = {}
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()
        mock_proc.poll = lambda: 0
        mock_proc.wait = MagicMock()

        def _capture_write(data: bytes) -> int:
            import json

            captured.update(json.loads(data.decode().strip()))
            return len(data)

        mock_proc.stdin.write.side_effect = _capture_write

        with (
            patch.object(py_debug, "_debug_ipc_loop", return_value=None),
            patch("services.scripting.debug.py_debug.subprocess.Popen", return_value=mock_proc),
            patch("services.scripting.debug.py_debug.threading.Timer", return_value=MagicMock()),
        ):
            protocol.stop()
            py_debug.debug_execute(
                'm = pm.require("local:lib/helpers.py")\n',
                ctx,
                protocol,
                script_type="pre_request",
            )

        assert "lib/helpers.py" in captured.get("local_modules", {})
