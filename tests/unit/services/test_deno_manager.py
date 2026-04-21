"""Tests for the DenoManager runtime binary manager."""

from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.scripting.deno_manager import DENO_VERSION, DenoManager


class TestDenoManagerPaths:
    """Test path computation methods."""

    def test_runtime_dir_contains_version(self) -> None:
        result = DenoManager.runtime_dir()
        assert DENO_VERSION in str(result)
        assert "postmark" in str(result)

    def test_deno_path_returns_none_when_missing(self, tmp_path: Path) -> None:
        with patch.object(DenoManager, "runtime_dir", return_value=tmp_path):
            assert DenoManager.deno_path() is None

    def test_deno_path_returns_path_when_exists(self, tmp_path: Path) -> None:
        binary = tmp_path / "deno"
        binary.write_text("fake")
        with patch.object(DenoManager, "runtime_dir", return_value=tmp_path):
            assert DenoManager.deno_path() == binary

    def test_is_available_false_when_missing(self, tmp_path: Path) -> None:
        with patch.object(DenoManager, "runtime_dir", return_value=tmp_path):
            assert DenoManager.is_available() is False

    def test_is_available_true_when_executable(self, tmp_path: Path) -> None:
        binary = tmp_path / "deno"
        binary.write_text("fake")
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
        with patch.object(DenoManager, "runtime_dir", return_value=tmp_path):
            assert DenoManager.is_available() is True


class TestDenoManagerDownloadUrl:
    """Test download URL construction."""

    def test_url_contains_version(self) -> None:
        url = DenoManager.download_url()
        assert DENO_VERSION in url

    def test_url_starts_with_github(self) -> None:
        url = DenoManager.download_url()
        assert url.startswith("https://github.com/denoland/deno/releases/")


class TestDenoManagerVersion:
    """Test version checking."""

    def test_version_returns_none_when_missing(self, tmp_path: Path) -> None:
        with patch.object(DenoManager, "runtime_dir", return_value=tmp_path):
            assert DenoManager.deno_version() is None


class TestDenoManagerDownload:
    """Test download with mocked HTTP."""

    def test_download_creates_binary(self, tmp_path: Path) -> None:
        """Simulate a zip download containing a 'deno' binary."""
        import io
        import zipfile

        # Create a fake zip in memory.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("deno", "#!/bin/sh\necho fake deno")
        zip_bytes = buf.getvalue()

        # Mock urlopen to return the fake zip.
        mock_response = MagicMock()
        mock_response.read.side_effect = [zip_bytes, b""]
        mock_response.headers = {"Content-Length": str(len(zip_bytes))}
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        dest = tmp_path / "runtimes" / f"deno-{DENO_VERSION}"

        with (
            patch.object(DenoManager, "runtime_dir", return_value=dest),
            patch("services.scripting.deno_manager.urlopen", return_value=mock_response),
        ):
            progress_calls: list[tuple[int, int]] = []
            path = DenoManager.download(
                progress_callback=lambda r, t: progress_calls.append((r, t)),
            )

        assert path.exists()
        assert path.name == "deno"
        assert len(progress_calls) > 0

    def test_download_raises_on_bad_zip(self, tmp_path: Path) -> None:
        """Corrupt zip data should raise RuntimeError."""
        mock_response = MagicMock()
        mock_response.read.side_effect = [b"not a zip", b""]
        mock_response.headers = {"Content-Length": "9"}
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        dest = tmp_path / "runtimes" / f"deno-{DENO_VERSION}"

        with (
            patch.object(DenoManager, "runtime_dir", return_value=dest),
            patch("services.scripting.deno_manager.urlopen", return_value=mock_response),
            pytest.raises(RuntimeError, match="corrupt"),
        ):
            DenoManager.download()


class TestDenoManagerRemove:
    """Test removal of cached binary."""

    def test_remove_deletes_directory(self, tmp_path: Path) -> None:
        dest = tmp_path / "runtimes" / f"deno-{DENO_VERSION}"
        dest.mkdir(parents=True)
        (dest / "deno").write_text("fake")

        with patch.object(DenoManager, "runtime_dir", return_value=dest):
            DenoManager.remove()

        assert not dest.exists()

    def test_remove_noop_when_missing(self, tmp_path: Path) -> None:
        dest = tmp_path / "runtimes" / f"deno-{DENO_VERSION}"
        with patch.object(DenoManager, "runtime_dir", return_value=dest):
            DenoManager.remove()  # should not raise
