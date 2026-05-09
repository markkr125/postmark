"""Resolve and validate script runtime executables (Deno, Python).

Uses :class:`PySide6.QtCore.QSettings` for ``scripting/deno_path`` and
``scripting/python_path`` without importing the UI package — organisation and
application names match ``src/ui/styling/theme_manager`` (``Postmark``).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from PySide6.QtCore import QSettings

from services.scripting.deno_manager import DenoManager

_SETTINGS_ORG = "Postmark"
_SETTINGS_APP = "Postmark"
_KEY_DENO = "scripting/deno_path"
_KEY_PYTHON = "scripting/python_path"
_KEY_LSP_ENABLED = "scripting/lsp_enabled"

# Short timeouts; validation must not block the UI thread for long.
_VALIDATE_DENO_TIMEOUT_S = 5.0
_VALIDATE_PYTHON_TIMEOUT_S = 15.0

_IS_WIN = platform.system() == "Windows"


class RuntimePathStatus(TypedDict):
    """Result of :meth:`RuntimeSettings.validate_deno` or ``validate_python``."""

    path: str
    available: bool
    version: str
    error: str


def _get_settings() -> QSettings:
    from PySide6.QtCore import QSettings as _Q

    return _Q(_SETTINGS_ORG, _SETTINGS_APP)


def _is_executable_file(path: str) -> bool:
    """Return True if *path* is a file we may run on this platform."""
    p = os.path.abspath(path)
    if not os.path.isfile(p):
        return False
    if _IS_WIN:
        return True
    return os.access(p, os.X_OK)


class RuntimeSettings:
    """Deno and Python paths from QSettings, PATH, and built-in fallbacks.

    All public methods are static; mirrors :class:`DenoManager` style.
    """

    @staticmethod
    def deno_path() -> str | None:
        """Return a resolved Deno executable path, or ``None`` if not found.

        Order:

        1. User setting ``scripting/deno_path`` (non-empty).
        2. :func:`shutil.which` (``deno``; on Windows also ``deno.exe``).
        3. :meth:`DenoManager.managed_deno_path` (managed download cache).
        """
        s = _get_settings()
        raw = s.value(_KEY_DENO, "")
        custom = (str(raw) if raw is not None else "").strip()
        if custom:
            return custom
        w = shutil.which("deno")
        if w:
            return w
        if _IS_WIN:
            w2 = shutil.which("deno.exe")
            if w2:
                return w2
        managed = DenoManager.managed_deno_path()
        if managed is not None:
            return str(managed)
        return None

    @staticmethod
    def auto_detected_deno_path() -> str | None:
        r"""Deno from ``PATH`` or managed cache only (no custom QSettings key).

        Used to preview the executable when the Settings line edit is empty
        and for the "Auto-detect" action before Apply.
        """
        w = shutil.which("deno")
        if w:
            return w
        if _IS_WIN:
            w2 = shutil.which("deno.exe")
            if w2:
                return w2
        managed = DenoManager.managed_deno_path()
        if managed is not None:
            return str(managed)
        return None

    @staticmethod
    def python_path() -> str:
        """Return the resolved Python executable (RestrictedPython host).

        Order:

        1. User setting ``scripting/python_path`` (non-empty).
        2. :data:`sys.executable`.
        """
        s = _get_settings()
        raw = s.value(_KEY_PYTHON, "")
        custom = (str(raw) if raw is not None else "").strip()
        if custom:
            return custom
        return sys.executable

    @staticmethod
    def lsp_enabled() -> bool:
        """Whether IDE-style language servers are enabled for script editors."""
        s = _get_settings()
        raw = s.value(_KEY_LSP_ENABLED, True)
        if isinstance(raw, str):
            return raw.lower() not in {"0", "false", "no", "off", ""}
        return bool(raw)

    @staticmethod
    def set_lsp_enabled(enabled: bool) -> None:
        """Persist script LSP toggle."""
        s = _get_settings()
        s.setValue(_KEY_LSP_ENABLED, enabled)

    @staticmethod
    def set_deno_path(path: str) -> None:
        """Persist custom Deno path to QSettings (apply from Settings UI)."""
        s = _get_settings()
        s.setValue(_KEY_DENO, path)

    @staticmethod
    def set_python_path(path: str) -> None:
        """Persist custom Python path to QSettings."""
        s = _get_settings()
        s.setValue(_KEY_PYTHON, path)

    @staticmethod
    def clear_deno_path() -> None:
        """Remove ``scripting/deno_path`` so auto-detection applies."""
        s = _get_settings()
        s.remove(_KEY_DENO)

    @staticmethod
    def clear_python_path() -> None:
        """Remove ``scripting/python_path`` so :data:`sys.executable` is used."""
        s = _get_settings()
        s.remove(_KEY_PYTHON)

    @staticmethod
    def validate_deno(path: str | None) -> RuntimePathStatus:
        """Run ``deno --version`` and report availability."""
        if path is None or not str(path).strip():
            return {
                "path": "",
                "available": False,
                "version": "",
                "error": "No Deno path configured or detected.",
            }
        p = os.path.expanduser(str(path).strip())
        if not _is_executable_file(p):
            return {
                "path": p,
                "available": False,
                "version": "",
                "error": "Path is missing or not executable on this system.",
            }
        try:
            result = subprocess.run(
                [p, "--version"],
                capture_output=True,
                text=True,
                timeout=_VALIDATE_DENO_TIMEOUT_S,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "path": p,
                "available": False,
                "version": "",
                "error": f"Failed to run Deno: {exc!s}",
            }
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            return {
                "path": p,
                "available": False,
                "version": "",
                "error": err or "deno --version failed.",
            }
        out = (result.stdout or result.stderr or "").strip()
        first = out.splitlines()[0] if out else "deno"
        return {"path": p, "available": True, "version": first, "error": ""}

    @staticmethod
    def validate_python(path: str | None) -> RuntimePathStatus:
        """Verify *path* can ``import RestrictedPython`` in a subprocess."""
        if path is None or not str(path).strip():
            return {
                "path": "",
                "available": False,
                "version": "",
                "error": "No Python path configured or detected.",
            }
        p = os.path.expanduser(str(path).strip())
        if not _is_executable_file(p):
            return {
                "path": p,
                "available": False,
                "version": "",
                "error": "Path is missing or not executable on this system.",
            }
        check = "import RestrictedPython; import sys; print(sys.version.split()[0])"
        try:
            result = subprocess.run(
                [p, "-c", check],
                capture_output=True,
                text=True,
                timeout=_VALIDATE_PYTHON_TIMEOUT_S,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "path": p,
                "available": False,
                "version": "",
                "error": f"Failed to run Python: {exc!s}",
            }
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            return {
                "path": p,
                "available": False,
                "version": "",
                "error": err or "Python check failed (RestrictedPython required).",
            }
        out = (result.stdout or "").strip()
        first = out.splitlines()[0] if out else ""
        return {"path": p, "available": True, "version": first, "error": ""}


__all__ = ["RuntimePathStatus", "RuntimeSettings"]
