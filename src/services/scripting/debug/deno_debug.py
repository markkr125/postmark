"""Deno + V8 inspector: CDP over WebSocket for step-through script debugging."""

from __future__ import annotations

import base64
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
from .protocol import CallFrame

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
    breakpoints: dict[int, str | None],
    n_user_lines: int,
) -> list[tuple[int, str | None]]:
    """Editor lines + optional conditions for ``Debugger.setBreakpointByUrl``."""
    if n_user_lines <= 0:
        return sorted((ln, None) for ln in g0s)
    editor_bps = {b: breakpoints[b] for b in breakpoints if 0 <= b < n_user_lines}
    lines = sorted(g0s | set(editor_bps.keys()))
    return [(ln, editor_bps.get(ln)) for ln in lines]


# ---------------------------------------------------------------------------
# Source map (Deno transpile) — reverse mapping for ``.ts`` debug bundles.
#
# When ``language="typescript"`` the bundle lands as ``bundle.ts``. Deno
# transpiles ``.ts`` → JS internally; V8's inspector script is the transpiled
# JS, not the on-disk source. Line counts collapse (Deno strips comments and
# blank lines) so editor-line ``N`` no longer matches generated-line ``N``.
# ``Debugger.setBreakpointByUrl`` in V8 looks up by URL but uses the
# *transpiled* line space, so a raw ``u0+N`` lookup either falls past
# ``endLine`` (silently empty ``locations``) or lands on the wrong statement.
#
# Fix: read the inline source map Deno emits (data URL on the
# ``Debugger.scriptParsed`` event), VLQ-decode it, and build two maps:
#   * ``src_to_gen``: bundle (source) line → set of generated lines
#   * ``gen_to_src``: generated line → bundle (source) line
# Then translate breakpoints before ``setBreakpointByUrl`` and translate
# ``Debugger.paused`` lines back when invoking ``protocol.checkpoint``.
# ---------------------------------------------------------------------------

_VLQ_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def _vlq_decode(s: str, i: int) -> tuple[int, int]:
    """Decode a single Base64 VLQ value starting at ``s[i]``; return (value, next_i)."""
    result = 0
    shift = 0
    while True:
        v = _VLQ_B64.index(s[i])
        i += 1
        result |= (v & 31) << shift
        shift += 5
        if not (v & 32):
            break
    sign = result & 1
    result >>= 1
    return (-result if sign else result, i)


def _build_source_map(mappings: str) -> tuple[dict[int, list[int]], dict[int, int]]:
    """Decode a source-map ``mappings`` string into ``src→[gen]`` and ``gen→src`` maps."""
    src_to_gen: dict[int, list[int]] = {}
    gen_to_src: dict[int, int] = {}
    src_line = 0
    src_col = 0
    src_idx = 0
    for gen_line, segs in enumerate(mappings.split(";")):
        if not segs:
            continue
        gen_col = 0
        for seg in segs.split(","):
            if not seg:
                continue
            i = 0
            d, i = _vlq_decode(seg, i)
            gen_col += d
            if i < len(seg):
                d, i = _vlq_decode(seg, i)
                src_idx += d
                d, i = _vlq_decode(seg, i)
                src_line += d
                d, i = _vlq_decode(seg, i)
                src_col += d
                src_to_gen.setdefault(src_line, []).append(gen_line)
                gen_to_src.setdefault(gen_line, src_line)
    return src_to_gen, gen_to_src


def _decode_inline_source_map(source_map_url: str) -> dict[str, Any] | None:
    """Decode a ``data:application/json;base64,…`` source map URL into a dict."""
    if not source_map_url.startswith("data:"):
        return None
    if "base64," not in source_map_url:
        return None
    b64 = source_map_url.split("base64,", 1)[1]
    try:
        raw = base64.b64decode(b64)
        decoded: Any = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _src_to_gen_line(src_to_gen: dict[int, list[int]] | None, src_line: int) -> int:
    """Return the first generated line for *src_line*, or *src_line* itself when no map."""
    if not src_to_gen:
        return src_line
    gens = src_to_gen.get(src_line)
    return gens[0] if gens else src_line


def _gen_to_src_line(gen_to_src: dict[int, int] | None, gen_line: int) -> int:
    """Return the source line for *gen_line*, or *gen_line* itself when no map."""
    if not gen_to_src:
        return gen_line
    return gen_to_src.get(gen_line, gen_line)


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


def _paused_reason(m: dict[str, Any]) -> str:
    """Return the CDP ``Debugger.paused`` reason string, or empty."""
    reason = (m.get("params") or {}).get("reason")
    return str(reason) if reason else ""


def _cdp_pause_on_exceptions_state(enabled: bool) -> str:
    """CDP ``Debugger.setPauseOnExceptions`` state for uncaught vs none."""
    return "uncaught" if enabled else "none"


def _line_paused(m: dict[str, Any]) -> int:
    cfs = m.get("params", {}).get("callFrames")
    if not cfs or not isinstance(cfs, list):
        return -1
    loc = (cfs[0] or {}).get("location") or {}
    ln = loc.get("lineNumber", -1)
    return int(ln) if isinstance(ln, int) else -1


def _cfid_paused(m: dict[str, Any], frame_index: int = 0) -> str:
    cfs = m.get("params", {}).get("callFrames")
    if not cfs or not isinstance(cfs, list) or frame_index >= len(cfs):
        return ""
    c = cfs[frame_index]
    if not isinstance(c, dict):
        return ""
    cfi = c.get("callFrameId")
    return str(cfi) if cfi is not None else ""


def _call_stack_from_paused(
    m: dict[str, Any],
    *,
    u0: int,
    gen_to_src: dict[int, int] | None,
) -> list[CallFrame]:
    """Build :class:`CallFrame` rows from a ``Debugger.paused`` event."""
    cfs = m.get("params", {}).get("callFrames")
    if not cfs or not isinstance(cfs, list):
        return []
    out: list[CallFrame] = []
    for cf in cfs:
        if not isinstance(cf, dict):
            continue
        loc = cf.get("location") or {}
        fl_raw = loc.get("lineNumber", 0)
        fl = int(fl_raw) if isinstance(fl_raw, int) else 0
        fl = _gen_to_src_line(gen_to_src, fl) if fl >= 0 else fl
        editor_line = max(0, fl - u0) if fl >= u0 else fl
        col_raw = loc.get("columnNumber", 0)
        col = int(col_raw) if isinstance(col_raw, int) else 0
        name = cf.get("functionName")
        fn = str(name) if isinstance(name, str) and name else "(anonymous)"
        cfi = cf.get("callFrameId")
        out.append(
            CallFrame(
                id=str(cfi) if cfi is not None else "",
                name=fn,
                line=editor_line,
                column=col,
            )
        )
    return out


def _paused_with_frame(m: dict[str, Any], frame_index: int) -> dict[str, Any]:
    """Return a copy of *m* whose ``callFrames[0]`` is ``callFrames[frame_index]``."""
    cfs = m.get("params", {}).get("callFrames")
    if not cfs or not isinstance(cfs, list) or not cfs:
        return m
    if frame_index < 0 or frame_index >= len(cfs):
        return m
    sel = cfs[frame_index]
    rest = [f for i, f in enumerate(cfs) if i != frame_index]
    params = dict(m.get("params") or {})
    params["callFrames"] = [sel, *rest]
    return {**m, "params": params}


def _locals_for_paused_frame(
    m: dict[str, Any],
    c: _CdpClient,
    *,
    frame_index: int,
    io_lock: threading.Lock,
) -> dict[str, Any]:
    """Read ``pm`` / scope locals for one call frame while paused."""
    pm: dict[str, Any] = {}
    gl: dict[str, Any] = {}
    evc: dict[str, Any] = {}
    gch: dict[str, Any] = {}
    cf = _cfid_paused(m, frame_index)
    if cf:
        with io_lock, contextlib.suppress(OSError, TypeError, json.JSONDecodeError, KeyError):
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
                pm_val: Any = rv.get("pm", {})
                gl_val: Any = rv.get("globals", {})
                if isinstance(pm_val, dict):
                    pm = pm_val
                if isinstance(gl_val, dict):
                    gl = gl_val
                ev_raw: Any = rv.get("env_changes", {})
                gc_raw: Any = rv.get("global_changes", {})
                if isinstance(ev_raw, dict):
                    evc = ev_raw
                if isinstance(gc_raw, dict):
                    gch = gc_raw
    framed = _paused_with_frame(m, frame_index)
    with io_lock:
        flat_locals, scopes_list = _collect_call_frame_scopes(framed, c)
    return {
        "pm": pm,
        "globals": gl,
        "locals": flat_locals,
        "scopes": scopes_list,
        "env_changes": evc,
        "global_changes": gch,
    }


def _register_pause_adapters(
    m: dict[str, Any],
    c: _Cdp,
    protocol: DebugProtocol,
    io_lock: threading.Lock,
) -> None:
    """Wire evaluate / frame-local callbacks for the current CDP pause."""

    def evaluate(expr: str, frame_index: int) -> str:
        cf = _cfid_paused(m, frame_index)
        if not cf:
            return "<invalid frame>"
        with io_lock, contextlib.suppress(OSError, TypeError, json.JSONDecodeError, KeyError):
            rve = c.req(
                "Debugger.evaluateOnCallFrame",
                {
                    "callFrameId": cf,
                    "expression": expr,
                    "returnByValue": True,
                },
            )
            if isinstance(rve, dict):
                return js_debug.cdp_evaluation_result_string(rve)
        return "<error>"

    def evaluate_many(items: list[tuple[str, int]]) -> list[str]:
        if not items:
            return []
        ids: list[int] = []
        with io_lock:
            for expr, frame_index in items:
                cf = _cfid_paused(m, frame_index)
                if not cf:
                    ids.append(-1)
                    continue
                mid = c._n()
                ids.append(mid)
                c._ws.send(
                    json.dumps(
                        {
                            "id": mid,
                            "method": "Debugger.evaluateOnCallFrame",
                            "params": {
                                "callFrameId": cf,
                                "expression": expr,
                                "returnByValue": True,
                            },
                        },
                    ),
                )
            pending = {i for i in ids if i >= 0}
            results: dict[int, str] = {}
            while pending:
                try:
                    raw = c._ws.recv(8.0)
                except TimeoutError:
                    break
                msg = json.loads(str(raw))
                if not isinstance(msg, dict):
                    continue
                rid = msg.get("id")
                if isinstance(rid, int) and rid in pending:
                    pending.discard(rid)
                    if "result" in msg and isinstance(msg["result"], dict):
                        results[rid] = js_debug.cdp_evaluation_result_string(msg["result"])
                    else:
                        results[rid] = "<error>"
                elif msg.get("method") == "Debugger.paused":
                    c.q.append(msg)
                elif msg.get("method") == "Debugger.scriptParsed":
                    c.dedupe_script_parsed(msg)
        out: list[str] = []
        for mid in ids:
            if mid < 0:
                out.append("<invalid frame>")
            else:
                out.append(results.get(mid, "<error>"))
        return out

    def frame_locals(frame_index: int) -> dict[str, Any]:
        return _locals_for_paused_frame(m, c, frame_index=frame_index, io_lock=io_lock)

    protocol.set_evaluate_callback(evaluate)
    protocol.set_evaluate_batch_callback(evaluate_many)
    protocol.set_frame_locals_callback(frame_locals)

    def apply_pause_on_exceptions(enabled: bool) -> None:
        with io_lock, contextlib.suppress(OSError, TypeError, json.JSONDecodeError, KeyError):
            c.req(
                "Debugger.setPauseOnExceptions",
                {"state": _cdp_pause_on_exceptions_state(enabled)},
            )

    protocol.set_pause_on_exceptions_cdp_hook(apply_pause_on_exceptions)


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
    """WebSocket-backed CDP client (request/response + queued ``Debugger.paused``).

    Also collects ``Debugger.scriptParsed`` events received while waiting for
    request responses so the source-map lookup (used to translate transpiled
    ``.ts`` line numbers) can find the bundle's entry even if its parsed
    event arrives during the early ``Runtime.enable``/``Debugger.enable``
    handshake.
    """

    def __init__(self, ws: object, q: list[dict[str, Any]]) -> None:
        self._ws: Any = ws
        self._i = 0
        self.q = q
        self.script_parsed: list[dict[str, Any]] = []

    def _n(self) -> int:
        self._i += 1
        return self._i

    def dedupe_script_parsed(self, event: dict[str, Any]) -> None:
        """Keep only the latest ``Debugger.scriptParsed`` per script URL."""
        params = event.get("params") or {}
        url = params.get("url") or ""
        self.script_parsed = [
            e
            for e in self.script_parsed
            if not isinstance(e, dict) or (e.get("params") or {}).get("url") != url
        ]
        self.script_parsed.append(event)

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
            method_name = m.get("method")
            if method_name == "Debugger.paused":
                self.q.append(m)
            elif method_name == "Debugger.scriptParsed":
                self.dedupe_script_parsed(m)


def debug_execute(
    script: str,
    context: ScriptInput,
    protocol: DebugProtocol,
    *,
    script_type: str = "pre_request",
    source_name: str = "",
    language: str = "javascript",
    preamble_bundle_text: str | None = None,
    needs_net: bool | None = None,
    breakpoint_url: str | None = None,
    user_first_line_0: int | None = None,
    extra_read_paths: tuple[str, ...] = (),
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
    if user_first_line_0 is not None:
        u0 = user_first_line_0
    else:
        try:
            u0 = user_script_first_line_0_in_debug_bundle(ex, context, language=language)
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
    furl = breakpoint_url or bundle.resolve().as_uri()
    bundle_needs_net = False
    with contextlib.suppress(OSError):
        try:
            from services.scripting.js_runtime import write_local_modules_to_workdir

            if preamble_bundle_text is not None:
                dbg_text = preamble_bundle_text
                bundle_needs_net = bool(needs_net)
                local_mods: dict[str, Any] = {}
            else:
                dbg_text, bundle_needs_net, local_mods = build_debug_bundle_text(
                    ex, context, language=language
                )
                write_local_modules_to_workdir(wdir, local_mods)
            bundle.write_text(dbg_text, encoding="utf-8", newline="\n")
        except RuntimeError as exc:
            return _err(str(exc), (time.monotonic() - t0) * 1000)
    if needs_net is not None:
        bundle_needs_net = bool(needs_net)
    out = _e()
    done: list[dict[str, Any]] = []
    done_e = threading.Event()
    try:
        argv, env = deno_ipc_argv_and_env(
            deno,
            bundle,
            needs_net=bundle_needs_net,
            inspect_brk=f"--inspect-brk=127.0.0.1:{pport}",
            extra_read_paths=extra_read_paths,
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
    src_to_gen: dict[int, list[int]] | None = None
    gen_to_src: dict[int, int] | None = None
    cdp_io_lock = threading.Lock()
    try:
        with connect(ws_s) as wsc:  # type: ignore[union-attr, arg-type, abstract-overlap]
            c = _Cdp(wsc, q)
            c.req("Runtime.enable", {})
            c.req("Debugger.enable", {})
            c.req(
                "Debugger.setPauseOnExceptions",
                {"state": _cdp_pause_on_exceptions_state(protocol.pause_on_exceptions)},
            )
            # Find our bundle's ``Debugger.scriptParsed`` event (collected by
            # ``_Cdp`` during the ``enable`` handshake) and decode its inline
            # source map. Deno emits a source map only when it transpiles
            # (``.ts``); a ``.mjs`` bundle has no source map and we keep 1:1
            # line mapping.
            sp_deadline = time.monotonic() + 1.0
            while src_to_gen is None and time.monotonic() < sp_deadline:
                bundle_event = next(
                    (e for e in c.script_parsed if (e.get("params") or {}).get("url") == furl),
                    None,
                )
                if bundle_event is None:
                    # Drain a few more events to give Deno time to emit ours.
                    with contextlib.suppress(
                        ConnectionClosed,
                        ConnectionClosedError,
                        ConnectionClosedOK,
                    ):
                        try:
                            raw = wsc.recv(0.1)  # type: ignore[union-attr, arg-type, attr-defined]
                        except TimeoutError:
                            continue
                    try:
                        m_drain = json.loads(str(raw))
                    except json.JSONDecodeError:
                        continue
                    if isinstance(m_drain, dict):
                        if m_drain.get("method") == "Debugger.paused":
                            q.append(m_drain)
                        elif m_drain.get("method") == "Debugger.scriptParsed":
                            c.dedupe_script_parsed(m_drain)
                    continue
                p_sp = bundle_event.get("params") or {}
                sm_url = p_sp.get("sourceMapURL") or ""
                sm_data = _decode_inline_source_map(sm_url) if sm_url else None
                if sm_data and isinstance(sm_data.get("mappings"), str):
                    src_to_gen, gen_to_src = _build_source_map(sm_data["mappings"])
                break
            for gln, cond in cdp_break_lines:
                params: dict[str, Any] = {
                    "lineNumber": _src_to_gen_line(src_to_gen, u0 + gln),
                    "url": furl,
                    "columnNumber": 0,
                }
                if cond:
                    params["condition"] = cond
                c.req("Debugger.setBreakpointByUrl", params)
            c.req("Runtime.runIfWaitingForDebugger", {})
            while q and not stopped:
                m0 = q.pop(0)
                r = _process_one_paused(
                    m0,
                    c,
                    protocol,
                    u0,
                    n_user_lines,
                    source_name,
                    script_type,
                    gen_to_src,
                    cdp_io_lock,
                )
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
                        jm,
                        c,
                        protocol,
                        u0,
                        n_user_lines,
                        source_name,
                        script_type,
                        gen_to_src,
                        cdp_io_lock,
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
    c: _Cdp,
    protocol: DebugProtocol,
    u0: int,
    n_user_lines: int,
    source_name: str,
    script_type: str,
    gen_to_src: dict[int, int] | None = None,
    io_lock: threading.Lock | None = None,
) -> bool:
    """Run checkpoint for one ``Debugger.paused``; return ``False`` to stop, ``True`` to continue."""
    if protocol.is_stopped:
        return False
    lock = io_lock or threading.Lock()
    fl_raw = _line_paused(m)
    # When the bundle is transpiled (``.ts``), V8 reports ``lineNumber`` in
    # the *generated* (transpiled) line space. Translate back to bundle source
    # space via the source map before computing the editor-relative line.
    fl = _gen_to_src_line(gen_to_src, fl_raw) if fl_raw >= 0 else fl_raw
    if fl < 0 or fl < u0:
        with contextlib.suppress(OSError, TypeError, json.JSONDecodeError, KeyError), lock:
            c.req("Debugger.resume", {})
        return True
    el = fl - u0
    if n_user_lines <= 0 or el < 0 or el >= n_user_lines:
        with contextlib.suppress(OSError, TypeError, json.JSONDecodeError, KeyError), lock:
            c.req("Debugger.resume", {})
        return True
    reason = _paused_reason(m)
    is_exception = reason in ("exception", "promiseRejection", "assert")
    if is_exception and not protocol.pause_on_exceptions:
        with contextlib.suppress(OSError, TypeError, json.JSONDecodeError, KeyError), lock:
            c.req("Debugger.resume", {})
        return True

    stack = _call_stack_from_paused(m, u0=u0, gen_to_src=gen_to_src)
    _register_pause_adapters(m, c, protocol, lock)
    loc = _locals_for_paused_frame(m, c, frame_index=0, io_lock=lock)
    evc: Any = loc.pop("env_changes", {})
    gch: Any = loc.pop("global_changes", {})
    if not isinstance(evc, dict):
        evc = {}
    if not isinstance(gch, dict):
        gch = {}
    with lock:
        if not evc:
            fe = js_debug.cdp_runtime_evaluate_json_object(
                c, js_debug.CDP_RUNTIME_VARIABLE_CHANGES_JSON
            )
            if fe:
                evc = fe
        if not gch:
            fg = js_debug.cdp_runtime_evaluate_json_object(
                c, js_debug.CDP_RUNTIME_GLOBAL_CHANGES_JSON
            )
            if fg:
                gch = fg
    try:
        force_pause = is_exception and protocol.pause_on_exceptions
        if not protocol.checkpoint(
            el,
            source_name=source_name,
            local_vars=loc,
            script_type=script_type,
            env_changes=evc,
            global_changes=gch,
            call_stack=stack,
            selected_frame_index=0,
            force_pause=force_pause,
        ):
            protocol.set_evaluate_callback(None)
            protocol.set_evaluate_batch_callback(None)
            protocol.set_frame_locals_callback(None)
            return False
    finally:
        protocol.set_evaluate_callback(None)
        protocol.set_evaluate_batch_callback(None)
        protocol.set_frame_locals_callback(None)
    with contextlib.suppress(OSError, TypeError, json.JSONDecodeError, KeyError), lock:
        c.req("Debugger.resume", {})
    return True
