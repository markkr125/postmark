"""Run Postmark Python scripts inside Pyodide via a Deno subprocess.

Loads Pyodide from :file:`data/scripts/vendor_pyodide/` (offline runtime),
optional ``micropip`` installs for ``pm.require`` string literals, and the
shared :file:`data/scripts/pm_bootstrap.py` ``pm`` API.  Uses the same JSON
line IPC as :mod:`services.scripting.py_runtime` for ``pm.send_request``.
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.scripting.runtime_settings import RuntimeSettings

if TYPE_CHECKING:
    from services.scripting import ScriptInput

_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "data" / "scripts"
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_PYODIDE_ENTRY = _SCRIPTS_DIR / "pyodide_run.mjs"
_VENDOR_MARKER = _SCRIPTS_DIR / "vendor_pyodide" / "pyodide.asm.wasm"
_SUBPROCESS_TIMEOUT_S = 120.0

_PYPI_AND_CDN_HOSTS = (
    "pypi.org",
    "files.pythonhosted.org",
    "cdn.jsdelivr.net",
    "registry.npmjs.org",
)


def pyodide_vendor_ready() -> bool:
    """Return True when the vendored Pyodide runtime files are present."""
    return _VENDOR_MARKER.is_file()


def _postmark_pyodide_user_cache_dir() -> Path:
    """Return (and create) ``~/.cache/postmark/pyodide_cache`` (or OS equivalent)."""
    system = platform.system()
    if system == "Linux":
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    p = base / "postmark" / "pyodide_cache"
    p.mkdir(parents=True, exist_ok=True)
    (p / "pkgs").mkdir(exist_ok=True)
    (p / "deno_dir").mkdir(exist_ok=True)
    return p


def _pypi_index_hosts(urls: list[str]) -> list[str]:
    """Extract ``host[:port]`` entries from PyPI index URLs."""
    from urllib.parse import urlparse

    out: list[str] = []
    for url in urls:
        if not url:
            continue
        try:
            parsed = urlparse(url)
        except (ValueError, TypeError):
            continue
        host = parsed.hostname or ""
        if not host:
            continue
        if parsed.port:
            host = f"{host}:{parsed.port}"
        if host not in out:
            out.append(host)
    return out


def _deno_argv_and_env(
    deno: Path,
    *,
    needs_net: bool,
    extra_hosts: list[str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Build ``deno run`` argv + env for :file:`pyodide_run.mjs`.

    *extra_hosts* lets private PyPI registries be added to the ``--allow-net``
    list without exposing the public PyPI host when the user's config replaces
    it.
    """
    cache = _postmark_pyodide_user_cache_dir()
    read_parts: list[str] = [str(_SCRIPTS_DIR), str(_REPO_ROOT), str(cache)]
    read_paths = ",".join(read_parts)
    args: list[str] = [
        str(deno),
        "run",
        "--no-prompt",
        "--no-lock",
        f"--allow-read={read_paths}",
        f"--allow-write={cache}",
    ]
    if needs_net:
        hosts = list(_PYPI_AND_CDN_HOSTS) + [
            h for h in (extra_hosts or []) if h not in _PYPI_AND_CDN_HOSTS
        ]
        args.append(f"--allow-net={','.join(hosts)}")
    args.append("--allow-env")
    args.append(str(_PYODIDE_ENTRY))
    env = {
        **os.environ,
        "DENO_DIR": str(cache / "deno_dir"),
        "PM_PYODIDE_CACHE": str(cache / "pkgs"),
    }
    return args, env


def _resolve_pypi_index_urls() -> list[str]:
    """Build the ordered ``micropip.set_index_urls`` argument from settings.

    Iterates every configured PyPI index in priority order. Each row carries
    its own ``auth_kind`` / ``auth_ref`` (mixed auth across rows is
    supported — e.g. a token-authed corporate primary mirror with a
    public PyPI fallback as the extra).

    Auth is embedded via ``https://user:password@host/`` because that's the
    only format ``micropip`` honours (it has no ``.netrc`` parsing). For
    ``auth_kind == "basic"`` the secret is the base64 of
    ``user:password`` (matching the ``.npmrc`` ``_auth=`` convention);
    embedding the blob raw produces ``https://<base64>@host`` which
    ``urlparse`` reads as username-only and the server gets a malformed
    Basic header — we decode the blob back to ``user:password`` here so
    micropip can re-encode it correctly for the Authorization header.

    Pre-embedded credentials in the URL itself are left untouched so a
    user who wants to bypass our secret store can paste ``https://u:p@host/``
    directly.
    """
    import base64 as _base64
    from urllib.parse import quote

    from services.scripting.runtime_settings import RuntimeSettings
    from services.scripting.secret_store import get_default_store

    indexes = RuntimeSettings.get_pypi_indexes()
    if not indexes:
        return []

    store = get_default_store()
    out: list[str] = []
    for row in indexes:
        url = row.get("url", "")
        if not url:
            continue
        kind = row.get("auth_kind", "none")
        ref = row.get("auth_ref", "")
        secret = store.get(ref) if (ref and kind != "none") else ""
        secret = secret or ""

        creds_segment = ""
        if secret:
            if kind == "basic":
                try:
                    decoded = _base64.b64decode(secret, validate=False).decode("utf-8")
                except (UnicodeDecodeError, ValueError):
                    decoded = ""
                if ":" in decoded:
                    user, _, password = decoded.partition(":")
                    creds_segment = (
                        f"{quote(user, safe='')}:{quote(password, safe='')}"
                    )
            else:
                creds_segment = quote(secret, safe="")

        if not creds_segment or "://" not in url:
            out.append(url)
            continue
        scheme, rest = url.split("://", 1)
        host_part = rest.split("/", 1)[0]
        if "@" in host_part:  # pre-embedded creds win
            out.append(url)
        else:
            out.append(f"{scheme}://{creds_segment}@{rest}")
    return out


class PyodideRuntime:
    """Execute Python in Pyodide (WASM) under ``deno run``."""

    @staticmethod
    def execute(script: str, context: ScriptInput) -> dict[str, Any]:
        """Run *script* and return a raw dict (may include ``error`` or ``__done__``)."""
        from services.scripting.py_runtime import detect_pm_require_py_specs

        try:
            specs = [s.pip_spec for s in detect_pm_require_py_specs(script)]
        except ValueError as exc:
            return _err(str(exc))

        deno = RuntimeSettings.deno_path()
        st = RuntimeSettings.validate_deno(deno)
        if not st.get("available"):
            return _err(
                "Deno is not available for the Pyodide Python runtime. "
                "Configure Deno in Settings or install the managed runtime."
            )

        if not pyodide_vendor_ready():
            return _err(
                "Pyodide runtime files are missing under data/scripts/vendor_pyodide/. "
                "Install the Pyodide core bundle (see project docs)."
            )

        needs_net = bool(specs)
        pypi_index_urls = _resolve_pypi_index_urls() if needs_net else []
        extra_hosts = _pypi_index_hosts(pypi_index_urls)
        argv, env = _deno_argv_and_env(
            Path(st["path"]),
            needs_net=needs_net,
            extra_hosts=extra_hosts,
        )
        payload = {
            "user_script": script,
            "context": dict(context),
            "pm_require": specs,
            "pypi_index_urls": pypi_index_urls,
        }
        line = (json.dumps(payload, default=str) + "\n").encode("utf-8")

        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=str(_SCRIPTS_DIR),
            )
        except OSError as exc:
            return _err(f"Failed to start Pyodide subprocess: {exc}")

        timer = threading.Timer(_SUBPROCESS_TIMEOUT_S, _kill_proc, args=(proc,))
        timer.daemon = True
        timer.start()
        try:
            assert proc.stdin is not None
            proc.stdin.write(line)
            proc.stdin.flush()
            data = _ipc_loop(proc)
            if data is not None:
                data.pop("__done__", None)
                return data
            err = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            return _err(err.strip() or "Pyodide produced no __done__ line")
        except Exception as exc:
            return _err(f"Pyodide IPC error: {exc}")
        finally:
            timer.cancel()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=5)
            if proc.poll() is None:
                proc.kill()


def _kill_proc(proc: subprocess.Popen[bytes]) -> None:
    """Kill the subprocess (called from the timer thread)."""
    with contextlib.suppress(OSError):
        proc.kill()


def _ipc_loop(proc: subprocess.Popen[bytes]) -> dict[str, Any] | None:
    """Read stdout lines, fulfill ``sendRequest`` IPC on stdin."""
    from services.scripting.context import execute_sub_request

    assert proc.stdout is not None
    assert proc.stdin is not None

    while True:
        raw = proc.stdout.readline()
        if not raw:
            return None
        try:
            data: dict[str, Any] = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("__done__"):
            return data
        if data.get("__ipc__") == "sendRequest":
            resp = execute_sub_request(data.get("spec", {}))
            proc.stdin.write(json.dumps(resp, default=str).encode("utf-8") + b"\n")
            proc.stdin.flush()


def _err(message: str) -> dict[str, Any]:
    """Return a minimal error-shaped dict for :meth:`PyRuntime.execute` to convert."""
    return {
        "error": message,
        "test_results": [],
        "console_logs": [],
        "variable_changes": {},
        "request_mutations": None,
    }
