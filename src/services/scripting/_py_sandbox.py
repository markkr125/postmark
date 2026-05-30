"""Python sandbox worker — runs in a subprocess.

Reads a JSON ``ScriptInput`` from stdin, compiles the user script with
``RestrictedPython``, executes it in a heavily restricted environment,
and writes a JSON ``ScriptOutput`` to stdout.

Security layers:
1. **Subprocess isolation** — crash or exploit cannot affect the main app.
2. **RestrictedPython** — AST-level import/exec/eval blocking.
3. **Restricted builtins** — minimal whitelist, no ``open``/``__import__``.
4. **Attribute guard** — rejects all ``_``-prefixed attribute access.
5. **Resource limits** — CPU 5s, memory 128 MB, no new file descriptors.
"""

from __future__ import annotations

import json
import sys
from typing import Any

try:
    from RestrictedPython import (  # type: ignore[import-untyped]
        compile_restricted,
        safe_globals,
    )

    _HAS_RESTRICTED = True
except ImportError:
    _HAS_RESTRICTED = False
    compile_restricted = None  # type: ignore[assignment]
    safe_globals = {}  # type: ignore[assignment]

from services.scripting._sandbox_debug import _execute_debug
from services.scripting._sandbox_pm import _Pm, _legacy_script_globals, _serialize_request_mutations
from services.scripting._sandbox_pm_models import _HeaderList, _PmRequest, _PmResponse
from services.scripting._sandbox_runtime import (
    _ConsolePrintCollector,
    _apply_resource_limits,
    _console_emit,
    _console_logs,
    _error_output,
    _getattr_guard,
    _getitem_guard,
    _write_done,
)
from services.scripting._sandbox_safe_globals import _SAFE_BUILTINS, _SAFE_STDLIB

__all__ = [
    "_HeaderList",
    "_PmRequest",
    "_PmResponse",
    "_apply_resource_limits",
    "_console_emit",
    "_error_output",
    "_getattr_guard",
    "_write_done",
]


def main() -> None:
    """Read ScriptInput from stdin, execute script, write ScriptOutput to stdout."""
    _apply_resource_limits()
    raw = sys.stdin.readline()
    if not raw or not raw.strip():
        _write_done(_error_output("No input received"))
        return

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        _write_done(_error_output(f"Invalid JSON input: {e}"))
        return

    script = payload.get("script", "")
    context = payload.get("context", {})
    debug_cfg = payload.get("debug")

    pm = _Pm(context)

    output = _execute_debug(script, pm, debug_cfg) if debug_cfg else _execute_restricted(script, pm)
    _write_done(output)


def _execute_restricted(script: str, pm: _Pm) -> dict[str, Any]:
    """Compile and execute script in a restricted environment."""
    if not _HAS_RESTRICTED:
        return _error_output("RestrictedPython is not installed")

    # 1. Compile with AST restrictions.
    try:
        code = compile_restricted(script, filename="<script>", mode="exec")
    except SyntaxError as e:
        return _error_output(f"Syntax error: {e}")

    if code is None:
        return _error_output("Compilation failed — script contains restricted syntax")

    # 2. Build restricted globals.
    restricted_globals: dict[str, Any] = {}
    restricted_globals.update(safe_globals)  # type: ignore[arg-type]
    restricted_globals["__builtins__"] = _SAFE_BUILTINS
    restricted_globals["_getattr_"] = _getattr_guard
    restricted_globals["_getiter_"] = iter
    restricted_globals["_getitem_"] = _getitem_guard
    restricted_globals["_write_"] = lambda obj: obj
    restricted_globals["_inplacevar_"] = lambda op, x, y: op(x, y)

    # Inject pm object.
    restricted_globals["pm"] = pm

    # Inject safe stdlib functions.
    restricted_globals.update(_SAFE_STDLIB)

    # Inject Postman v1 legacy globals (responseBody, responseCode, …).
    restricted_globals.update(_legacy_script_globals(pm))

    # Redirect print to console.log.
    # RestrictedPython rewrites ``print(x)`` to ``_print._call_print(x)``
    # where ``_print = _print_()``.  We provide a factory returning an
    # object whose ``_call_print`` forwards to our console capture.
    restricted_globals["_print_"] = _ConsolePrintCollector

    # 3. Execute.
    try:
        exec(code, restricted_globals)
    except Exception as e:
        _console_emit("error", f"Runtime error: {e}")
        pm._test_results.append(
            {"name": "(runtime error)", "passed": False, "error": str(e), "duration_ms": 0.0}
        )

    from services.scripting.context import harvest_legacy_tests

    harvest_legacy_tests(restricted_globals.get("tests"), pm._test_results)

    # 4. Build output.
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


if __name__ == "__main__":
    main()
