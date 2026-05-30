"""Deno-based JavaScript script runtime (subprocess).

Replaces the in-process MiniRacer run path.  A bundle is built from
polyfills, required vendor files, :file:`data/scripts/pm_bootstrap.js`,
and the user script, then :file:`data/scripts/deno_drain.mjs` flushes
``pm.sendRequest`` by line-based IPC to Python (see :mod:`py_runtime`).

A valid :class:`services.scripting.runtime_settings.RuntimeSettings.deno_path`
or managed ``PATH`` binary is required; there is no MiniRacer fallback.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import platform
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from services.scripting._subprocess_env import safe_subprocess_env
from services.scripting.js_runtime import (
    append_js_pm_preamble,
    _pm_require_imports_block,
    prepare_pm_require_bundle,
    write_local_modules_to_workdir,
)
from services.scripting.runtime_settings import RuntimeSettings

# ESM: must be the first line of the bundle (before polyfills) so
# data/scripts/deno_drain.mjs can use ``writeSync``/``readSync`` — Deno 2.x
# no longer exposes ``Deno.writeSync``/``Deno.readSync`` on the ``Deno`` object.
_NODE_FS_IMPORT = 'import { readSync, writeSync } from "node:fs";'

if TYPE_CHECKING:
    from services.scripting import ScriptInput, ScriptOutput

logger = logging.getLogger(__name__)

_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "data" / "scripts"
_DENO_DRAIN_FILE = _SCRIPTS_DIR / "deno_drain.mjs"
_SUBPROCESS_TIMEOUT = 10.0

_PM_REQUIRE_NETWORK_HOSTS = ("registry.npmjs.org", "jsr.io", "deno.land")


def _registry_host(url: str) -> str:
    """Extract ``hostname[:port]`` from a registry URL for ``--allow-net``."""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return ""
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return host


def _npmrc_auth_host(url: str) -> str:
    """Return the ``host[:port]/path-prefix`` segment for an ``.npmrc`` auth line.

    Strips any embedded ``user:password@`` so the emitted line is
    ``//host[:port]/...:_authToken=…`` not ``//user:pw@host/...:_authToken=…``
    (which Deno's npm-rc parser rejects). Path prefix is preserved because
    ``.npmrc`` allows scoping auth to a sub-path on the same host.
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return ""
    netloc = parsed.hostname or ""
    if not netloc:
        return ""
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    # Preserve the path prefix (e.g. ``/registry/``) — drop the trailing
    # slash so the ``/`` in the auth line template doesn't double up.
    path = (parsed.path or "").rstrip("/")
    return f"{netloc}{path}" if path else netloc


def _build_npmrc_text() -> tuple[str, list[str]]:
    """Resolve configured private registries into ``.npmrc`` lines + extra hosts.

    Returns ``("", [])`` when no registries are configured. Otherwise returns
    a string suitable for writing to ``<workdir>/.npmrc`` and a list of extra
    ``hostname[:port]`` entries to append to ``--allow-net``.

    Tokens are resolved via :mod:`services.scripting.secret_store` and written
    *as plain text* into the generated ``.npmrc`` (Deno's env-var expansion
    in ``.npmrc`` is documented as unreliable — `supabase/cli#4927` — so we
    do the expansion ourselves and rely on ``chmod 0600`` for protection).
    """
    from services.scripting.runtime_settings import RuntimeSettings
    from services.scripting.secret_store import get_default_store

    entries = RuntimeSettings.get_registries()
    default_url, default_auth_ref, default_auth_kind = RuntimeSettings.get_default_npm_registry()
    if not entries and not default_url:
        return "", []

    store = get_default_store()
    lines: list[str] = []
    hosts: set[str] = set()

    if default_url:
        lines.append(f"registry={default_url}")
        host = _registry_host(default_url)
        if host:
            hosts.add(host)
            if default_auth_ref and default_auth_kind != "none":
                token = store.get(default_auth_ref) or ""
                auth_host = _npmrc_auth_host(default_url)
                if token and auth_host:
                    if default_auth_kind == "basic":
                        # ``_auth=<base64(user:password)>`` for legacy basic-auth
                        # registries (Nexus default realm, older Verdaccio).
                        lines.append(f"//{auth_host}/:_auth={token}")
                    else:
                        # ``_authToken=`` for modern bearer-token registries
                        # (Verdaccio, Cloudsmith, Artifactory, GitHub Packages).
                        lines.append(f"//{auth_host}/:_authToken={token}")

    for entry in entries:
        scope = entry.get("scope", "")
        url = entry.get("url", "")
        if not scope or not url:
            continue
        lines.append(f"{scope}:registry={url}")
        host = _registry_host(url)
        if host:
            hosts.add(host)
        auth_kind = entry.get("auth_kind", "none")
        auth_ref = entry.get("auth_ref", "")
        if auth_kind == "none" or not auth_ref:
            continue
        token_or_basic = store.get(auth_ref) or ""
        if not token_or_basic:
            continue
        auth_host = _npmrc_auth_host(url)
        if not auth_host:
            continue
        if auth_kind == "basic":
            lines.append(f"//{auth_host}/:_auth={token_or_basic}")
        else:
            lines.append(f"//{auth_host}/:_authToken={token_or_basic}")

    return ("\n".join(lines) + "\n" if lines else "", sorted(hosts))


def _postmark_deno_user_cache_dir() -> Path:
    """Return (and create) the per-user Deno cache directory for Postmark."""
    system = platform.system()
    if system == "Linux":
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    p = base / "postmark" / "deno_cache"
    p.mkdir(parents=True, exist_ok=True)
    (p / ".deno_dir").mkdir(exist_ok=True)
    return p


def deno_ipc_argv_and_env(
    deno: Path,
    bundle: Path,
    *,
    needs_net: bool,
    inspect_brk: str | None = None,
    extra_read_paths: tuple[str, ...] = (),
) -> tuple[list[str], dict[str, str]]:
    """Build ``deno run`` argv + env for bundle IPC (permissions + optional inspect)."""
    wdir = bundle.parent
    cache = _postmark_deno_user_cache_dir()
    read_bits = [str(wdir), str(cache), str(_SCRIPTS_DIR), *extra_read_paths]
    read_paths = ",".join(dict.fromkeys(read_bits))
    args: list[str] = [
        str(deno),
        "run",
        "--no-prompt",
        "--no-lock",
        f"--allow-read={read_paths}",
        f"--allow-write={cache}",
    ]
    if needs_net:
        # Drop a per-execution ``.npmrc`` into the bundle workdir so Deno
        # picks up private-registry configuration (scope mappings + auth
        # tokens). Tokens are resolved via the secret store and written in
        # plain text; ``chmod 0600`` keeps the file out of other users'
        # reach. Extra registry hostnames are added to ``--allow-net``.
        npmrc_text, extra_hosts = _build_npmrc_text()
        if npmrc_text:
            npmrc_path = wdir / ".npmrc"
            npmrc_path.write_text(npmrc_text, encoding="utf-8")
            with contextlib.suppress(OSError):
                os.chmod(npmrc_path, 0o600)
        all_hosts = list(_PM_REQUIRE_NETWORK_HOSTS) + [
            h for h in extra_hosts if h not in _PM_REQUIRE_NETWORK_HOSTS
        ]
        args.append(f"--allow-net={','.join(all_hosts)}")
        args.append("--node-modules-dir=auto")
    args.append("--allow-env")
    if inspect_brk:
        args.append(inspect_brk)
    args.append(str(bundle))
    # Minimal env: never forward host secrets to untrusted scripts. Postman
    # {{vars}} travel in the script payload, not the process environment.
    env = safe_subprocess_env({"DENO_DIR": str(cache / ".deno_dir")})
    return args, env


def _empty_output() -> ScriptOutput:
    """Return an empty ``ScriptOutput`` dict."""
    return {
        "test_results": [],
        "console_logs": [],
        "variable_changes": {},
        "request_mutations": None,
    }


def _error_output(msg: str, elapsed_ms: float) -> ScriptOutput:
    """Return a single (runtime error) :class:`ScriptOutput`."""
    o = _empty_output()
    o["test_results"] = [
        {
            "name": "(runtime error)",
            "passed": False,
            "error": msg,
            "duration_ms": elapsed_ms,
        }
    ]
    return cast("ScriptOutput", o)


class DenoRuntime:
    """Run JavaScript scripts in a ``deno run`` subprocess (no in-process V8)."""

    @staticmethod
    def execute(
        script: str,
        context: ScriptInput,
        *,
        language: str = "javascript",
    ) -> ScriptOutput:
        """Build a bundle, run *script* in Deno, return :class:`ScriptOutput`."""
        start = time.monotonic()
        deno = RuntimeSettings.deno_path()
        st = RuntimeSettings.validate_deno(deno)
        if not st["available"]:
            return _error_output(
                "Deno is not available. Open Settings, set the Deno path, or download the "
                "managed runtime. " + (st.get("error") or ""),
                (time.monotonic() - start) * 1000,
            )

        try:
            return _run_bundle(Path(st["path"]), script, context, start, language=language)
        except RuntimeError as exc:
            return _error_output(str(exc), (time.monotonic() - start) * 1000)
        except (OSError, FileNotFoundError) as exc:
            return _error_output(str(exc), (time.monotonic() - start) * 1000)


def _build_bundle_text(
    script: str,
    context: ScriptInput,
    *,
    language: str = "javascript",
) -> tuple[str, bool, dict[str, Any]]:
    """Concatenate bundle text, ``needs_net``, and resolved local modules."""
    from services.scripting.js_runtime import _detect_pm_require_specs

    parts: list[str] = []
    parts.append(_NODE_FS_IMPORT)
    try:
        _union, needs_net, local_mods = prepare_pm_require_bundle(script, language=language)
        specs = _detect_pm_require_specs(_union)
    except ValueError as exc:
        raise RuntimeError(f"Script bundling failed: {exc}") from exc
    parts.append(_pm_require_imports_block(specs, local_mods))
    append_js_pm_preamble(parts, script, context, include_json_schema=True)
    # Trailing ``;`` terminates the last user statement so the appended IIFE
    # (``(function __denoIpcDrain() { ... })``) is never ASI'd onto it as a
    # call (e.g. ``console.log('x')`` + ``(function`` → invalid / TypeError).
    user_tail = script.rstrip()
    _append_user_script_line0(parts)
    parts.append(f"{_USER_SCRIPT_MARKER}{user_tail}\n;\n")
    parts.append(_DENO_DRAIN_FILE.read_text(encoding="utf-8"))
    return "\n".join(parts), needs_net, local_mods


_DEBUG_BASELINE = (
    "var __pm_baseline_json = JSON.stringify(Object.getOwnPropertyNames(globalThis).sort());\n"
    "if (typeof globalThis !== 'undefined') { globalThis.__pm_baseline_json = __pm_baseline_json; }\n"
)

# ``HEAD`` must not end with ``\\n``: ``"\\n".join(parts)`` inserts one newline
# between ``HEAD`` and the user tail; a trailing ``\\n`` on ``HEAD`` would add a
# blank line and break ``user_script_first_line_0_in_debug_bundle`` / breakpoints.
# Wrapper is ``async`` because user scripts may use top-level ``await
# pm.sendRequest(...)`` (Postman-API parity). The outer call is itself
# awaited so the drain code that follows runs **after** the user script
# resolves, otherwise pm.test results queued post-await would be missed.
_USER_SCRIPT_MARKER = "\n// -- user script --\n"
_DEBUG_USER_SCRIPT_HEAD = "\n// -- user script --\nasync function __pm_debugUserScript() {"
_DEBUG_USER_SCRIPT_TAIL = "\n}\nawait __pm_debugUserScript();\n;\n"


def _bundle_line_count(parts: list[str]) -> int:
    """Return the number of lines in the bundle built from *parts* so far."""
    return len("\n".join(parts).splitlines())


def _append_user_script_line0(parts: list[str]) -> None:
    """Append ``var __pm_user_script_line0 = N`` for console stack mapping."""
    parts.append(f"var __pm_user_script_line0 = {_bundle_line_count(parts)};\n")


def build_debug_bundle_text(
    user_script: str,
    context: ScriptInput,
    *,
    language: str = "javascript",
) -> tuple[str, bool, dict[str, Any]]:
    """Same as :func:`_build_bundle_text` but with a ``__pm_baseline_json`` line before the user part."""
    from services.scripting.js_runtime import _detect_pm_require_specs

    parts: list[str] = []
    parts.append(_NODE_FS_IMPORT)
    try:
        _union, needs_net, local_mods = prepare_pm_require_bundle(user_script, language=language)
        specs = _detect_pm_require_specs(_union)
    except ValueError as exc:
        raise RuntimeError(f"Script bundling failed: {exc}") from exc
    parts.append(_pm_require_imports_block(specs, local_mods))
    append_js_pm_preamble(parts, user_script, context, include_json_schema=True)
    parts.append(_DEBUG_BASELINE)
    u_tail = user_script.rstrip()
    _append_user_script_line0(parts)
    parts.append(_DEBUG_USER_SCRIPT_HEAD)
    parts.append(u_tail)
    parts.append(_DEBUG_USER_SCRIPT_TAIL)
    parts.append(_DENO_DRAIN_FILE.read_text(encoding="utf-8"))
    return "\n".join(parts), needs_net, local_mods


def user_script_first_line_0_in_debug_bundle(
    _user_script: str,
    context: ScriptInput,
    *,
    language: str = "javascript",
) -> int:
    """Return 0-based line number in the debug bundle where *user* source starts."""
    text, _needs_net, _local = build_debug_bundle_text(_user_script, context, language=language)
    marker = _DEBUG_USER_SCRIPT_HEAD
    idx = text.find(marker)
    if idx < 0:
        return 0
    user_start = idx + len(marker)
    while user_start < len(text) and text[user_start] in "\r\n":
        user_start += 1
    return text[:user_start].count("\n")


def _apply_done_line(data: dict[str, Any], out: ScriptOutput, context: ScriptInput) -> None:
    """Copy a ``__done__`` line into *out* (same rules as :mod:`js_runtime`)."""
    st = {k: v for k, v in data.items() if k not in ("__done__", "__ipc__")}

    out["test_results"] = st.get("test_results", [])
    out["console_logs"] = st.get("console_logs", [])
    out["variable_changes"] = st.get("variable_changes", {})
    global_changes = st.get("global_variable_changes", {})
    if global_changes:
        out["global_variable_changes"] = global_changes

    if context.get("response") is None and st.get("request_mutations"):
        out["request_mutations"] = st.get("request_mutations")

    if st.get("next_request") is not None or "next_request" in st:
        out["next_request"] = st.get("next_request")
    if st.get("skip_request"):
        out["skip_request"] = True


def _reap_and_read_stderr(
    proc: subprocess.Popen[bytes],
    *,
    wait_s: float = 8.0,
    max_bytes: int = 12_000,
) -> str:
    """Wait for the child, then return a bounded tail of stderr (best-effort)."""
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=wait_s)
    if proc.stderr is None:
        return ""
    with contextlib.suppress(Exception):
        return proc.stderr.read(max_bytes).decode("utf-8", errors="replace").strip()
    return ""


def _ipc_subprocess(
    deno: Path,
    bundle: Path,
    context: ScriptInput,
    *,
    needs_net: bool,
    extra_read_paths: tuple[str, ...] = (),
) -> tuple[dict[str, Any] | None, str]:
    """Stream stdout, fulfill sendRequest lines from the Deno process.

    Returns ``(result_dict | None, stderr_if_failed)``.  *stderr_if_failed* is
    only populated when *result_dict* is ``None`` — see :func:`_run_bundle`.
    """
    from services.scripting.context import execute_sub_request

    wdir = bundle.parent
    argv, env = deno_ipc_argv_and_env(
        deno,
        bundle,
        needs_net=needs_net,
        extra_read_paths=extra_read_paths,
    )
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(wdir),
    )

    timer = threading.Timer(_SUBPROCESS_TIMEOUT, _kill_if_running, args=(proc,))
    timer.daemon = True
    timer.start()

    assert proc.stdout is not None
    assert proc.stdin is not None
    total = 0

    try:
        from services.scripting.js_runtime import _MAX_TOTAL_SUBREQUESTS as _tmax

        while True:
            line = proc.stdout.readline()
            if not line:
                return None, _reap_and_read_stderr(proc)
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("__done__") is True:
                return cast(dict[str, Any], data), ""
            if data.get("__ipc__") == "sendRequest" and "spec" in data:
                total += 1
                if total > _tmax:
                    r: dict[str, Any] = {"error": "Sub-request host limit (50) exceeded."}
                else:
                    r = execute_sub_request(data.get("spec", {}))
                if proc.stdin and not proc.stdin.closed:
                    proc.stdin.write(
                        (json.dumps(r) + "\n").encode("utf-8", errors="replace"),
                    )
                    proc.stdin.flush()
    except OSError as exc:  # pragma: no cover - best-effort
        logger.warning("Deno IPC error: %s", exc)
        return None, f"{type(exc).__name__}: {exc}"
    finally:
        timer.cancel()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=2)
        if proc.poll() is None:
            proc.kill()


def _kill_if_running(p: subprocess.Popen[bytes]) -> None:
    """Best-effort kill on timeout (timer thread)."""
    with contextlib.suppress(OSError):
        p.kill()


def _run_bundle(
    deno: Path,
    script: str,
    context: ScriptInput,
    start: float,
    *,
    language: str = "javascript",
) -> ScriptOutput:
    out = _empty_output()
    try:
        text, needs_net, local_mods = _build_bundle_text(script, context, language=language)
    except (ValueError, RuntimeError) as exc:
        return _error_output(str(exc), (time.monotonic() - start) * 1000)
    ext = "ts" if language == "typescript" else "mjs"
    with tempfile.TemporaryDirectory(prefix="postmark-deno-") as tdir:
        tpath = Path(tdir)
        write_local_modules_to_workdir(tpath, local_mods)
        bundle = tpath / f"bundle.{ext}"
        bundle.write_text(text, encoding="utf-8")
        dline, err_tail = _ipc_subprocess(deno, bundle, context, needs_net=needs_net)
        if dline is not None:
            _apply_done_line(dline, out, context)
            return cast("ScriptOutput", out)
        from services.scripting.es_module_rules import format_process_stderr

        detail = format_process_stderr(err_tail)
        if detail:
            msg = (
                "Deno did not print a result line (the process may have crashed or been killed). "
                f"Deno said: {detail}"
            )
        else:
            msg = (
                "Deno did not print a result line (timeout, crash, or no output on stdout). "
                "If Deno is installed, try again or check the path in Scripting settings."
            )
        return _error_output(msg, (time.monotonic() - start) * 1000)
