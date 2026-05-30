"""Test discovery: extract pm.test(...) call names and line numbers from script source.

Pure parsing helper — no I/O, no runtime. Used by:
- :mod:`services.scripting.engine` (re-export)
- :class:`ui.widgets.code_editor.editor_widget.CodeEditorWidget` (per-test gutter)
"""

from __future__ import annotations

import ast
import re
from typing import Any


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
        from services.scripting.esprima_deno import esprima_parse_to_dict

        result = esprima_parse_to_dict(source)
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
