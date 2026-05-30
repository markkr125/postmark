"""Resolve and validate script runtime executables (Deno, Python).

Uses :class:`PySide6.QtCore.QSettings` for ``scripting/deno_path`` and
``scripting/python_path`` without importing the UI package — organisation and
application names match ``src/ui/styling/theme_manager`` (``Postmark``).
"""

from __future__ import annotations

import functools
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import uuid
from typing import TYPE_CHECKING, Literal, TypedDict, cast

if TYPE_CHECKING:
    from PySide6.QtCore import QSettings

from services.scripting.deno_manager import DenoManager

logger = logging.getLogger(__name__)

_SETTINGS_ORG = "Postmark"
_SETTINGS_APP = "Postmark"
_KEY_DENO = "scripting/deno_path"
_KEY_PYTHON = "scripting/python_path"
_KEY_LSP_ENABLED = "scripting/lsp_enabled"
_KEY_FORMAT_ON_SAVE = "scripting/format_on_save"
_KEY_LSP_DID_CHANGE_DEBOUNCE_MS = "scripting/lsp_did_change_debounce_ms"
_KEY_LSP_PM_REQUIRE_DEBOUNCE_MS = "scripting/lsp_pm_require_debounce_ms"
_KEY_LSP_DIAG_CLEAR_DEBOUNCE_MS = "scripting/lsp_diag_clear_debounce_ms"
_KEY_LSP_DEP_DIAG_DEBOUNCE_MS = "scripting/lsp_dep_diag_debounce_ms"
_DEFAULT_LSP_DID_CHANGE_DEBOUNCE_MS = 250
_DEFAULT_LSP_PM_REQUIRE_DEBOUNCE_MS = 350
_DEFAULT_LSP_DIAG_CLEAR_DEBOUNCE_MS = 250
_DEFAULT_LSP_DEP_DIAG_DEBOUNCE_MS = 300
# Private package registries (npm + JSR share `.npmrc` mechanics).
_KEY_REGISTRIES = "scripting/registries/entries"
_KEY_DEFAULT_NPM = "scripting/registries/default_npm"
_KEY_DEFAULT_NPM_AUTH_REF = "scripting/registries/default_npm_auth_ref"
_KEY_DEFAULT_NPM_AUTH_KIND = "scripting/registries/default_npm_auth_kind"
_KEY_PYPI_INDEX = "scripting/pypi/index_url"
_KEY_PYPI_EXTRA_INDEX = "scripting/pypi/extra_index_url"
_KEY_PYPI_AUTH_REF = "scripting/pypi/auth_ref"
_KEY_PYPI_AUTH_KIND = "scripting/pypi/auth_kind"
# N-index list (top = primary, then extras), JSON-encoded ``list[PyPIIndex]``.
# Supersedes the legacy single-primary + single-extra keys above.
_KEY_PYPI_INDEXES = "scripting/pypi/indexes"

# Registry entry fields. ``auth_kind`` matches the keys an ``.npmrc`` line
# accepts: ``token`` -> ``_authToken=…``; ``basic`` -> ``_auth=<base64>``;
# ``none`` -> no auth line.
_AUTH_KINDS = ("token", "basic", "none")
_REGISTRY_KINDS = ("npm", "jsr")

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


@functools.lru_cache(maxsize=4)
def _validate_deno_cached(path: str, mtime: float) -> RuntimePathStatus:
    """Spawn ``deno --version`` once per (path, mtime) tuple.

    ``mtime`` is part of the key so updating the binary on disk invalidates
    the entry without manual intervention. Bounded to 4 entries — the typical
    set is just one path per session.
    """
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=_VALIDATE_DENO_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "path": path,
            "available": False,
            "version": "",
            "error": f"Failed to run Deno: {exc!s}",
        }
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        return {
            "path": path,
            "available": False,
            "version": "",
            "error": err or "deno --version failed.",
        }
    out = (result.stdout or result.stderr or "").strip()
    first = out.splitlines()[0] if out else "deno"
    return {"path": path, "available": True, "version": first, "error": ""}


class RegistryEntry(TypedDict):
    """One row in :meth:`RuntimeSettings.get_registries`.

    ``id`` is a stable per-row surrogate identifier (UUID4 hex) assigned at
    row creation. It anchors the ``auth_ref`` so renaming ``scope`` or
    swapping ``url`` does not orphan the stored secret. Legacy entries
    persisted before this field was introduced are auto-migrated at read
    time (see :meth:`get_registries`).

    ``scope`` is an npm-style scope (``@mycompany``). ``url`` is the registry
    base URL. ``kind`` distinguishes ``"npm"`` from ``"jsr"`` so the UI can
    label them; the on-disk ``.npmrc`` shape is the same for both since JSR
    private mirrors run through npm-compatible upstream proxies.
    ``auth_kind`` matches the keys an ``.npmrc`` line accepts. ``auth_ref``
    is the opaque reference into the :mod:`secret_store` keyed by the same
    string regardless of backend; canonical form is
    ``f"registry:{id}"``.
    """

    id: str
    scope: str
    url: str
    kind: Literal["npm", "jsr"]
    auth_kind: Literal["token", "basic", "none"]
    auth_ref: str


class PyPIConfig(TypedDict):
    """Legacy single-primary + single-extra PyPI shape.

    Kept so callers that already round-trip via :meth:`get_pypi_config` keep
    working. New code should prefer :meth:`get_pypi_indexes` which exposes
    the underlying N-index list (pip/micropip both support any number of
    index URLs in priority order). ``auth_kind`` matches the scoped-row
    semantics — see :class:`PyPIIndex` for the canonical per-row shape.
    """

    index_url: str
    extra_index_url: str
    auth_ref: str
    auth_kind: Literal["token", "basic", "none"]


class PyPIIndex(TypedDict):
    """One row in :meth:`RuntimeSettings.get_pypi_indexes`.

    pip / micropip support **any number** of index URLs in priority order
    (top = primary, then extras). Each row carries its own auth so a user
    can mix, for example, a token-authed primary mirror with a public
    fallback. ``id`` is a stable UUID4 hex so renaming/reordering can't
    orphan secrets in the OS keychain.

    The canonical ``auth_ref`` is ``f"pypi:{id}"``.
    """

    id: str
    url: str
    auth_kind: Literal["token", "basic", "none"]
    auth_ref: str


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
    def format_on_save() -> bool:
        """Whether script editors auto-format via LSP after idle typing."""
        s = _get_settings()
        raw = s.value(_KEY_FORMAT_ON_SAVE, False)
        if isinstance(raw, str):
            return raw.lower() not in {"0", "false", "no", "off", ""}
        return bool(raw)

    @staticmethod
    def set_format_on_save(enabled: bool) -> None:
        """Persist format-on-save for script editors."""
        s = _get_settings()
        s.setValue(_KEY_FORMAT_ON_SAVE, enabled)

    @staticmethod
    def _int_setting(key: str, default: int) -> int:
        """Read a positive integer from QSettings with *default* fallback."""
        s = _get_settings()
        raw = s.value(key, default)
        try:
            value = int(str(raw))
        except (TypeError, ValueError):
            return default
        return value if value > 0 else default

    @staticmethod
    def lsp_did_change_debounce_ms() -> int:
        """Debounce for LSP ``textDocument/didChange`` (ms)."""
        return RuntimeSettings._int_setting(
            _KEY_LSP_DID_CHANGE_DEBOUNCE_MS,
            _DEFAULT_LSP_DID_CHANGE_DEBOUNCE_MS,
        )

    @staticmethod
    def lsp_pm_require_debounce_ms() -> int:
        """Debounce for ``pm.require`` index regeneration (ms)."""
        return RuntimeSettings._int_setting(
            _KEY_LSP_PM_REQUIRE_DEBOUNCE_MS,
            _DEFAULT_LSP_PM_REQUIRE_DEBOUNCE_MS,
        )

    @staticmethod
    def lsp_diag_clear_debounce_ms() -> int:
        """Debounce before clearing LSP diagnostics after edits (ms)."""
        return RuntimeSettings._int_setting(
            _KEY_LSP_DIAG_CLEAR_DEBOUNCE_MS,
            _DEFAULT_LSP_DIAG_CLEAR_DEBOUNCE_MS,
        )

    @staticmethod
    def lsp_dep_diag_debounce_ms() -> int:
        """Debounce for direct ``local:`` dependency diagnostics (ms)."""
        return RuntimeSettings._int_setting(
            _KEY_LSP_DEP_DIAG_DEBOUNCE_MS,
            _DEFAULT_LSP_DEP_DIAG_DEBOUNCE_MS,
        )

    @staticmethod
    def set_deno_path(path: str) -> None:
        """Persist custom Deno path to QSettings (apply from Settings UI)."""
        s = _get_settings()
        s.setValue(_KEY_DENO, path)
        _validate_deno_cached.cache_clear()

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
        _validate_deno_cached.cache_clear()

    @staticmethod
    def clear_python_path() -> None:
        """Remove ``scripting/python_path`` so :data:`sys.executable` is used."""
        s = _get_settings()
        s.remove(_KEY_PYTHON)

    # ------------------------------------------------------------------
    # Private package registries
    # ------------------------------------------------------------------

    @staticmethod
    def get_registries() -> list[RegistryEntry]:
        """Return the list of configured private registries.

        Stored as a JSON-encoded list in QSettings. Malformed entries are
        silently dropped so a corrupted settings file cannot crash startup.
        """
        s = _get_settings()
        raw = s.value(_KEY_REGISTRIES, "")
        if not isinstance(raw, str) or not raw.strip():
            return []
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Malformed %s: %s — dropping", _KEY_REGISTRIES, exc)
            return []
        if not isinstance(parsed, list):
            return []
        out: list[RegistryEntry] = []
        migrated = False
        for raw_entry in parsed:
            if not isinstance(raw_entry, dict):
                continue
            scope = str(raw_entry.get("scope") or "").strip()
            url = str(raw_entry.get("url") or "").strip()
            if not scope or not url:
                continue
            kind = raw_entry.get("kind", "npm")
            if kind not in _REGISTRY_KINDS:
                kind = "npm"
            auth_kind = raw_entry.get("auth_kind", "none")
            if auth_kind not in _AUTH_KINDS:
                auth_kind = "none"
            auth_ref = str(raw_entry.get("auth_ref") or "").strip()
            # Migrate legacy entries (pre-``id`` field): assign a fresh UUID
            # so future scope renames don't orphan the keychain entry. The
            # previous behaviour keyed ``auth_ref`` off the scope itself,
            # which silently leaked secrets whenever a row was renamed.
            stored_id = str(raw_entry.get("id") or "").strip()
            if stored_id:
                row_id = stored_id
            else:
                row_id = uuid.uuid4().hex
                migrated = True
            out.append(
                {
                    "id": row_id,
                    "scope": scope,
                    "url": url,
                    "kind": kind,
                    "auth_kind": auth_kind,
                    "auth_ref": auth_ref,
                }
            )
        # Persist the migration on first read so the freshly-assigned
        # UUIDs stick. Without this, every call to ``get_registries``
        # would mint different IDs in memory while QSettings stays
        # legacy — and any ``auth_ref`` saved against an unpersisted
        # UUID would orphan its secret on the next read (Bug P4).
        if migrated:
            s.setValue(_KEY_REGISTRIES, json.dumps(list(out)))
        return out

    @staticmethod
    def set_registries(entries: list[RegistryEntry]) -> None:
        """Persist *entries* as a JSON blob. Pass ``[]`` to clear."""
        s = _get_settings()
        s.setValue(_KEY_REGISTRIES, json.dumps(list(entries)))

    @staticmethod
    def get_default_npm_registry() -> tuple[str, str, str]:
        """Return ``(url, auth_ref, auth_kind)`` for the default-npm override.

        Empty strings on all three when nothing is configured. ``auth_kind``
        matches scoped-row semantics (``"token"`` / ``"basic"`` / ``"none"``).
        """
        s = _get_settings()
        url = str(s.value(_KEY_DEFAULT_NPM, "") or "").strip()
        auth_ref = str(s.value(_KEY_DEFAULT_NPM_AUTH_REF, "") or "").strip()
        auth_kind = str(s.value(_KEY_DEFAULT_NPM_AUTH_KIND, "") or "").strip()
        if auth_kind not in _AUTH_KINDS:
            # ``""`` falls back to ``token`` to match the previous behaviour
            # while a saved entry without an explicit kind exists.
            auth_kind = "token" if auth_ref else "none"
        return url, auth_ref, auth_kind

    @staticmethod
    def set_default_npm_registry(url: str, auth_ref: str = "", auth_kind: str = "") -> None:
        """Persist the default-npm override; pass empty *url* to clear all three keys."""
        s = _get_settings()
        url = (url or "").strip()
        if url:
            s.setValue(_KEY_DEFAULT_NPM, url)
            s.setValue(_KEY_DEFAULT_NPM_AUTH_REF, (auth_ref or "").strip())
            kind = (auth_kind or "").strip()
            if kind not in _AUTH_KINDS:
                kind = "token" if (auth_ref or "").strip() else "none"
            s.setValue(_KEY_DEFAULT_NPM_AUTH_KIND, kind)
        else:
            s.remove(_KEY_DEFAULT_NPM)
            s.remove(_KEY_DEFAULT_NPM_AUTH_REF)
            s.remove(_KEY_DEFAULT_NPM_AUTH_KIND)

    @staticmethod
    def get_pypi_config() -> PyPIConfig:
        """Return the configured PyPI overrides (empty strings when unset)."""
        s = _get_settings()
        auth_ref = str(s.value(_KEY_PYPI_AUTH_REF, "") or "").strip()
        auth_kind = str(s.value(_KEY_PYPI_AUTH_KIND, "") or "").strip()
        if auth_kind not in _AUTH_KINDS:
            # ``""`` falls back to ``token`` to match the previous behaviour
            # while a saved entry without an explicit kind exists.
            auth_kind = "token" if auth_ref else "none"
        return {
            "index_url": str(s.value(_KEY_PYPI_INDEX, "") or "").strip(),
            "extra_index_url": str(s.value(_KEY_PYPI_EXTRA_INDEX, "") or "").strip(),
            "auth_ref": auth_ref,
            "auth_kind": cast("Literal['token', 'basic', 'none']", auth_kind),
        }

    @staticmethod
    def set_pypi_config(cfg: PyPIConfig) -> None:
        """Persist the PyPI overrides; empty strings remove the corresponding key."""
        s = _get_settings()
        for key, val in (
            (_KEY_PYPI_INDEX, cfg.get("index_url", "")),
            (_KEY_PYPI_EXTRA_INDEX, cfg.get("extra_index_url", "")),
            (_KEY_PYPI_AUTH_REF, cfg.get("auth_ref", "")),
        ):
            if (val or "").strip():
                s.setValue(key, val)
            else:
                s.remove(key)
        auth_kind = cfg.get("auth_kind", "")
        if auth_kind in _AUTH_KINDS and cfg.get("auth_ref", "").strip():
            s.setValue(_KEY_PYPI_AUTH_KIND, auth_kind)
        else:
            s.remove(_KEY_PYPI_AUTH_KIND)

    # -- N-index PyPI list --------------------------------------------

    @staticmethod
    def get_pypi_indexes() -> list[PyPIIndex]:
        """Return the configured PyPI index URLs in priority order.

        Top row = primary (replaces public PyPI); subsequent rows are
        extras. Legacy single-primary + single-extra settings (the old
        ``scripting/pypi/index_url`` + ``extra_index_url`` keys) are
        migrated to the list shape on first read, with the migration
        persisted so freshly-minted UUIDs stick across calls (mirrors the
        legacy-``id`` migration on :meth:`get_registries`).
        """
        s = _get_settings()
        raw = s.value(_KEY_PYPI_INDEXES, "")
        out: list[PyPIIndex] = []
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                parsed = []
            if isinstance(parsed, list):
                for entry in parsed:
                    if not isinstance(entry, dict):
                        continue
                    url = str(entry.get("url") or "").strip()
                    if not url:
                        continue
                    auth_kind = entry.get("auth_kind", "none")
                    if auth_kind not in _AUTH_KINDS:
                        auth_kind = "none"
                    out.append(
                        {
                            "id": str(entry.get("id") or "").strip() or uuid.uuid4().hex,
                            "url": url,
                            "auth_kind": auth_kind,
                            "auth_ref": str(entry.get("auth_ref") or "").strip(),
                        }
                    )
        if out:
            return out

        # Fall back to the legacy single-primary + single-extra keys.
        legacy = RuntimeSettings.get_pypi_config()
        migrated: list[PyPIIndex] = []
        if legacy["index_url"]:
            migrated.append(
                {
                    "id": uuid.uuid4().hex,
                    "url": legacy["index_url"],
                    "auth_kind": legacy.get("auth_kind") or "none",
                    "auth_ref": legacy.get("auth_ref") or "",
                }
            )
        if legacy["extra_index_url"]:
            # Extras inherit the single shared legacy auth_ref by design
            # (the old UI had no per-extra auth slot). The user can split
            # them later from the new table.
            migrated.append(
                {
                    "id": uuid.uuid4().hex,
                    "url": legacy["extra_index_url"],
                    "auth_kind": legacy.get("auth_kind") or "none",
                    "auth_ref": legacy.get("auth_ref") or "",
                }
            )
        if migrated:
            s.setValue(_KEY_PYPI_INDEXES, json.dumps(list(migrated)))
        return migrated

    @staticmethod
    def set_pypi_indexes(indexes: list[PyPIIndex]) -> None:
        """Persist the N-index list. Pass ``[]`` to clear all rows.

        Also clears the legacy keys so they don't shadow the list on
        subsequent reads.
        """
        s = _get_settings()
        clean: list[PyPIIndex] = []
        for entry in indexes:
            if not entry.get("url"):
                continue
            clean.append(
                {
                    "id": entry.get("id") or uuid.uuid4().hex,
                    "url": entry["url"].strip(),
                    "auth_kind": entry.get("auth_kind", "none"),
                    "auth_ref": entry.get("auth_ref", ""),
                }
            )
        if clean:
            s.setValue(_KEY_PYPI_INDEXES, json.dumps(list(clean)))
        else:
            s.remove(_KEY_PYPI_INDEXES)
        # Legacy keys are no longer authoritative — clear them so the
        # next ``get_pypi_indexes`` doesn't try to migrate stale data.
        for key in (
            _KEY_PYPI_INDEX,
            _KEY_PYPI_EXTRA_INDEX,
            _KEY_PYPI_AUTH_REF,
            _KEY_PYPI_AUTH_KIND,
        ):
            s.remove(key)

    @staticmethod
    def validate_deno(path: str | None) -> RuntimePathStatus:
        """Run ``deno --version`` and report availability.

        Cached per (path, mtime) so repeated probes from hot paths like
        ``py_runtime._use_pyodide()`` do not respawn ``deno --version``
        on every script invocation. The cache invalidates automatically
        when the binary on disk changes, and explicitly when the user
        changes the configured path via :meth:`set_deno_path` /
        :meth:`clear_deno_path`.
        """
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
            mtime = os.path.getmtime(p)
        except OSError:
            mtime = 0.0
        return _validate_deno_cached(p, mtime)

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


__all__ = [
    "PyPIConfig",
    "PyPIIndex",
    "RegistryEntry",
    "RuntimePathStatus",
    "RuntimeSettings",
]
