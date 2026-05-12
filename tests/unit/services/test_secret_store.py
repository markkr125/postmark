"""Unit tests for :mod:`services.scripting.secret_store`."""

from __future__ import annotations

import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.scripting.secret_store import (
    EncryptedFileSecretStore,
    KeyringSecretStore,
    NoopSecretStore,
    backend_status,
    get_default_store,
    reset_default_store,
)


@pytest.fixture(autouse=True)
def _isolate_default_store():  # type: ignore[no-untyped-def]
    """B7: ``_default_store`` is module-level cached for the process lifetime.

    Without this fixture, the first test that materialises the real
    backend (e.g. ``TestEncryptedFileBackend``'s explicit construction
    won't trigger this, but ``backend_status()`` will) poisons the cache
    for every test downstream. Reset before AND after each case so the
    selection logic gets a clean run.
    """
    reset_default_store()
    yield
    reset_default_store()


class TestEncryptedFileBackend:
    """Round-trip on a temp file with a deterministic key."""

    def test_put_get_delete(self, tmp_path: Path) -> None:
        store = EncryptedFileSecretStore(
            file_path=tmp_path / "secrets.enc",
            # Static key keeps the test independent of machine-id reads.
            key=b"5JpUTYBp2nKv5G7ePIH3MhvD0lE7l2HhWMs8XGT3-Pk=",
        )
        store.put("npm:@mycompany", "tok-abc")
        store.put("pypi:default", "pypi-zzz")
        assert store.get("npm:@mycompany") == "tok-abc"
        assert store.get("pypi:default") == "pypi-zzz"
        store.delete("npm:@mycompany")
        assert store.get("npm:@mycompany") is None
        assert store.get("pypi:default") == "pypi-zzz"

    def test_overwrite_replaces_value(self, tmp_path: Path) -> None:
        store = EncryptedFileSecretStore(
            file_path=tmp_path / "secrets.enc",
            key=b"5JpUTYBp2nKv5G7ePIH3MhvD0lE7l2HhWMs8XGT3-Pk=",
        )
        store.put("ref", "v1")
        store.put("ref", "v2")
        assert store.get("ref") == "v2"

    def test_missing_ref_returns_none(self, tmp_path: Path) -> None:
        store = EncryptedFileSecretStore(
            file_path=tmp_path / "secrets.enc",
            key=b"5JpUTYBp2nKv5G7ePIH3MhvD0lE7l2HhWMs8XGT3-Pk=",
        )
        assert store.get("nope") is None

    def test_file_perms_locked_down(self, tmp_path: Path) -> None:
        path = tmp_path / "secrets.enc"
        store = EncryptedFileSecretStore(
            file_path=path,
            key=b"5JpUTYBp2nKv5G7ePIH3MhvD0lE7l2HhWMs8XGT3-Pk=",
        )
        store.put("ref", "v")
        if sys.platform == "win32":  # pragma: no cover - Windows POSIX-mode unreliable
            return
        mode = path.stat().st_mode & 0o777
        # 0o600 — owner read/write, no group, no other.
        assert mode & stat.S_IRGRP == 0
        assert mode & stat.S_IROTH == 0

    def test_corrupt_file_yields_empty_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "secrets.enc"
        path.write_bytes(b"not-a-fernet-blob")
        store = EncryptedFileSecretStore(
            file_path=path,
            key=b"5JpUTYBp2nKv5G7ePIH3MhvD0lE7l2HhWMs8XGT3-Pk=",
        )
        # No exception; treats the corrupt blob as "no secrets stored".
        assert store.get("ref") is None


class TestKeyringBackend:
    """Verify the backend delegates to the ``keyring`` module."""

    def test_round_trip_through_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = MagicMock()
        fake.get_password.return_value = "secret-val"
        monkeypatch.setattr("services.scripting.secret_store._keyring_lib", fake)
        monkeypatch.setattr("services.scripting.secret_store._KEYRING_AVAILABLE", True)
        store = KeyringSecretStore()
        store.put("ref", "secret-val")
        assert store.get("ref") == "secret-val"
        fake.set_password.assert_called_once_with("postmark-scripting", "ref", "secret-val")
        store.delete("ref")
        fake.delete_password.assert_called_once_with("postmark-scripting", "ref")

    def test_delete_swallows_missing_entry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = MagicMock()
        fake.delete_password.side_effect = Exception("missing")
        monkeypatch.setattr("services.scripting.secret_store._keyring_lib", fake)
        monkeypatch.setattr("services.scripting.secret_store._KEYRING_AVAILABLE", True)
        store = KeyringSecretStore()
        # No exception escapes.
        store.delete("ref")

    def test_get_returns_none_when_keyring_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("services.scripting.secret_store._keyring_lib", None)
        monkeypatch.setattr("services.scripting.secret_store._KEYRING_AVAILABLE", False)
        store = KeyringSecretStore()
        assert store.get("ref") is None


class TestDefaultStoreSelection:
    """`get_default_store` picks the strongest backend that actually works."""

    def test_keyring_self_test_pass_picks_keyring(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_default_store()
        fake = MagicMock()
        fake.get_password.return_value = "ok"
        monkeypatch.setattr("services.scripting.secret_store._keyring_lib", fake)
        monkeypatch.setattr("services.scripting.secret_store._KEYRING_AVAILABLE", True)
        try:
            store = get_default_store()
            assert store.backend_id == "keyring"
        finally:
            reset_default_store()

    def test_keyring_throws_falls_back_to_encrypted(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        reset_default_store()
        fake = MagicMock()
        fake.set_password.side_effect = Exception("no backend daemon")
        monkeypatch.setattr("services.scripting.secret_store._keyring_lib", fake)
        monkeypatch.setattr("services.scripting.secret_store._KEYRING_AVAILABLE", True)
        monkeypatch.setattr("services.scripting.secret_store._CRYPTO_AVAILABLE", True)
        # Redirect the encrypted-file backend at a tmp dir.
        monkeypatch.setattr("services.scripting.secret_store._user_config_dir", lambda: tmp_path)
        try:
            store = get_default_store()
            assert store.backend_id == "encrypted_file"
        finally:
            reset_default_store()

    def test_neither_available_falls_back_to_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_default_store()
        monkeypatch.setattr("services.scripting.secret_store._KEYRING_AVAILABLE", False)
        monkeypatch.setattr("services.scripting.secret_store._CRYPTO_AVAILABLE", False)
        try:
            store = get_default_store()
            assert store.backend_id == "none"
            # No-op never raises and never returns a real secret.
            store.put("ref", "v")
            assert store.get("ref") is None
            store.delete("ref")
        finally:
            reset_default_store()


class TestBackendStatus:
    """UI-facing status label switches based on the active backend."""

    def test_keyring_status_is_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_default_store()
        fake = MagicMock()
        fake.get_password.return_value = "ok"
        monkeypatch.setattr("services.scripting.secret_store._keyring_lib", fake)
        monkeypatch.setattr("services.scripting.secret_store._KEYRING_AVAILABLE", True)
        try:
            assert backend_status() == {
                "backend": "keyring",
                "label": "OS keychain",
                "tone": "ok",
            }
        finally:
            reset_default_store()

    def test_noop_status_is_err(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_default_store()
        monkeypatch.setattr("services.scripting.secret_store._KEYRING_AVAILABLE", False)
        monkeypatch.setattr("services.scripting.secret_store._CRYPTO_AVAILABLE", False)
        try:
            s = backend_status()
            assert s["backend"] == "none"
            assert s["tone"] == "err"
        finally:
            reset_default_store()


def test_noop_store_is_silent_no_op() -> None:
    store = NoopSecretStore()
    store.put("ref", "x")
    assert store.get("ref") is None
    store.delete("ref")
