"""Script execution engine — orchestrates JS and Python runtimes.

Dispatches scripts to the appropriate runtime based on the ``language``
field, and merges outputs from multiple scripts in an inheritance chain.
All methods are ``@staticmethod`` to match the project service pattern.

Also provides :class:`ScriptLinter` for lightweight syntax checking
without executing scripts (used by the inline editor validation).
"""

from __future__ import annotations

import ast
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from services.scripting.js_runtime import JSRuntime
from services.scripting.py_runtime import PyRuntime

if TYPE_CHECKING:
    from services.scripting import ScriptEntry, ScriptInput, ScriptOutput
    from services.scripting.debug import DebugProtocol

logger = logging.getLogger(__name__)


def _empty_output() -> ScriptOutput:
    """Return an empty ``ScriptOutput`` dict."""
    return {
        "test_results": [],
        "console_logs": [],
        "variable_changes": {},
        "request_mutations": None,
    }


class ScriptEngine:
    """Orchestrate script execution across runtimes.

    Runs ordered script chains (pre-request or test) and merges their
    outputs into a single :class:`ScriptOutput`.
    """

    @staticmethod
    def run_pre_request_scripts(
        chain: list[ScriptEntry],
        context: ScriptInput,
    ) -> ScriptOutput:
        """Run pre-request scripts in top-down order.

        *chain* is ordered collection → folder → request.  Variable
        changes from earlier scripts propagate to later ones.
        """
        return _run_chain(chain, context)

    @staticmethod
    def run_test_scripts(
        chain: list[ScriptEntry],
        context: ScriptInput,
    ) -> ScriptOutput:
        """Run test scripts in bottom-up order.

        *chain* is ordered request → folder → collection.  Variable
        changes from earlier scripts propagate to later ones.
        """
        return _run_chain(chain, context)

    @staticmethod
    def run_single(
        script: str,
        language: str,
        context: ScriptInput,
    ) -> ScriptOutput:
        """Run a single script without chain merging."""
        if not script or not script.strip():
            return _empty_output()
        return _dispatch(script, language, context)


def _run_chain(chain: list[ScriptEntry], context: ScriptInput) -> ScriptOutput:
    """Execute each script in *chain*, merging outputs sequentially."""
    merged = _empty_output()

    for entry in chain:
        code = entry.get("code", "")
        if not code or not code.strip():
            continue

        language = entry.get("language", "javascript")
        source = entry.get("source_name", "")

        logger.info("Running %s script from %s", language, source)

        result = _dispatch(code, language, context)

        # Tag runtime errors with the source name so the UI can
        # show which inherited script caused the failure.
        for tr in result.get("test_results", []):
            if tr.get("name") == "(runtime error)" and source:
                tr["source_name"] = source

        # Merge results.
        merged["test_results"].extend(result.get("test_results", []))
        merged["console_logs"].extend(result.get("console_logs", []))

        # Accumulate variable changes (later scripts override earlier).
        changes = result.get("variable_changes", {})
        merged["variable_changes"].update(changes)

        # Accumulate global variable changes.
        global_changes = result.get("global_variable_changes", {})
        if global_changes:
            if "global_variable_changes" not in merged:
                merged["global_variable_changes"] = {}
            merged["global_variable_changes"].update(global_changes)

        # Propagate variable changes to the next script's context.
        if changes:
            updated_vars = dict(context.get("variables", {}))
            updated_vars.update(changes)
            context = {**context, "variables": updated_vars}

        # Propagate global changes to the next script's context.
        if global_changes:
            updated_globals = dict(context.get("global_vars", {}))
            updated_globals.update(global_changes)
            context = {**context, "global_vars": updated_globals}

        # Only keep request mutations from the last script that sets them.
        if result.get("request_mutations"):
            merged["request_mutations"] = result["request_mutations"]

        # Keep execution flow control (last script wins).
        if "next_request" in result:
            merged["next_request"] = result["next_request"]
        if result.get("skip_request"):
            merged["skip_request"] = True

    return merged


def _dispatch(script: str, language: str, context: ScriptInput) -> ScriptOutput:
    """Route a script to the correct runtime."""
    if language == "python":
        return PyRuntime.execute(script, context)
    return JSRuntime.execute(script, context)


def _debug_dispatch(
    script: str,
    language: str,
    context: ScriptInput,
    protocol: DebugProtocol,
    *,
    script_type: str = "pre_request",
    source_name: str = "",
) -> ScriptOutput:
    """Route a script to the correct debug runtime."""
    from services.scripting.debug import js_debug_execute, py_debug_execute

    if language == "python":
        return py_debug_execute(
            script,
            context,
            protocol,
            script_type=script_type,
            source_name=source_name,
        )
    return js_debug_execute(
        script,
        context,
        protocol,
        script_type=script_type,
        source_name=source_name,
    )


def run_debug_chain(
    chain: list[ScriptEntry],
    context: ScriptInput,
    protocol: DebugProtocol,
    *,
    script_type: str = "pre_request",
) -> ScriptOutput:
    """Execute each script in *chain* with debug support."""
    merged = _empty_output()

    for entry in chain:
        code = entry.get("code", "")
        if not code or not code.strip():
            continue

        language = entry.get("language", "javascript")
        source = entry.get("source_name", "")

        logger.info("Debug-running %s script from %s", language, source)

        result = _debug_dispatch(
            code,
            language,
            context,
            protocol,
            script_type=script_type,
            source_name=source,
        )

        merged["test_results"].extend(result.get("test_results", []))
        merged["console_logs"].extend(result.get("console_logs", []))

        changes = result.get("variable_changes", {})
        merged["variable_changes"].update(changes)

        global_changes = result.get("global_variable_changes", {})
        if global_changes:
            if "global_variable_changes" not in merged:
                merged["global_variable_changes"] = {}
            merged["global_variable_changes"].update(global_changes)

        if changes:
            updated_vars = dict(context.get("variables", {}))
            updated_vars.update(changes)
            context = {**context, "variables": updated_vars}

        if global_changes:
            updated_globals = dict(context.get("global_vars", {}))
            updated_globals.update(global_changes)
            context = {**context, "global_vars": updated_globals}

        if result.get("request_mutations"):
            merged["request_mutations"] = result["request_mutations"]

        if "next_request" in result:
            merged["next_request"] = result["next_request"]
        if result.get("skip_request"):
            merged["skip_request"] = True

    return merged


# -- Syntax linter (no execution) --------------------------------------

# V8 line offset: ``new Function(code)`` wraps code in
# ``function anonymous() {\n<code>\n}`` so user line 1 = V8 line 3.
_V8_LINE_OFFSET = 2

# Regex to extract line + message from V8 ``SyntaxError`` exceptions.
_V8_ERROR_RE = re.compile(
    r"^(?:undefined|\S+):(\d+):\s*SyntaxError:\s*(.+)",
    re.MULTILINE,
)


class ScriptLinter:
    """Lightweight syntax checker for JavaScript and Python scripts.

    Performs compile-time validation without executing any code.
    For JavaScript, a single ``MiniRacer`` context is lazily created
    and reused across calls (~0.3 ms per check after first use).
    """

    _js_ctx: Any = None  # Cached MiniRacer instance.

    @classmethod
    def shutdown(cls) -> None:
        """Release the cached V8 context so the process can exit.

        ``MiniRacer`` runs an internal event-loop thread that prevents
        clean shutdown.  Deleting the context stops the thread.
        """
        if cls._js_ctx is not None:
            del cls._js_ctx
            cls._js_ctx = None

    @classmethod
    def check(
        cls,
        script: str,
        language: str,
    ) -> tuple[str, int, int] | None:
        """Return ``(message, line, column)`` or ``None`` if valid.

        *line* and *column* are 1-based.
        """
        if not script or not script.strip():
            return None

        if language == "python":
            return cls._check_python(script)
        return cls._check_javascript(script)

    @staticmethod
    def _check_python(script: str) -> tuple[str, int, int] | None:
        """Validate Python syntax via ``ast.parse()``."""
        try:
            ast.parse(script)
        except SyntaxError as e:
            line = e.lineno or 1
            col = e.offset or 1
            return (e.msg, line, col)
        return None

    @classmethod
    def _check_javascript(cls, script: str) -> tuple[str, int, int] | None:
        """Validate JavaScript syntax via V8 ``new Function()``."""
        try:
            from py_mini_racer import MiniRacer  # type: ignore[import-untyped]
        except ImportError:
            return None

        if cls._js_ctx is None:
            cls._js_ctx = MiniRacer()

        safe = json.dumps(script)
        try:
            cls._js_ctx.eval(f"new Function({safe})")
        except Exception as exc:
            m = _V8_ERROR_RE.search(str(exc))
            if m:
                v8_line = int(m.group(1))
                return (m.group(2), max(1, v8_line - _V8_LINE_OFFSET), 1)
            return (str(exc).splitlines()[0], 1, 1)
        return None
