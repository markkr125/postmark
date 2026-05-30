"""Minimal process environment for sandbox subprocesses.

Script runtimes (Deno for JS/TS, Deno+Pyodide for Python) are spawned to run
user scripts that may come from **untrusted, imported, or shared collections**.
If we forwarded the full parent environment, a script could read host secrets
(cloud credentials, API tokens, …) via ``Deno.env`` / ``os.environ`` and
exfiltrate them through ``pm.sendRequest``.

To prevent that, subprocesses receive only the operational variables the
toolchain needs to run — never the parent's secrets.  Postman-style variables
(``pm.environment`` / ``{{var}}``) are unaffected: those travel in the script
*payload*, not the process environment.
"""

from __future__ import annotations

import os

# Operational variables the Deno / Pyodide / npm toolchain needs to start and
# resolve packages.  Compared case-insensitively so Windows' mixed-case names
# (``SystemRoot``) and POSIX names both match.  Anything NOT listed (AWS_*,
# *_TOKEN, *_SECRET, …) is withheld from the subprocess entirely.
_SAFE_ENV_NAMES: frozenset[str] = frozenset(
    name.upper()
    for name in (
        # --- POSIX ---
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "TERM",
        "TZ",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_CTYPE",
        "LC_NUMERIC",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
        # --- Windows ---
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "APPDATA",
        "LOCALAPPDATA",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMW6432",
        "PROGRAMDATA",
        "TEMP",
        "TMP",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
    )
)


def safe_subprocess_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return a minimal environment for a sandbox subprocess.

    Only operational variables (see :data:`_SAFE_ENV_NAMES`) are forwarded from
    the parent environment; *extra* (runtime-specific vars such as ``DENO_DIR``)
    is merged on top.  Host secrets are intentionally excluded so untrusted
    scripts cannot read and exfiltrate them.
    """
    env = {k: v for k, v in os.environ.items() if k.upper() in _SAFE_ENV_NAMES}
    if extra:
        env.update(extra)
    return env
