"""Compile declarative assertion rows into executable ``pm.test`` scripts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

Operator = Literal[
    "eq",
    "ne",
    "gt",
    "lt",
    "contains",
    "matches",
    "exists",
    "is_type",
]

VALID_OPERATORS: frozenset[str] = frozenset(
    {"eq", "ne", "gt", "lt", "contains", "matches", "exists", "is_type"}
)

# Common response-header names offered as ``res.headers[...]`` subject suggestions.
_COMMON_HEADER_NAMES: tuple[str, ...] = (
    "Content-Type",
    "Content-Length",
    "Cache-Control",
    "ETag",
    "Location",
    "Set-Cookie",
    "Authorization",
    "Date",
    "Server",
    "Access-Control-Allow-Origin",
)

# Ordered subject suggestions for the Assertions tab auto-complete. Covers every
# subject kind accepted by :func:`_parse_subject` (status, time, body, JSON path
# prefix, and common headers).
SUBJECT_SUGGESTIONS: tuple[str, ...] = (
    "res.status",
    "res.time",
    "res.body",
    "res.body.",
    *tuple(f'res.headers["{name}"]' for name in _COMMON_HEADER_NAMES),
)

_HEADER_SUBJECT_RE = re.compile(
    r"""^res\.headers(?:\["([^"]+)"\]|\.([A-Za-z0-9_-]+))$""",
)


def _json_path_expr(base: str, path: str, *, lang: str) -> str:
    """Build a nested accessor for a lodash-style dot/bracket path."""
    parts = [part for part in path.split(".") if part]
    expr = base
    for part in parts:
        bracket = part.startswith("[") and part.endswith("]")
        if bracket:
            index = part[1:-1]
            if lang == "js":
                expr += f"[{index}]"
            else:
                expr += f"[{index!r}]"
            continue
        if part.isdigit():
            expr += f"[{part}]"
            continue
        if lang == "js":
            expr += f".{part}"
        else:
            expr += f"[{part!r}]"
    return expr


@dataclass(frozen=True)
class _ParsedSubject:
    """Normalised subject selector for code generation."""

    kind: Literal["status", "time", "body", "json_path", "header"]
    path: str = ""
    header_name: str = ""


def _parse_subject(subject: str) -> _ParsedSubject | None:
    """Parse a declarative subject string into a structured selector."""
    raw = subject.strip()
    if raw == "res.status":
        return _ParsedSubject(kind="status")
    if raw == "res.time":
        return _ParsedSubject(kind="time")
    if raw == "res.body":
        return _ParsedSubject(kind="body")
    if raw.startswith("res.body."):
        return _ParsedSubject(kind="json_path", path=raw[len("res.body.") :])
    match = _HEADER_SUBJECT_RE.match(raw)
    if match:
        name = match.group(1) or match.group(2) or ""
        if name:
            return _ParsedSubject(kind="header", header_name=name)
    return None


def _parse_expected(expected: str) -> Any:
    """Parse stored expected text; fall back to raw string when not JSON."""
    text = expected.strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return expected


def _js_literal(value: Any) -> str:
    """Render *value* as a JavaScript literal."""
    return json.dumps(value, ensure_ascii=False)


def _py_literal(value: Any) -> str:
    """Render *value* as a Python literal."""
    return repr(value)


def _test_title(subject: str, operator: str, expected: str) -> str:
    """Build a human-readable ``pm.test`` name."""
    if operator == "exists":
        return f"{subject} exists"
    if operator == "is_type":
        return f"{subject} is {expected or 'type'}"
    op_labels = {
        "eq": "equals",
        "ne": "does not equal",
        "gt": "is above",
        "lt": "is below",
        "contains": "contains",
        "matches": "matches",
    }
    label = op_labels.get(operator, operator)
    return f"{subject} {label} {expected}".strip()


def _js_assertion(parsed: _ParsedSubject, operator: str, expected: str) -> str:
    """Return the inner assertion expression for JavaScript."""
    value = _parse_expected(expected)
    if parsed.kind == "status":
        expr = "pm.response.code"
    elif parsed.kind == "time":
        expr = "pm.response.responseTime"
    elif parsed.kind == "body":
        expr = "pm.response.text()"
    elif parsed.kind == "header":
        header = json.dumps(parsed.header_name)
        if operator == "exists":
            return f"pm.response.to.have.header({header})"
        if operator == "eq":
            return f"pm.response.to.have.header({header}, {_js_literal(value)})"
        if operator == "ne":
            return f"pm.expect(pm.response.headers[{header}]).to.not.equal({_js_literal(value)})"
        if operator == "contains":
            return f"pm.expect(pm.response.headers[{header}]).to.include({_js_literal(value)})"
        if operator == "matches":
            return f"pm.expect(pm.response.headers[{header}]).to.match(/{expected}/)"
        expr = f"pm.response.headers[{header}]"
    elif parsed.kind == "json_path":
        path = json.dumps(parsed.path)
        js_expr = _json_path_expr("pm.response.json()", parsed.path, lang="js")
        if operator == "exists":
            return f"pm.response.to.have.jsonBody({path})"
        if operator == "eq":
            return f"pm.response.to.have.jsonBody({path}, {_js_literal(value)})"
        if operator == "ne":
            return f"pm.expect({js_expr}).to.not.equal({_js_literal(value)})"
        expr = js_expr
    else:
        msg = f"unsupported subject kind: {parsed.kind}"
        raise ValueError(msg)

    if operator == "eq":
        return f"pm.expect({expr}).to.equal({_js_literal(value)})"
    if operator == "ne":
        return f"pm.expect({expr}).to.not.equal({_js_literal(value)})"
    if operator == "gt":
        return f"pm.expect({expr}).to.be.above({_js_literal(value)})"
    if operator == "lt":
        return f"pm.expect({expr}).to.be.below({_js_literal(value)})"
    if operator == "contains":
        return f"pm.expect({expr}).to.include({_js_literal(value)})"
    if operator == "matches":
        return f"pm.expect({expr}).to.match(/{expected}/)"
    if operator == "exists":
        return f"pm.expect({expr}).to.exist"
    if operator == "is_type":
        type_name = str(value or expected).strip().lower()
        return f"pm.expect({expr}).to.be.a({json.dumps(type_name)})"
    msg = f"unsupported operator: {operator}"
    raise ValueError(msg)


def _py_assertion(parsed: _ParsedSubject, operator: str, expected: str) -> str:
    """Return the inner assertion expression for Python."""
    value = _parse_expected(expected)
    if parsed.kind == "status":
        expr = "pm.response.code"
    elif parsed.kind == "time":
        expr = "pm.response.response_time"
    elif parsed.kind == "body":
        expr = "pm.response.text()"
    elif parsed.kind == "header":
        header = repr(parsed.header_name)
        if operator == "exists":
            return f"pm.response.to.have.header({header})"
        if operator == "eq":
            return f"pm.response.to.have.header({header}, {_py_literal(value)})"
        if operator == "ne":
            return f"pm.expect(pm.response.headers[{header}]).not_.equal({_py_literal(value)})"
        if operator == "contains":
            return f"pm.expect(pm.response.headers[{header}]).to.include({_py_literal(value)})"
        if operator == "matches":
            return f"pm.expect(pm.response.headers[{header}]).to.match(r{expected!r})"
        expr = f"pm.response.headers[{header}]"
    elif parsed.kind == "json_path":
        path = repr(parsed.path)
        py_expr = _json_path_expr("pm.response.json()", parsed.path, lang="py")
        if operator == "exists":
            return f"pm.response.to.have.json_body({path})"
        if operator == "eq":
            return f"pm.response.to.have.json_body({path}, {_py_literal(value)})"
        if operator == "ne":
            return f"pm.expect({py_expr}).not_.equal({_py_literal(value)})"
        expr = py_expr
    else:
        msg = f"unsupported subject kind: {parsed.kind}"
        raise ValueError(msg)

    if operator == "eq":
        return f"pm.expect({expr}).to.equal({_py_literal(value)})"
    if operator == "ne":
        return f"pm.expect({expr}).not_.equal({_py_literal(value)})"
    if operator == "gt":
        return f"pm.expect({expr}).to.be.above({_py_literal(value)})"
    if operator == "lt":
        return f"pm.expect({expr}).to.be.below({_py_literal(value)})"
    if operator == "contains":
        return f"pm.expect({expr}).to.include({_py_literal(value)})"
    if operator == "matches":
        return f"pm.expect({expr}).to.match(r{expected!r})"
    if operator == "exists":
        return f"pm.expect({expr}).to.exist"
    if operator == "is_type":
        type_name = str(value or expected).strip().lower()
        return f"pm.expect({expr}).to.a({type_name!r})"
    msg = f"unsupported operator: {operator}"
    raise ValueError(msg)


def compile_to_js(assertions: list[dict[str, Any]]) -> str:
    """Compile enabled *assertions* into a JavaScript post-response script."""
    lines = ['globalThis.__pm_test_source_name = "declarative";']
    for row in assertions:
        if not row.get("enabled", True):
            continue
        subject = str(row.get("subject", "")).strip()
        operator = str(row.get("operator", "eq")).strip()
        expected = str(row.get("expected", "") or "")
        if not subject or operator not in VALID_OPERATORS:
            continue
        parsed = _parse_subject(subject)
        if parsed is None:
            continue
        title = _test_title(subject, operator, expected)
        inner = _js_assertion(parsed, operator, expected)
        lines.append(f"pm.test({json.dumps(title)}, function() {{ {inner}; }});")
    lines.append("globalThis.__pm_test_source_name = null;")
    return "\n".join(lines)


def compile_to_py(assertions: list[dict[str, Any]]) -> str:
    """Compile enabled *assertions* into a Python post-response script."""
    lines = ['pm._test_source_name = "declarative"']
    for row in assertions:
        if not row.get("enabled", True):
            continue
        subject = str(row.get("subject", "")).strip()
        operator = str(row.get("operator", "eq")).strip()
        expected = str(row.get("expected", "") or "")
        if not subject or operator not in VALID_OPERATORS:
            continue
        parsed = _parse_subject(subject)
        if parsed is None:
            continue
        title = _test_title(subject, operator, expected)
        inner = _py_assertion(parsed, operator, expected)
        lines.append(f"pm.test({title!r}, lambda: ({inner}))")
    lines.append("pm._test_source_name = None")
    return "\n".join(lines)
