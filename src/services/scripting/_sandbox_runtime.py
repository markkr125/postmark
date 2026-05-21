"""Subprocess runtime helpers — resource limits, console capture, IPC output."""

from __future__ import annotations

import contextlib
import inspect
import json
import sys
import time
from typing import Any

_CPU_LIMIT_SEC = 5
_MEM_LIMIT_BYTES = 134_217_728  # 128 MB

_CONSOLE_LIMIT = 200
_console_logs: list[dict[str, Any]] = []


def _apply_resource_limits() -> None:
    """Set CPU, memory, and file-descriptor limits."""
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (_CPU_LIMIT_SEC, _CPU_LIMIT_SEC))
        resource.setrlimit(resource.RLIMIT_AS, (_MEM_LIMIT_BYTES, _MEM_LIMIT_BYTES))
        # Allow only stdin/stdout/stderr — no new file descriptors.
        resource.setrlimit(resource.RLIMIT_NOFILE, (3, 3))
    except (ImportError, ValueError, OSError):
        pass  # Non-Linux or unprivileged — limits won't apply.


def _console_source_line() -> int | None:
    """Best-effort 0-based editor line (mirrors ``py_runtime.python_console_frame_to_editor_line``)."""
    frame = inspect.currentframe()
    if frame is None:
        return None
    offset = 0
    if "__pm_user_script_line0" in frame.f_globals:
        with contextlib.suppress(TypeError, ValueError):
            offset += int(frame.f_globals["__pm_user_script_line0"])
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


def _console_emit(level: str, *args: object) -> None:
    """Capture a console message (rate-limited)."""
    if len(_console_logs) >= _CONSOLE_LIMIT:
        return
    parts = []
    for a in args:
        try:
            parts.append(str(a))
        except Exception:
            parts.append("<unprintable>")
    entry: dict[str, Any] = {
        "level": level,
        "message": " ".join(parts),
        "timestamp": time.time(),
    }
    sl = _console_source_line()
    if sl is not None:
        entry["source_line"] = sl
    _console_logs.append(entry)


def _getattr_guard(obj: object, name: str, default: Any = None) -> Any:
    """Block access to underscore-prefixed attributes."""
    if name.startswith("_"):
        msg = f"Attribute access denied: {name}"
        raise AttributeError(msg)
    return getattr(obj, name, default)


class _ConsolePrintCollector:
    """Print collector for RestrictedPython's rewritten ``print()`` calls."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def _call_print(self, *args: object, **kwargs: object) -> None:
        _console_emit("log", *args)


def _error_output(message: str) -> dict[str, Any]:
    """Return a ScriptOutput with a single failed test result."""
    return {
        "test_results": [
            {"name": "(runtime error)", "passed": False, "error": message, "duration_ms": 0.0}
        ],
        "console_logs": _console_logs,
        "variable_changes": {},
        "request_mutations": None,
    }


def _write_done(output: dict[str, Any]) -> None:
    """Write the final ScriptOutput to stdout with the ``__done__`` marker."""
    output["__done__"] = True
    sys.stdout.write(json.dumps(output) + "\n")
    sys.stdout.flush()
