"""Python script runtime using subprocess isolation.

Spawns a child process running ``_py_sandbox.py`` with
``RestrictedPython`` compilation and heavily restricted builtins.

Security layers:
- Subprocess isolation — crash/exploit cannot affect the main app.
- Empty environment — no leaked secrets from parent process.
- Hard timeout — killed after *_SUBPROCESS_TIMEOUT* seconds.
- One process per execution — no state reuse.
- IPC bridge for ``pm.sendRequest()`` — sandbox has no network.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.scripting import ScriptInput, ScriptOutput

logger = logging.getLogger(__name__)

# Hard timeout for the subprocess (seconds).
_SUBPROCESS_TIMEOUT = 10

# Module path for the sandbox worker.
_SANDBOX_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_py_sandbox.py")


def _empty_output() -> ScriptOutput:
    """Return an empty ``ScriptOutput`` dict."""
    return {
        "test_results": [],
        "console_logs": [],
        "variable_changes": {},
        "request_mutations": None,
    }


class PyRuntime:
    """Execute Python scripts in an isolated subprocess.

    Each call to :meth:`execute` spawns a fresh process — no state
    leaks between executions.
    """

    @staticmethod
    def execute(script: str, context: ScriptInput) -> ScriptOutput:
        """Run *script* with *context* and return accumulated results.

        Returns a valid :class:`ScriptOutput` even on error — failures
        are recorded as a single failed ``TestResult``.
        """
        return _run_in_subprocess(script, context)


def _run_in_subprocess(script: str, context: ScriptInput) -> ScriptOutput:
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

    # Hard-kill timer prevents runaway scripts.
    timer = threading.Timer(_SUBPROCESS_TIMEOUT, _kill_proc, args=(proc,))
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

        proc.wait(timeout=2)
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
