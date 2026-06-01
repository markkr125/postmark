"""Shared path helpers for the project tree and per-user Postmark data."""

from __future__ import annotations

import os
import platform
from pathlib import Path


def project_root() -> Path:
    """Return the repository root (parent of ``src/``).

    This module lives at ``src/database/data_paths.py``, so the repo root is
    two levels up — not ``parents[1]`` (that would be ``src/`` alone).
    """
    return Path(__file__).resolve().parents[2]


def postmark_user_data_dir() -> Path:
    """Return the OS-native Postmark user-data directory (created if missing).

    Linux: ``$XDG_DATA_HOME/postmark`` or ``~/.local/share/postmark``
    macOS: ``~/Library/Application Support/postmark``
    Windows: ``%LOCALAPPDATA%/postmark``
    """
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    root = base / "postmark"
    root.mkdir(parents=True, exist_ok=True)
    return root


def user_history_root() -> Path:
    """Return ``postmark_user_data_dir() / "history"`` (created if missing)."""
    root = postmark_user_data_dir() / "history"
    root.mkdir(parents=True, exist_ok=True)
    return root
