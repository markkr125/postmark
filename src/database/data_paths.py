"""Shared path helpers for the project tree and per-user Postmark data."""

from __future__ import annotations

import os
import platform
import uuid
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


def user_ai_conversations_root() -> Path:
    """Return ``postmark_user_data_dir() / "ai_conversations"`` (created if missing)."""
    root = postmark_user_data_dir() / "ai_conversations"
    root.mkdir(parents=True, exist_ok=True)
    return root


def user_ai_attachments_root() -> Path:
    """Return ``postmark_user_data_dir() / "ai_attachments"`` (created if missing)."""
    root = postmark_user_data_dir() / "ai_attachments"
    root.mkdir(parents=True, exist_ok=True)
    return root


def session_attachments_dir(session_id: str) -> Path:
    """Per-session attachment copies, kept out of the SDK's persistence directory.

    The SDK scans its own session directory for event files and warns about
    anything it does not recognise, so user files live in a sibling root.
    """
    return user_ai_attachments_root() / uuid.UUID(session_id).hex


def session_disk_dir(session_id: str) -> Path:
    """Per-session SDK persistence dir: ``<base>/<uuid.hex>/`` (matches SDK layout)."""
    return user_ai_conversations_root() / uuid.UUID(session_id).hex
