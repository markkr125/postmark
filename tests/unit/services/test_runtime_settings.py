"""Unit tests for :mod:`services.scripting.runtime_settings`."""

from __future__ import annotations

import stat
import sys
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

from services.scripting.runtime_settings import (
    PyPIIndex,
    RegistryEntry,
    RuntimePathStatus,
    RuntimeSettings,
    _is_executable_file,
)


class _MemoryQSettings:
    """Minimal QSettings stand-in (value / setValue / remove)."""

    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def value(self, key: str, default: str = "") -> str:
        return self._d.get(key, default)

    def setValue(self, key: str, value: str) -> None:
        self._d[key] = str(value)

    def remove(self, key: str) -> None:
        self._d.pop(key, None)


class TestDenoPathResolution:
    """Resolution order for :meth:`RuntimeSettings.deno_path`."""

    def test_custom_path_wins(
        self,
        tmp_path: Path,
    ) -> None:
        mem = _MemoryQSettings()
        mem.setValue("scripting/deno_path", str(tmp_path / "custom" / "deno"))
        with (
            patch("services.scripting.runtime_settings._get_settings", return_value=mem),
            patch("services.scripting.runtime_settings.shutil.which", return_value=None),
            patch(
                "services.scripting.deno_manager.DenoManager.managed_deno_path",
                return_value=None,
            ),
        ):
            p = tmp_path / "custom" / "deno"
            p.parent.mkdir(parents=True)
            p.write_text("x")
            assert RuntimeSettings.deno_path() == str(p)

    def test_which_when_no_custom(
        self,
    ) -> None:
        mem = _MemoryQSettings()
        with (
            patch("services.scripting.runtime_settings._get_settings", return_value=mem),
            patch("services.scripting.runtime_settings.shutil.which", return_value="/usr/bin/deno"),
        ):
            assert RuntimeSettings.deno_path() == "/usr/bin/deno"

    def test_deno_exe_on_windows(
        self,
    ) -> None:
        mem = _MemoryQSettings()
        with (
            patch("services.scripting.runtime_settings._get_settings", return_value=mem),
            patch("services.scripting.runtime_settings._IS_WIN", True),
            patch(
                "services.scripting.runtime_settings.shutil.which",
                side_effect=[None, r"C:\bin\deno.exe"],
            ),
        ):
            assert RuntimeSettings.deno_path() == r"C:\bin\deno.exe"

    def test_managed_cache_when_path_empty(
        self,
        tmp_path: Path,
    ) -> None:
        mem = _MemoryQSettings()
        managed = tmp_path / "deno"
        managed.write_text("fake")
        with (
            patch("services.scripting.runtime_settings._get_settings", return_value=mem),
            patch("services.scripting.runtime_settings.shutil.which", return_value=None),
            patch(
                "services.scripting.deno_manager.DenoManager.managed_deno_path",
                return_value=managed,
            ),
        ):
            assert RuntimeSettings.deno_path() == str(managed)

    def test_none_when_nothing(
        self,
    ) -> None:
        mem = _MemoryQSettings()
        with (
            patch("services.scripting.runtime_settings._get_settings", return_value=mem),
            patch("services.scripting.runtime_settings.shutil.which", return_value=None),
            patch(
                "services.scripting.deno_manager.DenoManager.managed_deno_path",
                return_value=None,
            ),
        ):
            assert RuntimeSettings.deno_path() is None

    def test_auto_detected_ignores_user_setting(
        self,
    ) -> None:
        """auto_detected_deno_path does not read QSettings."""
        mem = _MemoryQSettings()
        mem.setValue("scripting/deno_path", "/opt/custom/deno")
        with (
            patch("services.scripting.runtime_settings._get_settings", return_value=mem),
            patch("services.scripting.runtime_settings.shutil.which", return_value="/usr/deno"),
        ):
            assert RuntimeSettings.deno_path() == "/opt/custom/deno"
            assert RuntimeSettings.auto_detected_deno_path() == "/usr/deno"


class TestPythonPathResolution:
    """Python executable resolution."""

    def test_uses_sys_executable_by_default(
        self,
    ) -> None:
        mem = _MemoryQSettings()
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            assert RuntimeSettings.python_path() == sys.executable

    def test_custom_overrides(
        self,
    ) -> None:
        mem = _MemoryQSettings()
        mem.setValue("scripting/python_path", "/opt/py/bin/python")
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            assert RuntimeSettings.python_path() == "/opt/py/bin/python"


class TestQSettingsMutators:
    """set/clear for Deno and Python path keys."""

    def test_set_clear_deno(
        self,
    ) -> None:
        s = _MemoryQSettings()
        with patch("services.scripting.runtime_settings._get_settings", return_value=s):
            RuntimeSettings.set_deno_path("/x/deno")
            assert s.value("scripting/deno_path") == "/x/deno"
            RuntimeSettings.clear_deno_path()
            assert s.value("scripting/deno_path", "") == ""

    def test_set_clear_python(
        self,
    ) -> None:
        s = _MemoryQSettings()
        with patch("services.scripting.runtime_settings._get_settings", return_value=s):
            RuntimeSettings.set_python_path("/y/python")
            assert s.value("scripting/python_path") == "/y/python"
            RuntimeSettings.clear_python_path()
            assert s.value("scripting/python_path", "") == ""


class TestValidation:
    """validate_deno and validate_python."""

    def test_validate_deno_empty(
        self,
    ) -> None:
        st: RuntimePathStatus = RuntimeSettings.validate_deno(None)
        assert st["available"] is False
        assert st["error"] != ""
        st2: RuntimePathStatus = RuntimeSettings.validate_deno("   ")
        assert st2["available"] is False

    def test_validate_deno_missing_file(
        self,
    ) -> None:
        st: RuntimePathStatus = RuntimeSettings.validate_deno(
            str(Path("/this/path/should/not/exist/12345/deno"))
        )
        assert st["available"] is False
        assert "Path is missing" in st["error"] or st["error"]

    def test_validate_deno_rejects_on_bad_exit(
        self,
        tmp_path: Path,
    ) -> None:
        bad = tmp_path / "not-deno"
        bad.write_text("echo no")
        if sys.platform != "win32":  # pragma: no cover - line coverage on Unix
            bad.chmod(bad.stat().st_mode | stat.S_IXUSR)
        with patch("services.scripting.runtime_settings.subprocess.run") as m_run:
            m_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")
            st: RuntimePathStatus = RuntimeSettings.validate_deno(str(bad))
        assert st["available"] is False
        assert st["version"] == ""

    def test_validate_python_uses_current_interpreter(
        self,
    ) -> None:
        st: RuntimePathStatus = RuntimeSettings.validate_python(sys.executable)
        assert st["available"] is True
        assert st["version"] != ""


def test_is_executable_rejects_dir() -> None:
    """_is_executable_file is false for directories and missing paths."""
    assert _is_executable_file("/") is False
    assert _is_executable_file("notafile") is False


class TestPrivateRegistries:
    """Round-trip + corruption tolerance for :meth:`get_registries`."""

    def test_registries_round_trip(self) -> None:
        mem = _MemoryQSettings()
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            assert RuntimeSettings.get_registries() == []
            entries = [
                {
                    "id": "row-mc",
                    "scope": "@mycompany",
                    "url": "https://npm.mycorp.io/",
                    "kind": "npm",
                    "auth_kind": "token",
                    "auth_ref": "registry:row-mc",
                },
                {
                    "id": "row-std",
                    "scope": "@std",
                    "url": "https://jsr.mycorp.io/",
                    "kind": "jsr",
                    "auth_kind": "none",
                    "auth_ref": "",
                },
            ]
            RuntimeSettings.set_registries(cast(list[RegistryEntry], entries))
            assert RuntimeSettings.get_registries() == entries

    def test_registries_corrupt_json_returns_empty(self) -> None:
        mem = _MemoryQSettings()
        mem.setValue("scripting/registries/entries", "{not json")
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            assert RuntimeSettings.get_registries() == []

    def test_registries_drops_malformed_entries(self) -> None:
        """Entries missing ``scope`` or ``url`` are silently filtered."""
        mem = _MemoryQSettings()
        import json

        mem.setValue(
            "scripting/registries/entries",
            json.dumps(
                [
                    {"scope": "@ok", "url": "https://ok/", "kind": "npm"},
                    {"scope": "", "url": "https://no-scope/"},
                    {"scope": "@no-url"},
                    "not-a-dict",
                ]
            ),
        )
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            result = RuntimeSettings.get_registries()
        assert len(result) == 1
        assert result[0]["scope"] == "@ok"
        assert result[0]["auth_kind"] == "none"

    def test_registries_unknown_kind_or_auth_kind_falls_back(self) -> None:
        mem = _MemoryQSettings()
        import json

        mem.setValue(
            "scripting/registries/entries",
            json.dumps(
                [
                    {
                        "scope": "@ok",
                        "url": "https://ok/",
                        "kind": "deno-mart",
                        "auth_kind": "ssh-key",
                    }
                ]
            ),
        )
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            result = RuntimeSettings.get_registries()
        assert result[0]["kind"] == "npm"
        assert result[0]["auth_kind"] == "none"

    def test_default_npm_registry_round_trip(self) -> None:
        mem = _MemoryQSettings()
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            assert RuntimeSettings.get_default_npm_registry() == ("", "", "none")
            RuntimeSettings.set_default_npm_registry(
                "https://mirror.mycorp.io/", "npm:__default__", "token"
            )
            assert RuntimeSettings.get_default_npm_registry() == (
                "https://mirror.mycorp.io/",
                "npm:__default__",
                "token",
            )
            # Switching to basic auth survives a round trip.
            RuntimeSettings.set_default_npm_registry(
                "https://mirror.mycorp.io/", "npm:__default__", "basic"
            )
            assert RuntimeSettings.get_default_npm_registry()[2] == "basic"
            # Empty URL clears all three keys.
            RuntimeSettings.set_default_npm_registry("", "leftover", "token")
            assert RuntimeSettings.get_default_npm_registry() == ("", "", "none")

    def test_default_npm_legacy_auth_kind_defaults_to_token(self) -> None:
        """Entries persisted before ``auth_kind`` was introduced keep working."""
        mem = _MemoryQSettings()
        mem.setValue("scripting/registries/default_npm", "https://mirror.mycorp.io/")
        mem.setValue("scripting/registries/default_npm_auth_ref", "npm:__default__")
        # No ``default_npm_auth_kind`` — simulating a settings file from
        # before the audit fix.
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            url, ref, kind = RuntimeSettings.get_default_npm_registry()
        assert url == "https://mirror.mycorp.io/"
        assert ref == "npm:__default__"
        assert kind == "token"

    def test_pypi_config_round_trip(self) -> None:
        mem = _MemoryQSettings()
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            assert RuntimeSettings.get_pypi_config() == {
                "index_url": "",
                "extra_index_url": "",
                "auth_ref": "",
                "auth_kind": "none",
            }
            RuntimeSettings.set_pypi_config(
                {
                    "index_url": "https://pypi.mycorp.io/simple/",
                    "extra_index_url": "",
                    "auth_ref": "pypi:default",
                    "auth_kind": "basic",
                }
            )
            cfg = RuntimeSettings.get_pypi_config()
            assert cfg["index_url"] == "https://pypi.mycorp.io/simple/"
            assert cfg["auth_ref"] == "pypi:default"
            assert cfg["auth_kind"] == "basic"
            # Empty values remove keys.
            RuntimeSettings.set_pypi_config(
                {
                    "index_url": "",
                    "extra_index_url": "",
                    "auth_ref": "",
                    "auth_kind": "none",
                }
            )
            assert RuntimeSettings.get_pypi_config() == {
                "index_url": "",
                "extra_index_url": "",
                "auth_ref": "",
                "auth_kind": "none",
            }

    def test_legacy_id_migration_is_persisted(self) -> None:
        """P4 fix: legacy entries without ``id`` get a stable persisted UUID.

        A legacy entry without ``id`` gets a UUID *and* the new ID is written
        back to QSettings so subsequent reads return the same ID. Without
        persistence, auth saved against a freshly-minted ID would orphan its
        secret on the next ``get_registries`` call.
        """
        import json as _json

        mem = _MemoryQSettings()
        # Seed pre-``id`` storage.
        mem.setValue(
            "scripting/registries/entries",
            _json.dumps(
                [
                    {
                        "scope": "@legacy",
                        "url": "https://npm.legacy/",
                        "kind": "npm",
                        "auth_kind": "none",
                        "auth_ref": "",
                    }
                ]
            ),
        )
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            first_read = RuntimeSettings.get_registries()
            second_read = RuntimeSettings.get_registries()
        assert first_read[0]["id"]
        assert first_read[0]["id"] == second_read[0]["id"], (
            "Migration UUID drifted across reads — would orphan secrets"
        )

    def test_pypi_indexes_round_trip(self) -> None:
        """N-index list round-trips through QSettings as JSON."""
        mem = _MemoryQSettings()
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            assert RuntimeSettings.get_pypi_indexes() == []
            indexes = [
                {
                    "id": "row-primary",
                    "url": "https://pypi.mycorp.io/simple/",
                    "auth_kind": "token",
                    "auth_ref": "pypi:row-primary",
                },
                {
                    "id": "row-extra",
                    "url": "https://pypi.backup.io/simple/",
                    "auth_kind": "none",
                    "auth_ref": "",
                },
            ]
            RuntimeSettings.set_pypi_indexes(cast(list[PyPIIndex], indexes))
            assert RuntimeSettings.get_pypi_indexes() == indexes
            # Order preserved across reads.
            assert RuntimeSettings.get_pypi_indexes()[0]["url"] == indexes[0]["url"]
            # Clearing wipes the JSON key.
            RuntimeSettings.set_pypi_indexes([])
            assert RuntimeSettings.get_pypi_indexes() == []

    def test_pypi_indexes_migrate_from_legacy_config(self) -> None:
        """Migrate legacy single-primary + single-extra keys to the list shape.

        On first read the migration is persisted so IDs stay stable.
        """
        mem = _MemoryQSettings()
        mem.setValue("scripting/pypi/index_url", "https://pypi.mycorp.io/simple/")
        mem.setValue("scripting/pypi/extra_index_url", "https://pypi.public/simple/")
        mem.setValue("scripting/pypi/auth_ref", "pypi:legacy")
        mem.setValue("scripting/pypi/auth_kind", "token")
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            first = RuntimeSettings.get_pypi_indexes()
        assert len(first) == 2
        assert first[0]["url"] == "https://pypi.mycorp.io/simple/"
        assert first[1]["url"] == "https://pypi.public/simple/"
        assert first[0]["auth_kind"] == "token"
        # Persisted: re-read returns the same IDs.
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            second = RuntimeSettings.get_pypi_indexes()
        assert [e["id"] for e in first] == [e["id"] for e in second]

    def test_set_pypi_indexes_clears_legacy_keys(self) -> None:
        """Persisting the new list wipes legacy single-pair keys.

        They must not shadow the list on subsequent reads.
        """
        mem = _MemoryQSettings()
        mem.setValue("scripting/pypi/index_url", "https://old.example/")
        mem.setValue("scripting/pypi/auth_ref", "pypi:legacy")
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            RuntimeSettings.set_pypi_indexes(
                [
                    {
                        "id": "new-row",
                        "url": "https://new.example/",
                        "auth_kind": "none",
                        "auth_ref": "",
                    }
                ]
            )
            assert RuntimeSettings.get_pypi_indexes()[0]["url"] == "https://new.example/"
        assert "scripting/pypi/index_url" not in mem._d
        assert "scripting/pypi/auth_ref" not in mem._d

    def test_pypi_legacy_auth_kind_defaults_to_token(self) -> None:
        """PyPI configs without ``auth_kind`` default to token semantics.

        PyPI configs persisted before ``auth_kind`` was introduced keep working
        with implicit ``token`` semantics.
        """
        mem = _MemoryQSettings()
        mem.setValue("scripting/pypi/index_url", "https://pypi.mycorp.io/simple/")
        mem.setValue("scripting/pypi/auth_ref", "pypi:default")
        # No ``auth_kind`` key — simulates settings from before B2 fix.
        with patch("services.scripting.runtime_settings._get_settings", return_value=mem):
            cfg = RuntimeSettings.get_pypi_config()
        assert cfg["auth_ref"] == "pypi:default"
        assert cfg["auth_kind"] == "token"
