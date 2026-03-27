"""JavaScript script runtime using PyMiniRacer (V8 isolate).

Executes user scripts in an isolated V8 engine with zero ambient
capabilities.  The ``pm`` API is injected via ``pm_bootstrap.js``.

Resource limits:
- **Timeout:** 5 seconds per script execution.
- **Memory:** 64 MB maximum heap.
- **pm.sendRequest:** max 10 JS-side calls; 50 total per execution.
- **console output:** max 200 messages per execution.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.scripting import ScriptInput, ScriptOutput

logger = logging.getLogger(__name__)

# V8 resource limits.
_TIMEOUT_MS = 5_000
_MAX_MEMORY_BYTES = 67_108_864  # 64 MB

# Path to the bootstrap JS preamble.
_BOOTSTRAP_PATH = Path(__file__).resolve().parents[2] / "data" / "scripts" / "pm_bootstrap.js"

# Cached bootstrap source — loaded once on first use.
_bootstrap_source: str | None = None


def _get_bootstrap() -> str:
    """Return the bootstrap JS source, caching after first read."""
    global _bootstrap_source
    if _bootstrap_source is None:
        _bootstrap_source = _BOOTSTRAP_PATH.read_text(encoding="utf-8")
    return _bootstrap_source


def _empty_output() -> ScriptOutput:
    """Return an empty ``ScriptOutput`` dict."""
    return {
        "test_results": [],
        "console_logs": [],
        "variable_changes": {},
        "request_mutations": None,
    }


class JSRuntime:
    """Execute JavaScript scripts in a sandboxed V8 isolate.

    Each call to :meth:`execute` creates a fresh ``MiniRacer`` context
    so no state leaks between executions.
    """

    @staticmethod
    def execute(script: str, context: ScriptInput) -> ScriptOutput:
        """Run *script* with *context* and return accumulated results.

        Returns a valid :class:`ScriptOutput` even on error — failures
        are recorded as a single failed ``TestResult``.
        """
        try:
            from py_mini_racer import MiniRacer  # type: ignore[import-untyped]
        except ImportError:
            logger.error("py_mini_racer is not installed — JS scripts disabled")
            out = _empty_output()
            out["test_results"].append(
                {
                    "name": "(runtime error)",
                    "passed": False,
                    "error": "py_mini_racer is not installed",
                    "duration_ms": 0.0,
                }
            )
            return out

        return _run_in_isolate(MiniRacer, script, context)


def _run_in_isolate(
    mini_racer_cls: type,
    script: str,
    context: ScriptInput,
) -> ScriptOutput:
    """Create a V8 isolate, inject context, run script, extract state."""
    start = time.monotonic()
    output = _empty_output()

    try:
        ctx = mini_racer_cls()

        # 1. Set context data before bootstrap reads it.
        ctx.eval("var __pm_context = " + json.dumps(_build_js_context(context)) + ";")

        # 2. Run bootstrap to create pm/console objects.
        ctx.eval(_get_bootstrap())

        # 3. Execute user script with timeout and memory limits.
        ctx.eval(script, timeout=_TIMEOUT_MS, max_memory=_MAX_MEMORY_BYTES)

        # 4. Process sendRequest queue (trampoline loop).
        _process_send_queue(ctx)

        # 5. Extract accumulated state.
        state_json = ctx.eval("JSON.stringify(__pm_state)")
        state: dict[str, Any] = json.loads(state_json)

        output["test_results"] = state.get("test_results", [])
        output["console_logs"] = state.get("console_logs", [])
        output["variable_changes"] = state.get("variable_changes", {})
        global_changes = state.get("global_variable_changes", {})
        if global_changes:
            output["global_variable_changes"] = global_changes

        # 6. Capture request mutations (pre-request only).
        if context.get("response") is None and state.get("request_mutations"):
            output["request_mutations"] = state["request_mutations"]

        # 7. Capture execution flow control.
        if state.get("next_request") is not None or "next_request" in state:
            output["next_request"] = state.get("next_request")
        if state.get("skip_request"):
            output["skip_request"] = True

    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        error_msg = str(exc)

        # Classify common V8 errors for friendlier messages.
        if "timeout" in error_msg.lower() or "execution terminated" in error_msg.lower():
            error_msg = f"Script timed out after {_TIMEOUT_MS / 1000:.0f} seconds"
        elif "memory" in error_msg.lower():
            error_msg = f"Script exceeded memory limit ({_MAX_MEMORY_BYTES // 1048576} MB)"

        output["test_results"].append(
            {
                "name": "(runtime error)",
                "passed": False,
                "error": error_msg,
                "duration_ms": elapsed,
            }
        )
        logger.warning("JS script execution failed: %s", error_msg)

    return output


def _build_js_context(context: ScriptInput) -> dict[str, Any]:
    """Convert ``ScriptInput`` to the shape expected by ``pm_bootstrap.js``."""
    req = context.get("request", {})
    # Convert headers dict to list of {key, value} for the JS side.
    raw_headers = req.get("headers", {})
    if isinstance(raw_headers, dict):
        header_list = [{"key": k, "value": v} for k, v in raw_headers.items()]
    else:
        header_list = raw_headers

    resp = context.get("response")
    resp_data = None
    if resp:
        resp_headers = resp.get("headers", {})
        if isinstance(resp_headers, dict):
            resp_header_list = [{"key": k, "value": v} for k, v in resp_headers.items()]
        else:
            resp_header_list = resp_headers
        resp_data = {
            "status_code": resp.get("status_code", 0),
            "status": resp.get("status", ""),
            "headers": resp_header_list,
            "body": resp.get("body", ""),
            "response_time": resp.get("elapsed_ms", 0),
            "response_size": resp.get("size_bytes", 0),
        }

    return {
        "request": {
            "url": req.get("url", ""),
            "method": req.get("method", "GET"),
            "headers": header_list,
            "body": req.get("body", ""),
        },
        "response": resp_data,
        "variables": context.get("variables", {}),
        "environment_vars": context.get("environment_vars", {}),
        "collection_vars": context.get("collection_vars", {}),
        "global_vars": context.get("global_vars", {}),
        "info": context.get("info", {}),
        "is_pre_request": resp is None,
        "iteration_data": context.get("iteration_data", {}),
    }


# -- sendRequest trampoline -------------------------------------------

# Maximum rounds to prevent infinite callback loops.
_MAX_TRAMPOLINE_ROUNDS = 20

# Hard cap on total sub-requests per script execution.
_MAX_TOTAL_SUBREQUESTS = 50


def _process_send_queue(ctx: Any) -> None:
    """Drain the ``_send_queue`` by executing HTTP and invoking JS callbacks.

    After the user script completes, any calls to ``pm.sendRequest()``
    have queued entries in ``__pm_state._send_queue``.  For each entry
    we execute the HTTP request in Python, then call back into V8 with
    the response via ``__pm_fulfill_send()``.  Callbacks may enqueue
    further requests, so we loop until the queue is empty.

    Hard cap of ``_MAX_TOTAL_SUBREQUESTS`` prevents abuse even if the
    JS-side rate limit is bypassed.
    """
    from services.scripting.context import execute_sub_request

    total = 0

    for _ in range(_MAX_TRAMPOLINE_ROUNDS):
        queue_json = ctx.eval("JSON.stringify(__pm_state._send_queue)")
        queue: list[dict[str, Any]] = json.loads(queue_json)
        if not queue:
            break

        # Clear the queue before processing — callbacks may push new items.
        ctx.eval("__pm_state._send_queue = []")

        for item in queue:
            total += 1
            if total > _MAX_TOTAL_SUBREQUESTS:
                ctx.eval(
                    "__pm_state.console_logs.push({level:'error',"
                    "message:'[Script] pm.sendRequest total limit exceeded',"
                    "timestamp:Date.now()/1000});"
                )
                return

            spec = item.get("spec", {})

            # Validate callback index — reject non-integer values to
            # prevent JS injection via crafted queue entries.
            try:
                idx = int(item.get("callbackIndex", -1))
            except (TypeError, ValueError):
                continue

            # Log the sub-request (use json.dumps for safe string encoding).
            url = str(spec.get("url", ""))
            method = str(spec.get("method", "GET"))
            log_msg = json.dumps(f'[Script] pm.sendRequest("{method} {url}")')
            ctx.eval(
                f"__pm_state.console_logs.push({{level:'log',"
                f"message:{log_msg},"
                f"timestamp:Date.now()/1000}});"
            )

            resp = execute_sub_request(spec)
            resp_json = json.dumps(resp)

            # Pass response object directly — json.dumps with
            # ensure_ascii=True (default) produces valid JS literals.
            ctx.eval(f"__pm_fulfill_send({idx}, {resp_json})")
