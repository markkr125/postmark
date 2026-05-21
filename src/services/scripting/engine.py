"""Script execution engine — orchestrates JS and Python runtimes.

Dispatches scripts to the appropriate runtime based on the ``language``
field, and merges outputs from multiple scripts in an inheritance chain.
All methods are ``@staticmethod`` to match the project service pattern.

Also provides :class:`ScriptLinter` for syntax checking and static
``pm``/``postman`` API validation without executing scripts (used by the
inline editor validation).
"""

from __future__ import annotations

import ast
import logging
from typing import TYPE_CHECKING, Any, cast

from services.scripting.deno_runtime import DenoRuntime
from services.scripting.pm_api_linter import (
    Diagnostic,
    _emit_pm_diag,
    _js_walk_for_pm,
    _py_unwrap_attr,
)
from services.scripting.pm_test_finder import find_pm_tests as find_pm_tests
from services.scripting.py_runtime import PyRuntime
from services.scripting.script_breakpoint_analyzer import (
    find_top_level_statement_lines as find_top_level_statement_lines,
)

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
    return DenoRuntime.execute(script, context, language=language)


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
        language=language,
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


class ScriptLinter:
    """Lightweight syntax + pm-API checker for JavaScript and Python scripts."""

    @classmethod
    def shutdown(cls) -> None:
        """No-op: Esprima runs in a short-lived ``deno run`` process (no cached V8)."""
        _ = cls

    @classmethod
    def check_javascript_syntax(cls, script: str) -> list[Diagnostic]:
        """Return Esprima syntax + ``pm`` API diagnostics only (no ESM/CommonJS rules)."""
        if not script or not script.strip():
            return []
        return cls._check_javascript_from_result(cls._esprima_parse_result(script))

    @classmethod
    def check_commonjs_local_script(cls, script: str) -> list[Diagnostic]:
        """Syntax + ``pm`` API for local ``.cjs`` buffers (no ESM rule merge)."""
        from services.scripting.es_module_rules import collect_commonjs_esm_syntax_warnings

        if not script or not script.strip():
            return []
        syntax = cls.check_javascript_syntax(script)
        warnings = cast(list[Diagnostic], collect_commonjs_esm_syntax_warnings(script))
        return _merge_diagnostics(syntax, warnings)

    @classmethod
    def check_es_module(
        cls,
        script: str,
        language: str,
        *,
        parse_result: dict[str, Any] | None = None,
    ) -> list[Diagnostic]:
        """Return ESM vs CommonJS diagnostics (always safe to run alongside LSP)."""
        from services.scripting.es_module_rules import collect_es_module_diagnostics

        if parse_result is None and language == "javascript":
            parse_result = cls._esprima_parse_result(script)
        return cast(
            list[Diagnostic],
            collect_es_module_diagnostics(script, language, parse_result=parse_result),
        )

    @classmethod
    def check(cls, script: str, language: str) -> list[Diagnostic]:
        """Return diagnostics, or an empty list when there are no issues.

        *line* and *column* are 1-based.
        """
        if not script or not script.strip():
            return []
        if language == "python":
            return cls._check_python(script)
        if language == "typescript":
            # TODO: replace with a TS-aware parser. Esprima rejects type
            # annotations, so for now we accept anything syntactically.
            return cast(list[Diagnostic], cls.check_es_module(script, language))
        parse_result = cls._esprima_parse_result(script)
        diags = cls._check_javascript_from_result(parse_result)
        esm = cls.check_es_module(script, language, parse_result=parse_result)
        return _merge_diagnostics(diags, esm)

    # ---- Python ------------------------------------------------------

    @classmethod
    def _check_python(cls, script: str) -> list[Diagnostic]:
        try:
            tree = ast.parse(script)
        except SyntaxError as e:
            return [
                cast(
                    Diagnostic,
                    {
                        "message": e.msg,
                        "line": e.lineno or 1,
                        "column": e.offset or 1,
                        "severity": "error",
                    },
                )
            ]
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                node.func._pm_parent_call = True  # type: ignore[attr-defined]
        diags: list[Diagnostic] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                root, path = _py_unwrap_attr(node)
                if root in ("pm", "postman"):
                    is_call = bool(getattr(node, "_pm_parent_call", False))
                    _emit_pm_diag(
                        diags,
                        root,
                        path,
                        is_call,
                        node.lineno or 1,
                        (node.col_offset or 0) + 1,
                    )
        return diags

    # ---- JavaScript --------------------------------------------------

    @classmethod
    def _esprima_parse_result(cls, script: str) -> dict[str, Any] | None:
        """Run esprima through ``deno run data/scripts/esprima_parse.mjs`` (no MiniRacer)."""
        from services.scripting.esprima_deno import esprima_parse_to_dict

        _ = cls
        return esprima_parse_to_dict(script)

    @classmethod
    def _check_javascript(cls, script: str) -> list[Diagnostic]:
        return cls._check_javascript_from_result(cls._esprima_parse_result(script))

    @classmethod
    def _check_javascript_from_result(cls, result: dict[str, Any] | None) -> list[Diagnostic]:
        if result is None:
            return []
        if not result.get("ok"):
            return [
                cast(
                    Diagnostic,
                    {
                        "message": str(result.get("message", "parse error")),
                        "line": int(result.get("line", 1)),
                        "column": int(result.get("column", 1)),
                        "severity": "error",
                    },
                )
            ]
        diags: list[Diagnostic] = []
        _js_walk_for_pm(result.get("tree"), diags)
        return diags


def _merge_diagnostics(
    primary: list[Diagnostic],
    extra: list[Diagnostic],
) -> list[Diagnostic]:
    """Append *extra* diagnostics, skipping duplicates at the same line/message."""
    if not extra:
        return primary
    seen = {(d["line"], d["message"]) for d in primary}
    out = list(primary)
    for d in extra:
        key = (d["line"], d["message"])
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out
