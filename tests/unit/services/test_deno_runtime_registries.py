"""Unit tests for the private-registry plumbing in :mod:`deno_runtime`.

Covers the ``.npmrc`` emission and ``--allow-net`` extension paths added for
private package registries (npm / JSR scope-mapped + default-npm override).
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

from services.scripting.deno_runtime import _build_npmrc_text, deno_ipc_argv_and_env


class _MemoryStore:
    """In-memory replacement for :class:`SecretStore` used in tests."""

    backend_id = "memory"

    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._d: dict[str, str] = dict(mapping or {})

    def put(self, ref: str, secret: str) -> None:
        self._d[ref] = secret

    def get(self, ref: str) -> str | None:
        return self._d.get(ref)

    def delete(self, ref: str) -> None:
        self._d.pop(ref, None)


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with empty registries / no default-npm / no PyPI.

    Also clears the cached ``_default_store`` (B7) so a backend choice made
    by a sibling test file does not leak into ours via the module-level
    cache in :mod:`services.scripting.secret_store`.
    """
    from services.scripting.secret_store import reset_default_store

    reset_default_store()
    monkeypatch.setattr(
        "services.scripting.runtime_settings.RuntimeSettings.get_registries",
        staticmethod(lambda: []),
    )
    monkeypatch.setattr(
        "services.scripting.runtime_settings.RuntimeSettings.get_default_npm_registry",
        staticmethod(lambda: ("", "", "none")),
    )


class TestBuildNpmrcText:
    """``_build_npmrc_text`` rolls registries + default into a single blob."""

    def test_empty_when_nothing_configured(self) -> None:
        text, hosts = _build_npmrc_text()
        assert text == ""
        assert hosts == []

    def test_scoped_registry_with_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _MemoryStore({"npm:@mycompany": "tok-abc"})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        monkeypatch.setattr(
            "services.scripting.runtime_settings.RuntimeSettings.get_registries",
            staticmethod(
                lambda: [
                    {
                        "scope": "@mycompany",
                        "url": "https://npm.mycorp.io/",
                        "kind": "npm",
                        "auth_kind": "token",
                        "auth_ref": "npm:@mycompany",
                    }
                ]
            ),
        )
        text, hosts = _build_npmrc_text()
        assert "@mycompany:registry=https://npm.mycorp.io/" in text
        assert "//npm.mycorp.io/:_authToken=tok-abc" in text
        assert hosts == ["npm.mycorp.io"]

    def test_scoped_registry_basic_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``auth_kind=basic`` emits ``_auth=`` (base64) rather than ``_authToken=``."""
        store = _MemoryStore({"npm:@mycompany": "dXNlcjpwYXNz"})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        monkeypatch.setattr(
            "services.scripting.runtime_settings.RuntimeSettings.get_registries",
            staticmethod(
                lambda: [
                    {
                        "scope": "@mycompany",
                        "url": "https://npm.mycorp.io/",
                        "kind": "npm",
                        "auth_kind": "basic",
                        "auth_ref": "npm:@mycompany",
                    }
                ]
            ),
        )
        text, _ = _build_npmrc_text()
        assert "//npm.mycorp.io/:_auth=dXNlcjpwYXNz" in text
        assert "_authToken" not in text

    def test_scoped_registry_no_auth_kind(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A scope with ``auth_kind=none`` writes only the registry line, no token."""
        store = _MemoryStore({})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        monkeypatch.setattr(
            "services.scripting.runtime_settings.RuntimeSettings.get_registries",
            staticmethod(
                lambda: [
                    {
                        "scope": "@public",
                        "url": "https://npm.public.example/",
                        "kind": "npm",
                        "auth_kind": "none",
                        "auth_ref": "",
                    }
                ]
            ),
        )
        text, hosts = _build_npmrc_text()
        assert "@public:registry=https://npm.public.example/" in text
        assert "_auth" not in text
        assert hosts == ["npm.public.example"]

    def test_default_npm_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _MemoryStore({"npm:__default__": "tok-default"})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        monkeypatch.setattr(
            "services.scripting.runtime_settings.RuntimeSettings.get_default_npm_registry",
            staticmethod(lambda: ("https://npm.mirror.io/", "npm:__default__", "token")),
        )
        text, hosts = _build_npmrc_text()
        # First non-blank line should be the default override.
        first_line = next(line for line in text.splitlines() if line)
        assert first_line == "registry=https://npm.mirror.io/"
        assert "//npm.mirror.io/:_authToken=tok-default" in text
        assert hosts == ["npm.mirror.io"]

    def test_default_registry_basic_auth_emits_underscore_auth(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Basic auth on the default registry must emit ``_auth=`` (audit fix).

        Audit-flagged bug: Basic auth on the default registry must emit
        ``_auth=`` (legacy base64), not ``_authToken=`` (bearer).
        """
        store = _MemoryStore({"npm:__default__": "dXNlcjpwYXNz"})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        monkeypatch.setattr(
            "services.scripting.runtime_settings.RuntimeSettings.get_default_npm_registry",
            staticmethod(lambda: ("https://npm.mirror.io/", "npm:__default__", "basic")),
        )
        text, _ = _build_npmrc_text()
        assert "//npm.mirror.io/:_auth=dXNlcjpwYXNz" in text
        assert "_authToken" not in text

    def test_url_with_embedded_credentials_strips_them_from_auth_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Strip embedded credentials from the auth line (B5).

        ``urlparse`` strips ``user:pass@`` from the auth line so Deno doesn't
        reject ``//baked:in@host/:_authToken=...``.
        """
        store = _MemoryStore({"npm:@mycompany": "tok-xyz"})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        monkeypatch.setattr(
            "services.scripting.runtime_settings.RuntimeSettings.get_registries",
            staticmethod(
                lambda: [
                    {
                        "scope": "@mycompany",
                        "url": "https://baked:in@npm.mycorp.io/scope/",
                        "kind": "npm",
                        "auth_kind": "token",
                        "auth_ref": "npm:@mycompany",
                    }
                ]
            ),
        )
        text, hosts = _build_npmrc_text()
        # The auth line — which is the one Deno parses — uses the clean
        # host (+ path prefix), never the embedded creds. The user's
        # original ``registry=`` URL is left as-typed (Deno tolerates
        # creds-in-URL there).
        assert "//npm.mycorp.io/scope/:_authToken=tok-xyz" in text
        auth_lines = [ln for ln in text.splitlines() if ":_authToken=" in ln]
        assert all("baked:in" not in ln for ln in auth_lines)
        # Host list for --allow-net also drops the creds.
        assert hosts == ["npm.mycorp.io"]

    def test_url_with_port_preserved_in_auth_line(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _MemoryStore({"npm:@local": "tok"})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        monkeypatch.setattr(
            "services.scripting.runtime_settings.RuntimeSettings.get_registries",
            staticmethod(
                lambda: [
                    {
                        "scope": "@local",
                        "url": "http://localhost:4873/",
                        "kind": "npm",
                        "auth_kind": "token",
                        "auth_ref": "npm:@local",
                    }
                ]
            ),
        )
        text, _ = _build_npmrc_text()
        assert "//localhost:4873/:_authToken=tok" in text

    def test_default_registry_auth_kind_none_skips_token_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A default registry override with no auth emits only ``registry=…``."""
        store = _MemoryStore({"npm:__default__": "ignored"})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        monkeypatch.setattr(
            "services.scripting.runtime_settings.RuntimeSettings.get_default_npm_registry",
            staticmethod(lambda: ("https://npm.mirror.io/", "npm:__default__", "none")),
        )
        text, _ = _build_npmrc_text()
        assert "registry=https://npm.mirror.io/" in text
        assert "_auth" not in text

    def test_port_propagates_to_allow_net(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _MemoryStore({})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        monkeypatch.setattr(
            "services.scripting.runtime_settings.RuntimeSettings.get_registries",
            staticmethod(
                lambda: [
                    {
                        "scope": "@local",
                        "url": "https://verdaccio.lan:4873/",
                        "kind": "npm",
                        "auth_kind": "none",
                        "auth_ref": "",
                    }
                ]
            ),
        )
        _, hosts = _build_npmrc_text()
        assert hosts == ["verdaccio.lan:4873"]


class TestDenoArgvWithRegistries:
    """``deno_ipc_argv_and_env`` writes the ``.npmrc`` + extends ``--allow-net``."""

    def test_no_registries_does_not_write_npmrc(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # No need to mock store / settings — the autouse fixture stubs them empty.
        bundle = tmp_path / "bundle.mjs"
        bundle.write_text("// noop")
        argv, _env = deno_ipc_argv_and_env(
            Path("/usr/bin/deno"),
            bundle,
            script_for_network_scan='pm.require("npm:lodash")',
        )
        assert not (tmp_path / ".npmrc").exists()
        # ``--allow-net`` still includes the default trio.
        net_arg = next(a for a in argv if a.startswith("--allow-net="))
        hosts = net_arg.split("=", 1)[1].split(",")
        assert "registry.npmjs.org" in hosts

    def test_registry_writes_npmrc_with_secure_perms(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        store = _MemoryStore({"npm:@mycompany": "tok-xyz"})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        monkeypatch.setattr(
            "services.scripting.runtime_settings.RuntimeSettings.get_registries",
            staticmethod(
                lambda: [
                    {
                        "scope": "@mycompany",
                        "url": "https://npm.mycorp.io/",
                        "kind": "npm",
                        "auth_kind": "token",
                        "auth_ref": "npm:@mycompany",
                    }
                ]
            ),
        )
        bundle = tmp_path / "bundle.mjs"
        bundle.write_text("// noop")
        argv, _env = deno_ipc_argv_and_env(
            Path("/usr/bin/deno"),
            bundle,
            script_for_network_scan='pm.require("npm:@mycompany/foo@1.0.0")',
        )
        npmrc = tmp_path / ".npmrc"
        assert npmrc.is_file()
        body = npmrc.read_text()
        assert "@mycompany:registry=https://npm.mycorp.io/" in body
        assert "//npm.mycorp.io/:_authToken=tok-xyz" in body
        if sys.platform != "win32":  # pragma: no cover - POSIX-only mode
            mode = npmrc.stat().st_mode & 0o777
            assert mode & stat.S_IRGRP == 0
            assert mode & stat.S_IROTH == 0
        net_arg = next(a for a in argv if a.startswith("--allow-net="))
        hosts = net_arg.split("=", 1)[1].split(",")
        assert "npm.mycorp.io" in hosts
        # Default hosts still present (public packages keep resolving).
        assert "registry.npmjs.org" in hosts

    def test_default_override_adds_host(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        store = _MemoryStore({})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        monkeypatch.setattr(
            "services.scripting.runtime_settings.RuntimeSettings.get_default_npm_registry",
            staticmethod(lambda: ("https://npm.mirror.io/", "", "none")),
        )
        bundle = tmp_path / "bundle.mjs"
        bundle.write_text("// noop")
        argv, _env = deno_ipc_argv_and_env(
            Path("/usr/bin/deno"),
            bundle,
            script_for_network_scan='pm.require("npm:lodash@4.17.21")',
        )
        body = (tmp_path / ".npmrc").read_text()
        assert "registry=https://npm.mirror.io/" in body
        net_arg = next(a for a in argv if a.startswith("--allow-net="))
        assert "npm.mirror.io" in net_arg.split("=", 1)[1].split(",")
