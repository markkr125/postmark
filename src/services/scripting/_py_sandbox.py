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

import hashlib
import json
import re
import sys
import types
from collections.abc import Callable
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
from services.scripting.context import harvest_legacy_tests

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

_LOCAL_MOD_NAME_RE = re.compile(r"[^A-Za-z0-9_]+")


def main() -> None:
    """Read ScriptInput from stdin, execute script, write ScriptOutput to stdout."""
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
    raw_local = payload.get("local_modules") or {}
    if not isinstance(raw_local, dict):
        _write_done(_error_output("Invalid local_modules payload (expected object)"))
        return
    local_modules: dict[str, str] = {
        str(k): str(v) for k, v in raw_local.items() if isinstance(k, str)
    }

    # Loader closes over a one-element pm holder so ``_Pm`` can receive the
    # loader via its constructor while nested ``pm.require("local:…")`` still
    # sees the same ``pm`` instance.
    pm_holder: list[_Pm] = []
    loader = _make_local_module_loader(local_modules, pm_holder)
    pm = _Pm(context, local_module_loader=loader)
    pm_holder.append(pm)

    output = _execute_debug(script, pm, debug_cfg) if debug_cfg else _execute_restricted(script, pm)
    _write_done(output)


def _sanitize_local_mod_name(rel_path: str) -> str:
    """Build a collision-resistant ``sys.modules`` key from a virtual local path.

    A short human-readable stem is kept for debugging; a path digest suffix
    ensures ``lib/a-b.py`` and ``lib/a_b.py`` never share a module name.
    """
    path = rel_path.strip()
    cleaned = _LOCAL_MOD_NAME_RE.sub("_", path).strip("_") or "module"
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
    return f"pm_local_{cleaned[:48]}_{digest}"


def _make_local_module_loader(
    sources: dict[str, str],
    pm_holder: list[_Pm],
) -> Callable[[str], Any]:
    """Return a ``pm.require('local:…')`` loader for *sources* (per-run cache).

    *pm_holder* is a one-element list populated with the ``_Pm`` instance after
    construction so this loader can be passed into the constructor.
    """
    cache: dict[str, types.ModuleType] = {}

    def load(rel_path: str) -> Any:
        path = rel_path.strip()
        if not path.endswith(".py"):
            valid = ", ".join(sorted(sources)) or "(none)"
            msg = f"pm.require: local path {path!r} must end with .py (available: {valid})"
            raise RuntimeError(msg)
        if path in cache:
            return cache[path]
        source = sources.get(path)
        if source is None:
            valid = ", ".join(sorted(sources)) or "(none)"
            msg = f"pm.require: no local script at {path!r} (available: {valid})"
            raise RuntimeError(msg)
        if not _HAS_RESTRICTED or compile_restricted is None:
            msg = "RestrictedPython is not installed"
            raise RuntimeError(msg)
        if not pm_holder:
            msg = "pm.require('local:…'): pm is not ready"
            raise RuntimeError(msg)
        pm = pm_holder[0]
        mod_name = _sanitize_local_mod_name(path)
        try:
            code = compile_restricted(source, filename=f"<local:{path}>", mode="exec")
        except SyntaxError as e:
            msg = f"pm.require('local:{path}'): Syntax error: {e}"
            raise RuntimeError(msg) from e
        if code is None:
            msg = (
                f"pm.require('local:{path}'): Compilation failed — "
                "script contains restricted syntax"
            )
            raise RuntimeError(msg)

        mod = types.ModuleType(mod_name)
        ns = mod.__dict__
        ns.update(safe_globals)  # type: ignore[arg-type]
        ns["__builtins__"] = _SAFE_BUILTINS
        ns["_getattr_"] = _getattr_guard
        ns["_getiter_"] = iter
        ns["_getitem_"] = _getitem_guard
        ns["_write_"] = lambda obj: obj
        ns["_inplacevar_"] = lambda op, x, y: op(x, y)
        ns["pm"] = pm
        ns.update(_SAFE_STDLIB)
        ns.update(_legacy_script_globals(pm))
        ns["_print_"] = _ConsolePrintCollector
        ns["__name__"] = mod_name
        try:
            exec(code, ns)
        except Exception as e:
            msg = f"pm.require('local:{path}'): Runtime error: {e}"
            raise RuntimeError(msg) from e
        sys.modules[mod_name] = mod
        cache[path] = mod
        return mod

    return load


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

    # 3. Execute (resource limits after compile/setup — RLIMIT_NOFILE=3 breaks imports).
    _apply_resource_limits()
    try:
        exec(code, restricted_globals)
    except Exception as e:
        _console_emit("error", f"Runtime error: {e}")
        pm._test_results.append(
            {"name": "(runtime error)", "passed": False, "error": str(e), "duration_ms": 0.0}
        )

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
