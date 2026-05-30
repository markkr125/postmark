"""Python script runtime — Pyodide (Deno + WASM) or RestrictedPython subprocess.

When Deno is available and :file:`data/scripts/vendor_pyodide/pyodide.asm.wasm`
exists, :meth:`PyRuntime.execute` runs scripts in **Pyodide** via
:mod:`services.scripting.pyodide_runtime` (``micropip`` + ``pm.require``).

Otherwise scripts run in a CPython child process with ``_py_sandbox.py`` and
``RestrictedPython`` (:meth:`PyRuntime.execute_restricted`).

Security layers (RestrictedPython path):
- Subprocess isolation — crash/exploit cannot affect the main app.
- Empty environment — no leaked secrets from parent process.
- Hard timeout — killed after *_SUBPROCESS_TIMEOUT* seconds.
- One process per execution — no state reuse.
- IPC bridge for ``pm.send_request()`` — sandbox has no network.
"""

from __future__ import annotations

import contextlib
import inspect
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from services.scripting import ScriptInput, ScriptOutput

logger = logging.getLogger(__name__)

# Hard timeout for the subprocess (seconds).
_SUBPROCESS_TIMEOUT = 10

# Module path for the sandbox worker.
_SANDBOX_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_py_sandbox.py")

_PYODIDE_VENDOR_MARKER = (
    Path(__file__).resolve().parents[3] / "data" / "scripts" / "vendor_pyodide" / "pyodide.asm.wasm"
)

# Extra lines prepended to user ``<script>`` before ``exec`` (0 today). Bootstraps
# subtract this from captured frame lines so inline console annotations align.
PYTHON_USER_SCRIPT_PRELUDE_LINE_COUNT = 0

_PM_REQUIRE_PY_RE = re.compile(
    r"""pm\s*\.\s*require\s*\(\s*['"]"""
    r"""(?P<name>[a-z0-9][a-z0-9._-]*)"""
    r"""(?:==(?P<ver>[^'"]+))?['"]\s*\)""",
    re.IGNORECASE,
)
_PY_EXACT_VERSION_RE = re.compile(r"^\d+(\.\d+){0,3}([abrc]\d+|\.post\d+|\.dev\d+)?$")


class PmPyRequireSpec(NamedTuple):
    """A literal ``pm.require("pkg"|"pkg==1.2.3")`` call found in Python source."""

    name: str
    version: str  # "" for latest

    @property
    def pip_spec(self) -> str:
        """Specifier passed to ``micropip.install``."""
        return f"{self.name}=={self.version}" if self.version else self.name


def python_console_frame_to_editor_line() -> int | None:
    """Map the innermost ``<script>`` frame to a 0-based editor line.

    Walks back from :func:`_console_emit` / print shims. Uses
    ``PYTHON_USER_SCRIPT_PRELUDE_LINE_COUNT`` and optional global
    ``__pm_user_script_line0`` (set by Pyodide host) for bundle offsets.
    """
    frame = inspect.currentframe()
    if frame is None:
        return None
    offset = PYTHON_USER_SCRIPT_PRELUDE_LINE_COUNT
    g = frame.f_globals
    if "__pm_user_script_line0" in g:
        with contextlib.suppress(TypeError, ValueError):
            offset += int(g["__pm_user_script_line0"])
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


def detect_pm_require_py_specs(source: str) -> list[PmPyRequireSpec]:
    """Collect unique ``pm.require`` string literals from *source*."""
    seen: dict[tuple[str, str], PmPyRequireSpec] = {}
    for m in _PM_REQUIRE_PY_RE.finditer(source):
        name = m.group("name").lower()
        ver = m.group("ver") or ""
        if ver and not _PY_EXACT_VERSION_RE.match(ver):
            raise ValueError(
                f"pm.require: version must be exact (got {ver!r}). "
                "Ranges and tags are not supported."
            )
        seen[(name, ver)] = PmPyRequireSpec(name, ver)
    return list(seen.values())


def _use_pyodide() -> bool:
    """Return True when the Pyodide + Deno path should run :meth:`PyRuntime.execute`."""
    from services.scripting.runtime_settings import RuntimeSettings

    if not _PYODIDE_VENDOR_MARKER.is_file():
        return False
    st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
    return bool(st.get("available"))


def _empty_output() -> ScriptOutput:
    """Return an empty ``ScriptOutput`` dict."""
    return {
        "test_results": [],
        "console_logs": [],
        "variable_changes": {},
        "request_mutations": None,
    }


class PyRuntime:
    """Execute Python scripts in Pyodide (preferred) or a RestrictedPython subprocess."""

    @staticmethod
    def execute(script: str, context: ScriptInput) -> ScriptOutput:
        """Run *script* with *context* and return accumulated results.

        Uses Pyodide under Deno when available; otherwise
        :meth:`execute_restricted`.
        """
        start = time.monotonic()
        if _use_pyodide():
            from services.scripting.pyodide_runtime import PyodideRuntime

            raw = PyodideRuntime.execute(script, context)
            elapsed_ms = (time.monotonic() - start) * 1000
            if raw.get("error"):
                o = _empty_output()
                o["test_results"] = [
                    {
                        "name": "(runtime error)",
                        "passed": False,
                        "error": str(raw["error"]),
                        "duration_ms": elapsed_ms,
                    }
                ]
                return o
            o = _empty_output()
            _apply_result(raw, o)
            return o
        return PyRuntime.execute_restricted(script, context)

    @staticmethod
    def execute_restricted(script: str, context: ScriptInput) -> ScriptOutput:
        """Run *script* in the RestrictedPython subprocess (CI security tests)."""
        return _run_restricted_subprocess(script, context)


def _run_restricted_subprocess(script: str, context: ScriptInput) -> ScriptOutput:
    r"""Spawn sandbox process and run the IPC loop.

    Communication protocol (line-based JSON):
    1. Parent writes the payload as a single JSON line to stdin.
    2. Sandbox reads the line, compiles, and executes the script.
    3. During execution, ``pm.send_request()`` writes IPC lines
       (``{"__ipc__": "sendRequest", "spec": {...}}\n``) to stdout;
       parent fulfills each and writes the response to stdin.
    4. When done, sandbox writes the final output with
       ``{"__done__": true, ...}\n``.
    """
    start = time.monotonic()
    output = _empty_output()

    payload = json.dumps({"script": script, "context": context}) + "\n"

    # Build a minimal environment — only PATH for finding Python.
    env: dict[str, str] = {"PATH": os.environ.get("PATH", "/usr/bin")}
    src_root = str(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    env["PYTHONPATH"] = src_root
    from services.scripting.dynamic_variables import dynvar_json_for_subprocess

    env["PM_DYNVAR_JSON"] = dynvar_json_for_subprocess()

    try:
        proc = subprocess.Popen(
            [sys.executable, _SANDBOX_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=src_root,
        )
    except OSError as exc:
        output["test_results"].append(
            {
                "name": "(runtime error)",
                "passed": False,
                "error": f"Failed to start sandbox process: {exc}",
                "duration_ms": 0.0,
            }
        )
        return output

    # Hard-kill timer prevents runaway scripts. Daemon so it does not
    # block interpreter shutdown if the app closes mid-run.
    timer = threading.Timer(_SUBPROCESS_TIMEOUT, _kill_proc, args=(proc,))
    timer.daemon = True
    timer.start()

    try:
        assert proc.stdin is not None
        proc.stdin.write(payload.encode())
        proc.stdin.flush()

        result = _ipc_loop(proc)
        if result is not None:
            _apply_result(result, output)
        else:
            output["test_results"].append(
                {
                    "name": "(runtime error)",
                    "passed": False,
                    "error": "Sandbox produced no output",
                    "duration_ms": (time.monotonic() - start) * 1000,
                }
            )
    except Exception as exc:
        output["test_results"].append(
            {
                "name": "(runtime error)",
                "passed": False,
                "error": f"Sandbox IPC error: {exc}",
                "duration_ms": (time.monotonic() - start) * 1000,
            }
        )
    finally:
        timer.cancel()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None and not stream.closed:
                with contextlib.suppress(OSError):
                    stream.close()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)
        if proc.poll() is None:
            proc.kill()

    return output


def _ipc_loop(proc: subprocess.Popen[bytes]) -> dict[str, Any] | None:
    """Read lines from the sandbox, fulfilling IPC requests."""
    from services.scripting.context import execute_sub_request

    assert proc.stdout is not None
    assert proc.stdin is not None

    while True:
        line = proc.stdout.readline()
        if not line:
            return None

        try:
            data: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            continue

        if data.get("__done__"):
            return data

        if data.get("__ipc__") == "sendRequest":
            resp = execute_sub_request(data.get("spec", {}))
            proc.stdin.write(json.dumps(resp).encode() + b"\n")
            proc.stdin.flush()


def _kill_proc(proc: subprocess.Popen[bytes]) -> None:
    """Kill the subprocess (called from the timer thread)."""
    with contextlib.suppress(OSError):
        proc.kill()


def _apply_result(data: dict[str, Any], output: ScriptOutput) -> None:
    """Copy sandbox result fields into *output*."""
    if "test_results" in data:
        output["test_results"] = data["test_results"]
    if "console_logs" in data:
        output["console_logs"] = data["console_logs"]
    if "variable_changes" in data:
        output["variable_changes"] = data["variable_changes"]
    if "global_variable_changes" in data:
        output["global_variable_changes"] = data["global_variable_changes"]
    if "request_mutations" in data:
        output["request_mutations"] = data["request_mutations"]
    if "next_request" in data:
        output["next_request"] = data["next_request"]
    if "skip_request" in data:
        output["skip_request"] = data["skip_request"]
