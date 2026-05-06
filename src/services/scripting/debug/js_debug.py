"""JavaScript debug helpers: grouping, ``let``/``const`` rewrite, and variable reads.

Step-through runs in :mod:`deno_debug` (Deno + Chrome DevTools protocol).
This module keeps the pure-Python statement splitter, regex
``const``/``let``  ``var`` at line starts, and the ``__pm_baseline`` / IIFE
string used to snapshot ``pm`` + new ``globalThis`` names for the
debugger panel.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.scripting import ScriptInput, ScriptOutput
    from services.scripting.debug.protocol import DebugProtocol

logger = logging.getLogger(__name__)

_LET_CONST_LINE_RE = re.compile(r"(?m)^([ \t]*)(const|let)\b")


def inject_checkpoints(source: str) -> str:
    """Insert ``__pm_checkpoint(N, stateJson)`` before each non-empty line.

    *N* is the 0-based line index in the **original** source so that
    breakpoint line numbers map directly to the editor.

    .. note::
       Retained for tests; step-through now uses the Deno inspector
       (:mod:`deno_debug`).
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


def _transform_let_const_regex_fallback(source: str) -> str:
    """Last-resort: line-anchored ``const``/``let`` → ``var`` (can misfire in edge cases)."""
    return _LET_CONST_LINE_RE.sub(r"\1var", source)


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
    in_block_comment = False

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
        code_for_braces, in_block_comment = _strip_comments_for_brace_count(
            line,
            in_block_comment,
        )
        depth += code_for_braces.count("{") - code_for_braces.count("}")

        # Never flush mid-block-comment: the next line is still inside
        # the comment and must be appended to the same group so the
        # whole /* ... */ span reaches ctx.eval as one valid unit.
        if depth <= 0 and not in_block_comment:
            groups.append((group_start, "\n".join(current)))
            current = []
            depth = 0

    # Flush any trailing group (e.g. unclosed brace).
    if current:
        groups.append((group_start, "\n".join(current)))

    return groups


def _strip_comments_for_brace_count(line: str, in_block_comment: bool) -> tuple[str, bool]:
    """Strip JS line/block comments from *line* while preserving string literals."""
    out: list[str] = []
    i = 0
    n = len(line)
    quote: str | None = None
    escaped = False
    while i < n:
        ch = line[i]
        nxt = line[i + 1] if i + 1 < n else ""

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if quote is not None:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            i += 1
            continue

        if ch in ("'", '"', "`"):
            quote = ch
            out.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "/":
            break
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue

        out.append(ch)
        i += 1
    return "".join(out), in_block_comment


def read_locals_from_iife_json_string(s: str) -> dict[str, Any]:
    """Parse the JSON from :data:`_READ_JS_DEBUG_VARS` (plain string, not the CDP wrapper)."""
    try:
        out: dict[str, Any] = json.loads(s)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "pm": {},
            "globals": {},
            "env_changes": {},
            "global_changes": {},
        }
    if isinstance(out.get("pm"), dict) and isinstance(out.get("globals"), dict):
        return {
            "pm": out["pm"],
            "globals": out["globals"],
            "env_changes": out.get("env_changes")
            if isinstance(out.get("env_changes"), dict)
            else {},
            "global_changes": out.get("global_changes")
            if isinstance(out.get("global_changes"), dict)
            else {},
        }
    return {
        "pm": {},
        "globals": {},
        "env_changes": {},
        "global_changes": {},
    }


def debug_execute(
    script: str,
    context: ScriptInput,
    protocol: DebugProtocol,
    *,
    script_type: str = "pre_request",
    source_name: str = "",
    language: str = "javascript",
) -> ScriptOutput:
    """Delegate to :func:`deno_debug.debug_execute` (Deno + V8 inspector)."""
    from .deno_debug import debug_execute as d

    return d(
        script,
        context,
        protocol,
        script_type=script_type,
        source_name=source_name,
        language=language,
    )


_READ_JS_DEBUG_VARS = r"""(function() {
  try {
    var baselineJson = (
      typeof globalThis !== "undefined" && typeof globalThis.__pm_baseline_json === "string"
    )
      ? globalThis.__pm_baseline_json
      : (typeof __pm_baseline_json !== "undefined" ? __pm_baseline_json : "[]");
    var baseList = JSON.parse(baselineJson);
    var base = Object.create ? Object.create(null) : {};
    for (var bi = 0; bi < baseList.length; bi++) {
      base[baseList[bi]] = 1;
    }
    var g = {};
    var names = Object.getOwnPropertyNames(globalThis);
    for (var j = 0; j < names.length; j++) {
      var k = names[j];
      if (base[k]) { continue; }
      try {
        var v = globalThis[k];
        if (v === null) { g[k] = null; }
        else if (typeof v === "function") { g[k] = "[fn]"; }
        else if (typeof v === "object") {
          try { g[k] = JSON.parse(JSON.stringify(v)); } catch (e2) { g[k] = "[object]"; }
        } else { g[k] = v; }
      } catch (e) {
        g[k] = "[unavailable]";
      }
    }
    var st = null;
    if (typeof globalThis !== "undefined" && globalThis.__pm_state) {
      st = globalThis.__pm_state;
    } else if (typeof __pm_state !== "undefined") {
      st = __pm_state;
    }
    var envc = st && st.variable_changes ? st.variable_changes : {};
    var gvc = st && st.global_variable_changes ? st.global_variable_changes : {};
    var pmSnap = {};
    try {
      var pmObj = (typeof globalThis !== "undefined" && globalThis.pm)
        ? globalThis.pm
        : (typeof pm !== "undefined" ? pm : null);
      if (pmObj && pmObj.response) {
        var r = pmObj.response;
        var hdrs = {};
        try {
          if (r.headers && typeof r.headers.toObject === "function") hdrs = r.headers.toObject();
          else if (r.headers && typeof r.headers === "object") hdrs = JSON.parse(JSON.stringify(r.headers));
        } catch (e) { hdrs = {"_error": "[unavailable]"}; }
        var bodyStr = "";
        try { bodyStr = typeof r.text === "function" ? r.text() : (r.body || ""); } catch (e) { bodyStr = ""; }
        if (typeof bodyStr === "string" && bodyStr.length > 500) bodyStr = bodyStr.slice(0, 500) + "…";
        pmSnap = {
          "response.code": r.code,
          "response.status": r.status,
          "response.responseTime": r.responseTime,
          "response.responseSize": r.responseSize,
          "response.headers": hdrs,
          "response.body": bodyStr
        };
      }
    } catch (e) { pmSnap = {}; }
    return JSON.stringify({ "pm": pmSnap, "globals": g, "env_changes": envc, "global_changes": gvc });
  } catch (e) {
    return JSON.stringify({ "pm": {}, "globals": {}, "env_changes": {}, "global_changes": {} });
  }
})()"""


def _read_js_debug_vars(ctx: Any) -> dict[str, Any]:
    """``pm`` environment/collection vars and new ``globalThis`` keys since the baseline.

    On failure, falls back to :func:`_read_js_vars_legacy` (``pm`` + empty ``globals``).
    """
    try:
        raw = ctx.eval(_READ_JS_DEBUG_VARS)
        if raw is None:
            return _read_js_vars_legacy(ctx)
        out: dict[str, Any] = json.loads(str(raw))  # type: ignore[assignment]
        if isinstance(out.get("pm"), dict) and isinstance(out.get("globals"), dict):
            return {
                "pm": out["pm"],
                "globals": out["globals"],
                "env_changes": out.get("env_changes")
                if isinstance(out.get("env_changes"), dict)
                else {},
                "global_changes": out.get("global_changes")
                if isinstance(out.get("global_changes"), dict)
                else {},
            }
    except Exception:
        pass
    return _read_js_vars_legacy(ctx)


def _read_js_vars_legacy(ctx: Any) -> dict[str, Any]:
    """Read ``variable_changes`` / ``global_variable_changes`` when the full IIFE fails."""
    try:
        ec_raw = ctx.eval("JSON.stringify(__pm_state.variable_changes || {})")
        gc_raw = ctx.eval("JSON.stringify(__pm_state.global_variable_changes || {})")
        ec: dict[str, Any] = json.loads(str(ec_raw))  # type: ignore[assignment]
        gc: dict[str, Any] = json.loads(str(gc_raw))  # type: ignore[assignment]
        return {"pm": {}, "globals": {}, "env_changes": ec, "global_changes": gc}
    except Exception:
        return {"pm": {}, "globals": {}, "env_changes": {}, "global_changes": {}}


def _cdp_remote_object_string(ro: dict[str, Any]) -> str:
    """String payload from a CDP ``Runtime.RemoteObject``-shaped dict."""
    v = ro.get("value")
    if isinstance(v, str):
        return v
    desc = ro.get("description")
    if isinstance(desc, str):
        return desc
    return str(ro)


def cdp_evaluation_result_string(res: Any) -> str:
    """String value from a CDP ``*evaluate*`` response (``result.result`` RemoteObject)."""
    if not isinstance(res, dict):
        return str(res) if res else ""
    inner = res.get("result")
    if isinstance(inner, dict):
        return _cdp_remote_object_string(inner)
    return _cdp_remote_object_string(res)


CDP_RUNTIME_VARIABLE_CHANGES_JSON = (
    'JSON.stringify((typeof globalThis!=="undefined"&&globalThis.__pm_state&&'
    "globalThis.__pm_state.variable_changes)||{})"
)
CDP_RUNTIME_GLOBAL_CHANGES_JSON = (
    'JSON.stringify((typeof globalThis!=="undefined"&&globalThis.__pm_state&&'
    "globalThis.__pm_state.global_variable_changes)||{})"
)


def cdp_runtime_evaluate_json_object(cdp_client: Any, expression: str) -> dict[str, Any]:
    """Run ``Runtime.evaluate`` on *cdp_client* and parse a JSON-object string result."""
    try:
        out = cdp_client.req(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True},
        )
    except (OSError, TypeError, KeyError, json.JSONDecodeError):
        return {}
    if not isinstance(out, dict):
        return {}
    raw = cdp_evaluation_result_string(out)
    try:
        parsed: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
