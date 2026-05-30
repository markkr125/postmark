"""Pluggable secret storage for private package-registry credentials.

Tokens for private npm / JSR registries and PyPI indexes are stored outside
of ``QSettings`` so they never end up in plain text on disk by default.

Two backends are provided:

* :class:`KeyringSecretStore` — uses the OS keychain via the ``keyring``
  library (macOS Keychain, GNOME Keyring / KWallet, Windows Credential
  Manager). The recommended default.
* :class:`EncryptedFileSecretStore` — Fernet-encrypted JSON blob under the
  user config dir, with a key derived from a stable per-machine identifier.
  Used when ``keyring`` is unavailable or the user explicitly opts in;
  surfaces a ``less safe`` warning in the UI.

Both backends share the same :class:`SecretStore` Protocol. Each entry is
addressed by an opaque ``ref`` string (e.g. ``"npm:@mycompany"``) that the
caller stores in ``QSettings`` alongside the registry URL. The actual token
is fetched at use time via :meth:`SecretStore.get`.

See :doc:`/scripting/external-packages` for the user-facing docs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import threading
import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# ``keyring`` and ``cryptography`` are optional at import time so the rest of
# the runtime works even when they're missing — the module degrades to a
# no-op store with a clear warning surfaced via :func:`backend_status`.
try:
    import keyring as _keyring_lib
    import keyring.errors as _keyring_errors

    _KEYRING_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without keyring
    _keyring_lib = None  # type: ignore[assignment]
    _keyring_errors = None  # type: ignore[assignment]
    _KEYRING_AVAILABLE = False

try:
    from cryptography.fernet import Fernet, InvalidToken

    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without cryptography
    Fernet = None  # type: ignore[assignment, misc]
    InvalidToken = Exception  # type: ignore[assignment, misc]
    _CRYPTO_AVAILABLE = False


_SERVICE_NAME = "postmark-scripting"
_ENCRYPTED_FILE_NAME = "scripting_secrets.enc"
_MACHINE_ID_PATHS = ("/etc/machine-id", "/var/lib/dbus/machine-id")


@runtime_checkable
class SecretStore(Protocol):
    """Minimal contract every secret backend honours."""

    backend_id: str

    def put(self, ref: str, secret: str) -> None:
        """Store *secret* under *ref* (overwrites)."""

    def get(self, ref: str) -> str | None:
        """Return the secret for *ref*, or ``None`` if absent / unreadable."""

    def delete(self, ref: str) -> None:
        """Remove the secret for *ref* (no-op when absent)."""


class KeyringSecretStore:
    """OS-keychain backend (macOS Keychain, GNOME Keyring, Windows CredMan)."""

    backend_id = "keyring"

    def put(self, ref: str, secret: str) -> None:
        """Store *secret* under *ref* (overwrites)."""
        if not _KEYRING_AVAILABLE or _keyring_lib is None:
            msg = "keyring library is not installed"
            raise RuntimeError(msg)
        _keyring_lib.set_password(_SERVICE_NAME, ref, secret)

    def get(self, ref: str) -> str | None:
        """Return the secret for *ref*, or ``None`` if absent / unreadable."""
        if not _KEYRING_AVAILABLE or _keyring_lib is None:
            return None
        try:
            return _keyring_lib.get_password(_SERVICE_NAME, ref)
        except Exception as exc:  # pragma: no cover - keyring backend-specific
            logger.warning("Keyring get failed for %r: %s", ref, exc)
            return None

    def delete(self, ref: str) -> None:
        """Remove the secret for *ref* (no-op when absent)."""
        if not _KEYRING_AVAILABLE or _keyring_lib is None:
            return
        try:
            _keyring_lib.delete_password(_SERVICE_NAME, ref)
        except Exception:
            # ``PasswordDeleteError`` for missing entries; treat as no-op.
            return


def _user_config_dir() -> Path:
    """Return (creating) the per-user config dir for Postmark secret files."""
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":  # pragma: no cover - platform-specific
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    out = base / "postmark"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _stable_machine_id() -> bytes:
    """Return a stable per-machine identifier as bytes.

    Falls back to ``uuid.getnode()`` (MAC address-derived) when ``machine-id``
    is unavailable on the platform. The result is not secret in any
    cryptographic sense — any process on the same machine can derive it —
    but it ties the encrypted file to this machine so a copy stolen onto
    another machine cannot be decrypted with our default key derivation.
    """
    for path in _MACHINE_ID_PATHS:
        try:
            data = Path(path).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            continue
        if data:
            return data.encode("utf-8")
    return uuid.getnode().to_bytes(8, "big", signed=False)


def _derive_fernet_key(machine_id: bytes) -> bytes:
    """Derive a Fernet-compatible (32-byte urlsafe base64) key from *machine_id*."""
    # SHA-256 → 32 bytes → urlsafe-base64 encode → Fernet key.
    digest = hashlib.sha256(b"postmark-scripting-secret/" + machine_id).digest()
    return base64.urlsafe_b64encode(digest)


class EncryptedFileSecretStore:
    """Fallback Fernet-encrypted JSON blob under the user config dir.

    Documented to the user as **less safe than the OS keychain** — the key
    is machine-bound but not user-bound, so anyone with disk access on this
    machine can decrypt. Still better than plain ``QSettings`` because the
    blob is opaque to casual snooping and grep-friendly tools.
    """

    backend_id = "encrypted_file"

    def __init__(self, file_path: Path | None = None, key: bytes | None = None) -> None:
        """Initialise with an optional override path (tests) and key (tests)."""
        self._path = file_path or (_user_config_dir() / _ENCRYPTED_FILE_NAME)
        self._key = key or _derive_fernet_key(_stable_machine_id())
        self._lock = threading.Lock()

    def _load(self) -> dict[str, str]:
        if not self._path.is_file():
            return {}
        if not _CRYPTO_AVAILABLE or Fernet is None:
            return {}
        try:
            raw = self._path.read_bytes()
            plain = Fernet(self._key).decrypt(raw)
            decoded = json.loads(plain.decode("utf-8"))
        except (OSError, InvalidToken, ValueError) as exc:
            logger.warning("EncryptedFileSecretStore: cannot read %s: %s", self._path, exc)
            return {}
        return decoded if isinstance(decoded, dict) else {}

    def _save(self, data: dict[str, str]) -> None:
        if not _CRYPTO_AVAILABLE or Fernet is None:
            msg = "cryptography library is not installed"
            raise RuntimeError(msg)
        blob = Fernet(self._key).encrypt(json.dumps(data).encode("utf-8"))
        # Atomic-ish replace + restrictive perms; the file holds tokens.
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_bytes(blob)
        os.chmod(tmp, 0o600)
        tmp.replace(self._path)

    def put(self, ref: str, secret: str) -> None:
        """Store *secret* under *ref* (overwrites)."""
        with self._lock:
            data = self._load()
            data[ref] = secret
            self._save(data)

    def get(self, ref: str) -> str | None:
        """Return the secret for *ref*, or ``None`` if absent / unreadable."""
        with self._lock:
            return self._load().get(ref)

    def delete(self, ref: str) -> None:
        """Remove the secret for *ref* (no-op when absent)."""
        with self._lock:
            data = self._load()
            if ref in data:
                del data[ref]
                self._save(data)


class NoopSecretStore:
    """Final fallback when both keyring and cryptography are missing.

    All operations succeed silently; ``get`` always returns ``None``. The
    UI surfaces this state so the user knows secrets cannot be stored.
    """

    backend_id = "none"

    def put(self, ref: str, secret: str) -> None:
        """Accept *secret* for *ref* but discard it (no persistent backend)."""
        logger.warning("NoopSecretStore: secret %r dropped (no backend available)", ref)

    def get(self, ref: str) -> str | None:
        """Always return ``None`` (secrets are not stored)."""
        return None

    def delete(self, ref: str) -> None:
        """No-op (nothing is stored)."""
        return None


_default_store: SecretStore | None = None


def get_default_store() -> SecretStore:
    """Return the process-wide :class:`SecretStore`, picking the best backend.

    Preference order:

    1. :class:`KeyringSecretStore` when ``keyring`` is importable AND its
       backend is usable (a quick self-test write/read).
    2. :class:`EncryptedFileSecretStore` when ``cryptography`` is importable.
    3. :class:`NoopSecretStore` last-resort.

    The choice is cached for the process lifetime; call :func:`reset_default_store`
    in tests to flip backends.
    """
    global _default_store
    if _default_store is not None:
        return _default_store

    if _KEYRING_AVAILABLE and _keyring_lib is not None:
        store = KeyringSecretStore()
        # Self-test: some backends (e.g. ``keyring.backends.fail.Keyring``
        # on Linux without a desktop daemon) accept registration but throw
        # on every call. Detect that here and fall through to the file
        # backend instead of surfacing the error on every settings save.
        try:
            probe_ref = "__postmark_self_test__"
            store.put(probe_ref, "ok")
            ok = store.get(probe_ref) == "ok"
            store.delete(probe_ref)
        except Exception as exc:
            logger.info("Keyring backend unusable (%s); falling back to encrypted file", exc)
            ok = False
        if ok:
            _default_store = store
            return _default_store

    if _CRYPTO_AVAILABLE:
        _default_store = EncryptedFileSecretStore()
        return _default_store

    logger.warning(
        "Neither keyring nor cryptography is available — secrets cannot be stored. "
        "Install one or both to enable private package registries."
    )
    _default_store = NoopSecretStore()
    return _default_store


def reset_default_store() -> None:
    """Clear the cached store (tests only)."""
    global _default_store
    _default_store = None


def backend_status() -> dict[str, str]:
    """UI helper: describe the active backend in one short blurb.

    Returns ``{"backend": <id>, "label": <human label>, "tone": <ok|warn|err>}``.
    """
    store = get_default_store()
    if store.backend_id == "keyring":
        return {
            "backend": "keyring",
            "label": "OS keychain",
            "tone": "ok",
        }
    if store.backend_id == "encrypted_file":
        return {
            "backend": "encrypted_file",
            "label": "Encrypted file (less safe than OS keychain)",
            "tone": "warn",
        }
    return {
        "backend": "none",
        "label": "Disabled — install ``keyring`` or ``cryptography``",
        "tone": "err",
    }


__all__ = [
    "EncryptedFileSecretStore",
    "KeyringSecretStore",
    "NoopSecretStore",
    "SecretStore",
    "backend_status",
    "get_default_store",
    "reset_default_store",
]
