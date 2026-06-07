"""Tests for database.data_paths helpers."""

from __future__ import annotations

import uuid

import database.data_paths as data_paths
from database.data_paths import (
    project_root,
    session_disk_dir,
    user_ai_conversations_root,
    user_history_root,
)
from openhands.sdk import BaseConversation


def test_project_root_is_repo_not_src() -> None:
    """SQLite and project ``data/`` live at the repo root, not under ``src/``."""
    root = project_root()
    assert root.name != "src"
    assert (root / "src" / "main.py").is_file()
    assert (root / "data" / "database").is_dir()


def test_user_history_under_postmark_user_data_dir(tmp_path, monkeypatch) -> None:
    """History bodies/snapshots use the OS user-data dir, not the project tree."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    history = user_history_root()
    assert history == tmp_path / "postmark" / "history"
    assert data_paths.postmark_user_data_dir() == tmp_path / "postmark"
    assert project_root() / "data" / "database" != history


def test_user_ai_conversations_under_postmark_user_data_dir(tmp_path, monkeypatch) -> None:
    """AI conversation SDK state uses the OS user-data dir, not the project tree."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    root = user_ai_conversations_root()
    assert root == tmp_path / "postmark" / "ai_conversations"
    assert root.is_dir()


def test_session_disk_dir_matches_sdk_persistence_layout(tmp_path, monkeypatch) -> None:
    """``session_disk_dir`` must match OpenHands ``get_persistence_dir`` (hex, no dashes)."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    session_id = str(uuid.uuid4())
    expected = BaseConversation.get_persistence_dir(
        user_ai_conversations_root(),
        uuid.UUID(session_id),
    )
    assert str(session_disk_dir(session_id)) == expected
    assert session_disk_dir(session_id).name == uuid.UUID(session_id).hex
