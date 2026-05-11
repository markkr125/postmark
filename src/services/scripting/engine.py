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
import re
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast

from services.scripting.deno_runtime import DenoRuntime
from services.scripting.pm_api_schema import lookup as _pm_lookup
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


class Diagnostic(TypedDict):
    """A static issue in a script (syntax or API misuse)."""

    message: str
    line: int
    column: int
    severity: Literal["error", "warning"]


class ScriptLinter:
    """Lightweight syntax + pm-API checker for JavaScript and Python scripts."""

    @classmethod
    def shutdown(cls) -> None:
        """No-op: Esprima runs in a short-lived ``deno run`` process (no cached V8)."""
        _ = cls

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
            return []
        return cls._check_javascript(script)

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
        result = cls._esprima_parse_result(script)
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


# ---- pm API helpers ---------------------------------------------------


def _py_unwrap_attr(node: ast.Attribute) -> tuple[str, list[str]]:
    """For `pm.a.b.c` return ``("pm", ["a", "b", "c"])``.

    If the root is not a :class:`ast.Name`, return ``("", [])``.
    """
    parts: list[str] = [node.attr]
    cur: ast.AST = node.value
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.reverse()
        return cur.id, parts
    return "", []


def _emit_pm_diag(
    diags: list[Diagnostic],
    root: str,
    path: list[str],
    is_call: bool,
    line: int,
    col: int,
) -> None:
    if not path:
        return
    node = _pm_lookup(root, path)
    if node is None:
        diags.append(
            cast(
                Diagnostic,
                {
                    "message": f"Unknown property `{path[-1]}` on `{root}`",
                    "line": line,
                    "column": col,
                    "severity": "warning",
                },
            )
        )
        return
    kind = node.get("kind")
    if is_call and kind in ("namespace", "scope"):
        diags.append(
            cast(
                Diagnostic,
                {
                    "message": f"`{root}.{'.'.join(path)}` is a {kind}, not a function",
                    "line": line,
                    "column": col,
                    "severity": "warning",
                },
            )
        )


def _js_walk_for_pm(tree: object, diags: list[Diagnostic]) -> None:
    """Walk an Esprima JSON AST, flag bad pm.*/postman.* access."""

    def visit(node: Any, parent: Any) -> None:
        if not isinstance(node, dict):
            return
        ntype = node.get("type")
        if ntype == "MemberExpression" and not (
            isinstance(parent, dict)
            and parent.get("type") == "MemberExpression"
            and parent.get("object") == node
        ):
            path: list[str] = []
            cur: Any = node
            while isinstance(cur, dict) and cur.get("type") == "MemberExpression":
                if cur.get("optional"):
                    path = []
                    break
                if cur.get("computed"):
                    path = []
                    break
                prop = cur.get("property") or {}
                if prop.get("type") != "Identifier":
                    path = []
                    break
                path.append(str(prop.get("name", "")))
                cur = cur.get("object") or {}
            if path and isinstance(cur, dict) and cur.get("type") == "Identifier":
                root_name = str(cur.get("name", ""))
                if root_name in ("pm", "postman"):
                    path.reverse()
                    is_call = bool(
                        isinstance(parent, dict)
                        and parent.get("type") == "CallExpression"
                        and parent.get("callee") == node
                    )
                    loc = (node.get("loc") or {}).get("start") or {}
                    line = int(loc.get("line", 1))
                    col0 = int(loc.get("column", 0))
                    # Esprima columns are 0-based
                    _emit_pm_diag(
                        diags,
                        root_name,
                        path,
                        is_call,
                        line,
                        col0 + 1,
                    )
        for v in node.values():
            if isinstance(v, dict):
                visit(v, node)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        visit(item, node)

    visit(tree, None)


def find_pm_tests(source: str, language: str) -> list[dict[str, Any]]:
    """Return ``{"name": str, "line": int}`` (1-based line) for each ``pm.test`` call.

    Used by the script editor gutter for per-test Run/Debug affordances.
    On parse failure, returns an empty list.
    """
    out: list[dict[str, Any]] = []
    if not source or not source.strip():
        return []
    if language == "python":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "test"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "pm"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                out.append({"name": node.args[0].value, "line": node.lineno})
        return out
    if language in ("javascript", "typescript"):
        result = ScriptLinter._esprima_parse_result(source)
        if result and result.get("ok") and result.get("tree") is not None:
            tree = result["tree"]

            def _walk(node: Any) -> None:
                if isinstance(node, dict):
                    if (
                        node.get("type") == "CallExpression"
                        and node.get("callee", {}).get("type") == "MemberExpression"
                        and node.get("callee", {}).get("object", {}).get("name") == "pm"
                        and node.get("callee", {}).get("property", {}).get("name") == "test"
                    ):
                        args = node.get("arguments") or []
                        if (
                            args
                            and args[0].get("type") == "Literal"
                            and isinstance(
                                args[0].get("value"),
                                str,
                            )
                        ):
                            loc = (node.get("loc") or {}).get("start") or {}
                            line = int(loc.get("line", 1))
                            out.append({"name": args[0]["value"], "line": line})
                    for v in node.values():
                        _walk(v)
                elif isinstance(node, list):
                    for v in node:
                        _walk(v)

            _walk(tree)
            return out
        pat = re.compile(r"""\bpm\s*\.\s*test\s*\(\s*['"]([^'"]+)['"]""")
        for m in pat.finditer(source):
            line = source.count("\n", 0, m.start()) + 1
            out.append({"name": m.group(1), "line": line})
        return out
    return []


def find_top_level_statement_lines(source: str, language: str) -> set[int]:
    """Return 0-based line numbers the step-debugger can pause on.

    Walks the full AST (Python) or Esprima tree (JS/TS) recursively so
    breakpoints inside ``try``/``if``/``for``/``while``/``with``/function
    bodies / ``pm.test`` callbacks are still considered reachable. The code
    editor renders breakpoints on lines outside this set with a muted style.

    Originally collected only ``tree.body`` (the script's top-level
    statements) on the assumption that ``DebugProtocol.checkpoint`` only
    fires at top-level boundaries. That stopped being true once V8's
    ``Debugger.setBreakpointByUrl`` and Python's ``sys.settrace`` started
    pausing at any executable line, but the function wasn't updated — so
    every breakpoint inside a wrapping ``try:`` rendered as unreachable
    even though it fired correctly.

    An **empty** set means the UI should not apply unreachable styling:
    parse failure, empty source, or an unsupported *language* string.
    """
    if not source or not source.strip():
        return set()
    lang = language.lower()
    if lang == "python":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        out: set[int] = set()
        # ``ast.stmt`` covers regular statements (assign, return, try, …);
        # ``ExceptHandler`` and ``match_case`` carry their own lineno but are
        # not ``stmt`` subclasses — settrace still fires line events for them
        # so their headers should render reachable too.
        keep_nodes: tuple[type, ...] = (ast.stmt, ast.ExceptHandler)
        match_case = getattr(ast, "match_case", None)
        if match_case is not None:
            keep_nodes = (*keep_nodes, match_case)
        for node in ast.walk(tree):
            if not isinstance(node, keep_nodes):
                continue
            line1 = getattr(node, "lineno", 0)
            if line1 > 0:
                out.add(line1 - 1)
        return out
    if lang in ("javascript", "typescript"):
        result = ScriptLinter._esprima_parse_result(source)
        if not result or not result.get("ok") or result.get("tree") is None:
            return set()
        tree = result["tree"]
        if not isinstance(tree, dict):
            return set()
        out_js: set[int] = set()

        def _walk_js(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    _walk_js(item)
                return
            if not isinstance(node, dict):
                return
            node_type = node.get("type")
            if isinstance(node_type, str) and (
                node_type.endswith("Statement")
                or node_type.endswith("Declaration")
            ):
                loc = (node.get("loc") or {}).get("start") or {}
                line1 = int(loc.get("line", 0))
                if line1 > 0:
                    out_js.add(line1 - 1)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    _walk_js(value)

        _walk_js(tree.get("body"))
        return out_js
    return set()
