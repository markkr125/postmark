"""PM API linter helpers — shared between Python and JS lint paths.

Pure functions. Called from :mod:`services.scripting.engine` inside
:class:`ScriptLinter`.
"""

from __future__ import annotations

import ast
from typing import Any, Literal, TypedDict, cast

from services.scripting.pm_api_schema import lookup as _pm_lookup


class Diagnostic(TypedDict):
    """Single inline diagnostic for script validation."""

    message: str
    line: int
    column: int
    severity: Literal["error", "warning"]


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
    """Append a warning when *path* is unknown or misused on *root*."""
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
