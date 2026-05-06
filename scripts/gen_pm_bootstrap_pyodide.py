#!/usr/bin/env python3
"""One-off generator: build ``data/scripts/pm_bootstrap.py`` from ``_py_sandbox.py``."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/services/scripting/_py_sandbox.py"
OUT = ROOT / "data/scripts/pm_bootstrap.py"

PREFIX = '''"""Postmark ``pm`` API for Pyodide (loaded by ``pyodide_run.mjs``).

Built from :file:`src/services/scripting/_py_sandbox.py` (shared behaviour, no
``RestrictedPython``).  ``__pm_context_json`` must exist before this module
initialises ``pm``.
"""

'''

SUFFIX = '''

def collect_pm_output() -> dict[str, Any]:
    """Build script output dict (mirrors :func:`_py_sandbox._execute_restricted` tail)."""
    all_changes: dict[str, str] = {}
    for scope in (pm.variables, pm.environment, pm.collection_variables):
        all_changes.update(scope._changes)
    global_changes: dict[str, str] = dict(pm.globals._changes)
    request_mutations: dict[str, Any] | None = None
    if pm._is_pre_request:
        request_mutations = {
            "url": pm.request.url,
            "method": pm.request.method,
            "headers": pm.request.headers,
            "body": pm.request.body,
        }
    logs = list(_console_logs)
    out: dict[str, Any] = {
        "test_results": pm._test_results,
        "console_logs": logs,
        "variable_changes": all_changes,
        "request_mutations": request_mutations,
    }
    if global_changes:
        out["global_variable_changes"] = global_changes
    if pm.execution._next_set:
        out["next_request"] = pm.execution._next
    if pm.execution._skip:
        out["skip_request"] = True
    return out


def _safe_type(obj: object) -> type:
    """Single-argument ``type()`` — blocks metaclass creation via 3-arg form."""
    return type(obj)


def _pm_print(*args: object, **kwargs: object) -> None:
    """Forward ``print()`` to the same capture as RestrictedPython scripts."""
    _console_emit("log", *args)


# fmt: off
_SAFE_BUILTINS: dict[str, Any] = {
    "True": True, "False": False, "None": None,
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "filter": filter, "float": float, "int": int,
    "isinstance": isinstance, "len": len, "list": list, "map": map,
    "max": max, "min": min, "print": _pm_print, "range": range, "reversed": reversed,
    "round": round, "set": set, "sorted": sorted, "str": str,
    "sum": sum, "tuple": tuple, "type": _safe_type, "zip": zip,
}
# fmt: on

# fmt: off
_SAFE_STDLIB: dict[str, Any] = {
    "json_loads": json.loads, "json_dumps": json.dumps,
    "re_match": re.match, "re_search": re.search,
    "re_findall": re.findall, "re_sub": re.sub,
    "math_ceil": math.ceil, "math_floor": math.floor,
    "math_sqrt": math.sqrt, "math_pow": math.pow, "math_log": math.log,
    "math_pi": math.pi, "math_e": math.e,
    "b64encode": b64encode, "b64decode": b64decode,
    "hashlib_md5": lambda d: md5(d.encode() if isinstance(d, str) else d).hexdigest(),
    "hashlib_sha256": lambda d: sha256(d.encode() if isinstance(d, str) else d).hexdigest(),
    "hashlib_hmac_sha256": lambda d, k: hmac.new(
        k.encode() if isinstance(k, str) else k,
        d.encode() if isinstance(d, str) else d,
        "sha256",
    ).hexdigest(),
    "uuid_v4": lambda: str(uuid.uuid4()),
    "datetime_now": lambda: datetime.now(tz=UTC).isoformat(),
    "datetime_utcnow": lambda: datetime.now(tz=UTC).isoformat(),
    "url_quote": quote, "url_urlencode": urlencode,
}
# fmt: on


def init_pm() -> None:
    """Parse ``__pm_context_json`` and set ``pm``."""
    global pm
    ctx: dict[str, Any] = json.loads(__pm_context_json)
    globals()["pm"] = _Pm(ctx)


def run_user_script(src: str) -> None:
    """Execute user *src* with the same globals shape as the RestrictedPython path."""
    g: dict[str, Any] = {}
    g.update(_SAFE_BUILTINS)
    g["__builtins__"] = _SAFE_BUILTINS
    g["pm"] = pm
    g.update(_SAFE_STDLIB)
    exec(compile(src, "<script>", "exec"), g, g)
'''


OLD_SEND = '''    def send_request(self, spec: Any, callback: Any = None) -> Any:
        """Execute sub-request via IPC to the parent process."""
        if self._send_count >= 10:
            msg = "pm.sendRequest rate limit exceeded (max 10)"
            raise RuntimeError(msg)
        self._send_count += 1
        req_spec: dict[str, Any] = (
            {"url": spec, "method": "GET"} if isinstance(spec, str) else dict(spec)
        )
        _console_emit(
            "log",
            f'[Script] pm.sendRequest("{req_spec.get("method", "GET")} {req_spec.get("url", "")}")',
        )
        sys.stdout.write(json.dumps({"__ipc__": "sendRequest", "spec": req_spec}) + "\\n")
        sys.stdout.flush()
        resp_line = sys.stdin.readline()
        if not resp_line:
            msg = "No IPC response received"
            raise RuntimeError(msg)
        resp: dict[str, Any] = json.loads(resp_line)
        if callback:
            callback(resp.get("error"), resp)
        return resp'''

NEW_SEND = '''    def send_request(self, spec: Any, callback: Any = None) -> Any:
        """Execute sub-request via IPC to the Deno parent (``postmark_ipc``)."""
        if self._send_count >= 10:
            msg = "pm.sendRequest rate limit exceeded (max 10)"
            raise RuntimeError(msg)
        self._send_count += 1
        req_spec: dict[str, Any] = (
            {"url": spec, "method": "GET"} if isinstance(spec, str) else dict(spec)
        )
        _console_emit(
            "log",
            f'[Script] pm.sendRequest("{req_spec.get("method", "GET")} {req_spec.get("url", "")}")',
        )
        import postmark_ipc

        raw = postmark_ipc.send_request_sync(json.dumps(req_spec))
        resp: dict[str, Any] = json.loads(raw)
        if callback:
            callback(resp.get("error"), resp)
        return resp

    def require(self, spec: str) -> Any:
        """Import a package pre-installed by micropip (``name`` or ``name==version``)."""
        import importlib

        name_part = spec.split("==", 1)[0].strip().lower()
        candidates = [name_part.replace("-", "_"), name_part]
        last_err: Exception | None = None
        for mod in candidates:
            try:
                return importlib.import_module(mod)
            except Exception as e:
                last_err = e
                continue
        msg = f"pm.require({spec!r}): could not import (tried {candidates}): {last_err}"
        raise RuntimeError(msg) from last_err'''


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    for i, line in enumerate(lines):
        n = i + 1
        # Keep stdlib imports through ``hashlib`` (line 28); skip RestrictedPython
        # and resource limits (29--55); keep console capture (56--71) and
        # ``_VariableScope`` through ``_Pm`` (81--522).
        if n <= 28 or (56 <= n <= 71) or (81 <= n <= 522):
            kept.append(line)
    body = "\n".join(kept)
    body = re.sub(r'^"""[\s\S]*?"""\n\n', "", body, count=1)
    if OLD_SEND not in body:
        raise SystemExit("send_request block not found in excerpt")
    body = body.replace(OLD_SEND, NEW_SEND)
    OUT.write_text(PREFIX + body + SUFFIX, encoding="utf-8", newline="\n")
    print("Wrote", OUT, "lines", len(OUT.read_text().splitlines()))


if __name__ == "__main__":
    main()
