"""Deno runtime binary manager — download, cache, and version check.

Manages a locally cached Deno binary under the user's data directory
(``~/.local/share/postmark/runtimes/`` on Linux, platform-appropriate
elsewhere).  The binary is downloaded on explicit user action only —
never automatically.

All public methods are ``@staticmethod`` to match the project service
pattern.
"""

from __future__ import annotations

import io
import logging
import os
import platform
import stat
import subprocess
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# -- Pinned Deno version -----------------------------------------------
DENO_VERSION = "2.1.4"

# -- Platform detection -------------------------------------------------

_PLATFORM_MAP: dict[str, str] = {
    "Linux-x86_64": "x86_64-unknown-linux-gnu",
    "Linux-aarch64": "aarch64-unknown-linux-gnu",
    "Darwin-x86_64": "x86_64-apple-darwin",
    "Darwin-arm64": "aarch64-apple-darwin",
    "Windows-AMD64": "x86_64-pc-windows-msvc",
    "Windows-x86_64": "x86_64-pc-windows-msvc",
}


def _platform_triple() -> str:
    """Return the Deno target triple for the current OS and architecture."""
    system = platform.system()
    machine = platform.machine()
    key = f"{system}-{machine}"
    triple = _PLATFORM_MAP.get(key)
    if triple is None:
        msg = f"Unsupported platform: {key}"
        raise RuntimeError(msg)
    return triple


def _archive_ext() -> str:
    """Return the archive extension for the current OS."""
    return ".zip"


# -- Download URL -------------------------------------------------------

_DOWNLOAD_TEMPLATE = (
    "https://github.com/denoland/deno/releases/download/v{version}/deno-{triple}{ext}"
)


class DenoManager:
    """Manage a locally cached Deno binary.

    All methods are static.  The binary lives at
    ``runtime_dir() / "deno"`` (or ``deno.exe`` on Windows).
    """

    @staticmethod
    def runtime_dir() -> Path:
        """Return the directory where the Deno binary is cached.

        Uses ``XDG_DATA_HOME`` on Linux, ``~/Library/Application Support``
        on macOS, and ``%LOCALAPPDATA%`` on Windows.
        """
        system = platform.system()
        if system == "Linux":
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        elif system == "Darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "postmark" / "runtimes" / f"deno-{DENO_VERSION}"

    @staticmethod
    def managed_deno_path() -> Path | None:
        """Return the path to the **managed cache** binary only, or ``None``.

        This is the user-downloaded or extracted Deno from :meth:`download` —
        not a PATH or user-configured executable.  Full resolution
        (settings, ``PATH``, then managed) lives in
        :class:`services.scripting.runtime_settings.RuntimeSettings`.
        """
        binary = "deno.exe" if platform.system() == "Windows" else "deno"
        path = DenoManager.runtime_dir() / binary
        if path.is_file():
            return path
        return None

    @staticmethod
    def deno_path() -> Path | None:
        """Return the path to the cached (managed) Deno binary, or ``None``.

        Same as :meth:`managed_deno_path` (name kept for call sites that only
        care about the managed download cache, not a fully resolved path).
        """
        return DenoManager.managed_deno_path()

    @staticmethod
    def is_available() -> bool:
        """Return ``True`` if a managed cached Deno binary exists and is executable."""
        path = DenoManager.managed_deno_path()
        if path is None:
            return False
        return os.access(path, os.X_OK)

    @staticmethod
    def deno_version() -> str | None:
        """Run ``deno --version`` and return the version string, or ``None``."""
        path = DenoManager.managed_deno_path()
        if path is None:
            return None
        try:
            result = subprocess.run(
                [str(path), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip().splitlines()[0]
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None

    @staticmethod
    def download_url() -> str:
        """Return the GitHub release URL for the current platform."""
        return _DOWNLOAD_TEMPLATE.format(
            version=DENO_VERSION,
            triple=_platform_triple(),
            ext=_archive_ext(),
        )

    @staticmethod
    def download(progress_callback: Callable[[int, int], None] | None = None) -> Path:
        """Download and extract the Deno binary to :meth:`runtime_dir`.

        *progress_callback* is called with ``(bytes_received, total_bytes)``
        during the download.  ``total_bytes`` may be ``0`` if the server
        does not send ``Content-Length``.

        Returns the path to the extracted binary.

        Raises :class:`RuntimeError` on download or extraction failure.
        """
        url = DenoManager.download_url()
        dest_dir = DenoManager.runtime_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)

        binary_name = "deno.exe" if platform.system() == "Windows" else "deno"
        dest_path = dest_dir / binary_name

        logger.info("Downloading Deno %s from %s", DENO_VERSION, url)

        try:
            req = Request(url, headers={"User-Agent": "Postmark-Desktop"})
            with urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                data = io.BytesIO()
                received = 0
                chunk_size = 65536

                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    data.write(chunk)
                    received += len(chunk)
                    if progress_callback:
                        progress_callback(received, total)

        except Exception as exc:
            msg = f"Failed to download Deno: {exc}"
            raise RuntimeError(msg) from exc

        # Extract binary from zip archive.
        try:
            data.seek(0)
            with zipfile.ZipFile(data) as zf:
                # Find the deno binary inside the archive.
                names = zf.namelist()
                deno_entry = None
                for name in names:
                    if name.endswith(binary_name) or name == binary_name:
                        deno_entry = name
                        break
                if deno_entry is None:
                    msg = f"Deno binary not found in archive (contents: {names})"
                    raise RuntimeError(msg)

                # Extract to destination.
                with zf.open(deno_entry) as src, open(dest_path, "wb") as dst:
                    dst.write(src.read())

        except zipfile.BadZipFile as exc:
            msg = f"Downloaded archive is corrupt: {exc}"
            raise RuntimeError(msg) from exc

        # Make executable on Unix.
        if platform.system() != "Windows":
            dest_path.chmod(dest_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

        logger.info("Deno %s installed to %s", DENO_VERSION, dest_path)
        return dest_path

    @staticmethod
    def remove() -> None:
        """Delete the cached Deno binary and its directory."""
        import shutil

        dest_dir = DenoManager.runtime_dir()
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
            logger.info("Removed Deno runtime at %s", dest_dir)
