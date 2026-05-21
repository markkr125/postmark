"""Identify pausable top-level statement lines for the step debugger.

Pure parsing helper — used by the editor's breakpoint gutter (B2).
"""

from __future__ import annotations

import ast
from typing import Any


def find_top_level_statement_lines(source: str, language: str) -> set[int]:
    """Return 0-based line numbers the step-debugger can pause on.

    Walks the full AST (Python) or Esprima tree (JS/TS) recursively so
    breakpoints inside ``try``/``if``/``for``/``while``/``with``/function
    bodies / ``pm.test`` callbacks are still considered reachable. The code
    editor renders breakpoints on lines outside this set with a muted style.

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
        from services.scripting.esprima_deno import esprima_parse_to_dict

        result = esprima_parse_to_dict(source)
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
                node_type.endswith("Statement") or node_type.endswith("Declaration")
            ):
                loc = (node.get("loc") or {}).get("start") or {}
                line1 = int(loc.get("line", 0))
                if line1 > 0:
                    out_js.add(line1 - 1)
            for value in node.values():
                if isinstance(value, dict | list):
                    _walk_js(value)

        _walk_js(tree.get("body"))
        return out_js
    return set()
