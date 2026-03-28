"""Python debug execution — ``sys.settrace`` via subprocess IPC.

Extends the standard Python sandbox IPC protocol with ``debugPause``
messages.  When the sandbox hits a breakpoint or step, it writes::

    {"__ipc__": "debugPause", "line": N, "locals": {...}}

and waits for a resume command on stdin::

    {"command": "continue"|"step_over"|"step_into"|"step_out"|"stop"}
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
    from services.scripting.debug.protocol import DebugProtocol

logger = logging.getLogger(__name__)

_SUBPROCESS_TIMEOUT = 30  # longer timeout for debug mode
_SANDBOX_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir,
    "_py_sandbox.py",
)


def debug_execute(
    script: str,
    context: ScriptInput,
    protocol: DebugProtocol,
    *,
    script_type: str = "pre_request",
    source_name: str = "",
) -> ScriptOutput:
    """Run *script* in debug mode via subprocess with ``sys.settrace``.

    The payload includes a ``debug`` field with breakpoint line numbers.
    The sandbox sets up a trace function that pauses at breakpoints and
    communicates via the IPC protocol.
    """
    from services.scripting.py_runtime import _apply_result, _empty_output

    output = _empty_output()
    start = time.monotonic()

    payload = (
        json.dumps(
            {
                "script": script,
                "context": context,
                "debug": {
                    "breakpoints": sorted(protocol.breakpoints),
                },
            }
        )
        + "\n"
    )

    src_root = str(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    env: dict[str, str] = {"PATH": os.environ.get("PATH", "/usr/bin")}
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
                "name": "(debug error)",
                "passed": False,
                "error": f"Failed to start sandbox: {exc}",
                "duration_ms": 0.0,
            }
        )
        return output

    timer = threading.Timer(_SUBPROCESS_TIMEOUT, _kill_proc, args=(proc,))
    timer.start()

    try:
        assert proc.stdin is not None
        proc.stdin.write(payload.encode())
        proc.stdin.flush()

        result = _debug_ipc_loop(proc, protocol, script_type, source_name)
        if result is not None:
            _apply_result(result, output)
        else:
            output["test_results"].append(
                {
                    "name": "(debug error)",
                    "passed": False,
                    "error": "Sandbox produced no output",
                    "duration_ms": (time.monotonic() - start) * 1000,
                }
            )
    except Exception as exc:
        output["test_results"].append(
            {
                "name": "(debug error)",
                "passed": False,
                "error": f"Debug IPC error: {exc}",
                "duration_ms": (time.monotonic() - start) * 1000,
            }
        )
    finally:
        timer.cancel()
        protocol.finish()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)
        if proc.poll() is None:
            proc.kill()

    return output


def _debug_ipc_loop(
    proc: subprocess.Popen[bytes],
    protocol: DebugProtocol,
    script_type: str,
    source_name: str,
) -> dict[str, Any] | None:
    """Read IPC lines, handling debugPause and sendRequest messages."""
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

        if data.get("__ipc__") == "debugPause":
            pause_line = int(data.get("line", 0))
            local_vars = data.get("locals", {})

            should_continue = protocol.checkpoint(
                pause_line,
                source_name=source_name,
                local_vars=local_vars,
                script_type=script_type,
            )

            cmd = {"command": protocol._step_mode.value} if should_continue else {"command": "stop"}

            proc.stdin.write(json.dumps(cmd).encode() + b"\n")
            proc.stdin.flush()

        elif data.get("__ipc__") == "sendRequest":
            resp = execute_sub_request(data.get("spec", {}))
            proc.stdin.write(json.dumps(resp).encode() + b"\n")
            proc.stdin.flush()


def _kill_proc(proc: subprocess.Popen[bytes]) -> None:
    """Kill the subprocess (called from the timer thread)."""
    with contextlib.suppress(OSError):
        proc.kill()
