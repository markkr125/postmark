"""Debug execution helpers for the RestrictedPython sandbox subprocess."""

from __future__ import annotations

import json
import sys
from typing import Any

from services.scripting._sandbox_pm import _Pm, _serialize_request_mutations
from services.scripting._sandbox_runtime import (
    _ConsolePrintCollector,
    _console_emit,
    _console_logs,
    _error_output,
    _getattr_guard,
)
from services.scripting._sandbox_safe_globals import _SAFE_BUILTINS, _SAFE_STDLIB

try:
    from RestrictedPython import compile_restricted, safe_globals  # type: ignore[import-untyped]

    _HAS_RESTRICTED = True
except ImportError:
    _HAS_RESTRICTED = False
    compile_restricted = None  # type: ignore[assignment]
    safe_globals = {}  # type: ignore[assignment]


_DEBUG_VAR_MAX_DEPTH = 4
_DEBUG_VAR_MAX_STR = 400
_DEBUG_VAR_MAX_LEN = 64


def _serialize_debug_value(
    value: Any,
    depth: int = 0,
    seen: set[int] | None = None,
) -> Any:
    """Convert *value* into a JSON-friendly tree for the debug variables panel.

    Returns scalars as-is, walks ``dict``/``list``/``tuple`` recursively, and
    introspects wrapped objects (``_PmResponse``, ``_PmRequest``, ``_HeaderList``,
    ``_PmUrl`` …) by exposing their non-callable public attributes as a dict.
    Without this, every wrapped object would arrive in the UI as
    ``"<__main__._PmResponse object at 0x…>"`` — useless for inspection.
    """
    if seen is None:
        seen = set()
    if depth > _DEBUG_VAR_MAX_DEPTH:
        return f"<truncated {type(value).__name__}>"

    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value if len(value) <= _DEBUG_VAR_MAX_STR else value[:_DEBUG_VAR_MAX_STR] + "…"
    if isinstance(value, bytes):
        try:
            decoded = value.decode("utf-8", errors="replace")
        except Exception:
            return f"<bytes len={len(value)}>"
        return decoded if len(decoded) <= _DEBUG_VAR_MAX_STR else decoded[:_DEBUG_VAR_MAX_STR] + "…"

    oid = id(value)
    if oid in seen:
        return "<circular>"
    seen = seen | {oid}

    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= _DEBUG_VAR_MAX_LEN:
                out["__truncated__"] = f"… +{len(value) - _DEBUG_VAR_MAX_LEN} more"
                break
            try:
                out[str(k)] = _serialize_debug_value(v, depth + 1, seen)
            except Exception:
                out[str(k)] = "<error>"
        return out
    if isinstance(value, list | tuple | set | frozenset):
        items = list(value)
        out_l: list[Any] = []
        for i, item in enumerate(items):
            if i >= _DEBUG_VAR_MAX_LEN:
                out_l.append(f"… +{len(items) - _DEBUG_VAR_MAX_LEN} more")
                break
            try:
                out_l.append(_serialize_debug_value(item, depth + 1, seen))
            except Exception:
                out_l.append("<error>")
        return out_l

    # Wrapped types (``_PmResponse``, ``_HeaderList``, …) opt in by defining
    # ``__pm_debug__()`` returning a JSON-friendly view. Their real data lives
    # behind underscore-prefixed attrs (``_cookies``, ``_items``) which the
    # generic ``dir()`` walk would skip, leaving an opaque ``repr``.
    debug_view = getattr(value, "__pm_debug__", None)
    if callable(debug_view):
        try:
            return _serialize_debug_value(debug_view(), depth + 1, seen)
        except Exception:
            pass

    # Generic object: collect non-callable public attrs.
    obj_dict: dict[str, Any] = {}
    try:
        names = [n for n in dir(value) if not n.startswith("_")]
    except Exception:
        names = []
    for name in names:
        try:
            attr = getattr(value, name)
        except Exception:
            continue
        if callable(attr):
            continue
        try:
            obj_dict[name] = _serialize_debug_value(attr, depth + 1, seen)
        except Exception:
            obj_dict[name] = "<error>"
    if obj_dict:
        return obj_dict
    try:
        return repr(value)[:_DEBUG_VAR_MAX_STR]
    except Exception:
        return "<repr error>"


def _stack_frames_from(frame: Any) -> list[Any]:
    """Return Python frames for the user ``<script>`` stack (innermost first)."""
    frames: list[Any] = []
    f = frame
    while f is not None and getattr(f.f_code, "co_filename", "") == "<script>":
        frames.append(f)
        f = f.f_back
    return frames


def _call_stack_from_frame(frame: Any) -> list[dict[str, Any]]:
    """Serialise the user-script stack for the debug call-stack panel."""
    out: list[dict[str, Any]] = []
    for fr in _stack_frames_from(frame):
        name = fr.f_code.co_name or "<module>"
        out.append(
            {
                "id": str(id(fr)),
                "name": name,
                "line": fr.f_lineno - 1,
                "column": 0,
            }
        )
    return out


def _safe_locals_for_frame(frame: Any, initial_namespace: set[str], pm: _Pm) -> dict[str, Any]:
    """Build the filtered locals dict for one Python debug frame."""
    safe_locals: dict[str, Any] = {}
    for k, v in frame.f_locals.items():
        if k.startswith("_") or k == "pm":
            continue
        if k in initial_namespace:
            continue
        try:
            safe_locals[k] = _serialize_debug_value(v)
        except Exception:
            safe_locals[k] = "<error>"
    try:
        resp = getattr(pm, "response", None)
        if resp is not None:
            safe_locals["pm.response"] = _serialize_debug_value(resp)
    except Exception:
        pass
    return safe_locals


def _parse_breakpoints(raw: Any) -> dict[int, str | None]:
    """Normalise breakpoint payload from the debug IPC resume command."""
    out: dict[int, str | None] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                line = int(k)
            except (TypeError, ValueError):
                continue
            out[line] = v if isinstance(v, str) and v.strip() else None
        return out
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, int):
                out[x] = None
    return out


def _execute_debug(script: str, pm: _Pm, debug_cfg: dict[str, Any]) -> dict[str, Any]:
    """Execute *script* with ``sys.settrace`` for line-level debugging.

    On each line event the trace function checks breakpoints, writes a
    ``debugPause`` IPC message, and waits for a resume command.
    """
    breakpoints: dict[int, str | None] = _parse_breakpoints(debug_cfg.get("breakpoints"))
    step_mode: list[str] = ["continue"]  # mutable container for closure
    pause_frames: list[Any] = []
    # Names present in the script's namespace BEFORE user code runs — every
    # ``_SAFE_GLOBALS``/``_SAFE_STDLIB`` helper, ``pm``, RestrictedPython
    # plumbing (``_getattr_``, ``_print_``), etc. Filtering against this set
    # at pause time keeps the locals view focused on user-introduced names
    # (``response``, ``body``, …) instead of drowning them in dozens of
    # injected helpers like ``b64decode``, ``json_loads``, ``math_pi``.
    initial_namespace: set[str] = set()

    def _eval_expr(expr: str, fr: Any) -> str:
        try:
            val = eval(expr, fr.f_globals, fr.f_locals)
            return str(_serialize_debug_value(val))
        except Exception as exc:
            return f"<error: {exc}>"

    def _trace_fn(frame: Any, event: str, arg: Any) -> Any:
        """Trace function installed via ``sys.settrace``."""
        if frame.f_code.co_filename != "<script>":
            return _trace_fn
        if event != "line":
            return _trace_fn

        line = frame.f_lineno - 1  # 0-based

        should_pause = step_mode[0] in ("step_over", "step_into")
        if line in breakpoints:
            cond = breakpoints[line]
            if cond:
                try:
                    if not eval(cond, frame.f_globals, frame.f_locals):
                        return _trace_fn
                except Exception:
                    pass  # fail-open on condition errors
            should_pause = True
        if not should_pause:
            return _trace_fn

        pause_frames.clear()
        pause_frames.extend(_stack_frames_from(frame))
        active = pause_frames[0] if pause_frames else frame
        safe_locals = _safe_locals_for_frame(active, initial_namespace, pm)

        env_changes: dict[str, str] = {}
        for scope in (pm.variables, pm.environment, pm.collection_variables):
            env_changes.update(scope._changes)
        global_changes: dict[str, str] = dict(pm.globals._changes)

        # Write pause message.
        sys.stdout.write(
            json.dumps(
                {
                    "__ipc__": "debugPause",
                    "line": line,
                    "locals": safe_locals,
                    "env_changes": env_changes,
                    "global_changes": global_changes,
                    "call_stack": _call_stack_from_frame(frame),
                    "selected_frame_index": 0,
                }
            )
            + "\n"
        )
        sys.stdout.flush()

        # Wait for resume / eval commands from parent.
        while True:
            cmd_line = sys.stdin.readline()
            if not cmd_line:
                sys.settrace(None)
                return None
            try:
                cmd = json.loads(cmd_line)
            except json.JSONDecodeError:
                return _trace_fn
            if not isinstance(cmd, dict):
                continue
            op = cmd.get("op")
            if op == "eval":
                idx = int(cmd.get("frame", 0))
                fr = pause_frames[idx] if 0 <= idx < len(pause_frames) else active
                result = _eval_expr(str(cmd.get("expr", "")), fr)
                sys.stdout.write(json.dumps({"__ipc__": "evalResult", "value": result}) + "\n")
                sys.stdout.flush()
                continue
            if op == "evalMany":
                raw_items = cmd.get("exprs", [])
                values: list[str] = []
                if isinstance(raw_items, list):
                    for item in raw_items:
                        if isinstance(item, list | tuple) and len(item) >= 2:
                            expr_s = str(item[0])
                            idx = int(item[1])
                        else:
                            expr_s = ""
                            idx = 0
                        fr = pause_frames[idx] if 0 <= idx < len(pause_frames) else active
                        values.append(_eval_expr(expr_s, fr))
                sys.stdout.write(json.dumps({"__ipc__": "evalManyResult", "values": values}) + "\n")
                sys.stdout.flush()
                continue
            if op == "getLocals":
                idx = int(cmd.get("frame", 0))
                fr = pause_frames[idx] if 0 <= idx < len(pause_frames) else active
                locals_out = _safe_locals_for_frame(fr, initial_namespace, pm)
                sys.stdout.write(
                    json.dumps({"__ipc__": "localsResult", "locals": locals_out}) + "\n"
                )
                sys.stdout.flush()
                continue

            raw_bp = cmd.get("breakpoints")
            if raw_bp is not None:
                breakpoints.clear()
                breakpoints.update(_parse_breakpoints(raw_bp))

            command = cmd.get("command", "continue")
            if command == "stop":
                sys.settrace(None)
                msg = "Debug session stopped by user"
                raise SystemExit(msg)

            step_mode[0] = command
            break
        return _trace_fn

    if not _HAS_RESTRICTED:
        return _error_output("RestrictedPython is not installed")

    try:
        code = compile_restricted(script, filename="<script>", mode="exec")
    except SyntaxError as e:
        return _error_output(f"Syntax error: {e}")

    if code is None:
        return _error_output("Compilation failed — script contains restricted syntax")

    restricted_globals: dict[str, Any] = {}
    restricted_globals.update(safe_globals)  # type: ignore[arg-type]
    restricted_globals["__builtins__"] = _SAFE_BUILTINS
    restricted_globals["_getattr_"] = _getattr_guard
    restricted_globals["_getiter_"] = iter
    restricted_globals["_getitem_"] = lambda obj, key: obj[key]
    restricted_globals["_write_"] = lambda obj: obj
    restricted_globals["_inplacevar_"] = lambda op, x, y: op(x, y)
    restricted_globals["pm"] = pm
    restricted_globals.update(_SAFE_STDLIB)
    restricted_globals["_print_"] = _ConsolePrintCollector

    # Snapshot namespace keys BEFORE user code runs — closure used by
    # ``_trace_fn`` to hide injected helpers from the debug locals view.
    initial_namespace.update(restricted_globals.keys())

    sys.settrace(_trace_fn)
    try:
        exec(code, restricted_globals)
    except SystemExit:
        _console_emit("info", "[Debug] Session stopped by user")
    except Exception as e:
        _console_emit("error", f"Runtime error: {e}")
        pm._test_results.append(
            {"name": "(runtime error)", "passed": False, "error": str(e), "duration_ms": 0.0}
        )
    finally:
        sys.settrace(None)

    from services.scripting.context import harvest_legacy_tests

    harvest_legacy_tests(restricted_globals.get("tests"), pm._test_results)

    all_changes: dict[str, str] = {}
    for scope in (pm.variables, pm.environment, pm.collection_variables):
        all_changes.update(scope._changes)

    global_changes: dict[str, str] = dict(pm.globals._changes)

    request_mutations: dict[str, Any] | None = None
    if pm._is_pre_request:
        request_mutations = _serialize_request_mutations(pm.request)

    return {
        "test_results": pm._test_results,
        "console_logs": _console_logs,
        "variable_changes": all_changes,
        **({"global_variable_changes": global_changes} if global_changes else {}),
        "request_mutations": request_mutations,
        **({"next_request": pm.execution._next} if pm.execution._next_set else {}),
        **({"skip_request": True} if pm.execution._skip else {}),
    }
