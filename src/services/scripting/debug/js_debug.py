"""JavaScript debug execution — statement-by-statement V8 stepping.

Splits a script into top-level statement groups (respecting brace
nesting), then executes each group with a separate ``ctx.eval()`` call.
Between groups the :class:`DebugProtocol` is consulted so the UI can
pause, inspect variables, and step.

All ``eval()`` calls share a single :pyclass:`MiniRacer` context so
side effects (variable assignments, ``pm.*`` calls) accumulate across
groups exactly as they would in a single-pass execution.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.scripting import ScriptInput, ScriptOutput
    from services.scripting.debug.protocol import DebugProtocol

logger = logging.getLogger(__name__)


def inject_checkpoints(source: str) -> str:
    """Insert ``__pm_checkpoint(N, stateJson)`` before each non-empty line.

    *N* is the 0-based line index in the **original** source so that
    breakpoint line numbers map directly to the editor.

    .. note::
       This function is retained for tests and potential future use
       with an async MiniRacer backend.
    """
    lines = source.split("\n")
    result: list[str] = []
    for i, line in enumerate(lines):
        if line.strip():
            indent = len(line) - len(line.lstrip())
            result.append(
                " " * indent
                + f"__pm_checkpoint({i},"
                + " JSON.stringify(__pm_state.variables || {}));"
            )
        result.append(line)
    return "\n".join(result)


# ------------------------------------------------------------------
# Statement grouping
# ------------------------------------------------------------------


def _split_into_groups(source: str) -> list[tuple[int, str]]:
    """Split JS source into executable top-level statement groups.

    Returns a list of ``(start_line, code_fragment)`` tuples.  Brace
    nesting is tracked so multi-line blocks (``if``, ``for``,
    ``function``) are kept as a single group.
    """
    lines = source.split("\n")
    groups: list[tuple[int, str]] = []
    current: list[str] = []
    group_start = 0
    depth = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            # Preserve blank lines inside open blocks.
            if current:
                current.append(line)
            continue

        if not current:
            group_start = i

        current.append(line)
        depth += stripped.count("{") - stripped.count("}")

        if depth <= 0:
            groups.append((group_start, "\n".join(current)))
            current = []
            depth = 0

    # Flush any trailing group (e.g. unclosed brace).
    if current:
        groups.append((group_start, "\n".join(current)))

    return groups


def debug_execute(
    script: str,
    context: ScriptInput,
    protocol: DebugProtocol,
    *,
    script_type: str = "pre_request",
    source_name: str = "",
) -> ScriptOutput:
    """Run *script* in debug mode, executing statement-by-statement.

    Each top-level statement group is executed as a separate
    ``ctx.eval()`` call.  Between groups, the :class:`DebugProtocol`
    checkpoint blocks the worker thread until the UI resumes.
    """
    from services.scripting.js_runtime import (
        _MAX_MEMORY_BYTES,
        _build_js_context,
        _detect_required_modules,
        _empty_output,
        _get_bootstrap,
        _get_polyfills,
        _get_vendor_file,
        _process_send_queue,
        _resolve_vendor_files,
    )

    output = _empty_output()
    start = time.monotonic()

    try:
        from py_mini_racer import MiniRacer  # type: ignore[import-untyped]

        ctx = MiniRacer()

        # 1. Load polyfills (always) + vendor libs required by the script.
        ctx.eval(_get_polyfills())
        for vf in _resolve_vendor_files(_detect_required_modules(script)):
            ctx.eval(_get_vendor_file(vf))

        # 2. Set context data before bootstrap reads it.
        ctx.eval("var __pm_context = " + json.dumps(_build_js_context(context)) + ";")

        # 3. Run bootstrap to create pm/console objects.
        ctx.eval(_get_bootstrap())

        # 4. Split into statement groups and step through.
        groups = _split_into_groups(script)

        stopped = False
        for group_start, code in groups:
            # Read current variable state for the debugger panel.
            local_vars = _read_js_vars(ctx)

            should_continue = protocol.checkpoint(
                group_start,
                source_name=source_name,
                local_vars=local_vars,
                script_type=script_type,
            )
            if not should_continue:
                stopped = True
                break

            ctx.eval(code, max_memory=_MAX_MEMORY_BYTES)

        if stopped:
            output["console_logs"].append(
                {
                    "level": "info",
                    "message": "[Debug] Session stopped by user",
                    "timestamp": time.time(),
                }
            )
        else:
            # 4. Process sendRequest queue after all groups.
            _process_send_queue(ctx)

        # 5. Extract accumulated state.
        state_json = ctx.eval("JSON.stringify(__pm_state)")
        state: dict[str, Any] = json.loads(state_json)  # type: ignore[arg-type]

        output["test_results"] = state.get("test_results", [])
        output["console_logs"].extend(state.get("console_logs", []))
        output["variable_changes"] = state.get("variable_changes", {})
        global_changes = state.get("global_variable_changes", {})
        if global_changes:
            output["global_variable_changes"] = global_changes

        if context.get("response") is None and state.get("request_mutations"):
            output["request_mutations"] = state["request_mutations"]

        if state.get("next_request") is not None or "next_request" in state:
            output["next_request"] = state.get("next_request")
        if state.get("skip_request"):
            output["skip_request"] = True

    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        error_msg = str(exc)
        if "memory" in error_msg.lower():
            error_msg = "Script exceeded memory limit"

        output["test_results"].append(
            {
                "name": "(debug error)",
                "passed": False,
                "error": error_msg,
                "duration_ms": elapsed,
            }
        )
        logger.warning("JS debug execution failed: %s", error_msg)
    finally:
        protocol.finish()

    return output


def _read_js_vars(ctx: Any) -> dict[str, Any]:
    """Read current ``__pm_state.variables`` from the V8 context."""
    try:
        raw = ctx.eval("JSON.stringify(__pm_state.variables || {})")
        result: dict[str, Any] = json.loads(raw)  # type: ignore[arg-type]
        return result
    except Exception:
        return {}
