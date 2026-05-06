"""Deno + V8 inspector: CDP over WebSocket for step-through script debugging."""

from __future__ import annotations

import contextlib
import json
import logging
import re
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK
from websockets.sync.client import connect

from services.scripting.context import execute_sub_request
from services.scripting.deno_runtime import (
    _apply_done_line,
    _empty_output,
    _kill_if_running,
    build_debug_bundle_text,
    deno_ipc_argv_and_env,
    user_script_first_line_0_in_debug_bundle,
)
from services.scripting.js_runtime import _MAX_TOTAL_SUBREQUESTS
from services.scripting.runtime_settings import RuntimeSettings

from . import js_debug
from .deno_scope import _CdpClient, _collect_call_frame_scopes

if TYPE_CHECKING:
    from services.scripting import ScriptInput, ScriptOutput
    from services.scripting.debug.protocol import DebugProtocol

logger = logging.getLogger(__name__)

_WS_RE = re.compile(rb"ws://[0-9.:/a-zA-Z_\-?=&+]+")
_DISCOVER_S = 6.0
_IPC_LOOP_S = 20.0
# ``_stdout_ipc`` can block on ``readline`` for up to ``_IPC_LOOP_S``; if the
# main thread ``join``s for less, ``finally`` may kill the child before the
# ``__done__`` line is read (worse under heavy CPU / full test runs).
_IPC_THREAD_JOIN_S = 25.0


def _cdp_break_editor_lines(
    g0s: set[int],
    breakpoints: set[int],
    n_user_lines: int,
) -> list[int]:
    """Editor 0-based lines to bind with ``Debugger.setBreakpointByUrl`` (deduped, sorted)."""
    if n_user_lines <= 0:
        return sorted(g0s)
    editor_bps = {b for b in breakpoints if 0 <= b < n_user_lines}
    return sorted(g0s | editor_bps)


def _e() -> ScriptOutput:
    return _empty_output()


def _err(msg: str, ms: float) -> ScriptOutput:
    o = _e()
    o["test_results"] = [
        {"name": "(debug error)", "passed": False, "error": msg, "duration_ms": ms},
    ]
    return o


def _port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with s:
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
    return p if isinstance(p, int) else 0


def _ws_stderr(proc: subprocess.Popen[bytes], deadline: float) -> str | None:
    assert proc.stderr
    while time.monotonic() < deadline and proc.poll() is None:
        line: bytes
        with contextlib.suppress(BlockingIOError, OSError, ValueError):
            line = proc.stderr.readline(8192)  # type: ignore[assignment, union-attr]
        if not line and proc.stderr:
            if proc.poll() is not None:
                return None
            time.sleep(0.02)
            continue
        m = _WS_RE.search(line)
        if m:
            return m.group(0).decode("ascii", errors="replace")
    return None


def _ws_http_list(port: int, deadline: float) -> str | None:
    u = f"http://127.0.0.1:{port}/json/list"
    while time.monotonic() < deadline:
        try:
            with urlopen(u, timeout=0.4) as r:
                data: Any = json.loads(r.read().decode("utf-8", errors="replace"))
        except (OSError, HTTPError, URLError, TypeError, json.JSONDecodeError):
            time.sleep(0.04)
            continue
        if isinstance(data, list) and data and isinstance(data[0], dict):
            u2 = data[0].get("webSocketDebuggerUrl")
            if isinstance(u2, str) and u2.startswith("ws://"):
                return u2
        time.sleep(0.04)
    return None


def _line_paused(m: dict[str, Any]) -> int:
    cfs = m.get("params", {}).get("callFrames")
    if not cfs or not isinstance(cfs, list):
        return -1
    loc = (cfs[0] or {}).get("location") or {}
    ln = loc.get("lineNumber", -1)
    return int(ln) if isinstance(ln, int) else -1


def _cfid_paused(m: dict[str, Any]) -> str:
    cfs = m.get("params", {}).get("callFrames")
    if not cfs or not isinstance(cfs, list) or not cfs[0]:
        return ""
    c = cfs[0]
    if not isinstance(c, dict):
        return ""
    cfi = c.get("callFrameId")
    return str(cfi) if cfi is not None else ""


def _stdout_ipc(
    proc: subprocess.Popen[bytes],
    done_box: list[dict[str, Any]],
    ev: threading.Event,
) -> None:
    """Read *proc* stdout until a ``__done__`` line or the loop times out.

    Do not gate on ``proc.poll() is None`` only: when the child exits, the
    last JSON line can still be buffered; the previous version could leave
    the loop before *readline* saw it.
    """
    t0 = time.monotonic()
    n = 0
    assert proc.stdout and proc.stdin
    while (time.monotonic() - t0) < _IPC_LOOP_S and not ev.is_set():
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.01)
            continue
        try:
            data: Any = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("__done__") is True:
            done_box.append(data)
            ev.set()
            return
        if data.get("__ipc__") == "sendRequest" and "spec" in data:
            n += 1
            r: dict[str, Any] = (
                {"error": "Sub-request host limit (50) exceeded."}
                if n > _MAX_TOTAL_SUBREQUESTS
                else execute_sub_request(data.get("spec", {}))
            )
            with contextlib.suppress(OSError):
                proc.stdin.write((json.dumps(r) + "\n").encode("utf-8", errors="replace"))
                proc.stdin.flush()


class _Cdp:
    """WebSocket-backed CDP client (request/response + queued ``Debugger.paused``)."""

    def __init__(self, ws: object, q: list[dict[str, Any]]) -> None:
        self._ws: Any = ws
        self._i = 0
        self.q = q

    def _n(self) -> int:
        self._i += 1
        return self._i

    def req(self, method: str, params: dict[str, Any] | None) -> Any:
        mid = self._n()
        self._ws.send(
            json.dumps(
                {
                    "id": mid,
                    "method": method,
                    "params": params or {},
                },
            ),
        )
        while True:
            try:
                raw = self._ws.recv(8.0)
            except TimeoutError:
                raise OSError("CDP recv timeout") from None
            m = json.loads(str(raw))
            if m.get("id") == mid:
                if m.get("error"):
                    raise OSError(str(m.get("error")))
                return m.get("result")
            if m.get("method") == "Debugger.paused":
                self.q.append(m)


def debug_execute(
    script: str,
    context: ScriptInput,
    protocol: DebugProtocol,
    *,
    script_type: str = "pre_request",
    source_name: str = "",
    language: str = "javascript",
) -> ScriptOutput:
    """Run *script* under the Deno inspector with CDP breakpoints and pauses."""
    t0 = time.monotonic()
    st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
    if not st["available"]:
        return _err(
            "Deno is not available for step-through. " + (st.get("error") or ""),
            (time.monotonic() - t0) * 1000,
        )
    if not (script and script.strip()):
        return _e()
    ex = js_debug._transform_let_const_regex_fallback(script)
    groups = js_debug._split_into_groups(ex)
    if not groups:
        return _e()
    try:
        u0 = user_script_first_line_0_in_debug_bundle(ex, context)
    except RuntimeError as exc:
        return _err(str(exc), (time.monotonic() - t0) * 1000)
    g0s = {a for a, _ in groups}
    n_user_lines = len(ex.splitlines())
    cdp_break_lines = _cdp_break_editor_lines(g0s, protocol.breakpoints, n_user_lines)
    deno = Path(st["path"])
    pport = _port()
    tdir = Path(tempfile.mkdtemp(prefix="postmark-dbg-"))
    ext = "ts" if language == "typescript" else "mjs"
    bundle = tdir / f"bundle.{ext}"
    wdir = bundle.parent
    with contextlib.suppress(OSError):
        (wdir / ".deno_dir").mkdir(exist_ok=True)
    furl = bundle.resolve().as_uri()
    with contextlib.suppress(OSError):
        try:
            bundle.write_text(build_debug_bundle_text(ex, context), encoding="utf-8", newline="\n")
        except RuntimeError as exc:
            return _err(str(exc), (time.monotonic() - t0) * 1000)
    out = _e()
    done: list[dict[str, Any]] = []
    done_e = threading.Event()
    try:
        argv, env = deno_ipc_argv_and_env(
            deno,
            bundle,
            script_for_network_scan=ex,
            inspect_brk=f"--inspect-brk=127.0.0.1:{pport}",
        )
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=str(wdir),
        )
    except (OSError, FileNotFoundError) as exc:
        return _err(str(exc), (time.monotonic() - t0) * 1000)

    def _killp() -> None:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            if proc.poll() is None:
                _kill_if_running(proc)

    protocol.set_abort_callback(_killp)
    t_ipc = threading.Thread(target=_stdout_ipc, args=(proc, done, done_e), daemon=True)
    t_ipc.start()
    dl = time.monotonic() + _DISCOVER_S
    ws_s = _ws_stderr(proc, dl)
    if not ws_s:
        ws_s = _ws_http_list(pport, time.monotonic() + 1.0)
    if not ws_s:
        _killp()
        protocol.set_abort_callback(None)
        with contextlib.suppress(Exception):
            protocol.finish()
        return _err("Deno debugger WebSocket URL not found.", (time.monotonic() - t0) * 1000)
    q: list[dict[str, Any]] = []
    stopped = False
    try:
        with connect(ws_s) as wsc:  # type: ignore[union-attr, arg-type, abstract-overlap]
            c = _Cdp(wsc, q)
            c.req("Runtime.enable", {})
            c.req("Debugger.enable", {})
            for gln in cdp_break_lines:
                c.req(
                    "Debugger.setBreakpointByUrl",
                    {
                        "lineNumber": u0 + gln,
                        "url": furl,
                        "columnNumber": 0,
                    },
                )
            c.req("Runtime.runIfWaitingForDebugger", {})
            while q and not stopped:
                m0 = q.pop(0)
                r = _process_one_paused(m0, c, protocol, u0, n_user_lines, source_name, script_type)
                if r is False:
                    stopped = True
            if not stopped and not done_e.is_set():
                while proc.poll() is None and not done_e.is_set() and not stopped:
                    with contextlib.suppress(
                        ConnectionClosed,
                        ConnectionClosedError,
                        ConnectionClosedOK,
                    ):
                        try:
                            raw = wsc.recv(0.35)  # type: ignore[union-attr, arg-type, attr-defined]
                        except TimeoutError:
                            if protocol.is_stopped:
                                stopped = True
                                break
                            continue
                    try:
                        jm = json.loads(str(raw))
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(jm, dict) or jm.get("method") != "Debugger.paused":
                        continue
                    r2 = _process_one_paused(
                        jm, c, protocol, u0, n_user_lines, source_name, script_type
                    )
                    if r2 is False:
                        stopped = True
                        break
    except (
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        KeyError,
        ConnectionClosed,
        ConnectionClosedError,
        ConnectionClosedOK,
    ) as cdp_err:
        logger.debug("Deno debug CDP: %s", cdp_err, exc_info=False)
    finally:
        # Let the stdout reader see the final ``__done__`` line before the
        # process is killed and the pipe is torn down.
        t_ipc.join(timeout=_IPC_THREAD_JOIN_S)
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            _killp()
        with contextlib.suppress(Exception):
            proc.wait(timeout=1.0)
        protocol.set_abort_callback(None)
        with contextlib.suppress(Exception):
            protocol.finish()
    if stopped:
        out["console_logs"].append(
            {
                "level": "info",
                "message": "[Debug] Session stopped by user",
                "timestamp": time.time(),
            }
        )
    if done and len(done) > 0 and isinstance(done[0], dict):
        _apply_done_line(done[0], out, context)
    return out


def _process_one_paused(
    m: dict[str, Any],
    c: _CdpClient,
    protocol: DebugProtocol,
    u0: int,
    n_user_lines: int,
    source_name: str,
    script_type: str,
) -> bool:
    """Run checkpoint for one ``Debugger.paused``; return ``False`` to stop, ``True`` to continue."""
    if protocol.is_stopped:
        return False
    fl = _line_paused(m)
    if fl < 0 or fl < u0:
        with contextlib.suppress(OSError, TypeError, json.JSONDecodeError, KeyError):
            c.req("Debugger.resume", {})
        return True
    el = fl - u0
    if n_user_lines <= 0 or el < 0 or el >= n_user_lines:
        with contextlib.suppress(OSError, TypeError, json.JSONDecodeError, KeyError):
            c.req("Debugger.resume", {})
        return True
    cf = _cfid_paused(m)
    raw = "{}"
    if cf:
        with contextlib.suppress(OSError, TypeError, json.JSONDecodeError, KeyError):
            rve = c.req(
                "Debugger.evaluateOnCallFrame",
                {
                    "callFrameId": cf,
                    "expression": js_debug._READ_JS_DEBUG_VARS,
                    "returnByValue": True,
                },
            )
            if isinstance(rve, dict):
                raw = js_debug.cdp_evaluation_result_string(rve)
    rv = js_debug.read_locals_from_iife_json_string(raw)
    pm: Any = rv.get("pm", {})
    gl: Any = rv.get("globals", {})
    if not isinstance(pm, dict):
        pm = {}
    if not isinstance(gl, dict):
        gl = {}
    flat_locals, scopes_list = _collect_call_frame_scopes(m, c)
    loc = {
        "pm": pm,
        "globals": gl,
        "locals": flat_locals,
        "scopes": scopes_list,
    }
    evc: Any = rv.get("env_changes", {})
    gch: Any = rv.get("global_changes", {})
    if not isinstance(evc, dict):
        evc = {}
    if not isinstance(gch, dict):
        gch = {}
    if not evc:
        fe = js_debug.cdp_runtime_evaluate_json_object(
            c, js_debug.CDP_RUNTIME_VARIABLE_CHANGES_JSON
        )
        if fe:
            evc = fe
    if not gch:
        fg = js_debug.cdp_runtime_evaluate_json_object(c, js_debug.CDP_RUNTIME_GLOBAL_CHANGES_JSON)
        if fg:
            gch = fg
    if not protocol.checkpoint(
        el,
        source_name=source_name,
        local_vars=loc,
        script_type=script_type,
        env_changes=evc,
        global_changes=gch,
    ):
        return False
    with contextlib.suppress(OSError, TypeError, json.JSONDecodeError, KeyError):
        c.req("Debugger.resume", {})
    return True
