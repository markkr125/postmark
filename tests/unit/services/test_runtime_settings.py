"""Unit tests for :mod:`services.scripting.runtime_settings`."""

from __future__ import annotations

import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.scripting.runtime_settings import (
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
