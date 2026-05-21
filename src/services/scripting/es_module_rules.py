"""ES module rules for Deno script editors (CommonJS detection, stderr cleanup)."""

from __future__ import annotations

import re
from typing import Any, Literal, TypedDict, cast

# ANSI SGR and related escape sequences (Deno/npm use these on stderr).
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\].*?(?:\x07|\x1b\\)")

# Fallback when Esprima is unavailable (TypeScript, parse failure).
_MODULE_EXPORTS_RE = re.compile(r"\bmodule\s*\.\s*exports\b")
_EXPORTS_DOT_RE = re.compile(r"\bexports\s*\.")
_REQUIRE_CALL_RE = re.compile(r"\brequire\s*\(")


class EsModuleDiagnostic(TypedDict):
    """A single inline-editor diagnostic for ESM vs CommonJS."""

    message: str
    line: int
    column: int
    severity: Literal["error", "warning"]


def strip_ansi(text: str) -> str:
    """Remove terminal colour/ style escape codes from *text*."""
    if not text:
        return ""
    return _ANSI_ESCAPE_RE.sub("", text)


def format_process_stderr(text: str, *, max_len: int = 1200) -> str:
    """Return *text* without ANSI codes, trimmed for UI display."""
    cleaned = strip_ansi(text).replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(cleaned) > max_len:
        cleaned = f"{cleaned[: max_len - 3]}..."
    return cleaned


def _line_col_at(source: str, index: int) -> tuple[int, int]:
    """Return 1-based ``(line, column)`` for a byte offset in *source*."""
    line = source.count("\n", 0, index) + 1
    last_nl = source.rfind("\n", 0, index)
    col = index - last_nl if last_nl >= 0 else index + 1
    return line, col


def _vendor_require_names() -> frozenset[str]:
    """Built-in vendor modules allowed via legacy ``require('name')``."""
    from services.scripting.js_runtime import _REQUIRE_MAP

    return frozenset(_REQUIRE_MAP.keys())


def _diag(
    message: str,
    line: int,
    column: int,
    *,
    severity: Literal["error", "warning"] = "error",
) -> EsModuleDiagnostic:
    return cast(
        EsModuleDiagnostic,
        {"message": message, "line": line, "column": column, "severity": severity},
    )


def _loc_start(node: dict[str, Any]) -> tuple[int, int]:
    loc = (node.get("loc") or {}).get("start") or {}
    return int(loc.get("line", 1)), int(loc.get("column", 0)) + 1


def _is_module_exports_member(node: Any) -> bool:
    if not isinstance(node, dict) or node.get("type") != "MemberExpression":
        return False
    if node.get("computed"):
        return False
    prop = node.get("property") or {}
    obj = node.get("object") or {}
    return (
        prop.get("type") == "Identifier"
        and prop.get("name") == "exports"
        and obj.get("type") == "Identifier"
        and obj.get("name") == "module"
    )


def _is_exports_member(node: Any) -> bool:
    if not isinstance(node, dict) or node.get("type") != "MemberExpression":
        return False
    if node.get("computed"):
        return False
    obj = node.get("object") or {}
    return obj.get("type") == "Identifier" and obj.get("name") == "exports"


def _walk_esprima_tree(tree: object, diags: list[EsModuleDiagnostic]) -> None:
    """Flag CommonJS patterns in an Esprima JSON AST."""
    allowed_requires = _vendor_require_names()

    def visit(node: Any, parent: Any) -> None:
        if not isinstance(node, dict):
            return
        ntype = node.get("type")

        if ntype == "AssignmentExpression":
            left = node.get("left")
            if _is_module_exports_member(left) or _is_exports_member(left):
                line, col = _loc_start(node)
                diags.append(
                    _diag(
                        "CommonJS module.exports / exports.* is not supported in Deno scripts. "
                        "Use ESM: export default { … } or export const name = …",
                        line,
                        col,
                    )
                )

        if ntype == "CallExpression":
            callee = node.get("callee") or {}
            if (
                isinstance(callee, dict)
                and callee.get("type") == "Identifier"
                and callee.get("name") == "require"
            ):
                args = node.get("arguments") or []
                mod_name: str | None = None
                if (
                    args
                    and isinstance(args[0], dict)
                    and args[0].get("type") == "Literal"
                    and isinstance(args[0].get("value"), str)
                ):
                    mod_name = args[0]["value"]
                if mod_name not in allowed_requires:
                    line, col = _loc_start(node)
                    hint = (
                        "Use pm.require('npm:…') or pm.require('local:…'), "
                        "or a built-in vendor require such as require('lodash')."
                    )
                    diags.append(
                        _diag(
                            f"CommonJS require() is not supported for this call. {hint}",
                            line,
                            col,
                        )
                    )

        if ntype == "MemberExpression" and _is_module_exports_member(node):
            # ``module.exports`` in an expression (rare); still invalid in ESM.
            line, col = _loc_start(node)
            diags.append(
                _diag(
                    "CommonJS module.exports is not supported. "
                    "Use ESM: export default { … } or export const name = …",
                    line,
                    col,
                )
            )

        for v in node.values():
            if isinstance(v, dict):
                visit(v, node)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        visit(item, node)

    visit(tree, None)


def _regex_fallback_diagnostics(script: str) -> list[EsModuleDiagnostic]:
    """Best-effort CommonJS detection when Esprima did not run (e.g. TypeScript)."""
    diags: list[EsModuleDiagnostic] = []
    seen: set[tuple[int, str]] = set()

    def add_once(message: str, index: int) -> None:
        line, col = _line_col_at(script, index)
        key = (line, message[:40])
        if key in seen:
            return
        seen.add(key)
        diags.append(_diag(message, line, col))

    for m in _MODULE_EXPORTS_RE.finditer(script):
        add_once(
            "CommonJS module.exports is not supported. "
            "Use ESM: export default { … } or export const name = …",
            m.start(),
        )
    for m in _EXPORTS_DOT_RE.finditer(script):
        add_once(
            "CommonJS exports.* is not supported. "
            "Use ESM: export default { … } or export const name = …",
            m.start(),
        )

    allowed = _vendor_require_names()
    for m in _REQUIRE_CALL_RE.finditer(script):
        start = m.start()
        prefix = script[:start]
        if re.search(r"pm\s*\.\s*$", prefix):
            continue
        # Literal vendor require('lodash') — allow.
        tail = script[m.end() : m.end() + 80]
        lit = re.match(r"""^\s*['"]([^'"]+)['"]""", tail)
        if lit and lit.group(1) in allowed:
            continue
        add_once(
            "CommonJS require() is not supported for this call. "
            "Use pm.require('npm:…') or pm.require('local:…'), "
            "or a built-in vendor require such as require('lodash').",
            start,
        )
    return diags


def es_module_to_lsp_diagnostics(script: str, language: str) -> list[Any]:
    """Return :class:`~services.lsp.client.Diagnostic` rows for the Problems tab."""
    from services.lsp.client import Diagnostic
    from services.scripting.engine import ScriptLinter

    lang = (language or "javascript").lower()
    if lang not in ("javascript", "typescript") or not (script or "").strip():
        return []
    rows: list[Diagnostic] = []
    for d in ScriptLinter.check_es_module(script, lang):
        line0 = max(0, int(d["line"]) - 1)
        col0 = max(0, int(d["column"]) - 1)
        rows.append(
            Diagnostic(
                line=line0,
                column=col0,
                end_line=line0,
                end_column=col0 + 1,
                severity=str(d.get("severity", "error")),
                message=str(d["message"]),
                source="postmark",
            )
        )
    return rows


_CJS_ESM_SYNTAX_RE = re.compile(r"^\s*(import|export)\b", re.MULTILINE)


def collect_commonjs_esm_syntax_warnings(script: str) -> list[EsModuleDiagnostic]:
    """Warn when ``import`` / ``export`` appear in a local CommonJS (``.cjs``) body."""
    if not script or not script.strip():
        return []
    diags: list[EsModuleDiagnostic] = []
    for m in _CJS_ESM_SYNTAX_RE.finditer(script):
        line = script.count("\n", 0, m.start()) + 1
        last_nl = script.rfind("\n", 0, m.start())
        col = m.start() - last_nl if last_nl >= 0 else m.start() + 1
        diags.append(
            _diag(
                "import/export is not valid in CommonJS local scripts; use module.exports instead.",
                line,
                col,
                severity="warning",
            )
        )
    return diags


def collect_es_module_diagnostics(
    script: str,
    language: str,
    *,
    parse_result: dict[str, Any] | None = None,
) -> list[EsModuleDiagnostic]:
    """Return CommonJS / ESM diagnostics for *script* (javascript or typescript)."""
    if not script or not script.strip():
        return []
    lang = (language or "javascript").lower()
    if lang not in ("javascript", "typescript"):
        return []

    diags: list[EsModuleDiagnostic] = []
    if (
        lang == "javascript"
        and parse_result
        and parse_result.get("ok")
        and parse_result.get("tree")
    ):
        _walk_esprima_tree(parse_result["tree"], diags)
        return diags
    return _regex_fallback_diagnostics(script)
