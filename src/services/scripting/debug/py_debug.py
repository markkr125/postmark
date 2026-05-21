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
                    "breakpoints": protocol.breakpoints,
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
    timer.daemon = True
    timer.start()

    # Killing the sandbox on protocol.stop() unblocks the IPC loop
    # when the sandbox is paused at a breakpoint (no output to read).
    protocol.set_abort_callback(lambda: _kill_proc(proc))

    try:
        assert proc.stdin is not None
        with contextlib.suppress(BrokenPipeError, OSError):
            proc.stdin.write(payload.encode())
            proc.stdin.flush()

        result = _debug_ipc_loop(proc, protocol, script_type, source_name)
        if result is not None:
            _apply_result(result, output)
        elif protocol.is_stopped:
            output["console_logs"].append(
                {
                    "level": "info",
                    "message": "[Debug] Session stopped by user",
                    "timestamp": time.time(),
                }
            )
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
        if not protocol.is_stopped:
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
        # Close stdin explicitly (suppress) before ``proc`` is finalised so the
        # ``BufferedWriter``'s ``__del__`` does not try to flush queued bytes
        # into a closed pipe and raise "Exception ignored in: <_io.BufferedWriter>".
        if proc.stdin is not None:
            with contextlib.suppress(BrokenPipeError, OSError, ValueError):
                proc.stdin.close()
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
            env_changes = data.get("env_changes", {}) or {}
            global_changes = data.get("global_changes", {}) or {}
            call_stack = data.get("call_stack", []) or []
            if not isinstance(call_stack, list):
                call_stack = []
            selected_frame = int(data.get("selected_frame_index", 0))

            proc_io_lock = threading.Lock()

            def evaluate(expr: str, frame_index: int, _lock: threading.Lock = proc_io_lock) -> str:
                stdin = proc.stdin
                stdout = proc.stdout
                if stdin is None or stdout is None:
                    return "<error>"
                with _lock:
                    try:
                        stdin.write(
                            (
                                json.dumps({"op": "eval", "expr": expr, "frame": frame_index})
                                + "\n"
                            ).encode()
                        )
                        stdin.flush()
                        resp_line = stdout.readline()
                    except (BrokenPipeError, OSError):
                        return "<error>"
                if not resp_line:
                    return "<error>"
                try:
                    resp: Any = json.loads(resp_line)
                except json.JSONDecodeError:
                    return "<error>"
                if isinstance(resp, dict) and resp.get("__ipc__") == "evalResult":
                    val = resp.get("value")
                    return str(val) if val is not None else ""
                return "<error>"

            def frame_locals(
                frame_index: int, _lock: threading.Lock = proc_io_lock
            ) -> dict[str, Any]:
                stdin = proc.stdin
                stdout = proc.stdout
                if stdin is None or stdout is None:
                    return {}
                with _lock:
                    try:
                        stdin.write(
                            (json.dumps({"op": "getLocals", "frame": frame_index}) + "\n").encode()
                        )
                        stdin.flush()
                        resp_line = stdout.readline()
                    except (BrokenPipeError, OSError):
                        return {}
                if not resp_line:
                    return {}
                try:
                    resp = json.loads(resp_line)
                except json.JSONDecodeError:
                    return {}
                if isinstance(resp, dict) and resp.get("__ipc__") == "localsResult":
                    lv = resp.get("locals", {})
                    return lv if isinstance(lv, dict) else {}
                return {}

            protocol.set_evaluate_callback(evaluate)
            protocol.set_frame_locals_callback(frame_locals)
            try:
                should_continue = protocol.checkpoint(
                    pause_line,
                    source_name=source_name,
                    local_vars=local_vars,
                    script_type=script_type,
                    env_changes=env_changes,
                    global_changes=global_changes,
                    call_stack=call_stack,
                    selected_frame_index=selected_frame,
                )
            finally:
                protocol.set_evaluate_callback(None)
                protocol.set_frame_locals_callback(None)

            command = protocol._step_mode.value if should_continue else "stop"
            cmd: dict[str, Any] = {
                "command": command,
                "breakpoints": protocol.breakpoints,
            }

            # Sandbox may have died (timeout, abort, crash) between read and
            # write — tolerate the broken pipe and let the read loop terminate
            # naturally on the next empty ``readline``.
            try:
                proc.stdin.write(json.dumps(cmd).encode() + b"\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                return None

        elif data.get("__ipc__") == "sendRequest":
            resp = execute_sub_request(data.get("spec", {}))
            try:
                proc.stdin.write(json.dumps(resp).encode() + b"\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                return None


def _kill_proc(proc: subprocess.Popen[bytes]) -> None:
    """Kill the subprocess (called from the timer thread)."""
    with contextlib.suppress(OSError):
        proc.kill()
